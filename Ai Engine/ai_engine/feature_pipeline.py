from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Tuple
import json

import pandas as pd

from .ai_config import FORM_WINDOWS, ODDS_LINES
from .db_adapter import (
    fetch_fixtures_for_date,
    fetch_matches_for_league_seasons,
    fetch_related_by_fixture_ids,
    fetch_standings_by_league_seasons,
)
from .elo_ratings import compute_elo_features
from .preprocessing.statistics import build_team_window_stats


def _sanitize_col(name: str) -> str:
    return (
        name.strip()
        .lower()
        .replace("%", "pct")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def _safe_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _odds_features(odds_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    if not odds_rows:
        return pd.DataFrame(columns=["fixture_id"])
    df = pd.DataFrame(odds_rows)
    if df.empty:
        return pd.DataFrame(columns=["fixture_id"])

    df["market_name"] = df["market_name"].fillna("").str.lower()
    df["label"] = df["label"].fillna("").str.lower()

    def pick_value(sub: pd.DataFrame) -> float:
        if "snapshot_time" in sub.columns and sub["snapshot_time"].notna().any():
            sub = sub.copy()
            sub["snapshot_time"] = pd.to_datetime(sub["snapshot_time"], errors="coerce")
            sub = sub.dropna(subset=["snapshot_time"]).sort_values("snapshot_time")
            if sub.empty:
                vals = sub["odd_value"].dropna().astype(float)
                return float(vals.median()) if not vals.empty else float("nan")
            last_ts = sub["snapshot_time"].iloc[-1]
            vals = sub.loc[sub["snapshot_time"] == last_ts, "odd_value"].dropna().astype(float)
            return float(vals.median()) if not vals.empty else float("nan")
        vals = sub["odd_value"].dropna().astype(float)
        return float(vals.median()) if not vals.empty else float("nan")

    rows = []
    for fixture_id, g in df.groupby("fixture_id"):
        row: Dict[str, Any] = {"fixture_id": fixture_id}

        # 1X2
        row["odds_1x2_home"] = pick_value(g[g["label"].isin({"home", "1"})])
        row["odds_1x2_draw"] = pick_value(g[g["label"].isin({"draw", "x"})])
        row["odds_1x2_away"] = pick_value(g[g["label"].isin({"away", "2"})])

        # Over/Under 2.5
        for line in ODDS_LINES:
            over_mask = g["label"].str.contains(f"over {line}")
            under_mask = g["label"].str.contains(f"under {line}")
            row[f"odds_over_{str(line).replace('.', '_')}"] = pick_value(g[over_mask])
            row[f"odds_under_{str(line).replace('.', '_')}"] = pick_value(g[under_mask])

        # BTTS
        row["odds_btts_yes"] = pick_value(g[g["label"].isin({"yes", "btts_yes"})])
        row["odds_btts_no"] = pick_value(g[g["label"].isin({"no", "btts_no"})])

        rows.append(row)

    return pd.DataFrame(rows)


def _odds_features_from_raw_json(fixtures_df: pd.DataFrame) -> pd.DataFrame:
    if fixtures_df.empty or "raw_json_odds" not in fixtures_df.columns:
        return pd.DataFrame(columns=["fixture_id"])

    rows = []
    for _, row in fixtures_df.iterrows():
        fixture_id = row.get("fixture_id")
        raw = row.get("raw_json_odds")
        if raw is None or fixture_id is None:
            continue
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                continue
        if not isinstance(raw, dict):
            continue

        values = []
        for bm in raw.get("bookmakers", []) or []:
            for bet in bm.get("bets", []) or []:
                bet_name = str(bet.get("name", "")).lower()
                for v in bet.get("values", []) or []:
                    values.append(
                        {
                            "fixture_id": fixture_id,
                            "market_name": bet_name,
                            "label": str(v.get("value", "")).lower(),
                            "odd_value": v.get("odd"),
                            "snapshot_time": raw.get("update"),
                        }
                    )
        if values:
            rows.extend(values)

    if not rows:
        return pd.DataFrame(columns=["fixture_id"])
    return _odds_features(rows)


def _events_features(events_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    if not events_rows:
        return pd.DataFrame(columns=["fixture_id"])
    df = pd.DataFrame(events_rows)
    if df.empty:
        return pd.DataFrame(columns=["fixture_id"])

    df["event_type"] = df["event_type"].fillna("").str.lower()
    df["detail"] = df["detail"].fillna("").str.lower()

    df["is_goal"] = df["event_type"].eq("goal")
    df["is_yellow"] = df["detail"].str.contains("yellow")
    df["is_red"] = df["detail"].str.contains("red")

    agg = (
        df.groupby(["fixture_id", "team_id"], dropna=False)
        .agg(
            goals=("is_goal", "sum"),
            yellow_cards=("is_yellow", "sum"),
            red_cards=("is_red", "sum"),
            avg_goal_minute=("minute", "mean"),
        )
        .reset_index()
    )

    # Add first (minimum) goal minute per team per fixture — only from goal events.
    # avg_goal_minute is a poor proxy for "target_first_goal_before_30" because
    # a team scoring at 10' and 70' has avg=40' which incorrectly signals "no early goal".
    goal_events = df[df["is_goal"]].copy()
    if not goal_events.empty:
        goal_timing = (
            goal_events.groupby(["fixture_id", "team_id"], dropna=False)
            .agg(min_goal_minute=("minute", "min"))
            .reset_index()
        )
        agg = agg.merge(goal_timing, on=["fixture_id", "team_id"], how="left")
    else:
        agg["min_goal_minute"] = float("nan")

    return agg


def _team_stats_features(team_stats_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    if not team_stats_rows:
        return pd.DataFrame(columns=["fixture_id"])
    df = pd.DataFrame(team_stats_rows)
    if df.empty:
        return pd.DataFrame(columns=["fixture_id"])

    df["stat_type"] = df["stat_type"].fillna("").apply(_sanitize_col)
    df["value_numeric"] = _safe_num(df["value_numeric"])

    pivot = (
        df.pivot_table(
            index=["fixture_id", "team_id"],
            columns="stat_type",
            values="value_numeric",
            aggfunc="mean",
        )
        .reset_index()
    )
    pivot.columns = [str(c) for c in pivot.columns]
    return pivot


def _player_stats_features(player_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    if not player_rows:
        return pd.DataFrame(columns=["fixture_id"])
    df = pd.DataFrame(player_rows)
    if df.empty:
        return pd.DataFrame(columns=["fixture_id"])

    numeric_cols = [
        "minutes",
        "shots_total",
        "shots_on",
        "goals_total",
        "assists_total",
        "passes_total",
        "passes_key",
        "passes_accurate",
        "tackles_total",
        "interceptions",
        "duels_total",
        "duels_won",
        "dribbles_attempts",
        "dribbles_success",
        "fouls_drawn",
        "fouls_committed",
        "yellow_cards",
        "red_cards",
        "offsides",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = _safe_num(df[col])

    if "rating" in df.columns:
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")

    agg_map = {col: "sum" for col in numeric_cols if col in df.columns}
    if "rating" in df.columns:
        agg_map["rating"] = "mean"

    agg = df.groupby(["fixture_id", "team_id"], dropna=False).agg(agg_map).reset_index()
    return agg


def _standings_features(standings_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    if not standings_rows:
        return pd.DataFrame(columns=["league_id"])
    df = pd.DataFrame(standings_rows)
    if df.empty:
        return pd.DataFrame(columns=["league_id"])
    return df


def _merge_team_side(
    base: pd.DataFrame,
    side_df: pd.DataFrame,
    side_prefix: str,
    team_col: str,
) -> pd.DataFrame:
    if side_df.empty:
        return base
    side_df = side_df.copy()
    side_df = side_df.add_prefix(f"{side_prefix}_")
    return base.merge(
        side_df,
        how="left",
        left_on=["fixture_id", team_col],
        right_on=[f"{side_prefix}_fixture_id", f"{side_prefix}_team_id"],
    )


def _merge_historical_features(
    base: pd.DataFrame,
    hist_df: pd.DataFrame,
    side_prefix: str,
    team_col: str,
) -> pd.DataFrame:
    if hist_df.empty:
        return base

    base = base.copy()
    base["fixture_date"] = pd.to_datetime(base["fixture_date"], errors="coerce")
    if getattr(base["fixture_date"].dt, "tz", None) is not None:
        base["fixture_date"] = base["fixture_date"].dt.tz_convert(None)
    if team_col in base.columns:
        base = base.dropna(subset=[team_col, "fixture_date"])
    if team_col in base.columns:
        base[team_col] = pd.to_numeric(base[team_col], errors="coerce").astype("Int64")
    hist_df = hist_df.copy()
    hist_df["fixture_date"] = pd.to_datetime(hist_df["fixture_date"], errors="coerce")
    if getattr(hist_df["fixture_date"].dt, "tz", None) is not None:
        hist_df["fixture_date"] = hist_df["fixture_date"].dt.tz_convert(None)
    if "team_id" in hist_df.columns and team_col != "team_id":
        hist_df = hist_df.rename(columns={"team_id": team_col})
    if team_col in hist_df.columns:
        hist_df[team_col] = pd.to_numeric(hist_df[team_col], errors="coerce").astype("Int64")
    hist_df = hist_df.dropna(subset=[team_col, "fixture_date"])

    base = base.sort_values("fixture_date")
    hist_df = hist_df.sort_values("fixture_date")

    merged = pd.merge_asof(
        base,
        hist_df,
        by=team_col,
        on="fixture_date",
        direction="backward",
        allow_exact_matches=False,
    )

    hist_cols = [c for c in hist_df.columns if c not in [team_col, "fixture_date"]]
    for c in hist_cols:
        merged.rename(columns={c: f"{side_prefix}_{c}"}, inplace=True)

    return merged


def _build_team_match_base(history_df: pd.DataFrame) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame()

    history_df = history_df.copy()
    history_df["fixture_date"] = pd.to_datetime(history_df["fixture_date"], errors="coerce")

    home = history_df[["fixture_id", "fixture_date", "home_team_id", "goals_home", "goals_away"]].copy()
    home.rename(columns={"home_team_id": "team_id"}, inplace=True)
    home["gf"] = _safe_num(home["goals_home"])
    home["ga"] = _safe_num(home["goals_away"])
    home.drop(columns=["goals_home", "goals_away"], inplace=True)

    away = history_df[["fixture_id", "fixture_date", "away_team_id", "goals_home", "goals_away"]].copy()
    away.rename(columns={"away_team_id": "team_id"}, inplace=True)
    away["gf"] = _safe_num(away["goals_away"])
    away["ga"] = _safe_num(away["goals_home"])
    away.drop(columns=["goals_home", "goals_away"], inplace=True)

    return pd.concat([home, away], ignore_index=True)


def _build_historical_team_features(
    history_df: pd.DataFrame,
    events_rows: List[Dict[str, Any]],
    team_stats_rows: List[Dict[str, Any]],
    player_stats_rows: List[Dict[str, Any]],
) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame()

    base = _build_team_match_base(history_df)
    if base.empty:
        return pd.DataFrame()

    events_df = _events_features(events_rows)
    team_stats_df = _team_stats_features(team_stats_rows)
    player_stats_df = _player_stats_features(player_stats_rows)
    merged = base.copy()
    for df in [events_df, team_stats_df, player_stats_df]:
        if not df.empty:
            merged = merged.merge(df, on=["fixture_id", "team_id"], how="left")

    # compute rolling means per team for windows
    merged = merged.sort_values("fixture_date")
    numeric_cols = [c for c in merged.columns if c not in ["fixture_id", "fixture_date", "team_id"]]

    out_rows = []
    for team_id, g in merged.groupby("team_id"):
        g = g.sort_values("fixture_date")
        for n in FORM_WINDOWS:
            roll = g[numeric_cols].rolling(n, min_periods=1).mean()
            roll["team_id"] = team_id
            roll["fixture_date"] = g["fixture_date"].values
            roll = roll.add_prefix(f"hist_w{n}_")
            out_rows.append(roll)

    if not out_rows:
        return pd.DataFrame()

    hist = pd.concat(out_rows, ignore_index=True)
    # Restore team_id and fixture_date columns that were prefixed by add_prefix.
    # Each window produces hist_w{n}_team_id and hist_w{n}_fixture_date;
    # we need to consolidate them back into canonical column names.
    for n in FORM_WINDOWS:
        tid = f"hist_w{n}_team_id"
        fdt = f"hist_w{n}_fixture_date"
        if tid in hist.columns and "team_id" not in hist.columns:
            hist.rename(columns={tid: "team_id"}, inplace=True)
        elif tid in hist.columns:
            # Fill missing team_id from this window's column, then drop it
            hist["team_id"] = hist["team_id"].combine_first(hist[tid])
            hist.drop(columns=[tid], inplace=True)
        if fdt in hist.columns and "fixture_date" not in hist.columns:
            hist.rename(columns={fdt: "fixture_date"}, inplace=True)
        elif fdt in hist.columns:
            hist["fixture_date"] = hist["fixture_date"].combine_first(hist[fdt])
            hist.drop(columns=[fdt], inplace=True)
    return hist


def _compute_form_features(history_df: pd.DataFrame) -> pd.DataFrame:
    if history_df.empty:
        return history_df

    history_df = history_df.copy()
    history_df["fixture_date"] = pd.to_datetime(history_df["fixture_date"], errors="coerce")
    history_df = history_df.dropna(subset=["fixture_date"])
    history_df = history_df.sort_values("fixture_date")
    history_df["home_goals"] = _safe_num(history_df["goals_home"])
    history_df["away_goals"] = _safe_num(history_df["goals_away"])

    rows = []
    for n in FORM_WINDOWS:
        home = history_df[["fixture_date", "home_team_id", "home_goals", "away_goals"]].copy()
        home.rename(columns={"home_team_id": "team_id"}, inplace=True)
        home["gf"] = home["home_goals"]
        home["ga"] = home["away_goals"]
        home.drop(columns=["home_goals", "away_goals"], inplace=True)
        home["is_home"] = 1

        away = history_df[["fixture_date", "away_team_id", "home_goals", "away_goals"]].copy()
        away.rename(columns={"away_team_id": "team_id"}, inplace=True)
        away["gf"] = away["away_goals"]
        away["ga"] = away["home_goals"]
        away.drop(columns=["home_goals", "away_goals"], inplace=True)
        away["is_home"] = 0

        team_matches = pd.concat([home, away], ignore_index=True).sort_values("fixture_date")

        team_matches[f"form_{n}_gf"] = (
            team_matches.groupby("team_id")["gf"].rolling(n, min_periods=1).mean().reset_index(level=0, drop=True)
        )
        team_matches[f"form_{n}_ga"] = (
            team_matches.groupby("team_id")["ga"].rolling(n, min_periods=1).mean().reset_index(level=0, drop=True)
        )
        team_matches[f"form_{n}_gd"] = team_matches[f"form_{n}_gf"] - team_matches[f"form_{n}_ga"]

        rows.append(team_matches[["fixture_date", "team_id", f"form_{n}_gf", f"form_{n}_ga", f"form_{n}_gd"]])

    merged = rows[0]
    for r in rows[1:]:
        merged = merged.merge(r, on=["fixture_date", "team_id"], how="left")
    return merged


def _build_h2h_features(df: pd.DataFrame, history_df: pd.DataFrame) -> pd.DataFrame:
    """Compute head-to-head stats from the last 5 meetings between the two teams.

    Optimised: pre-groups history by team-pair key for O(1) lookup per fixture
    instead of O(n×h) full-scan per row.
    """
    if history_df.empty or df.empty:
        return df

    hist = history_df.copy()
    hist["fixture_date"] = pd.to_datetime(hist["fixture_date"], errors="coerce")
    hist["goals_home"] = _safe_num(hist["goals_home"])
    hist["goals_away"] = _safe_num(hist["goals_away"])
    hist = hist.dropna(subset=["fixture_date", "home_team_id", "away_team_id"])
    hist["home_team_id"] = hist["home_team_id"].astype(int)
    hist["away_team_id"] = hist["away_team_id"].astype(int)
    hist = hist.sort_values("fixture_date")

    # Build pair-key index: frozenset(home, away) → sorted list of rows
    from collections import defaultdict
    pair_index: dict = defaultdict(list)
    for row_tuple in hist[["fixture_date", "home_team_id", "away_team_id",
                           "goals_home", "goals_away"]].itertuples(index=False):
        key = (min(row_tuple[1], row_tuple[2]), max(row_tuple[1], row_tuple[2]))
        pair_index[key].append(row_tuple)

    empty_rec = {"h2h_matches": 0, "h2h_home_wins": 0,
                 "h2h_draws": 0, "h2h_avg_goals": float("nan")}

    h2h_records = []
    for _, row in df.iterrows():
        h_id = row.get("home_team_id")
        a_id = row.get("away_team_id")
        match_date = pd.to_datetime(row.get("fixture_date"), errors="coerce")

        if pd.isna(h_id) or pd.isna(a_id) or pd.isna(match_date):
            h2h_records.append(empty_rec.copy())
            continue

        h_id, a_id = int(h_id), int(a_id)
        key = (min(h_id, a_id), max(h_id, a_id))
        meetings = pair_index.get(key, [])

        # Filter to pre-match only, take last 5
        prior = [m for m in meetings if m[0] < match_date]
        last5 = prior[-5:] if len(prior) > 5 else prior

        if not last5:
            h2h_records.append(empty_rec.copy())
        else:
            home_wins = 0
            draws = 0
            total_goals = 0.0
            for m in last5:
                gh, ga = m[3], m[4]
                m_home = m[1]  # home_team_id of this historical match
                if pd.notna(gh) and pd.notna(ga):
                    total_goals += gh + ga
                    if gh == ga:
                        draws += 1
                    elif (m_home == h_id and gh > ga) or (m_home != h_id and ga > gh):
                        home_wins += 1
            avg_goals = total_goals / len(last5) if last5 else float("nan")
            h2h_records.append({
                "h2h_matches": len(last5),
                "h2h_home_wins": home_wins,
                "h2h_draws": draws,
                "h2h_avg_goals": round(avg_goals, 2),
            })

    h2h_df = pd.DataFrame(h2h_records, index=df.index)
    return pd.concat([df, h2h_df], axis=1)


def build_feature_dataframe_for_fixtures(
    fixtures_df: pd.DataFrame,
    history_df: pd.DataFrame,
    league_seasons_tuples: List[Tuple[int, int]],
    include_odds: bool = True,
    include_player_stats: bool = True,
    include_events: bool = True,
    include_team_stats: bool = True,
    include_team_window_stats: bool = True,
    pre_match: bool = False,
) -> pd.DataFrame:
    if fixtures_df.empty:
        return pd.DataFrame()

    fixture_ids = fixtures_df["fixture_id"].dropna().astype(int).tolist()

    events_rows = []
    odds_rows = []
    team_stats_rows = []
    player_stats_rows = []
    odds_market_filter = [
        "Match Winner",
        "Goals Over/Under",
        "Both Teams Score",
        "Over/Under",
        "Goals Over Under",
    ]

    if pre_match:
        # use historical aggregates
        history_fixture_ids = history_df["fixture_id"].dropna().astype(int).tolist()
        if include_events:
            events_rows = fetch_related_by_fixture_ids(
                "match_events",
                history_fixture_ids,
                "fixture_id,team_id,event_type,detail,minute",
            )
        if include_team_stats:
            team_stats_rows = fetch_related_by_fixture_ids(
                "match_team_stats",
                history_fixture_ids,
                "fixture_id,team_id,stat_type,value_numeric",
            )
        if include_player_stats:
            player_stats_rows = fetch_related_by_fixture_ids(
                "match_player_stats",
                history_fixture_ids,
                "fixture_id,team_id,minutes,rating,shots_total,shots_on,goals_total,assists_total,"
                "passes_total,passes_key,passes_accurate,tackles_total,interceptions,duels_total,duels_won,"
                "dribbles_attempts,dribbles_success,fouls_drawn,fouls_committed,yellow_cards,red_cards,offsides",
            )
        # odds for fixture (pre-match)
        if include_odds:
            odds_rows = fetch_related_by_fixture_ids(
                "match_odds",
                fixture_ids,
                "fixture_id,market_name,label,odd_value,snapshot_time",
                extra_filters=[("in", "market_name", odds_market_filter)],
            )
    else:
        if include_events:
            events_rows = fetch_related_by_fixture_ids(
                "match_events",
                fixture_ids,
                "fixture_id,team_id,event_type,detail,minute",
            )
        if include_odds:
            odds_rows = fetch_related_by_fixture_ids(
                "match_odds",
                fixture_ids,
                "fixture_id,market_name,label,odd_value,snapshot_time",
                extra_filters=[("in", "market_name", odds_market_filter)],
            )
        if include_team_stats:
            team_stats_rows = fetch_related_by_fixture_ids(
                "match_team_stats",
                fixture_ids,
                "fixture_id,team_id,stat_type,value_numeric",
            )
        if include_player_stats:
            player_stats_rows = fetch_related_by_fixture_ids(
                "match_player_stats",
                fixture_ids,
                "fixture_id,team_id,minutes,rating,shots_total,shots_on,goals_total,assists_total,"
                "passes_total,passes_key,passes_accurate,tackles_total,interceptions,duels_total,duels_won,"
                "dribbles_attempts,dribbles_success,fouls_drawn,fouls_committed,yellow_cards,red_cards,offsides",
            )
    standings_rows = fetch_standings_by_league_seasons(league_seasons_tuples)

    events_df = _events_features(events_rows) if include_events else pd.DataFrame()
    odds_df = _odds_features(odds_rows) if include_odds else pd.DataFrame()
    if include_odds and pre_match and "raw_json_odds" in fixtures_df.columns:
        raw_odds_df = _odds_features_from_raw_json(fixtures_df)
        if odds_df.empty:
            odds_df = raw_odds_df
        elif not raw_odds_df.empty:
            merged = odds_df.merge(raw_odds_df, on="fixture_id", how="outer", suffixes=("", "_raw"))
            for col in [c for c in merged.columns if c.endswith("_raw")]:
                base_col = col.replace("_raw", "")
                if base_col in merged.columns:
                    merged[base_col] = merged[base_col].combine_first(merged[col])
                merged.drop(columns=[col], inplace=True)
            odds_df = merged
    team_stats_df = _team_stats_features(team_stats_rows) if include_team_stats else pd.DataFrame()
    player_stats_df = _player_stats_features(player_stats_rows) if include_player_stats else pd.DataFrame()

    hist_team_df = pd.DataFrame()
    if pre_match:
        hist_team_df = _build_historical_team_features(
            history_df, events_rows, team_stats_rows, player_stats_rows
        )
    team_window_stats_df = pd.DataFrame()
    if pre_match and include_team_window_stats and not history_df.empty:
        team_window_stats_df = build_team_window_stats(history_df, FORM_WINDOWS)
    standings_df = _standings_features(standings_rows)

    # Base merge
    base = fixtures_df.copy()

    # Team-side merges
    if pre_match:
        base = _merge_historical_features(base, hist_team_df, "home_hist", "home_team_id")
        base = _merge_historical_features(base, hist_team_df, "away_hist", "away_team_id")
        base = _merge_historical_features(base, team_window_stats_df, "home_stat", "home_team_id")
        base = _merge_historical_features(base, team_window_stats_df, "away_stat", "away_team_id")
    else:
        base = _merge_team_side(base, team_stats_df, "home_stats", "home_team_id")
        base = _merge_team_side(base, team_stats_df, "away_stats", "away_team_id")
        base = _merge_team_side(base, player_stats_df, "home_players", "home_team_id")
        base = _merge_team_side(base, player_stats_df, "away_players", "away_team_id")
        base = _merge_team_side(base, events_df, "home_events", "home_team_id")
        base = _merge_team_side(base, events_df, "away_events", "away_team_id")

    # Standings for home/away
    if not standings_df.empty:
        standings_df = standings_df.rename(
            columns={
                "team_id": "standings_team_id",
                "league_id": "standings_league_id",
                "season_year": "standings_season_year",
            }
        )
        base = base.merge(
            standings_df.add_prefix("home_"),
            how="left",
            left_on=["league_id", "season_year", "home_team_id"],
            right_on=["home_standings_league_id", "home_standings_season_year", "home_standings_team_id"],
        )
        base = base.merge(
            standings_df.add_prefix("away_"),
            how="left",
            left_on=["league_id", "season_year", "away_team_id"],
            right_on=["away_standings_league_id", "away_standings_season_year", "away_standings_team_id"],
        )

    # Odds merge
    if not odds_df.empty:
        base = base.merge(odds_df, on="fixture_id", how="left")

    # Implied probabilities from 1X2 odds (normalised to remove bookmaker margin)
    if "odds_1x2_home" in base.columns:
        base["implied_prob_home"] = 1.0 / base["odds_1x2_home"].clip(lower=1.01)
        base["implied_prob_draw"] = 1.0 / base["odds_1x2_draw"].clip(lower=1.01)
        base["implied_prob_away"] = 1.0 / base["odds_1x2_away"].clip(lower=1.01)
        total_imp = (
            base["implied_prob_home"] + base["implied_prob_draw"] + base["implied_prob_away"]
        )
        base["fair_prob_home"] = base["implied_prob_home"] / total_imp
        base["fair_prob_draw"] = base["implied_prob_draw"] / total_imp
        base["fair_prob_away"] = base["implied_prob_away"] / total_imp

    # Form features
    if not history_df.empty:
        form_df = _compute_form_features(history_df)
        base = _merge_historical_features(base, form_df, "home_form", "home_team_id")
        base = _merge_historical_features(base, form_df, "away_form", "away_team_id")

    # H2H (Head-to-Head) features
    if not history_df.empty:
        try:
            base = _build_h2h_features(base, history_df)
        except Exception:
            pass  # H2H is a nice-to-have, don't break the pipeline

    # ELO ratings — computed from historical match results
    if not history_df.empty:
        try:
            elo_hist = compute_elo_features(history_df)
            # Build ELO lookup: (team_id, fixture_date) → elo_value
            # Merge via merge_asof on home/away team_id
            elo_home = elo_hist[["fixture_date", "home_team_id", "home_elo"]].copy()
            elo_home = elo_home.rename(columns={"home_team_id": "team_id", "home_elo": "elo"})
            elo_away = elo_hist[["fixture_date", "away_team_id", "away_elo"]].copy()
            elo_away = elo_away.rename(columns={"away_team_id": "team_id", "away_elo": "elo"})
            elo_all = pd.concat([elo_home, elo_away], ignore_index=True)
            elo_all = elo_all.drop_duplicates(subset=["fixture_date", "team_id"], keep="last")
            base = _merge_historical_features(base, elo_all, "home_elo", "home_team_id")
            base = _merge_historical_features(base, elo_all, "away_elo", "away_team_id")
            if "home_elo_elo" in base.columns and "away_elo_elo" in base.columns:
                base["elo_diff"] = base["home_elo_elo"] - base["away_elo_elo"]
        except Exception:
            pass  # ELO is a nice-to-have, don't break the pipeline

    return base


def build_feature_dataframe(target_date: date) -> pd.DataFrame:
    fixtures_rows = fetch_fixtures_for_date(target_date)
    if not fixtures_rows:
        return pd.DataFrame()

    fixtures_df = pd.DataFrame(fixtures_rows)

    league_seasons = (
        fixtures_df[["league_id", "season_year"]].dropna().drop_duplicates().astype(int).values.tolist()
    )
    league_seasons_tuples: List[Tuple[int, int]] = [(int(x[0]), int(x[1])) for x in league_seasons]

    history_rows = fetch_matches_for_league_seasons(league_seasons_tuples)
    history_df = pd.DataFrame(history_rows)

    return build_feature_dataframe_for_fixtures(
        fixtures_df, history_df, league_seasons_tuples, pre_match=True
    )
