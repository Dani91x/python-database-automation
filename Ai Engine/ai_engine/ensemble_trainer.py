"""
Ensemble trainer: stacking diverse models + calibrated meta-learner.

Models:
  - RandomForest         (captures non-linear interactions)
  - LightGBM / GradientBoosting (captures sequential patterns, typically strongest)
  - XGBoost              (gradient boosting with regularisation)
  - LogisticRegression   (calibrated baseline, regularized)

The meta-learner combines base-model OOF probabilities into a final
calibrated prediction via a logistic regression stacker (or MLP for LARGE tier).
"""
from __future__ import annotations

import logging
import warnings
from collections import Counter
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

try:
    from xgboost import XGBClassifier as _XGBClassifier
    _XGBOOST_AVAILABLE = True
except ImportError:
    _XGBClassifier = None  # type: ignore
    _XGBOOST_AVAILABLE = False

try:
    import lightgbm as lgb
    from lightgbm import LGBMClassifier
    _LIGHTGBM_AVAILABLE = True
except ImportError:
    _LIGHTGBM_AVAILABLE = False

try:
    import tensorflow as _tf
    _tf.get_logger().setLevel("ERROR")
    _TENSORFLOW_AVAILABLE = True
except ImportError:
    _TENSORFLOW_AVAILABLE = False

try:
    from imblearn.over_sampling import SVMSMOTE
    _IMBLEARN_AVAILABLE = True
except ImportError:
    _IMBLEARN_AVAILABLE = False

warnings.filterwarnings("ignore", module="lightgbm")


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
    isotonic_calibrators: Dict[str, Any] = field(default_factory=dict)


def _clone_model(model: Any) -> Any:
    """Clone a scikit-learn estimator (or _XGBWrapper)."""
    # sklearn.base.clone checks `is` identity on get_params() return values,
    # which fails for _XGBWrapper because get_params() returns a dict copy.
    # Handle it explicitly to bypass the protocol. Use deepcopy to protect
    # against mutable nested values in xgb_kwargs.
    if isinstance(model, _XGBWrapper):
        import copy
        return _XGBWrapper(xgb_kwargs=copy.deepcopy(model._xgb_kwargs))
    from sklearn.base import clone
    return clone(model)


class _XGBWrapper:
    """
    Thin wrapper around XGBClassifier that handles string labels.

    XGBoost 3.x requires integer labels 0..n_classes-1.  This wrapper
    encodes labels with LabelEncoder on fit so callers can pass string
    targets (e.g. ['H', 'D', 'A']) without modification.

    sklearn.base.clone compatible via get_params / set_params.
    """

    def __init__(self, xgb_kwargs: dict | None = None):
        from sklearn.preprocessing import LabelEncoder
        self._xgb_kwargs: dict = xgb_kwargs or {}
        self._le = LabelEncoder()
        self.classes_: Optional[np.ndarray] = None
        self._xgb: Any = None

    def _make_xgb(self) -> Any:
        return _XGBClassifier(verbosity=0, **self._xgb_kwargs)

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: Optional[np.ndarray] = None) -> "_XGBWrapper":
        y_enc = self._le.fit_transform(y)
        self.classes_ = self._le.classes_
        self._xgb = self._make_xgb()
        kw: Dict[str, Any] = {}
        if sample_weight is not None:
            kw["sample_weight"] = sample_weight
        try:
            self._xgb.fit(X, y_enc, **kw)
        except TypeError:
            self._xgb.fit(X, y_enc)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._xgb.predict_proba(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        y_pred_enc = np.round(self._xgb.predict(X)).astype(int)
        return self._le.inverse_transform(y_pred_enc)

    def get_params(self, deep: bool = True) -> dict:
        return {"xgb_kwargs": dict(self._xgb_kwargs)}

    def set_params(self, **params: Any) -> "_XGBWrapper":
        if "xgb_kwargs" in params:
            self._xgb_kwargs = dict(params["xgb_kwargs"])
        return self


def _get_league_tier(n_train: int) -> str:
    """Return league tier based on training set size."""
    if n_train < 150:
        return "TINY"
    elif n_train < 350:
        return "SMALL"
    elif n_train < 700:
        return "MEDIUM"
    else:
        return "LARGE"


def _run_optuna_tuning(
    X_train: np.ndarray,
    y_train: np.ndarray,
    splits: List[Tuple[np.ndarray, np.ndarray]],
    tier: str,
    n_trials: int,
    random_state: int = 42,
) -> dict:
    """
    Run Optuna hyperparameter tuning for RF, LGB/GB and XGB.

    Uses TPE sampler with NLL (OOF log-loss) as the objective metric.
    Returns dict {"rf": {...}, "lgb": {...}, "xgb": {...}} or {} on failure.
    """
    if n_trials == 0:
        return {}

    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        logger.debug("Optuna not available — skipping hyperparameter tuning.")
        return {}

    classes = np.unique(y_train)

    def _oof_nll(model_fn, X: np.ndarray, y: np.ndarray) -> float:
        """Compute mean OOF NLL across splits.

        Aligns predicted probabilities to the global ``classes`` array before
        computing log_loss.  This handles two cases that cause shape mismatches:

        1. _XGBWrapper: its internal LabelEncoder is fit on y[tr_idx] only, so
           if a rare class is absent from a fold its classes_ has fewer entries
           than the global classes array — proba has fewer columns.
        2. Any model: a fold may not contain all classes in y[tr_idx] so the
           model's classes_ can be a strict subset of the global classes.

        Without alignment, log_loss(labels=classes) raises a shape error or
        silently computes the metric on misaligned columns.
        """
        if not splits:
            return float("inf")
        n_global = len(classes)
        class_to_global_idx: Dict[Any, int] = {c: i for i, c in enumerate(classes)}
        nlls = []
        for tr_idx, val_idx in splits:
            m = model_fn()
            try:
                m.fit(X[tr_idx], y[tr_idx])
                raw_proba = m.predict_proba(X[val_idx])
                model_classes = getattr(m, "classes_", None)
                # Fast path: model was trained on all classes in correct order
                if (
                    model_classes is not None
                    and len(model_classes) == n_global
                    and all(mc == gc for mc, gc in zip(model_classes, classes))
                ):
                    aligned = raw_proba
                else:
                    # Align columns to global classes; missing classes → 0.0
                    n_val = len(val_idx)
                    aligned = np.zeros((n_val, n_global))
                    if model_classes is not None:
                        for local_i, c in enumerate(model_classes):
                            global_i = class_to_global_idx.get(c)
                            if global_i is not None:
                                aligned[:, global_i] = raw_proba[:, local_i]
                    else:
                        # No classes_ attribute: assume columns match global order
                        n_cols = min(raw_proba.shape[1], n_global)
                        aligned[:, :n_cols] = raw_proba[:, :n_cols]
                    # Renormalise rows that had missing classes
                    row_sums = aligned.sum(axis=1, keepdims=True)
                    row_sums = np.where(row_sums == 0, 1.0, row_sums)
                    aligned = aligned / row_sums
                nlls.append(log_loss(y[val_idx], aligned, labels=classes))
            except Exception:
                nlls.append(float("inf"))
        return float(np.mean(nlls)) if nlls else float("inf")

    best_params: dict = {}

    # --- RF ---
    def _rf_objective(trial: Any) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 20),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.5]),
        }
        def _build():
            return RandomForestClassifier(random_state=random_state, n_jobs=-1, **params)
        return _oof_nll(_build, X_train, y_train)

    try:
        sampler = optuna.samplers.TPESampler(seed=random_state)
        study_rf = optuna.create_study(direction="minimize", sampler=sampler)
        study_rf.optimize(_rf_objective, n_trials=n_trials, show_progress_bar=False)
        best_params["rf"] = study_rf.best_params
    except Exception as exc:
        logger.warning("Optuna RF tuning failed: %s", exc)

    # --- LGB / GB ---
    def _lgb_objective(trial: Any) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 400),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        }
        def _build():
            if _LIGHTGBM_AVAILABLE and tier in ("MEDIUM", "LARGE"):
                return LGBMClassifier(random_state=random_state, n_jobs=-1, verbose=-1, **params)
            gb_params = {k: v for k, v in params.items() if k in (
                "n_estimators", "learning_rate", "max_depth", "subsample"
            )}
            gb_params["min_samples_leaf"] = params.get("min_child_samples", 10)
            return GradientBoostingClassifier(random_state=random_state, **gb_params)
        return _oof_nll(_build, X_train, y_train)

    try:
        sampler = optuna.samplers.TPESampler(seed=random_state)
        study_lgb = optuna.create_study(direction="minimize", sampler=sampler)
        study_lgb.optimize(_lgb_objective, n_trials=n_trials, show_progress_bar=False)
        best_params["lgb"] = study_lgb.best_params
    except Exception as exc:
        logger.warning("Optuna LGB/GB tuning failed: %s", exc)

    # --- XGB ---
    if _XGBOOST_AVAILABLE and tier in ("SMALL", "MEDIUM", "LARGE"):
        def _xgb_objective(trial: Any) -> float:
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 50, 400),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
            }
            def _build():
                _kw = dict(params)
                _kw.setdefault("random_state", random_state)
                _kw.setdefault("n_jobs", 1)
                return _XGBWrapper(xgb_kwargs=_kw)
            return _oof_nll(_build, X_train, y_train)

        try:
            sampler = optuna.samplers.TPESampler(seed=random_state)
            study_xgb = optuna.create_study(direction="minimize", sampler=sampler)
            study_xgb.optimize(_xgb_objective, n_trials=n_trials, show_progress_bar=False)
            best_params["xgb"] = study_xgb.best_params
        except Exception as exc:
            logger.warning("Optuna XGB tuning failed: %s", exc)

    return best_params


def _build_base_models(
    n_classes: int,
    n_samples: int = 5000,
    imbalance_ratio: float = 1.0,
    tier: str = "MEDIUM",
    xgb_params: dict | None = None,
    lgb_params: dict | None = None,
    rf_params: dict | None = None,
    n_jobs: int = -1,
) -> List[Tuple[str, Any]]:
    """Instantiate the base models based on tier and available libraries.

    Args:
        n_classes: number of target classes.
        n_samples: training set size — controls tree depth and n_estimators.
        imbalance_ratio: min_class_count / max_class_count (1.0 = balanced).
            class_weight is only applied when ratio < 0.35 (genuinely
            imbalanced targets like 1x2 or clean_sheet).
        tier: league tier (TINY/SMALL/MEDIUM/LARGE).
        xgb_params: optional Optuna-tuned XGBoost params.
        lgb_params: optional Optuna-tuned LGB/GB params.
        rf_params: optional Optuna-tuned RF params.
        n_jobs: parallelism hint for tree-based models.  Pass a value < -1
            or compute ``max(1, cpu_count // parallel_workers)`` at the call
            site to prevent CPU over-subscription when multiple targets are
            trained in parallel via ThreadPoolExecutor.  Default -1 = use
            all cores (safe when only one target is trained at a time).
    """
    use_balanced = imbalance_ratio < 0.35
    logreg_class_weight = "balanced" if use_balanced else None

    max_depth = 6 if n_samples < 2000 else 10
    n_estimators_rf = 100 if n_samples < 1000 else 200

    models: List[Tuple[str, Any]] = []

    # --- RandomForest (always present) ---
    if rf_params:
        rf = RandomForestClassifier(
            random_state=42,
            n_jobs=n_jobs,
            class_weight="balanced_subsample" if use_balanced else None,
            **rf_params,
        )
    else:
        rf = RandomForestClassifier(
            n_estimators=n_estimators_rf,
            random_state=42,
            n_jobs=n_jobs,
            class_weight="balanced_subsample" if use_balanced else None,
            max_depth=max_depth,
            min_samples_leaf=5,
        )
    models.append(("rf", rf))

    # --- LightGBM (MEDIUM/LARGE) or GradientBoosting (SMALL) ---
    if tier in ("MEDIUM", "LARGE") and _LIGHTGBM_AVAILABLE:
        if lgb_params:
            _lgb_kw = dict(lgb_params)
        else:
            # 300 trees with lr=0.05 is the right balance: more trees than the
            # old 100/150 so the model can use early stopping to find the
            # optimal iteration instead of being capped artificially.
            # max_depth=-1 + num_leaves=31 is idiomatic LightGBM (leaf-wise
            # growth controlled by num_leaves, not level-wise depth).
            # min_child_samples=20 prevents leaves with <20 samples —
            # important regularisation for leghe MEDIUM (350-700 matches).
            # reg_alpha / reg_lambda mirror the XGBoost L1/L2 defaults.
            # colsample_bytree adds feature-subsampling per tree.
            _lgb_kw = {
                "n_estimators": 300,
                "learning_rate": 0.05,
                "max_depth": -1,
                "num_leaves": 31,
                "min_child_samples": 20,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_alpha": 0.1,
                "reg_lambda": 1.0,
            }
        lgb_model = LGBMClassifier(
            random_state=42,
            n_jobs=n_jobs,
            verbose=-1,
            # class_weight deliberately None: we pass sample_weight (time-decay)
            # which conflicts with class_weight inside LightGBM.
            class_weight=None,
            **_lgb_kw,
        )
        models.append(("lgb", lgb_model))
    elif tier == "SMALL":
        # sklearn GradientBoosting for SMALL tier: more stable than LightGBM
        # leaf-wise growth on <350 samples where num_leaves can overfit.
        if lgb_params:
            gb_kw = {k: v for k, v in lgb_params.items() if k in (
                "n_estimators", "learning_rate", "max_depth", "subsample"
            )}
            gb_kw.setdefault("min_samples_leaf", lgb_params.get("min_child_samples", 10))
        else:
            gb_kw = {
                "n_estimators": 100,
                "learning_rate": 0.05,
                "max_depth": min(max_depth, 4),
                "min_samples_leaf": 10,
                "subsample": 0.8,
            }
        gb_model = GradientBoostingClassifier(random_state=42, **gb_kw)
        models.append(("gb", gb_model))
    # TINY: no GB/LGB

    # --- XGBoost (SMALL/MEDIUM/LARGE) ---
    # Uses _XGBWrapper for transparent string-label encoding (XGBoost 3.x
    # requires integer labels 0..n_classes-1).
    if _XGBOOST_AVAILABLE and tier in ("SMALL", "MEDIUM", "LARGE"):
        if xgb_params:
            _xgb_kw = dict(xgb_params)
        else:
            # reg_alpha (L1) promotes feature sparsity — valuable when many
            # rolling-window columns are NaN-filled with the median (no signal).
            # reg_lambda (L2) smooths leaf weights and reduces overfitting on
            # small leagues.  Both are absent from sklearn GradientBoosting,
            # which is a key reason XGBoost is more robust here.
            _xgb_kw = {
                "n_estimators": 100 if n_samples < 1000 else 150,
                "learning_rate": 0.05,
                "max_depth": min(max_depth, 6),
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_alpha": 0.1,
                "reg_lambda": 1.0,
                "eval_metric": "mlogloss",
            }
        _xgb_kw.setdefault("reg_alpha", 0.1)
        _xgb_kw.setdefault("reg_lambda", 1.0)
        _xgb_kw.setdefault("random_state", 42)
        _xgb_kw.setdefault("n_jobs", n_jobs)
        xgb_model = _XGBWrapper(xgb_kwargs=_xgb_kw)
        models.append(("xgb", xgb_model))

    # --- LogisticRegression (always present) ---
    models.append((
        "logreg",
        LogisticRegression(
            max_iter=2000,
            class_weight=logreg_class_weight,
            C=1.0,
            random_state=0,
        ),
    ))

    return models


def _apply_smote(
    X: np.ndarray,
    y: np.ndarray,
    imbalance_ratio: float,
    tier: str,
    random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Apply SVMSMOTE oversampling when conditions are met."""
    if not _IMBLEARN_AVAILABLE:
        return X, y
    if imbalance_ratio >= 0.35 or tier not in ("MEDIUM", "LARGE"):
        return X, y

    unique, counts = np.unique(y, return_counts=True)
    min_class_count = counts.min()
    if min_class_count < 6:
        return X, y

    try:
        smote = SVMSMOTE(random_state=random_state, k_neighbors=min(5, min_class_count - 1))
        X_res, y_res = smote.fit_resample(X, y)
        logger.info("SMOTE applied: %d → %d samples", len(y), len(y_res))
        return X_res, y_res
    except Exception as exc:
        logger.warning("SMOTE failed, using original data: %s", exc)
        return X, y


def _generate_oof_probas(
    models: List[Tuple[str, Any]],
    X: np.ndarray,
    y: np.ndarray,
    splits: List[Tuple[np.ndarray, np.ndarray]],
    sample_weights: Optional[np.ndarray] = None,
    classes: Optional[np.ndarray] = None,
    smote_params: dict | None = None,
    X_val_for_es: Optional[np.ndarray] = None,
    y_val_for_es: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, List[Tuple[str, Any]]]:
    """
    Generate out-of-fold (OOF) predicted probabilities for the meta-learner.

    Args:
        models: list of (name, model_template) base learners.
        X: scaled training features (n_train, n_features).
        y: training labels.
        splits: walk-forward (train_idx, val_idx) pairs for OOF generation.
        sample_weights: optional time-decay weights aligned to X rows.
        classes: global class array; ensures OOF matrix width is stable even
            when individual folds miss a rare class.
        smote_params: if set, SVMSMOTE is applied inside each training fold.
        X_val_for_es: validation features for LightGBM early stopping on the
            final full fit.  Only used for LGBMClassifier; ignored otherwise.
        y_val_for_es: validation labels paired with X_val_for_es.

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

            # Apply SMOTE before fitting if requested
            if smote_params is not None:
                X_tr_fit, y_tr_fit = _apply_smote(
                    X_tr, y_tr,
                    imbalance_ratio=smote_params["imbalance_ratio"],
                    tier=smote_params["tier"],
                )
                if w_tr is not None and len(X_tr_fit) > len(X_tr):
                    n_new = len(X_tr_fit) - len(X_tr)
                    w_tr_fit = np.concatenate([w_tr, np.ones(n_new)])
                else:
                    w_tr_fit = w_tr
            else:
                X_tr_fit, y_tr_fit, w_tr_fit = X_tr, y_tr, w_tr

            model_clone = _clone_model(model)
            try:
                if w_tr_fit is not None:
                    model_clone.fit(X_tr_fit, y_tr_fit, sample_weight=w_tr_fit)
                else:
                    model_clone.fit(X_tr_fit, y_tr_fit)
            except TypeError:
                model_clone.fit(X_tr_fit, y_tr_fit)

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model_clone.predict_proba(X_val)

            # Align columns to global classes using a precomputed dict (O(1)
            # per lookup vs O(n) for list.index in the original code).
            model_classes = model_clone.classes_
            model_class_to_idx: Dict[Any, int] = {
                c: i for i, c in enumerate(model_classes)
            }
            aligned_proba = np.zeros((len(val_idx), n_classes))
            for global_i, c in enumerate(classes):
                local_i = model_class_to_idx.get(c)
                if local_i is not None:
                    aligned_proba[:, global_i] = proba[:, local_i]

            start_col = m_idx * n_classes
            oof[val_idx, start_col : start_col + n_classes] = aligned_proba

    # Fit models on full training data for final predictions.
    # LightGBM uses early stopping against X_val_for_es (when provided) so
    # n_estimators=300 acts as a ceiling and the model stops at the optimal
    # iteration, avoiding the overfitting that a fixed n_estimators causes.
    fitted_models = []
    for name, model in models:
        model_clone = _clone_model(model)
        fit_kwargs: Dict[str, Any] = {}
        if sample_weights is not None:
            fit_kwargs["sample_weight"] = sample_weights

        # LightGBM early stopping on final fit using the held-out val set.
        # Early stopping is NOT applied inside OOF folds because each fold
        # has no separate val set (the fold val_idx is used for OOF probas,
        # not for early stopping).  This is only for the final full-data fit.
        _es_applied = False
        if (
            _LIGHTGBM_AVAILABLE
            and isinstance(model_clone, LGBMClassifier)
            and X_val_for_es is not None
            and y_val_for_es is not None
            and len(y_val_for_es) >= 20
        ):
            try:
                fit_kwargs["eval_set"] = [(X_val_for_es, y_val_for_es)]
                # early_stopping: stop when val loss doesn't improve for 30 rounds.
                # log_evaluation(period=0): suppress all LightGBM iteration output.
                # Both callbacks are portable across LightGBM >= 3.3.0.
                fit_kwargs["callbacks"] = [
                    lgb.early_stopping(stopping_rounds=30),
                    lgb.log_evaluation(period=0),
                ]
                _es_applied = True
            except Exception as _es_exc:
                logger.debug("LightGBM early stopping setup failed: %s — training without ES", _es_exc)
                fit_kwargs.pop("eval_set", None)
                fit_kwargs.pop("callbacks", None)

        try:
            model_clone.fit(X, y, **fit_kwargs)
            if _es_applied:
                best_iter = getattr(model_clone, "best_iteration_", None)
                if best_iter and best_iter > 0:
                    logger.info(
                        "[lgb early stopping] best_iteration=%d / %d",
                        best_iter,
                        model_clone.get_params().get("n_estimators", "?"),
                    )
        except TypeError:
            # A kwarg in fit_kwargs is unsupported by this model.  Retry in
            # degrading order to preserve as much information as possible:
            #   1st retry: sample_weight only (drop ES-specific keys)
            #   2nd retry: bare fit (no kwargs at all)
            _sw = fit_kwargs.get("sample_weight")
            try:
                if _sw is not None:
                    model_clone.fit(X, y, sample_weight=_sw)
                else:
                    model_clone.fit(X, y)
            except TypeError:
                model_clone.fit(X, y)
        fitted_models.append((name, model_clone))

    return oof, fitted_models


def _compute_base_weights(
    fitted_models: List[Tuple[str, Any]],
    X_val: np.ndarray,
    y_val: np.ndarray,
    classes: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """Compute weights based on inverse log-loss on validation.

    Uses the global `classes` array for log_loss labels so that models
    trained on folds missing a rare class are still evaluated correctly
    against the full label set.
    """
    weights = {}
    for name, model in fitted_models:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model.predict_proba(X_val)
            # Use global classes when provided to handle missing classes in model
            labels = classes if classes is not None else model.classes_
            ll = log_loss(y_val, proba, labels=labels)
            weights[name] = 1.0 / max(ll, 0.01)
        except Exception:
            weights[name] = 1.0
    return weights


def _fit_temperature_scaling(
    proba: np.ndarray,
    y_true: np.ndarray,
    classes: np.ndarray,
    use_class_bias: bool = False,
    min_samples: int = 30,
) -> dict | None:
    """
    Fit temperature scaling (+ optional per-class bias) on held-out probabilities.

    Returns dict {"T": float, "bias": list|None, "nll": float} or None on failure.
    """
    from scipy.optimize import minimize
    from scipy.special import softmax as scipy_softmax

    if len(y_true) < min_samples:
        return None

    n_classes = len(classes)
    class_to_idx = {str(c): i for i, c in enumerate(classes)}
    y_onehot = np.zeros((len(y_true), n_classes))
    for i, y in enumerate(y_true):
        idx = class_to_idx.get(str(y))
        if idx is not None:
            y_onehot[i, idx] = 1

    log_proba = np.log(np.clip(proba, 1e-9, 1.0))

    def nll(params: np.ndarray) -> float:
        T = params[0]
        if T <= 0:
            return 1e9
        bias = params[1:] if use_class_bias else np.zeros(n_classes)
        scaled_logits = log_proba / T + bias
        cal_proba = scipy_softmax(scaled_logits, axis=1)
        return -float(np.mean(np.sum(y_onehot * np.log(np.clip(cal_proba, 1e-9, 1.0)), axis=1)))

    n_params = 1 + (n_classes if use_class_bias else 0)
    x0 = np.ones(n_params)
    bounds = [(0.1, 5.0)] + ([(-2.0, 2.0)] * (n_classes if use_class_bias else 0))

    try:
        result = minimize(nll, x0, method="L-BFGS-B", bounds=bounds,
                         options={"maxiter": 500, "ftol": 1e-7})
        T_opt = float(result.x[0])
        bias_opt = result.x[1:].tolist() if use_class_bias else None
        return {"T": T_opt, "bias": bias_opt, "nll": float(result.fun)}
    except Exception as exc:
        logger.warning("Temperature scaling fit failed: %s", exc)
        return None


def _apply_temperature_scaling(
    proba: np.ndarray,
    ts_params: dict,
    classes: np.ndarray,
) -> np.ndarray:
    """Apply temperature scaling (+ optional bias) to a probability matrix."""
    from scipy.special import softmax as scipy_softmax
    T = ts_params.get("T", 1.0)
    bias = ts_params.get("bias")
    log_proba = np.log(np.clip(proba, 1e-9, 1.0))
    scaled = log_proba / T
    if bias is not None:
        scaled = scaled + np.array(bias)
    return scipy_softmax(scaled, axis=1)


def _train_calibrators(
    fitted_models: List[Tuple[str, Any]],
    meta_model: Any,
    X_val: np.ndarray,
    y_val: np.ndarray,
    classes: np.ndarray,
    min_samples: int = 50,
    base_weights: Optional[Dict[str, float]] = None,
    tier: str = "MEDIUM",
) -> Dict[str, Any]:
    """
    Train calibrators on the validation set.

    - Binary targets: IsotonicRegression per-class (P(True) only, P(False) derived).
    - Multiclass targets: temperature scaling (with per-class bias for MEDIUM/LARGE).
    - TINY tier or insufficient samples: returns {}.

    Perché isotonic invece di Platt (sigmoid)?
    - Isotonic è non-parametrico: non assume forma della curva di calibrazione.
    - Appropriato quando la curva prevista→reale non è monotona lineare.
    - Richiede più dati (min ~50 per classe) ma è più flessibile.
    """
    if tier == "TINY" or len(y_val) < min_samples:
        return {}

    class_strs = [str(c) for c in classes]
    n_classes = len(class_strs)

    # Compute ensemble probabilities on val set
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
            meta_classes = [str(c) for c in getattr(meta_model, "classes_", class_strs)]
            # Align to class_strs
            proba_aligned = np.zeros((X_val.shape[0], n_classes))
            for i, c in enumerate(class_strs):
                if c in meta_classes:
                    idx_c = meta_classes.index(c)
                    proba_aligned[:, i] = ensemble_proba[:, idx_c]
        except Exception as exc:
            logger.warning("calibration (meta model) failed: %s", exc)
            return {}
    else:
        # Weighted average of base models
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
            logger.warning("calibration (weighted avg) failed: %s", exc)
            return {}

    y_val_str = np.array([str(v) for v in y_val])

    if n_classes == 2:
        # Binary: isotonic on P(True), derive P(False) = 1 - P(True)
        calibrators: Dict[str, Any] = {}
        for i, c in enumerate(class_strs):
            y_binary = (y_val_str == c).astype(float)
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
    else:
        # Multiclass: temperature scaling
        use_bias = tier in ("MEDIUM", "LARGE")
        ts_params = _fit_temperature_scaling(
            proba_aligned, y_val_str, np.array(class_strs),
            use_class_bias=use_bias,
        )
        if ts_params is None:
            return {}
        class_strs_out = [str(c) for c in classes]
        return {"__temperature_scaling__": ts_params, "__classes__": class_strs_out}


# Keep old name as alias for backward compatibility
_train_isotonic_calibrators = _train_calibrators


def _build_mlp_meta(n_input: int, n_classes: int, dropout_rate: float = 0.3) -> Any:
    """Build a small MLP meta-learner using Keras/TensorFlow."""
    try:
        import tensorflow as tf
        tf.get_logger().setLevel("ERROR")
        import keras
        from keras import layers
        model = keras.Sequential([
            layers.Input(shape=(n_input,)),
            layers.Dense(32, activation="relu",
                        kernel_regularizer=keras.regularizers.l2(0.01)),
            layers.Dropout(dropout_rate),
            layers.Dense(n_classes, activation="softmax"),
        ])
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.001),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        return model
    except Exception:
        return None


class _KerasMetaWrapper:
    """Pickle-safe wrapper around a Keras MLP meta-learner."""

    def __init__(self, n_input: int, n_classes: int, class_labels: list):
        self._n_input = n_input
        self._n_classes = n_classes
        self.classes_ = np.array(class_labels)
        self._model = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_KerasMetaWrapper":
        try:
            import keras
            self._model = _build_mlp_meta(self._n_input, self._n_classes)
            if self._model is None:
                raise RuntimeError("Keras not available")
            label_to_idx = {str(c): i for i, c in enumerate(self.classes_)}
            y_int = np.array([label_to_idx.get(str(v), 0) for v in y])
            from sklearn.model_selection import StratifiedShuffleSplit
            sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
            tr_idx, v_idx = next(sss.split(X, y_int))
            es = keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=15, restore_best_weights=True, verbose=0
            )
            self._model.fit(
                X[tr_idx], y_int[tr_idx],
                validation_data=(X[v_idx], y_int[v_idx]),
                epochs=200,
                batch_size=min(32, max(8, len(tr_idx) // 10)),
                callbacks=[es],
                verbose=0,
            )
        except Exception as exc:
            logger.warning("MLP meta-learner fit failed: %s — falling back to None", exc)
            self._model = None
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            # Graceful degradation: return uniform distribution so the caller
            # (build_ensemble / predict_ensemble) can keep running.  The
            # weighted-average fallback in build_ensemble will take over
            # because meta_model._model is checked and set to None there.
            logger.warning(
                "_KerasMetaWrapper.predict_proba called with _model=None "
                "(TF unavailable or weights failed to restore) — "
                "returning uniform distribution as fallback."
            )
            return np.full((len(X), self._n_classes), 1.0 / self._n_classes)
        proba = self._model.predict(X, verbose=0)
        proba = np.clip(proba, 1e-9, 1.0)
        return proba / proba.sum(axis=1, keepdims=True)

    def predict(self, X: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(X)
        idx = np.argmax(proba, axis=1)
        return np.array([str(self.classes_[i]) for i in idx])

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        if self._model is not None:
            try:
                state["_keras_weights"] = [w.tolist() for w in self._model.get_weights()]
            except Exception:
                state["_keras_weights"] = None
        else:
            state["_keras_weights"] = None
        state["_model"] = None
        return state

    def __setstate__(self, state: dict) -> None:
        weights = state.pop("_keras_weights", None)
        self.__dict__.update(state)
        if weights is not None and _TENSORFLOW_AVAILABLE:
            try:
                self._model = _build_mlp_meta(self._n_input, self._n_classes)
                if self._model is not None:
                    self._model.set_weights([np.array(w) for w in weights])
            except Exception as _exc:
                logger.warning(
                    "_KerasMetaWrapper: ripristino pesi fallito (%s) — "
                    "inferenza ricadrà su weighted average.",
                    _exc,
                )
                self._model = None


def build_ensemble(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    sample_weights: Optional[np.ndarray] = None,
    feature_cols: Optional[List[str]] = None,
    feature_medians: Optional[Dict[str, float]] = None,
    train_dates: Optional[pd.Series] = None,
    optuna_params: dict | None = None,
    tier: str | None = None,
    n_jobs: int = -1,
) -> EnsemblePayload:
    """
    Train a stacking ensemble and return the full payload.

    Args:
        ...
        n_jobs: parallelism hint forwarded to _build_base_models.  When
            multiple targets are trained in parallel (ThreadPoolExecutor),
            pass ``max(1, cpu_count // parallel_workers)`` to avoid
            CPU over-subscription.  Default -1 = all cores.

    Steps:
    1. Determine league tier
    2. Standardize features for LogReg
    3. Generate OOF predictions via walk-forward CV on training
    4. Train meta-learner (LogReg or MLP for LARGE tier) on OOF
    5. Compute base model weights on validation
    6. Calibrate ensemble probabilities
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

    # Determine league tier
    if tier is None:
        tier = _get_league_tier(len(y_tr_np))

    # n_splits based on tier
    n_splits_map = {"TINY": 3, "SMALL": 5, "MEDIUM": 5, "LARGE": 7}
    n_splits_for_wf = n_splits_map.get(tier, 5)

    # Build walk-forward (temporal) splits for OOF within training.
    # StratifiedKFold causes temporal leakage — fold 1 trains on future data.
    # walk_forward_splits uses expanding windows with purge gaps.
    n_tr = len(y_tr_np)

    # TINY: force weighted average as meta-learner (no OOF)
    if tier == "TINY":
        splits: List[Tuple[np.ndarray, np.ndarray]] = []
    else:
        splits = []
        if train_dates is not None and len(train_dates) == n_tr:
            combined_for_wf = pd.DataFrame(X_tr_np)
            combined_for_wf["fixture_date"] = train_dates.values
            wf_splits = walk_forward_splits(
                combined_for_wf,
                n_splits=n_splits_for_wf,
                purge_days=30,
                min_train_rows=50,
            )
            splits = wf_splits if wf_splits else []

        if not splits:
            # Fallback: simple 70/30 temporal split when walk_forward_splits unavailable.
            cut = max(20, int(n_tr * 0.7))
            if cut < n_tr:
                splits = [(np.arange(0, cut), np.arange(cut, n_tr))]
            else:
                # Dataset too small for any split — use weighted average fallback.
                splits = []

    # Scale for LogReg
    scaler = StandardScaler()
    X_tr_scaled = scaler.fit_transform(X_tr_np)
    X_val_scaled = scaler.transform(X_val_np)

    # Compute imbalance ratio for conditional class_weight / SMOTE
    _class_counts = pd.Series(y_tr_np).value_counts()
    _imbalance_ratio = float(_class_counts.min() / _class_counts.max()) if len(_class_counts) > 1 else 1.0

    # Extract Optuna-tuned params if provided
    _xgb_params = (optuna_params or {}).get("xgb", None)
    _lgb_params = (optuna_params or {}).get("lgb", None)
    _rf_params = (optuna_params or {}).get("rf", None)

    # Build base models
    base_templates = _build_base_models(
        n_classes,
        n_samples=len(y_tr_np),
        imbalance_ratio=_imbalance_ratio,
        tier=tier,
        xgb_params=_xgb_params,
        lgb_params=_lgb_params,
        rf_params=_rf_params,
        n_jobs=n_jobs,
    )

    # SMOTE params (only for MEDIUM/LARGE with genuine imbalance)
    smote_params: dict | None = None
    if _imbalance_ratio < 0.35 and tier in ("MEDIUM", "LARGE") and _IMBLEARN_AVAILABLE:
        smote_params = {"imbalance_ratio": _imbalance_ratio, "tier": tier}

    # Generate OOF probabilities — pass pre-computed classes so OOF matrix
    # width matches meta-learner input (fixes mismatch when val has rare classes
    # absent from train, e.g. target_ht_ft with many outcome combinations).
    # X_val_scaled / y_val_np are passed for LightGBM early stopping on the
    # final full-data fit only (never inside OOF folds).
    oof, fitted_models = _generate_oof_probas(
        base_templates, X_tr_scaled, y_tr_np, splits, sample_weights,
        classes=classes,
        smote_params=smote_params,
        X_val_for_es=X_val_scaled,
        y_val_for_es=y_val_np,
    )

    # Handle NaN in OOF (rows not covered by any fold)
    nan_mask = np.isnan(oof).any(axis=1)
    oof_clean = oof[~nan_mask]
    y_oof = y_tr_np[~nan_mask]

    # Train meta-learner on OOF predictions.
    # For LARGE tier with enough data: MLP meta-learner.
    # Otherwise: LogisticRegression stacker.
    # If OOF is empty: weighted average fallback (meta_model = None).
    _use_mlp = (
        tier == "LARGE"
        and len(oof_clean) >= 400
        and _TENSORFLOW_AVAILABLE
    )

    meta_model: Any = None
    if len(oof_clean) >= 20 and oof_clean.shape[1] > 0:
        if _use_mlp:
            meta_model = _KerasMetaWrapper(
                n_input=oof_clean.shape[1],
                n_classes=n_classes,
                class_labels=[str(c) for c in classes],
            )
            try:
                meta_model.fit(oof_clean, y_oof)
                if meta_model._model is None:
                    meta_model = None
            except Exception:
                meta_model = None

        if not _use_mlp or meta_model is None:
            meta_base = LogisticRegression(max_iter=2000, C=0.5, random_state=0)
            try:
                meta_base.fit(oof_clean, y_oof)
                meta_model = meta_base
            except Exception:
                meta_model = None
    else:
        # Fallback: simple weighted average (meta_model = None)
        meta_model = None

    # Compute base weights on validation (pass global classes for correct log_loss)
    base_weights = _compute_base_weights(fitted_models, X_val_scaled, y_val_np, classes=classes)

    # Compute ensemble metrics on validation
    metrics = _evaluate_ensemble(
        fitted_models, meta_model, X_val_scaled, y_val_np, classes
    )

    class_labels = [str(c) for c in classes]

    # Train calibrators on validation set.
    # Binary: isotonic. Multiclass: temperature scaling.
    # Requires min 50 val samples; falls back to empty dict for small leagues.
    isotonic_calibrators = _train_calibrators(
        fitted_models, meta_model, X_val_scaled, y_val_np, classes,
        base_weights=base_weights,
        tier=tier,
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
    Accepts exactly one row. For batch predictions call in a loop.
    """
    if len(X) != 1:
        raise ValueError(
            f"predict_ensemble accetta esattamente 1 riga, ricevute {len(X)}. "
            "Per predizioni batch, chiama predict_ensemble in un loop."
        )

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

    def _weighted_avg_fallback() -> Dict[str, float]:
        """Compute weighted average of base models as fallback."""
        total_weight = sum(payload.base_weights.values()) or 1.0
        res: Dict[str, float] = {c: 0.0 for c in classes}
        for name, model in payload.base_models:
            w = payload.base_weights.get(name, 1.0) / total_weight
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model.predict_proba(X_scaled)
            model_classes = [str(c) for c in model.classes_]
            for i, c in enumerate(classes):
                if c in model_classes:
                    idx_c = model_classes.index(c)
                    res[c] += w * float(proba[0][idx_c])
        return res

    # For _KerasMetaWrapper loaded from disk with TF unavailable, _model is None
    # but the wrapper instance itself is not None.  Detect this case and route
    # directly to the weighted-average fallback instead of returning a
    # (correct but useless) uniform distribution.
    _effective_meta = payload.meta_model
    if isinstance(_effective_meta, _KerasMetaWrapper) and _effective_meta._model is None:
        logger.warning(
            "predict_ensemble: _KerasMetaWrapper._model is None (TF unavailable "
            "or weights failed to restore) — falling back to weighted average."
        )
        _effective_meta = None

    if _effective_meta is not None:
        try:
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
                final_proba = _effective_meta.predict_proba(meta_input)

            # Align meta output to classes
            meta_classes = [str(c) for c in getattr(_effective_meta, "classes_", classes)]
            result: Dict[str, float] = {}
            for i, c in enumerate(classes):
                if c in meta_classes:
                    idx_c = meta_classes.index(c)
                    result[c] = float(final_proba[0][idx_c])
                else:
                    result[c] = 0.0
        except Exception as _meta_exc:
            logger.warning(
                "Meta-learner predict_proba failed (%s), using weighted average", _meta_exc
            )
            result = _weighted_avg_fallback()
    else:
        # Fallback: weighted average of base models
        result = _weighted_avg_fallback()

    # Apply calibration if available.
    #
    # For binary {True, False}: calibrate only P(True) via isotonic, derive
    # P(False) = 1 - P(True). This preserves the guarantee:
    #   iso_True(p) ≈ P(outcome=True | pred_prob=p)
    # which joint renormalisation would destroy.
    #
    # For multiclass: temperature scaling (stored as __temperature_scaling__ key).
    # For legacy multiclass isotonic (if present): per-class isotonic + renormalise.
    if getattr(payload, "isotonic_calibrators", None):
        cals = payload.isotonic_calibrators

        # --- Temperature scaling path (multiclass) ---
        if "__temperature_scaling__" in cals:
            ts_params = cals["__temperature_scaling__"]
            ts_classes = np.array(cals.get("__classes__", list(result.keys())))
            proba_arr = np.array([[result.get(c, 0.0) for c in ts_classes]])
            try:
                cal_arr = _apply_temperature_scaling(proba_arr, ts_params, ts_classes)
                result = {c: float(cal_arr[0, i]) for i, c in enumerate(ts_classes)}
            except Exception as exc:
                logger.warning("Temperature scaling apply failed: %s", exc)
                # keep uncalibrated result, just normalise
                total = sum(result.values()) or 1.0
                result = {c: v / total for c, v in result.items()}

        else:
            # --- Isotonic path (binary or legacy multiclass) ---
            # Case-insensitive detection of binary {True, False} targets.
            # HIGH fix: comparing with {"True", "False"} would silently miss labels
            # stored as "true"/"TRUE" (string-typed Series from CSV loaders).
            classes_lower = {c.lower(): c for c in result.keys()}
            if set(classes_lower.keys()) == {"true", "false"}:
                true_key = classes_lower["true"]
                false_key = classes_lower["false"]
                iso_true = cals.get(true_key)
                if iso_true is not None:
                    p_true_cal = float(np.clip(iso_true.predict([result[true_key]])[0], 0.001, 0.999))
                    p_false_cal = 1.0 - p_true_cal
                    # MEDIUM fix: renormalise to guarantee exact sum=1.0 despite
                    # IEEE 754 floating-point rounding.
                    total_cal = p_true_cal + p_false_cal
                    result = {true_key: p_true_cal / total_cal, false_key: p_false_cal / total_cal}
                else:
                    # iso_true absent: try iso_false as a symmetric fallback.
                    iso_false = cals.get(false_key)
                    if iso_false is not None:
                        p_false_cal = float(np.clip(iso_false.predict([result[false_key]])[0], 0.001, 0.999))
                        p_true_cal = 1.0 - p_false_cal
                        total_cal = p_true_cal + p_false_cal
                        result = {true_key: p_true_cal / total_cal, false_key: p_false_cal / total_cal}
                    else:
                        # Neither calibrator available: normalise uncalibrated values.
                        logger.debug(
                            "predict_ensemble: no isotonic calibrator for binary target "
                            "(%s / %s); returning normalised uncalibrated probabilities.",
                            true_key, false_key,
                        )
                        clipped = {c: float(np.clip(v, 0.001, 0.999)) for c, v in result.items()}
                        total = sum(clipped.values()) or 1.0
                        result = {c: v / total for c, v in clipped.items()}
            else:
                # Multiclass legacy isotonic: apply per-class then renormalise.
                calibrated = {}
                for c in result:
                    iso = cals.get(c)
                    if iso is not None:
                        calibrated[c] = float(np.clip(iso.predict([result[c]])[0], 0.001, 0.999))
                    else:
                        calibrated[c] = result[c]
                total = sum(calibrated.values()) or 1.0
                result = {c: v / total for c, v in calibrated.items()}
    else:
        # No calibration: normalise raw values.
        total = sum(result.values()) or 1.0
        result = {c: v / total for c, v in result.items()}

    return result


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
            ll = log_loss(y_val, proba, labels=classes)
            acc = float((model.predict(X_val) == y_val).mean())
            metrics[f"{name}_logloss"] = round(ll, 4)
            metrics[f"{name}_accuracy"] = round(acc, 4)
        except Exception:
            pass

    # Ensemble metrics (via meta-learner or weighted average).
    # Apply the same _KerasMetaWrapper guard used in predict_ensemble:
    # a deserialized wrapper with _model=None would emit a uniform
    # distribution, producing artificially low log-loss and high accuracy.
    _eval_meta = meta_model
    if isinstance(_eval_meta, _KerasMetaWrapper) and _eval_meta._model is None:
        logger.warning(
            "_evaluate_ensemble: _KerasMetaWrapper._model is None — "
            "skipping ensemble metrics to avoid contamination."
        )
        _eval_meta = None

    if _eval_meta is not None:
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
                final_proba = _eval_meta.predict_proba(meta_input)
            y_str = np.array([str(v) for v in y_val])
            meta_classes_list = [str(c) for c in getattr(_eval_meta, "classes_", classes)]
            meta_ll = log_loss(y_str, final_proba, labels=meta_classes_list)
            try:
                meta_preds = _eval_meta.predict(meta_input)
            except Exception:
                meta_preds = np.array(meta_classes_list)[np.argmax(final_proba, axis=1)]
            meta_acc = float((meta_preds == y_str).mean())
            metrics["ensemble_logloss"] = round(meta_ll, 4)
            metrics["ensemble_accuracy"] = round(meta_acc, 4)
        except Exception:
            pass

    return metrics
