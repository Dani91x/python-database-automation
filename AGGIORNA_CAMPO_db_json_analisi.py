"""
AGGIORNA_CAMPO_db_json_analisi.py
==================================
Script standalone per aggiornare il campo db_json_analisi
nella tabella fixture_predictions sul pregresso storico.

Aggiorna SOLO db_json_analisi — non tocca ht_predictions né altri campi.
Il calcolo usa ESATTAMENTE la stessa funzione compute_db_json_analisi
di today_predictions_backfill.py, garantendo formato e logica identici.

Design per produzione:
  - Scritture SEQUENZIALI (nessun threading → nessun WSAEWOULDBLOCK su Windows)
  - Client Supabase creato UNA volta e riutilizzato per tutta la sessione
  - Retry con backoff esponenziale su ogni scrittura (3 tentativi: 2s, 4s, 8s)
  - Checkpoint su file: se lo script viene interrotto, riparte da dove si era fermato
  - Pausa configurabile tra scritture per non saturare la rete
  - Riepilogo finale con fixture fallite elencate per eventuale re-run manuale

Uso tipico:
  python AGGIORNA_CAMPO_db_json_analisi.py              # solo NULL
  python AGGIORNA_CAMPO_db_json_analisi.py --force      # ricalcola TUTTI
  python AGGIORNA_CAMPO_db_json_analisi.py --dry-run    # simula, nessuna scrittura
  python AGGIORNA_CAMPO_db_json_analisi.py --limit 200  # test su N fixture
  python AGGIORNA_CAMPO_db_json_analisi.py --league 39  # solo una lega
  python AGGIORNA_CAMPO_db_json_analisi.py --season 2024
  python AGGIORNA_CAMPO_db_json_analisi.py --fixture 1454540  # singola fixture (test)
  python AGGIORNA_CAMPO_db_json_analisi.py --resume     # riprende da checkpoint
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ----------------------------------------------------------
# Project root su sys.path
# ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_client import get_supabase_client  # noqa: E402
from Prediction.today_predictions_backfill import compute_db_json_analisi  # noqa: E402

# ----------------------------------------------------------
# Logging
# ----------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------
# Configurazione
# ----------------------------------------------------------
PAGE_SIZE        = 1000   # righe per pagina nella fetch iniziale
WRITE_DELAY      = 0.05   # secondi tra una scrittura e la successiva (50ms)
PROGRESS_EVERY   = 100    # log di avanzamento ogni N fixture scritte
MAX_RETRIES      = 3      # tentativi per ogni scrittura
RETRY_BASE_DELAY = 2.0    # secondi base per backoff esponenziale (2s, 4s, 8s)
CHECKPOINT_FILE  = PROJECT_ROOT / "aggiorna_db_json_checkpoint.json"


# ----------------------------------------------------------
# Checkpoint
# ----------------------------------------------------------

def load_checkpoint() -> Set[int]:
    """Carica la lista di fixture_id già scritte con successo."""
    if not CHECKPOINT_FILE.exists():
        return set()
    try:
        data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        done = set(data.get("done", []))
        logger.info("📌 Checkpoint trovato: %d fixture già scritte — verranno saltate", len(done))
        return done
    except Exception as exc:
        logger.warning("⚠️  Impossibile leggere checkpoint: %s — si riparte da zero", exc)
        return set()


def save_checkpoint(done: Set[int]) -> None:
    """Salva la lista aggiornata di fixture_id già scritte."""
    try:
        CHECKPOINT_FILE.write_text(
            json.dumps({"done": sorted(done), "updated_at": datetime.now(timezone.utc).isoformat()},
                       indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("⚠️  Impossibile salvare checkpoint: %s", exc)


def clear_checkpoint() -> None:
    """Elimina il checkpoint a fine run completato con successo."""
    try:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
    except Exception:
        pass


# ----------------------------------------------------------
# Fetch
# ----------------------------------------------------------

def fetch_target_fixtures(
    sb: Any,
    force: bool,
    league_id: Optional[int],
    season_year: Optional[int],
    limit: Optional[int],
    fixture_id: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Recupera le fixture_predictions da processare.
    Filtra su result_status_short IN ('FT','AET','PEN').
    Se fixture_id è fornito, processa solo quella.
    Se force=False aggiunge il filtro db_json_analisi IS NULL.
    """
    offset = 0
    results: List[Dict[str, Any]] = []

    while True:
        q = (
            sb.table("fixture_predictions")
            .select("fixture_id,league_id,season_year,fixture_date,home_team_id,away_team_id")
            .in_("result_status_short", ["FT", "AET", "PEN"])
        )

        if fixture_id is not None:
            q = q.eq("fixture_id", fixture_id)
        else:
            if not force:
                q = q.is_("db_json_analisi", "null")
            if league_id is not None:
                q = q.eq("league_id", league_id)
            if season_year is not None:
                q = q.eq("season_year", season_year)

        resp = q.range(offset, offset + PAGE_SIZE - 1).execute()
        batch: List[Dict[str, Any]] = getattr(resp, "data", []) or []
        results.extend(batch)

        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    if fixture_id is None and limit:
        results = results[:limit]

    return results


# ----------------------------------------------------------
# Write singola fixture con retry esponenziale
# ----------------------------------------------------------

def write_one(sb: Any, fixture_id: int, analysis: Dict[str, Any], dry_run: bool) -> Optional[str]:
    """
    Aggiorna db_json_analisi per una singola fixture.
    Ritenta con backoff esponenziale in caso di errore.
    Ritorna None se OK, stringa di errore se tutti i tentativi falliscono.
    """
    if dry_run:
        return None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            sb.table("fixture_predictions").update({
                "db_json_analisi": analysis,
                "updated_at":      datetime.now(timezone.utc).isoformat(),
            }).eq("fixture_id", fixture_id).execute()
            return None  # successo

        except Exception as exc:
            wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))  # 2s, 4s, 8s
            if attempt < MAX_RETRIES:
                logger.warning(
                    "  ⚠️  fixture_id=%s tentativo %d/%d fallito (%s) — retry in %.0fs",
                    fixture_id, attempt, MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
            else:
                return str(exc)  # tutti i tentativi esauriti

    return "MAX_RETRIES raggiunto"


# ----------------------------------------------------------
# Runner principale
# ----------------------------------------------------------

def run(
    force: bool = False,
    dry_run: bool = False,
    league_id: Optional[int] = None,
    season_year: Optional[int] = None,
    limit: Optional[int] = None,
    fixture_id: Optional[int] = None,
    resume: bool = False,
) -> None:
    t_start = time.monotonic()

    if dry_run:
        logger.info("⚠️  DRY-RUN attivo — nessuna scrittura verrà effettuata")

    # ---- Client unico per tutta la sessione ----
    sb = get_supabase_client()

    # ---- Checkpoint ----
    already_done: Set[int] = load_checkpoint() if resume else set()
    if not resume and CHECKPOINT_FILE.exists():
        logger.info(
            "ℹ️  Esiste un checkpoint da una sessione precedente. "
            "Usa --resume per riprenderlo, oppure prosegui per ignorarlo."
        )

    # ---- Fetch ----
    logger.info(
        "🔍 Fetching fixture_predictions  [fixture=%s | force=%s | league=%s | season=%s | limit=%s]",
        fixture_id, force, league_id, season_year, limit,
    )
    rows = fetch_target_fixtures(sb, force, league_id, season_year, limit, fixture_id)
    if not rows:
        logger.info("✅ Nessuna fixture da aggiornare.")
        return

    total = len(rows)
    logger.info("📊 Fixture da processare: %d", total)

    # ---- Raggruppa per (league_id, season_year) ----
    groups: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for r in rows:
        try:
            key = (int(r["league_id"]), int(r["season_year"]))
        except (TypeError, KeyError, ValueError):
            logger.warning("⚠️  Riga ignorata (dati mancanti): %s", r)
            continue
        groups.setdefault(key, []).append(r)

    # Cache condivisa per lega/stagione — costruita una volta, riutilizzata
    match_cache: Dict[Tuple[int, int], Dict[str, Any]] = {}
    xg_cache:    Dict[Tuple[int, int], Dict[Tuple[int, int], float]] = {}

    written   = 0
    resumed   = 0   # fixture saltate perché già scritte in sessione precedente (--resume)
    skipped   = 0
    errors    = 0
    failed_ids: List[int] = []
    done_set: Set[int] = set(already_done)

    # ---- Ciclo principale ----
    for (l_id, s_year), group in groups.items():
        logger.info("🚀 Lega %-6d | Stagione %d | %d fixture", l_id, s_year, len(group))

        for fixture_row in group:
            fid = fixture_row.get("fixture_id")

            # Skip se già scritto in una sessione precedente (--resume)
            if fid in already_done:
                resumed += 1
                continue

            try:
                ctx: Dict[str, Any] = {
                    "fixture_id":   int(fixture_row["fixture_id"]),
                    "league_id":    int(fixture_row["league_id"]),
                    "season_year":  int(fixture_row["season_year"]),
                    "fixture_date": fixture_row["fixture_date"],
                    "home_team_id": int(fixture_row["home_team_id"]) if fixture_row.get("home_team_id") else None,
                    "away_team_id": int(fixture_row["away_team_id"]) if fixture_row.get("away_team_id") else None,
                }

                result = compute_db_json_analisi(ctx, match_cache, xg_cache)

                if result is None:
                    skipped += 1
                    continue  # dati insufficienti per Poisson

                analysis, _ht_pred = result

                # Scrittura sequenziale con retry
                err = write_one(sb, int(ctx["fixture_id"]), analysis, dry_run)

                if err:
                    errors += 1
                    failed_ids.append(int(ctx["fixture_id"]))
                    logger.error("  ❌ fixture_id=%s FALLITA dopo %d tentativi: %s", fid, MAX_RETRIES, err)
                else:
                    written += 1
                    done_set.add(int(ctx["fixture_id"]))
                    # Salva checkpoint ogni 100 scritture OK
                    if written % 100 == 0:
                        save_checkpoint(done_set)

                # Pausa tra scritture — evita burst sul socket Windows
                if not dry_run:
                    time.sleep(WRITE_DELAY)

                # Log avanzamento
                if (written + resumed + skipped + errors) % PROGRESS_EVERY == 0:
                    done_total = written + resumed + skipped + errors
                    pct = done_total / total * 100
                    elapsed = time.monotonic() - t_start
                    eta = (elapsed / done_total * (total - done_total)) if done_total > 0 else 0
                    eta_m, eta_s = divmod(int(eta), 60)
                    logger.info(
                        "  📈 %d/%d (%.1f%%)  scritti=%d  skip=%d  err=%d  ETA: %dm%02ds",
                        done_total, total, pct, written, skipped, errors, eta_m, eta_s,
                    )

            except Exception as exc:
                errors += 1
                failed_ids.append(fid)
                logger.error("❌ fixture_id=%s — errore inatteso: %s", fid, exc)

    # Flush checkpoint finale
    if not dry_run:
        save_checkpoint(done_set)

    # ---- Riepilogo ----
    elapsed = time.monotonic() - t_start
    mins, secs = divmod(int(elapsed), 60)

    logger.info("=" * 65)
    logger.info("🏁  COMPLETATO  (tempo: %dm %02ds)", mins, secs)
    logger.info("    Scritti    : %d", written)
    logger.info("    Ripresi    : %d  (già scritti in sessione precedente, saltati)", resumed)
    logger.info("    Skippati   : %d  (dati Poisson insufficienti)", skipped)
    logger.info("    Errori     : %d", errors)
    logger.info("    Totale     : %d", total)
    if dry_run:
        logger.info("    ⚠️  DRY-RUN — nessuna scrittura effettuata")
    logger.info("=" * 65)

    if failed_ids:
        logger.warning("⚠️  Fixture non scritte (%d) — rilancia con --resume per riprovare:", len(failed_ids))
        logger.warning("    %s", failed_ids[:50])
        if len(failed_ids) > 50:
            logger.warning("    ... e altri %d", len(failed_ids) - 50)
    elif not dry_run and errors == 0:
        # Tutto OK: rimuovi checkpoint
        clear_checkpoint()
        logger.info("✅ Checkpoint rimosso — run completato senza errori")


# ----------------------------------------------------------
# Entry point CLI
# ----------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Aggiorna il campo db_json_analisi in fixture_predictions.\n"
            "Aggiorna SOLO quel campo — non tocca ht_predictions né altri campi.\n\n"
            "Esempi:\n"
            "  python AGGIORNA_CAMPO_db_json_analisi.py                    # solo NULL\n"
            "  python AGGIORNA_CAMPO_db_json_analisi.py --force            # ricalcola tutti\n"
            "  python AGGIORNA_CAMPO_db_json_analisi.py --dry-run          # simula\n"
            "  python AGGIORNA_CAMPO_db_json_analisi.py --resume           # riprende da checkpoint\n"
            "  python AGGIORNA_CAMPO_db_json_analisi.py --fixture 1454540  # singola fixture\n"
            "  python AGGIORNA_CAMPO_db_json_analisi.py --league 39        # solo una lega\n"
            "  python AGGIORNA_CAMPO_db_json_analisi.py --season 2024      # solo una stagione\n"
        ),
    )
    parser.add_argument("--force",    action="store_true", help="Ricalcola anche chi ha già db_json_analisi.")
    parser.add_argument("--dry-run",  action="store_true", help="Simula senza scrivere nulla nel DB.")
    parser.add_argument("--resume",   action="store_true", help="Riprende dal checkpoint dell'ultimo run interrotto.")
    parser.add_argument("--limit",    type=int, metavar="N",          help="Processa al massimo N fixture.")
    parser.add_argument("--league",   type=int, metavar="LEAGUE_ID",  help="Filtra per league_id.")
    parser.add_argument("--season",   type=int, metavar="YEAR",       help="Filtra per season_year.")
    parser.add_argument("--fixture",  type=int, metavar="FIXTURE_ID", help="Processa una singola fixture.")

    args = parser.parse_args()

    run(
        force=args.force,
        dry_run=args.dry_run,
        league_id=args.league,
        season_year=args.season,
        limit=args.limit,
        fixture_id=args.fixture,
        resume=args.resume,
    )
