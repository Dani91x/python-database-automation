"""
backfill_engine_signals.py
Popola engine_signals dallo storico gia' esistente (Betfair/mm_history.json), facendo il join
con `matches` per esito/lega/squadre/kickoff. Idempotente (upsert on_conflict=signal_uid).

SICUREZZA: legge mm_history.json in SOLA LETTURA; sul DB fa solo SELECT su `matches` e UPSERT su
`engine_signals`. NON tocca signal_history ne' altri file di produzione.

USO:
  python migrations/backfill_engine_signals.py --dry-run         # nessuna scrittura, solo conteggi
  python migrations/backfill_engine_signals.py                   # esegue l'upsert
  python migrations/backfill_engine_signals.py --since 2026-05-01
"""
from __future__ import annotations
import os
import sys
import json
import argparse
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db_client import get_supabase_client
from Betfair.reject_categories import classify_reject_reason

COMM = 0.05
HISTORY = os.path.join(ROOT, "Betfair", "mm_history.json")
LEAGUE_NAMES_CSV = r"C:\Users\Admin\Desktop\SIGNAL_ANALYSIS\league_names.csv"
NO_SIGNAL_MARKET = "(none)"


# --- valutazione esito: replica VERBATIM di money_management._evaluate_bet_result ---
def evaluate_bet(market, gh, ga, hth, hta):
    gh = int(gh or 0); ga = int(ga or 0)
    if market == "H":   return gh > ga
    if market == "D":   return gh == ga
    if market == "A":   return gh < ga
    if market == "O25": return (gh + ga) >= 3
    if market == "U25": return (gh + ga) < 3
    if market == "O15": return (gh + ga) >= 2
    if market == "U15": return (gh + ga) < 2
    if market == "O35": return (gh + ga) >= 4
    if market == "U35": return (gh + ga) < 4
    if market == "BTTS":    return gh >= 1 and ga >= 1
    if market == "BTTS_NO": return gh == 0 or ga == 0
    if market in ("HT05", "HT_U05", "HT_H", "HT_D", "HT_A"):
        if hth is None or hta is None:
            return None
        hth = int(hth); hta = int(hta)
        if market == "HT05":   return (hth + hta) >= 1
        if market == "HT_U05": return (hth + hta) == 0
        if market == "HT_H":   return hth > hta
        if market == "HT_D":   return hth == hta
        if market == "HT_A":   return hth < hta
    return None


def norm_engine(track):
    t = (track or "").lower()
    if t in ("poisson", "p", "pois"): return "poisson"
    if t in ("ml", "m"): return "ml"
    return t or "?"


def split_event(event_name):
    if event_name and " v " in event_name:
        h, _, a = event_name.partition(" v ")
        return h.strip(), a.strip()
    return None, None


def load_league_names():
    m = {}
    if os.path.exists(LEAGUE_NAMES_CSV):
        import csv
        with open(LEAGUE_NAMES_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    m[int(row["league_id"])] = row.get("league_name")
                except (ValueError, TypeError, KeyError):
                    pass
    return m


def flatten_history(history, since=None):
    """Ritorna una lista di record grezzi (un dict per segnale emesso)."""
    recs = []
    for day in history:
        d = day.get("date")
        if since and d and d < since:
            continue
        for s in day.get("slots", []):
            recs.append(_placed_rec(s, d, "poisson"))
        for s in day.get("ml_slots", []):
            recs.append(_placed_rec(s, d, "ml"))
        for r in day.get("rejected", []):
            recs.append(_rejected_rec(r, d))
    return [r for r in recs if r and r.get("fixture_id") is not None]


def _placed_rec(s, d, engine):
    return dict(
        engine=engine, run_date=d, status="PLACED",
        fixture_id=s.get("fixture_id"), event_name=s.get("event_name", ""),
        market=s.get("market"), market_label=s.get("market_label"),
        prob=s.get("prob"), odds=s.get("odds"), edge=s.get("edge"),
        score=s.get("score"), stake=s.get("stake"),
        is_best=bool(s.get("is_best", False)),
        hist_result=s.get("result"), hist_pnl=s.get("pnl"),
        reason=None,
    )


def _rejected_rec(r, d):
    has_nums = r.get("prob") is not None and r.get("edge") is not None and r.get("market")
    return dict(
        engine=norm_engine(r.get("track")), run_date=r.get("date") or d,
        status="REJECTED" if has_nums else "NO_SIGNAL",
        fixture_id=r.get("fixture_id"), event_name=r.get("event", ""),
        market=r.get("market") if has_nums else NO_SIGNAL_MARKET,
        market_label=r.get("market_label") if has_nums else "No signal",
        prob=r.get("prob"), odds=r.get("odds"), edge=r.get("edge"),
        score=None, stake=None, is_best=None,
        hist_result=None, hist_pnl=None,
        reason=r.get("reason", ""),
    )


def fetch_matches(sb, fixture_ids):
    mmap = {}
    fids = sorted({int(x) for x in fixture_ids})
    for i in range(0, len(fids), 200):
        chunk = fids[i:i + 200]
        resp = sb.table("matches").select(
            "fixture_id, league_id, season_year, fixture_date, status_short, "
            "goals_home, goals_away, halftime_home, halftime_away, home_team_name, away_team_name"
        ).in_("fixture_id", chunk).execute()
        for m in (resp.data or []):
            mmap[int(m["fixture_id"])] = m
    return mmap


def build_rows(recs, mmap, lname_map):
    # 1) costruisci le righe base
    rows = []
    for r in recs:
        fid = int(r["fixture_id"])
        m = mmap.get(fid, {})
        gh = m.get("goals_home"); ga = m.get("goals_away")
        hth = m.get("halftime_home"); hta = m.get("halftime_away")
        status_short = str(m.get("status_short") or "").upper()
        resolved = status_short in ("FT", "AET", "PEN")

        # market sempre valorizzato (NO_SIGNAL usa sentinella) -> signal_uid stabile/idempotente
        market = r["market"] or NO_SIGNAL_MARKET
        won = None
        # valuta SOLO con gol realmente presenti (evita 0-0 fittizio su gap dati -> esito corrotto)
        if resolved and market != NO_SIGNAL_MARKET and gh is not None and ga is not None:
            won = evaluate_bet(market, gh, ga, hth, hta)

        # esito + pnl
        result = "PENDING"; pnl = None
        if won is not None:
            result = "VINTO ✅" if won else "PERSO ❌"
            if r["status"] == "PLACED" and r.get("stake"):
                st = r["stake"]; od = r.get("odds")
                if od and od > 1:
                    pnl = round(st * (od - 1) * (1 - COMM), 2) if won else round(-st, 2)

        prob = r.get("prob"); odds = r.get("odds")
        home, away = split_event(r.get("event_name"))

        rows.append(dict(
            signal_uid=f"{r['engine']}|{fid}|{market}|{r['run_date']}",
            run_date=r["run_date"], emitted_at=f"{r['run_date']}T00:00:00Z",
            engine=r["engine"],
            fixture_id=fid, league_id=m.get("league_id"),
            league_name=lname_map.get(m.get("league_id")),
            season_year=m.get("season_year"),
            home_team=m.get("home_team_name") or home,
            away_team=m.get("away_team_name") or away,
            kickoff=m.get("fixture_date"),
            market=market, market_label=r.get("market_label"), direction="back",
            prob_raw=None, prob_calibrated=prob, edge=r.get("edge"), score=r.get("score"),
            fair_odds=round(1.0 / prob, 4) if prob else None,
            implied_prob=round(1.0 / odds, 4) if odds else None,
            cal_source=None, trust_score=None, z_score=None, safety_vault=None,
            bss=None, reliability_multiplier=None,
            odds=odds, available_size=None,
            status=r["status"], is_best=r.get("is_best"),
            reject_filter=classify_reject_reason(r["reason"]) if r["status"] != "PLACED" else None,
            reject_detail=r.get("reason"), stake=r.get("stake"),
            concordant=None, other_engine=None, other_engine_prob=None,
            other_engine_status=None, agreement_strength=None,
            result=result, pnl=pnl,
            closing_odds=None, clv=None,
            goals_home=gh if resolved else None, goals_away=ga if resolved else None,
            ht_home=hth if resolved else None, ht_away=hta if resolved else None,
            backfilled=True,
        ))

    # 2) concordanza: per (fixture, market, run_date) guarda l'altro motore
    by_key = {}
    for row in rows:
        if row["market"] == NO_SIGNAL_MARKET:
            continue
        by_key.setdefault((row["fixture_id"], row["market"], row["run_date"]), {})[row["engine"]] = row
    for (fid, mk, rd), engines in by_key.items():
        for eng, row in engines.items():
            other = next((o for e, o in engines.items() if e != eng), None)
            if other is None:
                continue
            row["other_engine"] = other["engine"]
            row["other_engine_prob"] = other["prob_calibrated"]
            row["other_engine_status"] = other["status"]
            row["concordant"] = (row["status"] == "PLACED" and other["status"] == "PLACED")
            p, po = row["prob_calibrated"], other["prob_calibrated"]
            if p is not None and po is not None:
                row["agreement_strength"] = round(1 - abs(p - po), 4)

    # 3) dedup per signal_uid: preferisci la riga RISOLTA su una PENDING (no regressione esito)
    dedup = {}
    for row in rows:
        existing = dedup.get(row["signal_uid"])
        if existing is None or existing["result"] == "PENDING":
            dedup[row["signal_uid"]] = row
    return list(dedup.values())


def run_backfill(since: str | None = None, dry_run: bool = False, quiet: bool = False) -> int:
    """Popola/aggiorna engine_signals dallo storico. Idempotente (upsert on_conflict=signal_uid).
    Ritorna il numero di righe upsertate (o costruite, in dry-run). Pensata per essere richiamata
    sia da CLI sia dalla pipeline (best-effort)."""
    def log(*a):
        if not quiet:
            print(*a)

    log("=" * 60)
    log("  BACKFILL engine_signals" + ("  [DRY-RUN]" if dry_run else ""))
    log("=" * 60)
    with open(HISTORY, encoding="utf-8") as f:
        history = json.load(f)
    log(f"Giorni nello storico: {len(history)}")

    recs = flatten_history(history, since=since)
    log(f"Record grezzi (segnali emessi): {len(recs)}")

    sb = get_supabase_client()
    lname_map = load_league_names()
    log(f"Mappa nomi-lega: {len(lname_map)} leghe")

    mmap = fetch_matches(sb, [r["fixture_id"] for r in recs])
    log(f"Fixture trovate in matches: {len(mmap)}")

    rows = build_rows(recs, mmap, lname_map)
    by_status = Counter(r["status"] for r in rows)
    by_engine = Counter(r["engine"] for r in rows)
    resolved = sum(1 for r in rows if r["result"] != "PENDING")
    concord = sum(1 for r in rows if r["concordant"] is True)
    log(f"\nRighe finali (dedup): {len(rows)}")
    log(f"  per stato : {dict(by_status)}")
    log(f"  per motore: {dict(by_engine)}")
    log(f"  risolte (esito noto): {resolved}")
    log(f"  concordi (entrambi PLACED): {concord}")

    if dry_run:
        log("\n[DRY-RUN] nessuna scrittura. Esempio riga:")
        if rows:
            log(json.dumps(rows[0], ensure_ascii=False, indent=2, default=str))
        return len(rows)

    log("\nUpsert su engine_signals (chunk 500)...")
    n = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        sb.table("engine_signals").upsert(chunk, on_conflict="signal_uid").execute()
        n += len(chunk)
        log(f"  {n}/{len(rows)}")
    log(f"[OK] {n} righe upsertate in engine_signals.")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--since", default=None, help="YYYY-MM-DD: solo run_date >= since")
    args = ap.parse_args()
    run_backfill(since=args.since, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
