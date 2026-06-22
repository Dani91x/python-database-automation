"""fix_storico_prob.py — FIX C1/C2/H2 sullo storico analytics_signals.

Lo storico veniva da engine_signals (solo selezioni tradate, prob PER-SCOMMESSA
overround che invertiva l'argmax nel 27% dei 1x2, selezioni mancanti). Questo fix
RICOSTRUISCE la previsione POISSON COMPLETA da fixture_predictions (markets_calibrated,
fallback markets grezzo) riusando il populator `_rows_for_fixture`:
  • genera anche le SELEZIONI MANCANTI (es. il Pareggio assente) → direzione/concordanza corrette;
  • prob = previsione PURA (no overround, argmax corretto);
  • esito a 90' (hit/result/settled/goals), line, prob_raw, first_goal coerenti.
Le righe ML restano (engine_signals = unica fonte storica). placed/status NON toccati
(ownership merger). Poi la concordanza viene ricalcolata (top-pick Poisson completo + ML).

Uso: python fix_storico_prob.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client
from build_analytics_signals import _rows_for_fixture, _fetch_matches, _fetch_first_goals

_FP_SEL = ("fixture_id,league_id,league_name,season_year,fixture_date,"
           "home_team_name,away_team_name,db_json_analisi")


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
        chunk = fids[i:i + 200]
        r = sb.table("fixture_predictions").select(_FP_SEL).in_("fixture_id", chunk).execute().data
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
                    print(f"  [ERR] upsert: {str(e)[:120]}")
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

    # genera le righe POISSON complete (fp con SOLO db_json_analisi → _rows_for_fixture
    # produce solo Poisson; ML/Tactical non passati). placed/status NON nel payload.
    rows = []
    for fid, fp in fps.items():
        fp_poisson = dict(fp)
        fp_poisson["model_predictions_json"] = None
        fp_poisson["tactical_engine_json"] = None
        m = matches.get(fid)
        prows = [r for r in _rows_for_fixture(fp_poisson, m, first_goals.get(fid))
                 if r["engine"] == "poisson"]
        # la concordanza qui sarebbe solo-Poisson → la ricalcoliamo dopo via SQL:
        # rimuoviamo n_engines_agree/consensus_prob dal payload per non sporcare.
        for r in prows:
            r.pop("n_engines_agree", None)
            r.pop("consensus_prob", None)
        rows.extend(prows)
    print(f"righe Poisson complete generate: {len(rows)}", flush=True)

    if args.dry_run:
        sels = defaultdict(set)
        for r in rows:
            sels[r["market"]].add(r["selection"])
        print("  mercati×selezioni:", {k: sorted(v) for k, v in list(sels.items())[:4]})
        print("  esempio:", {k: rows[0].get(k) for k in ("signal_uid", "prob", "prob_raw", "line", "hit", "result")})
        print("[DRY-RUN] nessuna scrittura.")
        return

    counters = {"upserted": 0, "errors": 0}
    _upsert(sb, rows, counters)
    print(f"upserted: {counters['upserted']} | errori: {counters['errors']}", flush=True)
    if counters["errors"]:
        raise SystemExit(f"ATTENZIONE: {counters['errors']} righe non scritte.")
    print("FATTO (Poisson completo + prob pura). Ora ricalcola la concordanza (SQL forzato).", flush=True)


if __name__ == "__main__":
    main()
