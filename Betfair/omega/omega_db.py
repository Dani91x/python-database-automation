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


# colonne aggiunte da migrations/omega_manual.sql (enrichment 16/07): se la
# migrazione non è ancora applicata l'upsert fallirebbe → retry senza di esse.
_EVENT_ENRICH_COLS = (
    "country_code", "competition_id", "competition_name",
    "fixture_id", "league_id", "home_team_id", "away_team_id",
)


def fail_stale_processing(max_age_min: int = 10) -> None:
    """Richieste manuali rimaste in 'processing' (servizio morto a metà) → 'error'
    dopo max_age_min: senza questo una 'place' interrotta spariva in silenzio e
    la UI restava senza esito per sempre (AUDIT L10 16/07). Il reserve-first
    evita comunque il doppio ordine."""
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_min)).isoformat()
    (
        _sb().table("omega_manual_requests")
        .update({
            "status": "error",
            "result": {"err": "servizio interrotto durante l'elaborazione"},
            "processed_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("status", "processing").lt("created_at", cutoff).execute()
    )


def replace_events(events: list[dict[str, Any]]) -> None:
    """SOSTITUISCE la cache eventi: upsert delle righe fresche + DELETE delle
    righe non più presenti. Senza purge la cache accumulava eventi di giorni
    passati (mostrati senza data → missioni attivate su partite già finite)."""
    if events:
        try:
            _sb().table("omega_events").upsert(events, on_conflict="event_id").execute()
        except Exception as ex:  # noqa: BLE001 — colonne enrichment assenti (migrazione non applicata)
            logger.warning("[omega] upsert eventi con enrichment fallito (%s): retry legacy — applicare migrations/omega_manual.sql", str(ex)[:120])
            legacy = [{k: v for k, v in r.items() if k not in _EVENT_ENRICH_COLS} for r in events]
            _sb().table("omega_events").upsert(legacy, on_conflict="event_id").execute()
    ids = [str(r.get("event_id")) for r in events if r.get("event_id")]
    q = _sb().table("omega_events").delete()
    if ids:
        # PostgREST: not_.in_ vuole la lista fra parentesi
        q = q.not_.in_("event_id", ids)
    else:
        q = q.neq("event_id", "")  # lista vuota → svuota tutta la cache
    q.execute()


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
# ESECUZIONE VIA FLUMINE — omega come CLIENT della coda ESISTENTE del runner
# calcio (betfair_live_order_queue.sql / live_order_worker.py). SOLO enqueue
# (RPC) + letture + revoca atomica di righe MAI prese in carico: il worker
# della coda NON è mai toccato. Usato dal gate _flumine_gate e dal poll di
# conferma in omega_service. v1 (16/07): solo paper; v2 (17/07): anche il LIVE
# (timeInForce=FILL_OR_KILL nel payload, kill-switch omega_live_via_flumine).
# Il mode della richiesta deriva SEMPRE e SOLO dal mode del trade.
# ---------------------------------------------------------------------------
def live_follow_status(event_id: str) -> Optional[str]:
    """``live_follow.status`` per l'evento ('STREAMING' = runner agganciato)."""
    rows = (
        _sb().table("live_follow").select("status")
        .eq("event_id", str(event_id)).limit(1).execute().data or []
    )
    return rows[0].get("status") if rows else None


def runner_heartbeat() -> Optional[dict[str, Any]]:
    """Heartbeat del runner calcio (singleton ``betfair_live_heartbeat`` id=1):
    ``ts`` (freschezza = runner vivo) + ``mode`` (OFF|PAPER|LIVE)."""
    rows = (
        _sb().table("betfair_live_heartbeat").select("ts,mode,pid")
        .eq("id", 1).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def enqueue_live_order(payload: dict[str, Any]) -> Optional[int]:
    """Accoda UN comando sulla coda del runner via RPC ``request_betfair_live_order``
    (contratto esistente: idempotente su client_ref, owner/service_role only).
    Ritorna l'id della richiesta accodata (o già esistente)."""
    res = _sb().rpc("request_betfair_live_order", {"p": payload}).execute()
    data = getattr(res, "data", None)
    return int(data) if data is not None else None


def get_live_order_request_by_ref(client_ref: str) -> Optional[dict[str, Any]]:
    """Riga della coda per ``client_ref`` (idempotenza): recovery quando il
    processo è morto tra enqueue e persistenza di ``flumine_request_id``
    (fix F1 review 16/07)."""
    rows = (
        _sb().table("betfair_live_order_requests")
        .select("id,status,result,error,bet_id,processed_at")
        .eq("client_ref", str(client_ref)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def get_live_order_request(request_id: int) -> Optional[dict[str, Any]]:
    """Riga della coda (status/result/error/bet_id) per id — poll dell'esito."""
    rows = (
        _sb().table("betfair_live_order_requests")
        .select("id,status,result,error,bet_id,processed_at")
        .eq("id", int(request_id)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def revoke_live_order_request(request_id: int) -> bool:
    """REVOCA atomica di una richiesta ancora 'pending' (pending→error),
    SPECULARE al claim del worker (una sola delle due transizioni vince).
    Usata dal percorso LIVE via flumine oltre la hard deadline: il runner,
    tornando vivo ore dopo, NON deve piazzare un ordine reale stantio.
    Ritorna True SOLO se questa chiamata ha vinto la transizione."""
    from datetime import datetime, timezone

    res = (
        _sb().table("betfair_live_order_requests")
        .update({"status": "error",
                 "error": "revocata da omega (deadline live)",
                 "processed_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", int(request_id)).eq("status", "pending").execute()
    )
    return bool(res.data)


def get_live_order_mirror(client_order_ref: str, mode: str = "paper") -> Optional[dict[str, Any]]:
    """Riga dello specchio ``betfair_live_orders`` per (mode, client_order_ref =
    ``awlq<request_id>``): fill/size/prezzo medio REALI simulati da flumine."""
    rows = (
        _sb().table("betfair_live_orders").select("*")
        .eq("mode", str(mode)).eq("client_order_ref", str(client_order_ref))
        .limit(1).execute().data or []
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# MISSIONI (centro di controllo per partita)
# ---------------------------------------------------------------------------
def active_missions() -> list[dict[str, Any]]:
    """Missioni con status='active' (le stantie si auto-chiudono via fase 'finita')."""
    res = _sb().table("omega_missions").select("*").eq("status", "active").execute()
    return res.data or []


def mission_event_ids() -> set[str]:
    """event_id con missione attiva O IN PAUSA: il loop automatico li salta.
    (AUDIT M7 16/07: una missione pausata senza trade lasciava l'evento libero
    all'automatico → al rientro dalla pausa esposizione doppia invisibile.)"""
    res = (
        _sb().table("omega_missions").select("event_id")
        .in_("status", ["active", "paused"]).execute()
    )
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
    # FIX F2 (review 16/07, HIGH): ``meta`` DEVE essere nella select — senza,
    # aggregate_trades non vede ``meta.flumine_client_ref`` e i pending in attesa
    # del fill flumine (paper E live) NON contano in liability/max_events (dead
    # code con dati reali). ``mode`` incluso per la stessa ragione (audit/futuro).
    rows = (
        _sb().table("omega_trades")
        .select("status,pnl,liability,bet_id,placed_at,settled_at,meta,mode")
        .execute().data or []
    )
    from Betfair.omega import omega_engine as E

    return E.aggregate_trades(rows, day_start)  # logica PURA e testata (§I8: pending+bet_id contano)
