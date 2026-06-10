"""De-vigging corretto per-mercato: multiplicativo (basic) e Shin."""
from __future__ import annotations
import numpy as np
from scipy.optimize import brentq


def implied(odds: list[float]) -> np.ndarray:
    return np.array([1.0 / o for o in odds], dtype=float)


def devig_multiplicative(odds: list[float]) -> np.ndarray:
    """fair_i = (1/odds_i) / overround. Standard per Pinnacle (margine ~proporzionale)."""
    p = implied(odds)
    return p / p.sum()


def _shin_probs(pi: np.ndarray, booksum: float, z: float) -> np.ndarray:
    """Probabilita' di Shin per dato z, formula canonica (pi grezze + booksum)."""
    return (np.sqrt(z * z + 4 * (1 - z) * (pi ** 2) / booksum) - z) / (2 * (1 - z))


def devig_shin(odds: list[float]) -> np.ndarray:
    """
    Metodo di Shin: corregge la favorite-longshot bias modellando una quota
    di scommettitori informati z. Migliore del multiplicativo su book soft.

    Formulazione canonica (Shin 1992/1993):
        p_i(z) = [sqrt(z^2 + 4(1-z) * pi_i^2 / booksum) - z] / (2(1-z))
    dove pi_i = 1/odds_i sono le implied grezze e booksum = sum(pi_i).
    z e' risolto imponendo sum_i p_i(z) = 1 via brentq.
    """
    pi = implied(odds)
    booksum = float(pi.sum())
    # Se non c'e' overround (booksum <= 1) Shin non si applica: ritorna normalizzato.
    if booksum <= 1.0:
        return pi / booksum

    def g(z: float) -> float:
        return float(_shin_probs(pi, booksum, z).sum()) - 1.0

    # g(0) = sqrt(booksum) - 1 > 0; g cresce con z calante -> radice in (0, 1).
    # Bracket alto < 1 per evitare la singolarita' in z=1.
    z = brentq(g, 0.0, 0.999, xtol=1e-12, rtol=1e-12)
    p = _shin_probs(pi, booksum, z)
    return p / p.sum()
