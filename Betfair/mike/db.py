"""db — I/O Supabase del bot Mike (service_role, bypassa RLS).

Specchio di ``Betfair/safe_strategy/bot_db.py`` sulle tabelle di
``migrations/mike_bot.sql`` (control singleton id=1, events, trades, activity,
requests) PIU' le letture del feed unico (``safe_strategy_scan``) e gli accessori
della CODA FLUMINE (copiati 1:1: il gate ``omega_service._flumine_gate`` verifica
che l'oggetto db li esponga; senza, l'esecuzione via runner resta chiusa e si usa
il percorso legacy — che e' comunque quello di default di Mike, vedi service.py).

Tutte le funzioni sono ridefinibili nei test (``run_once(db=FakeDB())``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from db_client import get_supabase_client

logger = logging.getLogger("mike.db")

CONTROL_ID = 1
T_CONTROL = "mike_control"
T_EVENTS = "mike_events"
T_TRADES = "mike_trades"
T_ACTIVITY = "mike_activity"
T_REQUESTS = "mike_requests"
PAGE_SIZE = 1000


def _sb() -> Any:
    return get_supabase_client()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Control (singleton)
# ---------------------------------------------------------------------------
def read_control() -> Optional[dict[str, Any]]:
    rows = _sb().table(T_CONTROL).select("*").eq("id", CONTROL_ID).limit(1).execute().data or []
    return rows[0] if rows else None


def set_control(**fields: Any) -> None:
    if not fields:
        return
    fields.setdefault("updated_at", _now_iso())
    _sb().table(T_CONTROL).update(fields).eq("id", CONTROL_ID).execute()


def log(kind: str, payload: Optional[dict[str, Any]] = None, event_id: Optional[str] = None) -> None:
    try:
        row = {"kind": kind, "payload": payload or {}}
        if event_id is not None:
            row["event_id"] = str(event_id)
        _sb().table(T_ACTIVITY).insert(row).execute()
    except Exception as ex:  # noqa: BLE001 — il log non deve mai fermare il bot
        logger.warning("[mike.db] log '%s' fallito: %s", kind, str(ex)[:120])


# ---------------------------------------------------------------------------
# Events (stato per partita: macchina a stati + gambe + dossier)
# ---------------------------------------------------------------------------
def list_events(states: Optional[list[str]] = None, since_iso: Optional[str] = None) -> list[dict[str, Any]]:
    """Partite seguite; ``since_iso`` limita alle righe aggiornate di recente
    (le terminali vecchie escono dal ciclo ma restano nello storico)."""
    q = _sb().table(T_EVENTS).select("*")
    if states:
        q = q.in_("state", list(states))
    if since_iso:
        q = q.gte("updated_at", str(since_iso))
    return q.execute().data or []


def get_event(event_id: str) -> Optional[dict[str, Any]]:
    rows = _sb().table(T_EVENTS).select("*").eq("event_id", str(event_id)).limit(1).execute().data or []
    return rows[0] if rows else None


def upsert_event(row: dict[str, Any]) -> None:
    row = dict(row)
    row.setdefault("updated_at", _now_iso())
    _sb().table(T_EVENTS).upsert(row, on_conflict="event_id").execute()


def delete_events(event_ids: list[str]) -> None:
    if event_ids:
        _sb().table(T_EVENTS).delete().in_("event_id", [str(e) for e in event_ids]).execute()


# ---------------------------------------------------------------------------
# Trades (mirror per la UI / storico; una riga per gamba)
# ---------------------------------------------------------------------------
def insert_trade(trade: dict[str, Any]) -> Optional[int]:
    res = _sb().table(T_TRADES).insert(trade).execute()
    rows = res.data or []
    return rows[0].get("id") if rows else None


def update_trade(trade_id: int, **fields: Any) -> None:
    if not fields:
        return
    _sb().table(T_TRADES).update(fields).eq("id", int(trade_id)).execute()


def get_trade(trade_id: int) -> Optional[dict[str, Any]]:
    rows = _sb().table(T_TRADES).select("*").eq("id", int(trade_id)).limit(1).execute().data or []
    return rows[0] if rows else None


def open_trades() -> list[dict[str, Any]]:
    return (_sb().table(T_TRADES).select("*").in_("status", ["open", "hedged", "pending"])
            .order("placed_at", desc=False).execute().data or [])


def trades_for_event(event_id: str) -> list[dict[str, Any]]:
    return (_sb().table(T_TRADES).select("*").eq("event_id", str(event_id))
            .order("placed_at", desc=False).execute().data or [])


def all_trades(page_size: int = PAGE_SIZE) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    start = 0
    while True:
        chunk = (_sb().table(T_TRADES).select("*").order("id", desc=False)
                 .range(start, start + page_size - 1).execute().data or [])
        out.extend(chunk)
        if len(chunk) < page_size:
            return out
        start += page_size


def aggregates(now: Optional[datetime] = None) -> dict[str, float]:
    """Aggregati per le stats (riuso della funzione PURA di bot_db)."""
    from Betfair.safe_strategy import bot_db as _bot_db
    from Betfair.safe_strategy import risk as _risk

    rows = all_trades()
    return _bot_db.aggregate_rows(rows, _risk.operating_day_start(now))


# ---------------------------------------------------------------------------
# Requests (comandi dalla UI)
# ---------------------------------------------------------------------------
def pending_requests(limit: int = 50) -> list[dict[str, Any]]:
    return (_sb().table(T_REQUESTS).select("*").eq("status", "pending")
            .order("created_at", desc=False).limit(int(limit)).execute().data or [])


def set_request_status(req_id: int, status: str, result: Optional[dict[str, Any]] = None) -> None:
    fields: dict[str, Any] = {"status": status, "updated_at": _now_iso()}
    if result is not None:
        fields["result"] = result
    _sb().table(T_REQUESTS).update(fields).eq("id", int(req_id)).execute()


def fail_stale_processing(max_age_min: int = 10) -> None:
    try:
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_min * 60
        rows = _sb().table(T_REQUESTS).select("id,updated_at").eq("status", "processing").execute().data or []
        for r in rows:
            ts = r.get("updated_at")
            try:
                t = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError):
                t = 0.0
            if t < cutoff:
                set_request_status(int(r["id"]), "error", {"error": "processing_stale"})
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike.db] fail_stale_processing KO: %s", str(ex)[:120])


# ---------------------------------------------------------------------------
# FEED UNICO (safe_strategy_scan) — sola lettura
# ---------------------------------------------------------------------------
def fetch_scan_rows() -> list[dict[str, Any]]:
    """Tutte le righe calcio del feed: {event_id, sport, payload, updated_at}. UNA select."""
    try:
        return (_sb().table("safe_strategy_scan").select("event_id,sport,payload,updated_at")
                .eq("sport", "calcio").execute().data or [])
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike.db] lettura feed KO: %s", str(ex)[:160])
        return []


def scanner_status() -> Optional[dict[str, Any]]:
    try:
        rows = (_sb().table("safe_strategy_status").select("payload,updated_at")
                .eq("id", "scanner").limit(1).execute().data or [])
        return rows[0] if rows else None
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike.db] lettura scanner status KO: %s", str(ex)[:160])
        return None


# ---------------------------------------------------------------------------
# Dossier: ponte evento → fixture e letture modelli (nessuna chiamata Betfair)
# ---------------------------------------------------------------------------
def fixture_id_for_event(event_id: str) -> Optional[int]:
    """Ponte Betfair event_id → fixture_id: SOLO se la partita e' in live_follow."""
    try:
        rows = (_sb().table("live_follow").select("fixture_id,league_id")
                .eq("event_id", str(event_id)).limit(1).execute().data or [])
        fid = rows[0].get("fixture_id") if rows else None
        return int(fid) if fid is not None else None
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.db] live_follow KO %s: %s", event_id, str(ex)[:120])
        return None


def fixture_lambdas(fixture_id: Optional[int]) -> Optional[tuple]:
    """(λ_casa, λ_trasferta, league_id) dal DB — delega a Betfair/stream/db."""
    if fixture_id is None:
        return None
    try:
        from Betfair.stream import db as _sdb

        return _sdb.get_fixture_prematch_lambdas(int(fixture_id))
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.db] fixture_lambdas KO %s: %s", fixture_id, str(ex)[:120])
        return None


def fixture_analysis(fixture_id: Optional[int]) -> Optional[dict[str, Any]]:
    if fixture_id is None:
        return None
    try:
        from Betfair.omega import omega_db

        return omega_db.fixture_analysis(int(fixture_id))
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.db] fixture_analysis KO %s: %s", fixture_id, str(ex)[:120])
        return None


def ht_ft_rows(league_id: Optional[int]) -> list[dict[str, Any]]:
    try:
        from Betfair.omega import omega_db

        return omega_db.ht_ft_transitions(league_id)
    except Exception as ex:  # noqa: BLE001
        logger.debug("[mike.db] ht_ft_rows KO: %s", str(ex)[:120])
        return []


# ---------------------------------------------------------------------------
# CODA FLUMINE — copia 1:1 di bot_db (il gate ne verifica la presenza).
# ---------------------------------------------------------------------------
def live_follow_status(event_id: str) -> Optional[str]:
    rows = (_sb().table("live_follow").select("status").eq("event_id", str(event_id))
            .limit(1).execute().data or [])
    return rows[0].get("status") if rows else None


def runner_heartbeat() -> Optional[dict[str, Any]]:
    rows = (_sb().table("betfair_live_heartbeat").select("ts,mode,pid").eq("id", 1)
            .limit(1).execute().data or [])
    return rows[0] if rows else None


def enqueue_live_order(payload: dict[str, Any]) -> Optional[int]:
    res = _sb().rpc("request_betfair_live_order", {"p": payload}).execute()
    data = getattr(res, "data", None)
    return int(data) if data is not None else None


def get_live_order_request_by_ref(client_ref: str) -> Optional[dict[str, Any]]:
    rows = (_sb().table("betfair_live_order_requests")
            .select("id,status,result,error,bet_id,processed_at")
            .eq("client_ref", str(client_ref)).limit(1).execute().data or [])
    return rows[0] if rows else None


def get_live_order_request(request_id: int) -> Optional[dict[str, Any]]:
    rows = (_sb().table("betfair_live_order_requests")
            .select("id,status,result,error,bet_id,processed_at")
            .eq("id", int(request_id)).limit(1).execute().data or [])
    return rows[0] if rows else None


def revoke_live_order_request(request_id: int) -> bool:
    res = (_sb().table("betfair_live_order_requests")
           .update({"status": "error", "error": "revocata da mike (deadline live)",
                    "processed_at": _now_iso()})
           .eq("id", int(request_id)).eq("status", "pending").execute())
    return bool(res.data)


def get_live_order_mirror(client_order_ref: str, mode: str = "paper") -> Optional[dict[str, Any]]:
    rows = (_sb().table("betfair_live_orders").select("*").eq("mode", str(mode))
            .eq("client_order_ref", str(client_order_ref)).limit(1).execute().data or [])
    return rows[0] if rows else None
