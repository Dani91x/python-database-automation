"""
Walk-forward backtesting with real odds P&L.

Divides history into temporal folds, trains on past data only,
predicts next window, applies value-betting rules using real
market odds from the `match_odds` table, and tracks cumulative
ROI, yield, max drawdown, Sharpe ratio, Brier score, and ECE.
"""
from __future__ import annotations

import os
import sys
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from ai_engine.db_adapter import fetch_seasons_for_league, fetch_related_by_fixture_ids
from ai_engine.training_dataset import build_training_dataset
from ai_engine.preprocessing.temporal_split import walk_forward_splits
from ai_engine.value_betting import (
    expected_value,
    kelly_criterion,
    implied_probability,
    MIN_EDGE,
    MIN_PROB,
    KELLY_FRACTION,
    MAX_KELLY,
    DEFAULT_BANKROLL,
    BETFAIR_COMMISSION,
)


# Mapping from target names to odds keys built as "{market_name}_{label}".lower()
TARGET_ODDS_MAP = {
    "target_1x2": {"H": "match_winner_home", "D": "match_winner_draw", "A": "match_winner_away"},
    "target_btts": {"True": "both_teams_score_yes", "False": "both_teams_score_no"},
    "target_over_0_5": {"True": "goals_over/under_over_0.5", "False": "goals_over/under_under_0.5"},
    "target_over_1_5": {"True": "goals_over/under_over_1.5", "False": "goals_over/under_under_1.5"},
    "target_over_2_5": {"True": "goals_over/under_over_2.5", "False": "goals_over/under_under_2.5"},
    "target_over_3_5": {"True": "goals_over/under_over_3.5", "False": "goals_over/under_under_3.5"},
    "target_over_4_5": {"True": "goals_over/under_over_4.5", "False": "goals_over/under_under_4.5"},
}


def _fetch_odds_by_fixture(fixture_ids: List[int]) -> Dict[int, Dict[str, float]]:
    """Fetch real odds from match_odds and return dict keyed by fixture_id."""
    if not fixture_ids:
        return {}
    rows = fetch_related_by_fixture_ids(
        "match_odds", fixture_ids,
        columns="fixture_id,bookmaker_name,market_name,label,odd_value",
    )
    odds_by_fid: Dict[int, Dict[str, float]] = {}
    for r in rows:
        fid = r.get("fixture_id")
        if fid is None:
            continue
        if fid not in odds_by_fid:
            odds_by_fid[fid] = {}
        market_name = str(r.get("market_name", "")).strip()
        label = str(r.get("label", "")).strip()
        odd_value = r.get("odd_value")
        if odd_value is None:
            continue
        try:
            odd_f = float(odd_value)
        except (ValueError, TypeError):
            continue
        # Map to standardized keys: "{market_name}_{label}" in lowercase
        key = f"{market_name}_{label}".lower().replace(" ", "_")
        # Store the best (first) odds we find
        if key not in odds_by_fid[fid]:
            odds_by_fid[fid][key] = odd_f
    return odds_by_fid


def _get_real_odds_for_target(
    fixture_id: int, target: str, predicted_class: str,
    odds_lookup: Dict[int, Dict[str, float]],
) -> Optional[float]:
    """Look up real decimal odds for a specific fixture/target/class."""
    fid_odds = odds_lookup.get(fixture_id, {})
    if not fid_odds:
        return None
    target_map = TARGET_ODDS_MAP.get(target)
    if target_map:
        col = target_map.get(str(predicted_class))
        if col and col in fid_odds:
            return fid_odds[col]
    # Fallback: try to find any matching odds
    for key, val in fid_odds.items():
        if target.replace("target_", "") in key and str(predicted_class).lower() in key:
            return val
    return None


def _brier_score_multiclass(y_true: np.ndarray, proba: np.ndarray, classes: list) -> float:
    """Compute Brier score for multiclass."""
    y_onehot = np.zeros_like(proba)
    for i, yt in enumerate(y_true):
        cls_str = str(yt)
        if cls_str in classes:
            y_onehot[i, classes.index(cls_str)] = 1
    return float(np.mean(np.sum((proba - y_onehot) ** 2, axis=1)))


def _prepare_xy(
    df: pd.DataFrame,
    target: str,
    drop_cols: List[str],
) -> Tuple[pd.DataFrame, pd.Series, Dict[str, float]]:
    """Prepare features and target, return (X, y, medians)."""
    sub = df.dropna(subset=[target]).copy()
    y = sub[target]
    X = sub.drop(columns=drop_cols + [target], errors="ignore")
    X = X.select_dtypes(include=["number", "bool"]).copy()
    medians = X.median(numeric_only=True).to_dict()
    X = X.fillna(medians)
    return X, y, medians


def _get_standard_drop_cols(df: pd.DataFrame) -> List[str]:
    """Standard columns to drop (same as seriea_model_export)."""
    drop = [
        "fixture_id", "league_id", "league_name", "season_year", "fixture_date",
        "home_team_id", "home_team_name", "away_team_id", "away_team_name",
        "status", "advice", "winner_team_id", "winner_name",
        "win_or_draw", "under_over_line", "goals_home_line", "goals_away_line",
        "goals_home", "goals_away", "halftime_home", "halftime_away",
        "fulltime_home", "fulltime_away", "extratime_home", "extratime_away",
        "penalty_home", "penalty_away", "target_total_goals", "target_exact_score",
    ]
    drop += [c for c in df.columns if c.startswith("target_")]
    drop += [c for c in df.columns if c.endswith("_fixture_id") or c.endswith("_team_id")]
    drop += [c for c in df.columns if c.startswith("home_events_") or c.startswith("away_events_")]
    drop += [c for c in df.columns if c.startswith("home_stats_") or c.startswith("away_stats_")]
    drop += [c for c in df.columns if c.startswith("home_players_") or c.startswith("away_players_")]
    return drop


def run_backtest(
    league_id: int,
    last_n_seasons: int = 3,
    n_folds: int = 3,
    targets: List[str] | None = None,
    bankroll: float = DEFAULT_BANKROLL,
    commission: float = BETFAIR_COMMISSION,
) -> Dict[str, Any]:
    """
    Run walk-forward backtest for a league.

    Returns summary dict with per-target and overall metrics.
    """
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import accuracy_score, log_loss

    seasons = fetch_seasons_for_league(league_id)
    seasons = seasons[-last_n_seasons:] if len(seasons) > last_n_seasons else seasons
    league_seasons = [(league_id, s) for s in seasons]

    df = build_training_dataset(league_seasons)
    if df.empty:
        return {"error": "No training data"}

    df["fixture_date"] = pd.to_datetime(df["fixture_date"], errors="coerce")
    df = df.dropna(subset=["fixture_date"]).sort_values("fixture_date").reset_index(drop=True)

    drop_cols = _get_standard_drop_cols(df)

    target_cols = targets or [c for c in df.columns if c.startswith("target_")]
    # Skip non-predictive targets
    skip_targets = {"target_total_goals", "target_exact_score", "target_ht_ft",
                    "target_corners_total", "target_sot_total",
                    "target_cards_total", "target_home_cards", "target_away_cards"}
    target_cols = [t for t in target_cols if t not in skip_targets]

    splits = walk_forward_splits(df, n_splits=n_folds, purge_days=30)
    if not splits:
        return {"error": "Not enough data for walk-forward splits"}

    # Prefetch ALL odds once to avoid repeated Supabase calls per fold/target
    all_fixture_ids = df["fixture_id"].dropna().astype(int).tolist() if "fixture_id" in df.columns else []
    print(f"Fetching real odds for {len(all_fixture_ids)} fixtures (this may take a moment)...")
    odds_lookup_all = _fetch_odds_by_fixture(all_fixture_ids)
    print(f"  Found odds for {len(odds_lookup_all)} fixtures")

    results_per_target: Dict[str, Dict[str, Any]] = {}
    all_bets: List[Dict[str, Any]] = []

    for target in target_cols:
        target_bets = []
        target_correct = 0
        target_total = 0
        fold_metrics = []

        for fold_idx, (train_idx, val_idx) in enumerate(splits):
            X, y, medians = _prepare_xy(df, target, drop_cols)
            if X.empty or len(np.unique(y)) < 2:
                continue

            # Ensure indices are valid
            valid_train = [i for i in train_idx if i in X.index]
            valid_val = [i for i in val_idx if i in X.index]
            if len(valid_train) < 20 or len(valid_val) < 5:
                continue

            X_train = X.loc[valid_train]
            X_val = X.loc[valid_val]
            y_train = y.loc[valid_train]
            y_val = y.loc[valid_val]

            if len(np.unique(y_train)) < 2:
                continue

            # Train simple RF (fast for backtest)
            n_classes = len(np.unique(y_train))
            n_est = 200 if n_classes <= 5 else 100
            clf = RandomForestClassifier(
                n_estimators=n_est, random_state=0, n_jobs=-1,
                class_weight="balanced_subsample", max_depth=10,
            )
            clf.fit(X_train, y_train)

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                proba = clf.predict_proba(X_val)
                preds = clf.predict(X_val)

            classes = [str(c) for c in clf.classes_]
            y_val_arr = y_val.to_numpy()

            acc = float((preds == y_val_arr).mean())
            try:
                ll = log_loss(y_val_arr, proba, labels=clf.classes_)
            except Exception:
                ll = float("nan")

            # Brier score
            brier = _brier_score_multiclass(y_val_arr, proba, classes)

            # Baseline: majority class accuracy
            from collections import Counter
            majority_class = Counter(str(v) for v in y_train.to_numpy()).most_common(1)[0][0]
            baseline_acc = float((np.array([str(v) for v in y_val_arr]) == majority_class).mean())

            fold_metrics.append({
                "fold": fold_idx,
                "accuracy": acc,
                "logloss": ll,
                "brier": round(brier, 4),
                "baseline_accuracy": round(baseline_acc, 4),
                "lift_vs_baseline": round(acc - baseline_acc, 4),
            })

            # Use prefetched real odds (no per-fold DB calls)
            odds_lookup_fold = odds_lookup_all

            for i in range(len(y_val_arr)):
                best_idx = int(np.argmax(proba[i]))
                best_class = classes[best_idx]
                best_prob = float(proba[i][best_idx])
                actual = str(y_val_arr[i])

                if best_prob > 0.52:
                    # Look up real odds for this fixture
                    fid = None
                    if "fixture_id" in df.columns:
                        fid_val = df.iloc[valid_val[i]]["fixture_id"] if i < len(valid_val) else None
                        fid = int(fid_val) if pd.notna(fid_val) else None

                    real_odds = _get_real_odds_for_target(
                        fid, target, best_class, odds_lookup_fold
                    ) if fid else None

                    if real_odds is None or real_odds < 1.01:
                        continue  # Skip if no real odds available

                    bookie_odds = real_odds
                    ev = expected_value(best_prob, bookie_odds)

                    if ev > MIN_EDGE and best_prob > MIN_PROB:
                        kelly = kelly_criterion(best_prob, bookie_odds, commission=commission)
                        stake = kelly * bankroll
                        won = best_class == actual
                        # Deduct Betfair commission from winning profit.
                        # Commission is applied to NET WINNINGS (not stake).
                        gross_win = stake * (bookie_odds - 1)
                        profit = gross_win * (1.0 - commission) if won else -stake

                        bet_record = {
                            "fold": fold_idx,
                            "target": target,
                            "predicted": best_class,
                            "actual": actual,
                            "prob": best_prob,
                            "odds": round(bookie_odds, 3),
                            "odds_source": "match_odds",
                            "ev": round(ev, 4),
                            "stake": round(stake, 2),
                            "won": won,
                            "profit": round(profit, 2),
                        }
                        target_bets.append(bet_record)
                        all_bets.append(bet_record)

                        if won:
                            target_correct += 1
                        target_total += 1

        # Summarise target
        if target_bets:
            profits = [b["profit"] for b in target_bets]
            stakes = [b["stake"] for b in target_bets]
            total_profit = sum(profits)
            total_staked = sum(stakes)
            roi = total_profit / total_staked if total_staked > 0 else 0.0
            win_rate = target_correct / target_total if target_total > 0 else 0.0

            # Max drawdown
            cumulative = np.cumsum(profits)
            peak = np.maximum.accumulate(cumulative)
            drawdowns = peak - cumulative
            max_dd = float(drawdowns.max()) if len(drawdowns) > 0 else 0.0

            # Sharpe (daily returns proxy)
            if len(profits) > 1:
                sharpe = float(np.mean(profits) / (np.std(profits) + 1e-8))
            else:
                sharpe = 0.0

            results_per_target[target] = {
                "n_bets": len(target_bets),
                "win_rate": round(win_rate, 4),
                "total_profit": round(total_profit, 2),
                "total_staked": round(total_staked, 2),
                "roi": round(roi, 4),
                "max_drawdown": round(max_dd, 2),
                "sharpe": round(sharpe, 4),
                "fold_metrics": fold_metrics,
            }

    # Overall summary
    if all_bets:
        all_profits = [b["profit"] for b in all_bets]
        all_stakes = [b["stake"] for b in all_bets]
        total_profit = sum(all_profits)
        total_staked = sum(all_stakes)
        overall_roi = total_profit / total_staked if total_staked > 0 else 0.0
        overall_win_rate = sum(1 for b in all_bets if b["won"]) / len(all_bets)

        cumulative = np.cumsum(all_profits)
        peak = np.maximum.accumulate(cumulative)
        drawdowns = peak - cumulative
        max_dd = float(drawdowns.max()) if len(drawdowns) > 0 else 0.0
        sharpe = float(np.mean(all_profits) / (np.std(all_profits) + 1e-8)) if len(all_profits) > 1 else 0.0
    else:
        total_profit = 0
        total_staked = 0
        overall_roi = 0
        overall_win_rate = 0
        max_dd = 0
        sharpe = 0

    return {
        "league_id": league_id,
        "seasons": seasons,
        "n_folds": n_folds,
        "overall": {
            "n_bets": len(all_bets),
            "win_rate": round(overall_win_rate, 4),
            "total_profit": round(total_profit, 2),
            "total_staked": round(total_staked, 2),
            "roi": round(overall_roi, 4),
            "max_drawdown": round(max_dd, 2),
            "sharpe": round(sharpe, 4),
        },
        "per_target": results_per_target,
    }


def generate_backtest_report(league_id: int, **kwargs) -> str:
    """Run backtest and save report as markdown."""
    result = run_backtest(league_id, **kwargs)

    # Determine absolute path to "reports" folder (sibling of "ai_engine" package)
    script_dir = os.path.dirname(os.path.abspath(__file__))  # .../ai_engine
    project_root = os.path.dirname(script_dir)  # .../Ai Engine
    report_dir = os.path.join(project_root, "reports")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"backtest_league_{league_id}.md")

    lines = []
    lines.append(f"# Backtest Report — League {league_id}")
    lines.append("")
    lines.append(f"Generated at: {datetime.now(timezone.utc).isoformat()} UTC")
    lines.append(f"Seasons: {result.get('seasons', [])}")
    lines.append(f"Folds: {result.get('n_folds', 0)}")
    lines.append("")

    overall = result.get("overall", {})
    lines.append("## Overall Results")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Bets | {overall.get('n_bets', 0)} |")
    lines.append(f"| Win Rate | {overall.get('win_rate', 0):.1%} |")
    lines.append(f"| ROI | {overall.get('roi', 0):.1%} |")
    lines.append(f"| Total Profit | {overall.get('total_profit', 0):.2f} |")
    lines.append(f"| Total Staked | {overall.get('total_staked', 0):.2f} |")
    lines.append(f"| Max Drawdown | {overall.get('max_drawdown', 0):.2f} |")
    lines.append(f"| Sharpe Ratio | {overall.get('sharpe', 0):.3f} |")
    lines.append("")

    per_target = result.get("per_target", {})
    if per_target:
        lines.append("## Per-Target Results")
        lines.append("")
        lines.append("| Target | Bets | Win Rate | ROI | Profit | Sharpe | Avg Brier | Baseline Acc | Lift |")
        lines.append("|--------|------|----------|-----|--------|--------|-----------|-------------|------|")
        for target, data in sorted(per_target.items(), key=lambda x: x[1].get("roi", 0), reverse=True):
            fm = data.get("fold_metrics", [])
            avg_brier = np.mean([f.get("brier", 0) for f in fm]) if fm else 0
            avg_baseline = np.mean([f.get("baseline_accuracy", 0) for f in fm]) if fm else 0
            avg_lift = np.mean([f.get("lift_vs_baseline", 0) for f in fm]) if fm else 0
            lines.append(
                f"| {target} "
                f"| {data.get('n_bets', 0)} "
                f"| {data.get('win_rate', 0):.1%} "
                f"| {data.get('roi', 0):.1%} "
                f"| {data.get('total_profit', 0):.2f} "
                f"| {data.get('sharpe', 0):.3f} "
                f"| {avg_brier:.3f} "
                f"| {avg_baseline:.1%} "
                f"| {avg_lift:+.1%} |"
            )
        lines.append("")

    # Interpretation
    lines.append("## Interpretation")
    lines.append("")
    lines.append("> [!NOTE]")
    lines.append("> Odds source: **real market odds** from `match_odds` table.")
    lines.append("> Fixtures without odds data are excluded from P&L calculations.")
    lines.append("")
    if overall.get("roi", 0) > 0:
        lines.append("> [!TIP]")
        lines.append(f"> ROI positivo ({overall.get('roi', 0):.1%}). Il modello mostra edge.")
    else:
        lines.append("> [!WARNING]")
        lines.append(f"> ROI negativo ({overall.get('roi', 0):.1%}). Necessario ottimizzare.")
    lines.append("")
    if overall.get("sharpe", 0) > 1.0:
        lines.append("Sharpe > 1.0 indica buon risk/reward.")
    elif overall.get("sharpe", 0) > 0.5:
        lines.append("Sharpe tra 0.5 e 1.0: accettabile ma migliorabile.")
    else:
        lines.append("Sharpe < 0.5: rischio elevato rispetto al rendimento.")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python backtest.py <league_id> [last_n_seasons] [n_folds]")
    lid = int(sys.argv[1])
    last_n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    folds = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    out = generate_backtest_report(lid, last_n_seasons=last_n, n_folds=folds)
    print(f"Report saved: {out}")
