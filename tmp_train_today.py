"""
Train the leagues that have fixtures on today's card (read from the Segnali sheet),
on the bettable markets, and upload to the registry so predict_fixture can serve
them. Today's matches have NO result in the DB (status NS) → they are automatically
excluded from training (C2 filter) → predictions on them are out-of-sample.

2 leagues in parallel (ProcessPool); each league parallelizes targets internally.
"""
from __future__ import annotations

import os
import sys
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

os.environ.setdefault("RETRAIN_N_WORKERS", "2")
os.environ.setdefault("RETRAIN_PARALLEL_LEAGUES", "2")

ROOT = os.path.dirname(os.path.abspath(__file__))

PRIORITY = [
    "target_1x2", "target_over_2_5", "target_over_1_5",
    "target_over_0_5", "target_btts", "target_ht_over_0_5",
]


def train_one(lid: int) -> dict:
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "Ai Engine"))
    try:
        from ai_engine.seriea_model_export import train_and_save_all, upload_and_register
        res = train_and_save_all(lid, last_n_seasons=3, targets_filter=PRIORITY)
        uploaded = 0
        rows = []
        for r in res:
            rows.append({
                "target": r["target"], "brier": r.get("brier"), "ece": r.get("ece"),
                "n_classes": r.get("n_classes"), "train_rows": r.get("train_rows"),
                "base_models": list((r.get("base_weights") or {}).keys()),
            })
            if not r.get("upload_skipped"):
                try:
                    upload_and_register(r["model_path"], r["file_size"], r["target"], r)
                    uploaded += 1
                except Exception as e:
                    rows[-1]["upload_error"] = str(e)[:120]
        return {"league": lid, "n_models": len(res), "uploaded": uploaded, "models": rows}
    except Exception as e:
        return {"league": lid, "error": str(e)[:300]}


if __name__ == "__main__":
    leagues = [10, 666, 200, 893, 333, 115, 141, 114, 72, 246]  # 928 skipped (65 matches)
    t0 = time.time()
    out = []
    with ProcessPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(train_one, l): l for l in leagues}
        for f in as_completed(futs):
            r = f.result()
            out.append(r)
            if "error" in r:
                print(f"  league {r['league']}: ERROR {r['error']}")
            else:
                bsss = []
                for m in r["models"]:
                    b, nc = m.get("brier"), m.get("n_classes")
                    if b and nc:
                        bsss.append(f"{m['target'].replace('target_','')}:BSS={round(1-b/((nc-1)/nc),2)}")
                print(f"  league {r['league']}: {r['n_models']} models, {r['uploaded']} uploaded | {', '.join(bsss)}")
    json.dump({"elapsed_min": round((time.time() - t0) / 60, 1), "results": out},
              open(os.path.join(ROOT, "tmp_train_today_result.json"), "w"), indent=2)
    print(f"\nALL DONE in {round((time.time()-t0)/60,1)} min")
