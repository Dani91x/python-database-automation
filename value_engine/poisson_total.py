"""
poisson_total.py — mercati a GOL TOTALI (Over/Under, FT o HT) come processo di Poisson.

Probabilita' condizionata: dato il minuto t e i gol gia' segnati nel periodo, i gol RIMANENTI
seguono Poisson(lambda_full * frazione_tempo_rimasto). La frazione di default e' lineare
(T-t)/T, ma puo' essere sostituita da una CDF calibrata (vedi goal_timing, task #6).
Logica estratta dal prototipo SIGNAL_ANALYSIS/calcolatore_valore.py.
"""
from __future__ import annotations
from math import exp, factorial
from typing import Callable, Optional

_LAM_MAX = 50.0  # bound superiore per l'inversione del lambda

def brentq(f: Callable[[float], float], a: float, b: float, it: int = 64) -> float:
    """Bisezione pura IDENTICA al port TS (niente scipy): garantisce parita' 1:1 sui totali.
    Solleva se non c'e' cambio di segno nel bracket."""
    fa, fb = f(a), f(b)
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if fa * fb > 0:
        raise ValueError("brentq: f(a) e f(b) hanno lo stesso segno (nessuna radice nel bracket)")
    for _ in range(it):
        m = (a + b) / 2.0
        fm = f(m)
        if fm == 0.0:
            return m
        if fa * fm <= 0:
            b = m
        else:
            a, fa = m, fm
    return (a + b) / 2.0


def p_le(k: int, lam: float) -> float:
    """P(Poisson(lam) <= k)."""
    if lam < 0:
        raise ValueError(f"lam deve essere >= 0, ricevuto {lam}")
    if k < 0:
        return 0.0
    return sum(exp(-lam) * lam ** i / factorial(i) for i in range(k + 1))


def lam_from_prematch(side: str, k: int, prob: float) -> float:
    """Ricava il lambda del PERIODO INTERO dalla prob pre-match del mercato.
    side='under' -> prob = P(<=k); side='over' -> prob = 1 - P(<=k)."""
    if side not in ("under", "over"):
        raise ValueError(f"side deve essere 'under' o 'over', ricevuto {side!r}")
    prob = min(max(prob, 1e-6), 1 - 1e-6)
    if side == "under":
        f = lambda L: p_le(k, L) - prob  # noqa: E731
    else:
        f = lambda L: (1.0 - p_le(k, L)) - prob  # noqa: E731
    fa, fb = f(1e-4), f(_LAM_MAX)
    if fa * fb > 0:
        raise ValueError(
            f"Nessuna radice Poisson in [1e-4, {_LAM_MAX}] per side={side!r}, k={k}, prob={prob:.6f}"
        )
    return brentq(f, 1e-4, _LAM_MAX)


def cond_prob_total(side: str, k: int, lam_full: float, minute: float, goals: int,
                    T: float = 90.0,
                    remaining_frac: Optional[Callable[[float, float], float]] = None) -> float:
    """Prob condizionata del mercato Over/Under(line=k+0.5) dato (minuto, gol segnati nel periodo).
    remaining_frac(t,T) -> frazione di gol attesi ancora da venire (default lineare, clampata [0,1])."""
    frac = remaining_frac(minute, T) if remaining_frac else max(T - minute, 0.0) / T
    frac = max(0.0, min(1.0, frac))
    lam_rem = lam_full * frac
    if side == "under":
        need = k - goals                       # gol ancora ammessi
        if need < 0:
            return 0.0                          # gia' superato -> Under perso
        return p_le(need, lam_rem)
    else:  # over
        need = (k + 1) - goals                  # gol ancora necessari
        if need <= 0:
            return 1.0                          # gia' raggiunto -> Over vinto
        return 1.0 - p_le(need - 1, lam_rem)
