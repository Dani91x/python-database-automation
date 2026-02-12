import logging
from typing import Set, Dict, Any, List

from db_client import get_supabase_client
from api_client import APIFootballClient
from fixtures_backfill import map_fixture_to_row, upsert_matches

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ===============================
# 1) Trova fixture_id nelle tabelle per-fixture
# ===============================

PER_FIXTURE_TABLES = [
    "match_events",
    "match_lineups",
    "match_player_stats",
    "match_team_stats",
    "match_odds",
]


def get_fixture_ids_from_table(table_name: str) -> Set[int]:
    sb = get_supabase_client()
    logger.info(f"🔍 Leggo fixture_id da {table_name} ...")

    try:
        resp = (
            sb.table(table_name)
            .select("fixture_id")
            .not_.is_("fixture_id", None)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        return {int(row["fixture_id"]) for row in data if "fixture_id" in row}
    except Exception as e:
        logger.error(f"❌ Errore leggendo {table_name}: {e}")
        return set()


def get_all_fixture_ids_from_per_fixture_tables() -> Set[int]:
    all_ids = set()
    for table in PER_FIXTURE_TABLES:
        all_ids |= get_fixture_ids_from_table(table)
    logger.info(f"📌 Totale fixture_id trovati nelle tabelle per-fixture: {len(all_ids)}")
    return all_ids


# ===============================
# 2) Leggi fixture già presenti in `matches`
# ===============================

def get_existing_matches_ids() -> Set[int]:
    sb = get_supabase_client()
    logger.info("🔍 Leggo fixture_id già presenti in matches ...")

    try:
        resp = sb.table("matches").select("fixture_id").execute()
        data = getattr(resp, "data", None) or []
        return {int(row["fixture_id"]) for row in data if "fixture_id" in row}
    except Exception as e:
        logger.error(f"❌ Errore leggendo matches: {e}")
        return set()


# ===============================
# 3) Fetch + upsert da API
# ===============================

def fetch_fixture_from_api(api: APIFootballClient, fixture_id: int) -> Dict[str, Any] | None:
    logger.info(f"📡 Chiamata /fixtures?id={fixture_id}")

    try:
        data = api.call("/fixtures", params={"id": fixture_id})
    except Exception as e:
        logger.error(f"❌ Errore chiamando API per fixture_id={fixture_id}: {e}")
        return None

    if not data:
        logger.error(f"❌ Nessun dato ricevuto dalla API per fixture_id={fixture_id}")
        return None

    resp = data.get("response") or []
    if not resp:
        logger.error(f"❌ API ha restituito response vuoto per fixture_id={fixture_id}")
        return None

    return resp[0]


def repair_missing_match(api: APIFootballClient, fixture_id: int) -> bool:
    entry = fetch_fixture_from_api(api, fixture_id)
    if entry is None:
        return False

    row = map_fixture_to_row(entry)
    if row is None:
        logger.error(f"❌ map_fixture_to_row ha restituito None per fixture_id={fixture_id}")
        return False

    try:
        upsert_matches([row])
        logger.info(f"✅ Match inserito correttamente per fixture_id={fixture_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Errore in upsert_matches per fixture_id={fixture_id}: {e}")
        return False


# ===============================
# 4) Script principale
# ===============================

def repair_missing_matches():
    logger.info("==============================================")
    logger.info("🚑 AVVIO RIPARAZIONE MATCHES MANCANTI")
    logger.info("==============================================")

    api = APIFootballClient()

    per_fixture_ids = get_all_fixture_ids_from_per_fixture_tables()
    matches_ids = get_existing_matches_ids()

    missing_ids = sorted(per_fixture_ids - matches_ids)

    logger.info(f"🧮 Fixture totali nelle per-fixture: {len(per_fixture_ids)}")
    logger.info(f"🧮 Fixture già presenti in matches: {len(matches_ids)}")
    logger.info(f"⚠️ Fixture SENZA match: {len(missing_ids)}")

    repaired = 0
    failed = 0

    for fixture_id in missing_ids:
        logger.info(f"▶️ Riparo fixture_id={fixture_id} ...")
        if repair_missing_match(api, fixture_id):
            repaired += 1
        else:
            failed += 1

    logger.info("==============================================")
    logger.info("🏁 RIPARAZIONE COMPLETATA")
    logger.info(f"   ➕ Inseriti correttamente: {repaired}")
    logger.info(f"   ❌ Falliti: {failed}")
    logger.info("==============================================")

    # Query di verifica finale
    logger.info("🔎 Usa questa query per verificare la coerenza:")
    logger.info(
        """
WITH pf AS (
    SELECT DISTINCT fixture_id FROM match_events
    UNION SELECT DISTINCT fixture_id FROM match_lineups
    UNION SELECT DISTINCT fixture_id FROM match_player_stats
    UNION SELECT DISTINCT fixture_id FROM match_team_stats
    UNION SELECT DISTINCT fixture_id FROM match_odds
), m AS (
    SELECT fixture_id FROM matches
)
SELECT
    COUNT(*) FILTER (WHERE pf.fixture_id NOT IN (SELECT fixture_id FROM m)) 
        AS fixture_senza_match,
    COUNT(*) FILTER (WHERE pf.fixture_id IN (SELECT fixture_id FROM m)) 
        AS fixture_con_match
FROM pf;
"""
    )


if __name__ == "__main__":
    repair_missing_matches()
