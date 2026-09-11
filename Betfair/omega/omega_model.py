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
    p_data: Optional[float] = None        # P empirica dai dati storici (§14/§15); None = non disponibile
    back_price: Optional[float] = None    # §15: miglior back della selezione (costo di copertura)
    back_size: Optional[float] = None

    @property
    def p_selected(self) -> float:
        """P usata per filtro e ordinamento: la PIÙ ALTA fra modello e dati
        (un risultato si banca solo se è raro per entrambe le viste)."""
        return self.p_model if self.p_data is None else max(self.p_model, self.p_data)

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
    # §15: gialli dal blocco IPS del feed — moltiplicatori GIÀ calibrati per lega
    # in live_engine (finora mai passati al modello)
    yellow_home: int = 0
    yellow_away: int = 0


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


def lambdas_from_pre_ko(pre_ko: Optional[dict], total_goals: float = DEFAULT_TOTAL_GOALS,
                        rho: float = DEFAULT_RHO) -> Optional[Tuple[float, float]]:
    """(λ_casa, λ_trasferta) dalle quote 1X2 pre-KO congelate dallo scanner, con
    lo split casa/trasferta RISOLTO sulla griglia (review F4: la ripartizione
    proporzionale alle P sottostimava λ_trasferta fino a 3× col favorito netto)."""
    if not isinstance(pre_ko, dict):
        return None
    probs = devig_1x2(pre_ko.get("home"), pre_ko.get("draw"), pre_ko.get("away"))
    if probs is None:
        return None
    total = total_goals_from_1x2(probs[0], probs[2], rho, fallback=total_goals)
    return split_lambdas_1x2(probs[0], probs[2], total, rho)


def _full_match_1x2(lh: float, la: float, rho: float) -> Tuple[float, float, float]:
    g = residual_grid(lh, la, rho, MAX_GOALS_GRID, dixon_coles=True)
    ph = sum(p for (h, a), p in g.items() if h > a)
    pa = sum(p for (h, a), p in g.items() if a > h)
    return ph, 1.0 - ph - pa, pa


def total_goals_from_1x2(p_home: float, p_away: float, rho: float = DEFAULT_RHO,
                         fallback: float = DEFAULT_TOTAL_GOALS) -> float:
    """Gol totali attesi T impliciti nel PAREGGIO dell'1X2 (seconda passata F-02): a
    rapporto casa/trasferta fisso, P(X) decresce in T (più gol = meno pareggi);
    bisezione su T in [1,2; 5,5]. Il sistema {ph, pd, pa} è esattamente identificato
    da (λh, λa): fissare T = 2,6 buttava via il pareggio e sottostimava la coda
    fino a 2,7× nelle partite da molti gol."""
    try:
        pd = 1.0 - float(p_home) - float(p_away)
    except (TypeError, ValueError):
        return fallback
    if not (0.02 < pd < 0.6):
        return fallback

    def draw_at(t: float) -> float:
        lh, la = split_lambdas_1x2(p_home, p_away, t, rho)
        _, d, _ = _full_match_1x2(lh, la, rho)
        return d

    lo, hi = 1.2, 5.5
    if draw_at(lo) < pd:
        return lo
    if draw_at(hi) > pd:
        return hi
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if draw_at(mid) > pd:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def split_lambdas_1x2(p_home: float, p_away: float, total_goals: float,
                      rho: float = DEFAULT_RHO) -> Tuple[float, float]:
    """(λ_casa, λ_trasferta) con λ_casa + λ_trasferta = ``total_goals`` tali che la
    griglia Poisson-DC riproduce il rapporto P(casa)/P(trasferta) del mercato.
    Bisezione sul log del rapporto λ_casa/λ_trasferta (monotono)."""
    total = max(0.4, float(total_goals))
    target = math.log(max(1e-6, float(p_home)) / max(1e-6, float(p_away)))
    lo, hi = -3.0, 3.0

    def f(r: float) -> float:
        share = 1.0 / (1.0 + math.exp(-r))
        ph, _, pa = _full_match_1x2(total * share, total * (1.0 - share), rho)
        return math.log(max(1e-9, ph) / max(1e-9, pa)) - target

    if f(lo) > 0:
        r = lo
    elif f(hi) < 0:
        r = hi
    else:
        r = 0.0
        for _ in range(40):
            r = 0.5 * (lo + hi)
            if f(r) > 0:
                hi = r
            else:
                lo = r
        r = 0.5 * (lo + hi)
    share = 1.0 / (1.0 + math.exp(-r))
    return max(0.2, total * share), max(0.2, total * (1.0 - share))


def residual_lambdas(lh_pre: float, la_pre: float, state: LiveState,
                     league_id: Optional[int], *, half: bool) -> Tuple[float, float]:
    """λ residui (fino al 90′, o al 45′ se ``half``) dallo stato live."""
    from Betfair.stream.engine.live_engine import inplay_residual_rates
    lh, la = inplay_residual_rates(
        lh_pre, la_pre, state.minute, state.score_home, state.score_away,
        red_home=state.red_home, red_away=state.red_away,
        yellow_home=state.yellow_home, yellow_away=state.yellow_away,
        league_id=league_id,
    )
    if half:
        k = ht_residual_share(state.minute)
        lh, la = lh * k, la * k
    return max(0.001, lh), max(0.001, la)


HT_INJURY_MIN = 3.0   # recupero atteso del 1° tempo


def ht_residual_share(minute: int) -> float:
    """Quota del λ RESIDUO di partita (fino al 90′) che cade da ``minute`` alla
    fine del 1° tempo — dalla CDF empirica dei minuti dei gol (review 11/09 F3:
    la vecchia formula lineare sottostimava il λ del 1T del 20 % al 40′ e fino a
    3× al 44′, in direzione anti-conservativa). Recupero del 1T: massa dopo il 44′
    decadente su HT_INJURY_MIN minuti. Fallback lineare se la CDF manca."""
    try:
        from value_engine.goal_timing import first_half_share, remaining_frac
    except Exception:  # noqa: BLE001
        left_ht = max(0.0, 45.0 - float(minute))
        left_ft = max(1.0, 90.0 - float(minute))
        return min(1.0, left_ht / left_ft) * FIRST_HALF_INTENSITY
    m = max(0.0, float(minute))
    rem_ft = max(1e-6, float(remaining_frac(m, 90.0)))
    if m < 45.0:
        rem_ht = float(remaining_frac(m, 45.0))
    else:
        rem_ht = float(remaining_frac(44.0, 45.0)) * max(0.0, (HT_INJURY_MIN - (m - 45.0)) / HT_INJURY_MIN)
    return max(0.0, min(1.0, rem_ht * float(first_half_share()) / rem_ft))


def _dc_tau(h: int, a: int, lh: float, la: float, rho: float) -> float:
    """Correzione Dixon-Coles sulle celle basse, SEMPRE ≥ 0 (review F14)."""
    if h == 0 and a == 0:
        return max(0.0, 1.0 - lh * la * rho)
    if h == 1 and a == 0:
        return max(0.0, 1.0 + la * rho)
    if h == 0 and a == 1:
        return max(0.0, 1.0 + lh * rho)
    if h == 1 and a == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


# Gauss-Hermite a 5 nodi (∫ e^{-x²} f(x) dx): per E[f(Z)], Z ~ N(0,1) usare x·√2 e w/√π
_GH5 = ((0.0, 0.9453087204829419), (0.9585724646138185, 0.3936193231522412),
        (-0.9585724646138185, 0.3936193231522412), (2.0201828704560856, 0.019953242059045913),
        (-2.0201828704560856, 0.019953242059045913))
DEFAULT_LAMBDA_CV = 0.30   # incertezza relativa su λ (review I2: riproduce la coda 1,1–1,8× misurata)


def _poisson_grid(lh: float, la: float, rho: float, max_goals: int, dixon_coles: bool) -> Dict[Tuple[int, int], float]:
    grid: Dict[Tuple[int, int], float] = {}
    for h in range(max_goals + 1):
        ph = math.exp(-lh) * lh ** h / math.factorial(h)
        for a in range(max_goals + 1):
            p = ph * math.exp(-la) * la ** a / math.factorial(a)
            if dixon_coles and h <= 1 and a <= 1:
                p *= _dc_tau(h, a, lh, la, rho)
            grid[(h, a)] = p
    return grid


def residual_grid(lh: float, la: float, rho: float, max_goals: int, *, dixon_coles: bool,
                  cv: float = 0.0) -> Dict[Tuple[int, int], float]:
    """Distribuzione dei GOL RESIDUI (h, a), normalizzata sulla griglia troncata.
    La correzione Dixon-Coles ha senso solo sulle celle basse di una partita che
    parte da 0-0: applicata solo se ``dixon_coles`` (punteggio corrente 0-0).
    ``cv`` > 0 = INCERTEZZA su λ (review I2): λ·θ con θ log-normale di media 1 e
    coefficiente di variazione ``cv``, θ COMUNE ai due lati (quadratura di
    Gauss-Hermite a 5 nodi). La coda risultante è quella di una binomiale
    negativa: più grassa, in modo dipendente dalla cella, senza fattori inventati."""
    if cv and cv > 0:
        sigma = math.sqrt(math.log(1.0 + float(cv) ** 2))
        grid: Dict[Tuple[int, int], float] = {}
        for x, w in _GH5:
            theta = math.exp(sigma * math.sqrt(2.0) * x - 0.5 * sigma * sigma)
            g = _poisson_grid(lh * theta, la * theta, rho, max_goals, dixon_coles)
            wk = w / math.sqrt(math.pi)
            for k, v in g.items():
                grid[k] = grid.get(k, 0.0) + wk * v
    else:
        grid = _poisson_grid(lh, la, rho, max_goals, dixon_coles)
    total = sum(grid.values())
    if total <= 0 or min(grid.values()) < 0:
        return {}
    return {k: v / total for k, v in grid.items()}


def score_probs(*, lh_pre: float, la_pre: float, rho: float, state: LiveState,
                league_id: Optional[int], half: bool, cv: float = 0.0) -> Dict[Tuple[int, int], float]:
    """P(risultato FINALE = (H, A)) per il mercato scelto (FT, o HT se ``half``),
    condizionata a minuto/punteggio/rossi/gialli correnti; ``cv`` = incertezza su λ."""
    lh, la = residual_lambdas(lh_pre, la_pre, state, league_id, half=half)
    grid = residual_grid(lh, la, rho, MAX_GOALS_GRID_HT if half else MAX_GOALS_GRID,
                         dixon_coles=(state.score_home == 0 and state.score_away == 0), cv=cv)
    return {(state.score_home + h, state.score_away + a): p for (h, a), p in grid.items()}


# ---------------------------------------------------------------------------
# CALIBRAZIONE (10/09): la P del modello passa dal calibratore condiviso di
# Betfair/safe_strategy/calibration.py (``Calibrator.load(path)`` /
# ``.apply(p, family, minute)``, famiglie 'cs' = Correct Score, 'hts' = Half
# Time Score) SE il modulo esiste. Import GUARDATO: modulo assente/rotto → P
# grezza, mai un crash della selezione. Cache per processo con TTL breve.
# ---------------------------------------------------------------------------
# famiglie del calibratore condiviso (safe_strategy/calibration.py): "cs_cell" =
# celle del Correct Score, "hts_cell" = Half Time Score. (Fino all'11/09 erano
# "cs"/"hts": nomi inesistenti → la calibrazione era un no-op silenzioso.)
CALIBRATION_FAMILY_FT = "cs_cell"
CALIBRATION_FAMILY_HT = "hts_cell"
# §15: FATTORE DI CODA stimato dal banco di validazione (tools/omega_validate_models):
# i risultati che il modello dà a ≤ TAIL_P_MAX escono ~1,7× più spesso del
# previsto (rapporti 11/09: 1,1–1,8 secondo minuto e campione). P usata =
# max(P calibrata, P grezza × fattore continuo) — vedi model_p. Parametro
# `model_tail_factor`.
TAIL_P_MAX = 0.05
DEFAULT_TAIL_FACTOR = 1.3
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
            # senza percorso → file di default del calibratore (fino all'11/09 si
            # chiamava loader() senza argomenti: TypeError → calibratore MAI caricato)
            path_ = key or getattr(_cal_mod, "DEFAULT_CALIBRATION_PATH", "")
            cal = loader(path_) if path_ else loader()
            if cal is not None and not callable(getattr(cal, "apply", None)):
                cal = None
    except Exception:  # noqa: BLE001 - modulo assente o rotto: selezione grezza
        cal = None
    _CALIBRATOR_CACHE[key] = (ts, cal)
    return cal


def apply_tail_factor(p: float, factor: float, p_max: float = TAIL_P_MAX) -> float:
    """P del modello con fattore di coda CONTINUO e monotono (review F12):
    f(p) = 1 + (f0 − 1)·p_max/(p_max + p) → f0 per p → 0, (1+f0)/2 a p = p_max,
    → 1 per p ≫ p_max; p·f(p) è crescente. Fattore ≤ 0/non finito → invariata."""
    try:
        f0 = float(factor)
    except (TypeError, ValueError):
        return float(p)
    if not math.isfinite(f0) or f0 <= 0 or f0 == 1.0:
        return float(p)
    q = max(0.0, float(p))
    f = 1.0 + (f0 - 1.0) * float(p_max) / (float(p_max) + q)
    return min(1.0, q * f)


def model_p(p_raw: float, family: str, minute: int, calibrator: Any, tail_factor: float = 1.0) -> float:
    """LA probabilità del modello usata OVUNQUE (selezione, green-up, sizing —
    review F1: prima il green-up usava la grezza e la selezione la prudente):
    la più prudente fra P calibrata (tabelle sui nostri stati registrati) e
    grezza × fattore di coda. Mai la somma delle due correzioni."""
    return max(apply_calibration(p_raw, family, minute, calibrator),
               apply_tail_factor(p_raw, tail_factor))


def uncertainty_p(ps: "list[float]", *, k_se: float, cv_min: float = 0.10) -> Tuple[float, float]:
    """(P centrale, P prudente) da più stime della stessa cella (fonti λ /
    modelli diversi — review I3): centro = pool logaritmico; prudente =
    centro + k·SE con SE = max(dev. std. delle stime, centro·cv_min)."""
    vals = [max(1e-9, float(p)) for p in ps if p is not None and math.isfinite(float(p))]
    if not vals:
        return 0.0, 0.0
    centre = math.exp(sum(math.log(v) for v in vals) / len(vals))
    if len(vals) > 1:
        mean = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
    else:
        sd = 0.0
    se = max(sd, centre * float(cv_min))
    return centre, min(1.0, centre + float(k_se) * se)


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
    p_data: Optional[Callable[[int, int], Optional[float]]] = None,
    cost_aware: bool = False,
    band_ratio: float = 2.0,
    tail_factor: float = 1.0,
    commission: float = 0.0,
    probs_alt: Optional["list[Dict[Tuple[int, int], float]]"] = None,
    k_se: float = 0.0,
    p_hedge: float = 0.5,
    ev_kappa: float = 1.0,
    liability_cap: float = 0.0,
) -> Optional[ModelSelection]:
    """Runner con la probabilità PIÙ BASSA che rispetti tutti i vincoli.
    ``runners``: ``omega_engine.ScoreRunner`` (lay_price/lay_size). None se nessuno.
    Con ``calibrator`` i vincoli e l'ordinamento usano la P CALIBRATA
    (``p_model``); la grezza resta in ``p_model_raw`` per l'audit.
    Con ``p_data`` (§14: P empirica HT→FT dai dati storici, ``omega_empirical``)
    la P di filtro/ordinamento è max(P modello, P dati): mai bancare un
    risultato che i dati dicono meno raro di quanto creda il modello."""
    best: Optional[ModelSelection] = None
    cands: list = []
    for r in runners:
        price = getattr(r, "lay_price", None)
        if price is None or price < price_min or price > price_max:
            continue
        # liquidità richiesta = size CAPPATA a questo prezzo (seconda passata F4: con
        # un cap di liability la size piazzata è molto più piccola di quella "da
        # target" → skip falsi per liquidità)
        need = max(float(min_liquidity), E.apply_liability_cap(float(size_needed), float(price), liability_cap))
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
        # I3: più stime della stessa cella (modelli/fonti λ diverse) → centro (pool
        # log) e P PRUDENTE (centro + k·SE); con una sola stima resta la grezza
        if probs_alt:
            alts = [p_raw] + [d.get((h, a)) for d in probs_alt if isinstance(d, dict)]
            alts = [v for v in alts if v is not None]
            centre, prudent = uncertainty_p(alts, k_se=k_se) if k_se > 0 else (p_raw, p_raw)
            p_raw_used = centre if k_se > 0 else p_raw
            p_model = max(model_p(p_raw_used, family, state.minute, calibrator, tail_factor), prudent)
        else:
            p_model = model_p(p_raw, family, state.minute, calibrator, tail_factor)
        # soglia di valore CON commissione (F11 = gate di Kelly φ* > 0):
        # un lay a L vale solo se p < (1−c)/(L−c)
        c = max(0.0, min(0.5, float(commission)))
        p_implied = (1.0 - c) / (float(price) - c)
        p_emp: Optional[float] = None
        if p_data is not None:
            try:
                got = p_data(h, a)
                p_emp = float(got) if got is not None and math.isfinite(float(got)) else None
            except Exception:  # noqa: BLE001 - i dati non devono mai rompere la selezione
                p_emp = None
        p_sel = p_model if p_emp is None else max(p_model, p_emp)
        if p_sel > p_max or p_sel >= p_implied:
            continue                      # più probabile del consentito, o del mercato
        cand = ModelSelection(
            selection_id=int(r.selection_id), name=str(r.name),
            price=E.round_to_tick(float(price)),
            lay_size_available=float(r.lay_size or 0.0),
            p_model=float(p_model), p_implied=float(p_implied),
            p_model_raw=float(p_raw), p_data=p_emp,
            back_price=(float(r.back_price) if getattr(r, "back_price", None) else None),
            back_size=(float(r.back_size) if getattr(r, "back_size", None) else None),
        )
        cands.append(cand)
        if best is None or (cand.p_selected, cand.price, -cand.lay_size_available) < (best.p_selected, best.price, -best.lay_size_available):
            best = cand
    if best is not None and cost_aware and size_needed > 0:
        # §15/F5: si massimizza il VALORE ATTESO (vincita netta, perdita, costo
        # atteso della copertura) — non una banda di P con il costo per primo
        return rank_by_ev(cands, size=float(size_needed), commission=commission,
                          p_hedge=p_hedge, kappa=ev_kappa, liability_cap=liability_cap)
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
        # §14: P empirica HT→FT (se disponibile) e P effettivamente usata
        "p_data": None if sel.p_data is None else round(sel.p_data, 6),
        "p_selected": round(sel.p_selected, 6),
        "lambda_pre": [round(lh_pre, 3), round(la_pre, 3)],
        "lambda_source": source,
        # §15: costo di copertura immediata della selezione scelta (audit)
        "back_price": sel.back_price, "back_size": sel.back_size,
        "state": [state.minute, state.score_home, state.score_away, state.red_home, state.red_away],
        "horizon": "HT" if half else "FT",
    }


LambdaReader = Callable[[str], Optional[Tuple[float, float, Optional[int], str]]]


# ---------------------------------------------------------------------------
# λ DAL MERCATO LIVE (§14, 11/09): quando né la fixture né le quote 1X2 pre-KO
# sono disponibili (scanner riavviato a partita in corso, lega minore senza
# fixture), i gol residui attesi si leggono dal mercato OVER/UNDER in stream
# (blocchi ``ou`` del feed unico): P(over) de-viggata → λ residuo (Poisson,
# inversione ``value_engine.poisson_total``) → riportato a "λ pre-match
# equivalente" con gli STESSI moltiplicatori live del modello, così il resto
# della catena (residui per minuto/stato/rossi, griglia DC) resta identico.
# Split casa/trasferta neutro con vantaggio casa (le quote 1X2 live riflettono
# il punteggio, non la forza residua). Fonte dichiarata: 'live_ou'.
# ---------------------------------------------------------------------------
LIVE_OU_HOME_SHARE = 0.54
LIVE_OU_ANCHOR_GOALS = 2.5        # linea preferita: gol attuali + 2.5 (la più liquida)
LIVE_OU_P_MIN, LIVE_OU_P_MAX = 0.03, 0.97
LAMBDA_PRE_MIN, LAMBDA_PRE_MAX = 0.2, 4.0


def _ou_sides(block: dict) -> Tuple[Optional[float], Optional[float]]:
    """(back Over, back Under) del blocco O/U del feed; None se manca un lato."""
    over = under = None
    for s in block.get("selections") or []:
        if not isinstance(s, dict) or s.get("runner_status") not in (None, "ACTIVE"):
            continue
        name = str(s.get("name") or "").strip().lower()
        back = s.get("back")
        if not isinstance(back, (int, float)) or back <= 1.0:
            continue
        if name.startswith("over"):
            over = float(back)
        elif name.startswith("under"):
            under = float(back)
    return over, under


def residual_total_from_ou(payload: Optional[dict], state: LiveState) -> Optional[Tuple[float, float, float]]:
    """(λ residuo TOTALE, linea usata, P(over) de-viggata) dal mercato O/U più
    vicino a gol attuali + 2.5 con entrambi i lati prezzati e mercato OPEN.
    None se nessuna linea è utilizzabile (linea già superata, book vuoto)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("ou"), list):
        return None
    try:
        from value_engine.devig import devig_pair
        from value_engine.poisson_total import lam_from_prematch
    except Exception:  # noqa: BLE001 - libreria assente: nessuna stima
        return None
    goals = int(state.score_home) + int(state.score_away)
    best: Optional[Tuple[float, float, float]] = None   # (distanza, linea, p_over)
    for blk in payload["ou"]:
        if not isinstance(blk, dict):
            continue
        if str(blk.get("status") or "OPEN").upper() != "OPEN":
            continue
        line = blk.get("line")
        if not isinstance(line, (int, float)):
            continue
        k = int(float(line) - 0.5) - goals        # "over" = residuo ≥ k+1
        if k < 0:
            continue                                # linea già superata dai gol fatti
        over, under = _ou_sides(blk)
        if over is None or under is None:
            continue
        p_over = float(devig_pair(over, under))
        if not (LIVE_OU_P_MIN <= p_over <= LIVE_OU_P_MAX):
            continue
        dist = abs(float(line) - (goals + LIVE_OU_ANCHOR_GOALS))
        if best is None or dist < best[0]:
            best = (dist, float(line), p_over)
    if best is None:
        return None
    _, line, p_over = best
    k = int(line - 0.5) - goals
    try:
        lam_res = float(lam_from_prematch("over", k, p_over))
    except Exception:  # noqa: BLE001 - inversione non riuscita
        return None
    if not math.isfinite(lam_res) or lam_res <= 0:
        return None
    return lam_res, line, p_over


def lambdas_from_live_ou(payload: Optional[dict], state: LiveState,
                         league_id: Optional[int]) -> Optional[Tuple[float, float, Dict[str, Any]]]:
    """(λ_casa pre-match equivalente, λ_trasferta, dettagli) dal mercato O/U live.
    ``dettagli`` = {line, p_over, lambda_residual} per l'audit. None se non stimabile."""
    est = residual_total_from_ou(payload, state)
    if est is None:
        return None
    lam_res, line, p_over = est
    if not (RESIDUAL_MIN <= lam_res <= RESIDUAL_MAX):
        return None                     # F8: mai clampare in silenzio un λ fuori scala
    mult = _live_multipliers(state, league_id)
    if mult is None:
        return None
    mh, ma = mult
    lh = LIVE_OU_HOME_SHARE * lam_res / mh
    la = (1.0 - LIVE_OU_HOME_SHARE) * lam_res / ma
    return lh, la, {"line": line, "p_over": round(p_over, 4), "lambda_residual": round(lam_res, 4)}


RESIDUAL_MIN, RESIDUAL_MAX = 0.005, 3.5      # λ residui plausibili (F8: clamp in spazio residuo)


def _live_multipliers(state: LiveState, league_id: Optional[int]) -> Optional[Tuple[float, float]]:
    """(m_casa, m_trasferta): moltiplicatori live del modello (tempo, stato,
    rossi, gialli) — quelli con cui λ_pre → λ_res. Usati per invertire."""
    try:
        from Betfair.stream.engine.live_engine import inplay_residual_rates
        mh, ma = inplay_residual_rates(1.0, 1.0, state.minute, state.score_home, state.score_away,
                                       red_home=state.red_home, red_away=state.red_away,
                                       yellow_home=state.yellow_home, yellow_away=state.yellow_away,
                                       league_id=league_id)
    except Exception:  # noqa: BLE001
        return None
    if mh <= 0 or ma <= 0:
        return None
    return mh, ma


def half_time_score(payload: Optional[dict]) -> Optional[Tuple[int, int]]:
    """Punteggio del 45′ dal blocco IPS del feed (``halfTimeScore``), o None."""
    if not isinstance(payload, dict):
        return None
    raw = payload.get("score_raw")
    score = raw.get("score") if isinstance(raw, dict) else None
    if not isinstance(score, dict):
        return None
    home = score.get("home") if isinstance(score.get("home"), dict) else {}
    away = score.get("away") if isinstance(score.get("away"), dict) else {}
    try:
        h, a = str(home.get("halfTimeScore") or "").strip(), str(away.get("halfTimeScore") or "").strip()
        if h == "" or a == "":
            return None
        return int(h), int(a)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# §15 — λ IMPLICITI NEL MERCATO INTERO (11/09, richiesta "modello definitivo").
# In stream abbiamo la scala COMPLETA del Correct Score (chi segna) e tutte le
# linee Over/Under (quanti gol): si cercano i λ residui (casa, trasferta) la cui
# griglia di Poisson riproduce meglio le probabilità de-viggate del mercato —
# il consenso di chi rischia soldi in quel minuto. Ricerca su griglia
# log-spaziata + raffinamento locale: pochi millisecondi, nessuna dipendenza.
# I λ residui vengono riportati a "pre-match equivalenti" con gli stessi
# moltiplicatori live del modello (come per la singola linea O/U).
# ---------------------------------------------------------------------------
MARKET_GRID_MIN_CS = 6          # selezioni CS prezzate minime per fidarsi della scala
MARKET_GRID_LAMBDA_MIN = 0.02
MARKET_GRID_LAMBDA_MAX = 4.0
_GRID_STEPS = 28


def market_cs_probs(payload: Optional[dict], state: LiveState) -> Dict[Tuple[int, int], float]:
    """Probabilità DE-VIGGATE del mercato Correct Score per risultato raggiungibile
    (mid fra back e lay, o il lato disponibile), normalizzate su TUTTE le
    selezioni prezzate (aggregati inclusi). {} se la scala non è utilizzabile."""
    if not isinstance(payload, dict) or not isinstance(payload.get("cs"), dict):
        return {}
    cs = payload["cs"]
    if str(cs.get("status") or "OPEN").upper() != "OPEN":
        return {}
    raw: Dict[Tuple[int, int], float] = {}
    total = 0.0
    n_scores = 0
    for s_ in cs.get("selections") or []:
        if not isinstance(s_, dict) or s_.get("runner_status") not in (None, "ACTIVE"):
            continue
        back, lay = s_.get("back"), s_.get("lay")
        prices = [float(q) for q in (back, lay) if isinstance(q, (int, float)) and q > 1.0]
        if not prices:
            continue
        p = sum(1.0 / q for q in prices) / len(prices)
        total += p
        parsed = E.parse_scoreline(str(s_.get("name") or ""))
        if parsed is None:
            continue                                  # "Any Other…": pesa nella normalizzazione
        h, a = parsed
        if h < state.score_home or a < state.score_away:
            continue                                  # irraggiungibile (sospeso): non dovrebbe esserci
        raw[(h, a)] = p
        n_scores += 1
    if total <= 0 or n_scores < MARKET_GRID_MIN_CS:
        return {}
    return {k: v / total for k, v in raw.items()}


def market_ou_probs(payload: Optional[dict], state: LiveState) -> Dict[int, float]:
    """{k: P(gol residui ≥ k+1)} da OGNI linea Over/Under aperta e prezzata (devig
    a coppia). Solo le linee non ancora superate dai gol fatti."""
    if not isinstance(payload, dict) or not isinstance(payload.get("ou"), list):
        return {}
    try:
        from value_engine.devig import devig_pair
    except Exception:  # noqa: BLE001
        return {}
    goals = int(state.score_home) + int(state.score_away)
    out: Dict[int, float] = {}
    for blk in payload["ou"]:
        if not isinstance(blk, dict) or str(blk.get("status") or "OPEN").upper() != "OPEN":
            continue
        line = blk.get("line")
        if not isinstance(line, (int, float)):
            continue
        k = int(float(line) - 0.5) - goals
        if k < 0:
            continue
        over, under = _ou_sides(blk)
        if over is None or under is None:
            continue
        p = float(devig_pair(over, under))
        if LIVE_OU_P_MIN <= p <= LIVE_OU_P_MAX:
            out[k] = p
    return out


def market_cs_brackets(payload: Optional[dict], state: LiveState
                       ) -> Tuple[Dict[Tuple[int, int], Tuple[float, float, float]], "list[Tuple[str, float, float]]"]:
    """(celle: (H,A) → (p_mid, p_lo=1/lay, p_hi=1/back) NORMALIZZATE; aggregati:
    [(kind, p_lo, p_hi)] con kind ∈ home|away|draw = "Any Other …"). Review F9/F10:
    la forchetta [1/lay, 1/back] è l'informazione VERA del book (sulle longshot
    vale 2:1) e gli aggregati sono la massa di coda quotata dal mercato."""
    if not isinstance(payload, dict) or not isinstance(payload.get("cs"), dict):
        return {}, []
    cs = payload["cs"]
    if str(cs.get("status") or "OPEN").upper() != "OPEN":
        return {}, []
    cells: Dict[Tuple[int, int], Tuple[float, float, float]] = {}
    aggs: "list[Tuple[str, float, float]]" = []
    total = 0.0
    for s_ in cs.get("selections") or []:
        if not isinstance(s_, dict) or s_.get("runner_status") not in (None, "ACTIVE"):
            continue
        back, lay = s_.get("back"), s_.get("lay")
        pb = 1.0 / float(back) if isinstance(back, (int, float)) and back > 1.0 else None
        pl = 1.0 / float(lay) if isinstance(lay, (int, float)) and lay > 1.0 else None
        if pb is None and pl is None:
            continue
        # microprice pesato per size quando ci sono entrambi i lati
        qb, ql = float(s_.get("back_size") or 0.0), float(s_.get("lay_size") or 0.0)
        if pb is not None and pl is not None:
            mid = (ql * pb + qb * pl) / (qb + ql) if (qb + ql) > 0 else 0.5 * (pb + pl)
        else:
            mid = pb if pb is not None else pl
        lo, hi = (pl if pl is not None else mid), (pb if pb is not None else mid)
        total += mid
        name = str(s_.get("name") or "")
        parsed = E.parse_scoreline(name)
        if parsed is None:
            n = name.lower()
            kind = "home" if "home" in n else "away" if "away" in n else "draw" if "draw" in n else None
            if kind:
                aggs.append((kind, lo, hi))
            continue
        h, a = parsed
        if h < state.score_home or a < state.score_away:
            continue
        cells[(h, a)] = (mid, lo, hi)
    if total <= 0 or len(cells) < MARKET_GRID_MIN_CS:
        return {}, []
    cells = {k: (v[0] / total, v[1] / total, v[2] / total) for k, v in cells.items()}
    aggs = [(k, lo / total, hi / total) for k, lo, hi in aggs]
    return cells, aggs


def _bracket_loss(p_mod: float, lo: float, hi: float, mid: float) -> float:
    """χ² a forchetta: zero dentro [lo, hi], pesato 1/p per contare la coda."""
    lo, hi = min(lo, hi), max(lo, hi)
    d = (lo - p_mod) if p_mod < lo else (p_mod - hi) if p_mod > hi else 0.0
    return d * d / max(float(mid), 1e-4)


def _grid_loss(lh: float, la: float, cs_target: Dict[Tuple[int, int], Any],
               ou_target: Dict[int, float], state: LiveState, rho: float,
               aggs: Optional["list[Tuple[str, float, float]]"] = None) -> float:
    grid = residual_grid(lh, la, rho, MAX_GOALS_GRID,
                         dixon_coles=(state.score_home == 0 and state.score_away == 0))
    loss = 0.0
    listed = set()
    for cell, tgt in cs_target.items():
        h, a = cell
        listed.add(cell)
        p_mod = grid.get((h - state.score_home, a - state.score_away), 0.0)
        if isinstance(tgt, tuple):
            loss += _bracket_loss(p_mod, tgt[1], tgt[2], tgt[0])
        else:
            loss += (p_mod - float(tgt)) ** 2 / max(float(tgt), 1e-4)
    for kind, lo, hi in aggs or []:
        # massa delle celle NON quotate col segno dell'aggregato
        p_agg = 0.0
        for (h, a), p in grid.items():
            H, A = h + state.score_home, a + state.score_away
            if (H, A) in listed:
                continue
            if (kind == "home" and H > A) or (kind == "away" and A > H) or (kind == "draw" and H == A):
                p_agg += p
        loss += _bracket_loss(p_agg, lo, hi, 0.5 * (lo + hi))
    if ou_target:
        w = max(1.0, float(len(cs_target))) / len(ou_target)
        for k, p_over in ou_target.items():
            p_mod = sum(p for (h, a), p in grid.items() if h + a >= k + 1)
            loss += w * (p_mod - p_over) ** 2 / max(p_over, 1e-4)
    return loss


def fit_residual_lambdas_to_market(cs_target: Dict[Tuple[int, int], Any],
                                   ou_target: Dict[int, float], state: LiveState,
                                   rho: float = DEFAULT_RHO,
                                   aggs: Optional["list[Tuple[str, float, float]]"] = None
                                   ) -> Optional[Tuple[float, float, float]]:
    """(λ_res casa, λ_res trasferta, loss) che meglio riproduce il mercato. PURA.
    ``cs_target``: cella → P (float) oppure (mid, lo, hi) (forchetta)."""
    if not cs_target and not ou_target:
        return None
    lo, hi = math.log(MARKET_GRID_LAMBDA_MIN), math.log(MARKET_GRID_LAMBDA_MAX)
    axis = [math.exp(lo + (hi - lo) * i / (_GRID_STEPS - 1)) for i in range(_GRID_STEPS)]
    best: Optional[Tuple[float, float, float]] = None
    for lh in axis:
        for la in axis:
            loss = _grid_loss(lh, la, cs_target, ou_target, state, rho, aggs)
            if best is None or loss < best[2]:
                best = (lh, la, loss)
    if best is None:
        return None
    lh, la, loss = best
    step = (hi - lo) / (_GRID_STEPS - 1)

    def clamp(v: float) -> float:
        return min(MARKET_GRID_LAMBDA_MAX, max(MARKET_GRID_LAMBDA_MIN, v))

    for _ in range(2):                      # raffinamento locale, passo dimezzato
        step /= 2.0
        improved = True
        while improved:
            improved = False
            for dh, da in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step)):
                cand = (clamp(math.exp(math.log(lh) + dh)), clamp(math.exp(math.log(la) + da)))
                cl = _grid_loss(cand[0], cand[1], cs_target, ou_target, state, rho, aggs)
                if cl < loss - 1e-12:
                    lh, la, loss = cand[0], cand[1], cl
                    improved = True
    return lh, la, loss


def lambdas_from_market_grid(payload: Optional[dict], state: LiveState, league_id: Optional[int],
                             rho: float = DEFAULT_RHO) -> Optional[Tuple[float, float, Dict[str, Any]]]:
    """(λ_casa pre-match equivalente, λ_trasferta, dettagli) dall'INTERO mercato
    (scala CS + linee O/U). None se la scala CS non è utilizzabile (servono almeno
    ``MARKET_GRID_MIN_CS`` risultati prezzati: con la sola O/U si usa
    ``lambdas_from_live_ou``)."""
    cells, aggs = market_cs_brackets(payload, state)
    if not cells:
        return None
    ou_target = market_ou_probs(payload, state)
    fit = fit_residual_lambdas_to_market(cells, ou_target, state, rho, aggs=aggs)
    if fit is None:
        return None
    lh_res, la_res, loss = fit
    # F8: un fit sul bordo della griglia non è un λ, è un fallimento → None
    edge = MARKET_GRID_LAMBDA_MIN * 1.05
    if lh_res <= edge or la_res <= edge or lh_res >= MARKET_GRID_LAMBDA_MAX * 0.95 or la_res >= MARKET_GRID_LAMBDA_MAX * 0.95:
        return None
    mult = _live_multipliers(state, league_id)
    if mult is None:
        return None
    mh, ma = mult
    return lh_res / mh, la_res / ma, {
        "lambda_residual": [round(lh_res, 4), round(la_res, 4)], "loss": round(loss, 6),
        "n_cs": len(cells), "n_ou": len(ou_target), "n_agg": len(aggs),
    }


def yellow_cards(payload: Optional[dict]) -> Tuple[int, int]:
    """(gialli casa, gialli trasferta) dal blocco IPS del feed; (0, 0) se assenti."""
    if not isinstance(payload, dict):
        return 0, 0
    raw = payload.get("score_raw")
    score = raw.get("score") if isinstance(raw, dict) else None
    if not isinstance(score, dict):
        return 0, 0
    out = []
    for side in ("home", "away"):
        blk = score.get(side) if isinstance(score.get(side), dict) else {}
        try:
            v = int(blk.get("numberOfYellowCards") or 0)
        except (TypeError, ValueError):
            v = 0
        out.append(max(0, min(v, 11)))
    return out[0], out[1]


# ---------------------------------------------------------------------------
# §15 — SELEZIONE CON COSTO DI COPERTURA. A quote fair il valore atteso della
# scommessa è ≈ 0: ciò che decide il P&L è quanto costa uscire (green-up) quando
# il rischio diventa reale. Fra i candidati con probabilità "equivalente"
# (entro ``band_ratio`` × la più bassa) si preferisce quello più ECONOMICO DA
# COPRIRE oggi — costo della copertura immediata = size·(lay/back − 1), con
# liquidità back sufficiente — poi la liability minore.
# ---------------------------------------------------------------------------
def cover_cost(size: float, lay_price: float, back_price: Optional[float]) -> Optional[float]:
    """Costo (€) di coprire SUBITO il lay al miglior back: size·(L/B − 1). None senza back."""
    if back_price is None or back_price <= 1.0 or lay_price <= 1.0 or size <= 0:
        return None
    return round(float(size) * (float(lay_price) / float(back_price) - 1.0), 2)


def expected_value(p: float, price: float, size: float, commission: float,
                   cover: Optional[float], p_hedge: float, kappa: float) -> float:
    """EV (€) di un lay di ``size`` a ``price`` con P ``p`` che il risultato esca:
    (1−p)·size·(1−c) − p·size·(L−1) − κ·p_hedge·costo_copertura (review F5)."""
    c = max(0.0, min(0.5, float(commission)))
    ev = (1.0 - p) * size * (1.0 - c) - p * size * (float(price) - 1.0)
    if cover is not None:
        ev -= float(kappa) * float(p_hedge) * float(cover)
    return ev


def rank_by_ev(cands: list, *, size: float, commission: float, p_hedge: float, kappa: float,
               liability_cap: float = 0.0) -> Optional[Any]:
    """Fra le ``ModelSelection`` sceglie quella col VALORE ATTESO massimo,
    contando anche il costo atteso della copertura; copertura impossibile
    (liquidità back insufficiente) penalizzata. La size è quella che verrebbe
    DAVVERO piazzata a quel prezzo (cap di liability, liquidità lay)."""
    if not cands:
        return None

    def key(c):
        s = E.apply_liability_cap(float(size), float(c.price), liability_cap)
        if c.lay_size_available and s > c.lay_size_available:
            s = float(c.lay_size_available)
        cost = cover_cost(s, c.price, c.back_price)
        need = float(s) * float(c.price) / float(c.back_price) if c.back_price and c.back_price > 1 else None
        liquid = c.back_size is None or c.back_size <= 0 or need is None or c.back_size >= need
        coverable = 1 if (cost is not None and liquid) else 0
        ev = expected_value(c.p_selected, c.price, s, commission, cost, p_hedge, kappa)
        return (coverable, ev, -c.p_selected)

    return max(cands, key=key)


def rank_by_cover_cost(cands: list, *, size: float, band_ratio: float) -> Optional[Any]:
    """Fra le ``ModelSelection`` prende la banda a P equivalente e sceglie: copertura
    possibile e più economica → liquidità back maggiore → prezzo lay più basso →
    P più bassa. Senza alcun back noto la banda si riduce alla P più bassa."""
    if not cands:
        return None
    p_min = min(c.p_selected for c in cands)
    band = [c for c in cands if c.p_selected <= p_min * max(1.0, float(band_ratio))]

    def key(c):
        cost = cover_cost(size, c.price, c.back_price)
        need = float(size) * float(c.price) / float(c.back_price) if c.back_price and c.back_price > 1 else None
        liquid = c.back_size is None or c.back_size <= 0 or need is None or c.back_size >= need
        coverable = 1 if (cost is not None and liquid) else 0
        return (-coverable, cost if cost is not None else float("inf"), -(c.back_size or 0.0), c.price, c.p_selected)

    return min(band, key=key)
