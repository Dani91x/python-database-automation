from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass
class VotingModel:
    """Simple ensemble wrapper for already fitted estimators."""

    estimators: List

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        probs = [est.predict_proba(x) for est in self.estimators]
        return np.mean(probs, axis=0)

    def predict(self, x: np.ndarray) -> np.ndarray:
        probs = self.predict_proba(x)
        return np.argmax(probs, axis=1)
