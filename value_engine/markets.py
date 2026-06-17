"""
markets.py — registry dei mercati e instradamento all'evaluator corretto.

TOTALI (gol totali, FT o HT) -> poisson_total (univariato).
Mercati legati al PUNTEGGIO (1X2/DC/DNB/BTTS/CS) -> bivariate (task #5): instradati qui appena
il modulo e' disponibile; per ora sollevano NotImplementedError esplicito.
"""
from __future__ import annotations
from typing import Optional, Callable
from . import poisson_total as pt
from . import bivariate as _bv

# code -> (side, line, periodo_minuti)
TOTALS = {
    "O05": ("over", 0.5, 90), "U05": ("under", 0.5, 90),
    "O15": ("over", 1.5, 90), "U15": ("under", 1.5, 90),
    "O25": ("over", 2.5, 90), "U25": ("under", 2.5, 90),
    "O35": ("over", 3.5, 90), "U35": ("under", 3.5, 90),
    "O45": ("over", 4.5, 90), "U45": ("under", 4.5, 90),
    "O55": ("over", 5.5, 90), "U55": ("under", 5.5, 90),
    # primo tempo (periodo 45'). NB: codici allineati alla produzione (_evaluate_bet_result):
    # HT05/HT15 = OVER 0.5/1.5 HT ; HT_U05/HT_U15 = UNDER. (NON seguono il pattern O../U.. apposta.)
    "HT05": ("over", 0.5, 45), "HT_U05": ("under", 0.5, 45),
    "HT15": ("over", 1.5, 45), "HT_U15": ("under", 1.5, 45),
}

# Fonte unica: i mercati a punteggio sono definiti dal bivariato (FT + 1X2 di primo tempo).
SCORE_MARKETS = _bv.SCORE_MARKETS


def is_total(market: str) -> bool:
    return market in TOTALS


def prob_total(market: str, prematch_prob: float, minute: float, period_goals: int,
               remaining_frac: Optional[Callable[[float, float], float]] = None) -> float:
    """Prob condizionata di un mercato a gol totali.
    prematch_prob = prob pre-match (de-viggata) del mercato; period_goals = gol nel periodo finora."""
    side, line, T = TOTALS[market]
    k = int(line)  # floor: Under k+0.5 <=> total <= k ; Over <=> total >= k+1
    lam_full = pt.lam_from_prematch(side, k, prematch_prob)
    return pt.cond_prob_total(side, k, lam_full, minute, period_goals, T=T,
                              remaining_frac=remaining_frac)


def evaluate(market: str, **ctx) -> float:
    """Dispatch. Per i totali richiede prematch_prob, minute, period_goals.
    Per i mercati a punteggio rimanda a bivariate (task #5)."""
    if is_total(market):
        return prob_total(market, ctx["prematch_prob"], ctx["minute"], ctx["period_goals"],
                          ctx.get("remaining_frac"))
    if market in SCORE_MARKETS:
        try:
            from . import bivariate  # disponibile dal task #5
        except ImportError:
            raise NotImplementedError(
                f"Mercato '{market}' richiede il modello bivariato (value_engine.bivariate, task #5)."
            )
        return bivariate.evaluate(market, **ctx)
    raise KeyError(f"Mercato sconosciuto: {market}")
