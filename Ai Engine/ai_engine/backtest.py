"""
Walk-forward backtesting with simulated P&L.

Divides history into temporal folds, trains on past data only,
predicts next window, applies value-betting rules, and tracks
cumulative ROI, yield, max drawdown, and Sharpe ratio.
"""
from __future__ import annotations

import os
import sys
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from ai_engine.db_adapter import fetch_seasons_for_league
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
)


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

            fold_metrics.append({"fold": fold_idx, "accuracy": acc, "logloss": ll})

            # Simulate bets per validation sample
            #
            # Simulate bookmaker odds realistically:
            # - The bookmaker sets odds based on true prob (unknown to model)
            # - We use the class base-rate in the validation set as a proxy
            # - Add overround (margin) so bookmaker pays less than fair
            # - If model prob > bookie implied prob → model has edge → positive EV
            #
            class_rates = {}
            for c in classes:
                class_rates[c] = max(0.05, float((y_val_arr == c).mean()) if str(c) in [str(v) for v in y_val_arr] else 0.1)

            rng = np.random.RandomState(fold_idx)
            for i in range(len(y_val_arr)):
                best_idx = int(np.argmax(proba[i]))
                best_class = classes[best_idx]
                best_prob = float(proba[i][best_idx])
                actual = str(y_val_arr[i])

                if best_prob > 0.52:
                    # Bookmaker odds: based on true rate + overround
                    true_rate = class_rates.get(best_class, 0.33)
                    # Add noise to simulate imperfect bookmaker pricing
                    noise = rng.uniform(-0.05, 0.05)
                    bookie_implied = max(0.10, true_rate + noise)
                    overround = 1.05  # 5% margin
                    bookie_odds = (1.0 / bookie_implied) / overround

                    if bookie_odds < 1.01:
                        continue

                    ev = expected_value(best_prob, bookie_odds)

                    if ev > MIN_EDGE and best_prob > MIN_PROB:
                        kelly = kelly_criterion(best_prob, bookie_odds)
                        stake = kelly * bankroll
                        won = best_class == actual
                        profit = stake * (bookie_odds - 1) if won else -stake

                        bet_record = {
                            "fold": fold_idx,
                            "target": target,
                            "predicted": best_class,
                            "actual": actual,
                            "prob": best_prob,
                            "odds": round(bookie_odds, 3),
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

    report_dir = os.path.join("Ai Engine", "reports")
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
        lines.append("| Target | Bets | Win Rate | ROI | Profit | Sharpe |")
        lines.append("|--------|------|----------|-----|--------|--------|")
        for target, data in sorted(per_target.items(), key=lambda x: x[1].get("roi", 0), reverse=True):
            lines.append(
                f"| {target} "
                f"| {data.get('n_bets', 0)} "
                f"| {data.get('win_rate', 0):.1%} "
                f"| {data.get('roi', 0):.1%} "
                f"| {data.get('total_profit', 0):.2f} "
                f"| {data.get('sharpe', 0):.3f} |"
            )
        lines.append("")

    # Interpretation
    lines.append("## Interpretation")
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
