"""dossier — "conoscere tutto della partita" per Mike, SENZA chiamate Betfair.

Pre-match (una volta, al primo aggancio): ponte evento→fixture (live_follow),
λ Dixon-Coles per squadra dal DB (``fixture_predictions``), ρ di lega, P(tot=4)
pre-match dalla griglia residua, calibrati Poisson/ML se presenti.
In-play (ogni ciclo): P(tot=4 | minuto, punteggio, rossi) dalla griglia residua
di Omega, hazard di gol nei prossimi 3' dall'Atlante (theta_bot).

Tutto FAIL-SAFE: dato mancante → None, mai un'eccezione verso il bot.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("mike.dossier")

DEFAULT_RHO = -0.13
MAX_GOALS = 8


def load_atlas() -> Optional[Dict[str, Any]]:
    try:
        from Betfair.stream.scalper.theta_bot import load_hazard_atlas

        return load_hazard_atlas()
    except Exception as ex:  # noqa: BLE001 — senza atlante Mike copre subito (fail-safe)
        logger.warning("[mike.dossier] atlante hazard non caricato: %s", str(ex)[:120])
        return None


def _p_total(grid: Dict[tuple, float], total: int) -> float:
    return round(sum(p for (h, a), p in grid.items() if h + a == total), 4)


def p4_from_lambdas(lh: Optional[float], la: Optional[float], rho: float) -> Optional[float]:
    if lh is None or la is None or lh <= 0 or la <= 0:
        return None
    try:
        from Betfair.omega.omega_model import residual_grid

        grid = residual_grid(float(lh), float(la), float(rho), MAX_GOALS, dixon_coles=True)
        return _p_total(grid, 4)
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.dossier] p4_from_lambdas KO: %s", str(ex)[:120])
        return None


def build_prematch(event_id: str, db: Any) -> Dict[str, Any]:
    """Dossier pre-match: {fixture_id, league_id, lambda_home, lambda_away, rho,
    p4_pre, p_under35_cal, p_over45_cal, source}. Chiavi None se non disponibili."""
    out: Dict[str, Any] = {"fixture_id": None, "league_id": None, "lambda_home": None,
                           "lambda_away": None, "rho": DEFAULT_RHO, "p4_pre": None,
                           "p_under35_cal": None, "p_over45_cal": None, "source": "none"}
    try:
        fid = db.fixture_id_for_event(str(event_id))
        out["fixture_id"] = fid
        lam = db.fixture_lambdas(fid) if fid is not None else None
        if lam:
            out["lambda_home"], out["lambda_away"] = float(lam[0]), float(lam[1])
            out["league_id"] = lam[2] if len(lam) > 2 else None
            out["source"] = "fixture"
        an = db.fixture_analysis(fid) if fid is not None else None
        if isinstance(an, dict):
            inputs = an.get("inputs") or {}
            rho = inputs.get("dc_rho")
            if isinstance(rho, (int, float)):
                out["rho"] = float(rho)
            mk = an.get("markets_calibrated") or an.get("markets") or {}
            o35 = (mk.get("over_3_5") or {}) if isinstance(mk, dict) else {}
            if isinstance(o35, dict) and o35.get("True") is not None:
                out["p_under35_cal"] = round(1.0 - float(o35["True"]), 4)
        out["p4_pre"] = p4_from_lambdas(out["lambda_home"], out["lambda_away"], out["rho"])
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.dossier] build_prematch %s KO: %s", event_id, str(ex)[:120])
    return out


def combine_hazard(atlas_p: Optional[float], model_p: Optional[float], pressure_mult: float = 1.0) -> Optional[float]:
    """Hazard 3' PRUDENTE: il MASSIMO fra Atlante empirico e modello λ-residue,
    quest'ultimo amplificato dalla pressione (corner/cartellini, ≤ ×1.25).
    None solo se entrambe le fonti mancano (→ l'engine copre subito)."""
    vals = []
    if atlas_p is not None:
        vals.append(float(atlas_p))
    if model_p is not None:
        vals.append(min(1.0, float(model_p) * max(1.0, float(pressure_mult))))
    return round(max(vals), 4) if vals else None


def cover_gain_pct(p_over_now: Optional[float], p_over_later: Optional[float]) -> Optional[float]:
    """Risparmio atteso (%) sulla size di copertura se si aspetta senza gol:
    X ∝ 1/(quota−1) con quota equa = 1/P(Over 4.5) → X_later/X_now = (1/p_now−1)/(1/p_later−1)."""
    if not p_over_now or not p_over_later or p_over_now >= 1 or p_over_later >= 1:
        return None
    x_now = 1.0 / (1.0 / p_over_now - 1.0)
    x_later = 1.0 / (1.0 / p_over_later - 1.0)
    return round(max(0.0, (1.0 - x_later / x_now) * 100.0), 2)


def _p_le(grid: Dict[tuple, float], total: int) -> float:
    return sum(p for (h, a), p in grid.items() if h + a <= total)


def model_probs_from_grids(grid_now: Dict[tuple, float], grid_later: Dict[tuple, float],
                           grid_goal_home: Dict[tuple, float], grid_goal_away: Dict[tuple, float],
                           w_home: float) -> Dict[str, float]:
    """P(Under 3.5) / P(Over 4.5) / P(Under 4.5) di modello in tre scenari:
    ``_now`` adesso, ``_later`` fra N minuti senza gol, ``_goal`` subito dopo un gol
    (media pesata gol casa/trasferta). Chiavi: u35_*, o45_*, u45_*."""
    w = min(1.0, max(0.0, float(w_home)))

    def trio(g: Dict[tuple, float]) -> tuple:
        u35 = _p_le(g, 3)
        u45 = _p_le(g, 4)
        return u35, 1.0 - u45, u45

    n, l = trio(grid_now), trio(grid_later)
    gh, ga = trio(grid_goal_home), trio(grid_goal_away)
    g = tuple(w * x + (1.0 - w) * y for x, y in zip(gh, ga))
    out: Dict[str, float] = {}
    for name, (u35, o45, u45) in (("now", n), ("later", l), ("goal", g)):
        out[f"u35_{name}"] = round(u35, 5)
        out[f"o45_{name}"] = round(o45, 5)
        out[f"u45_{name}"] = round(u45, 5)
    return out


def live_frame(dossier: Dict[str, Any], *, minute: Optional[int], score_home: Optional[int],
               score_away: Optional[int], red_home: int = 0, red_away: int = 0,
               atlas: Optional[Dict[str, Any]] = None, home: Optional[str] = None,
               away: Optional[str] = None, payload: Optional[Dict[str, Any]] = None,
               wait_step_min: int = 5) -> Dict[str, Any]:
    """{hazard, hazard_atlas, hazard_model, hazard_source, pressure, p4_model,
    p_over45_model, cover_gain_pct} per lo stato live corrente (None se ignoto).

    hazard = max(Atlante empirico, modello λ-residue × pressione): la fonte piu'
    prudente comanda. cover_gain_pct = quanto costerebbe di meno la copertura fra
    ``wait_step_min`` minuti senza gol (modello): sotto soglia, l'engine copre subito.
    """
    out: Dict[str, Any] = {"hazard": None, "hazard_atlas": None, "hazard_model": None,
                           "hazard_source": "none", "pressure": 1.0, "p4_model": None,
                           "p_over45_model": None, "cover_gain_pct": None, "model_probs": None}
    if minute is None or score_home is None or score_away is None:
        return out
    goals = int(score_home) + int(score_away)
    try:
        if atlas is not None:
            from Betfair.stream.scalper.theta_bot import hazard_lookup

            p, src = hazard_lookup(atlas, float(minute), goals, dossier.get("league_id"), home, away)
            out["hazard_atlas"] = round(float(p), 4) if p is not None else None
            out["hazard_source"] = src
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.dossier] hazard atlante KO: %s", str(ex)[:120])
    try:
        if payload:
            from Betfair.safe_strategy.pressure import pressure_from_payload

            mh, ma = pressure_from_payload(payload)
            out["pressure"] = round(max(float(mh), float(ma)), 3)
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.dossier] pressione KO: %s", str(ex)[:120])
    lh, la = dossier.get("lambda_home"), dossier.get("lambda_away")
    if lh and la:
        try:
            from Betfair.stream.engine.live_engine_pro import event_goal_hazard

            hz = event_goal_hazard(score_home=int(score_home), score_away=int(score_away), minute=int(minute),
                                   prematch_lambda_home=float(lh), prematch_lambda_away=float(la),
                                   league_id=dossier.get("league_id"), red_home=int(red_home or 0),
                                   red_away=int(red_away or 0), horizon_min=3.0)
            if hz and hz.get("p_next") is not None:
                out["hazard_model"] = round(float(hz["p_next"]), 4)
        except Exception as ex:  # noqa: BLE001
            logger.debug("[mike.dossier] hazard modello KO: %s", str(ex)[:120])
        try:
            from Betfair.omega.omega_model import LiveState, score_probs

            rho = float(dossier.get("rho") or DEFAULT_RHO)
            state = LiveState(minute=int(minute), score_home=int(score_home), score_away=int(score_away),
                              red_home=int(red_home or 0), red_away=int(red_away or 0))
            grid = score_probs(lh_pre=float(lh), la_pre=float(la), rho=rho, state=state,
                               league_id=dossier.get("league_id"), half=False)
            out["p4_model"] = _p_total(grid, 4)
            p_over_now = round(sum(p for (h, a), p in grid.items() if h + a >= 5), 4)
            out["p_over45_model"] = p_over_now
            later = LiveState(minute=min(90, int(minute) + int(wait_step_min)), score_home=int(score_home),
                              score_away=int(score_away), red_home=int(red_home or 0), red_away=int(red_away or 0))
            grid_l = score_probs(lh_pre=float(lh), la_pre=float(la), rho=rho, state=later,
                                 league_id=dossier.get("league_id"), half=False)
            p_over_later = round(sum(p for (h, a), p in grid_l.items() if h + a >= 5), 4)
            out["cover_gain_pct"] = cover_gain_pct(p_over_now, p_over_later)
            # scenario "gol adesso": media pesata (quota λ) fra gol casa e gol trasferta
            wh = float(lh) / (float(lh) + float(la))
            gh = LiveState(minute=int(minute), score_home=int(score_home) + 1, score_away=int(score_away),
                           red_home=int(red_home or 0), red_away=int(red_away or 0))
            ga = LiveState(minute=int(minute), score_home=int(score_home), score_away=int(score_away) + 1,
                           red_home=int(red_home or 0), red_away=int(red_away or 0))
            grid_gh = score_probs(lh_pre=float(lh), la_pre=float(la), rho=rho, state=gh,
                                  league_id=dossier.get("league_id"), half=False)
            grid_ga = score_probs(lh_pre=float(lh), la_pre=float(la), rho=rho, state=ga,
                                  league_id=dossier.get("league_id"), half=False)
            out["model_probs"] = model_probs_from_grids(grid, grid_l, grid_gh, grid_ga, wh)
        except Exception as ex:  # noqa: BLE001
            logger.debug("[mike.dossier] p4_model KO: %s", str(ex)[:120])
    out["hazard"] = combine_hazard(out["hazard_atlas"], out["hazard_model"], out["pressure"])
    return out
