from __future__ import annotations

import numpy as np


def compute_profit_balance(odds: np.ndarray) -> float:
    """
    Computes Profit Balance metric given array of odds.
    Returns a float (lower is better in original formulation).
    """
    odds = np.asarray(odds, dtype=float)
    odds = odds[~np.isnan(odds)]
    if odds.size == 0:
        return float("nan")
    normalized_sum = (1.0 / odds).sum()
    if normalized_sum == 0:
        return float("nan")
    normalized_factor = (1.0 - (1.0 / normalized_sum)) * 100.0
    normalized_odds = (100.0 - normalized_factor) / odds
    normalized_profit = normalized_odds * (odds - 1.0)
    normalized_profit_balance = normalized_profit.sum() / 100.0 + 1.0
    profit_balance = 1 / normalized_profit_balance
    return round(float(profit_balance), 2)
