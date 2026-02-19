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

        # Drop post-match features for training (prevent leakage)
        # Must be computed here after train_df is available
        league_drop_cols = list(drop_cols)
        league_drop_cols += [c for c in train_df.columns if c.startswith("home_events_") or c.startswith("away_events_")]
        league_drop_cols += [c for c in train_df.columns if c.startswith("home_stats_") or c.startswith("away_stats_")]
        league_drop_cols += [c for c in train_df.columns if c.startswith("home_players_") or c.startswith("away_players_")]

        if not target_cols:
            target_cols = [c for c in train_df.columns if c.startswith("target_")]

        for target in target_cols:
            results = train_and_predict(train_df, pred_df, target, league_drop_cols)
            if not results:
                continue

            # aggregate per fixture across models
            for idx, row_idx in enumerate(pred_df.index):
                prob_maps = [r.pred_probas[idx] for r in results]
                pred_labels = [r.pred_labels[idx] for r in results]
                weights = [r.weight or 1.0 for r in results]
                agg = aggregate_model_outputs(prob_maps, weights)
                df.loc[row_idx, f"{target}_ensemble"] = max(agg, key=agg.get) if agg else None
                df.loc[row_idx, f"{target}_entropy"] = entropy(agg) if agg else None
                df.loc[row_idx, f"{target}_consensus"] = consensus(pred_labels)

            model_summary.append(target)

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
