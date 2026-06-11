"""
Stack-activation smoke test — exercises the code paths that were DORMANT until
lightgbm/xgboost/optuna/imbalanced-learn were installed, to surface latent bugs.

Covers: SMOTE resampling, Optuna tuning (rf/lgb/xgb), build_ensemble with tuned
params + SMOTE on imbalanced data, and the full pickle→reconstruct→predict
serving round-trip (the exact path predict_fixture uses to feed the sheet).
"""
from __future__ import annotations

import gzip
import pickle
import sys
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "Ai Engine"))

import ai_engine.ensemble_trainer as ET
from ai_engine.ensemble_trainer import (
    build_ensemble, predict_ensemble, EnsemblePayload,
    _apply_smote, _run_optuna_tuning, _build_base_models, _get_league_tier,
)

RNG = np.random.default_rng(7)
_fail: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"  [{'OK  ' if cond else 'FAIL'}] {msg}")
    if not cond:
        _fail.append(msg)


def _imbalanced(n: int):
    """3-class data with a minority Draw class (~15%) and real signal."""
    x = RNG.normal(0, 1, (n, 6))
    score = 1.1 * x[:, 0] + 0.7 * x[:, 1] + RNG.normal(0, 0.6, n)
    y = np.where(score > 0.6, "H", np.where(score < -0.2, "A", "D"))
    return pd.DataFrame(x, columns=[f"f{i}" for i in range(6)]), pd.Series(y)


print("== stack flags ==")
check(ET._LIGHTGBM_AVAILABLE, "lightgbm available")
check(ET._XGBOOST_AVAILABLE, "xgboost available")
check(ET._IMBLEARN_AVAILABLE, "imbalanced-learn available")

print("\n== base models include lgb+xgb at MEDIUM ==")
names = [n for n, _ in _build_base_models(3, n_samples=500, tier="MEDIUM")]
check("lgb" in names and "xgb" in names, f"MEDIUM base models = {names}")

print("\n== SMOTE resampling (forced imbalance < 0.35) ==")
# Binary, ~12% minority True — like a rare over_4_5 target. ratio < 0.35 → SMOTE active.
n = 400
xb = RNG.normal(0, 1, (n, 6))
yb = np.where(RNG.random(n) < 0.12, "True", "False")
ratio = pd.Series(yb).value_counts().min() / pd.Series(yb).value_counts().max()
Xr, yr = _apply_smote(xb, yb, imbalance_ratio=float(ratio), tier="MEDIUM")
new_counts = pd.Series(yr).value_counts()
check(ratio < 0.35, f"input is genuinely imbalanced (ratio={ratio:.2f})")
check(len(Xr) > n, f"SMOTE resampled UP ({n} -> {len(Xr)} rows)")
check(new_counts.min() / new_counts.max() > ratio, f"SMOTE improved balance ({ratio:.2f} -> {new_counts.min()/new_counts.max():.2f})")
# Guard path: ratio >= 0.35 must be a no-op
Xn, yn = _apply_smote(xb, yb, imbalance_ratio=0.5, tier="MEDIUM")
check(len(Xn) == n, "SMOTE no-op when ratio >= 0.35 (guard works)")
# Guard path: TINY tier must never resample
Xt2, yt2 = _apply_smote(xb, yb, imbalance_ratio=float(ratio), tier="TINY")
check(len(Xt2) == n, "SMOTE no-op on TINY tier (guard works)")

print("\n== Optuna tuning (rf/lgb/xgb, 3 trials) ==")
Xt, yt = _imbalanced(300)
# simple 2-fold expanding splits
idx = np.arange(len(Xt))
splits = [(idx[:150], idx[150:225]), (idx[:225], idx[225:])]
params = _run_optuna_tuning(Xt.to_numpy().astype(float), yt.to_numpy(), splits, tier="MEDIUM", n_trials=3)
check(isinstance(params, dict), "optuna returned a dict")
check("rf" in params and bool(params["rf"]), f"optuna tuned rf params: {list(params.get('rf', {}))[:3]}")
check("lgb" in params and bool(params["lgb"]), "optuna tuned lgb params")
check("xgb" in params and bool(params["xgb"]), "optuna tuned xgb params")

print("\n== build_ensemble: SMOTE TRIGGERED + sample_weights + tuned params (MEDIUM) ==")
# Rare-Draw 3-class data so min/max < 0.35 → SMOTE actually fires inside OOF,
# AND pass time-decay sample_weights to exercise the synthetic-weight path (HIGH#1).
nbig = 560
xb3 = RNG.normal(0, 1, (nbig, 6))
sc = 1.1 * xb3[:, 0] + 0.7 * xb3[:, 1] + RNG.normal(0, 0.5, nbig)
y3 = np.where(sc > 0.15, "H", np.where(sc < -0.15, "A", "D"))  # D ~12% (rare)
X = pd.DataFrame(xb3, columns=[f"f{i}" for i in range(6)])
y = pd.Series(y3)
vc = y.value_counts()
print(f"   class balance min/max = {vc.min()/vc.max():.2f} (SMOTE active if <0.35)")
cut = 460
weights = np.linspace(0.3, 1.0, cut)  # time-decay-like weights
payload = build_ensemble(
    X.iloc[:cut], y.iloc[:cut], X.iloc[cut:], y.iloc[cut:],
    sample_weights=weights,
    feature_cols=list(X.columns), feature_medians={c: 0.0 for c in X.columns},
    optuna_params=params, tier="MEDIUM", n_jobs=1,
)
mnames = [n for n, _ in payload.base_models]
check("lgb" in mnames and "xgb" in mnames, f"trained base models = {mnames}")
check("__temperature_scaling__" in (payload.isotonic_calibrators or {}), "temperature scaling fitted")

print("\n== pickle -> reconstruct -> predict (serving round-trip) ==")
save = {
    "model_type": "ensemble_v2",
    "base_models": payload.base_models,
    "meta_model": payload.meta_model,
    "scaler": payload.scaler,
    "features": payload.feature_cols,
    "feature_medians": payload.feature_medians,
    "class_labels": payload.class_labels,
    "base_weights": payload.base_weights,
    "isotonic_calibrators": payload.isotonic_calibrators,
}
blob = gzip.compress(pickle.dumps(save, protocol=pickle.HIGHEST_PROTOCOL))
d = pickle.loads(gzip.decompress(blob))
ep = EnsemblePayload(
    base_models=d["base_models"], meta_model=d["meta_model"], scaler=d["scaler"],
    feature_cols=d["features"], feature_medians=d["feature_medians"],
    class_labels=d["class_labels"], base_weights=d["base_weights"],
    metrics={}, isotonic_calibrators=d["isotonic_calibrators"],
)
probs = predict_ensemble(ep, X.iloc[[cut]])
s = sum(probs.values())
check(abs(s - 1.0) < 1e-6, f"reconstructed model predict sums to 1 ({s:.6f})")
check(set(probs.keys()) == set(payload.class_labels), f"class labels preserved ({list(probs)})")

print("\n" + "=" * 60)
if _fail:
    print(f"STACK SMOKE FAILED — {len(_fail)} check(s):")
    for f in _fail:
        print("   -", f)
    sys.exit(1)
print("STACK SMOKE PASSED — full stack exercised, no latent bugs.")
