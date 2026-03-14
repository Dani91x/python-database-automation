"""
ELO rating tracker per team. Computes pre-match ELO for each fixture.

K-factor is variable: higher for the first K_WARMUP_MATCHES games of a team
(faster convergence from the 1500 prior) then drops to K_FACTOR_STABLE.
This mimics the FIDE provisional rating approach and avoids the problem of
all newcomer teams anchored at 1500 for too long.

Usage:
    df = compute_elo_features(df)
    # Adds columns: home_elo, away_elo, elo_diff
"""
from __future__ import annotations

import pandas as pd

DEFAULT_ELO = 1500.0
K_FACTOR_STABLE  = 32.0   # K once team has played >= K_WARMUP_MATCHES
K_FACTOR_WARMUP  = 56.0   # K during first K_WARMUP_MATCHES (faster convergence)
K_WARMUP_MATCHES = 10     # matches to use warmup K before switching to stable K


def _k_factor(matches_played: int) -> float:
    """Return K-factor based on how many matches the team has played so far."""
    return K_FACTOR_WARMUP if matches_played < K_WARMUP_MATCHES else K_FACTOR_STABLE


def compute_elo_features(
    df: pd.DataFrame,
    date_col: str = "fixture_date",
) -> pd.DataFrame:
    """
    Compute pre-match ELO ratings for home and away teams.

    Iterates chronologically, recording each team's ELO *before* the match,
    then updating it based on the result. K-factor is higher during a team's
    first K_WARMUP_MATCHES games so the rating converges quickly from the
    1500 prior, then settles to K_FACTOR_STABLE.

    Returns df with columns: home_elo, away_elo, elo_diff.
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.sort_values(date_col).reset_index(drop=True)

    elo: dict[int, float] = {}
    matches_played: dict[int, int] = {}  # tracks games played per team for K selection
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
            k_h = _k_factor(matches_played.get(h_id, 0))
            k_a = _k_factor(matches_played.get(a_id, 0))
            elo[h_id] = h_elo + k_h * (actual_h - exp_h)
            elo[a_id] = a_elo + k_a * ((1.0 - actual_h) - (1.0 - exp_h))
            matches_played[h_id] = matches_played.get(h_id, 0) + 1
            matches_played[a_id] = matches_played.get(a_id, 0) + 1

    df["home_elo"] = home_elos
    df["away_elo"] = away_elos
    df["elo_diff"] = df["home_elo"] - df["away_elo"]

    return df
