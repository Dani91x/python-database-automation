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


def _risposta_o_none(data: Any) -> Optional[List[Dict[str, Any]]]:
    """25/09/2026 - distingue ERRORE da risposta VUOTA.
    APIFootballClient.call ritorna {} su QUALUNQUE errore (HTTP, rete, JSON) e
    API-Football risponde HTTP 200 con `errors` non vuoto quando la quota e'
    finita o i parametri non vanno: in entrambi i casi -> None (errore, da
    ritentare). Solo una risposta valida con `response: []` e' VUOTA ([])."""
    if not isinstance(data, dict) or not data:
        return None
    if data.get("errors"):
        return None
    resp_list = data.get("response")
    if not isinstance(resp_list, list):
        return None
    return [x for x in resp_list if isinstance(x, dict)]


def _api_get_fixture_events(client: APIFootballClient, fixture_id: int) -> Optional[List[Dict[str, Any]]]:
    return _risposta_o_none(client.call("/fixtures/events", params={"fixture": fixture_id}))


def _api_get_fixture_lineups(client: APIFootballClient, fixture_id: int) -> Optional[List[Dict[str, Any]]]:
    return _risposta_o_none(client.call("/fixtures/lineups", params={"fixture": fixture_id}))


def _api_get_fixture_players(client: APIFootballClient, fixture_id: int) -> Optional[List[Dict[str, Any]]]:
    return _risposta_o_none(client.call("/fixtures/players", params={"fixture": fixture_id}))


def _api_get_fixture_odds(client: APIFootballClient, fixture_id: int) -> Optional[List[Dict[str, Any]]]:
    return _risposta_o_none(client.call("/odds", params={"fixture": fixture_id}))


def _api_get_fixture_team_stats(client: APIFootballClient, fixture_id: int) -> Optional[List[Dict[str, Any]]]:
    """
    Chiama /fixtures/statistics per ottenere le statistiche di squadra.
    """
    return _risposta_o_none(client.call("/fixtures/statistics", params={"fixture": fixture_id}))


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


# chiave endpoint -> (tabella, funzione API, funzione di mapping, etichetta log)
_PIPELINE = {
    "events": ("match_events", "_api_get_fixture_events", "map_events", "/fixtures/events"),
    "lineups": ("match_lineups", "_api_get_fixture_lineups", "map_lineups", "/fixtures/lineups"),
    "player_stats": ("match_player_stats", "_api_get_fixture_players", "map_player_stats", "/fixtures/players"),
    "team_stats": ("match_team_stats", "_api_get_fixture_team_stats", "map_team_stats", "/fixtures/statistics"),
    "odds": ("match_odds", "_api_get_fixture_odds", "map_odds", "/odds"),
}


def _sostituisci_righe(table: str, fixture_id: int, rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Cancella le righe di QUESTA tabella per la fixture e inserisce le nuove.
    Chiamata SOLO dopo una risposta API valida e non vuota: un errore API non
    cancella mai piu' dati gia' presenti (prima: delete di tutto in testa).
    match_odds ha DUE fonti per la stessa partita: 'api_football' (scritta qui)
    e 'football_data_csv' (quote di chiusura importate da CSV, usate da ML e
    backtest): si cancella SOLO snapshot_type='api_football', mai altre fonti.
    Le altre 4 tabelle non hanno una colonna di fonte: per fixture_id."""
    supabase = get_supabase()
    try:
        q = supabase.table(table).delete().eq("fixture_id", fixture_id)
        if table == "match_odds":
            q = q.eq("snapshot_type", "api_football")
        q.execute()
    except Exception as e:
        logger.error("   Errore cancellazione in %s per fixture_id=%s: %s", table, fixture_id, e)
        return 0, 1
    return insert_rows(table, rows)


def process_single_fixture(
    client: APIFootballClient,
    fixture_id: int,
    league_id: int,
    season_year: int,
    coverage: Dict[str, bool],
    endpoints: Optional[List[str]] = None,
    registra: bool = True,
    registro_obbligatorio: bool = False,
) -> Dict[str, Any]:
    """
    Processa gli endpoint per-fixture di UNA partita.

    25/09/2026:
    - `endpoints` (opzionale): chiavi da chiamare (events/lineups/player_stats/
      team_stats/odds); None = tutte. In ogni caso si chiama SOLO se il flag di
      coverage e' True.
    - niente piu' delete di tutte le tabelle in testa: per ogni endpoint si
      cancella e si reinserisce SOLO dopo una risposta valida e non vuota
      (match_odds compreso: prima non veniva cancellata -> doppioni al rilancio).
    - esito per endpoint in stats["esiti"]: righe / vuoto / errore / saltato.
      Vuoti ed errori vengono registrati in fixture_detail_checks (RPC
      record_fixture_detail_checks) cosi' il recupero sa che la partita e' stata
      interrogata: niente richiamate ogni notte, niente buchi persi in silenzio.
    NON solleva eccezioni verso l'alto (salvo registro_obbligatorio senza
    migrazione): logga tutto e continua.
    """
    logger.info("==============================================")
    logger.info(
        "Process single fixture_id=%s (league_id=%s, season_year=%s, endpoints=%s)",
        fixture_id,
        league_id,
        season_year,
        endpoints or "tutti",
    )

    stats: Dict[str, Any] = {"fixture_id": fixture_id, "esiti": {}}
    for chiave in _PIPELINE:
        stats[f"{chiave}_rows"] = 0
        stats[f"{chiave}_errors"] = 0

    da_registrare: List[Dict[str, Any]] = []
    richiesti = list(_PIPELINE) if endpoints is None else [e for e in _PIPELINE if e in endpoints]

    for chiave, (tabella, nome_api, nome_map, etichetta) in _PIPELINE.items():
        if chiave not in richiesti:
            stats["esiti"][chiave] = "saltato"
            continue
        if not coverage.get(chiave):
            logger.info("   Coverage.%s=false -> skip %s", chiave, etichetta)
            stats["esiti"][chiave] = "saltato"
            continue
        try:
            grezzi = globals()[nome_api](client, fixture_id)
            if grezzi is None:
                stats[f"{chiave}_errors"] += 1
                stats["esiti"][chiave] = "errore"
                logger.error("   API %s fixture_id=%s: errore/risposta non valida", etichetta, fixture_id)
                da_registrare.append({"fixture_id": fixture_id, "tabella": tabella, "league_id": league_id,
                                      "season_year": season_year, "esito": "errore"})
                continue
            logger.info("   API %s fixture_id=%s -> %s elementi grezzi", etichetta, fixture_id, len(grezzi))
            rows = globals()[nome_map](grezzi, fixture_id, league_id, season_year)
            if not rows:
                stats["esiti"][chiave] = "vuoto"
                da_registrare.append({"fixture_id": fixture_id, "tabella": tabella, "league_id": league_id,
                                      "season_year": season_year, "esito": "vuoto"})
                continue
            inserted, batch_err = _sostituisci_righe(tabella, fixture_id, rows)
            stats[f"{chiave}_rows"] = inserted
            stats[f"{chiave}_errors"] = batch_err
            stats["esiti"][chiave] = "errore" if batch_err else "righe"
            # Insert fallito a meta' (o delete fallita): le righe presenti sono
            # PARZIALI e la sonda "esiste almeno una riga" le vedrebbe piene ->
            # buco invisibile per sempre. Si registra 'parziale': la lacuna resta
            # 'errore' e al giro dopo si rifa' delete+insert. (Nessun ritentativo
            # immediato: un insert fallito sotto carico, es. 57014, fallirebbe di
            # nuovo; la ripresa dal giro dopo e' gia' garantita.) Esito pieno ->
            # 'ok' cancella un'eventuale riga di controllo vecchia.
            da_registrare.append({"fixture_id": fixture_id, "tabella": tabella, "league_id": league_id,
                                  "season_year": season_year, "esito": "parziale" if batch_err else "ok"})
        except Exception as e:
            stats[f"{chiave}_errors"] += 1
            stats["esiti"][chiave] = "errore"
            logger.error("Errore generale su %s per fixture_id=%s: %s", etichetta, fixture_id, e)
            da_registrare.append({"fixture_id": fixture_id, "tabella": tabella, "league_id": league_id,
                                  "season_year": season_year, "esito": "parziale"})

    if registra and da_registrare:
        from season_gaps import registra_esiti
        registra_esiti(get_supabase(), da_registrare, obbligatorio=registro_obbligatorio)

    logger.info(
        "Riepilogo fixture_id=%s -> events_rows=%s, lineups_rows=%s, player_stats_rows=%s, team_stats_rows=%s, odds_rows=%s",
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

_CHIAVI_TOTALI = [f"{c}_{t}" for c in _PIPELINE for t in ("rows", "errors")]


def backfill_per_fixture_for_league_season(
    league_id: int,
    season_year: int,
    *,
    lacune: Any = None,
    coverage: Optional[Dict[str, bool]] = None,
    client: Optional[APIFootballClient] = None,
    quota: Any = None,
    deve_fermarsi: Any = None,
    registro_obbligatorio: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    25/09/2026 - RIPARTIBILE: chiama l'API SOLO per le partite FT che mancano
    (season_gaps.lacune_stagione, dati veri del DB) e SOLO per gli endpoint con
    flag di coverage True. Prima: tutte le fixture della stagione, 5 chiamate
    ciascuna, a ogni rilancio (get_fixtures_from_matches, senza controllo).

    Si ferma SEMPRE a fine partita (mai a meta'):
      - quota: prima di ogni partita `quota.copre(costo_partita)`;
      - `deve_fermarsi()` (action concorrente in corso / tempo finito): ogni 25 partite.
    Ritorna le statistiche (con `fermato_per`), oppure None se manca la coverage.
    """
    from season_gaps import lacune_stagione

    if coverage is None:
        coverage = get_coverage_for_season(league_id, season_year)
    if not coverage:
        logger.warning(
            "Coverage mancante per league_id=%s, season_year=%s -> per-fixture backfill SKIPPATO.",
            league_id,
            season_year,
        )
        return None

    if lacune is None:
        lacune = lacune_stagione(get_supabase(), league_id, season_year)
    lavoro = lacune.da_chiamare_per_fixture(coverage)

    total_stats: Dict[str, Any] = {k: 0 for k in _CHIAVI_TOTALI}
    total_stats.update({"fixtures_ft": lacune.ft_totali, "fixtures_da_fare": len(lavoro),
                        "fixtures_fatte": 0, "chiamate": 0, "fermato_per": None,
                        "vuoti": 0, "errori_api": 0})

    if not lavoro:
        logger.info("Nessuna partita FT mancante per league_id=%s season=%s: zero chiamate.", league_id, season_year)
        return total_stats

    client = client or APIFootballClient()
    di_fila_tutto_errore = 0

    for idx, (fixture_id, endpoints) in enumerate(lavoro.items()):
        costo = len(endpoints)
        if quota is not None and not quota.copre(costo):
            total_stats["fermato_per"] = "quota"
            logger.warning("Quota: margine %s < costo partita %s -> mi fermo a fine partita (%s/%s fatte).",
                           quota.margine(), costo, idx, len(lavoro))
            break
        if deve_fermarsi is not None and idx and idx % 25 == 0:
            motivo = deve_fermarsi()
            if motivo:
                total_stats["fermato_per"] = motivo
                logger.warning("Stop a fine partita: %s (%s/%s fatte).", motivo, idx, len(lavoro))
                break
        logger.info("[Fixture %s/%s] fixture_id=%s endpoint=%s", idx + 1, len(lavoro), fixture_id, endpoints)
        prima = int(getattr(client, "richieste_http", 0) or 0)
        fs = process_single_fixture(client, fixture_id, league_id, season_year, coverage,
                                    endpoints=endpoints, registra=True,
                                    registro_obbligatorio=registro_obbligatorio)
        dopo = int(getattr(client, "richieste_http", 0) or 0)
        total_stats["chiamate"] += (dopo - prima) if hasattr(client, "richieste_http") else costo
        total_stats["fixtures_fatte"] += 1
        for k in _CHIAVI_TOTALI:
            total_stats[k] += fs.get(k, 0)
        esiti = [fs["esiti"].get(e) for e in endpoints]
        total_stats["vuoti"] += esiti.count("vuoto")
        total_stats["errori_api"] += esiti.count("errore")
        di_fila_tutto_errore = di_fila_tutto_errore + 1 if esiti and all(x == "errore" for x in esiti) else 0
        if di_fila_tutto_errore >= 10:
            total_stats["fermato_per"] = "errori_api"
            logger.error("10 partite di fila con TUTTI gli endpoint in errore: interrompo la lega-stagione.")
            break
        time.sleep(0.1)

    logger.info("==============================================")
    logger.info("RIEPILOGO per-fixture league_id=%s, season_year=%s: FT=%s, da fare=%s, fatte=%s, "
                "chiamate=%s, vuoti=%s, errori=%s, fermato_per=%s",
                league_id, season_year, total_stats["fixtures_ft"], total_stats["fixtures_da_fare"],
                total_stats["fixtures_fatte"], total_stats["chiamate"], total_stats["vuoti"],
                total_stats["errori_api"], total_stats["fermato_per"])
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
