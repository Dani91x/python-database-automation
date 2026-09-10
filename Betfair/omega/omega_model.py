"""Omega v2 — MODELLO di probabilità dei risultati esatti CONDIZIONATO allo stato
LIVE della partita (09/09/2026 sera).

La regola di selezione di Omega non è più "la quota lay più alta" ma "il
risultato con la PROBABILITÀ PIÙ BASSA di verificarsi secondo i NOSTRI dati",
dentro una fascia di prezzo (che limita la liability) e con liquidità reale.

Catena, tutta riusata dallo stack esistente:
  1. λ pre-match per squadra: ``fixture_predictions`` (tactical_engine / Poisson
     xG ibrido DC) via ``Betfair.stream.db.get_fixture_prematch_lambdas``;
     fallback: quote 1X2 pre-KO congelate dallo scanner → devig → split
     (``live_engine.estimate_prematch_lambdas``).
  2. λ RESIDUI live: ``live_engine.inplay_residual_rates`` (CDF reale del tempo
     residuo per lega, stato di gioco, cartellini rossi, intensità di lega).
  3. Griglia Poisson+Dixon-Coles sui GOL RESIDUI (ρ per lega da
     ``live_engine_pro.rho_for_league``), traslata sul punteggio corrente:
     P(finale = H-A) = P(residuo = (H−h, A−a)).
     Per il mercato HALF TIME SCORE l'orizzonte è il 45′: i λ residui vengono
     scalati alla frazione di gioco che resta nel primo tempo.
  4. Selezione: tra i runner ACTIVE con lay in [price_min, price_max], liquidità
     ≥ max(min_liquidity, size necessaria), distanza ≥ min_goal_distance gol dal
     punteggio corrente, P_modello ≤ p_max e P_modello < P_implicita (1/quota):
     il MINIMO di P_modello; a parità, prezzo più basso (meno liability), poi
     liquidità. Gli aggregati ("Any Other…") non sono mai candidati.

Tutto puro: nessuna rete, nessun DB. I lettori di λ e ρ sono iniettati dal
servizio (vedi ``omega_service._prematch_lambdas``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from Betfair.omega import omega_engine as E

# gol attesi totali quando l'unica fonte sono le quote 1X2 (media Europa)
DEFAULT_TOTAL_GOALS = 2.6
# ρ Dixon-Coles di default (stesso del motore Poisson) se la lega non è calibrata
DEFAULT_RHO = -0.13
# nel primo tempo si segna meno che nel secondo (~45% dei gol): scala dei λ
# residui quando l'orizzonte è l'intervallo
FIRST_HALF_INTENSITY = 0.90
MAX_GOALS_GRID = 10
MAX_GOALS_GRID_HT = 6


@dataclass(frozen=True)
class ModelSelection:
    """Runner scelto dal modello + numeri di audit (finiscono in trade.meta)."""

    selection_id: int
    name: str
    price: float                 # tick Betfair valido
    lay_size_available: float
    p_model: float               # probabilità del modello che il risultato esca (CALIBRATA se c'è il calibratore)
    p_implied: float             # 1/quota (probabilità implicita del mercato)
    p_model_raw: Optional[float] = None   # P grezza del modello (audit); None = uguale a p_model

    @property
    def raw(self) -> float:
        return self.p_model if self.p_model_raw is None else self.p_model_raw

    @property
    def edge(self) -> float:
        """Quanto il mercato sovraprezza il risultato rispetto al modello."""
        return self.p_implied - self.p_model

    def as_selection(self) -> E.Selection:
        return E.Selection(selection_id=self.selection_id, name=self.name,
                           price=self.price, lay_size_available=self.lay_size_available)


@dataclass(frozen=True)
class LiveState:
    minute: int
    score_home: int
    score_away: int
    red_home: int = 0
    red_away: int = 0


def devig_1x2(back_home: float, back_draw: float, back_away: float) -> Optional[Tuple[float, float, float]]:
    """Probabilità 1X2 dalle quote back (normalizzazione dell'overround)."""
    try:
        inv = [1.0 / float(x) for x in (back_home, back_draw, back_away)]
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if any(v <= 0 or not math.isfinite(v) for v in inv):
        return None
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def lambdas_from_pre_ko(pre_ko: Optional[dict], total_goals: float = DEFAULT_TOTAL_GOALS) -> Optional[Tuple[float, float]]:
    """(λ_casa, λ_trasferta) dalle quote 1X2 pre-KO congelate dallo scanner."""
    if not isinstance(pre_ko, dict):
        return None
    probs = devig_1x2(pre_ko.get("home"), pre_ko.get("draw"), pre_ko.get("away"))
    if probs is None:
        return None
    from Betfair.stream.engine.live_engine import estimate_prematch_lambdas
    return estimate_prematch_lambdas(probs[0], probs[2], expected_total_goals=total_goals)


def residual_lambdas(lh_pre: float, la_pre: float, state: LiveState,
                     league_id: Optional[int], *, half: bool) -> Tuple[float, float]:
    """λ residui (fino al 90′, o al 45′ se ``half``) dallo stato live."""
    from Betfair.stream.engine.live_engine import inplay_residual_rates
    lh, la = inplay_residual_rates(
        lh_pre, la_pre, state.minute, state.score_home, state.score_away,
        red_home=state.red_home, red_away=state.red_away, league_id=league_id,
    )
    if half:
        # frazione del residuo che cade nel primo tempo, ridotta dall'intensità 1T
        left_ht = max(0.0, 45.0 - float(state.minute))
        left_ft = max(1.0, 90.0 - float(state.minute))
        k = min(1.0, left_ht / left_ft) * FIRST_HALF_INTENSITY
        lh, la = lh * k, la * k
    return max(0.001, lh), max(0.001, la)


def _dc_tau(h: int, a: int, lh: float, la: float, rho: float) -> float:
    if h == 0 and a == 0:
        return 1.0 - lh * la * rho
    if h == 1 and a == 0:
        return max(0.0, 1.0 + la * rho)
    if h == 0 and a == 1:
        return max(0.0, 1.0 + lh * rho)
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


def residual_grid(lh: float, la: float, rho: float, max_goals: int, *, dixon_coles: bool) -> Dict[Tuple[int, int], float]:
    """Distribuzione dei GOL RESIDUI (h, a), normalizzata sulla griglia troncata.
    La correzione Dixon-Coles ha senso solo sulle celle basse di una partita che
    parte da 0-0: applicata solo se ``dixon_coles`` (punteggio corrente 0-0)."""
    grid: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for h in range(max_goals + 1):
        ph = math.exp(-lh) * lh ** h / math.factorial(h)
        for a in range(max_goals + 1):
            p = ph * math.exp(-la) * la ** a / math.factorial(a)
            if dixon_coles and h <= 1 and a <= 1:
                p *= _dc_tau(h, a, lh, la, rho)
            grid[(h, a)] = p
            total += p
    if total <= 0:
        return {}
    return {k: v / total for k, v in grid.items()}


def score_probs(*, lh_pre: float, la_pre: float, rho: float, state: LiveState,
                league_id: Optional[int], half: bool) -> Dict[Tuple[int, int], float]:
    """P(risultato FINALE = (H, A)) per il mercato scelto (FT, o HT se ``half``),
    condizionata a minuto/punteggio/rossi correnti."""
    lh, la = residual_lambdas(lh_pre, la_pre, state, league_id, half=half)
    grid = residual_grid(lh, la, rho, MAX_GOALS_GRID_HT if half else MAX_GOALS_GRID,
                         dixon_coles=(state.score_home == 0 and state.score_away == 0))
    return {(state.score_home + h, state.score_away + a): p for (h, a), p in grid.items()}


# ---------------------------------------------------------------------------
# CALIBRAZIONE (10/09): la P del modello passa dal calibratore condiviso di
# Betfair/safe_strategy/calibration.py (``Calibrator.load(path)`` /
# ``.apply(p, family, minute)``, famiglie 'cs' = Correct Score, 'hts' = Half
# Time Score) SE il modulo esiste. Import GUARDATO: modulo assente/rotto → P
# grezza, mai un crash della selezione. Cache per processo con TTL breve.
# ---------------------------------------------------------------------------
CALIBRATION_FAMILY_FT = "cs"
CALIBRATION_FAMILY_HT = "hts"
_CALIBRATION_TTL_S = 600.0
_CALIBRATOR_CACHE: Dict[str, Tuple[float, Any]] = {}   # path → (ts caricamento, calibratore|None)


def reset_calibration_cache() -> None:
    _CALIBRATOR_CACHE.clear()


def load_calibrator(path: Optional[str] = None, *, now_ts: Optional[float] = None) -> Optional[Any]:
    """Calibratore condiviso, o None (modulo assente, load fallito). Mai solleva."""
    import time as _time
    key = str(path or "")
    ts = float(now_ts) if now_ts is not None else _time.time()
    cached = _CALIBRATOR_CACHE.get(key)
    if cached is not None and ts - cached[0] < _CALIBRATION_TTL_S:
        return cached[1]
    cal = None
    try:
        from Betfair.safe_strategy import calibration as _cal_mod   # agent W-A
        klass = getattr(_cal_mod, "Calibrator", None)
        loader = getattr(klass, "load", None)
        if callable(loader):
            cal = loader(key) if key else loader()
            if not callable(getattr(cal, "apply", None)):
                cal = None
    except Exception:  # noqa: BLE001 - modulo assente o rotto: selezione grezza
        cal = None
    _CALIBRATOR_CACHE[key] = (ts, cal)
    return cal


def apply_calibration(p: float, family: str, minute: int, calibrator: Any) -> float:
    """P calibrata; la grezza se il calibratore manca, esplode o dà un valore assurdo."""
    if calibrator is None:
        return float(p)
    try:
        q = float(calibrator.apply(float(p), str(family), int(minute)))
    except Exception:  # noqa: BLE001
        return float(p)
    if not math.isfinite(q) or q < 0.0 or q > 1.0:
        return float(p)
    return q


def select_by_model(
    runners: list,
    probs: Dict[Tuple[int, int], float],
    *,
    state: LiveState,
    price_min: float,
    price_max: float,
    min_liquidity: float,
    p_max: float,
    size_needed: float = 0.0,
    min_goal_distance: int = 2,
    calibrator: Any = None,
    family: str = CALIBRATION_FAMILY_FT,
) -> Optional[ModelSelection]:
    """Runner con la probabilità di modello PIÙ BASSA che rispetti tutti i vincoli.
    ``runners``: ``omega_engine.ScoreRunner`` (lay_price/lay_size). None se nessuno.
    Con ``calibrator`` i vincoli e l'ordinamento usano la P CALIBRATA
    (``p_model``); la grezza resta in ``p_model_raw`` per l'audit."""
    need = max(float(min_liquidity), float(size_needed))
    best: Optional[ModelSelection] = None
    for r in runners:
        price = getattr(r, "lay_price", None)
        if price is None or price < price_min or price > price_max:
            continue
        if float(getattr(r, "lay_size", 0.0) or 0.0) < need:
            continue
        parsed = E.parse_scoreline(getattr(r, "name", "") or "")
        if parsed is None:
            continue                      # mai gli aggregati
        h, a = parsed
        if h < state.score_home or a < state.score_away:
            continue                      # irraggiungibile
        if (h - state.score_home) + (a - state.score_away) < min_goal_distance:
            continue                      # troppo vicino al punteggio corrente
        p_raw = probs.get((h, a))
        if p_raw is None:
            continue                      # fuori griglia: non stimabile → mai a occhi chiusi
        p_model = apply_calibration(p_raw, family, state.minute, calibrator)
        p_implied = 1.0 / float(price)
        if p_model > p_max or p_model >= p_implied:
            continue                      # più probabile del consentito, o del mercato
        cand = ModelSelection(
            selection_id=int(r.selection_id), name=str(r.name),
            price=E.round_to_tick(float(price)),
            lay_size_available=float(r.lay_size or 0.0),
            p_model=float(p_model), p_implied=float(p_implied),
            p_model_raw=float(p_raw),
        )
        if best is None or (cand.p_model, cand.price, -cand.lay_size_available) < (best.p_model, best.price, -best.lay_size_available):
            best = cand
    return best


def leg_target(match_target: float, leg: str, ht_done: bool) -> float:
    """Target della gamba: metà del target partita; la gamba 2T prende l'intero
    target se la gamba 1T non è stata fatta (partita presa in corsa)."""
    t = max(0.0, float(match_target))
    if leg == "ft_cs" and not ht_done:
        return t
    return t / 2.0


def audit_block(sel: ModelSelection, *, lh_pre: float, la_pre: float, source: str,
                state: LiveState, half: bool) -> Dict[str, Any]:
    """Blocco di audit per trade.meta / suggestion (numeri, mai decisioni)."""
    return {
        "p_model": round(sel.p_model, 6),
        "p_model_raw": round(sel.raw, 6),
        "calibrated": sel.p_model_raw is not None and abs(sel.p_model - sel.p_model_raw) > 1e-12,
        "p_implied": round(sel.p_implied, 6),
        "edge": round(sel.edge, 6),
        "lambda_pre": [round(lh_pre, 3), round(la_pre, 3)],
        "lambda_source": source,
        "state": [state.minute, state.score_home, state.score_away, state.red_home, state.red_away],
        "horizon": "HT" if half else "FT",
    }


LambdaReader = Callable[[str], Optional[Tuple[float, float, Optional[int], str]]]
