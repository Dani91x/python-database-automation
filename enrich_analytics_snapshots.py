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
SCRITTURA BULK A FETTE (veloce + poco stressante per il DB):
  Niente UPDATE riga-per-riga (46k round-trip → I/O-bound), ma nemmeno UN SOLO
  UPDATE per l'intera lega (sulle leghe grandi supera lo statement_timeout di 8s
  → 57014 → lega intera NON aggiornata, in silenzio). Ora, per FETTE di poche
  centinaia di righe:
    1) calcola gli snapshot in Python (compute_market_snapshots, INVARIATO),
    2) carica la FETTA in `analytics_snap_staging` (un upsert),
    3) UPDATE ... FROM scopato alla lega (RPC flush_analytics_snap_staging), che
       aggiorna e poi CANCELLA dalla staging le chiavi appena flushate,
    4) fetta successiva (staging di nuovo vuota per quella lega).
  → stato finale IDENTICO al flush unico: le fette sono disgiunte, ogni chiave è
  aggiornata una volta sola e la somma delle righe aggiornate coincide. I numeri
  scritti sono IDENTICI, riga-per-riga, a quelli del metodo riga-per-riga (lo
  staging è solo trasporto + JOIN set-based).

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
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client
from analytics_market_stats import (
    Snapshot,
    compute_current_state,
    compute_market_snapshots,
)

_MATCH_COLS = ("fixture_id,fixture_date,status_short,goals_home,goals_away,"
               "fulltime_home,fulltime_away,halftime_home,halftime_away")
_STAGE_BATCH = 500      # tetto massimo di righe in UNA richiesta di upsert
_FLUSH_SLICE = 400      # righe per FETTA carica->flush (adattiva: dimezza sui transitori)
_FLUSH_MIN = 50         # fetta minima
_RETRY = 5              # tentativi su errori TRANSITORI

# Errori TRANSITORI (si ritentano): statement timeout, DB occupato/riavvio,
# deadlock/serializzazione, connessione persa, 5xx del gateway, PGRST002 (schema
# cache non pronta). Gli errori LOGICI (vincoli, 4xx di validazione) NON si ritentano.
_TRANSIENT_CODES = {"57014", "53300", "53400", "55P03", "40001", "40P01",
                    "08006", "08003", "08000", "57P01", "57P02", "57P03",
                    "PGRST002", "408", "500", "502", "503", "504"}


def _is_transient(e: Exception) -> bool:
    """True solo per gli errori che ha senso ritentare."""
    if isinstance(e, httpx.TransportError):   # ReadTimeout, ConnectError, PoolTimeout...
        return True
    code = getattr(e, "code", None)
    if code is not None and str(code) in _TRANSIENT_CODES:
        return True
    msg = str(getattr(e, "message", "") or "").lower()
    return "timeout" in msg or "temporarily unavailable" in msg


def _sleep_backoff(attempt: int) -> None:
    """Attesa crescente con jitter (0,7x-1,3x)."""
    time.sleep(min(8.0, 0.5 * (2 ** attempt)) * (0.7 + random.random() * 0.6))


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


def _upsert_stage(sb, rows: list[dict], counters: dict) -> bool:
    """Carica UNA fetta nella staging (una sola richiesta). True se scritta."""
    for attempt in range(_RETRY):
        try:
            (sb.table("analytics_snap_staging")
             .upsert(rows, on_conflict="fixture_id,market,selection").execute())
            return True
        except Exception as e:  # noqa: BLE001
            if not _is_transient(e) or attempt == _RETRY - 1:
                counters["failed"] += len(rows)
                print(f"    [ERR staging] {len(rows)} righe perse: "
                      f"{type(e).__name__}: {str(e)[:100]}")
                return False
            _sleep_backoff(attempt)
    return False


def _flush_league(sb, league_id: int) -> tuple[bool, int]:
    """UN UPDATE ... FROM (RPC) sulle righe ATTUALMENTE in staging per la lega.
    La RPC cancella dalla staging le sole chiavi flushate → le fette successive
    partono da una staging vuota. Ritorna (riuscito, righe_aggiornate)."""
    for attempt in range(_RETRY):
        try:
            res = sb.rpc("flush_analytics_snap_staging",
                         {"p_league_id": league_id}).execute()
            return True, (res.data if isinstance(res.data, int) else 0)
        except Exception as e:  # noqa: BLE001
            if not _is_transient(e) or attempt == _RETRY - 1:
                print(f"    [ERR flush lega {league_id}] "
                      f"{type(e).__name__}: {str(e)[:100]}")
                return False, 0
            _sleep_backoff(attempt)
    return False, 0


def _flush_staging(sb, league_id: int, stage_rows: list[dict], counters: dict,
                   slice_state: Optional[dict] = None) -> int:
    """Scrive gli snapshot A FETTE: per ogni fetta di poche centinaia di righe
    → upsert in staging + UNA RPC di flush. Ritorna le righe aggiornate.

    PERCHE' A FETTE: la RPC fa UN SOLO UPDATE ... FROM per tutta la staging della
    lega; sulle leghe grandi (migliaia di righe) supera lo statement_timeout di 8s
    (57014) e l'intera lega resta NON aggiornata. Le fette danno lo STESSO stato
    finale: la RPC cancella dalla staging le chiavi appena flushate, quindi le
    fette sono sequenziali e disgiunte, ogni chiave viene aggiornata UNA volta, e
    la somma delle righe aggiornate e' identica a quella del flush unico.

    Se un flush non riesce dopo i retry, le sue righe restano in staging (le
    riprendera' il run successivo, che le sovrascrive) e la LEGA viene abbandonata:
    caricarne altre renderebbe l'UPDATE ancora piu' pesante. Le righe non scritte
    sono contate in counters['failed'] → exit != 0 a fine script.
    """
    if not stage_rows:
        return 0
    state = slice_state if slice_state is not None else {"size": _FLUSH_SLICE}
    updated = 0
    i = 0
    while i < len(stage_rows):
        size = max(_FLUSH_MIN, min(int(state["size"]), _STAGE_BATCH))
        part = stage_rows[i:i + size]
        i += len(part)
        if not _upsert_stage(sb, part, counters):
            continue                      # righe gia' contate come perse
        ok, n = _flush_league(sb, league_id)
        if ok:
            updated += n
            continue
        state["size"] = max(_FLUSH_MIN, size // 2)   # fetta adattiva
        persi = len(part) + (len(stage_rows) - i)
        counters["failed"] += persi
        print(f"    [ERR flush lega {league_id}] abbandono la lega: {persi} righe "
              f"NON scritte (fetta ridotta a {state['size']})")
        return updated
    return updated


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
                   current_fids: Optional[set[int]] = None,
                   slice_state: Optional[dict] = None) -> tuple[int, int]:
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
    updated = _flush_staging(sb, league_id, stage, counters, slice_state)
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
    # dimensione della fetta di flush, condivisa fra le leghe: si dimezza dopo un
    # flush fallito e resta ridotta per le leghe successive (DB sotto pressione).
    slice_state = {"size": _FLUSH_SLICE}

    # ---- MODO STORICO: una lega intera (point-in-time su tutte le settlate) ----
    if args.league:
        n_target, updated = _enrich_league(sb, args.league, args.dry_run, counters,
                                           slice_state=slice_state)
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
                                           current_fids=fids, slice_state=slice_state)
        tot_target += n_target
        tot_upd += updated
        print(f"  lega {league_id}: target {n_target} | aggiornate {updated}", end="\r")
    print(f"\nIncrementale: target {tot_target} | aggiornate {tot_upd} (BULK) | "
          f"falliti {counters['failed']}")
    if counters["failed"]:
        raise SystemExit(f"ATTENZIONE: {counters['failed']} righe non scritte.")


if __name__ == "__main__":
    main()
