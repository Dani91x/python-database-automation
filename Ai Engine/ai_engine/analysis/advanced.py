from __future__ import annotations

import numpy as np
import pandas as pd


def describe_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Basic describe for numeric features only."""
    numeric = df.select_dtypes(include=["number", "bool"]).copy()
    return numeric.describe().T


def feature_distributions(df: pd.DataFrame) -> pd.DataFrame:
    """Returns summary distribution stats for numeric features."""
    numeric = df.select_dtypes(include=["number", "bool"]).copy()
    return pd.DataFrame(
        {
            "mean": numeric.mean(numeric_only=True),
            "std": numeric.std(numeric_only=True),
            "min": numeric.min(numeric_only=True),
            "p25": numeric.quantile(0.25, numeric_only=True),
            "p50": numeric.quantile(0.50, numeric_only=True),
            "p75": numeric.quantile(0.75, numeric_only=True),
            "max": numeric.max(numeric_only=True),
            "missing_pct": numeric.isna().mean(),
        }
    ).sort_index()


def correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    numeric = df.select_dtypes(include=["number", "bool"]).copy()
    return numeric.corr()


def variance_ranking(df: pd.DataFrame) -> pd.DataFrame:
    numeric = df.select_dtypes(include=["number", "bool"]).copy()
    variances = numeric.var(numeric_only=True)
    return variances.sort_values(ascending=False).reset_index().rename(columns={"index": "feature", 0: "variance"})


def class_distribution(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    counts = df[target_col].value_counts(dropna=False)
    total = float(counts.sum()) if len(counts) else 1.0
    return pd.DataFrame({"count": counts, "pct": counts / total})


def coefficients_table(model, feature_names: list[str]) -> pd.DataFrame:
    if not hasattr(model, "coef_"):
        raise ValueError("Model does not expose coef_")
    coefs = model.coef_
    if coefs.ndim == 1:
        coefs = coefs.reshape(1, -1)
    rows = []
    for i, row in enumerate(coefs):
        for f, c in zip(feature_names, row):
            rows.append({"class_idx": i, "feature": f, "coef": float(c)})
    return pd.DataFrame(rows).sort_values(by="coef", key=lambda s: s.abs(), ascending=False)


def impurity_scores(model, feature_names: list[str]) -> pd.DataFrame:
    if not hasattr(model, "feature_importances_"):
        raise ValueError("Model does not expose feature_importances_")
    return (
        pd.DataFrame({"feature": feature_names, "importance": model.feature_importances_})
        .sort_values(by="importance", ascending=False, ignore_index=True)
    )


def decision_rules(tree_model, feature_names: list[str], max_depth: int = 3) -> str:
    from sklearn.tree import export_text

    return export_text(tree_model, feature_names=feature_names, max_depth=max_depth)


def boruta_select(df: pd.DataFrame, target_col: str) -> list[str]:
    try:
        from boruta import BorutaPy
    except Exception as e:  # pragma: no cover
        raise RuntimeError("boruta package not installed") from e

    from sklearn.ensemble import RandomForestClassifier

    clean = df.dropna(subset=[target_col]).copy()
    x = clean.drop(columns=[target_col], errors="ignore").select_dtypes(include=["number", "bool"]).to_numpy()
    y = clean[target_col].to_numpy()
    rf = RandomForestClassifier(n_estimators=200, random_state=0, n_jobs=-1, class_weight="balanced")
    boruta = BorutaPy(rf, n_estimators="auto", random_state=0)
    boruta.fit(x, y)
    cols = clean.drop(columns=[target_col], errors="ignore").select_dtypes(include=["number", "bool"]).columns
    return [c for c, keep in zip(cols, boruta.support_) if keep]
