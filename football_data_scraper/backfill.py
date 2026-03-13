"""
Orchestratore principale del backfill quote storiche da football-data.co.uk.

Uso:
    python backfill.py --league 135 --dry-run        # audit senza scrivere
    python backfill.py --league 135                  # scrittura reale

Comportamento:
  - Scarica CSV da football-data per ogni stagione presente nel nostro DB
  - Abbina ogni partita CSV al fixture_id corretto (date + score + nome squadra)
  - Inserisce in match_odds SOLO i record (fixture_id, market_name, label, bookmaker_name)
    che NON esistono già — a prescindere dallo snapshot_type
  - Inserisce in match_team_stats SOLO i record (fixture_id, team_id, stat_type)
    che NON esistono già
  - Non sovrascrive MAI nulla
  - Produce un log di audit completo

NESSUNA SOVRASCRITTURA — SOLO INSERIMENTO DI DATI MANCANTI.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

# ── sys.path setup ───────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db_client import get_supabase_client
from football_data_scraper.league_mapping import get_league_info
from football_data_scraper.csv_downloader import download_csv
from football_data_scraper.fixture_matcher import load_fixtures_for_league, match_csv_to_fixtures
from football_data_scraper.odds_column_map import ALL_ODDS_COLS, STATS_COLS

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Costanti ─────────────────────────────────────────────────────────────────
INSERT_CHUNK_SIZE = 200     # righe per batch INSERT
SNAPSHOT_TYPE = "football_data_csv"


# ─────────────────────────────────────────────────────────────────────────────
# Fetch stagioni disponibili nel DB per una lega
# ─────────────────────────────────────────────────────────────────────────────

def _get_db_seasons(league_id: int) -> List[int]:
    """Restituisce le stagioni (season_year) presenti in matches per la lega.
    Usa la tabella `matches` (storico completo partite giocate, status_short=FT).
    """
    sb = get_supabase_client()
    resp = (
        sb.table("matches")
        .select("season_year")
        .eq("league_id", league_id)
        .eq("status_short", "FT")
        .execute()
    )
    data = getattr(resp, "data", None) or []
    seasons = sorted({int(r["season_year"]) for r in data if r.get("season_year") is not None})
    logger.info("Stagioni nel DB per league_id=%d: %s", league_id, seasons)
    return seasons


# ─────────────────────────────────────────────────────────────────────────────
# Fetch existing match_odds per set di fixture_id
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_existing_odds_keys(fixture_ids: List[int]) -> Set[Tuple[int, str, str, str]]:
    """
    Carica tutte le chiavi (fixture_id, market_name, label, bookmaker_name) già
    presenti in match_odds per i fixture_ids indicati.
    Usato per deduplicazione prima dell'INSERT.
    """
    if not fixture_ids:
        return set()

    sb = get_supabase_client()
    existing: Set[Tuple[int, str, str, str]] = set()

    CHUNK = 200
    for i in range(0, len(fixture_ids), CHUNK):
        chunk = fixture_ids[i: i + CHUNK]
        offset = 0
        page_size = 1000
        while True:
            resp = (
                sb.table("match_odds")
                .select("fixture_id,market_name,label,bookmaker_name")
                .in_("fixture_id", chunk)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = getattr(resp, "data", None) or []
            for r in rows:
                fid = r.get("fixture_id")
                mn = (r.get("market_name") or "").strip()
                lb = (r.get("label") or "").strip()
                bk = (r.get("bookmaker_name") or "").strip()
                if fid:
                    existing.add((int(fid), mn, lb, bk))
            if len(rows) < page_size:
                break
            offset += page_size

    logger.info("Trovate %d combinazioni odds già esistenti per %d fixture",
                len(existing), len(fixture_ids))
    return existing


# ─────────────────────────────────────────────────────────────────────────────
# Fetch existing match_team_stats per set di fixture_id
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_existing_stats_keys(fixture_ids: List[int]) -> Set[Tuple[int, int, str]]:
    """
    Carica tutte le chiavi (fixture_id, team_id, stat_type) già presenti
    in match_team_stats per i fixture_ids indicati.
    """
    if not fixture_ids:
        return set()

    sb = get_supabase_client()
    existing: Set[Tuple[int, int, str]] = set()

    CHUNK = 200
    for i in range(0, len(fixture_ids), CHUNK):
        chunk = fixture_ids[i: i + CHUNK]
        offset = 0
        page_size = 1000
        while True:
            resp = (
                sb.table("match_team_stats")
                .select("fixture_id,team_id,stat_type")
                .in_("fixture_id", chunk)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = getattr(resp, "data", None) or []
            for r in rows:
                fid = r.get("fixture_id")
                tid = r.get("team_id")
                st = (r.get("stat_type") or "").strip()
                if fid and tid:
                    existing.add((int(fid), int(tid), st))
            if len(rows) < page_size:
                break
            offset += page_size

    logger.info("Trovate %d combinazioni stats già esistenti per %d fixture",
                len(existing), len(fixture_ids))
    return existing


# ─────────────────────────────────────────────────────────────────────────────
# Costruzione righe match_odds da CSV
# ─────────────────────────────────────────────────────────────────────────────

def _build_odds_rows(
    matched_df: pd.DataFrame,
    league_id: int,
    season_year: int,
    existing_keys: Set[Tuple[int, str, str, str]],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Per ogni partita matchata e ogni colonna odds nel CSV, genera le righe
    da inserire in match_odds — escludendo quelle già presenti.

    Returns: (rows_to_insert, n_skipped)
    """
    rows: List[Dict[str, Any]] = []
    n_skipped = 0

    # Colonne odds presenti nel CSV per questa stagione
    available_odds_cols = {
        col: defn
        for col, defn in ALL_ODDS_COLS.items()
        if col in matched_df.columns
    }

    if not available_odds_cols:
        logger.warning("Nessuna colonna odds riconosciuta nel CSV stagione %d", season_year)
        return rows, 0

    logger.info("Colonne odds disponibili nel CSV: %s", list(available_odds_cols.keys()))

    for _, row in matched_df.iterrows():
        fixture_id = int(row["fixture_id"])

        for col, (bookmaker, market_name, label, market_key) in available_odds_cols.items():
            raw = row.get(col)
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue  # valore mancante nel CSV, skip silenzioso

            try:
                odd_value = float(raw)
            except (ValueError, TypeError):
                continue

            # Deduplicazione: skip se questa combinazione esiste già
            key = (fixture_id, market_name, label, bookmaker)
            if key in existing_keys:
                n_skipped += 1
                continue

            rows.append({
                "fixture_id": fixture_id,
                "league_id": league_id,
                "season_year": season_year,
                "bookmaker_id": None,
                "bookmaker_name": bookmaker,
                "market_key": market_key,
                "market_name": market_name,
                "label": label,
                "odd_value": odd_value,
                "snapshot_type": SNAPSHOT_TYPE,
                "snapshot_time": str(row["fixture_date"]) + "T12:00:00",
                "raw_json": {"csv_col": col, "value": raw},
            })
            # Aggiungi alla cache per evitare duplicati intra-batch
            existing_keys.add(key)

    return rows, n_skipped


# ─────────────────────────────────────────────────────────────────────────────
# Costruzione righe match_team_stats da CSV
# ─────────────────────────────────────────────────────────────────────────────

def _build_stats_rows(
    matched_df: pd.DataFrame,
    league_id: int,
    season_year: int,
    existing_stats_keys: Set[Tuple[int, int, str]],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Per ogni partita matchata e ogni colonna statistica nel CSV, genera le
    righe da inserire in match_team_stats — escludendo quelle già presenti.

    Returns: (rows_to_insert, n_skipped)
    """
    rows: List[Dict[str, Any]] = []
    n_skipped = 0

    available_stats_cols = {
        col: defn
        for col, defn in STATS_COLS.items()
        if col in matched_df.columns
    }

    if not available_stats_cols:
        return rows, 0

    for _, row in matched_df.iterrows():
        fixture_id = int(row["fixture_id"])
        home_team_id = row.get("home_team_id")
        away_team_id = row.get("away_team_id")
        home_team_name = str(row.get("HomeTeam", ""))
        away_team_name = str(row.get("AwayTeam", ""))

        for col, (side, stat_type) in available_stats_cols.items():
            raw = row.get(col)
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue

            try:
                value_numeric = float(raw)
            except (ValueError, TypeError):
                continue

            if side == "home":
                team_id = home_team_id
                team_name = home_team_name
            else:
                team_id = away_team_id
                team_name = away_team_name

            if team_id is None:
                continue

            team_id_int = int(team_id)
            key = (fixture_id, team_id_int, stat_type)
            if key in existing_stats_keys:
                n_skipped += 1
                continue

            rows.append({
                "fixture_id": fixture_id,
                "league_id": league_id,
                "season_year": season_year,
                "team_id": team_id_int,
                "team_name": team_name,
                "stat_type": stat_type,
                "value_text": str(int(value_numeric)) if value_numeric == int(value_numeric) else str(value_numeric),
                "value_numeric": value_numeric,
                "raw_json": {"csv_col": col, "value": raw, "source": SNAPSHOT_TYPE},
            })
            existing_stats_keys.add(key)

    return rows, n_skipped


# ─────────────────────────────────────────────────────────────────────────────
# INSERT sicuro a chunk
# ─────────────────────────────────────────────────────────────────────────────

def _insert_rows(table: str, rows: List[Dict[str, Any]], dry_run: bool) -> Tuple[int, int]:
    """
    Inserisce `rows` nella tabella indicata in chunk da INSERT_CHUNK_SIZE.
    Se dry_run=True non scrive nulla ma logga.

    Returns: (n_inserted, n_errors)
    """
    if not rows:
        return 0, 0

    if dry_run:
        logger.info("[DRY-RUN] Salterei INSERT di %d righe in %s", len(rows), table)
        return len(rows), 0

    sb = get_supabase_client()
    n_inserted = 0
    n_errors = 0

    for i in range(0, len(rows), INSERT_CHUNK_SIZE):
        chunk = rows[i: i + INSERT_CHUNK_SIZE]
        try:
            sb.table(table).insert(chunk).execute()
            n_inserted += len(chunk)
        except Exception as e:
            msg = str(e)
            if "duplicate key" in msg.lower() or "unique" in msg.lower():
                # Duplicato residuo — non grave, skippa
                logger.warning("[%s] Duplicato residuo in chunk %d, skip: %s",
                               table, i // INSERT_CHUNK_SIZE + 1, msg[:120])
                n_errors += 1
            else:
                logger.error("[%s] Errore INSERT chunk %d: %s",
                             table, i // INSERT_CHUNK_SIZE + 1, msg[:200])
                n_errors += 1
        time.sleep(0.05)  # throttle minimo Supabase

    return n_inserted, n_errors


# ─────────────────────────────────────────────────────────────────────────────
# Orchestratore principale
# ─────────────────────────────────────────────────────────────────────────────

def run_backfill(league_id: int, dry_run: bool = True) -> None:
    info = get_league_info(league_id)
    mode_label = "[DRY-RUN]" if dry_run else "[LIVE]"

    logger.info("=" * 70)
    logger.info("%s Avvio backfill quote storiche", mode_label)
    logger.info("  Lega      : %s (id=%d)", info["name"], league_id)
    logger.info("  DB        : Supabase")
    logger.info("  Fonte     : football-data.co.uk")
    logger.info("  Modalità  : %s", "SOLO LOG — nessuna scrittura" if dry_run else "SCRITTURA REALE")
    logger.info("=" * 70)

    # 1. Stagioni disponibili nel DB
    db_seasons = _get_db_seasons(league_id)
    if not db_seasons:
        logger.error("Nessuna stagione con partite giocate nel DB per league_id=%d. Stop.", league_id)
        return

    # 2. Filtra stagioni disponibili su football-data
    fd_start = info["fd_start_year"]
    seasons_to_process = [s for s in db_seasons if s >= fd_start]
    logger.info("Stagioni da processare: %s", seasons_to_process)

    # 3. Carica TUTTE le fixture del DB per questa lega (una volta sola)
    fixtures_df = load_fixtures_for_league(league_id, seasons=seasons_to_process)
    if fixtures_df.empty:
        logger.error("Nessuna fixture caricata dal DB. Stop.")
        return

    # Riepilogo globale
    total_odds_inserted = 0
    total_odds_skipped = 0
    total_stats_inserted = 0
    total_stats_skipped = 0
    total_audit: List[Dict[str, Any]] = []
    seasons_summary: List[Dict[str, Any]] = []

    for season_year in seasons_to_process:
        logger.info("-" * 60)
        logger.info("Processando stagione %d/%d ...", season_year, season_year + 1)

        # 4. Scarica CSV
        csv_df = download_csv(league_id, season_year)
        if csv_df is None or csv_df.empty:
            logger.warning("CSV non disponibile per stagione %d — skip", season_year)
            seasons_summary.append({
                "season_year": season_year, "status": "csv_unavailable",
                "csv_rows": 0, "matched": 0,
                "odds_inserted": 0, "odds_skipped": 0,
                "stats_inserted": 0, "stats_skipped": 0,
            })
            continue

        # 5. Abbina CSV → fixture_id
        matched_df, audit_log = match_csv_to_fixtures(csv_df, fixtures_df, season_year)
        total_audit.extend(audit_log)

        n_matched = len(matched_df)
        n_csv = len(csv_df)
        if n_matched == 0:
            logger.warning("Nessuna riga abbinata per stagione %d — skip INSERT", season_year)
            seasons_summary.append({
                "season_year": season_year, "status": "no_matches",
                "csv_rows": n_csv, "matched": 0,
                "odds_inserted": 0, "odds_skipped": 0,
                "stats_inserted": 0, "stats_skipped": 0,
            })
            continue

        fixture_ids = matched_df["fixture_id"].astype(int).tolist()

        # 6. Carica keys esistenti in match_odds (batch fetch)
        existing_odds_keys = _fetch_existing_odds_keys(fixture_ids)

        # 7. Carica keys esistenti in match_team_stats (batch fetch)
        existing_stats_keys = _fetch_existing_stats_keys(fixture_ids)

        # 8. Costruisci righe odds da inserire
        odds_rows, odds_skipped = _build_odds_rows(
            matched_df, league_id, season_year, existing_odds_keys
        )

        # 9. Costruisci righe stats da inserire
        stats_rows, stats_skipped = _build_stats_rows(
            matched_df, league_id, season_year, existing_stats_keys
        )

        logger.info(
            "Stagione %d — odds: %d da inserire, %d già presenti | "
            "stats: %d da inserire, %d già presenti",
            season_year,
            len(odds_rows), odds_skipped,
            len(stats_rows), stats_skipped,
        )

        # 10. INSERT
        odds_ins, odds_err = _insert_rows("match_odds", odds_rows, dry_run)
        stats_ins, stats_err = _insert_rows("match_team_stats", stats_rows, dry_run)

        total_odds_inserted += odds_ins
        total_odds_skipped += odds_skipped
        total_stats_inserted += stats_ins
        total_stats_skipped += stats_skipped

        seasons_summary.append({
            "season_year": season_year,
            "status": "ok",
            "csv_rows": n_csv,
            "matched": n_matched,
            "match_rate": f"{100.0 * n_matched / n_csv:.1f}%" if n_csv else "0%",
            "odds_inserted": odds_ins,
            "odds_skipped": odds_skipped,
            "odds_errors": odds_err,
            "stats_inserted": stats_ins,
            "stats_skipped": stats_skipped,
            "stats_errors": stats_err,
        })

    # ── Riepilogo finale ──────────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("%s RIEPILOGO FINALE — lega %s (id=%d)", mode_label, info["name"], league_id)
    logger.info("")
    for s in seasons_summary:
        logger.info("  Stagione %s: %s", s["season_year"], s)
    logger.info("")
    logger.info("  TOTALE odds inserite   : %d", total_odds_inserted)
    logger.info("  TOTALE odds già presenti (skip): %d", total_odds_skipped)
    logger.info("  TOTALE stats inserite  : %d", total_stats_inserted)
    logger.info("  TOTALE stats già presenti (skip): %d", total_stats_skipped)
    logger.info("=" * 70)

    # ── Audit log su file ─────────────────────────────────────────────────────
    audit_path = os.path.join(ROOT, f"football_data_scraper/audit_league_{league_id}.json")
    try:
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.utcnow().isoformat(),
                "league_id": league_id,
                "dry_run": dry_run,
                "seasons_summary": seasons_summary,
                "match_audit": total_audit,
            }, f, indent=2, ensure_ascii=False)
        logger.info("Audit log salvato in: %s", audit_path)
    except Exception as e:
        logger.warning("Impossibile salvare audit log: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill quote storiche da football-data.co.uk"
    )
    parser.add_argument(
        "--league", type=int, required=True,
        help="league_id (es. 135 per Serie A)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Se specificato, esegue solo audit senza scrivere nel DB"
    )
    args = parser.parse_args()

    run_backfill(league_id=args.league, dry_run=args.dry_run)
