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
    """Gol residui attesi = lambda pre-match × frazione di tempo rimanente."""
    return max(0.0, prematch_lambda) * remaining_fraction(minute)


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
