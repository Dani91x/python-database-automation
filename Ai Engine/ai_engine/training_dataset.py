from __future__ import annotations

from typing import List, Tuple

import pandas as pd

from .db_adapter import (
    fetch_matches_full_for_league_seasons,
    fetch_standings_by_league_seasons,
)
from .feature_pipeline import build_feature_dataframe_for_fixtures
from .targets import add_targets_from_events, add_targets_from_matches, add_targets_from_team_stats


def build_training_dataset(
    league_seasons: List[Tuple[int, int]],
) -> pd.DataFrame:
    """
    Build a historical training dataset for given league_seasons.
    Uses matches as base, enriches with features, then adds all targets.
    """
    matches_rows = fetch_matches_full_for_league_seasons(league_seasons)
    if not matches_rows:
        return pd.DataFrame()

    matches_df = pd.DataFrame(matches_rows)

    history_df = matches_df.copy()
    features_df = build_feature_dataframe_for_fixtures(
        matches_df,
        history_df,
        league_seasons,
        include_odds=True,
        include_player_stats=False,
        include_events=True,
        include_team_stats=True,
    )

    # Targets from matches + team stats + events
    features_df = add_targets_from_matches(features_df)
    features_df = add_targets_from_team_stats(features_df)
    features_df = add_targets_from_events(features_df)

    return features_df
