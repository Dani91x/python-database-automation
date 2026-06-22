"""enrich_analytics_snapshots.py — riempie freq_*/delay_* in analytics_signals con
lo SNAPSHOT POINT-IN-TIME (valore del mercato AL MOMENTO di quella partita), per
OGNI (fixture × mercato × SELEZIONE).

⚠️ FIX BUG STORICO: la v1 applicava lo STESSO snapshot a Over e Under (e non
copriva H/D/A, btts, dc, ht_ft, ...). Sbagliato: freq/ritardo sono DIVERSI per ogni
selezione. Ora ogni riga (fixture, market, selection) riceve lo snapshot DELLA SUA
selezione, calcolato con la matematica certificata di analytics_market_stats
(replica 1:1 di get_market_frequency / get_market_delays — vedi test).

POINT-IN-TIME: per ogni fixture, freq_current = mm10 (media mobile su 10 esiti fino
a quella giornata), freq_baseline = baseline lega (mode all), freq_deviation =
mm10-baseline; delay_current = ritardo a quella giornata, delay_record = record
storico, delay_avg = media ritardi. Tutto sulle partite settlate a 90'.

COPERTURA: TUTTI i mercati canonici presenti in analytics_signals per la lega
(1x2, ht_1x2, over_*, first_half_over_*, home/away_over_*, btts, first_half_btts,
double_chance, first_half_double_chance, clean_sheet_home/away, ht_ft) × tutte le
loro selezioni. Una passata cronologica per (lega, market, selection).

EFFICIENZA: aggiorna SOLO i fixture realmente presenti in analytics_signals per la
lega (no UPDATE a vuoto). Pesante → eseguire on-demand / settimanale, NON nel path
notturno critico.

Uso:
  python enrich_analytics_snapshots.py --league 256
  python enrich_analytics_snapshots.py --league 256 --dry-run
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
from analytics_market_stats import Snapshot, compute_market_snapshots

_MATCH_COLS = ("fixture_id,fixture_date,status_short,goals_home,goals_away,"
               "fulltime_home,fulltime_away,halftime_home,halftime_away")


def _fetch_matches(sb, league_id: int) -> list[dict]:
    """Tutte le partite settlate (status 90') della lega, per la serie cronologica."""
    off, out = 0, []
    while True:
        r = (sb.table("matches").select(_MATCH_COLS)
             .eq("league_id", league_id).in_("status_short", ["FT", "AET", "PEN"])
             .range(off, off + 999).execute().data)
        if not r:
            break
        out += r
        if len(r) < 1000:
            break
        off += 1000
    return out


def _fetch_signal_targets(sb, league_id: int) -> dict[str, set[str]]:
    """{market: {selezioni presenti}} per i SOLI (fixture×market×selection) in
    analytics_signals — così non si fanno UPDATE a vuoto. Ritorna anche, via
    closure, l'insieme dei fixture presenti per (market, selection)."""
    off = 0
    by_ms: dict[tuple[str, str], set[int]] = defaultdict(set)
    while True:
        r = (sb.table("analytics_signals").select("fixture_id,market,selection")
             .eq("league_id", league_id).range(off, off + 999).execute().data)
        if not r:
            break
        for x in r:
            by_ms[(x["market"], x["selection"])].add(x["fixture_id"])
        if len(r) < 1000:
            break
        off += 1000
    return by_ms


def _snap_payload(s: Snapshot) -> dict:
    return {
        "freq_baseline": s.freq_baseline,
        "freq_current": s.freq_current,
        "freq_deviation": s.freq_deviation,
        "delay_current": s.delay_current,
        "delay_record": s.delay_record,
        "delay_avg": s.delay_avg,
    }


def _update_row(sb, fid: int, market: str, selection: str, payload: dict,
                counters: dict) -> bool:
    for attempt in range(3):
        try:
            (sb.table("analytics_signals").update(payload)
             .eq("fixture_id", fid).eq("market", market)
             .eq("selection", selection).execute())
            return True
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                counters["failed"] += 1
                print(f"    [ERR] fix {fid} {market}/{selection}: {str(e)[:80]}")
            else:
                time.sleep(0.4 * (attempt + 1))
    return False


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sb = get_supabase_client()

    by_ms = _fetch_signal_targets(sb, args.league)
    if not by_ms:
        print(f"Lega {args.league}: nessuna riga in analytics_signals. Nulla da fare.")
        return
    markets = sorted({m for (m, _) in by_ms})
    n_targets = sum(len(v) for v in by_ms.values())
    print(f"Lega {args.league}: {len(markets)} mercati, "
          f"{len(by_ms)} (market×selection), {n_targets} righe-target in tabella")

    matches = _fetch_matches(sb, args.league)
    print(f"  partite settlate (serie cronologica): {len(matches)}")
    if not matches:
        print("  nessuna partita settlata: impossibile calcolare snapshot.")
        return

    counters = {"failed": 0}
    updated = 0
    dry_examples: list[str] = []
    for (market, selection), present_fids in sorted(by_ms.items()):
        snaps = compute_market_snapshots(market, selection, matches)
        # solo i fixture realmente in tabella per QUESTA (market, selection)
        hit_fids = present_fids & set(snaps)
        if args.dry_run:
            ex = next(iter(hit_fids), None)
            if ex is not None and len(dry_examples) < 40:
                dry_examples.append(f"    {market}/{selection} fix {ex}: "
                                    f"{_snap_payload(snaps[ex])}")
            continue
        for fid in hit_fids:
            if _update_row(sb, fid, market, selection,
                           _snap_payload(snaps[fid]), counters):
                updated += 1

    if args.dry_run:
        print(f"\n[DRY-RUN] esempi snapshot per-selezione "
              f"(nota: Over≠Under, H≠D≠A):")
        for line in dry_examples:
            print(line)
        # confronto esplicito Over vs Under e H/D/A su una stessa fixture
        _dry_diff(matches, by_ms)
        return

    print(f"\nAggiornati {updated} righe (fixture×market×selection) | "
          f"falliti {counters['failed']}")
    if counters["failed"]:
        raise SystemExit(f"ATTENZIONE: {counters['failed']} update falliti.")


def _dry_diff(matches: list[dict], by_ms: dict) -> None:
    """Mostra, su una stessa fixture, che Over≠Under e H≠D≠A (la prova del fix)."""
    def first_common(m, sels):
        sets = [by_ms.get((m, s), set()) for s in sels]
        common = set.intersection(*[s for s in sets if s]) if all(sets) else set()
        return next(iter(common), None)

    fid = first_common("over_2_5", ["Over", "Under"])
    if fid is not None:
        ov = compute_market_snapshots("over_2_5", "Over", matches).get(fid)
        un = compute_market_snapshots("over_2_5", "Under", matches).get(fid)
        print(f"\n  PROVA per-selezione over_2_5 fix {fid}:")
        print(f"    Over : {_snap_payload(ov)}")
        print(f"    Under: {_snap_payload(un)}")
    fid2 = first_common("1x2", ["H", "D", "A"])
    if fid2 is not None:
        H = compute_market_snapshots("1x2", "H", matches).get(fid2)
        D = compute_market_snapshots("1x2", "D", matches).get(fid2)
        A = compute_market_snapshots("1x2", "A", matches).get(fid2)
        print(f"  PROVA per-selezione 1x2 fix {fid2}:")
        print(f"    H: {_snap_payload(H)}")
        print(f"    D: {_snap_payload(D)}")
        print(f"    A: {_snap_payload(A)}")


if __name__ == "__main__":
    main()
