from __future__ import annotations

from typing import Dict

import pandas as pd


def _result_1x2(row: pd.Series) -> str | None:
    gh = row.get("goals_home")
    ga = row.get("goals_away")
    if pd.isna(gh) or pd.isna(ga):
        return None
    if gh > ga:
        return "H"
    if gh < ga:
        return "A"
    return "D"


def _over_under(total_goals: float, line: float) -> str | None:
    if pd.isna(total_goals):
        return None
    return "over" if total_goals > line else "under"


def add_targets_from_matches(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds all available targets from matches table columns.
    Targets are appended as new columns. Does not modify inputs in-place.
    """
    if df.empty:
        return df

    out = df.copy()
    out["goals_home"] = pd.to_numeric(out.get("goals_home"), errors="coerce")
    out["goals_away"] = pd.to_numeric(out.get("goals_away"), errors="coerce")
    out["halftime_home"] = pd.to_numeric(out.get("halftime_home"), errors="coerce")
    out["halftime_away"] = pd.to_numeric(out.get("halftime_away"), errors="coerce")
    out["fulltime_home"] = pd.to_numeric(out.get("fulltime_home"), errors="coerce")
    out["fulltime_away"] = pd.to_numeric(out.get("fulltime_away"), errors="coerce")

    out["target_1x2"] = out.apply(_result_1x2, axis=1)

    out["target_btts"] = (out["goals_home"] > 0) & (out["goals_away"] > 0)

    out["target_total_goals"] = out["goals_home"] + out["goals_away"]

    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        out[f"target_over_{str(line).replace('.', '_')}"] = out["target_total_goals"] > line

    out["target_clean_sheet_home"] = out["goals_away"] == 0
    out["target_clean_sheet_away"] = out["goals_home"] == 0

    # Team goals lines
    for line in [0.5, 1.5, 2.5]:
        out[f"target_home_over_{str(line).replace('.', '_')}"] = out["goals_home"] > line
        out[f"target_away_over_{str(line).replace('.', '_')}"] = out["goals_away"] > line

    # HT/FT
    out["target_ht_1x2"] = out.apply(
        lambda r: _result_1x2(pd.Series({"goals_home": r["halftime_home"], "goals_away": r["halftime_away"]})),
        axis=1,
    )
    out["target_ft_1x2"] = out.apply(
        lambda r: _result_1x2(pd.Series({"goals_home": r["fulltime_home"], "goals_away": r["fulltime_away"]})),
        axis=1,
    )
    out["target_ht_ft"] = out["target_ht_1x2"].fillna("") + "_" + out["target_ft_1x2"].fillna("")

    # First Half Over 0.5 (direct boolean target)
    # Use .where() to propagate NaN when halftime data is missing, instead of
    # silently coercing NaN > 0 to False (which creates false negatives).
    ht_total = out["halftime_home"] + out["halftime_away"]
    out["target_ht_over_0_5"] = (ht_total > 0).where(ht_total.notna())

    # Exact score — keep NaN when goals are missing instead of using "-1--1"
    has_goals = out["goals_home"].notna() & out["goals_away"].notna()
    out["target_exact_score"] = (
        out["goals_home"].astype("Int64").astype(str) + "-" + out["goals_away"].astype("Int64").astype(str)
    ).where(has_goals, other=None)

    return out


def add_targets_from_team_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds targets derived from team stats (corners, shots on target).
    Expects columns like home_stats_corner_kicks, away_stats_corner_kicks, etc.
    """
    if df.empty:
        return df

    out = df.copy()
    hc = pd.to_numeric(out.get("home_stats_corner_kicks"), errors="coerce")
    ac = pd.to_numeric(out.get("away_stats_corner_kicks"), errors="coerce")
    out["target_corners_total"] = hc + ac

    hsot = pd.to_numeric(out.get("home_stats_shots_on_goal"), errors="coerce")
    asot = pd.to_numeric(out.get("away_stats_shots_on_goal"), errors="coerce")
    out["target_sot_total"] = hsot + asot

    return out


def add_targets_from_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds targets derived from match events (cards, goal timing).
    Expects columns like home_events_yellow_cards, away_events_yellow_cards, etc.
    """
    if df.empty:
        return df

    out = df.copy()
    def _series(col: str) -> pd.Series:
        if col in out.columns:
            return pd.to_numeric(out[col], errors="coerce")
        return pd.Series([pd.NA] * len(out))

    hy = _series("home_events_yellow_cards")
    ay = _series("away_events_yellow_cards")
    hr = _series("home_events_red_cards")
    ar = _series("away_events_red_cards")

    out["target_cards_total"] = hy + ay + hr + ar
    out["target_home_cards"] = hy + hr
    out["target_away_cards"] = ay + ar

    # Goal timing — use minimum (first) goal minute when available,
    # fallback to average as proxy.  The original code used avg_goal_minute
    # which is logically wrong: a team scoring at 10' and 70' has avg=40'
    # and would be classified as "no first goal before 30'" even though it did.
    hgm_min = _series("home_events_min_goal_minute")
    agm_min = _series("away_events_min_goal_minute")
    hgm = hgm_min.combine_first(_series("home_events_avg_goal_minute"))
    agm = agm_min.combine_first(_series("away_events_avg_goal_minute"))
    # If both teams have no goal events at all, the target is False (no goal happened).
    # Use .where() to preserve NaN only where we genuinely lack any timing data.
    first_goal_raw = (hgm < 30) | (agm < 30)
    out["target_first_goal_before_30"] = first_goal_raw.fillna(False)
    goal_in_2h_raw = (hgm >= 46) | (agm >= 46)
    out["target_goal_in_2h"] = goal_in_2h_raw.fillna(False)

    return out
