# daily_yesterday_backfill.py

import argparse
import logging
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple, Set, Optional

from api_client import APIFootballClient
from fixtures_backfill import map_fixture_to_row
from per_fixture_backfill import get_coverage_for_season, process_single_fixture
from db_client import get_supabase_client

from standings_backfill import backfill_standings_for_league_season
from top_scorers_backfill import backfill_top_scorers_for_league_season
from top_assists_backfill import backfill_top_assists_for_league_season
from top_cards_backfill import backfill_top_cards_for_league_season
from injuries_backfill import backfill_injuries_for_league_season

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# =====================================================
# MATCH "FINITI" (API-Football status.short)
# - FT  : Match Finished
# - AET : Match Finished After Extra Time
# - PEN : Match Finished After Penalty Shootout
# =====================================================
FINISHED_STATUSES = {"FT", "AET", "PEN"}

# Cache client Supabase (evita ricreazioni)
_SUPABASE = None


def get_supabase():
    global _SUPABASE
    if _SUPABASE is None:
        _SUPABASE = get_supabase_client()
    return _SUPABASE


def _get_status_short(fixture_entry: Dict[str, Any]) -> Optional[str]:
    try:
        return fixture_entry.get("fixture", {}).get("status", {}).get("short")
    except Exception:
        return None


# =====================================================
# FIXTURES PER DATA (API)
# =====================================================

def fetch_fixtures_for_date(api: APIFootballClient, target_date: str) -> List[Dict[str, Any]]:
    logger.info("📡 Chiamata API /fixtures?date=%s", target_date)
    data = api.call("/fixtures", params={"date": target_date})
    return data.get("response") or []


# =====================================================
# UPSERT STRICT SU MATCHES
# =====================================================

def upsert_matches_strict(rows: List[Dict[str, Any]]) -> None:
    """
    UPSERT vero su matches:
    - usa fixture_id come chiave
    - se fallisce → crash
    """
    if not rows:
        return

    sb = get_supabase()
    CHUNK = 200

    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        logger.info("💾 Upsert STRICT matches chunk %s (righe: %s)", i // CHUNK + 1, len(chunk))

        sb.table("matches").upsert(
            chunk,
            on_conflict="fixture_id"
        ).execute()

        time.sleep(0.2)

    logger.info("✅ Upsert STRICT matches completato.")


def upsert_matches_from_fixtures_finished_only(
    fixtures_json: List[Dict[str, Any]]
) -> List[Dict[str, int]]:
    """
    - filtra SOLO fixture con status.short in FINISHED_STATUSES (FT/AET/PEN)
    - upsert in matches
    - ritorna fixture_keys per per-fixture
    """

    statuses = Counter(_get_status_short(f) or "UNKNOWN" for f in fixtures_json)
    logger.info("📊 Status breakdown: %s", dict(statuses))

    finished = [
        f for f in fixtures_json
        if (_get_status_short(f) in FINISHED_STATUSES)
    ]

    logger.info(
        "✅ Filtrate FINISHED %s: %s (skippate non-finite: %s)",
        sorted(FINISHED_STATUSES),
        len(finished),
        len(fixtures_json) - len(finished),
    )

    rows: List[Dict[str, Any]] = []
    fixture_keys: List[Dict[str, int]] = []

    for entry in finished:
        row = map_fixture_to_row(entry)
        if not row:
            continue

        rows.append(row)
        fixture_keys.append(
            {
                "fixture_id": int(row["fixture_id"]),
                "league_id": int(row["league_id"]),
                "season_year": int(row["season_year"]),
            }
        )

    logger.info("📌 Righe matches FINISHED mappate: %s", len(rows))

    upsert_matches_strict(rows)

    # deduplica
    uniq = {fk["fixture_id"]: fk for fk in fixture_keys}
    return list(uniq.values())


# =====================================================
# SKIP SE GIA' PROCESSATO (BATCH)
# =====================================================

def coverage_required_tables(coverage: Dict[str, Any]) -> List[str]:
    """
    Mappa coverage -> tabelle per-fixture che devono esistere per considerare 'già processato'.
    """
    required: List[str] = []
    if coverage.get("events"):
        required.append("match_events")
    if coverage.get("lineups"):
        required.append("match_lineups")
    if coverage.get("team_stats"):
        required.append("match_team_stats")
    if coverage.get("player_stats"):
        required.append("match_player_stats")
    if coverage.get("odds"):
        required.append("match_odds")
    return required


def fetch_existing_fixture_ids_for_table(sb, table: str, fixture_ids: List[int], chunk: int = 200) -> Set[int]:
    """
    Ritorna il set dei fixture_id presenti in `table` per i fixture_ids richiesti.
    Esegue query a chunk per stabilità.
    """
    existing: Set[int] = set()
    if not fixture_ids:
        return existing

    uniq = sorted({int(x) for x in fixture_ids})

    for i in range(0, len(uniq), chunk):
        chunk_ids = uniq[i:i + chunk]
        resp = (
            sb.table(table)
            .select("fixture_id")
            .in_("fixture_id", chunk_ids)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        for r in data:
            fx = r.get("fixture_id")
            if fx is not None:
                existing.add(int(fx))

        time.sleep(0.05)  # micro-throttle

    return existing


def build_processed_map_for_group(
    sb,
    fixture_ids: List[int],
    required_tables: List[str],
) -> Dict[int, bool]:
    """
    Per un gruppo (stesso coverage), determina per ogni fixture_id se è già processato:
    "già processato" = presente in TUTTE le required_tables.
    """
    processed_map: Dict[int, bool] = {int(fx): True for fx in fixture_ids}

    if not required_tables:
        # se non c'è nulla richiesto, non skippiamo (forziamo processing)
        return {int(fx): False for fx in fixture_ids}

    # Pre-carica set per tabella
    existing_by_table: Dict[str, Set[int]] = {}
    for t in required_tables:
        existing_by_table[t] = fetch_existing_fixture_ids_for_table(sb, t, fixture_ids)

    # Intersezione logica: deve esserci in tutte
    for fx in fixture_ids:
        fx = int(fx)
        for t in required_tables:
            if fx not in existing_by_table[t]:
                processed_map[fx] = False
                break

    return processed_map


# =====================================================
# PER-FIXTURE
# =====================================================

def run_per_fixture_for_date(
    api: APIFootballClient,
    fixtures_keys: List[Dict[str, int]],
) -> Set[Tuple[int, int]]:

    season_keys: Set[Tuple[int, int]] = set()
    logger.info("▶️ Avvio per-fixture su %s match FINISHED", len(fixtures_keys))

    # 1) Raggruppo per (league_id, season_year) perché coverage dipende da questi
    groups: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for fk in fixtures_keys:
        groups[(int(fk["league_id"]), int(fk["season_year"]))].append(int(fk["fixture_id"]))

    sb = get_supabase()

    skipped_already = 0
    processed = 0

    # 2) Per ogni gruppo calcolo in batch chi è già processato
    for (league_id, season_year), fx_ids in groups.items():
        coverage = get_coverage_for_season(league_id, season_year)
        if not coverage:
            logger.warning("⚠️ Nessun coverage per league_id=%s season=%s → skip gruppo (%s fixtures)",
                           league_id, season_year, len(fx_ids))
            continue

        required_tables = coverage_required_tables(coverage)

        processed_map = build_processed_map_for_group(
            sb=sb,
            fixture_ids=fx_ids,
            required_tables=required_tables,
        )

        # 3) Ora processiamo solo quelli non già processati
        for fixture_id in fx_ids:
            if processed_map.get(int(fixture_id), False) is True:
                skipped_already += 1
                logger.info("⏭️ Skip già processato fixture_id=%s", fixture_id)
                season_keys.add((league_id, season_year))
                continue

            process_single_fixture(
                api,
                int(fixture_id),
                league_id,
                season_year,
                coverage,
            )

            processed += 1
            season_keys.add((league_id, season_year))

    logger.info("📌 Per-fixture: processed=%s | skipped_already=%s", processed, skipped_already)
    return season_keys


# =====================================================
# AGGREGATI
# =====================================================

def run_aggregates_for_seasons(season_keys: Set[Tuple[int, int]]) -> None:
    for league_id, season_year in season_keys:
        coverage = get_coverage_for_season(league_id, season_year)
        if not coverage:
            continue

        if coverage.get("standings"):
            backfill_standings_for_league_season(league_id, season_year)
        if coverage.get("top_scorers"):
            backfill_top_scorers_for_league_season(league_id, season_year)
        if coverage.get("top_assists"):
            backfill_top_assists_for_league_season(league_id, season_year)
        if coverage.get("top_cards"):
            backfill_top_cards_for_league_season(league_id, season_year)
        if coverage.get("injuries"):
            backfill_injuries_for_league_season(league_id, season_year)


# =====================================================
# ORCHESTRATORE
# =====================================================

def run_daily_backfill_for_date(target_date: str) -> None:
    logger.info("==============================================")
    logger.info("🚀 Avvio DAILY BACKFILL (FINISHED-only) per data=%s", target_date)
    logger.info("==============================================")

    api = APIFootballClient()

    fixtures_json = fetch_fixtures_for_date(api, target_date)

    fixtures_keys = upsert_matches_from_fixtures_finished_only(fixtures_json)

    if not fixtures_keys:
        logger.warning("⚠️ Nessun match FINISHED trovato per %s", target_date)
        return

    season_keys = run_per_fixture_for_date(api, fixtures_keys)

    run_aggregates_for_seasons(season_keys)

    logger.info("🏁 DAILY BACKFILL completato per data=%s", target_date)


# =====================================================
# CLI
# - Default: ieri
# - --date: singola data (uso normale)
# - --run-december-range: SOLO questa volta (2025-12-04 -> 2025-12-28)
# =====================================================

DEC_RANGE_FROM = date(2025, 12, 4)
DEC_RANGE_TO = date(2025, 12, 28)


def _parse_iso_date(s: str) -> date:
    return date.fromisoformat(s)


def _run_range(d_from: date, d_to: date) -> None:
    d = d_from
    while d <= d_to:
        run_daily_backfill_for_date(d.isoformat())
        d += timedelta(days=1)


def parse_args_and_run():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--date",
        type=str,
        help="Esegue una singola data (ISO, es: 2025-12-28). Se omesso: ieri.",
    )

    parser.add_argument(
        "--run-december-range",
        action="store_true",
        help="Esegue SOLO questa volta il range 2025-12-04 -> 2025-12-28.",
    )

    args = parser.parse_args()

    if args.run_december_range:
        if args.date:
            raise SystemExit("❌ Non usare --date insieme a --run-december-range.")
        logger.info("🗓️ Modalità RANGE attiva: %s -> %s", DEC_RANGE_FROM, DEC_RANGE_TO)
        _run_range(DEC_RANGE_FROM, DEC_RANGE_TO)
        return

    if args.date:
        target_date = _parse_iso_date(args.date).isoformat()
    else:
        target_date = (date.today() - timedelta(days=1)).isoformat()

    run_daily_backfill_for_date(target_date)


if __name__ == "__main__":
    parse_args_and_run()
