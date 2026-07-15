"""omega_db — I/O Supabase per Omega (service_role, bypassa RLS).

Il servizio locale legge ``omega_control`` (singleton, id=1) per stato/parametri
e scrive ``omega_trades`` (mirror dei lay) + ``omega_activity`` (log). La UI legge
gli stessi dati via RPC owner-only (migrations/omega_bot.sql).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from db_client import get_supabase_client

logger = logging.getLogger("omega.db")

CONTROL_ID = 1


def _sb() -> Any:
    return get_supabase_client()


# ---------------------------------------------------------------------------
# Control (singleton)
# ---------------------------------------------------------------------------
def read_control() -> Optional[dict[str, Any]]:
    res = _sb().table("omega_control").select("*").eq("id", CONTROL_ID).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def set_control(**fields: Any) -> None:
    if not fields:
        return
    _sb().table("omega_control").update(fields).eq("id", CONTROL_ID).execute()


def log(kind: str, payload: Optional[dict[str, Any]] = None) -> None:
    try:
        _sb().table("omega_activity").insert(
            {"kind": kind, "payload": payload or {}}
        ).execute()
    except Exception as ex:  # noqa: BLE001 - il log non deve mai fermare il bot
        logger.warning("[omega.db] log '%s' fallito: %s", kind, str(ex)[:120])


# ---------------------------------------------------------------------------
# Trades (mirror)
# ---------------------------------------------------------------------------
def insert_trade(trade: dict[str, Any]) -> Optional[int]:
    res = _sb().table("omega_trades").insert(trade).execute()
    rows = res.data or []
    return rows[0].get("id") if rows else None


def update_trade(trade_id: int, **fields: Any) -> None:
    if not fields:
        return
    _sb().table("omega_trades").update(fields).eq("id", trade_id).execute()


def delete_trade(trade_id: int) -> None:
    # GUARD su status='pending': se nel frattempo un operatore ha corretto a mano la
    # riga (es. a 'open' con bet_id reale dopo l'allarme CRITICAL), NON la cancella.
    _sb().table("omega_trades").delete().eq("id", trade_id).eq("status", "pending").execute()


def list_trades(status: Optional[str] = None) -> list[dict[str, Any]]:
    q = _sb().table("omega_trades").select("*")
    if status:
        q = q.eq("status", status)
    return q.order("placed_at", desc=False).execute().data or []


def traded_event_ids() -> set[str]:
    """event_id già piazzati (idempotenza I1)."""
    res = _sb().table("omega_trades").select("event_id").execute()
    return {str(r["event_id"]) for r in (res.data or []) if r.get("event_id")}


def open_trades() -> list[dict[str, Any]]:
    return list_trades(status="open")


# ---------------------------------------------------------------------------
# MANUALE: coda richieste, cache eventi, snapshot mercato
# ---------------------------------------------------------------------------
def pending_manual_requests() -> list[dict[str, Any]]:
    return (
        _sb().table("omega_manual_requests").select("*")
        .eq("status", "pending").order("created_at", desc=False).limit(50).execute().data
        or []
    )


def set_manual_status(req_id: int, status: str, result: Optional[dict[str, Any]] = None) -> None:
    from datetime import datetime, timezone

    fields: dict[str, Any] = {"status": status}
    if result is not None:
        fields["result"] = result
    if status in ("done", "error"):
        fields["processed_at"] = datetime.now(timezone.utc).isoformat()
    _sb().table("omega_manual_requests").update(fields).eq("id", req_id).execute()


def upsert_events(events: list[dict[str, Any]]) -> None:
    if not events:
        return
    _sb().table("omega_events").upsert(events, on_conflict="event_id").execute()


def update_event_markets(event_id: str, markets: list[dict[str, Any]]) -> None:
    from datetime import datetime, timezone

    _sb().table("omega_events").update(
        {"markets": markets, "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("event_id", event_id).execute()


def upsert_market_snapshot(snapshot: dict[str, Any]) -> None:
    _sb().table("omega_market_snapshot").upsert(snapshot, on_conflict="market_id").execute()


def get_event(event_id: str) -> Optional[dict[str, Any]]:
    rows = _sb().table("omega_events").select("*").eq("event_id", event_id).limit(1).execute().data or []
    return rows[0] if rows else None


def read_live_now(event_id: str) -> Optional[dict[str, Any]]:
    """Legge minuto+punteggio live dalla tabella CONDIVISA ``live_now`` (scritta dal
    runner calcio ogni ~5s). SOLA LETTURA: nessuna sessione Betfair, nessuna
    scrittura su tabelle altrui. Copre solo gli eventi seguiti dal runner
    (``live_follow``); per gli altri ritorna None → Omega usa il clock. Stesso
    pattern dello scalper (scalper_session.py:451-514).
    """
    try:
        res = (
            _sb().table("live_now")
            .select("minute,inplay,score_home,score_away,status,updated_at")
            .eq("event_id", str(event_id)).limit(1).execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as ex:  # noqa: BLE001 - il feed non deve mai fermare il bot
        logger.warning("[omega.db] read_live_now KO %s: %s", event_id, str(ex)[:120])
        return None


# ---------------------------------------------------------------------------
# MISSIONI (centro di controllo per partita)
# ---------------------------------------------------------------------------
def active_missions() -> list[dict[str, Any]]:
    """Missioni con status='active' (le stantie si auto-chiudono via fase 'finita')."""
    res = _sb().table("omega_missions").select("*").eq("status", "active").execute()
    return res.data or []


def mission_event_ids() -> set[str]:
    """event_id con missione ATTIVA: il loop automatico li deve saltare."""
    res = _sb().table("omega_missions").select("event_id").eq("status", "active").execute()
    return {str(r["event_id"]) for r in (res.data or []) if r.get("event_id")}


def update_mission(event_id: str, **fields: Any) -> None:
    if not fields:
        return
    _sb().table("omega_missions").update(fields).eq("event_id", event_id).execute()


def trades_for_event(event_id: str) -> list[dict[str, Any]]:
    res = (
        _sb().table("omega_trades")
        .select("id,phase,status,pnl,liability,bet_id,side,size,price,mode")
        .eq("event_id", str(event_id))
        .execute()
    )
    return res.data or []


# ---------------------------------------------------------------------------
# CONSULENTE DATI (advisor) — SOLO LETTURE per i segnali informativi delle
# proposte CS: fixture del giorno (matching), Poisson del motore, frequenze lega.
# Nessuna scrittura, nessun ordine: se una lettura fallisce l'advisor resta None.
# ---------------------------------------------------------------------------
def fixtures_for_window(start_iso: str, end_iso: str) -> list[dict[str, Any]]:
    """Fixture 'light' in [start, end) da fixture_predictions (per il matcher).
    Colonne minime: il db_json_analisi (pesante) si legge solo per la fixture
    abbinata via fixture_analysis()."""
    res = (
        _sb().table("fixture_predictions")
        .select("fixture_id,home_team_name,away_team_name,fixture_date,"
                "league_id,home_team_id,away_team_id")
        .gte("fixture_date", start_iso).lt("fixture_date", end_iso)
        .limit(2000).execute()
    )
    return res.data or []


def fixture_analysis(fixture_id: int) -> Optional[dict[str, Any]]:
    """db_json_analisi (output motore Poisson) della singola fixture abbinata."""
    rows = (
        _sb().table("fixture_predictions").select("db_json_analisi")
        .eq("fixture_id", int(fixture_id)).limit(1).execute().data or []
    )
    return rows[0].get("db_json_analisi") if rows else None


def market_frequency(league_id: int, market: str, selection: str) -> Optional[dict[str, Any]]:
    """RPC read-only get_market_frequency (baseline storica del punteggio in lega)."""
    res = _sb().rpc("get_market_frequency", {
        "p_league_id": int(league_id),
        "p_market": market,
        "p_selection": selection,
        "p_mode": "last_n",
        "p_last_n": 300,
    }).execute()
    return res.data or None


def aggregates(day_start=None) -> dict[str, float]:
    """Somma realizzato (won/lost/void settled) e liability aperta.

    ``day_start`` (datetime UTC, vedi ``omega_engine.day_start_utc``) aggiunge i
    campi della GIORNATA operativa (realized_today/matches_traded_today): senza,
    i contatori sarebbero cumulativi a vita e stop_on_goal/max_events/daily_loss_cap
    resterebbero scattati per sempre dal giorno dopo (§2 Costituzione).
    """
    rows = (
        _sb().table("omega_trades")
        .select("status,pnl,liability,bet_id,placed_at,settled_at")
        .execute().data or []
    )
    from Betfair.omega import omega_engine as E

    return E.aggregate_trades(rows, day_start)  # logica PURA e testata (§I8: pending+bet_id contano)
