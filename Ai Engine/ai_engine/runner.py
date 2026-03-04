from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from .ai_config import REPORT_DIR
from .coverage import build_coverage_report
from .feature_pipeline import build_feature_dataframe
from .report import write_report
from .validation import suggest_market
from .training_dataset import build_training_dataset
from .model_suite import train_and_predict
from .advanced_validation import aggregate_model_outputs, consensus, entropy
from .market_ranking import build_ranked_markets
from .seriea_model_export import train_and_save_all, upload_and_register
import logging

logger = logging.getLogger(__name__)


def run_daily_report(target_date: date | None = None, include_matches: bool = True) -> str:
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    df = build_feature_dataframe(target_date)

    if df.empty:
        Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)
        report_path = Path(REPORT_DIR) / f"{target_date.isoformat()}_report.md"
        write_report(target_date, df, {}, str(report_path), include_matches=False)
        return str(report_path)

    coverage = build_coverage_report(df)

    # Build training dataset per league (no mixing)
    league_seasons = (
        df[["league_id", "season_year"]].dropna().drop_duplicates().astype(int).values.tolist()
    )
    league_seasons_tuples = [(int(x[0]), int(x[1])) for x in league_seasons]

    # Targets to predict will be discovered per-league from training data
    target_cols = []

    # Drop columns not used as features (leakage control)
    drop_cols = [
        "fixture_id",
        "league_id",
        "league_name",
        "season_year",
        "fixture_date",
        "home_team_id",
        "home_team_name",
        "away_team_id",
        "away_team_name",
        "status",
        "advice",
        "winner_team_id",
        "winner_name",
        "win_or_draw",
        "under_over_line",
        "goals_home_line",
        "goals_away_line",
        "goals_home",
        "goals_away",
        "halftime_home",
        "halftime_away",
        "fulltime_home",
        "fulltime_away",
        "extratime_home",
        "extratime_away",
        "penalty_home",
        "penalty_away",
        "target_total_goals",
        "target_exact_score",
    ]

    # add suggestions
    suggestions = df.apply(suggest_market, axis=1)
    df["suggested_market"] = suggestions.apply(lambda x: x.get("market"))
    df["suggested_reason"] = suggestions.apply(lambda x: x.get("reason"))
    df["suggested_notes"] = suggestions.apply(lambda x: x.get("notes"))

    # model predictions (aggregate) per league
    model_summary = []
    for league_id in df["league_id"].dropna().unique():
        league_id_int = int(league_id)
        league_mask = df["league_id"] == league_id_int
        pred_df = df[league_mask].copy()

        league_seasons_l = [ls for ls in league_seasons_tuples if ls[0] == league_id_int]
        train_df = build_training_dataset(league_seasons_l)
        if train_df.empty:
            continue

        # Dynamic Training triggered by daily runner
        try:
            logger.info(f"Triggering dynamic training for League {league_id_int}...")
            # We train/save models using the production methodology
            results = train_and_save_all(league_id_int, last_n_seasons=3)
            for r in results:
                upload_and_register(r["model_path"], r["file_size"], r["target"], r)
                
            model_summary.extend([r["target"] for r in results])
        except Exception as e:
            logger.warning(f"Failed to dynamically train models for league {league_id_int}: {e}")
            continue

    if model_summary:
        df["suggested_confidence"] = df.get("target_over_2_5_consensus", 0)
    else:
        df["suggested_confidence"] = ""

    # Build ordered market list per match
    ordered_markets = []
    for _, row in df.iterrows():
        ranked = build_ranked_markets(row)
        ordered_markets.append(ranked)
    df["ordered_markets"] = ordered_markets

    Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)
    report_path = Path(REPORT_DIR) / f"{target_date.isoformat()}_report.md"
    write_report(target_date, df, coverage, str(report_path), include_matches=include_matches)
    return str(report_path)


if __name__ == "__main__":
    out = run_daily_report()
    print(f"Report saved to {out}")
