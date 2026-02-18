"""
predict_fixture.py  — Production prediction pipeline.

Loads the ensemble model for the fixture's league, builds features,
runs predictions through the stacking ensemble, applies value-betting
analysis and confidence gates, then optionally stores results.

Output JSON includes:
  - targets / targets_raw  (calibrated/raw probabilities)
  - coverage               (feature availability)
  - reliability             (data quality score)
  - ensemble_agreement      (base model consensus per target)
  - bet_signals             (value bets with EV, Kelly, stake)
  - no_bet_reasons          (why certain markets were excluded)
  - confidence_gates        (3-gate pass/fail summary)
  - profit_balance          (from odds)
"""
from __future__ import annotations

import os
import sys
import gzip
import pickle
import warnings
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import numpy as np
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
from ai_engine.coverage import build_coverage_report
from ai_engine.metrics.balance import compute_profit_balance
from ai_engine.value_betting import (
    evaluate_bet_opportunities,
    build_odds_mapping,
    BetSignal,
)
from ai_engine.confidence_gate import (
    apply_all_gates,
    summarize_gates,
)


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


def _payload_to_ensemble(payload: Dict) -> Any:
    """
    Reconstruct an EnsemblePayload dataclass from a saved dict payload.
    Handles both EnsemblePayload objects (already correct) and raw dicts.
    """
    from ai_engine.ensemble_trainer import EnsemblePayload
    if isinstance(payload, EnsemblePayload):
        return payload
    # Reconstruct from dict
    return EnsemblePayload(
        base_models=payload.get("base_models", []),
        meta_model=payload.get("meta_model"),
        scaler=payload.get("scaler"),
        feature_cols=payload.get("features", payload.get("feature_cols", [])),
        feature_medians=payload.get("feature_medians", {}),
        class_labels=payload.get("class_labels", []),
        base_weights=payload.get("base_weights", {}),
        metrics=payload.get("metrics", {}),
    )


def _predict_with_ensemble(
    payload: Dict,
    features_df: pd.DataFrame,
) -> tuple[Dict[str, float], Dict[str, float], Dict[str, Any]]:
    """
    Predict using ensemble payload.

    Returns (calibrated_probs, raw_probs, agreement_info).
    Handles both legacy (single model) and new ensemble payloads.
    """
    from ai_engine.ensemble_trainer import predict_ensemble, get_ensemble_agreement

    def _meta_n_features(meta: Any) -> Optional[int]:
        if meta is None:
            return None
        if hasattr(meta, "calibrated_classifiers_") and meta.calibrated_classifiers_:
            est = meta.calibrated_classifiers_[0].estimator
            return getattr(est, "n_features_in_", None)
        return getattr(meta, "n_features_in_", None)

    def _resolve_classes(p: Any) -> list[str]:
        meta = getattr(p, "meta_model", None)
        meta_classes = [str(c) for c in getattr(meta, "classes_", [])] if meta is not None else []
        payload_classes = [str(c) for c in getattr(p, "class_labels", [])]
        n_models = len(getattr(p, "base_models", []) or [])
        n_in = _meta_n_features(meta)

        if n_in and n_models:
            if meta_classes and len(meta_classes) * n_models == n_in:
                return meta_classes
            if payload_classes and len(payload_classes) * n_models == n_in:
                return payload_classes

        return meta_classes or payload_classes

    model_type = payload.get("model_type", "legacy")

    if model_type == "ensemble_v2":
        # Reconstruct EnsemblePayload and use canonical prediction functions
        ep = _payload_to_ensemble(payload)
        class_labels = _resolve_classes(ep)

        # Use the same predict_ensemble logic used during training
        cal_probs = predict_ensemble(ep, features_df)
        agreement = get_ensemble_agreement(ep, features_df)

        # Raw probs = weighted average of base models (no meta-learner)
        feats = ep.feature_cols
        medians = ep.feature_medians
        X = features_df.reindex(columns=feats).select_dtypes(include=["number", "bool"]).copy()
        if medians:
            X = X.fillna(medians)
        X = X.fillna(0)
        X_np = X.to_numpy().astype(float)
        X_scaled = ep.scaler.transform(X_np) if ep.scaler else X_np

        total_weight = sum(ep.base_weights.values()) or 1.0
        raw_probs = {c: 0.0 for c in class_labels}
        for name, model in ep.base_models:
            w = ep.base_weights.get(name, 1.0) / total_weight
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model.predict_proba(X_scaled)
            model_classes = [str(c) for c in model.classes_]
            for i, c in enumerate(class_labels):
                if c in model_classes:
                    idx_c = model_classes.index(c)
                    raw_probs[c] += w * float(proba[0][idx_c])

        # Add per-model probs to agreement info
        agreement["per_model_probs"] = {}
        for name, model in ep.base_models:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                proba = model.predict_proba(X_scaled)
            model_classes = [str(c) for c in model.classes_]
            agreement["per_model_probs"][name] = {
                c: float(proba[0][model_classes.index(c)]) if c in model_classes else 0.0
                for c in class_labels
            }

        return cal_probs, raw_probs, agreement

    else:
        # Legacy single model
        feats = payload["features"]
        medians = payload.get("feature_medians", {})
        X = features_df.reindex(columns=feats).select_dtypes(include=["number", "bool"]).copy()
        if medians:
            X = X.fillna(medians)
        X = X.fillna(0)
        model = payload["model"]
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            proba = model.predict_proba(X)
        classes = [str(c) for c in model.classes_]
        probs = {classes[i]: float(proba[0][i]) for i in range(len(classes))}
        agreement = {
            "predicted_class": max(probs, key=probs.get),
            "agreement_ratio": 1.0,
            "votes": {"model": max(probs, key=probs.get)},
        }
        return probs, probs, agreement


def _profit_balance_from_odds(raw_odds: Dict) -> Dict[str, float]:
    if not isinstance(raw_odds, dict):
        return {}

    def _extract(odds_json: dict, market_names: list[str]) -> list[float]:
        values = []
        name_set = {n.lower() for n in market_names}
        for bm in odds_json.get("bookmakers", []) or []:
            for bet in bm.get("bets", []) or []:
                bet_name = str(bet.get("name", "")).lower()
                if bet_name in name_set:
                    for v in bet.get("values", []) or []:
                        try:
                            values.append(float(v.get("odd")))
                        except Exception:
                            continue
        return values

    out = {}
    odds_1x2 = _extract(raw_odds, ["Match Winner", "1X2", "Fulltime Result"])
    if odds_1x2:
        out["1x2"] = compute_profit_balance(odds_1x2)
    odds_ou = _extract(raw_odds, ["Goals Over/Under", "Over/Under", "Goals Over Under"])
    if odds_ou:
        out["over_under"] = compute_profit_balance(odds_ou)
    odds_btts = _extract(raw_odds, ["Both Teams Score", "BTTS"])
    if odds_btts:
        out["btts"] = compute_profit_balance(odds_btts)
    return out


def _reliability_score(
    features_df: pd.DataFrame,
    feats_union: list[str],
    matches_home: int,
    matches_away: int,
    coverage: Dict[str, Dict[str, int]],
) -> Dict[str, Any]:
    if features_df.empty or not feats_union:
        return {"score": 0.0, "grade": "low", "reason": "feature set empty"}

    row = features_df.reindex(columns=feats_union).select_dtypes(include=["number", "bool"]).copy().iloc[0]
    features_pct = float(row.notna().mean())
    matches_depth = min(matches_home, matches_away) / 15.0 if min(matches_home, matches_away) > 0 else 0.0
    matches_depth = min(matches_depth, 1.0)
    key_presence = 0.0
    odds_ok = (
        coverage.get("odds_1x2", {}).get("ok", 0)
        or coverage.get("odds_ou_25", {}).get("ok", 0)
        or coverage.get("odds_btts", {}).get("ok", 0)
    )
    if odds_ok:
        key_presence += 0.34
    if coverage.get("team_stats", {}).get("ok"):
        key_presence += 0.33
    if coverage.get("events", {}).get("ok"):
        key_presence += 0.33

    score = (0.45 * features_pct) + (0.35 * matches_depth) + (0.20 * key_presence)
    grade = "high" if score >= 0.70 else "medium" if score >= 0.50 else "low"
    reason = f"features_pct={features_pct:.2f}, matches_depth={matches_depth:.2f}, key_presence={key_presence:.2f}"
    return {"score": round(score, 3), "grade": grade, "reason": reason}


def _scale_probabilities(probs: Dict[str, float], alpha: float) -> Dict[str, float]:
    """Shrink probabilities toward uniform based on alpha (0=uniform, 1=keep)."""
    if not probs:
        return probs
    labels = list(probs.keys())
    k = len(labels)
    if k == 0:
        return probs
    uniform = 1.0 / k
    scaled = {lbl: (alpha * float(p) + (1.0 - alpha) * uniform) for lbl, p in probs.items()}
    total = sum(scaled.values()) or 1.0
    return {lbl: val / total for lbl, val in scaled.items()}


def predict_fixture(fixture_id: int, store: bool = False) -> Dict[str, Any]:
    """
    Full prediction pipeline for a single fixture.

    Returns complete prediction dict with:
    - targets / targets_raw
    - ensemble_agreement per target
    - bet_signals + no_bet_reasons
    - confidence_gates
    - coverage, reliability, profit_balance
    """
    rows = fetch_fixture_prediction_by_id(fixture_id)
    if not rows:
        raise RuntimeError(f"fixture_id {fixture_id} not found in fixture_predictions")

    fx_df = pd.DataFrame(rows)
    league_id = int(fx_df.iloc[0]["league_id"])

    seasons = fetch_seasons_for_league(league_id)
    league_seasons = [(league_id, s) for s in seasons[-3:]]
    history_rows = fetch_matches_for_league_seasons(league_seasons)
    history_df = pd.DataFrame(history_rows)

    features_df = build_feature_dataframe_for_fixtures(
        fx_df, history_df, league_seasons,
        include_events=True, include_team_stats=True,
        include_player_stats=True, pre_match=True,
    )
    if features_df.empty:
        raise RuntimeError("No features produced for fixture")

    # Load models from registry
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
    raw_results: Dict[str, Dict[str, float]] = {}
    agreement_results: Dict[str, Dict[str, Any]] = {}
    feats_union: list[str] = []

    for m in models:
        target = m["target"]
        bucket = m["storage_bucket"]
        path = m["storage_path"]
        local_path = os.path.join(out_dir, os.path.basename(path))
        if not os.path.exists(local_path):
            _download_model(bucket, path, local_path)
        payload = _load_model(local_path)

        feats = payload["features"]
        feats_union.extend([f for f in feats if f not in feats_union])

        cal_probs, raw_probs, agreement = _predict_with_ensemble(payload, features_df)

        raw_results[target] = raw_probs
        agreement_results[target] = agreement

    # Coverage & reliability
    coverage = build_coverage_report(features_df)
    home_team_id = int(fx_df.iloc[0]["home_team_id"]) if not fx_df.empty else None
    away_team_id = int(fx_df.iloc[0]["away_team_id"]) if not fx_df.empty else None
    matches_home = int((history_df["home_team_id"].eq(home_team_id) | history_df["away_team_id"].eq(home_team_id)).sum()) if not history_df.empty and home_team_id else 0
    matches_away = int((history_df["home_team_id"].eq(away_team_id) | history_df["away_team_id"].eq(away_team_id)).sum()) if not history_df.empty and away_team_id else 0

    rel = _reliability_score(features_df, feats_union, matches_home, matches_away, coverage)
    alpha = float(rel.get("score", 0.0))

    # Apply reliability scaling to get final calibrated targets
    for target, probs in raw_results.items():
        results[target] = _scale_probabilities(probs, alpha)

    # ── VALUE BETTING ANALYSIS ─────────────────────────────────
    raw_odds = fx_df.iloc[0].get("raw_json_odds") if not fx_df.empty else None
    if isinstance(raw_odds, str):
        try:
            raw_odds = json.loads(raw_odds)
        except Exception:
            raw_odds = None

    odds_mapping = build_odds_mapping(raw_odds, results) if raw_odds else {}
    bet_signals, no_bet_reasons = evaluate_bet_opportunities(results, odds_mapping)

    # ── CONFIDENCE GATES ──────────────────────────────────────
    features_pct_val = float(features_df.reindex(columns=feats_union).notna().mean(axis=1).iloc[0]) if feats_union else 0.0

    # Apply gates per bet signal
    gated_signals: List[Dict[str, Any]] = []
    gated_no_bet: List[Dict[str, str]] = []

    for signal in bet_signals:
        target_agreement = agreement_results.get(signal.market, {})
        agr_ratio = target_agreement.get("agreement_ratio", 0.0)
        agr_votes = target_agreement.get("votes", {})

        all_passed, gate_results = apply_all_gates(
            coverage_pct=features_pct_val,
            matches_home=matches_home,
            matches_away=matches_away,
            reliability_score=alpha,
            agreement_ratio=agr_ratio,
            votes=agr_votes,
            bet_signal=signal,
        )

        signal_dict = {
            "market": signal.market,
            "action": signal.action,
            "model_prob": signal.model_prob,
            "implied_prob": signal.implied_prob,
            "decimal_odds": signal.decimal_odds,
            "expected_value": signal.expected_value,
            "kelly_fraction": signal.kelly_fraction,
            "kelly_stake": signal.kelly_stake,
            "confidence_grade": signal.confidence_grade,
            "edge": signal.edge,
            "gates_passed": all_passed,
            "gates_detail": summarize_gates(gate_results),
        }

        if all_passed:
            gated_signals.append(signal_dict)
        else:
            failed_gate = next((g for g in gate_results if not g.passed), None)
            gated_no_bet.append({
                "target": signal.market,
                "reason": f"Gate failed: {failed_gate.reason}" if failed_gate else "Unknown gate failure",
            })

    # Add remaining no-bet reasons
    gated_no_bet.extend(no_bet_reasons)

    profit_balance = _profit_balance_from_odds(raw_odds) if raw_odds else {}

    # ── BUILD OUTPUT JSON ─────────────────────────────────────
    model_predictions_json = {
        "model_name": "ensemble_v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targets": results,
        "targets_raw": raw_results,
        "coverage": {
            "features_pct": round(features_pct_val, 3),
            "matches_home": matches_home,
            "matches_away": matches_away,
            "detail": coverage,
        },
        "profit_balance": profit_balance,
        "reliability": {**rel, "alpha": round(alpha, 3), "scaling": "uniform_shrink"},
        "ensemble_agreement": {
            t: {
                "predicted_class": a.get("predicted_class", ""),
                "agreement_ratio": a.get("agreement_ratio", 0.0),
                "votes": a.get("votes", {}),
            }
            for t, a in agreement_results.items()
        },
        "bet_signals": gated_signals,
        "no_bet_reasons": gated_no_bet,
    }

    if store:
        sb.table("fixture_predictions").update(
            {
                "model_predictions_json": model_predictions_json,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("fixture_id", fixture_id).execute()

    return model_predictions_json


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python predict_fixture.py <fixture_id> [--store]")
    fixture_id = int(sys.argv[1])
    store = "--store" in sys.argv
    if fixture_id <= 0:
        raise SystemExit("Usage: python predict_fixture.py <fixture_id> [--store]")
    res = predict_fixture(fixture_id, store=store)
    # Print summary
    print(f"\n{'='*60}")
    print(f"Fixture {fixture_id} — Prediction Summary")
    print(f"{'='*60}")
    print(f"Reliability: {res['reliability']['grade']} ({res['reliability']['score']})")
    print(f"Coverage: {res['coverage']['features_pct']:.1%}")
    print(f"\nBET SIGNALS ({len(res['bet_signals'])}):")
    for s in res['bet_signals']:
        print(f"  ✅ {s['market']}: {s['action']} | "
              f"EV={s['expected_value']:.3f} | "
              f"odds={s['decimal_odds']} | "
              f"stake={s['kelly_stake']}€ | "
              f"conf={s['confidence_grade']}")
    print(f"\nNO BET ({len(res['no_bet_reasons'])}):")
    for nb in res['no_bet_reasons'][:10]:
        print(f"  ❌ {nb['target']}: {nb['reason']}")
