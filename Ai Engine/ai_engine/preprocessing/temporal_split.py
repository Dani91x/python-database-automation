"""
Temporal train/validation splitting with purge gap.

In sports prediction, random splits cause data leakage because
form/window features encode information from nearby matches.
Temporal splits ensure the model never sees future data.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


def temporal_train_val_split(
    df: pd.DataFrame,
    val_ratio: float = 0.20,
    purge_days: int = 30,
    date_col: str = "fixture_date",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split a DataFrame chronologically.

    The last `val_ratio` fraction (by date) becomes validation.
    A purge gap of `purge_days` is removed from the end of training
    to prevent leakage from rolling/form features.

    Returns (train_df, val_df).
    """
    dfc = df.copy()
    dfc[date_col] = pd.to_datetime(dfc[date_col], errors="coerce")
    dfc = dfc.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)

    if dfc.empty:
        return dfc, dfc

    n = len(dfc)
    cutoff_idx = int(n * (1.0 - val_ratio))
    cutoff_idx = max(1, min(cutoff_idx, n - 1))

    cutoff_date = dfc.iloc[cutoff_idx][date_col]
    purge_start = cutoff_date - pd.Timedelta(days=purge_days)

    val_df = dfc[dfc[date_col] >= cutoff_date].copy()
    train_df = dfc[dfc[date_col] < purge_start].copy()

    return train_df, val_df


def walk_forward_splits(
    df: pd.DataFrame,
    n_splits: int = 3,
    purge_days: int = 30,
    min_train_rows: int = 50,
    date_col: str = "fixture_date",
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Generate walk-forward (expanding window) train/val index arrays.

    Each fold uses all data before the fold boundary as training
    (minus purge gap) and the fold window as validation.

    Returns list of (train_indices, val_indices) tuples.
    """
    dfc = df.copy()
    dfc[date_col] = pd.to_datetime(dfc[date_col], errors="coerce")
    dfc = dfc.dropna(subset=[date_col]).sort_values(date_col)

    if dfc.empty or len(dfc) < min_train_rows + 10:
        return []

    dates = dfc[date_col].values
    n = len(dates)

    # Divide the last 60% of data into n_splits folds for validation
    # The first 40% is always training for the first fold.
    val_start_pct = 0.40
    val_start_idx = int(n * val_start_pct)
    val_total = n - val_start_idx
    fold_size = max(val_total // n_splits, 10)

    splits = []
    for i in range(n_splits):
        fold_begin = val_start_idx + i * fold_size
        fold_end = fold_begin + fold_size if i < n_splits - 1 else n

        if fold_begin >= n:
            break

        val_indices = np.arange(fold_begin, min(fold_end, n))
        val_start_date = dates[fold_begin]
        purge_date = val_start_date - np.timedelta64(purge_days, "D")

        train_mask = dates < purge_date
        train_indices = np.where(train_mask)[0]

        if len(train_indices) < min_train_rows or len(val_indices) < 5:
            continue

        splits.append((train_indices, val_indices))

    return splits
