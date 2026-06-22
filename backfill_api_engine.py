"""backfill_api_engine.py — aggiunge il MOTORE API (1x2 da percent_*) allo storico.

Lo storico analytics_signals proviene da engine_signals, che conteneva solo poisson+ml.
Il motore API (API-Football /predictions, 1x2 da percent_home/draw/away) non c'era.
Questo script genera le righe api 1x2 per OGNI fixture già in tabella, con esito a 90'
(hit/result/settled/goals/first_goal) coerente al settlement certificato per '1x2'.

Riusa `_rows_for_fixture` passando un fp con SOLO i percent_* (db_json_analisi/ML/Tactical
= None) → produce esclusivamente le righe 'api'. Upsert su signal_uid (idempotente).
DOPO: ri-eseguire il backfill concordanza (forzato) → ora include anche api nel top-pick.

Uso: python backfill_api_engine.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client
from build_analytics_signals import _rows_for_fixture, _fetch_matches, _fetch_first_goals

_FP_SEL = ("fixture_id,league_id,league_name,season_year,fixture_date,"
           "home_team_name,away_team_name,percent_home,percent_draw,percent_away,created_at")


def _fetch_fixture_ids(sb) -> list[int]:
    off, ids = 0, set()
    while True:
        r = sb.table("analytics_signals").select("fixture_id").range(off, off + 999).execute().data
        if not r:
            break
        ids.update(x["fixture_id"] for x in r)
        if len(r) < 1000:
            break
        off += 1000
    return sorted(ids)


def _fetch_fps(sb, fids: list[int]) -> dict[int, dict]:
    out = {}
    for i in range(0, len(fids), 200):
        r = sb.table("fixture_predictions").select(_FP_SEL).in_("fixture_id", fids[i:i + 200]).execute().data
        for row in r or []:
            out[row["fixture_id"]] = row
    return out


def _upsert(sb, rows: list[dict], counters: dict):
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        for attempt in range(3):
            try:
                sb.table("analytics_signals").upsert(chunk, on_conflict="signal_uid").execute()
                counters["upserted"] += len(chunk)
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    counters["errors"] += len(chunk)
                    print(f"  [ERR] upsert: {str(e)[:140]}")
                else:
                    time.sleep(0.4 * (attempt + 1))


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sb = get_supabase_client()

    fids = _fetch_fixture_ids(sb)
    print(f"fixture in tabella: {len(fids)}", flush=True)
    fps = _fetch_fps(sb, fids)
    matches = _fetch_matches(sb, fids)
    first_goals = _fetch_first_goals(sb, fids)
    print(f"fixture_predictions: {len(fps)} | matches: {len(matches)}", flush=True)

    rows = []
    no_pct = 0
    for fid, fp in fps.items():
        # fp con SOLO percent_* → _rows_for_fixture produce esclusivamente 'api'
        fp_api = dict(fp)
        fp_api["db_json_analisi"] = None
        fp_api["model_predictions_json"] = None
        fp_api["tactical_engine_json"] = None
        m = matches.get(fid)
        prows = [r for r in _rows_for_fixture(fp_api, m, first_goals.get(fid))
                 if r["engine"] == "api"]
        if not prows:
            no_pct += 1
            continue
        # la concordanza qui sarebbe solo-api → la ricalcoliamo via SQL forzato dopo
        for r in prows:
            r.pop("n_engines_agree", None)
            r.pop("consensus_prob", None)
        rows.extend(prows)
    print(f"righe api generate: {len(rows)} | fixture senza percent_*: {no_pct}", flush=True)

    if args.dry_run:
        s = rows[0] if rows else {}
        print("  esempio:", {k: s.get(k) for k in ("signal_uid", "selection", "prob", "hit", "result", "settled")})
        # check distribuzione: somma prob per fixture ~1
        from collections import defaultdict
        bf = defaultdict(list)
        for r in rows:
            bf[r["fixture_id"]].append(r["prob"])
        bad = sum(1 for v in bf.values() if len(v) == 3 and abs(sum(v) - 1) > 1e-4)
        print(f"  somma prob!=1: {bad}/{len(bf)} (atteso 0)")
        print("[DRY-RUN] nessuna scrittura.")
        return

    counters = {"upserted": 0, "errors": 0}
    _upsert(sb, rows, counters)
    print(f"upserted: {counters['upserted']} | errori: {counters['errors']}", flush=True)
    if counters["errors"]:
        raise SystemExit(f"ATTENZIONE: {counters['errors']} righe non scritte.")
    print("FATTO (motore api 1x2). Ora ri-esegui il backfill concordanza (forzato).", flush=True)


if __name__ == "__main__":
    main()
