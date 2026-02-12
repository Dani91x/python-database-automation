import argparse
import logging
from typing import List, Dict, Any

from db_client import get_supabase_client
from api_client import APIFootballClient
from per_fixture_backfill import process_single_fixture, get_coverage_for_season

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_current_season_year_for_league(supabase, league_id: int) -> int:
    """
    Ottiene la stagione corrente cercando l'ultima partita già giocata.
    """
    logger.info("📡 Lettura ultima partita già giocata...")

    res = (
        supabase.table("matches")
        .select("season_year, fixture_date")
        .eq("league_id", league_id)
        .lte("fixture_date", "now()")
        .order("fixture_date", desc=True)
        .limit(1)
        .execute()
    )

    if not res.data:
        raise ValueError("Nessuna partita trovata per questo league_id.")

    season_year = res.data[0]["season_year"]

    logger.info(f"🏷️ Stagione corrente rilevata: {season_year}")
    return season_year


def fetch_missing_fixtures(league_id: int) -> List[Dict[str, Any]]:
    """
    Chiama la function RPC che usa la materialized view.
    Nessun rischio di timeout.
    """
    logger.info("📡 Fetch missing fixtures via RPC...")

    supabase = get_supabase_client()

    res = supabase.rpc(
        "fetch_missing_fixture_coverage",
        {"p_league_id": league_id}
    ).execute()

    return res.data or []


def run_past_seasons_backfill(league_id: int):
    supabase = get_supabase_client()
    api = APIFootballClient()

    logger.info("====================================================")
    logger.info(f"🚀 Avvio backfill stagioni passate (league_id={league_id})")
    logger.info("====================================================")

    # 1️⃣ Determina stagione corrente
    current_season = get_current_season_year_for_league(supabase, league_id)

    # 2️⃣ Carica i missing fixture dalla view
    missing = fetch_missing_fixtures(league_id)

    # 3️⃣ Filtra le stagioni già iniziate (inclusa quella corrente)
    missing_targets: List[Dict[str, Any]] = []
    skipped_future = 0
    for row in missing:
        season_year = row.get("season_year")
        if not isinstance(season_year, int):
            logger.warning("⚠️ Riga senza season_year valido: %s", row)
            continue
        if season_year > current_season:
            skipped_future += 1
            continue
        missing_targets.append(row)

    logger.info(
        "📌 Trovati %s fixture mancanti da recuperare (fino alla stagione corrente).",
        len(missing_targets),
    )
    if skipped_future:
        logger.info(
            "ℹ️ Skippati %s fixture appartenenti a stagioni future (>%s).",
            skipped_future,
            current_season,
        )

    if not missing_targets:
        logger.info("✅ Nessun fixture mancante da recuperare per league_id=%s.", league_id)
        return

    # 4️⃣ Processa ogni fixture
    for row in missing_targets:
        fixture_id = row["fixture_id"]
        season_year = row["season_year"]

        logger.info(f"⚙️ Processing fixture_id={fixture_id} (season={season_year})")

        # Carica coverage per questa stagione
        coverage = get_coverage_for_season(league_id, season_year)

        if not coverage:
            logger.warning(f"⚠️ Nessuna coverage trovata per season={season_year}, skip.")
            continue

        try:
            # CHIAMATA CORRETTA E FINALE:
            process_single_fixture(
                api,          # client
                fixture_id,   # fixture_id (INT)
                league_id,    # league_id (INT)
                season_year,  # season_year (INT)
                coverage      # coverage (DICT)
            )

        except Exception as e:
            logger.error(f"❌ Errore fixture_id={fixture_id}: {e}")

    logger.info("🎉 Controllo missing fixtures completato per league_id=%s", league_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--league-id", type=int, required=True)
    args = parser.parse_args()
    run_past_seasons_backfill(args.league_id)
