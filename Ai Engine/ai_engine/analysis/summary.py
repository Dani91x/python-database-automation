from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pandas as pd

from ai_engine.analysis.tools import feature_importance, correlation_matrix, variance_ranking, target_distribution


@dataclass
class AnalysisSummary:
    importance: pd.DataFrame
    correlation: pd.DataFrame
    variance: pd.DataFrame
    targets: Dict[str, float]


def build_analysis_summary(df: pd.DataFrame, target_col: str) -> AnalysisSummary:
    return AnalysisSummary(
        importance=feature_importance(df, target_col=target_col),
        correlation=correlation_matrix(df),
        variance=variance_ranking(df),
        targets=target_distribution(df, target_col=target_col),
    )
