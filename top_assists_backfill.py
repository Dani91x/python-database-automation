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
# API – fetch top assists
# ========================


def fetch_top_assists_from_api(
    league_id: int,
    season_year: int,
) -> Optional[Dict[str, Any]]:
    """
    Chiama /players/topassists per league_id + season_year.
    Ritorna il JSON completo (dict) oppure None se errore/empty.
    """
    client = APIFootballClient()
    logger.info(
        "📡 Chiamata API /players/topassists per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )

    data = client.call(
        "/players/topassists",
        params={"league": league_id, "season": season_year},
    )

    if not data:
        logger.warning(
            "⚠️ Nessuna risposta (data=None) da /players/topassists per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return None

    resp_list = data.get("response") or []
    logger.info("📌 Top assists: elementi in 'response' = %s", len(resp_list))

    if not resp_list:
        logger.info(
            "📭 Nessun top assist disponibile per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return None

    return data


# ========================
# Mapping JSON → righe tabella
# ========================


def map_top_assists_response_to_rows(
    data: Dict[str, Any],
    league_id: int,
    season_year: int,
) -> List[Dict[str, Any]]:
    """
    Mappa il JSON di /players/topassists nella struttura della tabella public.top_assists.

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
          "statistics": [
            {
              "team": { "id": ..., "name": ... },
              "games": {
                "appearences": ...,
                "lineups": ...,
                "minutes": ...
              },
              "goals": {
                "total": ...,
                "conceded": ...,
                "assists": ...,
                "saves": ...
              },
              "penalty": {
                "won": ...,
                "scored": ...,
                "missed": ...,
                "saved": ...,
                "committed": ...,
                "conceded": ...
              },
              ...
            }
          ]
        },
        ...
      ]
    }
    """
    rows: List[Dict[str, Any]] = []

    resp_list = data.get("response") or []
    logger.info("📌 Numero top_assists in 'response': %s", len(resp_list))

    for entry_index, entry in enumerate(resp_list):
        if not isinstance(entry, dict):
            continue

        player_block = entry.get("player") or {}
        stats_list = entry.get("statistics") or []

        if not stats_list:
            logger.info(
                "   ⏭️ Entry index=%s senza statistics, skippo.",
                entry_index,
            )
            continue

        stats = stats_list[0] or {}

        team_block = stats.get("team") or {}
        games_block = stats.get("games") or {}
        goals_block = stats.get("goals") or {}
        penalty_block = stats.get("penalty") or stats.get("penalties") or {}

        row = {
            "league_id": league_id,
            "season_year": season_year,
            "player_id": _parse_int(player_block.get("id")),
            "player_name": player_block.get("name"),
            "player_age": _parse_int(player_block.get("age")),
            "player_nationality": player_block.get("nationality"),
            "team_id": _parse_int(team_block.get("id")),
            "team_name": team_block.get("name"),
            "games_appearances": _parse_int(
                games_block.get("appearences") or games_block.get("appearances")
            ),
            "games_lineups": _parse_int(games_block.get("lineups")),
            "games_minutes": _parse_int(games_block.get("minutes")),
            "goals_total": _parse_int(goals_block.get("total")),
            "goals_conceded": _parse_int(goals_block.get("conceded")),
            "goals_assists": _parse_int(goals_block.get("assists")),
            "goals_saves": _parse_int(goals_block.get("saves")),
            "penalties_won": _parse_int(penalty_block.get("won")),
            "penalties_scored": _parse_int(penalty_block.get("scored")),
            "penalties_missed": _parse_int(penalty_block.get("missed")),
            "penalties_saved": _parse_int(penalty_block.get("saved")),
            "penalties_committed": _parse_int(penalty_block.get("committed")),
            "penalties_conceded": _parse_int(penalty_block.get("conceded")),
            "raw_json": entry,
        }

        rows.append(row)

    logger.info("📌 Totale righe top_assists mappate: %s", len(rows))
    return rows


# ========================
# DB helpers
# ========================


def delete_existing_top_assists(league_id: int, season_year: int) -> None:
    """
    Per idempotenza: cancella le righe esistenti in public.top_assists
    per (league_id, season_year).
    """
    supabase = get_supabase()
    logger.info(
        "🧹 Cancellazione top_assists esistenti per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )
    try:
        resp = (
            supabase.table("top_assists")
            .delete()
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .execute()
        )
        deleted = len(getattr(resp, "data", None) or [])
        logger.info(
            "   🗑️ Righe top_assists cancellate per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            deleted,
        )
    except Exception as e:
        logger.error(
            "❌ Errore nella cancellazione top_assists per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            e,
        )


def insert_rows_top_assists(rows: List[Dict[str, Any]], batch_size: int = 200) -> None:
    """
    Inserisce le righe nella tabella top_assists, a chunk, con log verboso.
    """
    if not rows:
        logger.info("📭 Nessuna riga top_assists da inserire.")
        return

    supabase = get_supabase()
    logger.info("📥 Insert top_assists: %s righe", len(rows))
    start_time = time.time()

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        logger.info(
            "   🚚 Insert top_assists batch %s (righe %s-%s)...",
            (i // batch_size) + 1,
            i + 1,
            i + len(chunk),
        )
        try:
            resp = supabase.table("top_assists").insert(chunk).execute()
            data = getattr(resp, "data", None)
            logger.info(
                "   ✅ Insert top_assists batch %s completato (righe inserite: %s)",
                (i // batch_size) + 1,
                len(data or []),
            )
        except Exception as e:
            logger.error(
                "   ❌ Errore insert top_assists batch %s: %s",
                (i // batch_size) + 1,
                e,
            )

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info("⏱️ Insert top_assists completato in %sms", elapsed_ms)


# ========================
# Orchestratore top_assists
# ========================


def backfill_top_assists_for_league_season(
    league_id: int,
    season_year: int,
) -> None:
    """
    Orchestratore:
      - chiama /players/topassists
      - mappa il JSON in righe
      - cancella i top_assists esistenti per (league_id, season_year)
      - inserisce le nuove righe
    """
    logger.info(
        "🚀 Inizio backfill top_assists per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )

    data = fetch_top_assists_from_api(league_id, season_year)
    if not data:
        logger.warning(
            "⚠️ Nessun dato top_assists da processare per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return

    rows = map_top_assists_response_to_rows(data, league_id, season_year)
    if not rows:
        logger.warning(
            "⚠️ Nessuna riga top_assists mappata per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return

    delete_existing_top_assists(league_id, season_year)
    insert_rows_top_assists(rows)

    logger.info(
        "🏁 Backfill top_assists completato per league_id=%s, season_year=%s (righe inserite: %s)",
        league_id,
        season_year,
        len(rows),
    )


# ========================
# CLI
# ========================


def ask_and_run_cli():
    print("==============================================")
    print("  🅰️ Backfill top_assists da API-FOOTBALL")
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

    backfill_top_assists_for_league_season(league_id, season_year)


if __name__ == "__main__":
    ask_and_run_cli()
