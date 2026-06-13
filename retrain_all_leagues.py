"""
retrain_all_leagues.py — Retraining completo di tutti i modelli ML.

Questo script è SEPARATO dal report giornaliero (aggiorna_report.bat).
Va lanciato manualmente (o via aggiorna_modelli.bat) quando vuoi aggiornare
tutti i modelli con gli ultimi dati disponibili nel DB.

Caratteristiche:
- Riaddestra tutte le leghe che hanno già modelli in cache (o tutte quelle nel DB)
- Mostra BSS prima/dopo per ogni lega e target
- Saltabile per lega specifica con --leagues 39,40,41
- Riprendibile: con --skip-existing salta leghe già riaddestrate oggi
- Log completo con riepilogo finale

Uso:
    python retrain_all_leagues.py
    python retrain_all_leagues.py --leagues 39,40,41
    python retrain_all_leagues.py --last-n-seasons 3
    python retrain_all_leagues.py --skip-existing
    python retrain_all_leagues.py --dry-run
"""
from __future__ import annotations

import argparse
import gzip
import os
import pickle
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── Path setup ─────────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.dirname(__file__))
AI_ENGINE_DIR = os.path.join(ROOT, "Ai Engine")
for p in [ROOT, AI_ENGINE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from db_client import get_supabase_client
from ai_engine.seriea_model_export import train_and_save_all, upload_and_register

# Stdout robusto: su Windows con output rediretto l'encoding è cp1252 e i
# simboli unicode nei print (→ ✓ ✗) farebbero crashare i worker: degrada i
# caratteri non rappresentabili invece di interrompere il retrain.
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass


# ── Constants ───────────────────────────────────────────────────────────────
MODELS_CACHE_DIR = os.path.join(AI_ENGINE_DIR, "models_cache")
MIN_BSS_THRESHOLD = 0.12   # gate di qualità: modelli sotto questa soglia non scommettono
DEFAULT_LAST_N_SEASONS = 3


# ── Helpers ─────────────────────────────────────────────────────────────────

def _bss(brier: Optional[float], n_classes: int) -> Optional[float]:
    if brier is None:
        return None
    brier_random = (n_classes - 1) / n_classes if n_classes > 1 else 0.5
    if brier_random <= 0:
        return None
    return round(1.0 - brier / brier_random, 4)


def _load_existing_metrics(league_id: int) -> Dict[str, Dict]:
    """Carica le calibration_metrics dei modelli già in cache per la lega."""
    league_dir = os.path.join(MODELS_CACHE_DIR, f"league_{league_id}")
    metrics: Dict[str, Dict] = {}
    if not os.path.isdir(league_dir):
        return metrics
    for fname in os.listdir(league_dir):
        if not fname.endswith(".pkl.gz"):
            continue
        target = fname.replace("ensemble_v2_", "").replace(".pkl.gz", "")
        try:
            with gzip.open(os.path.join(league_dir, fname), "rb") as f:
                data = pickle.load(f)
            cal = data.get("calibration_metrics", {})
            n_cls = len(data.get("class_labels", [])) or 2
            metrics[target] = {
                "brier": cal.get("brier"),
                "ece": cal.get("ece"),
                "bss": _bss(cal.get("brier"), n_cls),
                "n_classes": n_cls,
                "trained_at": data.get("trained_at", "unknown"),
            }
        except Exception:
            pass
    return metrics


def _get_all_league_ids_from_cache() -> List[int]:
    """Raccoglie tutti i league_id che hanno una cartella in models_cache."""
    ids = []
    if not os.path.isdir(MODELS_CACHE_DIR):
        return ids
    for d in os.listdir(MODELS_CACHE_DIR):
        if d.startswith("league_"):
            try:
                ids.append(int(d.split("_")[1]))
            except ValueError:
                pass
    return sorted(ids)


def _get_all_league_ids_from_db() -> List[int]:
    """Recupera tutti i league_id da season_backfill_state (fonte autorevole, ~3k righe).

    Non usa 'matches' direttamente perché quella tabella ha milioni di righe e
    Supabase tronca ogni query a 100.000 righe: con leghe grandi (es. 39=6070,
    45=10294 righe) il buffer si satura e vengono restituite solo 64 leghe
    invece delle 328+ effettivamente popolate.
    season_backfill_state ha una riga per stagione di ogni lega, entra sempre
    in un singolo .execute() e si aggiorna automaticamente ogni volta che
    l'orchestratore popola una nuova lega.
    """
    try:
        sb = get_supabase_client()
        resp = sb.table("season_backfill_state").select("league_id").execute()
        data = getattr(resp, "data", None) or []
        ids = sorted({int(r["league_id"]) for r in data if r.get("league_id") is not None})
        if not ids:
            # Fallback: paginazione esplicita su matches
            print("  [WARN] season_backfill_state vuota, fallback su matches paginato")
            ids = _get_league_ids_from_matches_paginated(sb)
        return ids
    except Exception as e:
        print(f"  [WARN] Impossibile recuperare leghe dal DB: {e}")
        return []


def _get_league_ids_from_matches_paginated(sb: Any) -> List[int]:
    """Fallback: paginazione esplicita su matches per raccogliere tutti i league_id."""
    PAGE = 50_000
    offset = 0
    seen: set = set()
    while True:
        try:
            r = (
                sb.table("matches")
                .select("league_id")
                .range(offset, offset + PAGE - 1)
                .execute()
            )
        except Exception as exc:
            print(f"  [WARN] Errore paginazione matches a offset {offset}: {exc}")
            break
        rows = getattr(r, "data", None) or []
        if not rows:
            break
        for row in rows:
            lid = row.get("league_id")
            if lid is not None:
                seen.add(int(lid))
        if len(rows) < PAGE:
            break
        offset += PAGE
    return sorted(seen)


def _log(msg: str, log_lines: List[str]) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        # stdout cp1252 (es. output rediretto su Windows) non codifica '→' &co.:
        # degrada i caratteri non rappresentabili invece di far crashare il worker.
        enc = sys.stdout.encoding or "ascii"
        print(line.encode(enc, errors="replace").decode(enc))
    log_lines.append(line)


def _was_trained_recently(metrics: Dict[str, Dict], max_age_days: int = 0) -> bool:
    """
    True se almeno un modello è stato addestrato entro ``max_age_days`` giorni.

    max_age_days=0  → comportamento originale: solo oggi
    max_age_days=7  → salta la lega se è stata addestrata negli ultimi 7 giorni
    """
    now = datetime.now(timezone.utc)
    for m in metrics.values():
        trained_at_str = m.get("trained_at", "")
        if not trained_at_str:
            continue
        try:
            trained_at = datetime.fromisoformat(trained_at_str)
            if trained_at.tzinfo is None:
                trained_at = trained_at.replace(tzinfo=timezone.utc)
            age_days = (now - trained_at).total_seconds() / 86400.0
            if age_days <= max(max_age_days, 0) + 1:  # +1 = include "oggi"
                return True
        except (ValueError, TypeError):
            continue
    return False


# ── Main retraining logic ────────────────────────────────────────────────────

def retrain_league(
    league_id: int,
    last_n_seasons: int,
    dry_run: bool,
    log_lines: List[str],
) -> Dict:
    """Riaddestra tutti i target per una lega. Ritorna un dizionario con i risultati."""
    _log(f"  → Training league {league_id} (last {last_n_seasons} seasons)...", log_lines)

    if dry_run:
        _log(f"  [DRY-RUN] Saltato league {league_id}", log_lines)
        return {"league_id": league_id, "status": "dry_run", "targets": []}

    try:
        results = train_and_save_all(league_id, last_n_seasons=last_n_seasons)
    except Exception as e:
        _log(f"  [ERROR] league {league_id}: {e}", log_lines)
        return {"league_id": league_id, "status": "error", "error": str(e), "targets": []}

    # Upload to Supabase — skip models flagged as too large by _train_one_target.
    upload_errors = []
    for r in results:
        if r.get("upload_skipped"):
            _log(
                f"  [SKIP UPLOAD] {r['target']}: model too large "
                f"({r.get('file_size', 0) / 1024 / 1024:.1f} MB) — BSS tracked, upload skipped.",
                log_lines,
            )
            continue
        try:
            upload_and_register(r["model_path"], r["file_size"], r["target"], r)
        except Exception as e:
            upload_errors.append(f"{r['target']}: {e}")

    return {
        "league_id": league_id,
        "status": "ok",
        "targets": results,
        "upload_errors": upload_errors,
    }


def print_bss_comparison(
    league_id: int,
    before: Dict[str, Dict],
    after: List[Dict],
    log_lines: List[str],
) -> None:
    """Stampa confronto BSS prima/dopo per la lega."""
    if not after:
        _log(f"  [WARN] Nessun modello addestrato per league {league_id}", log_lines)
        return

    _log(f"  BSS comparison — league {league_id}:", log_lines)
    header = f"    {'Target':30} {'Prima BSS':12} {'Dopo BSS':12} {'Delta':10} {'Gate':6}"
    _log(header, log_lines)
    _log("    " + "-" * 70, log_lines)

    for r in after:
        target = r.get("target", "?")
        after_brier = r.get("brier")
        n_cls = len(r.get("class_labels", [])) if r.get("class_labels") else 2
        after_bss = _bss(after_brier, n_cls)

        before_m = before.get(target, {})
        before_bss = before_m.get("bss")

        before_str = f"{before_bss:+.3f}" if before_bss is not None else "  N/A "
        after_str = f"{after_bss:+.3f}" if after_bss is not None else "  N/A "
        if before_bss is not None and after_bss is not None:
            delta = after_bss - before_bss
            delta_str = f"{delta:+.3f}"
        else:
            delta_str = "  N/A "
        gate = "OK " if (after_bss is not None and after_bss >= MIN_BSS_THRESHOLD) else "FAIL"

        _log(f"    {target:30} {before_str:12} {after_str:12} {delta_str:10} {gate}", log_lines)


def _process_league_worker(
    league_id: int,
    idx: int,
    total: int,
    last_n_seasons: int,
    dry_run: bool,
    skip_existing: bool,
    max_age_days: int,
    deadline_ts: Optional[float] = None,
) -> Dict:
    """Elabora una singola lega: training, BSS comparison, upload Supabase.

    Progettato per essere chiamato in parallelo via ThreadPoolExecutor.
    Ogni worker usa la propria lista di log per evitare race condition.

    Se ``deadline_ts`` (epoch secondi) e' superato all'inizio, la lega NON viene
    addestrata e il worker esce subito: e' il meccanismo di time-budget che fa
    fermare il run sotto il cap delle 3h. Le leghe gia' completate sono salvate
    nel registry, quindi il run successivo (skip/planner) riprende da li'.
    """
    local_logs: List[str] = []

    if deadline_ts is not None and time.time() > deadline_ts:
        return {"league_id": league_id, "status": "timebudget", "logs": local_logs}

    print(f"\n[{idx}/{total}] League {league_id}")
    _log(f"[{idx}/{total}] League {league_id}", local_logs)

    before_metrics = _load_existing_metrics(league_id)

    if skip_existing and _was_trained_recently(before_metrics, max_age_days):
        _log(f"  → SALTATO (già addestrato negli ultimi {max_age_days} giorni)", local_logs)
        return {"league_id": league_id, "status": "skipped", "logs": local_logs}

    t_start = time.time()
    result = retrain_league(league_id, last_n_seasons, dry_run, local_logs)
    elapsed = time.time() - t_start

    if result["status"] == "dry_run":
        return {"league_id": league_id, "status": "dry_run", "logs": local_logs}

    if result["status"] == "error":
        return {
            "league_id": league_id, "status": "error",
            "error": result.get("error", ""),
            "elapsed_s": round(elapsed, 1),
            "logs": local_logs,
        }

    after_list = result["targets"]
    print_bss_comparison(league_id, before_metrics, after_list, local_logs)

    bss_improved = 0
    bss_degraded = 0
    for r in after_list:
        target = r.get("target", "?")
        n_cls = len(r.get("class_labels", [])) if r.get("class_labels") else 2
        after_bss = _bss(r.get("brier"), n_cls)
        before_bss = before_metrics.get(target, {}).get("bss")
        if before_bss is not None and after_bss is not None:
            if after_bss > before_bss + 0.005:
                bss_improved += 1
            elif after_bss < before_bss - 0.005:
                bss_degraded += 1

    try:
        sb = get_supabase_client()
        for r in after_list:
            target = r.get("target", "?")
            n_cls = r.get("n_classes") or (len(r.get("class_labels", [])) if r.get("class_labels") else 2)
            brier_val = r.get("brier")
            ece_val = r.get("ece")
            bss_val = _bss(brier_val, n_cls)
            brier_random = (n_cls - 1) / n_cls if n_cls > 1 else 0.5
            try:
                sb.table("model_performance").upsert({
                    "league_id": league_id,
                    "target": target,
                    "n_classes": n_cls,
                    "brier": brier_val,
                    "brier_random": round(brier_random, 4),
                    "bss": bss_val,
                    "ece": ece_val,
                    "train_rows": r.get("train_rows"),
                    "val_rows": r.get("val_rows"),
                    "trained_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as e:
                _log(f"  [WARN] model_performance upsert failed for {target}: {e}", local_logs)
    except Exception as e:
        _log(f"  [WARN] BSS tracking to Supabase failed: {e}", local_logs)

    upload_errors = result.get("upload_errors", [])
    for ue in upload_errors:
        _log(f"  [UPLOAD WARN] {ue}", local_logs)

    _log(f"  ✓ Completato in {elapsed:.1f}s | {len(after_list)} modelli", local_logs)

    return {
        "league_id": league_id,
        "status": "ok",
        "models_trained": len(after_list),
        "elapsed_s": round(elapsed, 1),
        "upload_errors": len(upload_errors),
        "bss_improved": bss_improved,
        "bss_degraded": bss_degraded,
        "logs": local_logs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Riaddestra tutti i modelli ML per tutte le leghe disponibili."
    )
    parser.add_argument(
        "--leagues",
        type=str,
        default=None,
        help="Leghe specifiche da riaddestrare (es. '39,40,41'). Default: tutte.",
    )
    parser.add_argument(
        "--last-n-seasons",
        type=int,
        default=DEFAULT_LAST_N_SEASONS,
        help=f"Stagioni da usare per il training. Default: {DEFAULT_LAST_N_SEASONS}.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Salta le leghe già riaddestrate recentemente (vedi --max-age-days).",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=0,
        help=(
            "Usato con --skip-existing: salta la lega se è stata addestrata "
            "negli ultimi N giorni. Default=0 (solo oggi). "
            "Es: --max-age-days 7 per saltare leghe già addestrate questa settimana."
        ),
    )
    parser.add_argument(
        "--parallel-leagues",
        type=int,
        default=1,
        help=(
            "Leghe da processare in parallelo. Default=1 (sequenziale). "
            "Con 2: dimezza il tempo totale usando tutti gli 8 core disponibili. "
            "Richiede RETRAIN_N_WORKERS=2 (settato automaticamente da aggiorna_modelli.bat)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Non addestra nulla, mostra solo quali leghe verrebbero riaddestrate.",
    )
    parser.add_argument(
        "--time-budget-min",
        type=float,
        default=0.0,
        help=(
            "Budget di tempo in minuti: oltre questo, i worker non prendono nuove "
            "leghe ed escono puliti (le fatte restano salvate nel registry, il run "
            "dopo riprende). 0 = nessun limite. Usato in cloud per restare sotto le 3h."
        ),
    )
    parser.add_argument(
        "--source",
        choices=["cache", "db", "both"],
        default="cache",
        help="Fonte dei league_id: 'cache' (default) = solo quelli con modelli esistenti, "
             "'db' = tutte le leghe nel database, 'both' = unione.",
    )
    args = parser.parse_args()

    log_lines: List[str] = []
    started_at = datetime.now(timezone.utc)

    # Time-budget: deadline epoch oltre cui non si avviano nuove leghe.
    deadline_ts: Optional[float] = None
    if args.time_budget_min and args.time_budget_min > 0:
        deadline_ts = time.time() + args.time_budget_min * 60.0

    print("=" * 70)
    print("  RETRAIN ALL LEAGUES — Betfair ML System")
    print(f"  Avviato: {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if deadline_ts is not None:
        print(f"  Time-budget: {args.time_budget_min:.0f} min (stop nuove leghe oltre il budget)")
    print("=" * 70)

    # ── Raccolta league_ids ────────────────────────────────────────────────
    if args.leagues:
        league_ids = [int(x.strip()) for x in args.leagues.split(",") if x.strip()]
        print(f"  Leghe specificate manualmente: {league_ids}")
    else:
        cache_ids = _get_all_league_ids_from_cache() if args.source in ("cache", "both") else []
        db_ids = _get_all_league_ids_from_db() if args.source in ("db", "both") else []
        league_ids = sorted(set(cache_ids) | set(db_ids))
        print(f"  Leghe trovate: {len(league_ids)} "
              f"(cache={len(cache_ids)}, db={len(db_ids)})")

    if not league_ids:
        print("  [ERROR] Nessuna lega trovata. Controlla MODELS_CACHE_DIR o la connessione al DB.")
        sys.exit(1)

    # ── Loop principale ────────────────────────────────────────────────────
    total = len(league_ids)
    ok_count = 0
    skipped_count = 0
    error_count = 0
    timebudget_count = 0
    bss_improved = 0
    bss_degraded = 0

    summary_rows: List[Dict] = []

    # ── Parallelismo a livello di lega ─────────────────────────────────────
    parallel = args.parallel_leagues
    if parallel > 1:
        # IMPORTANTE: env var deve essere settata PRIMA di creare il ThreadPoolExecutor,
        # altrimenti i worker potrebbero leggere il valore di default "1" anziché il reale.
        # aggiorna_modelli.bat setta già RETRAIN_PARALLEL_LEAGUES prima di lanciare Python;
        # questo set è un fallback per chi invoca retrain_all_leagues.py direttamente.
        os.environ["RETRAIN_PARALLEL_LEAGUES"] = str(parallel)
        print(f"  Modalità: {parallel} leghe in parallelo")

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {
            executor.submit(
                _process_league_worker,
                lid, i, total,
                args.last_n_seasons, args.dry_run,
                args.skip_existing, args.max_age_days,
                deadline_ts,
            ): lid
            for i, lid in enumerate(league_ids, 1)
        }
        for future in as_completed(futures):
            r = future.result()
            log_lines.extend(r.get("logs", []))
            status = r.get("status", "error")
            lid = r["league_id"]

            if status == "timebudget":
                timebudget_count += 1
            elif status in ("skipped", "dry_run"):
                skipped_count += 1
            elif status == "error":
                error_count += 1
                summary_rows.append({
                    "league_id": lid,
                    "status": "ERROR",
                    "error": r.get("error", ""),
                    "elapsed_s": r.get("elapsed_s", 0),
                })
            elif status == "ok":
                ok_count += 1
                bss_improved += r.get("bss_improved", 0)
                bss_degraded += r.get("bss_degraded", 0)
                summary_rows.append({
                    "league_id": lid,
                    "status": "OK",
                    "models_trained": r.get("models_trained", 0),
                    "elapsed_s": r.get("elapsed_s", 0),
                    "upload_errors": r.get("upload_errors", 0),
                })

    # ── Riepilogo finale ───────────────────────────────────────────────────
    ended_at = datetime.now(timezone.utc)
    total_elapsed = (ended_at - started_at).total_seconds()

    print("\n" + "=" * 70)
    print("  RIEPILOGO FINALE")
    print("=" * 70)
    print(f"  Leghe totali:     {total}")
    print(f"  ✓ OK:             {ok_count}")
    print(f"  ⟳ Saltate:        {skipped_count}")
    print(f"  ⏳ Stop budget:    {timebudget_count} (non avviate, riprese al prossimo run)")
    print(f"  ✗ Errori:         {error_count}")
    print(f"  BSS migliorati:   {bss_improved}")
    print(f"  BSS peggiorati:   {bss_degraded}")
    print(f"  Tempo totale:     {total_elapsed/60:.1f} min")
    print(f"  Fine:             {ended_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 70)

    # ── BSS Fleet Dashboard ─────────────────────────────────────────────
    # Aggregate post-training BSS by target across all successfully retrained
    # leagues.  Shows how many models are active (BSS≥0.12), blocked, and
    # worse-than-random per target.
    # Collect metrics from all OK leagues
    target_bss_values: Dict[str, List[float]] = {}
    for sr in summary_rows:
        if sr.get("status") != "OK":
            continue
        league_id = sr["league_id"]
        post_metrics = _load_existing_metrics(league_id)
        for target, m in post_metrics.items():
            bss_val = m.get("bss")
            if bss_val is not None:
                target_bss_values.setdefault(target, []).append(bss_val)

    if target_bss_values:
        print(f"\n  {'─' * 70}")
        print(f"  BSS FLEET DASHBOARD")
        print(f"  {'─' * 70}")
        print(f"  {'Target':30} {'Leghe':6} {'Attivi':8} {'Bloccati':10} {'<Random':8} {'BSS Medio':10}")
        print(f"  {'':30} {'':6} {'≥0.12':8} {'<0.12':10} {'<0':8} {'':10}")
        print(f"  {'─' * 70}")
        for target in sorted(target_bss_values.keys()):
            vals = target_bss_values[target]
            n_total = len(vals)
            n_active = sum(1 for v in vals if v >= MIN_BSS_THRESHOLD)
            n_blocked = sum(1 for v in vals if v < MIN_BSS_THRESHOLD)
            n_worse = sum(1 for v in vals if v < 0)
            mean_bss = sum(vals) / n_total if n_total > 0 else 0
            pct_active = n_active / n_total * 100 if n_total > 0 else 0
            print(f"  {target:30} {n_total:6} {n_active:5} ({pct_active:4.0f}%) {n_blocked:7}   {n_worse:5}   {mean_bss:+.4f}")
        print(f"  {'─' * 70}")

    # Leghe con errori
    errors = [r for r in summary_rows if r["status"] == "ERROR"]
    if errors:
        print(f"\n  Leghe con errore ({len(errors)}):")
        for e in errors:
            print(f"    - League {e['league_id']}: {e.get('error', '')}")

    # Salva log su file
    log_path = os.path.join(ROOT, f"retrain_log_{started_at.strftime('%Y%m%d_%H%M%S')}.txt")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines))
        print(f"\n  Log salvato in: {log_path}")
    except Exception as e:
        print(f"  [WARN] Impossibile salvare il log: {e}")

    print("\n  NOTA: Dopo il retraining, lancia 'aggiorna_report.bat' normalmente.")
    print("        I nuovi modelli vengono usati automaticamente.")

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
