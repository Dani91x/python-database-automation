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
from Betfair.safe_strategy.execution import residual_liability as _residual_liability

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


# la RPC degli aggregati arriva con la migrazione safe_strategy_bot_v2.sql: se
# non c'e', si ripiega sulla scansione e si riprova ogni 5 minuti (non a ogni ciclo)
_AGG_RPC: dict[str, float] = {"ko_ts": 0.0}
_AGG_RPC_RETRY_S = 300.0

_AGG_KEYS = ("realized_total", "realized_today", "open_liability", "open_count",
             "reconciling_liability", "day_liability", "day_liability_model",
             "day_trades", "legs_today", "events_today", "won_today", "lost_today")


def aggregates(now: Optional[datetime] = None) -> dict[str, float]:
    """Realizzato, rischio APERTO (residuo dopo le coperture) e capitale
    IMPEGNATO nella giornata operativa Europe/Rome
    (``risk.operating_day_start``) = giorno di PIAZZAMENTO della posizione.
    Le 'hedged' restano posizioni vive (il P&L si realizza al settlement) ma
    con il solo rischio RESIDUO.

    M-29: una sola RPC (``get_safe_aggregates``, migrazione
    ``safe_strategy_bot_v2.sql``) invece della lettura INTEGRALE della tabella a
    ogni ciclo (2 s). Se la migrazione non e' applicata si ripiega sulla
    scansione Python: stesso risultato, solo piu' costosa."""
    now_ts = (now or datetime.now(timezone.utc)).timestamp()
    if now_ts - float(_AGG_RPC["ko_ts"]) >= _AGG_RPC_RETRY_S:
        try:
            res = _sb().rpc("get_safe_aggregates", {}).execute()
            data = getattr(res, "data", None)
            if isinstance(data, dict) and "open_liability" in data:
                _AGG_RPC["ko_ts"] = 0.0
                return {k: data.get(k, 0) for k in _AGG_KEYS}
            logger.info("[safe.db] get_safe_aggregates risposta inattesa (%s): "
                        "scansione Python", type(data).__name__)
        except Exception as ex:  # noqa: BLE001 — migrazione non applicata / RPC KO
            logger.info("[safe.db] get_safe_aggregates non disponibile (%s): scansione Python",
                        str(ex)[:120])
        # L3: si arriva qui SOLO se la RPC non ha dato un risultato usabile
        # (eccezione O risposta non-dict): in entrambi i casi si apre la finestra
        # di attesa, altrimenti ogni ciclo (2 s) pagherebbe un round-trip inutile
        _AGG_RPC["ko_ts"] = now_ts
    rows = _fetch_all(lambda: (
        _sb().table("safe_strategy_trades")
        .select("id,event_id,status,pnl,liability,settled_at,placed_at,strategy,bet_id,meta,closes_trade_id")
        .order("id", desc=False)
    ))
    return aggregate_rows(rows, day_start=_risk.operating_day_start(now))


def _is_reconciling_row(r: dict[str, Any]) -> bool:
    """'pending' senza marker di coda il cui ordine REALE potrebbe esistere."""
    return str((r.get("meta") or {}).get("reason") or "") == "place_exception_reconciling"


def _counts_as_placed(r: dict[str, Any]) -> bool:
    """La riga ha (o può avere) un ordine a mercato: conta nell'esposizione."""
    status = str(r.get("status") or "")
    if status in ("open", "hedged", "won", "lost"):
        return True
    if status != "pending":
        return False
    meta = r.get("meta") or {}
    return bool(r.get("bet_id") or meta.get("flumine_client_ref")
                or _is_reconciling_row(r))


def _committed_liability(r: dict[str, Any]) -> float:
    """Capitale IMPEGNATO dalla riga nella giornata: la liability d'apertura,
    SEMPRE — anche se poi la posizione è stata coperta (review H1: usare il
    residuo qui liberava il cap giornaliero a ogni green-up)."""
    try:
        return max(0.0, float(r.get("liability") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def place_attempts() -> dict[tuple[str, str], dict[str, Any]]:
    """{(event_id, signal_key): {'attempts', 'last_ts', 'final'}} dalle righe
    AUTOMATICHE andate in 'error' col marker ``meta.place`` (H-21).

    Serve a NON ripartire da zero col budget dei ritentativi dopo un riavvio del
    servizio: senza, un FOK rifiutato tornerebbe a essere ritentato ogni 2 s."""
    rows = _fetch_all(lambda: (
        _sb().table("safe_strategy_trades").select("event_id,signal_key,meta")
        .eq("origin", "auto").eq("status", "error").order("id", desc=False)
    ))
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        eid, key = r.get("event_id"), r.get("signal_key")
        pl = (r.get("meta") or {}).get("place")
        if not (eid and key and isinstance(pl, dict)):
            continue
        prev = out.get((str(eid), str(key))) or {}
        if int(pl.get("attempts") or 0) >= int(prev.get("attempts") or 0):
            out[(str(eid), str(key))] = {"attempts": int(pl.get("attempts") or 0),
                                         "last_ts": pl.get("last_ts"),
                                         "final": bool(pl.get("final"))}
    return out


def recent_activity(limit: int = 60) -> list[dict[str, Any]]:
    """Ultime righe di ``safe_strategy_activity`` (per lo stato del servizio)."""
    try:
        return (
            _sb().table("safe_strategy_activity").select("id,ts,kind,payload")
            .order("id", desc=True).limit(int(limit)).execute().data or []
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.db] lettura attivita' KO: %s", str(ex)[:160])
        return []


def aggregate_rows(rows: list[dict[str, Any]], day_start: Optional[datetime] = None) -> dict[str, float]:
    """Aggregazione PURA (testabile) delle righe trade.

    GIORNATA OPERATIVA = giorno di PIAZZAMENTO della POSIZIONE (C-01/H-03):
    un solo numero per la stessa giornata in KPI, pannello rischio, tab Trade e
    storico. Una gamba di chiusura appartiene al giorno dell'APERTURA che chiude
    (``placed_at`` del padre): un green-up di mezzanotte non sposta il P&L di
    ieri sull'oggi.

    Gambe di CHIUSURA (``closes_trade_id``): ESCLUSE da open_count/open_liability
    — il rischio vivo della coppia e' gia' contato dall'originale — il loro pnl
    entra nel realizzato (del giorno del padre) quando regolate.

    DUE liability DIVERSE, e non vanno confuse (review H1):
      • ``open_liability`` = rischio ANCORA VIVO ora → dopo una copertura
        confermata conta il RESIDUO (M-26, ``execution.residual_liability``);
      • ``day_liability`` / ``day_liability_model`` = capitale IMPEGNATO nella
        giornata (colonna ``liability`` d'apertura) → base dei cap giornalieri
        di ``risk``: coprire una posizione NON libera il cap del giorno,
        altrimenti si potrebbe girare capitale all'infinito.
    I 'pending' in riconciliazione contano nell'esposizione E, a parte, in
    ``reconciling_liability`` (H-03).

    ``won_today``/``lost_today`` contano le POSIZIONI per SEGNO del P&L totale
    (apertura + chiusure), non per lo status grezzo della gamba (M-16)."""
    placed_by_id: dict[Any, Any] = {r.get("id"): r.get("placed_at") for r in rows
                                    if r.get("id") is not None}
    total_by_parent: dict[Any, float] = {}
    for r in rows:
        pid = r.get("closes_trade_id")
        if pid is not None and str(r.get("status") or "") in ("won", "lost", "void"):
            total_by_parent[pid] = total_by_parent.get(pid, 0.0) + float(r.get("pnl") or 0.0)

    realized = realized_today = open_liab = reconciling_liab = 0.0
    day_liab = day_liab_model = 0.0
    open_n = day_n = won_today = lost_today = legs_today = 0
    events_today: set[str] = set()
    for r in rows:
        status = str(r.get("status") or "")
        pnl = float(r.get("pnl") or 0.0)
        liab = _residual_liability(r)          # rischio VIVO ora
        committed = _committed_liability(r)    # capitale IMPEGNATO (cap del giorno)
        pid = r.get("closes_trade_id")
        # giorno della POSIZIONE: quello dell'apertura anche per le chiusure
        pos_placed = placed_by_id.get(pid) if pid is not None else r.get("placed_at")
        if pos_placed is None:
            pos_placed = r.get("placed_at")
        in_day = day_start is None or _on_or_after(pos_placed, day_start)
        if not pid and status != "void" and in_day and _counts_as_placed(r):
            day_liab += committed
            day_n += 1
            legs_today += 1
            if r.get("event_id"):
                events_today.add(str(r.get("event_id")))
            if str(r.get("strategy") or "") in _risk.MODEL_STRATEGIES:
                day_liab_model += committed
        if status in ("won", "lost", "void"):
            realized += pnl
            if in_day:
                realized_today += pnl
            if not pid and in_day:
                total = round(pnl + total_by_parent.get(r.get("id"), 0.0), 2)
                if total > 0:
                    won_today += 1
                elif total < 0:
                    lost_today += 1
        if pid:
            continue
        if status in ("open", "hedged") or (status == "pending" and _counts_as_placed(r)):
            open_liab += liab
            open_n += 1
            if status == "pending" and _is_reconciling_row(r):
                reconciling_liab += liab
    return {
        "realized_total": round(realized, 2),
        "realized_today": round(realized_today, 2),
        "open_liability": round(open_liab, 2),
        "open_count": open_n,
        "reconciling_liability": round(reconciling_liab, 2),
        "day_liability": round(day_liab, 2),
        "day_liability_model": round(day_liab_model, 2),
        "day_trades": day_n,
        "legs_today": legs_today,
        "events_today": len(events_today),
        "won_today": won_today,
        "lost_today": lost_today,
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


REQUEST_STATES = ("pending", "processing", "done", "rejected", "error")


def set_request_status(req_id: int, status: str,
                       result: Optional[dict[str, Any]] = None) -> None:
    """Chiude (o avanza) una richiesta della UI. ``status`` del vocabolario
    ``REQUEST_STATES``: 'rejected' = richiesta RIFIUTATA dal servizio (non un
    guasto: es. cancel di una riserva in riconciliazione) — richiede la
    migrazione ``safe_strategy_bot_v2.sql``; senza, il CHECK del DB la
    rifiuterebbe, quindi si ripiega su 'error' conservando il motivo."""
    fields: dict[str, Any] = {"status": status, "updated_at": _now_iso()}
    if result is not None:
        fields["result"] = result
    try:
        _sb().table("safe_strategy_requests").update(fields).eq("id", int(req_id)).execute()
    except Exception as ex:  # noqa: BLE001
        if status != "rejected":
            raise
        logger.info("[safe.db] stato 'rejected' non ammesso dal DB (%s): ripiego su 'error'",
                    str(ex)[:120])
        fields["status"] = "error"
        fields["result"] = {**(result or {}), "rejected": True}
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


def purge_opportunities(older_than_iso: str) -> None:
    """Cancella le righe di opportunità non aggiornate da prima di ``older_than_iso``:
    una partita finita non è più un'opportunità (11/09: 89 righe, metà del giorno
    prima, restavano in tabella per sempre e la UI le mostrava come attuali)."""
    try:
        (
            _sb().table("safe_strategy_opportunities").delete()
            .lt("updated_at", str(older_than_iso)).execute()
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.db] purge opportunità KO: %s", str(ex)[:160])


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
