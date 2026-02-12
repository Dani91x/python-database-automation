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
# API – fetch top cards
# ========================


def _fetch_top_cards_generic(
    endpoint: str,
    league_id: int,
    season_year: int,
) -> Optional[Dict[str, Any]]:
    """
    Helper generico per chiamare /players/topyellowcards o /players/topredcards.
    """
    client = APIFootballClient()
    logger.info(
        "📡 Chiamata API %s per league_id=%s, season_year=%s",
        endpoint,
        league_id,
        season_year,
    )

    data = client.call(
        endpoint,
        params={"league": league_id, "season": season_year},
    )

    if not data:
        logger.warning(
            "⚠️ Nessuna risposta (data=None) da %s per league_id=%s, season_year=%s",
            endpoint,
            league_id,
            season_year,
        )
        return None

    resp_list = data.get("response") or []
    logger.info("📌 %s: elementi in 'response' = %s", endpoint, len(resp_list))

    if not resp_list:
        logger.info(
            "📭 Nessun risultato da %s per league_id=%s, season_year=%s",
            endpoint,
            league_id,
            season_year,
        )
        return None

    return data


def fetch_top_yellow_cards_from_api(
    league_id: int, season_year: int
) -> Optional[Dict[str, Any]]:
    return _fetch_top_cards_generic("/players/topyellowcards", league_id, season_year)


def fetch_top_red_cards_from_api(
    league_id: int, season_year: int
) -> Optional[Dict[str, Any]]:
    return _fetch_top_cards_generic("/players/topredcards", league_id, season_year)


# ========================
# Mapping JSON → righe tabella
# ========================


def map_top_cards_response_to_rows(
    data: Dict[str, Any],
    league_id: int,
    season_year: int,
    card_type: str,
) -> List[Dict[str, Any]]:
    """
    Mappa il JSON di /players/topyellowcards o /players/topredcards
    nella struttura della tabella public.top_cards.

    card_type = 'yellow' o 'red' (passato dal chiamante).

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
              "cards": {
                "yellow": ...,
                "yellowred": ...,
                "red": ...
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
    logger.info(
        "📌 Numero top_cards (%s) in 'response': %s", card_type, len(resp_list)
    )

    for entry_index, entry in enumerate(resp_list):
        if not isinstance(entry, dict):
            continue

        player_block = entry.get("player") or {}
        stats_list = entry.get("statistics") or []

        if not stats_list:
            logger.info(
                "   ⏭️ Entry index=%s (%s) senza statistics, skippo.",
                entry_index,
                card_type,
            )
            continue

        stats = stats_list[0] or {}

        team_block = stats.get("team") or {}
        games_block = stats.get("games") or {}
        cards_block = stats.get("cards") or {}

        row = {
            "league_id": league_id,
            "season_year": season_year,
            "card_type": card_type,
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
            "yellow_cards": _parse_int(cards_block.get("yellow")),
            "red_cards": _parse_int(cards_block.get("red")),
            "raw_json": entry,
        }

        rows.append(row)

    logger.info(
        "📌 Totale righe top_cards mappate per card_type=%s: %s",
        card_type,
        len(rows),
    )
    return rows


# ========================
# DB helpers
# ========================


def delete_existing_top_cards(league_id: int, season_year: int) -> None:
    """
    Per idempotenza: cancella le righe esistenti in public.top_cards
    per (league_id, season_year).
    """
    supabase = get_supabase()
    logger.info(
        "🧹 Cancellazione top_cards esistenti per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )
    try:
        resp = (
            supabase.table("top_cards")
            .delete()
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .execute()
        )
        deleted = len(getattr(resp, "data", None) or [])
        logger.info(
            "   🗑️ Righe top_cards cancellate per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            deleted,
        )
    except Exception as e:
        logger.error(
            "❌ Errore nella cancellazione top_cards per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            e,
        )


def insert_rows_top_cards(rows: List[Dict[str, Any]], batch_size: int = 200) -> None:
    """
    Inserisce le righe nella tabella top_cards, a chunk, con log verboso.
    """
    if not rows:
        logger.info("📭 Nessuna riga top_cards da inserire.")
        return

    supabase = get_supabase()
    logger.info("📥 Insert top_cards: %s righe", len(rows))
    start_time = time.time()

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        logger.info(
            "   🚚 Insert top_cards batch %s (righe %s-%s)...",
            (i // batch_size) + 1,
            i + 1,
            i + len(chunk),
        )
        try:
            resp = supabase.table("top_cards").insert(chunk).execute()
            data = getattr(resp, "data", None)
            logger.info(
                "   ✅ Insert top_cards batch %s completato (righe inserite: %s)",
                (i // batch_size) + 1,
                len(data or []),
            )
        except Exception as e:
            logger.error(
                "   ❌ Errore insert top_cards batch %s: %s",
                (i // batch_size) + 1,
                e,
            )

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info("⏱️ Insert top_cards completato in %sms", elapsed_ms)


# ========================
# Orchestratore top_cards
# ========================


def backfill_top_cards_for_league_season(
    league_id: int,
    season_year: int,
) -> None:
    """
    Orchestratore:
      - chiama /players/topyellowcards e /players/topredcards
      - mappa entrambi i JSON in righe con card_type='yellow'/'red'
      - cancella i top_cards esistenti per (league_id, season_year)
      - inserisce le nuove righe
    """
    logger.info(
        "🚀 Inizio backfill top_cards per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )

    all_rows: List[Dict[str, Any]] = []

    # YELLOW
    data_yellow = fetch_top_yellow_cards_from_api(league_id, season_year)
    if data_yellow:
        rows_yellow = map_top_cards_response_to_rows(
            data_yellow, league_id, season_year, card_type="yellow"
        )
        all_rows.extend(rows_yellow)
    else:
        logger.info("📭 Nessun dato da /players/topyellowcards, nessuna riga yellow.")

    # piccola pausa per non spammare l'API
    time.sleep(0.2)

    # RED
    data_red = fetch_top_red_cards_from_api(league_id, season_year)
    if data_red:
        rows_red = map_top_cards_response_to_rows(
            data_red, league_id, season_year, card_type="red"
        )
        all_rows.extend(rows_red)
    else:
        logger.info("📭 Nessun dato da /players/topredcards, nessuna riga red.")

    if not all_rows:
        logger.warning(
            "⚠️ Nessuna riga top_cards mappata per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return

    delete_existing_top_cards(league_id, season_year)
    insert_rows_top_cards(all_rows)

    logger.info(
        "🏁 Backfill top_cards completato per league_id=%s, season_year=%s (righe inserite: %s)",
        league_id,
        season_year,
        len(all_rows),
    )


# ========================
# CLI
# ========================


def ask_and_run_cli():
    print("==============================================")
    print("  🟨🟥 Backfill top_cards da API-FOOTBALL")
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

    backfill_top_cards_for_league_season(league_id, season_year)


if __name__ == "__main__":
    ask_and_run_cli()
