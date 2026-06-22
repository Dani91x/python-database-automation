"""
backfill_poisson_calibrated.py — aggiunge db_json_analisi.markets_calibrated alle
partite gia' stoccate, usando poisson_calibrator (DB poisson_calibration o fallback
dynamic_cal.json).

ADDITIVO E NON DISTRUTTIVO: legge db_json_analisi intero, AGGIUNGE le chiavi
  markets_calibrated, calibrated_at, calibration_source
e riscrive. Il grezzo `markets` resta INTATTO (serve al calibratore settimanale).

Uso:
  python backfill_poisson_calibrated.py --fids 1492915 1553786 ...   # set specifico
  python backfill_poisson_calibrated.py --days 3                     # ultimi N giorni (fixture_date)
  python backfill_poisson_calibrated.py --all                        # TUTTO lo storico (streaming, batch upsert)
  python backfill_poisson_calibrated.py --days 3 --dry-run           # mostra prima/dopo, NON scrive
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client
from poisson_calibrator import PoissonCalibrator

DEFAULT_FIDS = [
    1529745, 1553788, 1529747, 1495868, 1553787, 1492916, 1492917, 1492915,
    1492717, 1492718, 1492919, 1492918, 1492719, 1492720, 1553786, 1492716,
    1514209, 1499479,
]


def _fetch(sb, fids=None, days=None):
    sel = "fixture_id,league_id,db_json_analisi"
    if fids:
        rows = []
        for i in range(0, len(fids), 200):
            chunk = fids[i:i + 200]
            r = sb.table("fixture_predictions").select(sel).in_("fixture_id", chunk).execute()
            rows.extend(r.data or [])
        return rows
    # per giorni: usa fixture_date
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    rows, off, page = [], 0, 1000
    while True:
        r = (sb.table("fixture_predictions").select(sel + ",fixture_date")
             .gte("fixture_date", f"{since}T00:00:00+00:00")
             .not_.is_("db_json_analisi", "null")
             .range(off, off + page - 1).execute())
        batch = r.data or []
        rows.extend(batch)
        if len(batch) < page:
            break
        off += page
    return rows


def _iter_all_pages(sb, page=1000, resume=False):
    """Stream di righe con db_json_analisi non-null (bassa memoria).

    resume=True: SOLO le righe Poisson ancora prive di markets_calibrated, cosi'
    una ripresa non riscrive le partite gia' calibrate (gentile sull'I/O Supabase).
    Nota: l'offset NON avanza in modalita' resume perche' ogni riga scritta esce
    dal filtro -> si ri-legge sempre dalla cima del residuo.
    """
    off = 0
    while True:
        q = (sb.table("fixture_predictions").select("fixture_id,league_id,db_json_analisi")
             .not_.is_("db_json_analisi", "null"))
        if resume:
            q = (q.eq("db_json_analisi->>model", "poisson_xg_hybrid_dc")
                 .is_("db_json_analisi->markets_calibrated", "null"))
        else:
            q = q.range(off, off + page - 1)
        r = q.limit(page).execute() if resume else q.execute()
        batch = r.data or []
        if not batch:
            break
        yield batch
        if resume:
            continue  # filtro auto-restringente: la prossima query parte dal nuovo residuo
        if len(batch) < page:
            break
        off += page


def _process(rows, cal, sb, now_iso, dry_run, counters, sample_state):
    """Calibra un gruppo di righe e (se non dry-run) le scrive con UPSERT a batch
    su {fixture_id, db_json_analisi} — tocca solo db_json_analisi (merge-duplicates)."""
    payload = []
    for r in rows:
        fid = r["fixture_id"]
        analisi = r.get("db_json_analisi")
        if not isinstance(analisi, dict) or analisi.get("model") != "poisson_xg_hybrid_dc":
            counters["skipped"] += 1
            continue
        markets = analisi.get("markets")
        if not isinstance(markets, dict):
            counters["skipped"] += 1
            continue
        league_id = analisi.get("league_id") or r.get("league_id")
        mc = cal.calibrate_markets(markets, league_id)

        if sample_state["n"] < 3:
            sample_state["n"] += 1
            print(f"  [esempio] fid {fid} lega {league_id}")
            for mk in ("over_2_5", "over_3_5", "1x2"):
                if mk in markets:
                    g = {k: round(v, 3) for k, v in markets[mk].items() if isinstance(v, (int, float))}
                    c = {k: round(v, 3) for k, v in mc[mk].items() if isinstance(v, (int, float))}
                    print(f"     {mk:18s} grezzo {g}  ->  calibrato {c}")

        new_analisi = dict(analisi)
        new_analisi["markets_calibrated"] = mc
        new_analisi["calibrated_at"] = now_iso
        new_analisi["calibration_source"] = cal.source
        payload.append({"fixture_id": fid, "db_json_analisi": new_analisi})

    if dry_run:
        counters["updated"] += len(payload)
        return

    # UPDATE per-riga SEQUENZIALE con retry (NON upsert: upsert costruisce una INSERT e
    # violerebbe i NOT NULL come `status`; NON multi-thread: il client Supabase condiviso
    # non e' thread-safe -> ReadError/WinError 10035). Tocca solo db_json_analisi, gentile
    # sull'istanza (vedi nota I/O exhaustion nel progetto).
    def _write(item, attempts=3):
        for k in range(attempts):
            try:
                sb.table("fixture_predictions").update(
                    {"db_json_analisi": item["db_json_analisi"]}
                ).eq("fixture_id", item["fixture_id"]).execute()
                return True
            except Exception as e:
                if k == attempts - 1:
                    print(f"  [ERRORE] fid {item['fixture_id']}: {type(e).__name__}: {e}")
                    return False
                time.sleep(0.5 * (k + 1))
        return False

    for item in payload:
        counters["updated" if _write(item) else "errors"] += 1


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--fids", type=int, nargs="*", default=None)
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--all", action="store_true", help="TUTTO lo storico (streaming)")
    ap.add_argument("--resume", action="store_true",
                    help="SOLO le righe Poisson senza markets_calibrated (ripresa mirata)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sb = get_supabase_client()
    cal = PoissonCalibrator()
    print(f"Sorgente calibrazione: {cal.source} "
          f"(leghe={len(cal._by_league)}, global_keys={len(cal._global)})")
    if cal.source == "none":
        print("ERRORE: nessuna sorgente di calibrazione (ne' DB ne' dynamic_cal.json). Esco.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    counters = {"updated": 0, "skipped": 0, "errors": 0}
    sample_state = {"n": 0}

    if args.all or args.resume:
        mode = "--resume (solo mancanti)" if args.resume else "--all"
        print(f"Modalita' {mode}: streaming...\n")
        n_pages = 0
        for page in _iter_all_pages(sb, resume=args.resume):
            n_pages += 1
            prev_updated = counters["updated"]
            _process(page, cal, sb, now_iso, args.dry_run, counters, sample_state)
            done = counters["updated"] + counters["skipped"] + counters["errors"]
            print(f"  ...pagina {n_pages}: processate {done} righe "
                  f"(calibrate {counters['updated']}, saltate {counters['skipped']}, "
                  f"errori {counters['errors']})", end="\r")
            # Anti-loop (resume): il filtro `markets_calibrated IS NULL` re-legge sempre
            # dalla cima del residuo. In dry-run NIENTE viene scritto -> le righe NON escono
            # mai dal filtro -> giro infinito: mostriamo 1 pagina di anteprima e stop.
            # In esecuzione reale: se una pagina non calibra nulla di nuovo, sono righe che
            # falliscono in scrittura -> stop per non ripetere all'infinito.
            if args.resume and (args.dry_run or counters["updated"] == prev_updated):
                reason = ("dry-run: 1 pagina di anteprima (nessuna scrittura)" if args.dry_run
                          else f"pagina {n_pages} senza progressi ({len(page)} righe non scrivibili)")
                print(f"\n[STOP] resume interrotto: {reason}.")
                break
        print()
    else:
        fids = args.fids if args.fids is not None else (None if args.days else DEFAULT_FIDS)
        rows = _fetch(sb, fids=fids, days=args.days)
        print(f"Partite da processare: {len(rows)}\n")
        _process(rows, cal, sb, now_iso, args.dry_run, counters, sample_state)

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Calibrate: {counters['updated']}  |  "
          f"saltate: {counters['skipped']}  |  errori: {counters['errors']}")
    if args.dry_run:
        print("Nessuna scrittura effettuata. Rilancia senza --dry-run per scrivere.")


if __name__ == "__main__":
    main()
