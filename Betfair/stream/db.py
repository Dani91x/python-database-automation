"""Accesso Supabase per il sottosistema live (backend = service_role, bypassa RLS).

Tutte le scritture sono IDEMPOTENTI:
  - live_follow / live_now / live_markets / live_run_log → upsert on_conflict
  - snapshot / timeline → delete-per-evento + insert (re-curazione ripetibile)
Pattern chunked come Ai Engine/ai_engine/db_adapter.py (CHUNK righe per insert).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db_client import get_supabase_client

from .config_stream import UPLOAD_CHUNK

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------------------
# live_follow
# ----------------------------------------------------------------------------
def register_follow(
    event_id: str,
    home_name: str,
    away_name: str,
    open_date: str,
    fixture_id: Optional[int] = None,
    watchlist_id: Optional[int] = None,
    league_name: Optional[str] = None,
    league_id: Optional[int] = None,
    status: str = "PENDING",
) -> None:
    sb = get_supabase_client()
    row = {
        "event_id": event_id,
        "fixture_id": fixture_id,
        "watchlist_id": watchlist_id,
        "league_name": league_name,
        "league_id": league_id,
        "home_name": home_name,
        "away_name": away_name,
        "open_date": open_date,
        "status": status,
        "updated_at": _now_iso(),
    }
    sb.table("live_follow").upsert(row, on_conflict="event_id").execute()


def set_follow_status(event_id: str, status: str, error_detail: Optional[str] = None) -> None:
    sb = get_supabase_client()
    # cap difensivo: error_detail può contenere messaggi d'eccezione → max 200 char
    safe_detail = (error_detail or "")[:200] or None
    sb.table("live_follow").update(
        {"status": status, "error_detail": safe_detail, "updated_at": _now_iso()}
    ).eq("event_id", event_id).execute()


def list_pending_follows() -> List[Dict[str, Any]]:
    """Partite da agganciare (PENDING o STREAMING non chiuse)."""
    sb = get_supabase_client()
    resp = (
        sb.table("live_follow")
        .select("*")
        .in_("status", ["PENDING", "STREAMING"])
        .execute()
    )
    return getattr(resp, "data", None) or []


# ----------------------------------------------------------------------------
# live_markets (catalogo)
# ----------------------------------------------------------------------------
def upsert_markets(event_id: str, markets: List[Dict[str, Any]]) -> None:
    """markets: [{market_id, market_type, market_name, sort_priority, selections}]"""
    if not markets:
        return
    sb = get_supabase_client()
    rows = [
        {
            "event_id": event_id,
            "market_id": m["market_id"],
            "market_type": m.get("market_type"),
            "market_name": m.get("market_name"),
            "sort_priority": m.get("sort_priority"),
            "selections": m.get("selections", []),
            "n_updates": m.get("n_updates", 0),
        }
        for m in markets
    ]
    for i in range(0, len(rows), UPLOAD_CHUNK):
        sb.table("live_markets").upsert(
            rows[i : i + UPLOAD_CHUNK], on_conflict="event_id,market_id"
        ).execute()


# ----------------------------------------------------------------------------
# live_now (glance real-time)
# ----------------------------------------------------------------------------
def update_live_now(
    event_id: str,
    state: Dict[str, Any],
    inplay: bool = False,
    minute: Optional[int] = None,
    score_home: Optional[int] = None,
    score_away: Optional[int] = None,
    status: str = "OPEN",
    score_source: Optional[str] = None,
) -> None:
    sb = get_supabase_client()
    row = {
        "event_id": event_id,
        "inplay": inplay,
        "minute": minute,
        "score_home": score_home,
        "score_away": score_away,
        "status": status,
        "score_source": score_source,
        "state": state,
        "updated_at": _now_iso(),
    }
    sb.table("live_now").upsert(row, on_conflict="event_id").execute()


# ----------------------------------------------------------------------------
# snapshot + timeline (post-match, delete+insert per idempotenza)
# ----------------------------------------------------------------------------
def upload_snapshots(event_id: str, rows: List[Dict[str, Any]]) -> int:
    sb = get_supabase_client()
    sb.table("live_market_snapshots").delete().eq("event_id", event_id).execute()
    n = 0
    for i in range(0, len(rows), UPLOAD_CHUNK):
        chunk = rows[i : i + UPLOAD_CHUNK]
        sb.table("live_market_snapshots").insert(chunk).execute()
        n += len(chunk)
    return n


def upload_timeline(event_id: str, rows: List[Dict[str, Any]]) -> int:
    sb = get_supabase_client()
    sb.table("live_score_timeline").delete().eq("event_id", event_id).execute()
    n = 0
    for i in range(0, len(rows), UPLOAD_CHUNK):
        chunk = rows[i : i + UPLOAD_CHUNK]
        sb.table("live_score_timeline").insert(chunk).execute()
        n += len(chunk)
    return n


# ----------------------------------------------------------------------------
# live_run_log
# ----------------------------------------------------------------------------
def write_run_log(event_id: str, fields: Dict[str, Any]) -> None:
    sb = get_supabase_client()
    row = {"event_id": event_id, "updated_at": _now_iso(), **fields}
    sb.table("live_run_log").upsert(row, on_conflict="event_id").execute()


# ----------------------------------------------------------------------------
# live_signals (motore live, write-on-change)
# ----------------------------------------------------------------------------
def upsert_live_signals(
    event_id: str,
    signals: Dict[str, Any],
    model_meta: Optional[Dict[str, Any]] = None,
) -> None:
    sb = get_supabase_client()
    row = {
        "event_id": event_id,
        "signals": signals,
        "model_meta": model_meta,
        "updated_at": _now_iso(),
    }
    sb.table("live_signals").upsert(row, on_conflict="event_id").execute()


# ----------------------------------------------------------------------------
# live_alerts (avvisi limiti Betfair)
# ----------------------------------------------------------------------------
def insert_alert(
    level: str,
    code: str,
    message: str,
    event_id: Optional[str] = None,
) -> None:
    sb = get_supabase_client()
    sb.table("live_alerts").insert(
        {
            "level": level,
            "code": code,
            "message": message[:500],
            "event_id": event_id,
        }
    ).execute()


# ----------------------------------------------------------------------------
# Backtest Automatico (coda richieste + risultati) — usato dal worker locale
# ----------------------------------------------------------------------------
def claim_backtest_request() -> Optional[Dict[str, Any]]:
    """Prende UNA richiesta PENDING e la porta a RUNNING (claim ottimistico)."""
    sb = get_supabase_client()
    resp = (
        sb.table("live_backtest_requests")
        .select("*")
        .eq("status", "PENDING")
        .order("created_at")
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if not rows:
        return None
    req = rows[0]
    upd = (
        sb.table("live_backtest_requests")
        .update({"status": "RUNNING", "updated_at": _now_iso()})
        .eq("id", req["id"])
        .eq("status", "PENDING")  # guard contro doppia presa
        .execute()
    )
    if not (getattr(upd, "data", None) or []):
        return None  # presa da un altro worker
    return req


def set_backtest_status(
    request_id: str, status: str, error_detail: Optional[str] = None
) -> None:
    sb = get_supabase_client()
    sb.table("live_backtest_requests").update(
        {"status": status, "error_detail": (error_detail or None) and error_detail[:500],
         "updated_at": _now_iso()}
    ).eq("id", request_id).execute()


def write_backtest_results(request_id: str, rows: List[Dict[str, Any]]) -> int:
    sb = get_supabase_client()
    sb.table("live_backtest_results").delete().eq("request_id", request_id).execute()
    n = 0
    for i in range(0, len(rows), UPLOAD_CHUNK):
        chunk = [{"request_id": request_id, **r} for r in rows[i : i + UPLOAD_CHUNK]]
        sb.table("live_backtest_results").insert(chunk).execute()
        n += len(chunk)
    return n
