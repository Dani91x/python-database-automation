from __future__ import annotations

import os
import sys
import gzip
import pickle
import warnings
from typing import Dict, List

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
if AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, AI_ENGINE_DIR)

from db_client import get_supabase_client
from ai_engine.db_adapter import (
    fetch_fixture_prediction_by_id,
    fetch_matches_for_league_seasons,
    fetch_seasons_for_league,
)
from ai_engine.feature_pipeline import build_feature_dataframe_for_fixtures


def _download_model(bucket: str, path: str, out_path: str) -> None:
    sb = get_supabase_client()
    res = sb.storage.from_(bucket).download(path)
    with open(out_path, "wb") as f:
        f.write(res)


def _load_model(path: str) -> Dict:
    try:
        with gzip.open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        with open(path, "rb") as f:
            return pickle.load(f)


def predict_fixture(fixture_id: int) -> Dict[str, Dict[str, float]]:
    rows = fetch_fixture_prediction_by_id(fixture_id)
    if not rows:
        raise RuntimeError(f"fixture_id {fixture_id} not found in fixture_predictions")

    fx_df = pd.DataFrame(rows)
    league_id = int(fx_df.iloc[0]["league_id"])

    seasons = fetch_seasons_for_league(league_id)
    league_seasons = [(league_id, s) for s in seasons[-3:]]  # use last 3 years, consistent with pilot
    history_rows = fetch_matches_for_league_seasons(league_seasons)
    history_df = pd.DataFrame(history_rows)

    features_df = build_feature_dataframe_for_fixtures(
        fx_df,
        history_df,
        league_seasons,
        include_events=True,
        include_team_stats=True,
        include_injuries=True,
        include_player_stats=True,
        pre_match=True,
    )
    if features_df.empty:
        raise RuntimeError("No features produced for fixture")

    sb = get_supabase_client()
    reg = (
        sb.table("ai_model_registry")
        .select("target,model_name,storage_bucket,storage_path,features_version,targets_version")
        .eq("league_id", league_id)
        .execute()
    )
    models = getattr(reg, "data", None) or []
    if not models:
        raise RuntimeError("No models found in ai_model_registry for league")

    out_dir = os.path.join("Ai Engine", "models_cache", "downloaded")
    os.makedirs(out_dir, exist_ok=True)

    results: Dict[str, Dict[str, float]] = {}
    for m in models:
        target = m["target"]
        bucket = m["storage_bucket"]
        path = m["storage_path"]
        local_path = os.path.join(out_dir, os.path.basename(path))
        if not os.path.exists(local_path):
            _download_model(bucket, path, local_path)
        payload = _load_model(local_path)
        model = payload["model"]
        feats = payload["features"]

        X = features_df.reindex(columns=feats).select_dtypes(include=["number", "bool"]).copy()
        X = X.fillna(0)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            proba = model.predict_proba(X)
        classes = [str(c) for c in model.classes_]
        results[target] = {classes[i]: float(proba[0][i]) for i in range(len(classes))}

    return results


if __name__ == "__main__":
    fixture_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if fixture_id <= 0:
        raise SystemExit("Usage: python predict_fixture.py <fixture_id>")
    res = predict_fixture(fixture_id)
    for k, v in res.items():
        print(k, v)
