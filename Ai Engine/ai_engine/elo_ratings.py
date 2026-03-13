"""
ELO rating tracker per team. Computes pre-match ELO for each fixture.

Usage:
    df = compute_elo_features(df)
    # Adds columns: home_elo, away_elo, elo_diff
"""
from __future__ import annotations

import pandas as pd

DEFAULT_ELO = 1500.0
K_FACTOR = 32.0


def compute_elo_features(
    df: pd.DataFrame,
    date_col: str = "fixture_date",
) -> pd.DataFrame:
    """
    Compute pre-match ELO ratings for home and away teams.

    Iterates chronologically, recording each team's ELO *before* the match,
    then updating it based on the result.

    Returns df with columns: home_elo, away_elo, elo_diff.
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.sort_values(date_col).reset_index(drop=True)

    elo: dict[int, float] = {}
    home_elos: list[float] = []
    away_elos: list[float] = []

    for _, row in df.iterrows():
        h_id = row.get("home_team_id")
        a_id = row.get("away_team_id")

        if pd.isna(h_id) or pd.isna(a_id):
            home_elos.append(DEFAULT_ELO)
            away_elos.append(DEFAULT_ELO)
            continue

        h_id = int(h_id)
        a_id = int(a_id)
        h_elo = elo.get(h_id, DEFAULT_ELO)
        a_elo = elo.get(a_id, DEFAULT_ELO)

        # Record pre-match ELO
        home_elos.append(h_elo)
        away_elos.append(a_elo)

        # Update ELO post-match if result is available
        gh = row.get("goals_home")
        ga = row.get("goals_away")
        if pd.notna(gh) and pd.notna(ga):
            actual_h = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
            exp_h = 1.0 / (1.0 + 10.0 ** ((a_elo - h_elo) / 400.0))
            elo[h_id] = h_elo + K_FACTOR * (actual_h - exp_h)
            elo[a_id] = a_elo + K_FACTOR * ((1.0 - actual_h) - (1.0 - exp_h))

    df["home_elo"] = home_elos
    df["away_elo"] = away_elos
    df["elo_diff"] = df["home_elo"] - df["away_elo"]

    return df
