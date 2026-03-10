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

    # add suggestions
    suggestions = df.apply(suggest_market, axis=1)
    df["suggested_market"] = suggestions.apply(lambda x: x.get("market"))
    df["suggested_reason"] = suggestions.apply(lambda x: x.get("reason"))
    df["suggested_notes"] = suggestions.apply(lambda x: x.get("notes"))

    # Daily report uses EXISTING cached models only.
    # Full retraining is handled by the dedicated retrain_all_leagues.py script
    # (or by running it from aggiorna_modelli.bat), not by the daily runner.
    # This keeps aggiorna_report.bat fast (seconds, not minutes/hours).
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
