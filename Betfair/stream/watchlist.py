"""Watchlist live: partite GIOCATA → eventi Betfair → live_follow.

Legge le partite marcate 'GIOCATA' in personal_watchlist, le aggancia agli
eventi Betfair del giorno (riusando il matcher money-critical betfair_match.py)
e le registra in live_follow (PENDING). Il runner poi le streamma.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from db_client import get_supabase_client

from Betfair.betfair_match import resolve_matches

from . import db

logger = logging.getLogger(__name__)

SOCCER_EVENT_TYPE_ID = "1"


def get_played_fixtures() -> List[Dict[str, Any]]:
    """Partite marcate GIOCATA in personal_watchlist (per il matching Betfair)."""
    sb = get_supabase_client()
    resp = (
        sb.table("personal_watchlist")
        .select("id, fixture_id, league_id, league_name, home_team, away_team, kickoff")
        .eq("status", "GIOCATA")
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "watchlist_id": r["id"],
                "fixture_id": r["fixture_id"],
                "league_id": r.get("league_id"),
                "league_name": r.get("league_name"),
                "home_team_name": r.get("home_team"),
                "away_team_name": r.get("away_team"),
                "fixture_date": r.get("kickoff"),
            }
        )
    return out


def resolve_and_register(client: Any, days_ahead: int = 1) -> List[Dict[str, Any]]:
    """Aggancia le GIOCATA agli eventi Betfair e le registra in live_follow.

    :param client: Betfair/client.py BetfairClient già loggato (REST JSON-RPC).
    :returns: lista dei follow registrati [{event_id, fixture_id, home, away, open_date}].
    """
    fixtures = get_played_fixtures()
    if not fixtures:
        logger.info("[watchlist] nessuna partita GIOCATA da agganciare.")
        return []

    raw_events = client.list_events([SOCCER_EVENT_TYPE_ID], days_ahead=days_ahead) or []
    events = [
        {
            "id": e["event"]["id"],
            "name": e["event"].get("name", ""),
            "openDate": e["event"].get("openDate"),
        }
        for e in raw_events
        if e.get("event")
    ]
    logger.info("[watchlist] %d GIOCATA vs %d eventi Betfair.", len(fixtures), len(events))

    matched, unmatched = resolve_matches(events, fixtures)

    registered: List[Dict[str, Any]] = []
    fx_by_id = {f["fixture_id"]: f for f in fixtures}
    for m in matched:
        ev = m["event"]
        fx = m["fixture"]
        fixture_id = fx.get("fixture_id")
        src = fx_by_id.get(fixture_id, {})
        db.register_follow(
            event_id=str(ev["id"]),
            home_name=fx.get("home_team_name") or "",
            away_name=fx.get("away_team_name") or "",
            open_date=ev.get("openDate") or fx.get("fixture_date"),
            fixture_id=fixture_id,
            watchlist_id=src.get("watchlist_id"),
            league_name=src.get("league_name"),
            league_id=src.get("league_id"),
            status="PENDING",
        )
        registered.append(
            {
                "event_id": str(ev["id"]),
                "fixture_id": fixture_id,
                "home": fx.get("home_team_name"),
                "away": fx.get("away_team_name"),
                "open_date": ev.get("openDate"),
            }
        )
        logger.info("[watchlist] registrato live_follow event=%s fixture=%s", ev["id"], fixture_id)

    if unmatched:
        logger.info("[watchlist] %d eventi non agganciati (non rilevante).", len(unmatched))
    return registered
