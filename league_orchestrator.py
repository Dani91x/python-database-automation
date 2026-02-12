from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from logger import logger  # type: ignore
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from db_client import get_supabase_client

# Backfill esistenti
from fixtures_backfill import backfill_fixtures_for_league_season
from per_fixture_backfill import backfill_per_fixture_for_league_season
from standings_backfill import backfill_standings_for_league_season
from top_scorers_backfill import backfill_top_scorers_for_league_season
from top_assists_backfill import backfill_top_assists_for_league_season
from top_cards_backfill import backfill_top_cards_for_league_season
from injuries_backfill import backfill_injuries_for_league_season
from missing_fixtures_backfill import run_past_seasons_backfill


_supabase = None


def get_supabase():
    global _supabase
    if _supabase is None:
        _supabase = get_supabase_client()
    return _supabase


# =========================
# Helper: refresh MV dashboard (NUOVO - safe)
# =========================
def refresh_coverage_mv() -> None:
    """
    Refresh della materialized view di reporting (dashboard).
    Non blocca l'orchestrator: se fallisce, logga e continua.
    Richiede che in Supabase esista la RPC:
      public.refresh_api_coverage_by_season_v2_mv()
    """
    supabase = get_supabase()
    try:
        logger.info("🔄 Refresh MV: api_coverage_by_season_v2_mv...")
        supabase.rpc("refresh_api_coverage_by_season_v2_mv", {}).execute()
        logger.info("✅ Refresh MV completato.")
    except Exception as e:
        logger.error("⚠️ Refresh MV fallito (non blocco l'orchestrator): %s", e)


# =========================
# Helper DB: stagioni & stato
# =========================


def get_league_seasons_with_coverage(league_id: int) -> List[Dict[str, Any]]:
    """
    Ritorna tutte le stagioni per una lega da api_coverage_by_season,
    ordinate dalla più vecchia alla più recente, con tutti i flag coverage.
    """
    supabase = get_supabase()
    logger.info("📡 Lettura stagioni da api_coverage_by_season per league_id=%s", league_id)
    resp = (
        supabase.table("api_coverage_by_season")
        .select(
            "season_year,"
            "fixtures_events, fixtures_lineups, "
            "fixtures_statistics_fixtures, fixtures_statistics_players, "
            "standings, players, top_scorers, top_assists, top_cards, "
            "injuries, predictions, odds"
        )
        .eq("league_id", league_id)
        .order("season_year", desc=False)  # ascendente
        .execute()
    )
    data = getattr(resp, "data", None) or []
    logger.info("📌 Trovate %s stagioni in coverage per league_id=%s", len(data), league_id)
    return data


def get_existing_season_states(league_id: int) -> Dict[int, Dict[str, Any]]:
    """
    Ritorna una mappa season_year -> record season_backfill_state per la lega.
    """
    supabase = get_supabase()
    logger.info("📡 Lettura stato stagioni da season_backfill_state per league_id=%s", league_id)
    resp = (
        supabase.table("season_backfill_state")
        .select("season_year, status, last_run_at, stats_json")
        .eq("league_id", league_id)
        .execute()
    )
    data = getattr(resp, "data", None) or []
    result: Dict[int, Dict[str, Any]] = {}
    for row in data:
        sy = row.get("season_year")
        if isinstance(sy, int):
            result[sy] = row
    logger.info("📌 Trovati %s record season_backfill_state per league_id=%s", len(result), league_id)
    return result


def upsert_season_state(
    league_id: int,
    season_year: int,
    status: str,
    stats_json: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Upsert in season_backfill_state per (league_id, season_year).
    """
    supabase = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()

    payload: Dict[str, Any] = {
        "league_id": league_id,
        "season_year": season_year,
        "status": status,
        "last_run_at": now_iso,
    }
    if stats_json is not None:
        payload["stats_json"] = stats_json

    logger.info(
        "📝 Aggiornamento season_backfill_state: league_id=%s, season_year=%s, status=%s",
        league_id,
        season_year,
        status,
    )

    resp = (
        supabase.table("season_backfill_state")
        .upsert(payload, on_conflict="league_id,season_year")
        .execute()
    )
    logger.debug("   🔎 Risposta upsert season_backfill_state: %s", getattr(resp, "data", None))


def count_rows(table: str, league_id: int, season_year: int) -> int:
    """
    Conta le righe in una tabella per (league_id, season_year).
    (usa select + len(data) per semplicità).
    """
    supabase = get_supabase()
    try:
        resp = (
            supabase.table(table)
            .select("id")
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        return len(data)
    except Exception as e:
        logger.error(
            "❌ Errore conteggio righe in %s per league_id=%s, season_year=%s: %s",
            table,
            league_id,
            season_year,
            e,
        )
        return 0


# =========================
# Backfill di una singola stagione
# =========================


def backfill_single_season_with_audit(
    league_id: int,
    coverage_row: Dict[str, Any],
) -> None:
    """
    Esegue TUTTO il backfill per una stagione:
      - fixtures
      - per-fixture (events, lineups, player stats, team stats, odds)
      - aggregati (standings, top_scorers, top_assists, top_cards, injuries)
    e scrive un report dettagliato in season_backfill_state.stats_json.
    """
    season_year = coverage_row.get("season_year")
    if not isinstance(season_year, int):
        logger.error("❌ coverage_row senza season_year valido: %s", coverage_row)
        return

    logger.info("==============================================")
    logger.info(
        "🚀 Inizio BACKFILL STAGIONE: league_id=%s, season_year=%s",
        league_id,
        season_year,
    )
    logger.info("==============================================")

    # Coverage dettagliato per audit
    coverage_flags = {
        "fixtures_events": bool(coverage_row.get("fixtures_events")),
        "fixtures_lineups": bool(coverage_row.get("fixtures_lineups")),
        "fixtures_statistics_fixtures": bool(coverage_row.get("fixtures_statistics_fixtures")),
        "fixtures_statistics_players": bool(coverage_row.get("fixtures_statistics_players")),
        "standings": bool(coverage_row.get("standings")),
        "players": bool(coverage_row.get("players")),
        "top_scorers": bool(coverage_row.get("top_scorers")),
        "top_assists": bool(coverage_row.get("top_assists")),
        "top_cards": bool(coverage_row.get("top_cards")),
        "injuries": bool(coverage_row.get("injuries")),
        "predictions": bool(coverage_row.get("predictions")),
        "odds": bool(coverage_row.get("odds")),
    }

    # Stato iniziale: running
    upsert_season_state(league_id, season_year, status="running", stats_json=None)

    # ======================
    # STEP 1: Fixtures (matches)
    # ======================
    logger.info("▶️ Step 1/4: Fixtures (matches)")
    try:
        backfill_fixtures_for_league_season(league_id, season_year)
    except Exception as e:
        logger.error(
            "❌ Errore durante backfill_fixtures_for_league_season(%s,%s): %s",
            league_id,
            season_year,
            e,
        )

    matches_count = count_rows("matches", league_id, season_year)
    logger.info(
        "   📊 matches_count per league_id=%s, season_year=%s → %s",
        league_id,
        season_year,
        matches_count,
    )

    # ======================
    # STEP 2: Per-fixture (events, lineups, stats, odds)
    # ======================
    logger.info("▶️ Step 2/4: per-fixture (events, lineups, player_stats, team_stats, odds)")
    per_fixture_stats = backfill_per_fixture_for_league_season(league_id, season_year)

    if per_fixture_stats is None:
        logger.warning(
            "⚠️ per_fixture_stats None per league_id=%s, season_year=%s (nessun fixture o coverage mancante)",
            league_id,
            season_year,
        )
        per_fixture_stats = {}

    # ======================
    # STEP 3: Aggregati di stagione
    # ======================
    logger.info("▶️ Step 3/4: Aggregati di stagione")

    aggregates_stats: Dict[str, Any] = {}

    # standings
    if coverage_flags["standings"]:
        logger.info("   📊 standings: coverage=true, avvio backfill...")
        try:
            backfill_standings_for_league_season(league_id, season_year)
        except Exception as e:
            logger.error(
                "❌ Errore durante backfill_standings_for_league_season(%s,%s): %s",
                league_id,
                season_year,
                e,
            )
        rows_after = count_rows("standings", league_id, season_year)
        aggregates_stats["standings"] = {"run": True, "rows_after": rows_after}
    else:
        logger.info("   ⏭️ standings: coverage=false, skippo.")
        aggregates_stats["standings"] = {"run": False, "rows_after": 0}

    # top_scorers
    if coverage_flags["top_scorers"]:
        logger.info("   🎯 top_scorers: coverage=true, avvio backfill...")
        try:
            backfill_top_scorers_for_league_season(league_id, season_year)
        except Exception as e:
            logger.error(
                "❌ Errore durante backfill_top_scorers_for_league_season(%s,%s): %s",
                league_id,
                season_year,
                e,
            )
        rows_after = count_rows("top_scorers", league_id, season_year)
        aggregates_stats["top_scorers"] = {"run": True, "rows_after": rows_after}
    else:
        logger.info("   ⏭️ top_scorers: coverage=false, skippo.")
        aggregates_stats["top_scorers"] = {"run": False, "rows_after": 0}

    # top_assists
    if coverage_flags["top_assists"]:
        logger.info("   🅰️ top_assists: coverage=true, avvio backfill...")
        try:
            backfill_top_assists_for_league_season(league_id, season_year)
        except Exception as e:
            logger.error(
                "❌ Errore durante backfill_top_assists_for_league_season(%s,%s): %s",
                league_id,
                season_year,
                e,
            )
        rows_after = count_rows("top_assists", league_id, season_year)
        aggregates_stats["top_assists"] = {"run": True, "rows_after": rows_after}
    else:
        logger.info("   ⏭️ top_assists: coverage=false, skippo.")
        aggregates_stats["top_assists"] = {"run": False, "rows_after": 0}

    # top_cards
    if coverage_flags["top_cards"]:
        logger.info("   🟨🟥 top_cards: coverage=true, avvio backfill...")
        try:
            backfill_top_cards_for_league_season(league_id, season_year)
        except Exception as e:
            logger.error(
                "❌ Errore durante backfill_top_cards_for_league_season(%s,%s): %s",
                league_id,
                season_year,
                e,
            )
        rows_after = count_rows("top_cards", league_id, season_year)
        aggregates_stats["top_cards"] = {"run": True, "rows_after": rows_after}
    else:
        logger.info("   ⏭️ top_cards: coverage=false, skippo.")
        aggregates_stats["top_cards"] = {"run": False, "rows_after": 0}

    # injuries
    if coverage_flags["injuries"]:
        logger.info("   🚑 injuries: coverage=true, avvio backfill...")
        try:
            backfill_injuries_for_league_season(league_id, season_year)
        except Exception as e:
            logger.error(
                "❌ Errore durante backfill_injuries_for_league_season(%s,%s): %s",
                league_id,
                season_year,
                e,
            )
        rows_after = count_rows("injuries", league_id, season_year)
        aggregates_stats["injuries"] = {"run": True, "rows_after": rows_after}
    else:
        logger.info("   ⏭️ injuries: coverage=false, skippo.")
        aggregates_stats["injuries"] = {"run": False, "rows_after": 0}

    # ======================
    # FLAG coverage NON implementati (players, predictions)
    # ======================
    not_implemented: Dict[str, bool] = {
        "players": coverage_flags["players"],
        "predictions": coverage_flags["predictions"],
    }
    for name, flag in not_implemented.items():
        if flag:
            logger.warning(
                "⚠️ Coverage.%s=true per league_id=%s, season_year=%s ma pipeline NON implementata → SKIP (TODO).",
                name,
                league_id,
                season_year,
            )

    # ======================
    # STEP 4: Scrittura AUDIT in season_backfill_state
    # ======================
    logger.info("▶️ Step 4/4: Scrittura AUDIT in season_backfill_state.stats_json")

    stats_json: Dict[str, Any] = {
        "coverage": coverage_flags,
        "fixtures": {
            "matches_count": matches_count,
        },
        "per_fixture": per_fixture_stats,
        "aggregates": aggregates_stats,
        "meta": {
            "version": "v1",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    upsert_season_state(league_id, season_year, status="completed", stats_json=stats_json)

    logger.info(
        "🏁 Backfill stagione COMPLETATO: league_id=%s, season_year=%s",
        league_id,
        season_year,
    )
    logger.info("==============================================")


# =========================
# Orchestratore lega
# =========================


def backfill_full_league(league_id: int) -> None:
    """
    Orchestratore completo per una singola lega:
      - legge tutte le stagioni dal coverage
      - salta quelle con season_backfill_state.status='completed'
      - per ognuna esegue backfill_single_season_with_audit
    """
    logger.info("==============================================")
    logger.info("🚀 Inizio backfill LEGA completa: league_id=%s", league_id)
    logger.info("==============================================")

    coverage_seasons = get_league_seasons_with_coverage(league_id)
    if not coverage_seasons:
        logger.warning(
            "⚠️ Nessuna stagione trovata in api_coverage_by_season per league_id=%s. Nulla da fare.",
            league_id,
        )
        return

    states_map = get_existing_season_states(league_id)

    seasons_to_process: List[Dict[str, Any]] = []
    for row in coverage_seasons:
        sy = row.get("season_year")
        if not isinstance(sy, int):
            continue
        existing = states_map.get(sy)
        if existing and existing.get("status") == "completed":
            logger.info(
                "⏭️ Stagione già completed in season_backfill_state, skippo: league_id=%s, season_year=%s",
                league_id,
                sy,
            )
            continue
        seasons_to_process.append(row)

    logger.info(
        "📌 Stagioni da processare per league_id=%s: %s (su %s totali coverage)",
        league_id,
        len(seasons_to_process),
        len(coverage_seasons),
    )

    for idx, row in enumerate(seasons_to_process):
        sy = row.get("season_year")
        logger.info(
            "▶️ [Stagione %s/%s] league_id=%s, season_year=%s",
            idx + 1,
            len(seasons_to_process),
            league_id,
            sy,
        )
        try:
            backfill_single_season_with_audit(league_id, row)
        except Exception as e:
            logger.error(
                "❌ Errore generale nel backfill della stagione league_id=%s, season_year=%s: %s",
                league_id,
                sy,
                e,
            )
        # piccola pausa tra una stagione e l'altra
        time.sleep(0.5)

    logger.info("✅ Backfill COMPLETO per la lega %s (tutte le stagioni processate o già complete).", league_id)

    logger.info("🔍 Avvio controllo missing fixtures per league_id=%s", league_id)
    try:
        run_past_seasons_backfill(league_id)
    except Exception as e:
        logger.error(
            "⚠️ Errore durante il controllo missing fixtures per league_id=%s: %s",
            league_id,
            e,
        )
    else:
        logger.info("✅ Controllo missing fixtures completato per league_id=%s", league_id)

    # =========================
    # Refresh dashboard cache (MV) - NUOVO
    # =========================
    refresh_coverage_mv()


# =========================
# CLI
# =========================


def ask_and_run_cli():
    print("==============================================")
    print("  🧠 Orchestratore backfill lega + stagioni")
    print("==============================================")

    while True:
        league_input = input("Inserisci league_id (oppure premi INVIO per uscire): ").strip()
        if not league_input:
            print("👋 Uscita dall'orchestratore.")
            break
        try:
            league_id = int(league_input)
        except ValueError:
            print("❌ Inserisci un intero valido per league_id.")
            continue

        print(f"➡️  Avvio backfill COMPLETO per league_id={league_id}")
        backfill_full_league(league_id)
        print(f"✅ Backfill completato per league_id={league_id}\n")


if __name__ == "__main__":
    ask_and_run_cli()
