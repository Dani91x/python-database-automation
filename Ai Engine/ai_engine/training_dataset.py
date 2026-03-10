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

    Uses pre_match=True so that:
    - home_stat_* / away_stat_* (win_rate, draw_rate, loss_rate over rolling
      windows) are computed from historical data and included as features.
    - home_hist_* / away_hist_* (rolling aggregates of team stats and events)
      are included where available.
    These features are also available at prediction time (predict_fixture.py
    already uses pre_match=True), so train/predict feature sets now match.
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
        pre_match=True,
    )

    # Targets from matches + team stats + events
    features_df = add_targets_from_matches(features_df)
    features_df = add_targets_from_team_stats(features_df)
    features_df = add_targets_from_events(features_df)

    return features_df
