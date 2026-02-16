from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

try:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, log_loss
    from sklearn.model_selection import StratifiedKFold, train_test_split
    from sklearn.preprocessing import StandardScaler
except Exception:  # pragma: no cover
    CalibratedClassifierCV = None  # type: ignore
    GradientBoostingClassifier = None  # type: ignore
    RandomForestClassifier = None  # type: ignore
    LogisticRegression = None  # type: ignore
    accuracy_score = None  # type: ignore
    log_loss = None  # type: ignore
    StratifiedKFold = None  # type: ignore
    train_test_split = None  # type: ignore
    StandardScaler = None  # type: ignore


@dataclass
class ModelResult:
    model_name: str
    pred_labels: List[Any]
    pred_probas: List[Dict[str, float]]
    train_accuracy: float | None
    cv_logloss: float | None
    weight: float | None


def _is_binary(target: pd.Series) -> bool:
    vals = target.dropna().unique()
    return len(vals) <= 2


def _prepare_features(
    train_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    target_col: str,
    drop_cols: List[str],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str]]:
    df = train_df.dropna(subset=[target_col]).copy()
    y = df[target_col].copy()

    X = df.drop(columns=drop_cols + [target_col], errors="ignore")
    X = X.select_dtypes(include=["number", "bool"]).copy()

    X_pred = pred_df.drop(columns=drop_cols, errors="ignore")
    X_pred = X_pred.select_dtypes(include=["number", "bool"]).copy()

    # align columns
    common_cols = [c for c in X.columns if c in X_pred.columns]
    X = X[common_cols].copy()
    X_pred = X_pred[common_cols].copy()

    # fill missing with train medians
    medians = X.median(numeric_only=True)
    X = X.fillna(medians)
    X_pred = X_pred.fillna(medians)

    # scale
    if StandardScaler is not None:
        scaler = StandardScaler()
        X = scaler.fit_transform(X)
        X_pred = scaler.transform(X_pred)

    # encode target
    if y.dtype == "bool":
        y = y.astype(int)

    return np.asarray(X), np.asarray(y), np.asarray(X_pred), common_cols


def _build_models(is_binary: bool) -> List[Tuple[str, Any]]:
    models: List[Tuple[str, Any]] = []
    if LogisticRegression is not None:
        models.append(("logreg", LogisticRegression(max_iter=2000, n_jobs=None, multi_class="auto", class_weight="balanced")))
    if RandomForestClassifier is not None:
        models.append(("rf", RandomForestClassifier(n_estimators=400, random_state=0, n_jobs=-1, class_weight="balanced_subsample")))
    if GradientBoostingClassifier is not None:
        models.append(("gb", GradientBoostingClassifier(random_state=0)))
    return models


def _cv_logloss(model: Any, X: np.ndarray, y: np.ndarray) -> float | None:
    if StratifiedKFold is None or log_loss is None:
        return None
    if len(np.unique(y)) < 2:
        return None
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=0)
    losses = []
    for train_idx, test_idx in cv.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)
        try:
            losses.append(log_loss(y_test, proba))
        except Exception:
            continue
    if not losses:
        return None
    return float(np.mean(losses))


def train_and_predict(
    train_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    target_col: str,
    drop_cols: List[str],
    test_size: float = 0.2,
) -> List[ModelResult]:
    if train_df.empty or pred_df.empty:
        return []

    X, y, X_pred, _ = _prepare_features(train_df, pred_df, target_col, drop_cols)
    if X.size == 0 or X_pred.size == 0:
        return []

    is_binary = _is_binary(pd.Series(y))
    models = _build_models(is_binary)
    outputs: List[ModelResult] = []

    for name, model in models:
        try:
            cv_ll = _cv_logloss(model, X, y)
            if train_test_split is not None:
                X_train, X_val, y_train, y_val = train_test_split(
                    X, y, test_size=test_size, random_state=0, stratify=y if len(np.unique(y)) > 1 else None
                )
                model.fit(X_train, y_train)
                y_pred = model.predict(X_val)
                acc = accuracy_score(y_val, y_pred) if accuracy_score is not None else None
            else:
                model.fit(X, y)
                acc = None

            # Calibrate probabilities for better reliability
            if CalibratedClassifierCV is not None:
                try:
                    calib = CalibratedClassifierCV(model, method="sigmoid", cv=3)
                    calib.fit(X_train if train_test_split is not None else X, y_train if train_test_split is not None else y)
                    proba = calib.predict_proba(X_pred)
                    classes = [str(c) for c in calib.classes_]
                except Exception:
                    proba = model.predict_proba(X_pred)
                    classes = [str(c) for c in model.classes_]
            else:
                proba = model.predict_proba(X_pred)
                classes = [str(c) for c in model.classes_]

            # Weight: inverse logloss if available, else accuracy
            if cv_ll is not None and cv_ll > 0:
                weight = 1.0 / cv_ll
            elif acc is not None:
                weight = float(acc)
            else:
                weight = None

            pred_labels = []
            pred_probas = []
            for i in range(proba.shape[0]):
                pred_idx = int(np.argmax(proba[i]))
                pred_label = classes[pred_idx]
                prob_map = {classes[j]: float(proba[i][j]) for j in range(len(classes))}
                pred_labels.append(pred_label)
                pred_probas.append(prob_map)

            outputs.append(
                ModelResult(
                    model_name=name,
                    pred_labels=pred_labels,
                    pred_probas=pred_probas,
                    train_accuracy=acc,
                    cv_logloss=cv_ll,
                    weight=weight,
                )
            )
        except Exception:
            continue

    return outputs
