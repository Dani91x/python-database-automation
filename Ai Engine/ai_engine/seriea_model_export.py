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
import tempfile
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import pickle
import gzip
import json
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
from ai_engine.preprocessing.temporal_split import (
    temporal_train_val_holdout_split,
    walk_forward_splits,
)
from ai_engine.preprocessing.selection import apply_feature_selection
from ai_engine.ensemble_trainer import (
    build_ensemble,
    EnsemblePayload,
    _get_league_tier,
    _run_optuna_tuning,
    _KerasMetaWrapper,
)


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

    # Drop columns that are >50% NaN — after median imputation these become
    # noise (majority of rows get the same constant value, no signal).
    nan_pct = X.isna().mean()
    high_nan_cols = nan_pct[nan_pct > 0.50].index.tolist()
    if high_nan_cols:
        print(f"    Dropping {len(high_nan_cols)} columns with >50% NaN")
        X = X.drop(columns=high_nan_cols)

    # Drop rows that are >80% NaN (insufficient data for meaningful prediction)
    row_nan_pct = X.isna().mean(axis=1)
    bad_rows = row_nan_pct > 0.80
    if bad_rows.any():
        print(f"    Dropping {int(bad_rows.sum())} rows with >80% NaN")
        X = X.loc[~bad_rows]
        y = y.loc[X.index]

    # fillna(0) on medians guards against all-NaN columns whose median is NaN,
    # which would leave NaN unfilled and crash GradientBoosting downstream.
    medians = X.median(numeric_only=True).fillna(0).to_dict()
    X = X.fillna(medians).fillna(0)
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
    """
    Multiclass Expected Calibration Error: average ECE across all classes.

    P3 fix: the previous implementation used np.max(proba, axis=1) — the "top-1
    ECE" — which only bins samples by their highest predicted probability.  For a
    3-class market (H/D/A) this means the Draw class (D) is almost never the
    highest-probability class, so its miscalibration is invisible to the metric.

    This implementation bins each class independently:
      ECE_c = (1/n) * Σ_b |B_b| * |hitrate(B_b) - meanconf(B_b)|
      ECE   = mean over all classes
    where B_b is the set of samples whose P(c) falls in bin b.

    This correctly detects calibration errors in minority classes (e.g. Draw)
    and is consistent with the multiclass ECE described in Guo et al. (2017).
    """
    n = len(y_true)
    if n == 0:
        return 0.0
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    total_ece = 0.0
    for ci, c in enumerate(classes):
        confidences = proba[:, ci]
        actuals = (y_true == c).astype(float)
        class_ece = 0.0
        for i in range(n_bins):
            # First bin: closed on both sides [0, upper] to include probability=0.0.
            # Subsequent bins: half-open (lower, upper] (standard convention).
            if i == 0:
                mask = (confidences >= bin_boundaries[0]) & (confidences <= bin_boundaries[1])
            else:
                mask = (confidences > bin_boundaries[i]) & (confidences <= bin_boundaries[i + 1])
            if mask.sum() == 0:
                continue
            bin_conf = confidences[mask].mean()
            bin_acc = actuals[mask].mean()
            class_ece += mask.sum() * abs(bin_acc - bin_conf)
        total_ece += class_ece / n
    return float(total_ece / len(classes))


def _train_one_target(
    target: str,
    train_df: "pd.DataFrame",
    drop_cols: list[str],
    league_id: int,
    seasons: list,
    out_dir: str,
    n_jobs: int = -1,
) -> "dict | None":
    """
    Train a single target for one league. Returns result dict or None if skipped.
    Designed to be called in parallel via ThreadPoolExecutor.

    Args:
        n_jobs: parallelism hint forwarded to build_ensemble → _build_base_models.
            Use ``max(1, cpu_count // parallel_workers)`` to avoid CPU
            over-subscription when multiple targets run in parallel.
    """
    print(f"  [league {league_id}] Training target: {target}")
    X_df, y, _, medians = _build_features(train_df, target, drop_cols)
    if len(np.unique(y)) < 2:
        print(f"    Skipped {target}: only 1 class")
        return None
    _, counts_all = np.unique(y, return_counts=True)
    if int(counts_all.min()) < 2:
        print(f"    Skipped {target}: min class count < 2")
        return None

    combined = X_df.copy()
    combined["__target__"] = y
    combined["fixture_date"] = train_df.loc[X_df.index, "fixture_date"]

    train_split, val_split, holdout_split = temporal_train_val_holdout_split(
        combined, val_ratio=0.15, holdout_ratio=0.10, purge_days=30, date_col="fixture_date"
    )
    # P8 fix: prefer holdout set for metrics (never seen during model fitting).
    # Fall back to val when holdout is too small for a reliable Brier estimate.
    metrics_split = holdout_split if len(holdout_split) >= 15 else val_split

    if train_split.empty or val_split.empty:
        print(f"    Skipped {target}: insufficient data after temporal split")
        return None

    y_train = train_split["__target__"]
    y_val = val_split["__target__"]
    y_metrics = metrics_split["__target__"]
    train_dates = train_split["fixture_date"]
    X_train_raw = train_split.drop(columns=["__target__", "fixture_date"], errors="ignore")
    X_val_raw = val_split.drop(columns=["__target__", "fixture_date"], errors="ignore")
    X_metrics_raw = metrics_split.drop(columns=["__target__", "fixture_date"], errors="ignore")

    if len(np.unique(y_train)) < 2 or len(np.unique(y_val)) < 2:
        print(f"    Skipped {target}: insufficient class diversity after split")
        return None

    try:
        X_train_sel, X_val_sel, selected_cols = apply_feature_selection(
            X_train_raw, y_train, X_val_raw,
            correlation_threshold=0.95,
            mi_top_k=60,
        )
    except Exception as e:
        print(f"    Feature selection failed for {target}: {e}")
        X_train_sel = X_train_raw.fillna(0)
        X_val_sel = X_val_raw.fillna(0)
        selected_cols = list(X_train_raw.columns)

    selected_medians = {c: medians.get(c, 0.0) for c in selected_cols}
    # Apply the same feature selection to the metrics set (column reindex only —
    # no refitting).  Missing columns are filled with 0 (consistent with the
    # median-imputation strategy applied to val and live-prediction data).
    # Use selected_medians for imputation (consistent with train/val path).
    # fill_value=0.0 would bias metrics for features whose median is far from 0.
    X_metrics_sel = X_metrics_raw.reindex(columns=selected_cols).fillna(selected_medians).fillna(0.0)
    weights_train = _compute_time_weights(train_dates)

    # ── Optuna hyperparameter tuning (con cache per-lega) ────────────────────
    optuna_params: dict = {}
    _tier = _get_league_tier(len(y_train))
    _n_trials = {"TINY": 0, "SMALL": 15, "MEDIUM": 20, "LARGE": 30}.get(_tier, 0)

    if _n_trials > 0:
        _optuna_cache_path = os.path.join(out_dir, f"optuna_params_{target}.json")
        _need_retune = True
        if os.path.exists(_optuna_cache_path):
            try:
                with open(_optuna_cache_path, "r") as _f:
                    _cached = json.load(_f)
                _cached_n = _cached.get("n_train_at_tuning", 0)
                _cached_tier = _cached.get("tier", "")
                _n_now = len(y_train)
                # Re-tune if: tier changed, dataset grew >20%, or dataset shrank >20%
                if (
                    _cached_tier == _tier
                    and _cached_n * 0.80 <= _n_now < _cached_n * 1.20
                ):
                    optuna_params = _cached.get("best_params", {})
                    _need_retune = False
                    print(f"    Optuna cache hit per {target} (n_train={_n_now})")
            except Exception:
                pass

        if _need_retune:
            print(f"    Optuna tuning {target}: {_n_trials} trial, tier={_tier}...")
            _combined_for_opt = X_train_sel.copy()
            _combined_for_opt["fixture_date"] = train_dates.values
            _opt_splits = walk_forward_splits(
                _combined_for_opt, n_splits=5, purge_days=30, min_train_rows=50
            )
            if _opt_splits:
                optuna_params = _run_optuna_tuning(
                    X_train_sel.to_numpy().astype(float),
                    y_train.to_numpy(),
                    _opt_splits,
                    tier=_tier,
                    n_trials=_n_trials,
                )
                try:
                    _cache_dir = os.path.dirname(_optuna_cache_path)
                    with tempfile.NamedTemporaryFile(
                        "w", dir=_cache_dir, delete=False, suffix=".json"
                    ) as _tf:
                        json.dump({
                            "league_id": league_id,
                            "target": target,
                            "n_train_at_tuning": len(y_train),
                            "tier": _tier,
                            "best_params": optuna_params,
                            "tuned_at": datetime.now(timezone.utc).isoformat(),
                        }, _tf, indent=2)
                    os.replace(_tf.name, _optuna_cache_path)
                except Exception as _e:
                    print(f"    Avviso: impossibile salvare cache Optuna: {_e}")

    try:
        payload = build_ensemble(
            X_train_sel, y_train,
            X_val_sel, y_val,
            sample_weights=weights_train,
            feature_cols=selected_cols,
            feature_medians=selected_medians,
            train_dates=train_dates,
            optuna_params=optuna_params,
            tier=_tier,
            n_jobs=n_jobs,
        )
    except Exception as e:
        print(f"    Ensemble training failed for {target}: {e}")
        return None

    # Calibration metrics — evaluated on pre-isotonic ensemble probabilities of the
    # metrics set (holdout when large enough, val otherwise).
    # P2 fix: ensemble_proba (before isotonic) removes the PAVA in-sample optimism.
    #         Previously, the isotonic calibrators were fitted and evaluated on the
    #         same val set, making the Brier score artificially low (by design:
    #         PAVA minimises squared error on the fitting data).
    # P5 fix: isotonic_calibrators from build_ensemble() are authoritative — the
    #         second fit here was redundant and overwrote them with an identical
    #         result.  Removed entirely to keep a single source of truth.
    # P8 fix: metrics_split is holdout_split when len(holdout_split) >= 15, giving
    #         a truly out-of-sample Brier/ECE that was never seen during fitting.
    calibration_metrics = {}
    try:
        # Minimum sample guard: fewer than 10 metrics samples produce unreliable
        # Brier/ECE estimates.  Raise early so the except handler stores None rather
        # than a statistically meaningless value that could fool calibration gates.
        if len(metrics_split) < 10:
            raise ValueError(
                f"metrics set too small ({len(metrics_split)} rows); "
                "brier/ece not computed"
            )
        X_metrics_np = X_metrics_sel.to_numpy().astype(float)
        X_metrics_scaled = payload.scaler.transform(X_metrics_np) if payload.scaler else X_metrics_np
        classes = np.array(payload.class_labels)
        base_probas_list = []
        for name, model in payload.base_models:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model.predict_proba(X_metrics_scaled)
            model_classes = [str(c) for c in model.classes_]
            aligned = np.zeros((X_metrics_scaled.shape[0], len(classes)))
            for ci, c in enumerate(classes):
                if c in model_classes:
                    idx_c = model_classes.index(c)
                    aligned[:, ci] = proba[:, idx_c]
            base_probas_list.append(aligned)
        # Guard: _KerasMetaWrapper deserialized with TF unavailable has
        # _model=None — using it as meta-learner would produce uniform
        # distributions and corrupt Brier/ECE metrics silently.
        _meta_for_metrics = payload.meta_model
        if isinstance(_meta_for_metrics, _KerasMetaWrapper) and _meta_for_metrics._model is None:
            print(f"    WARNING [{target}]: _KerasMetaWrapper._model is None "
                  "(TF unavailable) — using weighted average for calibration metrics.")
            _meta_for_metrics = None

        if _meta_for_metrics is not None:
            meta_input = np.hstack(base_probas_list)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                ensemble_proba = _meta_for_metrics.predict_proba(meta_input)
        else:
            total_w = sum(payload.base_weights.values()) or 1.0
            ensemble_proba = np.zeros_like(base_probas_list[0])
            for (name, _), bp in zip(payload.base_models, base_probas_list):
                w = payload.base_weights.get(name, 1.0) / total_w
                ensemble_proba += w * bp

        y_metrics_str = np.array([str(v) for v in y_metrics.to_numpy()])

        n_classes_expected = len(classes)
        if ensemble_proba.shape[1] != n_classes_expected:
            if _meta_for_metrics is not None and hasattr(_meta_for_metrics, "classes_"):
                meta_cls = [str(c) for c in _meta_for_metrics.classes_]
            else:
                # Positional fallback: assumes meta-model output order matches
                # `classes[:k]`.  This may be wrong if the meta-model was trained
                # with a different class ordering.  Metrics should be treated with
                # caution when this warning fires.
                meta_cls = [str(c) for c in classes[:ensemble_proba.shape[1]]]
                print(
                    f"    WARNING [{target}]: meta_model has no classes_ attribute — "
                    f"falling back to positional class mapping; calibration metrics "
                    f"may be unreliable if class ordering differs."
                )
            aligned_proba = np.zeros((ensemble_proba.shape[0], n_classes_expected))
            for ci, c in enumerate(classes):
                c_str = str(c)
                if c_str in meta_cls:
                    aligned_proba[:, ci] = ensemble_proba[:, meta_cls.index(c_str)]
            ensemble_proba = aligned_proba

        brier = _brier_score(y_metrics_str, ensemble_proba, classes)
        ece = _ece_score(y_metrics_str, ensemble_proba, classes)
        calibration_metrics = {"brier": round(brier, 4), "ece": round(ece, 4)}
    except Exception as e:
        print(f"    Calibration metrics failed for {target}: {e}")
        calibration_metrics = {"brier": None, "ece": None}

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
        "isotonic_calibrators": payload.isotonic_calibrators,
        "calibration_metrics": calibration_metrics,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    with gzip.open(model_path, "wb") as f:
        pickle.dump(save_payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    size = os.path.getsize(model_path)
    _too_large = size > MAX_UPLOAD_MB * 1024 * 1024
    if _too_large:
        # Model exceeds the upload limit: still return metrics so the caller
        # (retrain_all_leagues) can record BSS, log the event, and update the
        # model_performance table.  The upload step is skipped but the result
        # dict is marked with upload_skipped=True so the orchestrator knows.
        print(
            f"    WARNING [{target}]: model too large "
            f"({size / 1024 / 1024:.1f} MB > {MAX_UPLOAD_MB} MB limit) "
            f"— upload skipped, local file retained at {model_path}"
        )

    metrics = payload.metrics
    print(f"    {target}: acc={metrics.get('ensemble_accuracy', 'N/A')}, "
          f"ll={metrics.get('ensemble_logloss', 'N/A')}, "
          f"brier={calibration_metrics.get('brier', 'N/A')}, "
          f"ece={calibration_metrics.get('ece', 'N/A')}, "
          f"features={len(selected_cols)}")
    return {
        "target": target,
        "model_path": model_path,
        "file_size": size,
        "upload_skipped": _too_large,
        "accuracy": metrics.get("ensemble_accuracy", metrics.get("rf_accuracy", 0.0)),
        "logloss": metrics.get("ensemble_logloss", metrics.get("rf_logloss", 0.0)),
        "brier": calibration_metrics.get("brier"),
        "ece": calibration_metrics.get("ece"),
        "class_labels": payload.class_labels,
        "n_classes": len(payload.class_labels),
        "feature_count": len(selected_cols),
        "train_rows": int(len(y_train)),
        "val_rows": int(len(y_val)),
        "trained_range": f"{min(seasons)}-{max(seasons)}" if seasons else None,
        "league_id": league_id,
        "model_type": MODEL_NAME,
        "base_weights": payload.base_weights,
        "per_model_metrics": {
            k: v for k, v in metrics.items()
            if k.startswith(("rf_", "gb_", "lgb_", "xgb_", "logreg_"))
        },
    }


def train_and_save_all(
    league_id: int,
    last_n_seasons: int = 3,
    targets_filter: list[str] | None = None,
) -> list[dict]:
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

    # Stale data guard: warn if the most recent fixture is older than 30 days.
    # This can happen when the ETL pipeline has not run recently or when the
    # season is in a winter break.  The model will still train, but predictions
    # made from stale data may be unreliable.
    if "fixture_date" in train_df.columns:
        try:
            max_date = pd.to_datetime(train_df["fixture_date"], errors="coerce").max()
            if pd.notna(max_date):
                today = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
                if max_date.tz is not None:
                    max_date = max_date.tz_localize(None)
                days_stale = (today - max_date).days
                if days_stale > 30:
                    print(
                        f"  WARNING [league {league_id}]: most recent fixture is "
                        f"{days_stale} days old ({max_date.date()}) — training data may be stale."
                    )
        except Exception:
            pass

    all_target_cols = [c for c in train_df.columns if c.startswith("target_")]

    # Prioritise targets that have Betfair markets (can actually generate bets).
    # Other targets are still trained but placed last so critical ones finish first.
    PRIORITY_TARGETS = {
        "target_1x2", "target_btts", "target_over_2_5", "target_over_1_5",
        "target_over_3_5", "target_over_0_5", "target_ht_over_0_5",
        "target_clean_sheet_home", "target_clean_sheet_away",
    }
    priority = [t for t in all_target_cols if t in PRIORITY_TARGETS]
    rest = [t for t in all_target_cols if t not in PRIORITY_TARGETS]
    target_cols = priority + rest

    # Optional: filter to specific targets (e.g. priority-only for speed)
    if targets_filter:
        target_cols = [t for t in target_cols if t in targets_filter]

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

    out_dir = os.path.join(ROOT, "Ai Engine", "models_cache", f"league_{league_id}")
    os.makedirs(out_dir, exist_ok=True)

    # Parallel training: ogni target è indipendente → ThreadPoolExecutor (sklearn rilascia GIL)
    # n_workers e n_jobs_per_model sono configurabili via env var per supportare l'esecuzione
    # di più leghe in parallelo senza CPU over-subscription.
    # Esempio con 2 leghe parallele: RETRAIN_N_WORKERS=2, RETRAIN_PARALLEL_LEAGUES=2
    #   → n_workers=2, n_jobs=max(1, 8//(2*2))=2 → totale 8 core esatti.
    results = []
    _env_max_w = int(os.environ.get("RETRAIN_N_WORKERS") or "4")
    _env_par_l = int(os.environ.get("RETRAIN_PARALLEL_LEAGUES") or "1")
    n_workers = max(1, min(_env_max_w, len(target_cols)))
    n_jobs_per_model = max(1, (os.cpu_count() or 4) // max(n_workers * _env_par_l, 1))
    print(f"  [league {league_id}] Training {len(target_cols)} target con {n_workers} worker paralleli "
          f"(n_jobs_per_model={n_jobs_per_model})...")
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        future_to_target = {
            executor.submit(
                _train_one_target, t, train_df, drop_cols, league_id, seasons, out_dir, n_jobs_per_model
            ): t
            for t in target_cols
        }
        for future in as_completed(future_to_target):
            t = future_to_target[future]
            try:
                r = future.result()
                if r is not None:
                    results.append(r)
            except Exception as exc:
                print(f"    [league {league_id}] Target {t} ha sollevato un'eccezione: {exc}")

    return results


def upload_and_register(model_path: str, file_size: int, target: str, metrics: dict) -> None:
    """Upload model to Supabase storage and register in ai_model_registry."""
    sb = get_supabase_client()
    league_id = metrics.get("league_id")
    bucket = f"ai-models-league-{league_id}"
    _ensure_bucket(bucket)

    storage_path = f"{MODEL_NAME}_{target}.pkl.gz"
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
        if r.get("upload_skipped"):
            print(f"  SKIPPED upload {r['target']} — model too large "
                  f"({r['file_size'] / 1024 / 1024:.1f} MB), local file retained.")
            continue
        upload_and_register(r["model_path"], r["file_size"], r["target"], r)
        print(f"  Uploaded {r['target']} ({r['file_size']} bytes, "
              f"acc={r.get('accuracy', 'N/A')}, features={r.get('feature_count', '?')})")


if __name__ == "__main__":
    main()
