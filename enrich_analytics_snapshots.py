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

──────────────────────────────────────────────────────────────────────────────
SCRITTURA BULK (veloce + poco stressante per il DB):
  Niente più UPDATE riga-per-riga (46k round-trip → I/O-bound). Ora:
    1) calcola gli snapshot in Python (compute_market_snapshots, INVARIATO),
    2) li carica in `analytics_snap_staging` via upsert a BATCH (500/volta),
    3) UN SOLO UPDATE ... FROM scopato alla lega (RPC flush_analytics_snap_staging),
    4) pulizia staging per lega.
  → 1 UPDATE per lega invece di N. I numeri scritti sono IDENTICI, riga-per-riga,
  a quelli del vecchio metodo (lo staging è solo trasporto + JOIN set-based).

MODO INCREMENTALE (--days N / --today, per le partite del GIORNO, pre-match):
  Enrichisce SOLO le fixture recenti presenti in analytics_signals. ATTENZIONE
  POINT-IN-TIME: le partite del giorno NON sono ancora settlate → il loro
  freq/ritardo è lo STATO CORRENTE del mercato (il valore "in entrata", calcolato
  sulla storia settlata PRECEDENTE: delay_current = ritardo dopo l'ultima partita
  giocata, freq_current = mm10 corrente). Le fixture recenti GIÀ settlate ricevono
  invece il loro snapshot point-in-time normale. Vedi compute_current_state.

Uso:
  python enrich_analytics_snapshots.py --league 256              # storico lega
  python enrich_analytics_snapshots.py --league 256 --dry-run
  python enrich_analytics_snapshots.py --days 4                  # incrementale (action)
  python enrich_analytics_snapshots.py --today                   # solo oggi
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client
from analytics_market_stats import (
    Snapshot,
    compute_current_state,
    compute_market_snapshots,
)

_MATCH_COLS = ("fixture_id,fixture_date,status_short,goals_home,goals_away,"
               "fulltime_home,fulltime_away,halftime_home,halftime_away")
_STAGE_BATCH = 500


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


def _fetch_signal_targets(sb, league_id: int) -> dict[tuple[str, str], set[int]]:
    """{(market, selection): {fixture presenti}} per i SOLI (fixture×market×selection)
    in analytics_signals della lega — così non si fanno UPDATE a vuoto."""
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


def _stage_row(fid: int, market: str, selection: str, s: Snapshot) -> dict:
    return {"fixture_id": fid, "market": market, "selection": selection, **_snap_payload(s)}


def _flush_staging(sb, league_id: int, stage_rows: list[dict], counters: dict) -> int:
    """Carica gli snapshot in staging (upsert a batch) poi UN SOLO UPDATE ... FROM
    via RPC scopata alla lega; ritorna le righe aggiornate. La RPC pulisce la
    staging per la lega. Niente UPDATE riga-per-riga."""
    if not stage_rows:
        return 0
    # 1) upsert a batch nella staging
    for i in range(0, len(stage_rows), _STAGE_BATCH):
        chunk = stage_rows[i:i + _STAGE_BATCH]
        for attempt in range(3):
            try:
                (sb.table("analytics_snap_staging")
                 .upsert(chunk, on_conflict="fixture_id,market,selection").execute())
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    counters["failed"] += len(chunk)
                    print(f"    [ERR staging] {len(chunk)} righe: {str(e)[:80]}")
                else:
                    time.sleep(0.4 * (attempt + 1))
    # 2) UN SOLO UPDATE FROM (+ pulizia staging) via RPC
    for attempt in range(3):
        try:
            res = sb.rpc("flush_analytics_snap_staging",
                         {"p_league_id": league_id}).execute()
            return res.data if isinstance(res.data, int) else 0
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                counters["failed"] += len(stage_rows)
                print(f"    [ERR flush lega {league_id}] {str(e)[:80]}")
                return 0
            time.sleep(0.5 * (attempt + 1))
    return 0


def _build_stage_rows(by_ms: dict[tuple[str, str], set[int]],
                      matches: list[dict],
                      current_fids: Optional[set[int]] = None,
                      dry_examples: Optional[list[str]] = None) -> list[dict]:
    """Costruisce le righe di staging per la lega.
    - per i fixture SETTLATI (in matches): snapshot point-in-time (compute_market_snapshots).
    - per i fixture in `current_fids` (recenti/non-settlati, modo incrementale):
      STATO CORRENTE del mercato (compute_current_state) — il valore "in entrata".
    """
    current_fids = current_fids or set()
    stage: list[dict] = []
    for (market, selection), present_fids in sorted(by_ms.items()):
        snaps = compute_market_snapshots(market, selection, matches)
        # fixture settlati realmente in tabella per QUESTA (market, selection)
        hit_fids = present_fids & set(snaps)
        for fid in hit_fids:
            if dry_examples is not None and len(dry_examples) < 40:
                dry_examples.append(f"    {market}/{selection} fix {fid}: {_snap_payload(snaps[fid])}")
            stage.append(_stage_row(fid, market, selection, snaps[fid]))
        # fixture recenti NON settlati di questa (market, selection) → stato corrente
        cur_targets = (present_fids & current_fids) - set(snaps)
        if cur_targets:
            cur = compute_current_state(market, selection, matches)
            for fid in cur_targets:
                if dry_examples is not None and len(dry_examples) < 40:
                    dry_examples.append(f"    [CUR] {market}/{selection} fix {fid}: {_snap_payload(cur)}")
                stage.append(_stage_row(fid, market, selection, cur))
    return stage


def _enrich_league(sb, league_id: int, dry: bool, counters: dict,
                   current_fids: Optional[set[int]] = None) -> tuple[int, int]:
    """Enrichisce UNA lega (bulk). Ritorna (n_righe_target, n_aggiornate)."""
    by_ms = _fetch_signal_targets(sb, league_id)
    if not by_ms:
        return 0, 0
    matches = _fetch_matches(sb, league_id)
    if not matches:
        return sum(len(v) for v in by_ms.values()), 0
    dry_examples: list[str] = [] if dry else None  # type: ignore[assignment]
    stage = _build_stage_rows(by_ms, matches, current_fids, dry_examples)
    n_target = len(stage)
    if dry:
        print(f"  [DRY-RUN] lega {league_id}: {n_target} righe da scrivere (bulk). Esempi:")
        for line in (dry_examples or [])[:20]:
            print(line)
        return n_target, 0
    updated = _flush_staging(sb, league_id, stage, counters)
    return n_target, updated


def _recent_targets(sb, days: int) -> dict[int, set[int]]:
    """{league_id: {fixture recenti}} per le righe di analytics_signals con
    kickoff negli ultimi `days` giorni. Serve al modo incrementale: enrichisce
    SOLO queste leghe, e tratta i loro fixture non-settlati come stato corrente."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    off = 0
    out: dict[int, set[int]] = defaultdict(set)
    while True:
        r = (sb.table("analytics_signals").select("league_id,fixture_id")
             .gte("kickoff", since).range(off, off + 999).execute().data)
        if not r:
            break
        for x in r:
            if x.get("league_id") is not None:
                out[x["league_id"]].add(x["fixture_id"])
        if len(r) < 1000:
            break
        off += 1000
    return out


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", type=int, default=None, help="storico di UNA lega")
    ap.add_argument("--days", type=int, default=None,
                    help="incrementale: solo fixture (per lega) con kickoff negli ultimi N giorni")
    ap.add_argument("--today", action="store_true", help="alias di --days 1")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.league and not args.days and not args.today:
        raise SystemExit("Specificare --league N | --days N | --today")

    sb = get_supabase_client()
    counters = {"failed": 0}

    # ---- MODO STORICO: una lega intera (point-in-time su tutte le settlate) ----
    if args.league:
        n_target, updated = _enrich_league(sb, args.league, args.dry_run, counters)
        if n_target == 0:
            print(f"Lega {args.league}: nessuna riga in analytics_signals. Nulla da fare.")
            return
        print(f"\nLega {args.league}: {n_target} righe-target | aggiornate {updated} "
              f"(BULK) | falliti {counters['failed']}")
        if counters["failed"]:
            raise SystemExit(f"ATTENZIONE: {counters['failed']} righe non scritte.")
        return

    # ---- MODO INCREMENTALE: leghe con fixture recenti (point-in-time + stato corrente) ----
    days = args.days if args.days else 1
    recent = _recent_targets(sb, days)
    if not recent:
        print(f"Incrementale (--days {days}): nessuna fixture recente in analytics_signals.")
        return
    print(f"Incrementale (--days {days}): {len(recent)} leghe con fixture recenti, "
          f"{sum(len(v) for v in recent.values())} fixture-target.")
    tot_target = tot_upd = 0
    for league_id, fids in recent.items():
        n_target, updated = _enrich_league(sb, league_id, args.dry_run, counters,
                                           current_fids=fids)
        tot_target += n_target
        tot_upd += updated
        print(f"  lega {league_id}: target {n_target} | aggiornate {updated}", end="\r")
    print(f"\nIncrementale: target {tot_target} | aggiornate {tot_upd} (BULK) | "
          f"falliti {counters['failed']}")
    if counters["failed"]:
        raise SystemExit(f"ATTENZIONE: {counters['failed']} righe non scritte.")


if __name__ == "__main__":
    main()
