from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pickle
import gzip
import warnings
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import train_test_split

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from db_client import get_supabase_client
from ai_engine.db_adapter import fetch_seasons_for_league
from ai_engine.training_dataset import build_training_dataset


LEAGUE_ID = 135
MODEL_NAME = "rf_calibrated"
FEATURES_VERSION = "v1"
TARGETS_VERSION = "v1"
MAX_UPLOAD_MB = 45


def _ensure_bucket(bucket: str) -> None:
    sb = get_supabase_client()
    try:
        sb.storage.create_bucket(bucket)
    except Exception:
        # bucket probably exists
        pass


def _build_features(
    df: pd.DataFrame, target: str, drop_cols: list[str]
) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    df = df.dropna(subset=[target]).copy()
    y = df[target]
    X = df.drop(columns=drop_cols + [target], errors="ignore")
    X = X.select_dtypes(include=["number", "bool"]).copy()
    X = X.fillna(X.median(numeric_only=True))
    return X, y.to_numpy(), list(X.columns)


def _brier_score(y_true: np.ndarray, proba: np.ndarray, classes: np.ndarray) -> float:
    # Multi-class Brier: mean sum (p_i - y_i)^2
    class_to_idx = {c: i for i, c in enumerate(classes)}
    y_onehot = np.zeros_like(proba)
    for i, y in enumerate(y_true):
        if y in class_to_idx:
            y_onehot[i, class_to_idx[y]] = 1
    return float(np.mean(np.sum((proba - y_onehot) ** 2, axis=1)))


def train_and_save_all() -> list[dict]:
    seasons = fetch_seasons_for_league(LEAGUE_ID)
    seasons = seasons[-3:] if len(seasons) > 3 else seasons
    league_seasons = [(LEAGUE_ID, s) for s in seasons]
    train_df = build_training_dataset(league_seasons)
    if train_df.empty:
        raise RuntimeError("No training data for league 135.")

    target_cols = [c for c in train_df.columns if c.startswith("target_")]

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
    drop_cols += [c for c in train_df.columns if c.startswith("home_events_") or c.startswith("away_events_")]
    drop_cols += [c for c in train_df.columns if c.startswith("home_stats_") or c.startswith("away_stats_")]
    drop_cols += [c for c in train_df.columns if c.startswith("home_players_") or c.startswith("away_players_")]

    results = []
    for target in target_cols:
        X_df, y, feature_cols = _build_features(train_df, target, drop_cols)
        if len(np.unique(y)) < 2:
            continue
        # skip targets with extremely sparse classes (short window)
        _, counts_all = np.unique(y, return_counts=True)
        if int(counts_all.min()) < 2:
            continue

        X_train, X_val, y_train, y_val = train_test_split(
            X_df, y, test_size=0.2, random_state=0, stratify=y
        )

        class_count = len(np.unique(y))
        n_estimators = 400 if class_count <= 5 else 200
        base = RandomForestClassifier(
            n_estimators=n_estimators, random_state=0, n_jobs=-1, class_weight="balanced_subsample"
        )
        # handle small class counts for calibration
        _, counts = np.unique(y_train, return_counts=True)
        min_count = int(counts.min()) if len(counts) > 0 else 0
        if min_count >= 3:
            clf = CalibratedClassifierCV(base, method="sigmoid", cv=3)
            clf.fit(X_train, y_train)
        elif min_count == 2:
            clf = CalibratedClassifierCV(base, method="sigmoid", cv=2)
            clf.fit(X_train, y_train)
        else:
            base.fit(X_train, y_train)
            clf = base

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            proba = clf.predict_proba(X_val)
            acc = accuracy_score(y_val, clf.predict(X_val))
        ll = log_loss(y_val, proba, labels=getattr(clf, "classes_", None))
        brier = _brier_score(y_val, proba, getattr(clf, "classes_", np.unique(y_val)))

        out_dir = os.path.join("Ai Engine", "models_cache", "seriea")
        os.makedirs(out_dir, exist_ok=True)
        model_path = os.path.join(out_dir, f"{MODEL_NAME}_{target}.pkl.gz")
        with gzip.open(model_path, "wb") as f:
            pickle.dump(
                {"model": clf, "features": feature_cols, "trained_at": datetime.now(timezone.utc).isoformat()},
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        size = os.path.getsize(model_path)
        if size > MAX_UPLOAD_MB * 1024 * 1024:
            # skip overly large models for now
            continue
        results.append(
            {
                "target": target,
                "model_path": model_path,
                "file_size": size,
                "accuracy": float(acc),
                "logloss": float(ll),
                "brier": float(brier),
                "feature_count": len(feature_cols),
                "train_rows": int(len(y)),
                "trained_range": f"{min(seasons)}-{max(seasons)}" if seasons else None,
            }
        )

    return results


def upload_and_register(model_path: str, file_size: int, target: str, metrics: dict) -> None:
    sb = get_supabase_client()
    bucket = "ai-models"
    _ensure_bucket(bucket)

    storage_path = f"seriea/{MODEL_NAME}_{target}.pkl.gz"
    with open(model_path, "rb") as f:
        sb.storage.from_(bucket).upload(
            storage_path, f, {"content-type": "application/octet-stream", "upsert": "true"}
        )

    sb.table("ai_model_registry").upsert(
        {
            "league_id": LEAGUE_ID,
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
            "notes": "Serie A pilot model",
        }
    ).execute()


if __name__ == "__main__":
    results = train_and_save_all()
    for r in results:
        upload_and_register(r["model_path"], r["file_size"], r["target"], r)
        print(f"Saved {r['model_path']} ({r['file_size']} bytes)")
