"""
load_poisson_calibration_to_db.py — popola public.poisson_calibration leggendo
dynamic_cal.json (gia' generato dall'action settimanale). Cosi' la calibrazione
Poisson diventa disponibile nel DB SENZA ricalcolare nulla.

Una riga per lega (corrections = by_league[lid]) + una riga league_id=0 (global).
Gemella di compute_ml_post_calibration._write_to_db. Idempotente (upsert su PK league_id).

PREREQUISITO: aver eseguito migrations/poisson_calibration.sql in Supabase SQL Editor.

Uso:  python load_poisson_calibration_to_db.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dynamic_cal.json")


def rows_from_dynamic_cal(d: dict) -> list[dict]:
    ga = d.get("generated_at")
    mn = d.get("min_n_per_league")
    total = d.get("total_fixtures")
    # globale per prima (il fallback deve esistere sempre)
    rows = [{
        "league_id": 0,
        "corrections": d.get("global", {}) or {},
        "min_n": d.get("min_n_global"),
        "total_fixtures": total,
        "generated_at": ga,
    }]
    for lid, corr in (d.get("by_league", {}) or {}).items():
        try:
            rows.append({
                "league_id": int(lid),
                "corrections": corr or {},
                "min_n": mn,
                "generated_at": ga,
            })
        except (TypeError, ValueError):
            continue
    return rows


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    with open(_PATH, encoding="utf-8") as f:
        d = json.load(f)
    rows = rows_from_dynamic_cal(d)
    print(f"dynamic_cal.json: {d.get('total_fixtures')} fixture, "
          f"{len(rows) - 1} leghe + 1 globale (generato {d.get('generated_at')})")

    sb = get_supabase_client()
    written = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        sb.table("poisson_calibration").upsert(batch).execute()
        written += len(batch)
        print(f"  upsert {written}/{len(rows)}...", end="\r")
    print(f"\n[OK] Scritte {written} righe in public.poisson_calibration.")


if __name__ == "__main__":
    main()
