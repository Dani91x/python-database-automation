from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, train_test_split

from ai_engine.preprocessing.dataset import DatasetPreprocessor


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
        x_train, x_test, y_train, y_test = train_test_split(
            clean, clean[target_col], test_size=self._fit_test_size, random_state=0, stratify=clean[target_col]
        )

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

        cv = StratifiedKFold(n_splits=self._k_folds, shuffle=True, random_state=0).split(x, y)
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

        return {k: float(np.mean([s[k] for s in scores])) for k in scores[0].keys()}
