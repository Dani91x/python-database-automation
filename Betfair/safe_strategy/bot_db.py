"""bot_db — I/O Supabase del BOT Safe Strategy (service_role, bypassa RLS).

Specchio di ``Betfair/omega/omega_db.py`` sulle tabelle di
``migrations/safe_strategy_bot.sql`` (control singleton id=1, trades, activity,
requests, opportunities) PIÙ le letture del feed unico (``safe_strategy_scan``).

Contiene anche i metodi della CODA FLUMINE copiati da omega_db: il gate
``omega_service._flumine_gate`` verifica che l'oggetto db li esponga tutti,
quindi senza di essi l'esecuzione via runner sarebbe sempre chiusa (paper e
live degradati al fallback legacy).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from db_client import get_supabase_client

from Betfair.safe_strategy import risk as _risk

logger = logging.getLogger("safe.bot.db")

CONTROL_ID = 1


def _sb() -> Any:
    return get_supabase_client()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Control (singleton)
# ---------------------------------------------------------------------------
def read_control() -> Optional[dict[str, Any]]:
    rows = (
        _sb().table("safe_strategy_control").select("*")
        .eq("id", CONTROL_ID).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def set_control(**fields: Any) -> None:
    if not fields:
        return
    fields.setdefault("updated_at", _now_iso())
    _sb().table("safe_strategy_control").update(fields).eq("id", CONTROL_ID).execute()


def log(kind: str, payload: Optional[dict[str, Any]] = None) -> None:
    try:
        _sb().table("safe_strategy_activity").insert(
            {"kind": kind, "payload": payload or {}}
        ).execute()
    except Exception as ex:  # noqa: BLE001 — il log non deve mai fermare il bot
        logger.warning("[safe.db] log '%s' fallito: %s", kind, str(ex)[:120])


# ---------------------------------------------------------------------------
# Trades (mirror)
# ---------------------------------------------------------------------------
def insert_trade(trade: dict[str, Any]) -> Optional[int]:
    res = _sb().table("safe_strategy_trades").insert(trade).execute()
    rows = res.data or []
    return rows[0].get("id") if rows else None


def update_trade(trade_id: int, **fields: Any) -> None:
    if not fields:
        return
    _sb().table("safe_strategy_trades").update(fields).eq("id", int(trade_id)).execute()


def delete_trade(trade_id: int) -> None:
    """Elimina SOLO una riserva ancora 'pending' (mai una posizione reale)."""
    (
        _sb().table("safe_strategy_trades").delete()
        .eq("id", int(trade_id)).eq("status", "pending").execute()
    )


def get_trade(trade_id: int) -> Optional[dict[str, Any]]:
    rows = (
        _sb().table("safe_strategy_trades").select("*")
        .eq("id", int(trade_id)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def list_trades(status: Optional[str] = None) -> list[dict[str, Any]]:
    q = _sb().table("safe_strategy_trades").select("*")
    if status:
        q = q.eq("status", status)
    return q.order("placed_at", desc=False).execute().data or []


def open_trades() -> list[dict[str, Any]]:
    """Posizioni vive: 'open' e 'hedged' (chiuse a mercato ma non ancora
    regolate — il P&L si realizza quando il mercato si chiude)."""
    return (
        _sb().table("safe_strategy_trades").select("*")
        .in_("status", ["open", "hedged"])
        .order("placed_at", desc=False).execute().data or []
    )


def closing_trades_for(trade_ids: list[int]) -> list[dict[str, Any]]:
    """Righe di CHIUSURA (cash-out) delle aperture indicate."""
    if not trade_ids:
        return []
    return (
        _sb().table("safe_strategy_trades").select("*")
        .in_("closes_trade_id", [int(i) for i in trade_ids]).execute().data or []
    )


PAGE_SIZE = 1000  # cap PostgREST per risposta: oltre si pagina con .range()


def _fetch_all(build, page_size: int = PAGE_SIZE) -> list[dict[str, Any]]:
    """Esaurisce una query paginando con ``.range()`` (``build`` costruisce una
    query NUOVA a ogni chiamata: i builder supabase sono mutabili)."""
    out: list[dict[str, Any]] = []
    start = 0
    while True:
        rows = build().range(start, start + page_size - 1).execute().data or []
        out.extend(rows)
        if len(rows) < page_size:
            return out
        start += page_size


def trade_by_idempotency_key(key: str) -> Optional[dict[str, Any]]:
    """Trade NON in errore con ``meta.idempotency_key == key`` (dedupe del manuale)."""
    rows = (
        _sb().table("safe_strategy_trades").select("id,status,meta")
        .contains("meta", {"idempotency_key": str(key)})
        .neq("status", "error").limit(1).execute().data or []
    )
    return rows[0] if rows else None


def traded_signal_keys() -> set[tuple[str, str]]:
    """(event_id, signal_key) già riservati/piazzati dall'AUTOMATICO: idempotenza
    per segnale (le righe 'error' non bloccano il ripiazzamento). Paginata:
    oltre ~1000 righe una SELECT nuda perderebbe chiavi → doppi piazzamenti."""
    rows = _fetch_all(lambda: (
        _sb().table("safe_strategy_trades").select("event_id,signal_key")
        .eq("origin", "auto").neq("status", "error")
        .order("id", desc=False)
    ))
    out: set[tuple[str, str]] = set()
    for r in rows:
        eid, key = r.get("event_id"), r.get("signal_key")
        if eid and key:
            out.add((str(eid), str(key)))
    return out


def aggregates(now: Optional[datetime] = None) -> dict[str, float]:
    """Realizzato / esposizione aperta (le 'hedged' contano ancora come aperte),
    con la GIORNATA OPERATIVA Europe/Rome (``risk.operating_day_start``) per
    realized_today e per la liability giornaliera del motore di rischio."""
    rows = _fetch_all(lambda: (
        _sb().table("safe_strategy_trades")
        .select("status,pnl,liability,settled_at,placed_at,strategy,bet_id,meta,closes_trade_id")
        .order("id", desc=False)
    ))
    return aggregate_rows(rows, day_start=_risk.operating_day_start(now))


def aggregate_rows(rows: list[dict[str, Any]], day_start: Optional[datetime] = None) -> dict[str, float]:
    """Aggregazione PURA (testabile) delle righe trade.

    Gambe di CHIUSURA (``closes_trade_id``): ESCLUSE da open_count/open_liability
    — il rischio vivo della coppia e' gia' contato dall'originale 'hedged'
    (liability piena, stima prudente) — il loro pnl entra nel realizzato solo
    quando regolate. Stessa regola di ``get_safe_state`` (migrazione) e di
    ``omega_engine.aggregate_trades``; senza, stats.trades_open contava anche
    le chiusure (6 per 4 originali, E2E live 10/09).

    ``day_liability`` / ``day_liability_model`` / ``day_trades``: liability
    IMPEGNATA nella giornata (righe piazzate da ``day_start``: aperte, in
    riconciliazione o già regolate won/lost; le void non hanno impegnato nulla),
    totale e dei soli trade di modello — base dei cap giornalieri di ``risk``."""
    realized = realized_today = open_liab = 0.0
    day_liab = day_liab_model = 0.0
    open_n = day_n = 0
    for r in rows:
        status = str(r.get("status") or "")
        pnl = float(r.get("pnl") or 0.0)
        liab = float(r.get("liability") or 0.0)
        if not r.get("closes_trade_id") and status != "void" and \
                (day_start is None or _on_or_after(r.get("placed_at"), day_start)) and (
                status in ("open", "hedged", "won", "lost")
                or (status == "pending" and (r.get("bet_id")
                                             or (r.get("meta") or {}).get("flumine_client_ref")))):
            day_liab += liab
            day_n += 1
            if str(r.get("strategy") or "") in _risk.MODEL_STRATEGIES:
                day_liab_model += liab
        if r.get("closes_trade_id"):
            if status in ("won", "lost", "void"):
                realized += pnl
                if day_start is None or _on_or_after(r.get("settled_at"), day_start):
                    realized_today += pnl
            continue
        if status in ("won", "lost", "void"):
            realized += pnl
            if day_start is None or _on_or_after(r.get("settled_at"), day_start):
                realized_today += pnl
        elif status in ("open", "hedged") or (
            status == "pending" and (
                r.get("bet_id") or (r.get("meta") or {}).get("flumine_client_ref")
                # esito REST ignoto in riconciliazione: l'ordine può esistere
                or (r.get("meta") or {}).get("reason") == "place_exception_reconciling"
            )
        ):
            open_liab += liab
            open_n += 1
    return {
        "realized_total": round(realized, 2),
        "realized_today": round(realized_today, 2),
        "open_liability": round(open_liab, 2),
        "open_count": open_n,
        "day_liability": round(day_liab, 2),
        "day_liability_model": round(day_liab_model, 2),
        "day_trades": day_n,
    }


def _on_or_after(iso: Any, boundary: datetime) -> bool:
    if not iso:
        return False
    try:
        ts = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts >= boundary


# ---------------------------------------------------------------------------
# Coda richieste dalla UI (place / cashout / cancel)
# ---------------------------------------------------------------------------
def pending_requests(limit: int = 50) -> list[dict[str, Any]]:
    return (
        _sb().table("safe_strategy_requests").select("*")
        .eq("status", "pending").order("created_at", desc=False)
        .limit(int(limit)).execute().data or []
    )


def set_request_status(req_id: int, status: str,
                       result: Optional[dict[str, Any]] = None) -> None:
    fields: dict[str, Any] = {"status": status, "updated_at": _now_iso()}
    if result is not None:
        fields["result"] = result
    _sb().table("safe_strategy_requests").update(fields).eq("id", int(req_id)).execute()


def fail_stale_processing(max_age_min: int = 10) -> None:
    """Richieste rimaste in 'processing' (servizio morto a metà) → 'error'."""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_min)).isoformat()
    (
        _sb().table("safe_strategy_requests")
        .update({"status": "error",
                 "result": {"err": "servizio interrotto durante l'elaborazione"},
                 "updated_at": _now_iso()})
        .eq("status", "processing").lt("created_at", cutoff).execute()
    )


# ---------------------------------------------------------------------------
# Opportunità (scritte dal bot, lette dalla UI)
# ---------------------------------------------------------------------------
def upsert_opportunities(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    try:
        _sb().table("safe_strategy_opportunities").upsert(
            rows, on_conflict="event_id").execute()
    except Exception as ex:  # noqa: BLE001 — best-effort: mai fermare il bot
        logger.warning("[safe.db] upsert opportunità KO: %s", str(ex)[:160])


def delete_opportunities(event_ids: list[str]) -> None:
    if not event_ids:
        return
    try:
        (
            _sb().table("safe_strategy_opportunities").delete()
            .in_("event_id", [str(e) for e in event_ids]).execute()
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.db] delete opportunità KO: %s", str(ex)[:160])


# ---------------------------------------------------------------------------
# CATENA λ PRE-MATCH — sola lettura delle tabelle di Omega/motore:
# omega_events (evento → fixture_id/league_id, popolata dal refresh eventi di
# Omega) e fixture_predictions (fixture del giorno + db_json_analisi).
# ``get_event`` e' la copia di omega_db.get_event: cosi' il bot puo' passare
# se stesso a ``omega_service._prematch_lambdas`` (stesso contratto).
# ---------------------------------------------------------------------------
def get_event(event_id: str) -> Optional[dict[str, Any]]:
    rows = (
        _sb().table("omega_events").select("*")
        .eq("event_id", str(event_id)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def fixtures_for_window(start_iso: str, end_iso: str) -> list[dict[str, Any]]:
    """Fixture 'light' in [start, end) — delega a omega_db (stessa query del
    matcher di Omega). [] su qualsiasi errore: la catena λ passa oltre."""
    try:
        from Betfair.omega import omega_db

        return omega_db.fixtures_for_window(start_iso, end_iso) or []
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.db] fixtures_for_window KO: %s", str(ex)[:160])
        return []


def fixture_analysis(fixture_id: int) -> Optional[dict[str, Any]]:
    """db_json_analisi della fixture abbinata — delega a omega_db."""
    try:
        from Betfair.omega import omega_db

        return omega_db.fixture_analysis(int(fixture_id))
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.db] fixture_analysis %s KO: %s", fixture_id, str(ex)[:160])
        return None


# ---------------------------------------------------------------------------
# FEED UNICO (safe_strategy_scan) — sola lettura
# ---------------------------------------------------------------------------
def fetch_scan_rows() -> list[dict[str, Any]]:
    """Tutte le righe del feed: {event_id, sport, payload, updated_at}."""
    try:
        return (
            _sb().table("safe_strategy_scan")
            .select("event_id,sport,payload,updated_at").execute().data or []
        )
    except Exception as ex:  # noqa: BLE001 — feed KO: ciclo senza segnali
        logger.warning("[safe.db] lettura feed KO: %s", str(ex)[:160])
        return []


def scanner_status() -> Optional[dict[str, Any]]:
    """Heartbeat dello scanner (safe_strategy_status id='scanner')."""
    try:
        rows = (
            _sb().table("safe_strategy_status").select("payload,updated_at")
            .eq("id", "scanner").limit(1).execute().data or []
        )
        return rows[0] if rows else None
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.db] lettura scanner status KO: %s", str(ex)[:160])
        return None


# ---------------------------------------------------------------------------
# CODA FLUMINE — copia 1:1 di omega_db (il gate ne verifica la presenza).
# SOLO enqueue via RPC + letture + revoca atomica: il worker della coda non
# viene mai toccato.
# ---------------------------------------------------------------------------
def live_follow_status(event_id: str) -> Optional[str]:
    rows = (
        _sb().table("live_follow").select("status")
        .eq("event_id", str(event_id)).limit(1).execute().data or []
    )
    return rows[0].get("status") if rows else None


def runner_heartbeat() -> Optional[dict[str, Any]]:
    rows = (
        _sb().table("betfair_live_heartbeat").select("ts,mode,pid")
        .eq("id", 1).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def enqueue_live_order(payload: dict[str, Any]) -> Optional[int]:
    res = _sb().rpc("request_betfair_live_order", {"p": payload}).execute()
    data = getattr(res, "data", None)
    return int(data) if data is not None else None


def get_live_order_request_by_ref(client_ref: str) -> Optional[dict[str, Any]]:
    rows = (
        _sb().table("betfair_live_order_requests")
        .select("id,status,result,error,bet_id,processed_at")
        .eq("client_ref", str(client_ref)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def get_live_order_request(request_id: int) -> Optional[dict[str, Any]]:
    rows = (
        _sb().table("betfair_live_order_requests")
        .select("id,status,result,error,bet_id,processed_at")
        .eq("id", int(request_id)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def revoke_live_order_request(request_id: int) -> bool:
    res = (
        _sb().table("betfair_live_order_requests")
        .update({"status": "error",
                 "error": "revocata da safe strategy (deadline live)",
                 "processed_at": _now_iso()})
        .eq("id", int(request_id)).eq("status", "pending").execute()
    )
    return bool(res.data)


def get_live_order_mirror(client_order_ref: str, mode: str = "paper") -> Optional[dict[str, Any]]:
    rows = (
        _sb().table("betfair_live_orders").select("*")
        .eq("mode", str(mode)).eq("client_order_ref", str(client_order_ref))
        .limit(1).execute().data or []
    )
    return rows[0] if rows else None
