"""
Phase 4 — serving validation on REAL, held-out Serie A matches using the models
just trained locally. Builds real pre-match features, runs predict_ensemble, and
compares calibrated probabilities to the actual outcome.
"""
from __future__ import annotations

import os
import sys
import gzip
import pickle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ai Engine"))

import numpy as np  # noqa
import pandas as pd

from ai_engine.db_adapter import fetch_seasons_for_league
from ai_engine.training_dataset import build_training_dataset
from ai_engine.ensemble_trainer import predict_ensemble, EnsemblePayload

LEAGUE = 135
seasons = fetch_seasons_for_league(LEAGUE)[-3:]
df = build_training_dataset([(LEAGUE, s) for s in seasons])
df = df[
    pd.to_numeric(df["goals_home"], errors="coerce").notna()
    & pd.to_numeric(df["goals_away"], errors="coerce").notna()
].copy()
df = df.sort_values("fixture_date")
recent = df.tail(10)  # most recent played matches (temporal holdout region)


def load(target: str) -> EnsemblePayload:
    p = os.path.join("Ai Engine", "models_cache", f"league_{LEAGUE}", f"ensemble_v2_{target}.pkl.gz")
    d = pickle.load(gzip.open(p, "rb"))
    return EnsemblePayload(
        base_models=d["base_models"], meta_model=d["meta_model"], scaler=d["scaler"],
        feature_cols=d["features"], feature_medians=d["feature_medians"],
        class_labels=d["class_labels"], base_weights=d["base_weights"],
        metrics={}, isotonic_calibrators=d["isotonic_calibrators"],
    )


ep_1x2 = load("target_1x2")
ep_o15 = load("target_over_1_5")

print("\nPredizioni REALI su partite recenti (mai viste in training):")
print("-" * 100)
n_ok_1x2 = 0
n = 0
for idx in recent.index:
    X = df.loc[[idx]]
    row = df.loc[idx]
    p1 = predict_ensemble(ep_1x2, X)
    po = predict_ensemble(ep_o15, X)
    s1 = sum(p1.values())
    gh, ga = int(row["goals_home"]), int(row["goals_away"])
    actual = "H" if gh > ga else ("A" if gh < ga else "D")
    pred = max(p1, key=p1.get)
    ok = pred == actual
    n_ok_1x2 += int(ok)
    n += 1
    over15 = (gh + ga) > 1
    home = str(row.get("home_team_name", "?"))[:16]
    away = str(row.get("away_team_name", "?"))[:16]
    print(
        f"  {home:16} {gh}-{ga} {away:16} | "
        f"1x2 H{p1.get('H',0)*100:4.0f} D{p1.get('D',0)*100:4.0f} A{p1.get('A',0)*100:4.0f} "
        f"-> {pred} (real {actual}) {'OK' if ok else 'X '} | "
        f"Over1.5 {po.get('True',0)*100:4.0f}% (real {'SI' if over15 else 'NO'}) | sum1x2={s1:.3f}"
    )

print("-" * 100)
print(f"1x2 top-pick correct: {n_ok_1x2}/{n}  (campione minuscolo, solo sanity)")
print("Tutte le sum1x2 devono essere 1.000 (probabilita coerenti).")
