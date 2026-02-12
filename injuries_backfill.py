import time
from typing import Any, Dict, List, Optional

try:
    from logger import logger  # type: ignore
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from db_client import get_supabase_client
from api_client import APIFootballClient


# ========================
# Helper generici
# ========================


def _parse_int(value: Any) -> Optional[int]:
    """
    Converte value in int se possibile, altrimenti ritorna None.
    Gestisce None, stringhe vuote o spazi.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
            s = str(value).strip()
            if s == "":
                return None
            return int(s)
    except (ValueError, TypeError):
        return None


# ========================
# Supabase client
# ========================

_supabase = None


def get_supabase():
    global _supabase
    if _supabase is None:
        _supabase = get_supabase_client()
    return _supabase


# ========================
# API – fetch injuries
# ========================


def fetch_injuries_from_api(
    league_id: int,
    season_year: int,
) -> Optional[Dict[str, Any]]:
    """
    Chiama /injuries per league_id + season_year.
    Ritorna il JSON completo (dict) oppure None se errore/empty.
    """
    client = APIFootballClient()
    logger.info(
        "📡 Chiamata API /injuries per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )

    data = client.call(
        "/injuries",
        params={"league": league_id, "season": season_year},
    )

    if not data:
        logger.warning(
            "⚠️ Nessuna risposta (data=None) da /injuries per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return None

    resp_list = data.get("response") or []
    logger.info("📌 Injuries: elementi in 'response' = %s", len(resp_list))

    if not resp_list:
        logger.info(
            "📭 Nessuna injury disponibile per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return None

    return data


# ========================
# Mapping JSON → righe tabella
# ========================


def map_injuries_response_to_rows(
    data: Dict[str, Any],
    league_id: int,
    season_year: int,
) -> List[Dict[str, Any]]:
    """
    Mappa il JSON di /injuries nella struttura della tabella public.injuries.

    Struttura tipica (semplificata) API-FOOTBALL:
    {
      "response": [
        {
          "player": {
            "id": ...,
            "name": ...,
            "age": ...,
            "nationality": ...
          },
          "team": {
            "id": ...,
            "name": ...
          },
          "fixture": {
            "id": ...,
            "date": "YYYY-MM-DDTHH:MM:SS+00:00"
          },
          "league": {
            "id": ...,
            "season": ...
          },
          "game": {
            ...
          },
          "injury": {
            "type": "...",
            "reason": "..."
          }
        },
        ...
      ]
    }
    """
    rows: List[Dict[str, Any]] = []

    resp_list = data.get("response") or []
    logger.info("📌 Numero injuries in 'response': %s", len(resp_list))

    for entry_index, entry in enumerate(resp_list):
        if not isinstance(entry, dict):
            continue

        player_block = entry.get("player") or {}
        team_block = entry.get("team") or {}
        fixture_block = entry.get("fixture") or {}
        injury_block = entry.get("injury") or {}

        fixture_id = _parse_int(fixture_block.get("id"))
        fixture_date = fixture_block.get("date")  # stringa ISO, Postgres la converte

        row = {
            "league_id": league_id,
            "season_year": season_year,
            "fixture_id": fixture_id,
            "fixture_date": fixture_date,
            "player_id": _parse_int(player_block.get("id")),
            "player_name": player_block.get("name"),
            "player_age": _parse_int(player_block.get("age")),
            "player_nationality": player_block.get("nationality"),
            "team_id": _parse_int(team_block.get("id")),
            "team_name": team_block.get("name"),
            "type": injury_block.get("type"),
            "reason": injury_block.get("reason"),
            "raw_json": entry,
        }

        rows.append(row)

    logger.info("📌 Totale righe injuries mappate: %s", len(rows))
    return rows


# ========================
# DB helpers
# ========================


def delete_existing_injuries(league_id: int, season_year: int) -> None:
    """
    Per idempotenza: cancella le righe esistenti in public.injuries
    per (league_id, season_year).
    """
    supabase = get_supabase()
    logger.info(
        "🧹 Cancellazione injuries esistenti per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )
    try:
        resp = (
            supabase.table("injuries")
            .delete()
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .execute()
        )
        deleted = len(getattr(resp, "data", None) or [])
        logger.info(
            "   🗑️ Righe injuries cancellate per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            deleted,
        )
    except Exception as e:
        logger.error(
            "❌ Errore nella cancellazione injuries per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            e,
        )


def insert_rows_injuries(rows: List[Dict[str, Any]], batch_size: int = 200) -> None:
    """
    Inserisce le righe nella tabella injuries, a chunk, con log verboso.
    """
    if not rows:
        logger.info("📭 Nessuna riga injuries da inserire.")
        return

    supabase = get_supabase()
    logger.info("📥 Insert injuries: %s righe", len(rows))
    start_time = time.time()

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        logger.info(
            "   🚚 Insert injuries batch %s (righe %s-%s)...",
            (i // batch_size) + 1,
            i + 1,
            i + len(chunk),
        )
        try:
            resp = supabase.table("injuries").insert(chunk).execute()
            data = getattr(resp, "data", None)
            logger.info(
                "   ✅ Insert injuries batch %s completato (righe inserite: %s)",
                (i // batch_size) + 1,
                len(data or []),
            )
        except Exception as e:
            logger.error(
                "   ❌ Errore insert injuries batch %s: %s",
                (i // batch_size) + 1,
                e,
            )

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info("⏱️ Insert injuries completato in %sms", elapsed_ms)


# ========================
# Orchestratore injuries
# ========================


def backfill_injuries_for_league_season(
    league_id: int,
    season_year: int,
) -> None:
    """
    Orchestratore:
      - chiama /injuries
      - mappa il JSON in righe
      - cancella injuries esistenti per (league_id, season_year)
      - inserisce le nuove righe
    """
    logger.info(
        "🚀 Inizio backfill injuries per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )

    data = fetch_injuries_from_api(league_id, season_year)
    if not data:
        logger.warning(
            "⚠️ Nessun dato injuries da processare per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return

    rows = map_injuries_response_to_rows(data, league_id, season_year)
    if not rows:
        logger.warning(
            "⚠️ Nessuna riga injuries mappata per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return

    delete_existing_injuries(league_id, season_year)
    insert_rows_injuries(rows)

    logger.info(
        "🏁 Backfill injuries completato per league_id=%s, season_year=%s (righe inserite: %s)",
        league_id,
        season_year,
        len(rows),
    )


# ========================
# CLI
# ========================


def ask_and_run_cli():
    print("==============================================")
    print("  💊 Backfill injuries da API-FOOTBALL")
    print("==============================================")

    try:
        league_input = input("Inserisci league_id (default 4): ").strip()
        league_id = int(league_input) if league_input else 4

        season_input = input("Inserisci season_year (default 2016): ").strip()
        season_year = int(season_input) if season_input else 2016

        print(f"➡️  Userò league_id={league_id}, season_year={season_year}")
    except ValueError:
        print("❌ Input non valido. Usa solo numeri interi per league_id e season_year.")
        return

    backfill_injuries_for_league_season(league_id, season_year)


if __name__ == "__main__":
    ask_and_run_cli()
