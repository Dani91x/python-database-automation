from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from ai_engine.db_adapter import fetch_seasons_for_league, fetch_matches_full_for_league_seasons, _fetch_all
from ai_engine.feature_pipeline import build_feature_dataframe_for_fixtures
from ai_engine.coverage import build_coverage_report


def _group_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    return {
        "odds": [c for c in df.columns if c.startswith("odds_")],
        "form": [c for c in df.columns if c.startswith("home_form_") or c.startswith("away_form_")],
        "team_window_stats": [c for c in df.columns if c.startswith("home_stat_") or c.startswith("away_stat_")],
        "standings": [c for c in df.columns if c.startswith("home_standings_") or c.startswith("away_standings_")],
        "hist": [c for c in df.columns if c.startswith("home_hist_") or c.startswith("away_hist_")],
        "events_live": [c for c in df.columns if c.startswith("home_events_") or c.startswith("away_events_")],
        "team_stats_live": [c for c in df.columns if c.startswith("home_stats_") or c.startswith("away_stats_")],
        "player_stats_live": [c for c in df.columns if c.startswith("home_players_") or c.startswith("away_players_")],
    }


def audit_nulls(league_id: int, last_n_seasons: int = 3) -> str:
    seasons = fetch_seasons_for_league(league_id)
    seasons = seasons[-last_n_seasons:] if len(seasons) > last_n_seasons else seasons
    league_seasons = [(league_id, s) for s in seasons]
    matches_rows = fetch_matches_full_for_league_seasons(league_seasons)
    if not matches_rows:
        raise RuntimeError(f"No matches for league {league_id}")

    matches_df = pd.DataFrame(matches_rows)
    features_df = build_feature_dataframe_for_fixtures(
        matches_df,
        matches_df,
        league_seasons,
        include_odds=False,
        include_player_stats=False,
        include_events=True,
        include_team_stats=True,
        include_team_window_stats=True,
        pre_match=True,
    )

    if features_df.empty:
        raise RuntimeError("No features computed.")

    # Drop target columns if any
    features_df = features_df.drop(columns=[c for c in features_df.columns if c.startswith("target_")], errors="ignore")

    null_counts = features_df.isna().sum().sort_values(ascending=False)
    null_pct = (null_counts / len(features_df)).round(4)

    groups = _group_columns(features_df)
    group_summary = {}
    for name, cols in groups.items():
        if not cols:
            continue
        group_summary[name] = {
            "null_pct_avg": float(features_df[cols].isna().mean().mean()),
            "null_cols": int((features_df[cols].isna().mean() > 0).sum()),
            "total_cols": int(len(cols)),
        }

    coverage = build_coverage_report(features_df)

    report_dir = os.path.join("Ai Engine", "reports")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"audit_nulls_league_{league_id}.md")

    lines = []
    lines.append(f"# Audit Dati Null - League {league_id}")
    lines.append("")
    lines.append(f"Generated at: {datetime.now(timezone.utc).isoformat()} UTC")
    lines.append("")
    lines.append(f"Seasons: {seasons}")
    lines.append(f"Rows analizzate: {len(features_df)}")
    lines.append("")
    lines.append("Copertura gruppi (ok/total):")
    for k, v in coverage.items():
        lines.append(f"- {k}: {v.get('ok', 0)}/{v.get('total', 0)}")
    lines.append("")
    lines.append("Sintesi per gruppi (percentuale null media):")
    for k, v in group_summary.items():
        lines.append(
            f"- {k}: null_avg={v['null_pct_avg']:.2f} | cols_con_null={v['null_cols']}/{v['total_cols']}"
        )
    lines.append("")
    lines.append("Top 50 colonne con piu null:")
    for col, cnt in null_counts.head(50).items():
        lines.append(f"- {col}: {int(cnt)} ({null_pct[col]:.2%})")

    # Odds coverage from fixture_predictions raw_json_odds (if available)
    try:
        odds_present = 0
        odds_total = 0
        for league_id_i, season_year_i in league_seasons:
            rows = _fetch_all(
                "fixture_predictions",
                "fixture_id,raw_json_odds",
                filters=[("eq", "league_id", league_id_i), ("eq", "season_year", season_year_i)],
                page_size=1000,
            )
            odds_total += len(rows)
            odds_present += sum(1 for r in rows if r.get("raw_json_odds") is not None)
        if odds_total:
            lines.append("")
            lines.append(
                f"Copertura odds (raw_json_odds) in fixture_predictions: {odds_present}/{odds_total} "
                f"({odds_present/odds_total:.2%})"
            )
    except Exception:
        pass

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python audit_nulls.py <league_id> [last_n_seasons]")
    league_id = int(sys.argv[1])
    last_n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    out = audit_nulls(league_id, last_n)
    print(out)
