from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from ai_engine.preprocessing.dataset import DatasetPreprocessor


def feature_importance(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    clean = df.dropna(subset=[target_col]).copy()
    pre = DatasetPreprocessor()
    x = pre.preprocess_inputs(clean, return_dataframe=True)
    y = pre.preprocess_targets(clean, target_col)
    clf = RandomForestClassifier(random_state=0, n_jobs=-1)
    clf.fit(x, y)
    return (
        pd.DataFrame({"feature": x.columns.tolist(), "importance": clf.feature_importances_})
        .sort_values(by="importance", ascending=False, ignore_index=True)
    )


def correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    clean = clean.select_dtypes(include=["number", "bool"]).copy()
    return clean.corr()


def variance_ranking(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.select_dtypes(include=["number", "bool"]).copy()
    variances = clean.var(numeric_only=True)
    return variances.sort_values(ascending=False).reset_index().rename(columns={"index": "feature", 0: "variance"})


def target_distribution(df: pd.DataFrame, target_col: str) -> Dict[str, float]:
    clean = df.dropna(subset=[target_col])
    counts = clean[target_col].value_counts(dropna=False)
    total = float(counts.sum()) if len(counts) else 1.0
    return {str(k): float(v) / total for k, v in counts.items()}
