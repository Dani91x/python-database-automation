from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, train_test_split

from ai_engine.preprocessing.dataset import DatasetPreprocessor


def _temporal_train_test_split(df: pd.DataFrame, test_size: float = 0.2):
    """
    Split a DataFrame temporally: first (1-test_size) fraction as train,
    last test_size fraction as test.  If 'fixture_date' column is present,
    sort by it first; otherwise use existing row order.

    Replaces random train_test_split(shuffle=True) which causes data leakage
    on time-series data: future rows can end up in training, past rows in test.
    """
    if "fixture_date" in df.columns:
        df = df.sort_values("fixture_date").reset_index(drop=True)
    cut = int(len(df) * (1.0 - test_size))
    cut = max(cut, 1)
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


class Trainer:
    def __init__(self, fit_test_size: float = 0.2, k_folds: int = 5):
        self._preprocessor = DatasetPreprocessor()
        self._fit_test_size = fit_test_size
        self._k_folds = k_folds

    def fit(
        self,
        df: pd.DataFrame,
        target_col: str,
        model_cls,
        model_params: dict,
        normalizer: str | None = None,
        sampler: str | None = None,
    ) -> Dict[str, float]:
        clean = df.dropna(subset=[target_col]).copy()
        # Use temporal split instead of random shuffle to avoid data leakage:
        # with shuffle=True, the model can train on 2025 matches and validate
        # on 2024 matches, making rolling features from the future visible.
        x_train, x_test = _temporal_train_test_split(clean, test_size=self._fit_test_size)
        y_train = x_train[target_col]
        y_test = x_test[target_col]

        x_tr, y_tr, norm, samp = self._preprocessor.preprocess_dataset(
            df=x_train,
            target_col=target_col,
            fit_normalizer=True,
            normalizer=normalizer,
            sampler=sampler,
        )
        x_te, y_te, _, _ = self._preprocessor.preprocess_dataset(
            df=x_test,
            target_col=target_col,
            fit_normalizer=False,
            normalizer=norm,
            sampler=None,
        )

        model = model_cls(**model_params)
        model.fit(x_tr, y_tr)
        preds = model.predict(x_te)

        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

        return {
            "accuracy": float(accuracy_score(y_te, preds)),
            "f1": float(f1_score(y_te, preds, average="macro", zero_division=0.0)),
            "precision": float(precision_score(y_te, preds, average="macro", zero_division=0.0)),
            "recall": float(recall_score(y_te, preds, average="macro", zero_division=0.0)),
        }

    def cross_validate(
        self,
        df: pd.DataFrame,
        target_col: str,
        model_cls,
        model_params: dict,
        normalizer: str | None = None,
    ) -> Dict[str, float]:
        clean = df.dropna(subset=[target_col]).copy()
        x = np.zeros(shape=clean.shape[0])
        y = clean[target_col].to_numpy()

        # Temporal CV: expanding-window walk-forward splits.
        # Training always uses data from the beginning to the fold boundary,
        # validation uses the next chunk of data.
        # StratifiedKFold(shuffle=True) was wrong for time-series data because
        # it could place future rows into training and past rows into validation.
        n = len(clean)
        fold_size = max(n // self._k_folds, 1)
        # Burn the first fold as warm-up training data: start validation from
        # fold index 1 so every fold has at least fold_size rows for training.
        cv_splits = []
        for k in range(1, self._k_folds):
            val_start = k * fold_size
            val_end = val_start + fold_size if k < self._k_folds - 1 else n
            if val_start >= n or val_start < 5:
                continue
            train_ids = np.arange(0, val_start)
            val_ids = np.arange(val_start, min(val_end, n))
            if len(val_ids) < 2:
                continue
            cv_splits.append((train_ids, val_ids))
        if not cv_splits:
            # Fallback: single 70/30 temporal split
            cut = max(int(n * 0.7), 1)
            cv_splits = [(np.arange(0, cut), np.arange(cut, n))]
        cv = iter(cv_splits)
        scores: List[Dict[str, float]] = []

        for train_ids, test_ids in cv:
            df_train = clean.iloc[train_ids]
            df_test = clean.iloc[test_ids]

            x_tr, y_tr, norm, _ = self._preprocessor.preprocess_dataset(
                df=df_train,
                target_col=target_col,
                fit_normalizer=True,
                normalizer=normalizer,
                sampler=None,
            )
            x_te, y_te, _, _ = self._preprocessor.preprocess_dataset(
                df=df_test,
                target_col=target_col,
                fit_normalizer=False,
                normalizer=norm,
                sampler=None,
            )

            model = model_cls(**model_params)
            model.fit(x_tr, y_tr)
            preds = model.predict(x_te)

            from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

            scores.append(
                {
                    "accuracy": float(accuracy_score(y_te, preds)),
                    "f1": float(f1_score(y_te, preds, average="macro", zero_division=0.0)),
                    "precision": float(precision_score(y_te, preds, average="macro", zero_division=0.0)),
                    "recall": float(recall_score(y_te, preds, average="macro", zero_division=0.0)),
                }
            )

        if not scores:
            return {"accuracy": 0.0, "f1": 0.0, "precision": 0.0, "recall": 0.0}
        return {k: float(np.mean([s[k] for s in scores])) for k in scores[0].keys()}
