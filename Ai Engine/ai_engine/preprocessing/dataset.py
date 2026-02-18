from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd
from sklearn.base import TransformerMixin
from sklearn.preprocessing import MaxAbsScaler, MinMaxScaler, StandardScaler, RobustScaler

try:
    from imblearn.under_sampling import RandomUnderSampler, NearMiss
    from imblearn.over_sampling import RandomOverSampler, SVMSMOTE
    from imblearn.combine import SMOTEENN
except Exception:  # pragma: no cover - optional dependency
    RandomUnderSampler = NearMiss = RandomOverSampler = SVMSMOTE = SMOTEENN = None


class DatasetPreprocessor:
    """DB-first preprocessing: numeric feature selection, normalization, optional sampling."""

    def __init__(self):
        self._columns_to_drop = [
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
        ]

    @staticmethod
    def _get_normalizer(normalizer_str: str) -> TransformerMixin | None:
        if normalizer_str == "None" or normalizer_str is None:
            return None
        if normalizer_str == "Min-Max":
            return MinMaxScaler()
        if normalizer_str == "Max-Abs":
            return MaxAbsScaler()
        if normalizer_str == "Standard":
            return StandardScaler()
        if normalizer_str == "Robust":
            return RobustScaler()
        raise NotImplementedError(f'Undefined normalizer: "{normalizer_str}"')

    @staticmethod
    def _get_sampler(sampler_str: str) -> TransformerMixin | None:
        if sampler_str == "None" or sampler_str is None:
            return None
        if RandomUnderSampler is None:
            raise RuntimeError("imblearn is not installed. Install imbalanced-learn to use samplers.")
        if sampler_str == "Random-UnderSampling":
            return RandomUnderSampler(random_state=0)
        if sampler_str == "Near-Miss":
            return NearMiss(version=3)
        if sampler_str == "Random-OverSampling":
            return RandomOverSampler(random_state=0)
        if sampler_str == "SVM-SMOTE":
            return SVMSMOTE(random_state=0)
        if sampler_str == "SMOTE-NN":
            return SMOTEENN(random_state=0)
        raise NotImplementedError(f'Undefined sampler: "{sampler_str}"')

    def preprocess_inputs(self, df: pd.DataFrame, return_dataframe: bool = False) -> np.ndarray | pd.DataFrame:
        x = df.drop(columns=self._columns_to_drop, errors="ignore")
        x = x.select_dtypes(include=["number", "bool"]).copy()
        return x if return_dataframe else x.to_numpy(dtype=np.float64)

    @staticmethod
    def preprocess_targets(df: pd.DataFrame, target_col: str) -> np.ndarray:
        return df[target_col].to_numpy()

    @staticmethod
    def normalize_inputs(
        x: np.ndarray,
        normalizer: TransformerMixin | None,
        fit: bool,
    ) -> Tuple[np.ndarray, TransformerMixin | None]:
        if normalizer is None:
            return x, None
        if fit:
            x = normalizer.fit_transform(x)
            return x, normalizer
        x = normalizer.transform(x)
        return x, normalizer

    @staticmethod
    def sample_inputs(
        x: np.ndarray,
        y: np.ndarray | None,
        sampler: TransformerMixin | None,
    ) -> Tuple[np.ndarray, np.ndarray | None, TransformerMixin | None]:
        if sampler is None:
            return x, y, None
        x, y = sampler.fit_resample(x, y)
        return x, y, sampler

    def preprocess_dataset(
        self,
        df: pd.DataFrame,
        target_col: str,
        fit_normalizer: bool,
        normalizer: TransformerMixin | str | None,
        sampler: TransformerMixin | str | None,
    ) -> Tuple[np.ndarray, np.ndarray, TransformerMixin | None, TransformerMixin | None]:
        if isinstance(normalizer, str):
            normalizer = self._get_normalizer(normalizer_str=normalizer)
        if isinstance(sampler, str):
            sampler = self._get_sampler(sampler_str=sampler)

        clean = df.dropna(subset=[target_col]).copy()
        x = self.preprocess_inputs(df=clean, return_dataframe=False)
        y = self.preprocess_targets(df=clean, target_col=target_col)
        x, normalizer = self.normalize_inputs(x=x, normalizer=normalizer, fit=fit_normalizer)
        x, y, sampler = self.sample_inputs(x=x, y=y, sampler=sampler)
        return x, y, normalizer, sampler
