"""Matematica pura del modello Dixon-Coles (auto-contenuta, niente I/O, niente DB).

Tutte le funzioni sono deterministiche e testabili in isolamento. Riscritte
internamente al motore (non importate da Prediction/) per indipendenza totale.

Riferimento: Dixon & Coles (1997), "Modelling Association Football Scores and
Inefficiencies in the Football Betting Market", Applied Statistics 46(2):265-280.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
from scipy.stats import poisson


def poisson_pmf(lmbda: float, k: int) -> float:
    """P(X=k) per X ~ Poisson(lmbda). Wrapper esplicito per i test."""
    return float(poisson.pmf(k, lmbda))


def dc_tau(x: int, y: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    """Correzione Dixon-Coles tau sui quattro punteggi bassi (0-0,1-0,0-1,1-1).

    Modella la dipendenza tra i gol delle due squadre nei risultati a basso
    punteggio, che il Poisson indipendente sottostima. tau=1 altrove.
    """
    if x == 0 and y == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if x == 0 and y == 1:
        return 1.0 + lambda_home * rho
    if x == 1 and y == 0:
        return 1.0 + lambda_away * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lambda_home: float, lambda_away: float, rho: float,
                 max_goals: int = 10) -> np.ndarray:
    """Matrice P(x,y) normalizzata: riga x = gol casa, colonna y = gol trasferta.

    Poisson indipendente sui due marginali + correzione tau sui 4 angoli bassi,
    poi rinormalizzazione (recupera la massa di coda troncata a max_goals).
    """
    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("lambda devono essere > 0")
    ks = np.arange(max_goals + 1)
    ph = poisson.pmf(ks, lambda_home)
    pa = poisson.pmf(ks, lambda_away)
    grid = np.outer(ph, pa)  # P(x)*P(y) indipendente
    for x in (0, 1):
        for y in (0, 1):
            grid[x, y] *= dc_tau(x, y, lambda_home, lambda_away, rho)
    total = grid.sum()
    if total <= 0:
        raise ValueError("somma griglia non positiva")
    return grid / total


def markets_from_matrix(grid: np.ndarray) -> Dict[str, float]:
    """Deriva TUTTI i mercati come somme di celle della matrice P(x,y).

    Coerenti per costruzione (scommano alla stessa massa). Restituisce
    probabilita' in [0,1].
    """
    n = grid.shape[0]
    hg = np.arange(n).reshape(-1, 1)  # gol casa per riga
    ag = np.arange(n).reshape(1, -1)  # gol trasferta per colonna
    tot = hg + ag

    p_home = float(grid[hg > ag].sum())
    p_draw = float(grid[hg == ag].sum())
    p_away = float(grid[hg < ag].sum())
    # rinormalizza 1X2 per togliere il leakage float (la griglia somma ~1)
    s = p_home + p_draw + p_away
    if s > 0:
        p_home, p_draw, p_away = p_home / s, p_draw / s, p_away / s

    out = {
        "home": p_home, "draw": p_draw, "away": p_away,
        "double_1x": p_home + p_draw,
        "double_12": p_home + p_away,
        "double_x2": p_draw + p_away,
        "over_0_5": float(grid[tot >= 1].sum()),
        "over_1_5": float(grid[tot >= 2].sum()),
        "over_2_5": float(grid[tot >= 3].sum()),
        "over_3_5": float(grid[tot >= 4].sum()),
        "btts_yes": float(grid[(hg > 0) & (ag > 0)].sum()),
    }
    out["under_0_5"] = 1.0 - out["over_0_5"]
    out["under_1_5"] = 1.0 - out["over_1_5"]
    out["under_2_5"] = 1.0 - out["over_2_5"]
    out["under_3_5"] = 1.0 - out["over_3_5"]
    out["btts_no"] = 1.0 - out["btts_yes"]
    return out


def top_correct_scores(grid: np.ndarray, k: int = 5):
    """I k risultati esatti piu' probabili come [(x, y, prob), ...]."""
    n = grid.shape[0]
    flat = [(x, y, float(grid[x, y])) for x in range(n) for y in range(n)]
    flat.sort(key=lambda t: t[2], reverse=True)
    return flat[:k]


def expected_goals(grid: np.ndarray):
    """Gol attesi (casa, trasferta) implicati dalla matrice normalizzata."""
    n = grid.shape[0]
    hg = np.arange(n).reshape(-1, 1)
    ag = np.arange(n).reshape(1, -1)
    return float((grid * hg).sum()), float((grid * ag).sum())


@dataclass(frozen=True)
class MatchScoreline:
    """Una scoreline regolamentare (90') usata per il fit."""
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int
    weight: float = 1.0  # peso time-decay
