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
# API – fetch standings
# ========================


def fetch_standings_from_api(league_id: int, season_year: int) -> Optional[Dict[str, Any]]:
    """
    Chiama /standings per league_id + season_year usando APIFootballClient.
    Ritorna il JSON completo (dict) oppure None se errore/empty.
    """
    client = APIFootballClient()
    logger.info(
        "📡 Chiamata API /standings per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )

    data = client.call(
        "/standings",
        params={"league": league_id, "season": season_year},
    )

    if not data:
        logger.warning(
            "⚠️ Nessuna risposta (data=None) da /standings per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return None

    resp_list = data.get("response") or []
    logger.info("📌 Standings: elementi in 'response' = %s", len(resp_list))

    if not resp_list:
        logger.info(
            "📭 Nessuna standings disponibile per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return None

    return data


# ========================
# Mapping JSON → righe tabella
# ========================


def map_standings_response_to_rows(
    data: Dict[str, Any],
    league_id: int,
    season_year: int,
) -> List[Dict[str, Any]]:
    """
    Mappa il JSON di /standings nella struttura della tabella public.standings.

    Struttura tipica (semplificata) API-FOOTBALL:
    {
      "response": [
        {
          "league": {
            "id": ...,
            "season": ...,
            "standings": [
              [  <-- gruppo A
                {
                  "rank": 1,
                  "team": { "id": ..., "name": ... },
                  "points": ...,
                  "goalsDiff": ...,
                  "group": "Serie A",
                  "form": "...",
                  "description": "...",
                  "all": {
                    "played": ...,
                    "win": ...,
                    "draw": ...,
                    "lose": ...,
                    "goals": { "for": ..., "against": ... }
                  },
                  ...
                },
                ...
              ],
              [  <-- gruppo B (se esiste)
                ...
              ]
            ]
          }
        }
      ]
    }
    """
    rows: List[Dict[str, Any]] = []

    response_list = data.get("response") or []
    logger.info("📌 Numero blocchi 'response' in /standings: %s", len(response_list))

    for resp_entry in response_list:
        league_block = resp_entry.get("league") or {}
        standings_groups = league_block.get("standings") or []

        # standings_groups è una lista di liste:
        # ogni sotto-lista è un "gruppo" (es. girone, conference, ecc.)
        logger.info(
            "   📌 Numero gruppi standings in questo blocco league: %s",
            len(standings_groups),
        )

        for group_index, group_list in enumerate(standings_groups):
            # group_list è una lista di righe di standings
            if not group_list:
                continue

            logger.info(
                "      ▶️ Gruppo index=%s, righe nel gruppo=%s",
                group_index,
                len(group_list),
            )

            for st_row in group_list:
                if not isinstance(st_row, dict):
                    continue

                team_block = st_row.get("team") or {}
                team_id = _parse_int(team_block.get("id"))
                team_name = team_block.get("name")

                all_stats = (st_row.get("all") or {})  # stats generali
                goals_all = (all_stats.get("goals") or {}) if isinstance(all_stats, dict) else {}

                standing_group = st_row.get("group")
                # fallback: se manca, usiamo il nome "Group {index}"
                if not standing_group:
                    standing_group = f"Group {group_index + 1}"

                row = {
                    "league_id": league_id,
                    "season_year": season_year,
                    "standing_group": standing_group,
                    "rank": _parse_int(st_row.get("rank")),
                    "team_id": team_id,
                    "team_name": team_name,
                    "played": _parse_int(all_stats.get("played")) if isinstance(all_stats, dict) else None,
                    "win": _parse_int(all_stats.get("win")) if isinstance(all_stats, dict) else None,
                    "draw": _parse_int(all_stats.get("draw")) if isinstance(all_stats, dict) else None,
                    "lose": _parse_int(all_stats.get("lose")) if isinstance(all_stats, dict) else None,
                    "goals_for": _parse_int(goals_all.get("for")) if isinstance(goals_all, dict) else None,
                    "goals_against": _parse_int(goals_all.get("against")) if isinstance(goals_all, dict) else None,
                    "goals_diff": _parse_int(st_row.get("goalsDiff")),
                    "points": _parse_int(st_row.get("points")),
                    "form": st_row.get("form"),
                    "description": st_row.get("description"),
                    "raw_json": st_row,
                }

                rows.append(row)

    logger.info("📌 Totale righe standings mappate: %s", len(rows))
    return rows


# ========================
# DB helpers
# ========================


def delete_existing_standings(league_id: int, season_year: int) -> None:
    """
    Per idempotenza: cancella le righe esistenti in public.standings
    per (league_id, season_year).
    """
    supabase = get_supabase()
    logger.info(
        "🧹 Cancellazione standings esistenti per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )
    try:
        resp = (
            supabase.table("standings")
            .delete()
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .execute()
        )
        deleted = len(getattr(resp, "data", None) or [])
        logger.info(
            "   🗑️ Righe standings cancellate per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            deleted,
        )
    except Exception as e:
        logger.error(
            "❌ Errore nella cancellazione standings per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            e,
        )


def insert_rows_standings(rows: List[Dict[str, Any]], batch_size: int = 200) -> None:
    """
    Inserisce le righe nella tabella standings, a chunk, con log verboso.
    """
    if not rows:
        logger.info("📭 Nessuna riga standings da inserire.")
        return

    supabase = get_supabase()
    logger.info("📥 Insert standings: %s righe", len(rows))
    start_time = time.time()

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        logger.info(
            "   🚚 Insert standings batch %s (righe %s-%s)...",
            (i // batch_size) + 1,
            i + 1,
            i + len(chunk),
        )
        try:
            resp = supabase.table("standings").insert(chunk).execute()
            data = getattr(resp, "data", None)
            logger.info(
                "   ✅ Insert standings batch %s completato (righe inserite: %s)",
                (i // batch_size) + 1,
                len(data or []),
            )
        except Exception as e:
            logger.error(
                "   ❌ Errore insert standings batch %s: %s",
                (i // batch_size) + 1,
                e,
            )

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info("⏱️ Insert standings completato in %sms", elapsed_ms)


# ========================
# Orchestratore standings
# ========================


def backfill_standings_for_league_season(league_id: int, season_year: int) -> None:
    """
    Orchestratore:
      - chiama /standings
      - mappa il JSON in righe
      - cancella le standings esistenti per (league_id, season_year)
      - inserisce le nuove righe
    """
    logger.info(
        "🚀 Inizio backfill standings per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )

    data = fetch_standings_from_api(league_id, season_year)
    if not data:
        logger.warning(
            "⚠️ Nessun dato standings da processare per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return

    rows = map_standings_response_to_rows(data, league_id, season_year)
    if not rows:
        logger.warning(
            "⚠️ Nessuna riga standings mappata per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        return

    delete_existing_standings(league_id, season_year)
    insert_rows_standings(rows)

    logger.info(
        "🏁 Backfill standings completato per league_id=%s, season_year=%s (righe inserite: %s)",
        league_id,
        season_year,
        len(rows),
    )


# ========================
# CLI
# ========================


def ask_and_run_cli():
    print("==============================================")
    print("  📊 Backfill standings da API-FOOTBALL")
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

    backfill_standings_for_league_season(league_id, season_year)


if __name__ == "__main__":
    ask_and_run_cli()
