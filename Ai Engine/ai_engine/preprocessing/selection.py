"""
Feature selection utilities: variance filter, correlation filter,
mutual information ranking, and a combined pipeline.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_selection import VarianceThreshold, mutual_info_classif


def variance_threshold(df: pd.DataFrame, threshold: float = 0.0) -> List[str]:
    """Remove features with variance below threshold."""
    X = df.select_dtypes(include=["number", "bool"]).copy()
    if X.empty:
        return []
    selector = VarianceThreshold(threshold=threshold)
    selector.fit(X)
    return X.columns[selector.get_support(indices=True)].tolist()


def top_k_by_variance(df: pd.DataFrame, k: int = 50) -> List[str]:
    """Return top-k features by variance."""
    X = df.select_dtypes(include=["number", "bool"]).copy()
    vars_ = X.var(numeric_only=True).sort_values(ascending=False)
    return vars_.head(k).index.tolist()


def drop_correlated(
    df: pd.DataFrame, threshold: float = 0.95
) -> List[str]:
    """
    Drop features with pairwise correlation above threshold.
    Keeps the feature with higher variance in each correlated pair.
    Returns the list of columns to KEEP.
    """
    X = df.select_dtypes(include=["number", "bool"]).copy()
    if X.shape[1] < 2:
        return list(X.columns)

    corr = X.corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))

    to_drop = set()
    for col in upper.columns:
        correlated = upper.index[upper[col] > threshold].tolist()
        for c in correlated:
            # Drop the one with lower variance
            if X[col].var() >= X[c].var():
                to_drop.add(c)
            else:
                to_drop.add(col)

    return [c for c in X.columns if c not in to_drop]


def select_by_mutual_info(
    X: pd.DataFrame,
    y: pd.Series,
    k: int = 60,
) -> List[str]:
    """
    Select top-k features by mutual information with target.
    Works for both classification (discrete y) and handles
    multiclass targets automatically.
    """
    X_num = X.select_dtypes(include=["number", "bool"]).copy()
    if X_num.empty or len(y.dropna()) < 10:
        return list(X_num.columns)

    X_filled = X_num.fillna(X_num.median())

    # Encode target if string/object
    y_enc = y.copy()
    if y_enc.dtype == object or y_enc.dtype.name == "category":
        y_enc = y_enc.astype("category").cat.codes

    y_enc = y_enc.fillna(-1).astype(int)

    try:
        mi = mutual_info_classif(
            X_filled, y_enc, discrete_features=False, random_state=0
        )
    except Exception:
        return list(X_num.columns)

    mi_series = pd.Series(mi, index=X_num.columns).sort_values(ascending=False)
    return mi_series.head(k).index.tolist()


def apply_feature_selection(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    correlation_threshold: float = 0.95,
    mi_top_k: int = 60,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """
    Combined feature selection pipeline:
    1. Remove zero-variance features
    2. Remove highly correlated features (>threshold)
    3. Select top-K by mutual information

    Returns (X_train_selected, X_val_selected, selected_columns).
    """
    # Step 1: Variance filter
    var_cols = variance_threshold(X_train, threshold=0.0)
    X_tr = X_train[var_cols].copy()

    # Step 2: Correlation filter
    keep_cols = drop_correlated(X_tr, threshold=correlation_threshold)
    X_tr = X_tr[keep_cols].copy()

    # Step 3: Mutual information (only if we have more features than k)
    if len(keep_cols) > mi_top_k:
        mi_cols = select_by_mutual_info(X_tr, y_train, k=mi_top_k)
        X_tr = X_tr[mi_cols].copy()
        final_cols = mi_cols
    else:
        final_cols = keep_cols

    X_v = X_val.reindex(columns=final_cols).copy()
    return X_tr, X_v, final_cols
