"""merge_engine_signals.py — porta il firehose engine_signals (48k: piazzate/
scartate/no_signal + valore + motivo + metriche) dentro il centro di controllo.

Scrive DUE layer (idempotente, upsert):
  • analytics_decisions : la DECISIONE (decision_logic='google_sheets'), con tutti
    i dati di contorno (status, reject reason, edge/odds/stake/pnl, metriche, ...).
  • analytics_signals   : la PREVISIONE corrispondente (engine, mercato, prob),
    con hit RI-SETTLATO a 90' → così lo storico Poisson+ML (leak-free, erano
    predizioni live) entra nella pagella e l'ML non è più "vuoto".

I segnali engine_signals erano predizioni LIVE pre-partita → oos_valid=True.

Uso:
  python merge_engine_signals.py --dry-run
  python merge_engine_signals.py                 # tutto lo storico
  python merge_engine_signals.py --since 2026-06-01
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client
from analytics_settlement import ft_score_90, ht_score, hit

DECISION_LOGIC = "google_sheets"  # logica decisionale attuale (money_management/Sheets)

# codice engine_signals → (mercato canonico, selezione canonica)
DECODE = {
    "H": ("1x2", "H"), "D": ("1x2", "D"), "A": ("1x2", "A"),
    "O25": ("over_2_5", "Over"), "U25": ("over_2_5", "Under"),
    "O15": ("over_1_5", "Over"), "U15": ("over_1_5", "Under"),
    "O35": ("over_3_5", "Over"), "U35": ("over_3_5", "Under"),
    "BTTS": ("btts", "Yes"), "BTTS_NO": ("btts", "No"),
    "HT05": ("first_half_over_0_5", "Over"), "HT_U05": ("first_half_over_0_5", "Under"),
    "HT_H": ("ht_1x2", "H"), "HT_D": ("ht_1x2", "D"), "HT_A": ("ht_1x2", "A"),
}

_VALUE_FIELDS = ("prob_raw", "edge", "score", "implied_prob", "fair_odds", "odds", "stake",
                 "pnl", "closing_odds", "clv", "available_size", "cal_source", "trust_score",
                 "z_score", "bss", "reliability_multiplier", "safety_vault", "other_engine",
                 "other_engine_prob", "agreement_strength", "is_best", "reject_filter", "reject_detail")


def _fetch_engine_signals(sb, since: Optional[str], page=1000):
    off = 0
    while True:
        q = sb.table("engine_signals").select("*")
        if since:
            q = q.gte("run_date", since)
        r = q.range(off, off + page - 1).execute()
        batch = r.data or []
        if not batch:
            break
        yield batch
        if len(batch) < page:
            break
        off += page


def _fetch_matches(sb, fids):
    out = {}
    fids = list({f for f in fids if f})
    for i in range(0, len(fids), 300):
        chunk = fids[i:i + 300]
        r = (sb.table("matches")
             .select("fixture_id,status_short,goals_home,goals_away,fulltime_home,fulltime_away,halftime_home,halftime_away")
             .in_("fixture_id", chunk).execute())
        for m in r.data or []:
            out[m["fixture_id"]] = m
    return out


def _build(es: dict, match: Optional[dict]) -> tuple[dict, Optional[dict]]:
    """Ritorna (riga analytics_decisions, riga analytics_signals|None)."""
    code = es.get("market")
    fid = es["fixture_id"]
    canon = DECODE.get(code)
    market, selection = canon if canon else ("(none)", "(none)")

    ft = ht = None
    h = None
    settled = False
    g = {"goals_home": None, "goals_away": None, "total_goals": None, "ht_home": None, "ht_away": None}
    if match:
        ft, ht = ft_score_90(match), ht_score(match)
        settled = ft is not None
        if ft is not None:
            g["goals_home"], g["goals_away"], g["total_goals"] = ft[0], ft[1], ft[0] + ft[1]
        if ht is not None:
            g["ht_home"], g["ht_away"] = ht[0], ht[1]
        if canon:
            h = hit(market, selection, ft, ht)

    run_date = es.get("run_date")
    ctx = {
        "engine": es.get("engine"), "fixture_id": fid, "league_id": es.get("league_id"),
        "league_name": es.get("league_name"), "season_year": es.get("season_year"),
        "home_team": es.get("home_team"), "away_team": es.get("away_team"), "kickoff": es.get("kickoff"),
        "market": market, "selection": selection, "market_label": es.get("market_label"),
    }
    decision = {
        "decision_uid": f"{DECISION_LOGIC}|{es.get('engine')}|{fid}|{market}|{selection}|{run_date}",
        "decision_logic": DECISION_LOGIC, **ctx, "run_date": run_date,
        "status": es.get("status"),
        "prob": es.get("prob_calibrated"),
        "result_ft": es.get("result"), "hit": h, "settled": settled,
        **{k: es.get(k) for k in _VALUE_FIELDS},
    }

    # PREVISIONE: solo se il mercato è canonico (NO_SIGNAL non è una previsione).
    # OWNERSHIP COLONNE — il merger scrive SOLO placed/status (sue) + l'esito a 90'
    # (coerente, stesso calcolo del populator) + il contesto. NON scrive la `prob`:
    # ⚠️ FIX C1 (look-ahead-free): engine_signals.prob_calibrated è la prob calibrata
    # PER-SCOMMESSA (money_management, calibrazione per-bin NON-uniforme → overround,
    # somma>1, può INVERTIRE l'argmax/top-pick). La `prob` di analytics_signals deve
    # essere la PREVISIONE PURA del motore (markets_calibrated/targets), scritta dal
    # POPULATOR. Il merger NON la tocca più → niente direzione invertita. La prob
    # per-scommessa resta in analytics_decisions (record `decision`), dove è corretta.
    # NON tocca neppure: fair_odds, line, prob_raw, n_engines_agree, consensus_prob,
    # first_goal_minute, reliable, freq_*/delay_* → l'upsert preserva i valori già
    # presenti. PROVENIENZA prob delle righe SOLO-merge:
    #   • Poisson storico → ripopolato PURO da fix_storico_prob (markets_calibrated);
    #   • ML storico → prob CALIBRATA del modello (engine_signals.prob_calibrated,
    #     mappata su (fixture,market,selezione) canonici): distribuzione che somma a 1
    #     quando tutte le selezioni sono presenti (softmax, NON overround → argmax
    #     corretto), prob grezza per-selezione quando engine_signals ne aveva solo alcune.
    #   • Forward → la prob la scrive il populator (extract_*), questo ramo non serve.
    prediction = None
    if canon and es.get("prob_calibrated") is not None:
        result = "WON" if h is True else ("LOST" if h is False else None)
        prediction = {
            "signal_uid": f"{es.get('engine')}|{fid}|{market}|{selection}",
            "engine": es.get("engine"), "generated_at": es.get("emitted_at"),
            "fixture_id": fid, "league_id": es.get("league_id"), "league_name": es.get("league_name"),
            "season_year": es.get("season_year"), "home_team": es.get("home_team"),
            "away_team": es.get("away_team"), "kickoff": es.get("kickoff"),
            "market": market, "selection": selection, "direction": es.get("direction") or "back",
            "placed": es.get("status") == "PLACED", "status": es.get("status"),
            "settled": settled, "result": result, "hit": h, **g,
            "oos_valid": True,
        }
    return decision, prediction


def _upsert(sb, table, rows, conflict, dry, counters, key):
    if dry or not rows:
        return
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        for attempt in range(3):
            try:
                sb.table(table).upsert(chunk, on_conflict=conflict).execute()
                counters[key] += len(chunk)
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    counters["errors"] += len(chunk)
                    print(f"\n  [ERR] {table}: {str(e)[:110]}")
                else:
                    time.sleep(0.4 * (attempt + 1))


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="solo run_date >= YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=None, help="incrementale: run_date ultimi N giorni")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    since = args.since
    if args.days:
        since = (datetime.now(timezone.utc) - timedelta(days=args.days)).date().isoformat()
    sb = get_supabase_client()

    counters = {"decisions": 0, "predictions": 0, "errors": 0}
    unknown_codes: dict[str, int] = {}
    n_es = 0
    for batch in _fetch_engine_signals(sb, since):
        matches = _fetch_matches(sb, [b["fixture_id"] for b in batch])
        decisions, predictions = [], []
        for es in batch:
            code = es.get("market")
            # codice non-mappato e non NO_SIGNAL → previsione persa: lo segnaliamo
            if code not in DECODE and es.get("status") != "NO_SIGNAL":
                unknown_codes[code] = unknown_codes.get(code, 0) + 1
            d, p = _build(es, matches.get(es["fixture_id"]))
            decisions.append(d)
            if p:
                predictions.append(p)
        n_es += len(batch)
        _upsert(sb, "analytics_decisions", decisions, "decision_uid", args.dry_run, counters, "decisions")
        _upsert(sb, "analytics_signals", predictions, "signal_uid", args.dry_run, counters, "predictions")
        print(f"  ...engine_signals {n_es} | decisioni {counters['decisions']} | previsioni {counters['predictions']} | err {counters['errors']}", end="\r")
    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}engine_signals {n_es} | decisioni {counters['decisions']} | "
          f"previsioni {counters['predictions']} | errori {counters['errors']}")
    if unknown_codes:
        print(f"⚠️ CODICI-MERCATO NON MAPPATI (previsione persa, aggiungere a DECODE): {unknown_codes}")
    if counters["errors"]:
        raise SystemExit(f"ATTENZIONE: {counters['errors']} righe non scritte.")


if __name__ == "__main__":
    main()
