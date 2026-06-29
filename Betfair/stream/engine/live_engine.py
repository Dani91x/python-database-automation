"""Modello Poisson in-play: ricalcolo probabilità in-match.

PURO e deterministico (testabile). Dati: punteggio corrente, minuto, e i tassi
gol attesi PRE-MATCH (lambda casa/trasferta). I gol RESIDUI attesi scalano col
tempo rimanente; i gol futuri seguono Poisson indipendenti per lato. Da qui si
ricavano le probabilità dei mercati principali (1X2, Over/Under, BTTS) e la
"direzione" confrontando col mercato (prob implicita = 1/quota_back).

Coerente col principio del progetto: conta DIREZIONE + TIMING + DINAMICA.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

REG_MINUTES = 90.0


def _poisson_pmf(k: int, lam: float) -> float:
    if lam < 0:
        lam = 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def remaining_fraction(minute: Optional[int]) -> float:
    """Frazione di tempo regolamentare rimanente in [0, 1]."""
    if minute is None:
        return 1.0
    rem = (REG_MINUTES - float(minute)) / REG_MINUTES
    return max(0.0, min(1.0, rem))


def remaining_rate(prematch_lambda: float, minute: Optional[int]) -> float:
    """Gol residui attesi = lambda pre-match × frazione di tempo rimanente (LINEARE).

    Mantenuta per retro-compatibilità. Il motore live usa ``inplay_residual_rates``
    che modella un profilo temporale NON lineare + stato di gioco + cartellini.
    """
    return max(0.0, prematch_lambda) * remaining_fraction(minute)


# ----------------------------------------------------------------------------
# Intensità in-play DATA-DRIVEN (nessun valore hardcoded). La partita non è
# stazionaria: la rate dei gol cambia con (a) il MINUTO, (b) lo STATO DI GIOCO,
# (c) i CARTELLINI ROSSI. OGNI parametro è CALIBRATO sui dati storici:
#   - profilo temporale  -> CDF gol reale (value_engine/goal_timing, 120k+ gol);
#   - game-state e rossi -> coefficienti PER-LEGA da inplay_intensity_by_league.json
#     (prodotto da build_inplay_intensity.py su match_events), shrinkage->globale.
# Se per una lega manca il dato -> fallback al globale; se manca anche quello
# l'effetto è NEUTRO (1.0). MAI un numero inventato.
# ----------------------------------------------------------------------------
import json as _json
import os as _os

try:  # curva gol reale (120k+ gol) — degradazione sicura al lineare se assente
    from value_engine.goal_timing import remaining_frac as _goal_remaining_frac
except Exception:  # pragma: no cover
    _goal_remaining_frac = None

_INTENSITY_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))),
    "inplay_intensity_by_league.json",
)


def _load_intensity() -> dict:
    try:
        with open(_INTENSITY_PATH, encoding="utf-8") as fh:
            d = _json.load(fh)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


_INTENSITY = _load_intensity()


def _intensity_params(league_id: Optional[int], section: str) -> dict:
    """Coefficienti calibrati di ``section`` ('game_state'|'red_card') per lega,
    con fallback al globale. Ritorna {} se nessun dato (→ effetto neutro)."""
    by = _INTENSITY.get("by_league", {}) if isinstance(_INTENSITY, dict) else {}
    if league_id is not None and str(league_id) in by:
        node = by[str(league_id)].get(section)
        if isinstance(node, dict) and node:
            return node
    glob = _INTENSITY.get("global", {}) if isinstance(_INTENSITY, dict) else {}
    node = glob.get(section)
    return node if isinstance(node, dict) else {}


def residual_time_weight(minute: Optional[int], league_id: Optional[int] = None) -> float:
    """Frazione ATTESA dei gol di partita ancora da segnare dopo ``minute``,
    dalla CDF gol empirica REALE (non lineare). Fallback lineare se la CDF manca."""
    if minute is None:
        return 1.0
    if _goal_remaining_frac is not None:
        return float(_goal_remaining_frac(float(minute), 90.0))
    m = max(0.0, float(minute))
    return max(0.0, min(1.0, (90.0 - m) / 90.0))


def game_state_multipliers(
    score_diff: int, minute: Optional[int], league_id: Optional[int] = None
) -> tuple[float, float]:
    """Moltiplicatori (casa, trasferta) per lo STATO DI GIOCO, CALIBRATI per-lega.

    Coefficienti da ``inplay_intensity_by_league.json`` (chi insegue / chi è in
    vantaggio segna di più/meno). NEUTRO (1.0) se per la lega/globale non c'è dato.
    """
    if score_diff == 0:
        return 1.0, 1.0
    p = _intensity_params(league_id, "game_state")
    leader_pg, chaser_pg = p.get("leader_per_goal"), p.get("chaser_per_goal")
    if leader_pg is None or chaser_pg is None:
        return 1.0, 1.0  # nessun dato → nessun effetto inventato
    lead = min(abs(int(score_diff)), int(p.get("max_lead", 2)))
    late = 1.0 + float(p.get("late_amp", 0.0)) * max(0.0, ((minute or 0) - 45) / 45.0)
    leader = max(0.4, 1.0 + float(leader_pg) * lead * late)
    chaser = min(2.0, 1.0 + float(chaser_pg) * lead * late)
    return (leader, chaser) if score_diff > 0 else (chaser, leader)


def red_card_multipliers(
    red_home: int, red_away: int, league_id: Optional[int] = None
) -> tuple[float, float]:
    """Moltiplicatori (casa, trasferta) per i ROSSI, CALIBRATI per-lega.

    ``carded_factor``/``opponent_factor`` da calibrazione storica. NEUTRO se assenti.
    """
    rh, ra = max(0, int(red_home or 0)), max(0, int(red_away or 0))
    if rh == 0 and ra == 0:
        return 1.0, 1.0
    p = _intensity_params(league_id, "red_card")
    carded, opp = p.get("carded_factor"), p.get("opponent_factor")
    if carded is None or opp is None:
        return 1.0, 1.0
    home = (float(carded) ** rh) * (float(opp) ** ra)
    away = (float(carded) ** ra) * (float(opp) ** rh)
    return max(0.25, min(2.0, home)), max(0.25, min(2.0, away))


def inplay_residual_rates(
    prematch_lambda_home: float,
    prematch_lambda_away: float,
    minute: Optional[int],
    score_home: int,
    score_away: int,
    red_home: int = 0,
    red_away: int = 0,
    league_id: Optional[int] = None,
    pressure_home: float = 1.0,
    pressure_away: float = 1.0,
) -> tuple[float, float]:
    """Tassi gol RESIDUI adattati allo stato LIVE della specifica partita, con
    TUTTI i coefficienti calibrati per-lega: tempo (CDF reale) × stato di gioco ×
    cartellini × pressione. ``pressure_*`` è un hook (1.0) per tiri/corner live,
    attivabile solo dopo calibrazione."""
    w = residual_time_weight(minute, league_id)
    gh, ga = game_state_multipliers(int(score_home) - int(score_away), minute, league_id)
    rh, ra = red_card_multipliers(red_home, red_away, league_id)
    lam_h = max(0.0, prematch_lambda_home) * w * gh * rh * max(0.0, pressure_home)
    lam_a = max(0.0, prematch_lambda_away) * w * ga * ra * max(0.0, pressure_away)
    return max(0.001, lam_h), max(0.001, lam_a)


@dataclass(frozen=True)
class InPlayProbs:
    home: float
    draw: float
    away: float
    over: Dict[float, float]   # {line: P(over line)}
    under: Dict[float, float]  # {line: P(under line)}
    btts_yes: float
    btts_no: float


def compute_inplay_probs(
    score_home: int,
    score_away: int,
    minute: Optional[int],
    prematch_lambda_home: float,
    prematch_lambda_away: float,
    lines: Optional[List[float]] = None,
    max_goals: int = 10,
) -> InPlayProbs:
    """Distribuzione esiti finali data la situazione corrente."""
    if lines is None:
        lines = [0.5, 1.5, 2.5, 3.5]

    lam_h = remaining_rate(prematch_lambda_home, minute)
    lam_a = remaining_rate(prematch_lambda_away, minute)

    ph = [_poisson_pmf(k, lam_h) for k in range(max_goals + 1)]
    pa = [_poisson_pmf(k, lam_a) for k in range(max_goals + 1)]

    p_home = p_draw = p_away = 0.0
    p_over = {ln: 0.0 for ln in lines}
    btts_yes = 0.0

    for gh in range(max_goals + 1):
        for ga in range(max_goals + 1):
            p = ph[gh] * pa[ga]
            if p <= 0.0:
                continue
            fh = score_home + gh
            fa = score_away + ga
            if fh > fa:
                p_home += p
            elif fh == fa:
                p_draw += p
            else:
                p_away += p
            total = fh + fa
            for ln in lines:
                if total > ln:
                    p_over[ln] += p
            if fh >= 1 and fa >= 1:
                btts_yes += p

    # rinormalizza per la coda troncata a max_goals
    z = p_home + p_draw + p_away
    if z > 0:
        p_home, p_draw, p_away = p_home / z, p_draw / z, p_away / z

    p_under = {ln: max(0.0, 1.0 - p_over[ln]) for ln in lines}
    return InPlayProbs(
        home=p_home,
        draw=p_draw,
        away=p_away,
        over=p_over,
        under=p_under,
        btts_yes=min(1.0, btts_yes),
        btts_no=max(0.0, 1.0 - btts_yes),
    )


def implied_prob(back_price: Optional[float]) -> Optional[float]:
    """Probabilità implicita dalla quota back (1/quota)."""
    if not back_price or back_price <= 1.0:
        return None
    return 1.0 / back_price


def direction(model_prob: float, market_back_price: Optional[float], min_edge: float = 0.03) -> str:
    """Direzione del segnale confrontando modello vs mercato.

    edge = model_prob - implied. 'BACK' se il modello vede più valore (edge alto),
    'LAY' se meno, 'NEUTRAL' entro la soglia.
    """
    imp = implied_prob(market_back_price)
    if imp is None:
        return "NEUTRAL"
    edge = model_prob - imp
    if edge >= min_edge:
        return "BACK"
    if edge <= -min_edge:
        return "LAY"
    return "NEUTRAL"


def estimate_prematch_lambdas(
    p_home: float,
    p_away: float,
    expected_total_goals: float = 2.6,
) -> tuple[float, float]:
    """Stima grezza di (lambda_home, lambda_away) da prob 1X2 e gol totali attesi.

    Ripartisce expected_total_goals in proporzione alla forza relativa
    (prob casa vs trasferta), con un floor per evitare lambda nulli. Utile quando
    non si hanno i lambda dei motori e si parte dalle quote di apertura.
    """
    p_home = max(1e-6, p_home)
    p_away = max(1e-6, p_away)
    share_home = p_home / (p_home + p_away)
    lam_home = max(0.2, expected_total_goals * share_home)
    lam_away = max(0.2, expected_total_goals * (1.0 - share_home))
    return lam_home, lam_away
