from __future__ import annotations

from typing import Dict, List

import pandas as pd


def _result_for_team(goals_for: float, goals_against: float) -> str | None:
    if pd.isna(goals_for) or pd.isna(goals_against):
        return None
    if goals_for > goals_against:
        return "W"
    if goals_for < goals_against:
        return "L"
    return "D"


def build_team_window_stats(history_df: pd.DataFrame, windows: List[int]) -> pd.DataFrame:
    """
    Build rolling stats per team using match history.
    Returns columns keyed by team_id and fixture_date so we can merge_asof.
    """
    if history_df.empty:
        return pd.DataFrame()

    df = history_df.copy()
    df["fixture_date"] = pd.to_datetime(df["fixture_date"], errors="coerce")
    df["goals_home"] = pd.to_numeric(df.get("goals_home"), errors="coerce")
    df["goals_away"] = pd.to_numeric(df.get("goals_away"), errors="coerce")

    home = df[["fixture_id", "fixture_date", "home_team_id", "goals_home", "goals_away"]].copy()
    home.rename(columns={"home_team_id": "team_id"}, inplace=True)
    home["gf"] = home["goals_home"]
    home["ga"] = home["goals_away"]
    home["venue"] = "H"

    away = df[["fixture_id", "fixture_date", "away_team_id", "goals_home", "goals_away"]].copy()
    away.rename(columns={"away_team_id": "team_id"}, inplace=True)
    away["gf"] = away["goals_away"]
    away["ga"] = away["goals_home"]
    away["venue"] = "A"

    team_matches = pd.concat([home, away], ignore_index=True)
    team_matches["result"] = team_matches.apply(lambda r: _result_for_team(r["gf"], r["ga"]), axis=1)
    team_matches = team_matches.sort_values(["team_id", "fixture_date"])

    out_frames: List[pd.DataFrame] = []
    for team_id, g in team_matches.groupby("team_id"):
        g = g.sort_values("fixture_date")

        # Pre-compute venue masks and rolling inputs once per team
        is_win = (g["result"] == "W").astype(float)
        is_draw = (g["result"] == "D").astype(float)
        is_loss = (g["result"] == "L").astype(float)
        home_mask = g["venue"] == "H"
        away_mask = g["venue"] == "A"

        for n in windows:
            roll = pd.DataFrame(index=g.index)
            roll["team_id"] = g["team_id"]
            roll["fixture_date"] = g["fixture_date"]

            # ── General rolling stats (all games) ──────────────────
            roll[f"stat_w{n}_wins"] = is_win.rolling(n, min_periods=1).sum()
            roll[f"stat_w{n}_draws"] = is_draw.rolling(n, min_periods=1).sum()
            roll[f"stat_w{n}_losses"] = is_loss.rolling(n, min_periods=1).sum()
            roll[f"stat_w{n}_gf"] = g["gf"].rolling(n, min_periods=1).mean()
            roll[f"stat_w{n}_ga"] = g["ga"].rolling(n, min_periods=1).mean()
            roll[f"stat_w{n}_gd"] = roll[f"stat_w{n}_gf"] - roll[f"stat_w{n}_ga"]
            roll[f"stat_w{n}_win_rate"] = roll[f"stat_w{n}_wins"] / n
            roll[f"stat_w{n}_loss_rate"] = roll[f"stat_w{n}_losses"] / n
            roll[f"stat_w{n}_draw_rate"] = roll[f"stat_w{n}_draws"] / n

            # ── Venue-specific rolling stats ───────────────────────
            # Compute on venue-filtered subset, then .reindex() to align
            # back to the full team timeline.  Rows where the team played
            # at the *other* venue get NaN, which is correct: merge_asof
            # will pick the latest non-NaN value for each (team, date).
            for venue_mask, prefix in [(home_mask, "home"), (away_mask, "away")]:
                venue_wins = is_win[venue_mask]
                venue_draws = is_draw[venue_mask]
                if venue_wins.empty:
                    roll[f"stat_w{n}_{prefix}_win_rate"] = float("nan")
                    roll[f"stat_w{n}_{prefix}_draw_rate"] = float("nan")
                else:
                    roll[f"stat_w{n}_{prefix}_win_rate"] = (
                        venue_wins.rolling(n, min_periods=1).mean()
                        .reindex(g.index)
                    )
                    roll[f"stat_w{n}_{prefix}_draw_rate"] = (
                        venue_draws.rolling(n, min_periods=1).mean()
                        .reindex(g.index)
                    )

            # Fallback: fill venue NaN with general rate (team has no
            # home/away games yet → use overall rate as proxy)
            roll[f"stat_w{n}_home_win_rate"] = roll[f"stat_w{n}_home_win_rate"].fillna(
                roll[f"stat_w{n}_win_rate"]
            )
            roll[f"stat_w{n}_home_draw_rate"] = roll[f"stat_w{n}_home_draw_rate"].fillna(
                roll[f"stat_w{n}_draw_rate"]
            )
            roll[f"stat_w{n}_away_win_rate"] = roll[f"stat_w{n}_away_win_rate"].fillna(
                roll[f"stat_w{n}_win_rate"]
            )
            roll[f"stat_w{n}_away_draw_rate"] = roll[f"stat_w{n}_away_draw_rate"].fillna(
                roll[f"stat_w{n}_draw_rate"]
            )

            out_frames.append(roll)

    if not out_frames:
        return pd.DataFrame()

    out = pd.concat(out_frames, ignore_index=True)
    return out
