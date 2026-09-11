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


def live_frame(dossier: Dict[str, Any], *, minute: Optional[int], score_home: Optional[int],
               score_away: Optional[int], red_home: int = 0, red_away: int = 0,
               atlas: Optional[Dict[str, Any]] = None, home: Optional[str] = None,
               away: Optional[str] = None) -> Dict[str, Any]:
    """{hazard, hazard_source, p4_model} per lo stato live corrente (None se ignoto)."""
    out: Dict[str, Any] = {"hazard": None, "hazard_source": "none", "p4_model": None}
    if minute is None or score_home is None or score_away is None:
        return out
    goals = int(score_home) + int(score_away)
    try:
        if atlas is not None:
            from Betfair.stream.scalper.theta_bot import hazard_lookup

            p, src = hazard_lookup(atlas, float(minute), goals, dossier.get("league_id"), home, away)
            out["hazard"] = round(float(p), 4) if p is not None else None
            out["hazard_source"] = src
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.dossier] hazard KO: %s", str(ex)[:120])
    try:
        lh, la = dossier.get("lambda_home"), dossier.get("lambda_away")
        if lh and la:
            from Betfair.omega.omega_model import LiveState, score_probs

            state = LiveState(minute=int(minute), score_home=int(score_home), score_away=int(score_away),
                              red_home=int(red_home or 0), red_away=int(red_away or 0))
            grid = score_probs(lh_pre=float(lh), la_pre=float(la), rho=float(dossier.get("rho") or DEFAULT_RHO),
                               state=state, league_id=dossier.get("league_id"), half=False)
            out["p4_model"] = _p_total(grid, 4)
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.dossier] p4_model KO: %s", str(ex)[:120])
    return out
