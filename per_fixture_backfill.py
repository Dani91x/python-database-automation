import time
from typing import Any, Dict, List, Optional, Tuple

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
    Converte value in int se possibile, altrimenti None.
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


def _parse_float(value: Any) -> Optional[float]:
    """
    Converte value in float se possibile, altrimenti None.
    Gestisce stringhe tipo '7.4' o '54%'.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        s = str(value).strip()
        if s.endswith("%"):
            s = s[:-1]
        if s == "":
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_percentage_to_int(value: Any) -> Optional[int]:
    """
    Converte stringhe tipo '96%' -> 96.
    Se non valida, ritorna None.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        s = str(value).strip()
        if s.endswith("%"):
            s = s[:-1]
        if s == "":
            return None
        return int(round(float(s)))
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
# Coverage & fixtures list
# ========================


def get_coverage_for_season(league_id: int, season_year: int) -> Optional[Dict[str, Any]]:
    """
    Legge il coverage da api_coverage_by_season per (league_id, season_year).
    Ritorna un dict con i flag che ci interessano.
    """
    supabase = get_supabase()
    try:
        resp = (
            supabase.table("api_coverage_by_season")
            .select(
                "fixtures_events, fixtures_lineups, "
                "fixtures_statistics_fixtures, fixtures_statistics_players, "
                "odds"
            )
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .maybe_single()
            .execute()
        )
        data = getattr(resp, "data", None)
        if not data:
            logger.warning(
                "⚠️ Nessuna riga coverage per league_id=%s, season_year=%s",
                league_id,
                season_year,
            )
            return None

        coverage = {
            "events": bool(data.get("fixtures_events")),
            "lineups": bool(data.get("fixtures_lineups")),
            "team_stats": bool(data.get("fixtures_statistics_fixtures")),
            "player_stats": bool(data.get("fixtures_statistics_players")),
            "odds": bool(data.get("odds")),
        }
        logger.info(
            "📌 Coverage per league_id=%s, season_year=%s → %s",
            league_id,
            season_year,
            coverage,
        )
        return coverage
    except Exception as e:
        logger.error(
            "❌ Errore lettura coverage per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            e,
        )
        return None


def get_fixtures_from_matches(league_id: int, season_year: int) -> List[int]:
    """
    Ritorna la lista di fixture_id dalla tabella matches per (league_id, season_year).
    """
    supabase = get_supabase()
    fixtures: List[int] = []
    skipped = 0

    try:
        logger.info(
            "📡 Lettura fixtures da matches per league_id=%s, season_year=%s",
            league_id,
            season_year,
        )
        resp = (
            supabase.table("matches")
            .select("fixture_id")
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .range(0, 99999)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        for row in data:
            fid = _parse_int(row.get("fixture_id"))
            if fid is not None:
                fixtures.append(fid)
            else:
                skipped += 1

        logger.info(
            "📌 Fixtures trovati in matches per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            len(fixtures),
        )
        if skipped:
            logger.warning(
                "⚠️ Fixtures con fixture_id non valido (saltati): %s",
                skipped,
            )
    except Exception as e:
        logger.error(
            "❌ Errore lettura fixtures da matches per league_id=%s, season_year=%s: %s",
            league_id,
            season_year,
            e,
        )

    return fixtures


# ========================
# DB helpers per-fixture
# ========================


def delete_existing_for_fixture(fixture_id: int) -> None:
    """
    Per idempotenza: cancella tutte le righe per questo fixture_id
    dalle tabelle per-fixture.
    """
    supabase = get_supabase()
    tables = [
        "match_events",
        "match_lineups",
        "match_player_stats",
        "match_team_stats",  # nuova tabella per /fixtures/statistics
    ]
    logger.info("🧹 Cancellazione dati per fixture_id=%s dalle tabelle per-fixture", fixture_id)
    for table in tables:
        try:
            resp = (
                supabase.table(table)
                .delete()
                .eq("fixture_id", fixture_id)
                .execute()
            )
            deleted = len(getattr(resp, "data", None) or [])
            logger.info(
                "   🗑️ %s: cancellate %s righe per fixture_id=%s",
                table,
                deleted,
                fixture_id,
            )
        except Exception as e:
            logger.error(
                "   ❌ Errore cancellazione in %s per fixture_id=%s: %s",
                table,
                fixture_id,
                e,
            )


def insert_rows(table: str, rows: List[Dict[str, Any]], batch_size: int = 200) -> Tuple[int, int]:
    """
    Inserisce le righe nella tabella indicata, a chunk.
    Ritorna (righe_inserite, batch_error_count).
    """
    if not rows:
        logger.info("📭 Nessuna riga da inserire in %s.", table)
        return 0, 0

    supabase = get_supabase()
    inserted_total = 0
    batch_errors = 0

    logger.info("📥 Insert in %s: %s righe", table, len(rows))

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        logger.info(
            "   🚚 Insert %s batch %s (righe %s-%s)...",
            table,
            (i // batch_size) + 1,
            i + 1,
            i + len(chunk),
        )
        try:
            resp = supabase.table(table).insert(chunk).execute()
            data = getattr(resp, "data", None) or []
            inserted_total += len(data)
            logger.info(
                "   ✅ Insert %s batch %s completato (righe inserite: %s)",
                table,
                (i // batch_size) + 1,
                len(data),
            )
        except Exception as e:
            batch_errors += 1
            logger.error(
                "   ❌ Errore insert in %s batch %s: %s",
                table,
                (i // batch_size) + 1,
                e,
            )

    return inserted_total, batch_errors


# ========================
# API calls per endpoint
# ========================


def _api_get_fixture_events(client: APIFootballClient, fixture_id: int) -> List[Dict[str, Any]]:
    data = client.call("/fixtures/events", params={"fixture": fixture_id})
    resp_list = (data or {}).get("response") or []
    if not isinstance(resp_list, list):
        return []
    return [x for x in resp_list if isinstance(x, dict)]


def _api_get_fixture_lineups(client: APIFootballClient, fixture_id: int) -> List[Dict[str, Any]]:
    data = client.call("/fixtures/lineups", params={"fixture": fixture_id})
    resp_list = (data or {}).get("response") or []
    if not isinstance(resp_list, list):
        return []
    return [x for x in resp_list if isinstance(x, dict)]


def _api_get_fixture_players(client: APIFootballClient, fixture_id: int) -> List[Dict[str, Any]]:
    data = client.call("/fixtures/players", params={"fixture": fixture_id})
    resp_list = (data or {}).get("response") or []
    if not isinstance(resp_list, list):
        return []
    return [x for x in resp_list if isinstance(x, dict)]


def _api_get_fixture_odds(client: APIFootballClient, fixture_id: int) -> List[Dict[str, Any]]:
    data = client.call("/odds", params={"fixture": fixture_id})
    resp_list = (data or {}).get("response") or []
    if not isinstance(resp_list, list):
        return []
    return [x for x in resp_list if isinstance(x, dict)]


def _api_get_fixture_team_stats(client: APIFootballClient, fixture_id: int) -> List[Dict[str, Any]]:
    """
    Chiama /fixtures/statistics per ottenere le statistiche di squadra.
    """
    data = client.call("/fixtures/statistics", params={"fixture": fixture_id})
    resp_list = (data or {}).get("response") or []
    if not isinstance(resp_list, list):
        return []
    return [x for x in resp_list if isinstance(x, dict)]


# ========================
# Mapping: EVENTS
# ========================


def map_events(
    events_list: List[Dict[str, Any]],
    fixture_id: int,
    league_id: int,
    season_year: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    logger.info(
        "   🎬 Mappo events per fixture_id=%s (conteggio eventi grezzi: %s)",
        fixture_id,
        len(events_list),
    )

    for idx, ev in enumerate(events_list):
        try:
            if not isinstance(ev, dict):
                logger.warning(
                    "   ⏭️ Evento index=%s per fixture_id=%s non è un dict, skippo.",
                    idx,
                    fixture_id,
                )
                continue

            time_block = ev.get("time") if isinstance(ev.get("time"), dict) else {}
            team_block = ev.get("team") if isinstance(ev.get("team"), dict) else {}
            player_block = ev.get("player") if isinstance(ev.get("player"), dict) else {}
            assist_block = ev.get("assist") if isinstance(ev.get("assist"), dict) else {}

            minute = _parse_int(time_block.get("elapsed"))
            extra = _parse_int(time_block.get("extra"))

            row = {
                "fixture_id": fixture_id,
                "league_id": league_id,
                "season_year": season_year,
                "team_id": _parse_int(team_block.get("id")),
                "team_name": team_block.get("name"),
                "player_id": _parse_int(player_block.get("id")),
                "player_name": player_block.get("name"),
                "assist_id": _parse_int(assist_block.get("id")),
                "assist_name": assist_block.get("name"),
                "event_type": ev.get("type"),
                "detail": ev.get("detail"),
                "comments": ev.get("comments"),
                "minute": minute,
                "minute_extra": extra,
                "raw_json": ev,
            }
            rows.append(row)
        except Exception as e:
            logger.error(
                "   ❌ Errore mappando evento index=%s per fixture_id=%s: %s",
                idx,
                fixture_id,
                e,
            )

    logger.info(
        "   📌 Righe events mappate per fixture_id=%s: %s",
        fixture_id,
        len(rows),
    )
    return rows


# ========================
# Mapping: LINEUPS
# ========================


def _extract_lineup_rows_for_team(
    team_block: Dict[str, Any],
    players_list: List[Dict[str, Any]],
    fixture_id: int,
    league_id: int,
    season_year: int,
    is_starter: bool,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    team_id = _parse_int(team_block.get("id"))
    team_name = team_block.get("name")

    for idx, pl in enumerate(players_list):
        try:
            if not isinstance(pl, dict):
                logger.warning(
                    "   ⏭️ Player lineup index=%s non è un dict, skippo (fixture_id=%s).",
                    idx,
                    fixture_id,
                )
                continue

            player_block = pl.get("player") if isinstance(pl.get("player"), dict) else {}
            grid = pl.get("grid")

            row = {
                "fixture_id": fixture_id,
                "league_id": league_id,
                "season_year": season_year,
                "team_id": team_id,
                "team_name": team_name,
                "coach_id": None,  # sarà settato al livello superiore se serve
                "coach_name": None,
                "player_id": _parse_int(player_block.get("id")),
                "player_name": player_block.get("name"),
                "player_number": _parse_int(player_block.get("number")),
                "position": player_block.get("pos"),
                "grid": grid,
                "is_starter": is_starter,
                "raw_json": pl,
            }
            rows.append(row)
        except Exception as e:
            logger.error(
                "   ❌ Errore mappando lineup player index=%s per fixture_id=%s: %s",
                idx,
                fixture_id,
                e,
            )

    return rows


def map_lineups(
    lineups_list: List[Dict[str, Any]],
    fixture_id: int,
    league_id: int,
    season_year: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    logger.info(
        "   🎬 Mappo lineups per fixture_id=%s (teams nel JSON: %s)",
        fixture_id,
        len(lineups_list),
    )

    for team_idx, lineup in enumerate(lineups_list):
        try:
            if not isinstance(lineup, dict):
                logger.warning(
                    "   ⏭️ Lineup index=%s per fixture_id=%s non è un dict, skippo.",
                    team_idx,
                    fixture_id,
                )
                continue

            team_block = lineup.get("team") if isinstance(lineup.get("team"), dict) else {}
            coach_block = lineup.get("coach") if isinstance(lineup.get("coach"), dict) else {}
            start_xi = lineup.get("startXI") if isinstance(lineup.get("startXI"), list) else []
            subs = lineup.get("substitutes") if isinstance(lineup.get("substitutes"), list) else []

            # starter
            starter_rows = _extract_lineup_rows_for_team(
                team_block,
                start_xi,
                fixture_id,
                league_id,
                season_year,
                is_starter=True,
            )
            # subs
            subs_rows = _extract_lineup_rows_for_team(
                team_block,
                subs,
                fixture_id,
                league_id,
                season_year,
                is_starter=False,
            )

            # aggiorniamo coach su tutte le righe di questo team
            coach_id = _parse_int(coach_block.get("id"))
            coach_name = coach_block.get("name")
            for r in starter_rows + subs_rows:
                r["coach_id"] = coach_id
                r["coach_name"] = coach_name

            rows.extend(starter_rows)
            rows.extend(subs_rows)

        except Exception as e:
            logger.error(
                "   ❌ Errore mappando lineup team index=%s per fixture_id=%s: %s",
                team_idx,
                fixture_id,
                e,
            )

    logger.info(
        "   📌 Righe lineups mappate per fixture_id=%s: %s",
        fixture_id,
        len(rows),
    )
    return rows


# ========================
# Mapping: PLAYER STATS
# ========================


def map_player_stats(
    players_list: List[Dict[str, Any]],
    fixture_id: int,
    league_id: int,
    season_year: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    logger.info(
        "   🎬 Mappo player stats per fixture_id=%s (teams nel JSON: %s)",
        fixture_id,
        len(players_list),
    )

    for team_idx, team_entry in enumerate(players_list):
        try:
            if not isinstance(team_entry, dict):
                logger.warning(
                    "   ⏭️ Team stats index=%s per fixture_id=%s non è un dict, skippo.",
                    team_idx,
                    fixture_id,
                )
                continue

            team_block = team_entry.get("team") if isinstance(team_entry.get("team"), dict) else {}
            team_id = _parse_int(team_block.get("id"))
            team_name = team_block.get("name")

            players_arr = team_entry.get("players")
            if not isinstance(players_arr, list):
                logger.warning(
                    "   ⏭️ Nessun array 'players' valido per team index=%s fixture_id=%s, skippo team.",
                    team_idx,
                    fixture_id,
                )
                continue

            for p_idx, pl in enumerate(players_arr):
                try:
                    if not isinstance(pl, dict):
                        logger.warning(
                            "   ⏭️ Player stats index=%s per fixture_id=%s non è un dict, skippo.",
                            p_idx,
                            fixture_id,
                        )
                        continue

                    player_block = (
                        pl.get("player") if isinstance(pl.get("player"), dict) else {}
                    )
                    stats_list = (
                        pl.get("statistics") if isinstance(pl.get("statistics"), list) else []
                    )
                    if not stats_list:
                        logger.info(
                            "   ⏭️ Player stats index=%s fixture_id=%s senza 'statistics', skippo.",
                            p_idx,
                            fixture_id,
                        )
                        continue

                    stats = stats_list[0] if isinstance(stats_list[0], dict) else {}

                    games = stats.get("games") if isinstance(stats.get("games"), dict) else {}
                    shots = stats.get("shots") if isinstance(stats.get("shots"), dict) else {}
                    goals = stats.get("goals") if isinstance(stats.get("goals"), dict) else {}
                    passes = stats.get("passes") if isinstance(stats.get("passes"), dict) else {}
                    tackles = stats.get("tackles") if isinstance(stats.get("tackles"), dict) else {}
                    duels = stats.get("duels") if isinstance(stats.get("duels"), dict) else {}
                    dribbles = stats.get("dribbles") if isinstance(stats.get("dribbles"), dict) else {}
                    fouls = stats.get("fouls") if isinstance(stats.get("fouls"), dict) else {}
                    cards = stats.get("cards") if isinstance(stats.get("cards"), dict) else {}
                    offsides = (
                        stats.get("offsides") if isinstance(stats.get("offsides"), dict) else {}
                    )

                    passes_accuracy_raw = passes.get("accuracy")
                    passes_accuracy_int = _parse_percentage_to_int(passes_accuracy_raw)

                    row = {
                        "fixture_id": fixture_id,
                        "league_id": league_id,
                        "season_year": season_year,
                        "team_id": team_id,
                        "team_name": team_name,
                        "player_id": _parse_int(player_block.get("id")),
                        "player_name": player_block.get("name"),
                        "minutes": _parse_int(games.get("minutes")),
                        "rating": games.get("rating"),
                        "shots_total": _parse_int(shots.get("total")),
                        "shots_on": _parse_int(shots.get("on")),
                        "goals_total": _parse_int(goals.get("total")),
                        "assists_total": _parse_int(goals.get("assists")),
                        "passes_total": _parse_int(passes.get("total")),
                        "passes_key": _parse_int(passes.get("key")),
                        "passes_accurate": passes_accuracy_int,
                        "tackles_total": _parse_int(tackles.get("total")),
                        "interceptions": _parse_int(tackles.get("interceptions")),
                        "duels_total": _parse_int(duels.get("total")),
                        "duels_won": _parse_int(duels.get("won")),
                        "dribbles_attempts": _parse_int(dribbles.get("attempts")),
                        "dribbles_success": _parse_int(dribbles.get("success")),
                        "fouls_drawn": _parse_int(fouls.get("drawn")),
                        "fouls_committed": _parse_int(fouls.get("committed")),
                        "yellow_cards": _parse_int(cards.get("yellow")),
                        "red_cards": _parse_int(cards.get("red")),
                        "offsides": _parse_int(offsides.get("total")),
                        "raw_json": pl,
                    }
                    rows.append(row)
                except Exception as e:
                    logger.error(
                        "   ❌ Errore mappando player stats team_index=%s, player_index=%s, fixture_id=%s: %s",
                        team_idx,
                        p_idx,
                        fixture_id,
                        e,
                    )
        except Exception as e:
            logger.error(
                "   ❌ Errore mappando team stats index=%s per fixture_id=%s: %s",
                team_idx,
                fixture_id,
                e,
            )

    logger.info(
        "   📌 Righe player stats mappate per fixture_id=%s: %s",
        fixture_id,
        len(rows),
    )
    return rows


# ========================
# Mapping: TEAM STATS (/fixtures/statistics)
# ========================


def map_team_stats(
    team_stats_list: List[Dict[str, Any]],
    fixture_id: int,
    league_id: int,
    season_year: int,
) -> List[Dict[str, Any]]:
    """
    Mappa il risultato di /fixtures/statistics in righe per match_team_stats:
    una riga per (fixture, team, stat_type).
    """
    rows: List[Dict[str, Any]] = []

    logger.info(
        "   🎬 Mappo team stats per fixture_id=%s (entries nel JSON: %s)",
        fixture_id,
        len(team_stats_list),
    )

    for idx, entry in enumerate(team_stats_list):
        try:
            if not isinstance(entry, dict):
                logger.warning(
                    "   ⏭️ Team stats entry index=%s per fixture_id=%s non è un dict, skippo.",
                    idx,
                    fixture_id,
                )
                continue

            team_block = entry.get("team") if isinstance(entry.get("team"), dict) else {}
            team_id = _parse_int(team_block.get("id"))
            team_name = team_block.get("name")

            stats_arr = entry.get("statistics")
            if not isinstance(stats_arr, list):
                logger.warning(
                    "   ⏭️ Nessun array 'statistics' valido per entry index=%s fixture_id=%s, skippo team.",
                    idx,
                    fixture_id,
                )
                continue

            for s_idx, stat in enumerate(stats_arr):
                try:
                    if not isinstance(stat, dict):
                        logger.warning(
                            "   ⏭️ Stat index=%s non è un dict, skippo (fixture_id=%s).",
                            s_idx,
                            fixture_id,
                        )
                        continue

                    stat_type = stat.get("type")
                    val = stat.get("value")
                    # value_text: rappresentazione grezza
                    value_text = None
                    if val is not None:
                        value_text = str(val)

                    value_numeric = _parse_float(val)

                    row = {
                        "fixture_id": fixture_id,
                        "league_id": league_id,
                        "season_year": season_year,
                        "team_id": team_id,
                        "team_name": team_name,
                        "stat_type": stat_type,
                        "value_text": value_text,
                        "value_numeric": value_numeric,
                        "raw_json": stat,
                    }
                    rows.append(row)
                except Exception as e:
                    logger.error(
                        "   ❌ Errore mappando singola stat s_idx=%s per fixture_id=%s: %s",
                        s_idx,
                        fixture_id,
                        e,
                    )

        except Exception as e:
            logger.error(
                "   ❌ Errore mappando team stats entry index=%s per fixture_id=%s: %s",
                idx,
                fixture_id,
                e,
            )

    logger.info(
        "   📌 Righe team stats mappate per fixture_id=%s: %s",
        fixture_id,
        len(rows),
    )
    return rows


# ========================
# Mapping: ODDS
# ========================


def map_odds(
    odds_list: List[Dict[str, Any]],
    fixture_id: int,
    league_id: int,
    season_year: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    logger.info(
        "   🎬 Mappo odds per fixture_id=%s (bookmakers nel JSON: %s)",
        fixture_id,
        len(odds_list),
    )

    for idx, entry in enumerate(odds_list):
        try:
            if not isinstance(entry, dict):
                logger.warning(
                    "   ⏭️ Odds entry index=%s per fixture_id=%s non è un dict, skippo.",
                    idx,
                    fixture_id,
                )
                continue

            bookmakers = (
                entry.get("bookmakers") if isinstance(entry.get("bookmakers"), list) else []
            )
            for b_idx, bookmaker in enumerate(bookmakers):
                try:
                    if not isinstance(bookmaker, dict):
                        logger.warning(
                            "   ⏭️ Bookmaker index=%s non è un dict, skippo (fixture_id=%s).",
                            b_idx,
                            fixture_id,
                        )
                        continue

                    bookmaker_id = _parse_int(bookmaker.get("id"))
                    bookmaker_name = bookmaker.get("name")
                    bets = (
                        bookmaker.get("bets")
                        if isinstance(bookmaker.get("bets"), list)
                        else []
                    )
                    for bet_idx, bet in enumerate(bets):
                        try:
                            if not isinstance(bet, dict):
                                logger.warning(
                                    "   ⏭️ Bet index=%s non è un dict, skippo (fixture_id=%s).",
                                    bet_idx,
                                    fixture_id,
                                )
                                continue

                            market_key = bet.get("id")
                            market_name = bet.get("name")
                            values = (
                                bet.get("values")
                                if isinstance(bet.get("values"), list)
                                else []
                            )
                            for v_idx, val in enumerate(values):
                                try:
                                    if not isinstance(val, dict):
                                        logger.warning(
                                            "   ⏭️ Odds value index=%s non è un dict, skippo (fixture_id=%s).",
                                            v_idx,
                                            fixture_id,
                                        )
                                        continue

                                    label = val.get("value")
                                    odd_raw = val.get("odd")
                                    odd_value = _parse_float(odd_raw)

                                    row = {
                                        "fixture_id": fixture_id,
                                        "league_id": league_id,
                                        "season_year": season_year,
                                        "bookmaker_id": bookmaker_id,
                                        "bookmaker_name": bookmaker_name,
                                        "market_key": str(market_key) if market_key is not None else None,
                                        "market_name": market_name,
                                        "label": label,
                                        "odd_value": odd_value,
                                        "snapshot_type": "api_football",
                                        "snapshot_time": None,
                                        "raw_json": val,
                                    }
                                    rows.append(row)
                                except Exception as e:
                                    logger.error(
                                        "   ❌ Errore mappando odds value b_idx=%s, bet_idx=%s, v_idx=%s, fixture_id=%s: %s",
                                        b_idx,
                                        bet_idx,
                                        v_idx,
                                        fixture_id,
                                        e,
                                    )
                        except Exception as e:
                            logger.error(
                                "   ❌ Errore mappando bet index=%s per fixture_id=%s: %s",
                                bet_idx,
                                fixture_id,
                                e,
                            )
                except Exception as e:
                    logger.error(
                        "   ❌ Errore mappando bookmaker index=%s per fixture_id=%s: %s",
                        b_idx,
                        fixture_id,
                        e,
                    )
        except Exception as e:
            logger.error(
                "   ❌ Errore mappando odds entry index=%s per fixture_id=%s: %s",
                idx,
                fixture_id,
                e,
            )

    logger.info(
        "   📌 Righe odds mappate per fixture_id=%s: %s",
        fixture_id,
        len(rows),
    )
    return rows


# ========================
# Process single fixture (con audit interno)
# ========================


def process_single_fixture(
    client: APIFootballClient,
    fixture_id: int,
    league_id: int,
    season_year: int,
    coverage: Dict[str, bool],
) -> Dict[str, Any]:
    """
    Processa TUTTI gli endpoint per un singolo fixture, in base al coverage.
    Ritorna un dict con contatori di righe inserite/errori per endpoint.
    NON solleva eccezioni verso l'alto: logga tutto e continua.
    """
    logger.info("==============================================")
    logger.info(
        "⚙️  Process single fixture_id=%s (league_id=%s, season_year=%s)",
        fixture_id,
        league_id,
        season_year,
    )

    # Per idempotenza, cancelliamo prima tutto
    delete_existing_for_fixture(fixture_id)

    stats = {
        "fixture_id": fixture_id,
        "events_rows": 0,
        "events_errors": 0,
        "lineups_rows": 0,
        "lineups_errors": 0,
        "player_stats_rows": 0,
        "player_stats_errors": 0,
        "team_stats_rows": 0,
        "team_stats_errors": 0,
        "odds_rows": 0,
        "odds_errors": 0,
    }

    # EVENTS
    if coverage.get("events"):
        try:
            events_list = _api_get_fixture_events(client, fixture_id)
            logger.info(
                "   📡 API /fixtures/events fixture_id=%s → %s eventi grezzi",
                fixture_id,
                len(events_list),
            )
            rows = map_events(events_list, fixture_id, league_id, season_year)
            inserted, batch_err = insert_rows("match_events", rows)
            stats["events_rows"] = inserted
            stats["events_errors"] = batch_err
        except Exception as e:
            stats["events_errors"] += 1
            logger.error(
                "❌ Errore generale su /fixtures/events per fixture_id=%s: %s",
                fixture_id,
                e,
            )
    else:
        logger.info("   ⏭️ Coverage.events=false → skip /fixtures/events")

    # LINEUPS
    if coverage.get("lineups"):
        try:
            lineups_list = _api_get_fixture_lineups(client, fixture_id)
            logger.info(
                "   📡 API /fixtures/lineups fixture_id=%s → %s blocchi lineup",
                fixture_id,
                len(lineups_list),
            )
            rows = map_lineups(lineups_list, fixture_id, league_id, season_year)
            inserted, batch_err = insert_rows("match_lineups", rows)
            stats["lineups_rows"] = inserted
            stats["lineups_errors"] = batch_err
        except Exception as e:
            stats["lineups_errors"] += 1
            logger.error(
                "❌ Errore generale su /fixtures/lineups per fixture_id=%s: %s",
                fixture_id,
                e,
            )
    else:
        logger.info("   ⏭️ Coverage.lineups=false → skip /fixtures/lineups")

    # PLAYER STATS
    if coverage.get("player_stats"):
        try:
            players_list = _api_get_fixture_players(client, fixture_id)
            logger.info(
                "   📡 API /fixtures/players fixture_id=%s → %s blocchi teams+players",
                fixture_id,
                len(players_list),
            )
            rows = map_player_stats(players_list, fixture_id, league_id, season_year)
            inserted, batch_err = insert_rows("match_player_stats", rows)
            stats["player_stats_rows"] = inserted
            stats["player_stats_errors"] = batch_err
        except Exception as e:
            stats["player_stats_errors"] += 1
            logger.error(
                "❌ Errore generale su /fixtures/players per fixture_id=%s: %s",
                fixture_id,
                e,
            )
    else:
        logger.info("   ⏭️ Coverage.player_stats=false → skip /fixtures/players")

    # TEAM STATS
    if coverage.get("team_stats"):
        try:
            team_stats_list = _api_get_fixture_team_stats(client, fixture_id)
            logger.info(
                "   📡 API /fixtures/statistics fixture_id=%s → %s entries grezze",
                fixture_id,
                len(team_stats_list),
            )
            rows = map_team_stats(team_stats_list, fixture_id, league_id, season_year)
            inserted, batch_err = insert_rows("match_team_stats", rows)
            stats["team_stats_rows"] = inserted
            stats["team_stats_errors"] = batch_err
        except Exception as e:
            stats["team_stats_errors"] += 1
            logger.error(
                "❌ Errore generale su /fixtures/statistics per fixture_id=%s: %s",
                fixture_id,
                e,
            )
    else:
        logger.info("   ⏭️ Coverage.team_stats=false → skip /fixtures/statistics")

    # ODDS
    if coverage.get("odds"):
        try:
            odds_list = _api_get_fixture_odds(client, fixture_id)
            logger.info(
                "   📡 API /odds fixture_id=%s → %s blocchi odds grezzi",
                fixture_id,
                len(odds_list),
            )
            rows = map_odds(odds_list, fixture_id, league_id, season_year)
            inserted, batch_err = insert_rows("match_odds", rows)
            stats["odds_rows"] = inserted
            stats["odds_errors"] = batch_err
        except Exception as e:
            stats["odds_errors"] += 1
            logger.error(
                "❌ Errore generale su /odds per fixture_id=%s: %s",
                fixture_id,
                e,
            )
    else:
        logger.info("   ⏭️ Coverage.odds=false → skip /odds")

    logger.info(
        "✅ Riepilogo fixture_id=%s → events_rows=%s, lineups_rows=%s, player_stats_rows=%s, team_stats_rows=%s, odds_rows=%s",
        fixture_id,
        stats["events_rows"],
        stats["lineups_rows"],
        stats["player_stats_rows"],
        stats["team_stats_rows"],
        stats["odds_rows"],
    )

    return stats


# ========================
# Orchestratore per tutta la stagione (per-fixture)
# ========================


def backfill_per_fixture_for_league_season(league_id: int, season_year: int) -> Optional[Dict[str, Any]]:
    """
    Legge fixtures da matches per (league_id, season_year),
    legge il coverage, e per ogni fixture:
      - chiama gli endpoint per-fixture in base al coverage
      - inserisce nelle tabelle per-fixture
      - logga un riepilogo finale per la stagione.
    Ritorna un dict con le statistiche totali della stagione (per audit),
    oppure None se coverage o fixtures mancano.
    """
    logger.info("==============================================")
    logger.info(
        "🚀 Inizio per-fixture backfill per league_id=%s, season_year=%s",
        league_id,
        season_year,
    )
    logger.info("==============================================")

    coverage = get_coverage_for_season(league_id, season_year)
    if not coverage:
        logger.warning(
            "⚠️ Coverage mancante per league_id=%s, season_year=%s → per-fixture backfill SKIPPATO.",
            league_id,
            season_year,
        )
        return None

    fixtures = get_fixtures_from_matches(league_id, season_year)
    if not fixtures:
        logger.warning(
            "⚠️ Nessun fixture in matches per league_id=%s, season_year=%s → nulla da processare.",
            league_id,
            season_year,
        )
        return None

    client = APIFootballClient()

    total_stats: Dict[str, Any] = {
        "fixtures_total": len(fixtures),
        "events_rows": 0,
        "events_errors": 0,
        "lineups_rows": 0,
        "lineups_errors": 0,
        "player_stats_rows": 0,
        "player_stats_errors": 0,
        "team_stats_rows": 0,
        "team_stats_errors": 0,
        "odds_rows": 0,
        "odds_errors": 0,
    }

    for idx, fixture_id in enumerate(fixtures):
        logger.info(
            "▶️ [Fixture %s/%s] Elaboro fixture_id=%s",
            idx + 1,
            len(fixtures),
            fixture_id,
        )
        fixture_stats = process_single_fixture(
            client, fixture_id, league_id, season_year, coverage
        )

        # accumula a livello stagione
        for key in [
            "events_rows",
            "events_errors",
            "lineups_rows",
            "lineups_errors",
            "player_stats_rows",
            "player_stats_errors",
            "team_stats_rows",
            "team_stats_errors",
            "odds_rows",
            "odds_errors",
        ]:
            total_stats[key] += fixture_stats.get(key, 0)

        # piccola pausa per non stressare troppo l'API
        time.sleep(0.1)

    # Riepilogo stagione
    logger.info("==============================================")
    logger.info(
        "📊 RIEPILOGO per-fixture stagione league_id=%s, season_year=%s",
        league_id,
        season_year,
    )
    logger.info("   Fixtures totali: %s", total_stats["fixtures_total"])
    logger.info(
        "   Events → righe=%s, batch_error=%s",
        total_stats["events_rows"],
        total_stats["events_errors"],
    )
    logger.info(
        "   Lineups → righe=%s, batch_error=%s",
        total_stats["lineups_rows"],
        total_stats["lineups_errors"],
    )
    logger.info(
        "   Player stats → righe=%s, batch_error=%s",
        total_stats["player_stats_rows"],
        total_stats["player_stats_errors"],
    )
    logger.info(
        "   Team stats → righe=%s, batch_error=%s",
        total_stats["team_stats_rows"],
        total_stats["team_stats_errors"],
    )
    logger.info(
        "   Odds → righe=%s, batch_error=%s",
        total_stats["odds_rows"],
        total_stats["odds_errors"],
    )
    logger.info("==============================================")

    return total_stats


# ========================
# CLI
# ========================


def ask_and_run_cli():
    print("==============================================")
    print("  ⚙️  Per-fixture backfill manuale")
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

    backfill_per_fixture_for_league_season(league_id, season_year)


if __name__ == "__main__":
    ask_and_run_cli()
