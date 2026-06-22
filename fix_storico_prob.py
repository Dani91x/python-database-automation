"""fix_storico_prob.py — FIX C1/C2 sullo storico analytics_signals.

Ri-scrive la `prob` delle righe storiche dalla FONTE PURA (non più la prob
per-scommessa overround di engine_signals che invertiva l'argmax nel 27% dei 1x2):
  • Poisson: db_json_analisi.markets_calibrated (normalizzato, somma=1) — via extract_poisson.
  • ML: prob per-scommessa di engine_signals NORMALIZZATA per (fixture, market)
    (l'ML storico era forward-only: model_predictions_json non esiste → unica fonte).
  • altri motori: prob invariata.
Poi ricalcola n_engines_agree/consensus_prob con la semantica TOP-PICK (argmax per
motore; quanti motori hanno la stessa selezione come pick). Scrittura BULK via staging.

Uso: python fix_storico_prob.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client
from build_analytics_signals import extract_poisson


def _fetch_all_rows(sb):
    sel = "signal_uid,fixture_id,engine,market,selection,prob"
    off, out = 0, []
    while True:
        r = sb.table("analytics_signals").select(sel).range(off, off + 999).execute().data
        if not r:
            break
        out += r
        if len(r) < 1000:
            break
        off += 1000
    return out


def _fetch_poisson_dists(sb, fids: list[int]) -> dict[int, dict]:
    """{fixture_id: {market: {selection_canonica: (prob, raw)}}} dal markets_calibrated."""
    out: dict[int, dict] = {}
    for i in range(0, len(fids), 200):
        chunk = fids[i:i + 200]
        r = (sb.table("fixture_predictions").select("fixture_id,db_json_analisi")
             .in_("fixture_id", chunk).execute().data)
        for row in r or []:
            an = row.get("db_json_analisi")
            if isinstance(an, dict) and an.get("markets_calibrated"):
                out[row["fixture_id"]] = extract_poisson(an)
    return out


def _correct_fixture(frows: list[dict], pois: dict) -> list[dict]:
    """Ritorna [{signal_uid, prob, fair_odds, n_engines_agree, consensus_prob}]."""
    # prob corretta per ogni riga:
    #  • Poisson → markets_calibrated (PURA, normalizzata) = FIX C1 (no inversione argmax)
    #  • ML / altri → prob INVARIATA (engine_signals per-scommessa è l'unica fonte
    #    storica; normalizzarla su selezioni incomplete distorcerebbe la confidenza)
    new_prob: dict[tuple, Optional[float]] = {}
    for r in frows:
        e, mk, sel = r["engine"], r["market"], r["selection"]
        if e == "poisson":
            cell = pois.get(mk, {}).get(sel)
            p = cell[0] if cell else r["prob"]   # fallback: prob esistente se manca mc
        else:
            p = r["prob"]
        new_prob[(e, mk, sel)] = p

    # top-pick di ogni motore per (market):
    #  • Poisson → argmax della DISTRIBUZIONE COMPLETA markets_calibrated (anche
    #    selezioni non in tabella: se il top è il Pareggio e la riga D manca, il
    #    top resta D — coerente col populator forward);
    #  • ML/altri → argmax delle selezioni disponibili in tabella (limite storico).
    picks: dict[str, dict[str, str]] = defaultdict(dict)
    markets = {mk for (_, mk, _) in new_prob}
    for mk in markets:
        pdist = {sel: cell[0] for sel, cell in pois.get(mk, {}).items() if cell and cell[0] is not None}
        if pdist:
            picks[mk]["poisson"] = max(pdist, key=pdist.get)
        for e in {e for (e, mk2, _) in new_prob if mk2 == mk and e != "poisson"}:
            sels = {sel: new_prob[(e, mk, sel)] for (e2, mk2, sel) in new_prob
                    if e2 == e and mk2 == mk and new_prob[(e2, mk2, sel)] is not None}
            if sels:
                picks[mk][e] = max(sels, key=sels.get)

    out = []
    for r in frows:
        e, mk, sel = r["engine"], r["market"], r["selection"]
        p = new_prob[(e, mk, sel)]
        agree = [eng for eng, top in picks.get(mk, {}).items() if top == sel]
        ps = [new_prob[(eng, mk, sel)] for eng in agree if new_prob.get((eng, mk, sel)) is not None]
        out.append({
            "signal_uid": r["signal_uid"],
            "prob": round(p, 6) if p is not None else None,
            "fair_odds": round(1.0 / p, 4) if (p and p > 0) else None,
            "n_engines_agree": len(agree),
            "consensus_prob": round(sum(ps) / len(ps), 4) if ps else None,
        })
    return out


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sb = get_supabase_client()

    rows = _fetch_all_rows(sb)
    by_fix: dict[int, list] = defaultdict(list)
    for r in rows:
        by_fix[r["fixture_id"]].append(r)
    print(f"righe: {len(rows)} | fixture: {len(by_fix)}", flush=True)

    fids = list(by_fix)
    pois_all = _fetch_poisson_dists(sb, fids)
    print(f"fixture con markets_calibrated Poisson: {len(pois_all)}", flush=True)

    payload = []
    inv = 0
    for fid, frows in by_fix.items():
        corr = _correct_fixture(frows, pois_all.get(fid, {}))
        payload.extend(corr)
    print(f"correzioni calcolate: {len(payload)}", flush=True)

    if args.dry_run:
        ex = payload[:4]
        for e in ex:
            print("   ", e)
        print("[DRY-RUN] nessuna scrittura.")
        return

    # bulk: staging + flush
    n = 0
    for i in range(0, len(payload), 500):
        chunk = [p for p in payload[i:i + 500] if p["prob"] is not None]
        if not chunk:
            continue
        for attempt in range(3):
            try:
                sb.table("analytics_prob_staging").upsert(chunk, on_conflict="signal_uid").execute()
                n += len(chunk)
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    print(f"  [ERR] staging chunk: {str(e)[:100]}")
                else:
                    time.sleep(0.4 * (attempt + 1))
    print(f"staged: {n}. Flush...", flush=True)
    sb.rpc("flush_analytics_prob_staging").execute()
    print("FATTO (prob/concordanza storiche corrette).", flush=True)


if __name__ == "__main__":
    main()
