from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from db_client import get_supabase_client


def _chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _fetch_all(
    table: str,
    columns: str,
    filters: Optional[List[Tuple[str, str, Any]]] = None,
    page_size: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Fetch all rows from a table with optional filters.
    Filters are tuples (op, column, value), e.g. ("eq", "league_id", 39).
    """
    sb = get_supabase_client()
    offset = 0
    results: List[Dict[str, Any]] = []

    while True:
        query = sb.table(table).select(columns)
        if filters:
            for op, col, val in filters:
                if op == "eq":
                    query = query.eq(col, val)
                elif op == "gte":
                    query = query.gte(col, val)
                elif op == "lt":
                    query = query.lt(col, val)
                elif op == "in":
                    query = query.in_(col, val)
                else:
                    raise ValueError(f"Unsupported filter op: {op}")

        resp = query.range(offset, offset + page_size - 1).execute()
        data = getattr(resp, "data", None) or []
        results.extend(data)
        if len(data) < page_size:
            break
        offset += page_size

    return results


def fetch_fixtures_for_date(target_date: date) -> List[Dict[str, Any]]:
    start = datetime.combine(target_date, datetime.min.time()).isoformat()
    end = (datetime.combine(target_date, datetime.min.time()) + timedelta(days=1)).isoformat()

    columns = (
        "fixture_id,league_id,season_year,fixture_date,home_team_id,home_team_name,"
        "away_team_id,away_team_name,goals_home,goals_away,halftime_home,halftime_away,"
        "fulltime_home,fulltime_away,extratime_home,extratime_away,penalty_home,penalty_away,"
        "status_short,status_long,status_elapsed,venue_name,venue_city"
    )
    # Use fixture_predictions as daily source of fixtures
    fp_columns = (
        "fixture_id,league_id,league_name,season_year,fixture_date,home_team_id,home_team_name,"
        "away_team_id,away_team_name,status,goals_home_line,goals_away_line,under_over_line,"
        "percent_home,percent_draw,percent_away,win_or_draw,advice,winner_team_id,winner_name,"
        "raw_json_odds,raw_json"
    )
    filters = [("gte", "fixture_date", start), ("lt", "fixture_date", end)]
    return _fetch_all("fixture_predictions", fp_columns, filters)


def fetch_matches_for_league_seasons(
    league_seasons: List[Tuple[int, int]]
) -> List[Dict[str, Any]]:
    columns = (
        "fixture_id,league_id,season_year,fixture_date,home_team_id,home_team_name,"
        "away_team_id,away_team_name,goals_home,goals_away"
    )
    results: List[Dict[str, Any]] = []
    for league_id, season_year in league_seasons:
        filters = [("eq", "league_id", league_id), ("eq", "season_year", season_year)]
        results.extend(_fetch_all("matches", columns, filters))
    return results


def fetch_matches_full_for_league_seasons(
    league_seasons: List[Tuple[int, int]]
) -> List[Dict[str, Any]]:
    columns = (
        "fixture_id,league_id,season_year,fixture_date,home_team_id,home_team_name,"
        "away_team_id,away_team_name,goals_home,goals_away,halftime_home,halftime_away,"
        "fulltime_home,fulltime_away,extratime_home,extratime_away,penalty_home,penalty_away"
    )
    results: List[Dict[str, Any]] = []
    for league_id, season_year in league_seasons:
        filters = [("eq", "league_id", league_id), ("eq", "season_year", season_year)]
        results.extend(_fetch_all("matches", columns, filters))
    return results


def fetch_related_by_fixture_ids(
    table: str,
    fixture_ids: List[int],
    columns: str,
    extra_filters: Optional[List[Tuple[str, str, Any]]] = None,
    page_size: int = 1000,
    chunk_size: int = 1000,
) -> List[Dict[str, Any]]:
    if not fixture_ids:
        return []
    results: List[Dict[str, Any]] = []
    if table == "match_odds":
        # reduce payload to avoid timeouts on large odds tables
        page_size = min(page_size, 50)
        chunk_size = min(chunk_size, 50)
    for chunk in _chunked(fixture_ids, chunk_size):
        filters = [("in", "fixture_id", chunk)]
        if extra_filters:
            filters.extend(extra_filters)
        results.extend(_fetch_all(table, columns, filters, page_size=page_size))
    return results


def fetch_standings_by_league_seasons(
    league_seasons: List[Tuple[int, int]]
) -> List[Dict[str, Any]]:
    columns = (
        "league_id,season_year,team_id,team_name,rank,played,win,draw,lose,"
        "goals_for,goals_against,goals_diff,points,form,standing_group,description"
    )
    results: List[Dict[str, Any]] = []
    for league_id, season_year in league_seasons:
        filters = [("eq", "league_id", league_id), ("eq", "season_year", season_year)]
        results.extend(_fetch_all("standings", columns, filters))
    return results


def fetch_seasons_for_league(league_id: int) -> List[int]:
    sb = get_supabase_client()
    resp = (
        sb.table("matches")
        .select("season_year")
        .eq("league_id", league_id)
        .order("season_year", desc=False)
        .execute()
    )
    data = getattr(resp, "data", None) or []
    seasons = sorted({int(r.get("season_year")) for r in data if r.get("season_year") is not None})
    return seasons


def fetch_fixture_prediction_by_id(fixture_id: int) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    resp = (
        sb.table("fixture_predictions")
        .select(
            "fixture_id,league_id,league_name,season_year,fixture_date,home_team_id,home_team_name,"
            "away_team_id,away_team_name,status,goals_home_line,goals_away_line,under_over_line,"
            "percent_home,percent_draw,percent_away,win_or_draw,advice,winner_team_id,winner_name,"
            "raw_json_odds"
        )
        .eq("fixture_id", fixture_id)
        .execute()
    )
    return getattr(resp, "data", None) or []
