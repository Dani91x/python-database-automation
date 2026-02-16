from __future__ import annotations

from math import log
from typing import Dict, List, Tuple


def entropy(probs: Dict[str, float]) -> float:
    vals = [p for p in probs.values() if p > 0]
    if not vals:
        return 0.0
    return -sum(p * log(p, 2) for p in vals)


def consensus(preds: List[str]) -> float:
    if not preds:
        return 0.0
    top = max(preds.count(p) for p in set(preds))
    return top / len(preds)


def aggregate_model_outputs(model_outputs: List[Dict[str, float]], weights: List[float] | None = None) -> Dict[str, float]:
    agg: Dict[str, float] = {}
    if not model_outputs:
        return agg
    keys = set().union(*[m.keys() for m in model_outputs])
    if weights is None or len(weights) != len(model_outputs):
        weights = [1.0 for _ in model_outputs]
    wsum = sum(weights) if sum(weights) > 0 else 1.0
    for k in keys:
        vals = [m.get(k, 0.0) * weights[i] for i, m in enumerate(model_outputs)]
        agg[k] = sum(vals) / wsum
    return agg


def conflict_explanation(
    target_a: str,
    pred_a: str,
    target_b: str,
    pred_b: str,
    data_notes: List[str],
) -> str:
    if pred_a == pred_b:
        return ""
    note = "; ".join(data_notes) if data_notes else "No data notes"
    return f"Conflict {target_a}={pred_a} vs {target_b}={pred_b}. Evidence: {note}"
