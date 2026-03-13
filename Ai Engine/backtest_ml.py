"""
Backtest ML predictions vs historical odds.

Measures: hit rate, ROI (simulated Kelly 1/4), CLV (Closing Line Value).
CLV = (model_prob / closing_implied_prob - 1) * 100
Positive CLV = beating the market long-term.

Usage:
    python backtest_ml.py --leagues 135,78 --last-n-seasons 3
    python backtest_ml.py --all
"""
from __future__ import annotations

import argparse
import csv
import gzip
import os
import pickle
import sys
import warnings
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AI_ENGINE_DIR = os.path.abspath(os.path.dirname(__file__))
for p in [ROOT, AI_ENGINE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from ai_engine.db_adapter import fetch_matches_for_league_seasons, fetch_seasons_for_league
from ai_engine.training_dataset import build_training_dataset
from ai_engine.ensemble_trainer import predict_ensemble, EnsemblePayload
from ai_engine.value_betting import expected_value, kelly_criterion, implied_probability


MODELS_CACHE_DIR = os.path.join(AI_ENGINE_DIR, "models_cache")
KELLY_FRACTION = 0.25
BANKROLL = 1000.0


def _load_model(path: str) -> Optional[Dict]:
    try:
        with gzip.open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _payload_to_ensemble(payload: Dict) -> EnsemblePayload:
    if isinstance(payload, EnsemblePayload):
        return payload
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


def backtest_league(league_id: int, last_n_seasons: int = 3) -> List[Dict]:
    """Run backtest for a single league. Returns list of per-bet results."""
    league_dir = os.path.join(MODELS_CACHE_DIR, f"league_{league_id}")
    if not os.path.isdir(league_dir):
        print(f"  No models for league {league_id}")
        return []

    # Load all models for this league
    models: Dict[str, Dict] = {}
    for fname in os.listdir(league_dir):
        if not fname.endswith(".pkl.gz"):
            continue
        target = fname.replace("ensemble_v2_", "").replace(".pkl.gz", "")
        payload = _load_model(os.path.join(league_dir, fname))
        if payload:
            models[target] = payload

    if not models:
        print(f"  No valid models for league {league_id}")
        return []

    # Build dataset with temporal holdout
    seasons = fetch_seasons_for_league(league_id)
    seasons = seasons[-last_n_seasons:] if len(seasons) > last_n_seasons else seasons
    league_seasons = [(league_id, s) for s in seasons]

    train_df = build_training_dataset(league_seasons)
    if train_df.empty:
        print(f"  No training data for league {league_id}")
        return []

    # Use last 20% as holdout (temporal)
    train_df["fixture_date"] = pd.to_datetime(train_df["fixture_date"], errors="coerce")
    train_df = train_df.dropna(subset=["fixture_date"]).sort_values("fixture_date")
    n = len(train_df)
    cutoff = int(n * 0.80)
    holdout = train_df.iloc[cutoff:].copy()

    if holdout.empty:
        print(f"  Empty holdout for league {league_id}")
        return []

    print(f"  League {league_id}: {len(holdout)} holdout fixtures, {len(models)} targets")

    results = []
    for target, payload in models.items():
        if target not in holdout.columns:
            continue

        ep = _payload_to_ensemble(payload)
        class_labels = ep.class_labels

        # Get odds columns for this target
        odds_col_map = _get_odds_columns(target)

        for idx, row in holdout.iterrows():
            actual = row.get(target)
            if pd.isna(actual):
                continue

            # Predict
            feat_row = pd.DataFrame([row])
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore")
                    probs = predict_ensemble(ep, feat_row)
            except Exception:
                continue

            if not probs:
                continue

            # Get best class and its odds
            best_class = max(probs, key=probs.get)
            best_prob = probs[best_class]

            # Find odds for best class
            odds_col = odds_col_map.get(best_class)
            if not odds_col or odds_col not in row.index:
                continue

            decimal_odds = row.get(odds_col)
            if pd.isna(decimal_odds) or decimal_odds <= 1.0:
                continue

            decimal_odds = float(decimal_odds)
            impl_prob = implied_probability(decimal_odds)
            ev = expected_value(best_prob, decimal_odds)
            kelly = kelly_criterion(best_prob, decimal_odds, fraction=KELLY_FRACTION)
            stake = kelly * BANKROLL if kelly > 0 and ev > 0.03 else 0.0

            # Result
            hit = str(actual) == str(best_class)
            pnl = stake * (decimal_odds - 1.0) if hit else -stake

            # CLV
            clv = ((best_prob / impl_prob) - 1.0) * 100 if impl_prob > 0.01 else 0.0

            results.append({
                "league_id": league_id,
                "fixture_id": row.get("fixture_id"),
                "fixture_date": str(row.get("fixture_date"))[:10],
                "target": target,
                "predicted_class": best_class,
                "actual": str(actual),
                "model_prob": round(best_prob, 4),
                "implied_prob": round(impl_prob, 4),
                "decimal_odds": round(decimal_odds, 2),
                "ev": round(ev, 4),
                "kelly": round(kelly, 6),
                "stake": round(stake, 2),
                "hit": hit,
                "pnl": round(pnl, 2),
                "clv": round(clv, 2),
            })

    return results


def _get_odds_columns(target: str) -> Dict[str, str]:
    """Map target class labels to odds column names in the features DataFrame."""
    mapping: Dict[str, Dict[str, str]] = {
        "target_1x2": {"H": "odds_1x2_home", "D": "odds_1x2_draw", "A": "odds_1x2_away"},
        "target_btts": {"True": "odds_btts_yes", "False": "odds_btts_no"},
        "target_over_2_5": {"True": "odds_over_2_5", "False": "odds_under_2_5"},
        "target_over_1_5": {"True": "odds_over_1_5", "False": "odds_under_1_5"},
        "target_over_3_5": {"True": "odds_over_3_5", "False": "odds_under_3_5"},
    }
    return mapping.get(target, {})


def main():
    parser = argparse.ArgumentParser(description="ML Backtest on historical odds")
    parser.add_argument("--leagues", type=str, default=None)
    parser.add_argument("--last-n-seasons", type=int, default=3)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.leagues:
        league_ids = [int(x.strip()) for x in args.leagues.split(",")]
    elif args.all:
        league_ids = []
        if os.path.isdir(MODELS_CACHE_DIR):
            for d in os.listdir(MODELS_CACHE_DIR):
                if d.startswith("league_"):
                    try:
                        league_ids.append(int(d.split("_")[1]))
                    except ValueError:
                        pass
        league_ids = sorted(league_ids)
    else:
        print("Usage: python backtest_ml.py --leagues 135,78 or --all")
        sys.exit(1)

    print(f"Backtesting {len(league_ids)} leagues...")
    all_results = []
    for lid in league_ids:
        print(f"\nLeague {lid}:")
        results = backtest_league(lid, last_n_seasons=args.last_n_seasons)
        all_results.extend(results)

    if not all_results:
        print("\nNo results. Check that models and data are available.")
        sys.exit(0)

    # Summary
    df = pd.DataFrame(all_results)
    bets = df[df["stake"] > 0]

    print(f"\n{'='*70}")
    print(f"BACKTEST SUMMARY")
    print(f"{'='*70}")
    print(f"Total predictions:  {len(df)}")
    print(f"Bets placed:        {len(bets)}")

    if not bets.empty:
        total_staked = bets["stake"].sum()
        total_pnl = bets["pnl"].sum()
        roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0
        hit_rate = bets["hit"].mean() * 100
        avg_clv = bets["clv"].mean()

        print(f"Hit rate:           {hit_rate:.1f}%")
        print(f"Total staked:       {total_staked:.2f}")
        print(f"Total PnL:          {total_pnl:+.2f}")
        print(f"ROI:                {roi:+.1f}%")
        print(f"Avg CLV:            {avg_clv:+.2f}%")

        # Per target breakdown
        print(f"\n{'Target':30} {'Bets':6} {'Hit%':8} {'ROI%':8} {'CLV%':8}")
        print("-" * 62)
        for target, grp in bets.groupby("target"):
            t_staked = grp["stake"].sum()
            t_pnl = grp["pnl"].sum()
            t_roi = (t_pnl / t_staked * 100) if t_staked > 0 else 0
            t_hit = grp["hit"].mean() * 100
            t_clv = grp["clv"].mean()
            print(f"{target:30} {len(grp):6} {t_hit:7.1f}% {t_roi:+7.1f}% {t_clv:+7.2f}%")

    # Save CSV
    out_path = os.path.join(ROOT, f"backtest_ml_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    df.to_csv(out_path, index=False)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
