from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def explain_linear(model, feature_names: list[str]) -> pd.DataFrame:
    if not hasattr(model, "coef_"):
        raise ValueError("Model does not expose coef_")
    coefs = model.coef_
    if coefs.ndim == 1:
        coefs = coefs.reshape(1, -1)
    rows = []
    for i, row in enumerate(coefs):
        for f, c in zip(feature_names, row):
            rows.append({"class_idx": i, "feature": f, "weight": float(c)})
    return pd.DataFrame(rows).sort_values(by="weight", key=lambda s: s.abs(), ascending=False)


def explain_tree_importance(model, feature_names: list[str]) -> pd.DataFrame:
    if not hasattr(model, "feature_importances_"):
        raise ValueError("Model does not expose feature_importances_")
    return (
        pd.DataFrame({"feature": feature_names, "importance": model.feature_importances_})
        .sort_values(by="importance", ascending=False, ignore_index=True)
    )


def explain_model(model, feature_names: list[str]) -> Dict[str, pd.DataFrame]:
    if hasattr(model, "feature_importances_"):
        return {"importance": explain_tree_importance(model, feature_names)}
    if hasattr(model, "coef_"):
        return {"coefficients": explain_linear(model, feature_names)}
    return {}
