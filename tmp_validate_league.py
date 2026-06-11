"""
Definitive validation: train ONE real league against Supabase (local only, no
upload), measure real Brier/ECE/BSS, and confirm the full stack is active.
"""
from __future__ import annotations

import os
import sys
import json
import time

os.environ.setdefault("RETRAIN_N_WORKERS", "4")
os.environ.setdefault("RETRAIN_PARALLEL_LEAGUES", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ai Engine"))

from ai_engine.seriea_model_export import train_and_save_all

LEAGUE = int(sys.argv[1]) if len(sys.argv) > 1 else 135
TARGETS = [
    "target_1x2", "target_over_2_5", "target_over_1_5",
    "target_btts", "target_ht_over_0_5",
]


def bss(brier, n_classes):
    if brier is None or not n_classes:
        return None
    base = (n_classes - 1) / n_classes  # uniform-classifier Brier (summed form)
    return round(1.0 - brier / base, 3)


t0 = time.time()
results = train_and_save_all(LEAGUE, last_n_seasons=3, targets_filter=TARGETS)
dt = time.time() - t0

print("\n" + "=" * 70)
print(f"VALIDATION SUMMARY — league {LEAGUE} — {dt/60:.1f} min — {len(results)} models")
print("=" * 70)
rows = []
for r in sorted(results, key=lambda x: x["target"]):
    nc = r.get("n_classes")
    b = bss(r.get("brier"), nc)
    base_models = list((r.get("base_weights") or {}).keys())
    print(
        f"  {r['target']:20} brier={r.get('brier')} ece={r.get('ece')} "
        f"BSS={b} feat={r.get('feature_count')} train={r.get('train_rows')} "
        f"classes={nc} models={base_models}"
    )
    rows.append({
        "target": r["target"], "brier": r.get("brier"), "ece": r.get("ece"),
        "bss": b, "n_classes": nc, "feature_count": r.get("feature_count"),
        "train_rows": r.get("train_rows"), "base_models": base_models,
        "accuracy": r.get("accuracy"), "logloss": r.get("logloss"),
    })

full_stack = all(("lgb" in r["base_models"] and "xgb" in r["base_models"]) for r in rows) if rows else False
out = {
    "league": LEAGUE, "elapsed_min": round(dt / 60, 1),
    "n_models": len(results), "full_stack_active": full_stack, "results": rows,
}
with open("tmp_validation_result.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"\nfull_stack_active (lgb+xgb in every model): {full_stack}")
print("saved tmp_validation_result.json")
