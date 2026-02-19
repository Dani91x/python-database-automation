"""
Production model training: ensemble + temporal split + feature selection.

Trains a stacking ensemble (RF + GB + LogReg + meta-learner) per league
using chronological train/val split with purge gap. Applies correlation
filtering and mutual-information feature selection. Uploads models and
metrics to Supabase.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pickle
import gzip
import warnings
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from db_client import get_supabase_client
from ai_engine.db_adapter import fetch_seasons_for_league
from ai_engine.training_dataset import build_training_dataset
from ai_engine.preprocessing.temporal_split import temporal_train_val_split
from ai_engine.preprocessing.selection import apply_feature_selection
from ai_engine.ensemble_trainer import build_ensemble, EnsemblePayload


MODEL_NAME = "ensemble_v2"
FEATURES_VERSION = "v2"
TARGETS_VERSION = "v1"
MAX_UPLOAD_MB = 45


def _ensure_bucket(bucket: str) -> None:
    sb = get_supabase_client()
    try:
        sb.storage.create_bucket(bucket)
    except Exception:
        pass


def _build_features(
    df: pd.DataFrame, target: str, drop_cols: list[str]
) -> tuple[pd.DataFrame, pd.Series, list[str], dict]:
    """Extract numeric features, target, columns list, and medians."""
    df = df.dropna(subset=[target]).copy()
    y = df[target]
    X = df.drop(columns=drop_cols + [target], errors="ignore")
    X = X.select_dtypes(include=["number", "bool"]).copy()
    medians = X.median(numeric_only=True).to_dict()
    X = X.fillna(medians)
    return X, y, list(X.columns), medians


def _compute_time_weights(fixture_dates: pd.Series, half_life_days: int = 365) -> np.ndarray:
    """Exponential decay weights: recent matches have more influence."""
    dates = pd.to_datetime(fixture_dates, errors="coerce")
    max_date = dates.max()
    if pd.isna(max_date):
        return np.ones(len(dates), dtype=float)
    age_days = (max_date - dates).dt.days.clip(lower=0).fillna(0).astype(float)
    decay = 0.5 ** (age_days / float(half_life_days))
    return np.clip(decay.to_numpy(), 0.2, 1.0)


def _brier_score(y_true: np.ndarray, proba: np.ndarray, classes: np.ndarray) -> float:
    class_to_idx = {c: i for i, c in enumerate(classes)}
    y_onehot = np.zeros_like(proba)
    for i, y in enumerate(y_true):
        if y in class_to_idx:
            y_onehot[i, class_to_idx[y]] = 1
    return float(np.mean(np.sum((proba - y_onehot) ** 2, axis=1)))


def _ece_score(y_true: np.ndarray, proba: np.ndarray, classes: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error: weighted average of |accuracy - confidence| per bin."""
    class_to_idx = {c: i for i, c in enumerate(classes)}
    confidences = np.max(proba, axis=1)
    predictions = np.array([classes[i] for i in np.argmax(proba, axis=1)])
    accuracies = (predictions == y_true).astype(float)
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (confidences > bin_boundaries[i]) & (confidences <= bin_boundaries[i + 1])
        if mask.sum() == 0:
            continue
        bin_acc = accuracies[mask].mean()
        bin_conf = confidences[mask].mean()
        ece += mask.sum() * abs(bin_acc - bin_conf)
    return float(ece / len(y_true)) if len(y_true) > 0 else 0.0


def train_and_save_all(league_id: int, last_n_seasons: int = 3) -> list[dict]:
    """
    Train ensemble models for all targets in a league.

    Key improvements over v1:
    1. Temporal train/val split (no data leakage)
    2. Feature selection (correlation + mutual information)
    3. Stacking ensemble (RF + GB + LogReg + meta-learner)
    4. Time-weighted training (recent matches count more)
    """
    seasons = fetch_seasons_for_league(league_id)
    seasons = seasons[-last_n_seasons:] if len(seasons) > last_n_seasons else seasons
    league_seasons = [(league_id, s) for s in seasons]
    train_df = build_training_dataset(league_seasons)
    if train_df.empty:
        raise RuntimeError(f"No training data for league {league_id}.")

    target_cols = [c for c in train_df.columns if c.startswith("target_")]

    drop_cols = [
        "fixture_id", "league_id", "league_name", "season_year", "fixture_date",
        "home_team_id", "home_team_name", "away_team_id", "away_team_name",
        "status", "advice", "winner_team_id", "winner_name",
        "win_or_draw", "under_over_line", "goals_home_line", "goals_away_line",
        "goals_home", "goals_away", "halftime_home", "halftime_away",
        "fulltime_home", "fulltime_away", "extratime_home", "extratime_away",
        "penalty_home", "penalty_away", "target_total_goals", "target_exact_score",
    ]
    # Drop any target columns to avoid leakage across targets
    drop_cols += [c for c in train_df.columns if c.startswith("target_")]
    # Drop raw per-fixture ids from joined tables (leakage / non-predictive)
    drop_cols += [c for c in train_df.columns if c.endswith("_fixture_id") or c.endswith("_team_id")]
    drop_cols += [c for c in train_df.columns if c.startswith("home_events_") or c.startswith("away_events_")]
    drop_cols += [c for c in train_df.columns if c.startswith("home_stats_") or c.startswith("away_stats_")]
    drop_cols += [c for c in train_df.columns if c.startswith("home_players_") or c.startswith("away_players_")]

    results = []
    for target in target_cols:
        print(f"  [league {league_id}] Training target: {target}")
        X_df, y, feature_cols_all, medians = _build_features(train_df, target, drop_cols)
        if len(np.unique(y)) < 2:
            print(f"    Skipped {target}: only 1 class")
            continue
        _, counts_all = np.unique(y, return_counts=True)
        if int(counts_all.min()) < 2:
            print(f"    Skipped {target}: min class count < 2")
            continue

        # ── TEMPORAL SPLIT (anti-leakage) ──────────────────────────
        # Build a combined DataFrame with features + target + dates
        combined = X_df.copy()
        combined["__target__"] = y
        combined["fixture_date"] = train_df.loc[X_df.index, "fixture_date"]

        train_split, val_split = temporal_train_val_split(
            combined, val_ratio=0.20, purge_days=30, date_col="fixture_date"
        )

        if train_split.empty or val_split.empty:
            print(f"    Skipped {target}: insufficient data after temporal split")
            continue

        # Extract X/y directly from the split DataFrames (indices are reset)
        y_train = train_split["__target__"]
        y_val = val_split["__target__"]
        train_dates = train_split["fixture_date"]
        X_train_raw = train_split.drop(columns=["__target__", "fixture_date"], errors="ignore")
        X_val_raw = val_split.drop(columns=["__target__", "fixture_date"], errors="ignore")

        if len(np.unique(y_train)) < 2 or len(np.unique(y_val)) < 2:
            print(f"    Skipped {target}: insufficient class diversity after split")
            continue

        # ── FEATURE SELECTION ──────────────────────────────────────
        try:
            X_train_sel, X_val_sel, selected_cols = apply_feature_selection(
                X_train_raw, y_train, X_val_raw,
                correlation_threshold=0.95,
                mi_top_k=60,
            )
        except Exception as e:
            print(f"    Feature selection failed for {target}: {e}")
            X_train_sel = X_train_raw
            X_val_sel = X_val_raw
            selected_cols = list(X_train_raw.columns)

        # Update medians for selected features
        selected_medians = {c: medians.get(c, 0.0) for c in selected_cols}

        # ── TIME WEIGHTS ───────────────────────────────────────────
        weights_train = _compute_time_weights(train_dates)

        # ── ENSEMBLE TRAINING ─────────────────────────────────────
        try:
            payload = build_ensemble(
                X_train_sel, y_train,
                X_val_sel, y_val,
                sample_weights=weights_train,
                feature_cols=selected_cols,
                feature_medians=selected_medians,
            )
        except Exception as e:
            print(f"    Ensemble training failed for {target}: {e}")
            continue

        # ── COMPUTE CALIBRATION METRICS ON VALIDATION ──────────────
        calibration_metrics = {}
        try:
            from ai_engine.ensemble_trainer import predict_ensemble
            X_val_np = X_val_sel.to_numpy().astype(float)
            X_val_scaled = payload.scaler.transform(X_val_np) if payload.scaler else X_val_np
            classes = np.array(payload.class_labels)
            # Get ensemble probabilities for entire validation set
            base_probas_list = []
            for name, model in payload.base_models:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    proba = model.predict_proba(X_val_scaled)
                model_classes = [str(c) for c in model.classes_]
                aligned = np.zeros((X_val_scaled.shape[0], len(classes)))
                for ci, c in enumerate(classes):
                    if c in model_classes:
                        idx_c = model_classes.index(c)
                        aligned[:, ci] = proba[:, idx_c]
                base_probas_list.append(aligned)
            if payload.meta_model is not None:
                meta_input = np.hstack(base_probas_list)
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    ensemble_proba = payload.meta_model.predict_proba(meta_input)
            else:
                total_w = sum(payload.base_weights.values()) or 1.0
                ensemble_proba = np.zeros_like(base_probas_list[0])
                for (name, _), bp in zip(payload.base_models, base_probas_list):
                    w = payload.base_weights.get(name, 1.0) / total_w
                    ensemble_proba += w * bp
            y_val_str = np.array([str(v) for v in y_val.to_numpy()])
            brier = _brier_score(y_val_str, ensemble_proba, classes)
            ece = _ece_score(y_val_str, ensemble_proba, classes)
            calibration_metrics = {"brier": round(brier, 4), "ece": round(ece, 4)}
        except Exception as e:
            print(f"    Calibration metrics failed for {target}: {e}")
            calibration_metrics = {"brier": None, "ece": None}

        # ── SAVE MODEL ────────────────────────────────────────────
        out_dir = os.path.join("Ai Engine", "models_cache", f"league_{league_id}")
        os.makedirs(out_dir, exist_ok=True)
        model_path = os.path.join(out_dir, f"{MODEL_NAME}_{target}.pkl.gz")

        save_payload = {
            "model_type": "ensemble_v2",
            "base_models": payload.base_models,
            "meta_model": payload.meta_model,
            "scaler": payload.scaler,
            "features": payload.feature_cols,
            "feature_medians": payload.feature_medians,
            "class_labels": payload.class_labels,
            "base_weights": payload.base_weights,
            "calibration_metrics": calibration_metrics,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }

        with gzip.open(model_path, "wb") as f:
            pickle.dump(save_payload, f, protocol=pickle.HIGHEST_PROTOCOL)

        size = os.path.getsize(model_path)
        if size > MAX_UPLOAD_MB * 1024 * 1024:
            print(f"    {target}: model too large ({size / 1024 / 1024:.1f} MB), skipping upload")
            continue

        metrics = payload.metrics
        results.append({
            "target": target,
            "model_path": model_path,
            "file_size": size,
            "accuracy": metrics.get("ensemble_accuracy", metrics.get("rf_accuracy", 0.0)),
            "logloss": metrics.get("ensemble_logloss", metrics.get("rf_logloss", 0.0)),
            "brier": calibration_metrics.get("brier", 0.0),
            "ece": calibration_metrics.get("ece", 0.0),
            "feature_count": len(selected_cols),
            "train_rows": int(len(y_train)),
            "val_rows": int(len(y_val)),
            "trained_range": f"{min(seasons)}-{max(seasons)}" if seasons else None,
            "league_id": league_id,
            "model_type": MODEL_NAME,
            "base_weights": payload.base_weights,
            "per_model_metrics": {
                k: v for k, v in metrics.items()
                if k.startswith(("rf_", "gb_", "logreg_"))
            },
        })
        print(f"    {target}: acc={metrics.get('ensemble_accuracy', 'N/A')}, "
              f"ll={metrics.get('ensemble_logloss', 'N/A')}, "
              f"brier={calibration_metrics.get('brier', 'N/A')}, "
              f"ece={calibration_metrics.get('ece', 'N/A')}, "
              f"features={len(selected_cols)}")

    return results


def upload_and_register(model_path: str, file_size: int, target: str, metrics: dict) -> None:
    """Upload model to Supabase storage and register in ai_model_registry."""
    sb = get_supabase_client()
    bucket = "ai-models"
    _ensure_bucket(bucket)

    league_id = metrics.get("league_id")
    storage_path = f"league_{league_id}/{MODEL_NAME}_{target}.pkl.gz"
    with open(model_path, "rb") as f:
        sb.storage.from_(bucket).upload(
            storage_path, f, {"content-type": "application/octet-stream", "upsert": "true"}
        )

    sb.table("ai_model_registry").upsert(
        {
            "league_id": league_id,
            "season_year": None,
            "target": target,
            "model_name": MODEL_NAME,
            "storage_bucket": bucket,
            "storage_path": storage_path,
            "file_size_bytes": file_size,
            "features_version": FEATURES_VERSION,
            "targets_version": TARGETS_VERSION,
            "train_rows": metrics.get("train_rows"),
            "feature_count": metrics.get("feature_count"),
            "accuracy": metrics.get("accuracy"),
            "logloss": metrics.get("logloss"),
            "brier": metrics.get("brier"),
            "trained_range": metrics.get("trained_range"),
            "notes": f"League {league_id} ensemble_v2 ({metrics.get('model_type', MODEL_NAME)})",
        }
    ).execute()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python seriea_model_export.py <league_id> [last_n_seasons]")
    league_id = int(sys.argv[1])
    last_n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    print(f"Training ensemble models for league {league_id}...")
    results = train_and_save_all(league_id, last_n_seasons=last_n)
    print(f"\nTraining complete. {len(results)} models trained.")
    for r in results:
        upload_and_register(r["model_path"], r["file_size"], r["target"], r)
        print(f"  Uploaded {r['target']} ({r['file_size']} bytes, "
              f"acc={r.get('accuracy', 'N/A')}, features={r.get('feature_count', '?')})")


if __name__ == "__main__":
    main()
