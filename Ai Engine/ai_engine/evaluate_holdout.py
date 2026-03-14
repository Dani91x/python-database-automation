"""
Holdout evaluation with temporal split.

Uses proper chronological holdout (not random) to produce honest
metrics: accuracy, logloss, brier, ECE.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.preprocessing import StandardScaler

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from ai_engine.db_adapter import fetch_seasons_for_league
from ai_engine.training_dataset import build_training_dataset
from ai_engine.preprocessing.temporal_split import temporal_train_val_split
from ai_engine.preprocessing.selection import apply_feature_selection


def _brier_score(y_true: np.ndarray, proba: np.ndarray, classes: np.ndarray) -> float:
    class_to_idx = {c: i for i, c in enumerate(classes)}
    y_onehot = np.zeros_like(proba)
    for i, y in enumerate(y_true):
        if y in class_to_idx:
            y_onehot[i, class_to_idx[y]] = 1
    return float(np.mean(np.sum((proba - y_onehot) ** 2, axis=1)))


def _ece_score(y_true: np.ndarray, proba: np.ndarray, classes: np.ndarray, bins: int = 10) -> float:
    preds = np.argmax(proba, axis=1)
    probs = np.max(proba, axis=1)
    correct = (classes[preds] == y_true).astype(float)
    bin_edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for i in range(bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (probs > lo) & (probs <= hi)
        if not np.any(mask):
            continue
        acc = correct[mask].mean()
        conf = probs[mask].mean()
        ece += (mask.mean()) * abs(acc - conf)
    return float(ece)


def evaluate_holdout(league_id: int, last_n_seasons: int = 3, holdout_ratio: float = 0.20) -> str:
    """
    Evaluate models using proper temporal holdout.

    Changes from v1:
    - Always uses temporal split (never random)
    - 30-day purge gap between train/val
    - Feature selection applied
    - Multiple model comparison (RF, GB, LogReg)
    """
    seasons = fetch_seasons_for_league(league_id)
    seasons = seasons[-last_n_seasons:] if len(seasons) > last_n_seasons else seasons
    league_seasons = [(league_id, s) for s in seasons]
    df = build_training_dataset(league_seasons)
    if df.empty:
        raise RuntimeError(f"No training data for league {league_id}.")

    target_cols = [c for c in df.columns if c.startswith("target_")]

    drop_cols = [
        "fixture_id", "league_id", "league_name", "season_year", "fixture_date",
        "home_team_id", "home_team_name", "away_team_id", "away_team_name",
        "status", "advice", "winner_team_id", "winner_name",
        "win_or_draw", "under_over_line", "goals_home_line", "goals_away_line",
        "goals_home", "goals_away", "halftime_home", "halftime_away",
        "fulltime_home", "fulltime_away", "extratime_home", "extratime_away",
        "penalty_home", "penalty_away", "target_total_goals", "target_exact_score",
    ]
    drop_cols += [c for c in df.columns if c.startswith("target_")]
    drop_cols += [c for c in df.columns if c.endswith("_fixture_id") or c.endswith("_team_id")]
    drop_cols += [c for c in df.columns if c.startswith("home_events_") or c.startswith("away_events_")]
    drop_cols += [c for c in df.columns if c.startswith("home_stats_") or c.startswith("away_stats_")]
    drop_cols += [c for c in df.columns if c.startswith("home_players_") or c.startswith("away_players_")]

    report_dir = os.path.join("Ai Engine", "reports")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"eval_holdout_league_{league_id}.md")

    lines = []
    lines.append(f"# Holdout Evaluation — League {league_id}")
    lines.append("")
    lines.append(f"Generated at: {datetime.now(timezone.utc).isoformat()} UTC")
    lines.append(f"Seasons: {seasons}")
    lines.append(f"Split: temporal {1-holdout_ratio:.0%}/{holdout_ratio:.0%} with 30-day purge gap")
    lines.append("")

    summary_rows = []

    for target in target_cols:
        sub = df.dropna(subset=[target]).copy()
        if sub.empty or len(np.unique(sub[target])) < 2:
            continue

        # Prepare features
        y_series = sub[target]
        X_all = sub.drop(columns=drop_cols + [target], errors="ignore")
        X_all = X_all.select_dtypes(include=["number", "bool"]).copy()
        medians = X_all.median(numeric_only=True).to_dict()
        X_all = X_all.fillna(medians)

        # Temporal split with purge
        date_df = X_all.copy()
        date_df["fixture_date"] = sub["fixture_date"]
        train_split, val_split = temporal_train_val_split(
            date_df, val_ratio=holdout_ratio, purge_days=30, date_col="fixture_date"
        )

        if train_split.empty or val_split.empty or len(val_split) < 5:
            continue

        train_idx = train_split.index
        val_idx = val_split.index

        X_train = X_all.loc[train_idx].drop(columns=["fixture_date"], errors="ignore")
        X_val = X_all.loc[val_idx].drop(columns=["fixture_date"], errors="ignore")
        y_train = y_series.loc[train_idx].to_numpy()
        y_val = y_series.loc[val_idx].to_numpy()

        if len(np.unique(y_train)) < 2:
            continue

        # Feature selection
        try:
            X_tr_sel, X_v_sel, sel_cols = apply_feature_selection(
                X_train, pd.Series(y_train, index=X_train.index), X_val,
                correlation_threshold=0.95, mi_top_k=60,
            )
        except Exception:
            X_tr_sel, X_v_sel, sel_cols = X_train, X_val, list(X_train.columns)

        # Mirror ensemble_trainer.py: class_weight only when genuinely imbalanced
        _class_counts = np.unique(y_train, return_counts=True)[1]
        _imbalance_ratio = float(_class_counts.min() / _class_counts.max()) if len(_class_counts) > 1 else 1.0
        _use_balanced = _imbalance_ratio < 0.35
        _rf_class_weight = "balanced_subsample" if _use_balanced else None

        # Train and evaluate multiple models
        models_to_eval = {
            "RF": RandomForestClassifier(n_estimators=200, random_state=0, n_jobs=-1,
                                         class_weight=_rf_class_weight, max_depth=10),
            "GB": GradientBoostingClassifier(n_estimators=200, learning_rate=0.05,
                                             max_depth=5, random_state=0),
        }

        target_lines = [
            f"## {target}",
            f"- holdout rows: {len(y_val)}",
            f"- features: {len(sel_cols)}",
            f"- imbalance_ratio: {_imbalance_ratio:.3f} ({'balanced' if _use_balanced else 'no class_weight'})",
        ]

        for model_name, model in models_to_eval.items():
            try:
                _, counts = np.unique(y_train, return_counts=True)
                min_count = int(counts.min())

                if model_name == "GB":
                    model.fit(X_tr_sel.to_numpy(), y_train)
                else:
                    model.fit(X_tr_sel.to_numpy(), y_train)

                # Calibrate
                if min_count >= 3:
                    try:
                        cal = CalibratedClassifierCV(model, method="sigmoid", cv=3)
                        cal.fit(X_tr_sel.to_numpy(), y_train)
                        model = cal
                    except Exception:
                        pass

                proba = model.predict_proba(X_v_sel.to_numpy())
                classes = getattr(model, "classes_", np.unique(y_val))

                missing = set(np.unique(y_val)) - set(classes)
                if missing:
                    target_lines.append(f"- {model_name}: skipped (unseen labels)")
                    continue

                acc = accuracy_score(y_val, model.predict(X_v_sel.to_numpy()))
                ll = log_loss(y_val, proba, labels=classes)
                brier = _brier_score(y_val, proba, classes)
                ece = _ece_score(y_val, proba, classes)

                target_lines.append(
                    f"- {model_name}: acc={acc:.3f}, logloss={ll:.3f}, "
                    f"brier={brier:.3f}, ECE={ece:.3f}"
                )
                summary_rows.append({
                    "target": target, "model": model_name,
                    "acc": acc, "ll": ll, "brier": brier, "ece": ece,
                })

                # Feature importance for RF
                if model_name == "RF":
                    importances = []
                    if hasattr(model, "feature_importances_"):
                        importances = list(zip(sel_cols, model.feature_importances_))
                    elif hasattr(model, "calibrated_classifiers_"):
                        try:
                            est = model.calibrated_classifiers_[0].estimator
                            if hasattr(est, "feature_importances_"):
                                importances = list(zip(sel_cols, est.feature_importances_))
                        except Exception:
                            pass
                    top_imp = sorted(importances, key=lambda x: x[1], reverse=True)[:5]
                    if top_imp:
                        target_lines.append("  - top features:")
                        for feat, score in top_imp:
                            target_lines.append(f"    - {feat}={score:.4f}")

            except Exception as e:
                target_lines.append(f"- {model_name}: error ({e})")

        target_lines.append("")
        lines.extend(target_lines)

    # Summary table
    if summary_rows:
        lines.insert(6, "## Summary (best per target)")
        lines.insert(7, "")
        lines.insert(8, "| Target | Best Model | Accuracy | LogLoss | Brier | ECE |")
        lines.insert(9, "|--------|-----------|----------|---------|-------|-----|")
        # Best model per target by logloss
        summary_df = pd.DataFrame(summary_rows)
        for target in summary_df["target"].unique():
            t_df = summary_df[summary_df["target"] == target]
            best = t_df.loc[t_df["ll"].idxmin()]
            lines.insert(10, f"| {target} | {best['model']} | {best['acc']:.3f} | {best['ll']:.3f} | {best['brier']:.3f} | {best['ece']:.3f} |")
        lines.insert(10 + len(summary_df["target"].unique()), "")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python evaluate_holdout.py <league_id> [last_n_seasons]")
    league_id = int(sys.argv[1])
    last_n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    out = evaluate_holdout(league_id, last_n)
    print(f"Report: {out}")
