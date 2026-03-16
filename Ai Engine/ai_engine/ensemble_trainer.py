"""
Ensemble trainer: stacking 3 diverse models + calibrated meta-learner.

Models:
  - RandomForest    (captures non-linear interactions)
  - GradientBoosting (captures sequential patterns, typically strongest)
  - LogisticRegression (calibrated baseline, regularized)

The meta-learner combines base-model OOF probabilities into a final
calibrated prediction via a logistic regression stacker.
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

from .preprocessing.temporal_split import walk_forward_splits


@dataclass
class EnsemblePayload:
    """Serialisable payload for the full ensemble."""
    base_models: List[Tuple[str, Any]]        # [(name, fitted_model), ...]
    meta_model: Any                            # fitted meta-learner
    scaler: Optional[StandardScaler]           # scaler for LogReg base
    feature_cols: List[str]
    feature_medians: Dict[str, float]
    class_labels: List[str]
    base_weights: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    isotonic_calibrators: Optional[Dict[str, Any]] = field(default_factory=dict)


def _build_base_models(
    n_classes: int,
    n_samples: int = 5000,
    imbalance_ratio: float = 1.0,
) -> List[Tuple[str, Any]]:
    """Instantiate the 3 base models.

    Args:
        n_classes: number of target classes.
        n_samples: training set size — controls tree depth and n_estimators.
        imbalance_ratio: min_class_count / max_class_count (1.0 = balanced).
            class_weight is only applied when ratio < 0.35 (genuinely
            imbalanced targets like 1x2 or clean_sheet).  For near-balanced
            targets (e.g. over_0_5 at 95%) using class_weight inflates the
            minority class ~19x, destroying calibration (Brier 0.83).
    """
    use_balanced = imbalance_ratio < 0.35
    rf_class_weight = "balanced_subsample" if use_balanced else None
    logreg_class_weight = "balanced" if use_balanced else None

    max_depth = 6 if n_samples < 2000 else 10
    n_estimators_rf = 100 if n_samples < 1000 else 200
    n_estimators_gb = 100 if n_samples < 1000 else 150

    models = [
        (
            "rf",
            RandomForestClassifier(
                n_estimators=n_estimators_rf,
                random_state=0,
                n_jobs=-1,
                class_weight=rf_class_weight,
                max_depth=max_depth,
                min_samples_leaf=5,
            ),
        ),
        (
            "gb",
            GradientBoostingClassifier(
                n_estimators=n_estimators_gb,
                learning_rate=0.05,
                max_depth=min(max_depth, 5),
                min_samples_leaf=10,
                subsample=0.8,
                random_state=0,
            ),
        ),
        (
            "logreg",
            LogisticRegression(
                max_iter=2000,
                class_weight=logreg_class_weight,
                C=1.0,
                random_state=0,
            ),
        ),
    ]
    return models


def _generate_oof_probas(
    models: List[Tuple[str, Any]],
    X: np.ndarray,
    y: np.ndarray,
    splits: List[Tuple[np.ndarray, np.ndarray]],
    sample_weights: Optional[np.ndarray] = None,
    classes: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, List[Tuple[str, Any]]]:
    """
    Generate out-of-fold (OOF) predicted probabilities for the meta-learner.

    Returns:
      oof_matrix: (n_samples, n_classes * n_models) — OOF probabilities
      fitted_models: list of (name, fitted_model) on full training data
    """
    n_samples = X.shape[0]
    # Use pre-computed classes if provided (ensures OOF matrix width matches
    # the meta-learner input width when val set has classes absent from train).
    if classes is None:
        classes = np.unique(y)
    n_classes = len(classes)
    n_models = len(models)

    oof = np.full((n_samples, n_classes * n_models), np.nan)

    for m_idx, (name, model) in enumerate(models):
        for train_idx, val_idx in splits:
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr = y[train_idx]
            w_tr = sample_weights[train_idx] if sample_weights is not None else None

            model_clone = _clone_model(model)
            try:
                if w_tr is not None:
                    model_clone.fit(X_tr, y_tr, sample_weight=w_tr)
                else:
                    model_clone.fit(X_tr, y_tr)
            except TypeError:
                model_clone.fit(X_tr, y_tr)

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model_clone.predict_proba(X_val)

            # Align columns to classes
            model_classes = model_clone.classes_
            aligned_proba = np.zeros((len(val_idx), n_classes))
            for i, c in enumerate(classes):
                if c in model_classes:
                    idx_c = list(model_classes).index(c)
                    aligned_proba[:, i] = proba[:, idx_c]

            start_col = m_idx * n_classes
            oof[val_idx, start_col : start_col + n_classes] = aligned_proba

    # Fit models on full data for final predictions
    fitted_models = []
    for name, model in models:
        model_clone = _clone_model(model)
        try:
            if sample_weights is not None:
                model_clone.fit(X, y, sample_weight=sample_weights)
            else:
                model_clone.fit(X, y)
        except TypeError:
            model_clone.fit(X, y)
        fitted_models.append((name, model_clone))

    return oof, fitted_models


def _clone_model(model: Any) -> Any:
    """Clone a scikit-learn estimator."""
    from sklearn.base import clone
    return clone(model)


def _compute_base_weights(
    fitted_models: List[Tuple[str, Any]],
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> Dict[str, float]:
    """Compute weights based on inverse log-loss on validation."""
    weights = {}
    for name, model in fitted_models:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model.predict_proba(X_val)
            ll = log_loss(y_val, proba, labels=model.classes_)
            weights[name] = 1.0 / max(ll, 0.01)
        except Exception:
            weights[name] = 1.0
    return weights


def _train_isotonic_calibrators(
    fitted_models: List[Tuple[str, Any]],
    meta_model: Any,
    X_val: np.ndarray,
    y_val: np.ndarray,
    classes: np.ndarray,
    min_samples: int = 50,
    base_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Addestra un IsotonicRegression per classe sulle probabilità del validation set.

    Perché isotonic invece di Platt (sigmoid)?
    - Isotonic è non-parametrico: non assume forma della curva di calibrazione.
    - Appropriato quando la curva prevista→reale non è monotona lineare.
    - Richiede più dati (min ~50 per classe) ma è più flessibile.

    Flusso:
    1. Calcola probabilità ensemble sul val set (meta-learner o weighted avg)
    2. Per ogni classe c: fit ISO su (prob_pred_c, y_binary_c)
    3. Ritorna dict {class_label: IsotonicRegression} o {} se val troppo piccolo.

    NOTA: la calibrazione è fittata SULLO STESSO val set usato per le metriche.
    Questo introduce una lieve sovrastima della qualità di calibrazione, accettabile
    in produzione perché i fixture reali sono always out-of-sample rispetto al val.
    """
    if len(y_val) < min_samples:
        return {}

    class_strs = [str(c) for c in classes]
    n_classes = len(class_strs)

    # Calcola probabilità ensemble sul val set
    if meta_model is not None:
        try:
            base_probas = []
            for name, model in fitted_models:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    proba = model.predict_proba(X_val)
                model_classes = [str(c) for c in model.classes_]
                aligned = np.zeros((X_val.shape[0], n_classes))
                for i, c in enumerate(class_strs):
                    if c in model_classes:
                        idx_c = model_classes.index(c)
                        aligned[:, i] = proba[:, idx_c]
                base_probas.append(aligned)
            meta_input = np.hstack(base_probas)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                ensemble_proba = meta_model.predict_proba(meta_input)
            meta_classes = [str(c) for c in meta_model.classes_]
            # Allinea a class_strs
            proba_aligned = np.zeros((X_val.shape[0], n_classes))
            for i, c in enumerate(class_strs):
                if c in meta_classes:
                    idx_c = meta_classes.index(c)
                    proba_aligned[:, i] = ensemble_proba[:, idx_c]
        except Exception as exc:
            logger.warning("isotonic calibration (meta model) failed: %s", exc)
            return {}
    else:
        # Weighted average dei base models — usa gli stessi pesi di predict_ensemble
        try:
            _bw = base_weights or {}
            _total_w = sum(_bw.values()) if _bw else 0.0
            proba_aligned = np.zeros((X_val.shape[0], n_classes))
            for name, model in fitted_models:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    proba = model.predict_proba(X_val)
                model_classes = [str(c) for c in model.classes_]
                w = (_bw.get(name, 1.0) / _total_w) if _total_w > 0 else (1.0 / len(fitted_models))
                for i, c in enumerate(class_strs):
                    if c in model_classes:
                        idx_c = model_classes.index(c)
                        proba_aligned[:, i] += w * proba[:, idx_c]
        except Exception as exc:
            logger.warning("isotonic calibration (weighted avg) failed: %s", exc)
            return {}

    y_val_str = np.array([str(v) for v in y_val])
    calibrators: Dict[str, Any] = {}

    for i, c in enumerate(class_strs):
        y_binary = (y_val_str == c).astype(float)
        # Serve almeno un esempio positivo e uno negativo per fittare ISO
        if y_binary.sum() < 5 or (1.0 - y_binary).sum() < 5:
            continue
        preds = proba_aligned[:, i]
        try:
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(preds, y_binary)
            calibrators[c] = iso
        except Exception:
            continue

    return calibrators


def build_ensemble(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    sample_weights: Optional[np.ndarray] = None,
    feature_cols: Optional[List[str]] = None,
    feature_medians: Optional[Dict[str, float]] = None,
    train_dates: Optional[pd.Series] = None,
) -> EnsemblePayload:
    """
    Train a stacking ensemble and return the full payload.

    Steps:
    1. Standardize features for LogReg
    2. Generate OOF predictions via walk-forward CV on training
    3. Train meta-learner (calibrated LogReg) on OOF
    4. Compute base model weights on validation
    """
    if feature_cols is None:
        feature_cols = list(X_train.columns)
    if feature_medians is None:
        feature_medians = X_train.median(numeric_only=True).to_dict()

    X_tr_np = X_train.to_numpy().astype(float)
    y_tr_np = y_train.to_numpy()
    X_val_np = X_val.to_numpy().astype(float)
    y_val_np = y_val.to_numpy()

    classes = np.unique(np.concatenate([y_tr_np, y_val_np]))
    n_classes = len(classes)

    # Build walk-forward (temporal) splits for OOF within training.
    # StratifiedKFold causes temporal leakage — fold 1 trains on future data.
    # walk_forward_splits uses expanding windows with purge gaps.
    n_tr = len(y_tr_np)
    splits = []
    if train_dates is not None and len(train_dates) == n_tr:
        combined_for_wf = pd.DataFrame(X_tr_np)
        combined_for_wf["fixture_date"] = train_dates.values
        wf_splits = walk_forward_splits(
            combined_for_wf, n_splits=5, purge_days=30, min_train_rows=50,
        )
        splits = wf_splits if wf_splits else []

    if not splits:
        # Fallback: simple 70/30 temporal split when walk_forward_splits unavailable.
        cut = max(20, int(n_tr * 0.7))
        if cut < n_tr:
            splits = [(np.arange(0, cut), np.arange(cut, n_tr))]
        else:
            # Dataset troppo piccolo per qualsiasi split (n_tr <= 20):
            # NON usare train==val — il meta-learner overfitterebbe in-sample
            # producendo un BSS gonfiato e stake ingiustificatamente alte.
            # Lascia splits=[] → oof_clean sarà vuoto → meta_model=None →
            # predict_ensemble cade back su weighted average dei base models.
            splits = []

    # Scale for LogReg
    scaler = StandardScaler()
    X_tr_scaled = scaler.fit_transform(X_tr_np)
    X_val_scaled = scaler.transform(X_val_np)

    # Compute imbalance ratio for conditional class_weight
    _class_counts = pd.Series(y_tr_np).value_counts()
    _imbalance_ratio = float(_class_counts.min() / _class_counts.max()) if len(_class_counts) > 1 else 1.0

    # Build base models
    base_templates = _build_base_models(
        n_classes, n_samples=len(y_tr_np), imbalance_ratio=_imbalance_ratio,
    )

    # Generate OOF probabilities — pass pre-computed classes so OOF matrix
    # width matches meta-learner input (fixes mismatch when val has rare classes
    # absent from train, e.g. target_ht_ft with many outcome combinations).
    oof, fitted_models = _generate_oof_probas(
        base_templates, X_tr_scaled, y_tr_np, splits, sample_weights,
        classes=classes,
    )

    # Handle NaN in OOF (rows not covered by any fold)
    nan_mask = np.isnan(oof).any(axis=1)
    oof_clean = oof[~nan_mask]
    y_oof = y_tr_np[~nan_mask]

    # Train meta-learner on OOF predictions.
    # LogisticRegression is used directly (no CalibratedClassifierCV wrapper): LR
    # already outputs true probabilities by construction, so wrapping it in a
    # second sigmoid calibration would create double-calibration and push
    # extreme probabilities further toward 0/1, inflating false confidence.
    meta_model: Any
    if len(oof_clean) >= 20 and oof_clean.shape[1] > 0:
        meta_base = LogisticRegression(max_iter=2000, C=0.5, random_state=0)
        try:
            meta_base.fit(oof_clean, y_oof)
            meta_model = meta_base
        except Exception:
            meta_model = None
    else:
        # Fallback: simple average (meta_model = None)
        meta_model = None

    # Compute base weights on validation
    base_weights = _compute_base_weights(fitted_models, X_val_scaled, y_val_np)

    # Compute ensemble metrics on validation
    metrics = _evaluate_ensemble(
        fitted_models, meta_model, X_val_scaled, y_val_np, classes
    )

    class_labels = [str(c) for c in classes]

    # Train isotonic calibrators on validation set.
    # This maps ensemble predicted probabilities → actual win rates.
    # Requires min 50 val samples per class; falls back to empty dict (no calibration)
    # for small leagues. The calibration is applied automatically in predict_ensemble.
    isotonic_calibrators = _train_isotonic_calibrators(
        fitted_models, meta_model, X_val_scaled, y_val_np, classes,
        base_weights=base_weights,
    )

    return EnsemblePayload(
        base_models=fitted_models,
        meta_model=meta_model,
        scaler=scaler,
        feature_cols=feature_cols,
        feature_medians=feature_medians,
        class_labels=class_labels,
        base_weights=base_weights,
        metrics=metrics,
        isotonic_calibrators=isotonic_calibrators,
    )


def predict_ensemble(
    payload: EnsemblePayload,
    X: pd.DataFrame,
) -> Dict[str, float]:
    """
    Predict probabilities using the full ensemble.

    Returns dict of {class_label: probability}.
    """
    def _meta_n_features(meta: Any) -> Optional[int]:
        if meta is None:
            return None
        if hasattr(meta, "calibrated_classifiers_") and meta.calibrated_classifiers_:
            est = meta.calibrated_classifiers_[0].estimator
            return getattr(est, "n_features_in_", None)
        return getattr(meta, "n_features_in_", None)

    def _resolve_classes(p: EnsemblePayload) -> List[str]:
        meta = p.meta_model
        meta_classes = [str(c) for c in getattr(meta, "classes_", [])] if meta is not None else []
        payload_classes = [str(c) for c in getattr(p, "class_labels", [])]
        n_models = len(p.base_models) if getattr(p, "base_models", None) is not None else 0
        n_in = _meta_n_features(meta)

        if n_in and n_models:
            if meta_classes and len(meta_classes) * n_models == n_in:
                return meta_classes
            if payload_classes and len(payload_classes) * n_models == n_in:
                return payload_classes

        return meta_classes or payload_classes

    X_reindexed = X.reindex(columns=payload.feature_cols).select_dtypes(include=["number", "bool"]).copy()
    # Impute NaN con mediane (stessa logica del training) per evitare ValueError
    if getattr(payload, "feature_medians", None):
        X_reindexed = X_reindexed.fillna(payload.feature_medians)
    X_reindexed = X_reindexed.fillna(0)
    X_np = X_reindexed.to_numpy().astype(float)
    X_scaled = payload.scaler.transform(X_np) if payload.scaler else X_np
    classes = _resolve_classes(payload)
    if not classes:
        logger.warning("predict_ensemble: impossibile risolvere le classi — payload corrotto o vuoto. Ritorno {}.")
        return {}
    n_classes = len(classes)

    if payload.meta_model is not None:
        # Stacking: combine base model probabilities through meta-learner
        base_probas = []
        for name, model in payload.base_models:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model.predict_proba(X_scaled)
            # Align to classes
            model_classes = [str(c) for c in model.classes_]
            aligned = np.zeros((X_scaled.shape[0], n_classes))
            for i, c in enumerate(classes):
                if c in model_classes:
                    idx_c = model_classes.index(c)
                    aligned[:, i] = proba[:, idx_c]
            base_probas.append(aligned)

        meta_input = np.hstack(base_probas)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            final_proba = payload.meta_model.predict_proba(meta_input)

        # Align meta output to classes
        meta_classes = [str(c) for c in payload.meta_model.classes_]
        result = {}
        for i, c in enumerate(classes):
            if c in meta_classes:
                idx_c = meta_classes.index(c)
                result[c] = float(final_proba[0][idx_c])
            else:
                result[c] = 0.0
    else:
        # Fallback: weighted average of base models
        total_weight = sum(payload.base_weights.values()) or 1.0
        result = {c: 0.0 for c in classes}
        for name, model in payload.base_models:
            w = payload.base_weights.get(name, 1.0) / total_weight
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model.predict_proba(X_scaled)
            model_classes = [str(c) for c in model.classes_]
            for i, c in enumerate(classes):
                if c in model_classes:
                    idx_c = model_classes.index(c)
                    result[c] += w * float(proba[0][idx_c])

    # Apply isotonic calibration if available
    if getattr(payload, "isotonic_calibrators", None):
        calibrated = {}
        for c in result:
            iso = payload.isotonic_calibrators.get(c)
            if iso is not None:
                # IsotonicRegression.predict expects array-like
                calibrated[c] = float(np.clip(iso.predict([result[c]])[0], 0.001, 0.999))
            else:
                calibrated[c] = result[c]
        result = calibrated

    # Normalize
    total = sum(result.values()) or 1.0
    return {c: v / total for c, v in result.items()}


def get_ensemble_agreement(
    payload: EnsemblePayload,
    X: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Check how many base models agree on the predicted class.

    Returns: {
        'predicted_class': str,
        'agreement_ratio': float (0..1),
        'votes': {model_name: predicted_class},
    }
    """
    X_reindexed = X.reindex(columns=payload.feature_cols).select_dtypes(include=["number", "bool"]).copy()
    if getattr(payload, "feature_medians", None):
        X_reindexed = X_reindexed.fillna(payload.feature_medians)
    X_reindexed = X_reindexed.fillna(0)
    X_np = X_reindexed.to_numpy().astype(float)
    X_scaled = payload.scaler.transform(X_np) if payload.scaler else X_np

    votes = {}
    for name, model in payload.base_models:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                pred = model.predict(X_scaled)
            votes[name] = str(pred[0])
        except Exception as _exc:
            logger.warning("get_ensemble_agreement: modello '%s' ha sollevato eccezione: %s", name, _exc)

    if not votes:
        return {"predicted_class": "", "agreement_ratio": 0.0, "votes": {}}

    # Majority vote
    from collections import Counter
    counter = Counter(votes.values())
    most_common = counter.most_common(1)[0]
    predicted_class = most_common[0]
    agreement_ratio = most_common[1] / len(votes)

    return {
        "predicted_class": predicted_class,
        "agreement_ratio": agreement_ratio,
        "votes": votes,
    }


def _evaluate_ensemble(
    fitted_models: List[Tuple[str, Any]],
    meta_model: Any,
    X_val: np.ndarray,
    y_val: np.ndarray,
    classes: np.ndarray,
) -> Dict[str, float]:
    """Compute ensemble metrics on validation data."""
    metrics: Dict[str, float] = {}
    n_classes = len(classes)

    # Per-model metrics
    for name, model in fitted_models:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model.predict_proba(X_val)
            ll = log_loss(y_val, proba, labels=model.classes_)
            acc = float((model.predict(X_val) == y_val).mean())
            metrics[f"{name}_logloss"] = round(ll, 4)
            metrics[f"{name}_accuracy"] = round(acc, 4)
        except Exception:
            pass

    # Ensemble metrics (via meta-learner or weighted average)
    if meta_model is not None:
        try:
            base_probas = []
            for name, model in fitted_models:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    proba = model.predict_proba(X_val)
                model_classes = [str(c) for c in model.classes_]
                class_strs = [str(c) for c in classes]
                aligned = np.zeros((X_val.shape[0], n_classes))
                for i, c in enumerate(class_strs):
                    if c in model_classes:
                        idx_c = model_classes.index(c)
                        aligned[:, i] = proba[:, idx_c]
                base_probas.append(aligned)
            meta_input = np.hstack(base_probas)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                final_proba = meta_model.predict_proba(meta_input)
            y_str = np.array([str(v) for v in y_val])
            meta_ll = log_loss(y_str, final_proba, labels=meta_model.classes_)
            meta_preds = meta_model.predict(meta_input)
            meta_acc = float((meta_preds == y_str).mean())
            metrics["ensemble_logloss"] = round(meta_ll, 4)
            metrics["ensemble_accuracy"] = round(meta_acc, 4)
        except Exception:
            pass

    return metrics
