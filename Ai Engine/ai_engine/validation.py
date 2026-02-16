from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd


def _pick_form_value(row: pd.Series, prefix: str, metric: str) -> Optional[float]:
    for n in [10, 15, 5]:
        col = f"{prefix}_form_form_{n}_{metric}"
        if col in row and pd.notna(row[col]):
            return float(row[col])
    return None


def suggest_market(row: pd.Series) -> Dict[str, str]:
    """
    Heuristic market suggestion based on available features.
    This does not use model outputs yet.
    """
    notes: List[str] = []

    home_gf = _pick_form_value(row, "home", "gf")
    away_gf = _pick_form_value(row, "away", "gf")
    home_ga = _pick_form_value(row, "home", "ga")
    away_ga = _pick_form_value(row, "away", "ga")

    expected_goals = None
    if home_gf is not None and away_gf is not None:
        expected_goals = home_gf + away_gf
        notes.append(f"expected_goals={expected_goals:.2f}")

    # Suggested market
    market = "no_clear_signal"
    reason = "Insufficient data"

    if expected_goals is not None:
        if expected_goals >= 2.6:
            market = "over_2_5"
            reason = "High expected goals from form"
        elif expected_goals <= 2.2:
            market = "under_2_5"
            reason = "Low expected goals from form"

    if home_gf is not None and away_gf is not None:
        if home_gf >= 1.0 and away_gf >= 1.0:
            notes.append("btts_yes_signal")

    return {
        "market": market,
        "reason": reason,
        "notes": "; ".join(notes) if notes else "",
    }


def validate_conflicts(model_outputs: Dict[str, Dict[str, float]]) -> str:
    """
    Placeholder: in future, compare model outputs and generate justification text.
    """
    if not model_outputs:
        return "No model outputs provided"
    return "Model outputs present; conflict analysis not yet implemented"

