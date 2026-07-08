"""Accesso Supabase per il sottosistema live TENNIS (service_role, bypassa RLS).

Mirror di ``Betfair/stream/db.py`` (calcio) ma su storage tennis DEDICATO: qui si
scrivono SOLO tabelle ``tennis_*``. Nessuna riga/tabella/RPC del calcio.

CLIENT PER-THREAD: il runner tennis gira più worker flumine (ladder, score/now,
bot-control, ordini) su thread distinti. supabase-py/httpx non è garantito
thread-safe sotto carico → ogni thread usa la PROPRIA istanza di client
(``threading.local``), tutte con la service-role key da ``config``.

Tutte le scritture di stato sono IDEMPOTENTI (upsert on_conflict). Le scritture
"a firma" (ladder/now) sono write-on-change: il chiamante salta la scrittura se la
firma non è cambiata (vedi ``tennis_runner``), per non stressare il DB.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

_ORDER_TABLE = "tennis_live_order_queue"

# ---------------------------------------------------------------------------
# Client Supabase PER-THREAD (service_role)
# ---------------------------------------------------------------------------
_local = threading.local()


def get_tennis_client() -> Client:
    """Client Supabase service_role dedicato al thread corrente (creato on-demand)."""
    sb = getattr(_local, "client", None)
    if sb is None:
        sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        _local.client = sb
    return sb


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# tennis_live_follow — eventi tennis da seguire live
# ---------------------------------------------------------------------------
def register_tennis_follow(
    event_id: str,
    market_id: str,
    player1_name: str,
    player2_name: str,
    open_date: Optional[str] = None,
    competition_name: Optional[str] = None,
    status: str = "PENDING",
) -> None:
    """Registra/aggiorna un evento tennis da seguire (idempotente su event_id)."""
    sb = get_tennis_client()
    row = {
        "event_id": event_id,
        "market_id": market_id,
        "player1_name": player1_name,
        "player2_name": player2_name,
        "open_date": open_date,
        "competition_name": competition_name,
        "status": status,
        "updated_at": _now_iso(),
    }
    sb.table("tennis_live_follow").upsert(row, on_conflict="event_id").execute()


def set_tennis_follow_status(
    event_id: str, status: str, error_detail: Optional[str] = None
) -> None:
    sb = get_tennis_client()
    safe_detail = (error_detail or "")[:200] or None
    sb.table("tennis_live_follow").update(
        {"status": status, "error_detail": safe_detail, "updated_at": _now_iso()}
    ).eq("event_id", event_id).execute()


def list_pending_tennis_follows() -> List[Dict[str, Any]]:
    """Eventi da agganciare (PENDING o STREAMING non chiusi)."""
    sb = get_tennis_client()
    resp = (
        sb.table("tennis_live_follow")
        .select("*")
        .in_("status", ["PENDING", "STREAMING"])
        .execute()
    )
    return getattr(resp, "data", None) or []


# ---------------------------------------------------------------------------
# tennis_live_ladder — ladder LIVE per-mercato (write-on-change dal ladder_worker)
# ---------------------------------------------------------------------------
def upsert_tennis_ladder(row: Dict[str, Any]) -> None:
    """Ladder corrente di UN mercato tennis → ``tennis_live_ladder`` (idempotente).

    Chiave: ``market_id`` (il frontend legge la ladder per market_id, maybeSingle).
    ``updated_at`` forzato. Shape ``ladder`` identica al calcio (LiveLadderState).
    """
    sb = get_tennis_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    sb.table("tennis_live_ladder").upsert(payload, on_conflict="market_id").execute()


# ---------------------------------------------------------------------------
# tennis_live_now — stato glance real-time (mercati + order_mode + punteggio)
# ---------------------------------------------------------------------------
def upsert_tennis_now(
    event_id: str,
    inplay: bool,
    status: str,
    state: Dict[str, Any],
    score: Optional[Dict[str, Any]] = None,
    points: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Stato live di UN evento tennis → ``tennis_live_now`` (idempotente su event_id).

    ``state`` = TennisLiveNowState (markets + order_mode); ``score`` = TennisScoreState;
    ``points`` = ultimi TennisPointEvent. Match 1:1 con lib/tennis.ts::TennisLiveNowRow.
    """
    sb = get_tennis_client()
    row = {
        "event_id": event_id,
        "inplay": inplay,
        "status": status,
        "state": state,
        "score": score,
        "points": points,
        "updated_at": _now_iso(),
    }
    sb.table("tennis_live_now").upsert(row, on_conflict="event_id").execute()


# ---------------------------------------------------------------------------
# tennis_bot_control / tennis_bot_activity — hosting dei bot armati
# ---------------------------------------------------------------------------
def list_tennis_bot_controls(
    event_id: Optional[str] = None,
    statuses: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Righe di controllo bot (opz. filtrate per evento e/o stato)."""
    sb = get_tennis_client()
    q = sb.table("tennis_bot_control").select("*")
    if event_id is not None:
        q = q.eq("event_id", event_id)
    if statuses:
        q = q.in_("status", statuses)
    return getattr(q.execute(), "data", None) or []


def set_tennis_bot_status(
    event_id: str,
    bot_key: str,
    status: str,
    *,
    error: Optional[str] = None,
    stats: Optional[Dict[str, Any]] = None,
    heartbeat: bool = False,
    started: bool = False,
    stopped: bool = False,
) -> None:
    """Aggiorna lo stato/heartbeat/stat di un bot in ``tennis_bot_control``."""
    sb = get_tennis_client()
    now = _now_iso()
    upd: Dict[str, Any] = {"status": status}
    if error is not None:
        upd["error"] = str(error)[:300]
    if stats is not None:
        upd["stats"] = stats
    if heartbeat:
        upd["heartbeat_at"] = now
    if started:
        upd["started_at"] = now
    if stopped:
        upd["stopped_at"] = now
    sb.table("tennis_bot_control").update(upd).eq("event_id", event_id).eq(
        "bot_key", bot_key
    ).execute()


def write_tennis_bot_activity(
    event_id: str, bot_key: str, kind: str, payload: Dict[str, Any]
) -> None:
    """Append di una riga di attività bot → ``tennis_bot_activity`` (best-effort)."""
    sb = get_tennis_client()
    sb.table("tennis_bot_activity").insert(
        {
            "event_id": event_id,
            "bot_key": bot_key,
            "kind": kind,
            "payload": payload,
            "ts": _now_iso(),
        }
    ).execute()


# ---------------------------------------------------------------------------
# tennis_live_order_queue — coda comandi ordine manuali (drenata dal worker)
# ---------------------------------------------------------------------------
def list_pending_tennis_orders(limit: int = 5) -> List[Dict[str, Any]]:
    sb = get_tennis_client()
    resp = (
        sb.table(_ORDER_TABLE)
        .select("*")
        .eq("status", "pending")
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return getattr(resp, "data", None) or []


def claim_tennis_order(rid: int) -> bool:
    """CLAIM atomico pending → processing. True se questa chiamata l'ha preso."""
    sb = get_tennis_client()
    claimed = (
        sb.table(_ORDER_TABLE)
        .update({"status": "processing"})
        .eq("id", rid)
        .eq("status", "pending")
        .execute()
        .data
        or []
    )
    return len(claimed) > 0


def write_tennis_order_done(rid: int, result: Dict[str, Any]) -> None:
    sb = get_tennis_client()
    sb.table(_ORDER_TABLE).update(
        {
            "status": "done",
            "result": result,
            "error": result.get("error"),
            "bet_id": result.get("bet_id"),
            "processed_at": _now_iso(),
        }
    ).eq("id", rid).execute()


def write_tennis_order_error(rid: int, result: Dict[str, Any]) -> None:
    sb = get_tennis_client()
    sb.table(_ORDER_TABLE).update(
        {
            "status": "error",
            "error": (result.get("error") or "")[:300] or None,
            "result": result,
            "processed_at": _now_iso(),
        }
    ).eq("id", rid).execute()


# ---------------------------------------------------------------------------
# tennis_live_orders / tennis_live_positions — specchio ordini + esposizioni
# ---------------------------------------------------------------------------
def upsert_tennis_order(row: Dict[str, Any]) -> None:
    """Specchio di UN ordine tennis → ``tennis_live_orders`` (idempotente).

    Chiave: ``(mode, client_order_ref)`` (una riga per ordine). ``updated_at`` forzato.
    """
    sb = get_tennis_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    sb.table("tennis_live_orders").upsert(
        payload, on_conflict="mode,client_order_ref"
    ).execute()


def upsert_tennis_position(row: Dict[str, Any]) -> None:
    """Esposizione di UNA selezione tennis → ``tennis_live_positions`` (idempotente).

    Chiave: ``(mode, market_id, selection_id, handicap)``. ``updated_at`` forzato.
    """
    sb = get_tennis_client()
    payload = dict(row)
    payload["updated_at"] = _now_iso()
    sb.table("tennis_live_positions").upsert(
        payload, on_conflict="mode,market_id,selection_id,handicap"
    ).execute()
