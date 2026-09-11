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

# memo: la RPC degli aggregati esiste solo dopo mike_bot_v2.sql — se manca si
# ripiega UNA volta e non si riprova a ogni ciclo (H5: niente errori a raffica)
_AGG_RPC: dict[str, bool] = {}
# cache dei cumulativi di sempre (realized_total/won/lost) per il fallback H5
_TOTALS: dict[str, Any] = {}
_TOTALS_TTL_S = 300.0


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


def open_trades(page_size: int = PAGE_SIZE) -> list[dict[str, Any]]:
    """Righe non terminali, PAGINATE (L1: oltre 1000 righe Supabase troncava in
    silenzio e la riconciliazione avrebbe visto gambe "senza riga")."""
    out: list[dict[str, Any]] = []
    start = 0
    while True:
        chunk = (_sb().table(T_TRADES).select("*").in_("status", ["open", "hedged", "pending"])
                 .order("id", desc=False).range(start, start + page_size - 1).execute().data or [])
        out.extend(chunk)
        if len(chunk) < page_size:
            return out
        start += page_size


def trades_for_event(event_id: str) -> list[dict[str, Any]]:
    return (_sb().table(T_TRADES).select("*").eq("event_id", str(event_id))
            .order("placed_at", desc=False).execute().data or [])


def live_trades(since_iso: Optional[str] = None) -> list[dict[str, Any]]:
    """Righe che il ciclo deve davvero guardare (H5): quelle NON terminali
    (pending/open/hedged) piu' quelle regolate DOPO ``since_iso``. Niente piu'
    lettura integrale di ``mike_trades`` a ogni giro (IO exhaustion Supabase).

    Include anche le APERTURE delle righe regolate nella finestra (una chiusura
    eredita il giorno operativo della sua apertura, M6): senza, l'attribuzione
    del giorno userebbe il piazzamento della chiusura."""
    sb = _sb()
    rows = open_trades()
    seen = {r.get("id") for r in rows}
    if since_iso:
        recent = (sb.table(T_TRADES).select("*").gte("settled_at", str(since_iso))
                  .order("placed_at", desc=False).execute().data or [])
        rows.extend(r for r in recent if r.get("id") not in seen)
        seen |= {r.get("id") for r in rows}
        parents = [r["closes_trade_id"] for r in rows
                   if r.get("closes_trade_id") and r["closes_trade_id"] not in seen]
        if parents:
            extra = (sb.table(T_TRADES).select("*").in_("id", list({int(p) for p in parents}))
                     .execute().data or [])
            rows.extend(r for r in extra if r.get("id") not in seen)
    return rows


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


def aggregate_rows(rows: list[dict[str, Any]], day_start: Optional[datetime] = None) -> dict[str, Any]:
    """Aggregazione PURA delle righe ``mike_trades``. Regole Mike:

    * M6 — la giornata operativa e' il giorno di PIAZZAMENTO (Europe/Rome) della
      POSIZIONE: una chiusura eredita il giorno della sua apertura
      (``closes_trade_id``), un regolamento notturno resta nel giorno in cui il
      trade e' stato aperto. Vale per KPI, regolate e storico (stesso criterio
      della RPC ``get_mike_daily`` con ``p_day_by='placed'``).
    * H4 — ``pnl`` di ogni riga e' NETTO commissione: si somma senza correzioni.
    * M4 — ``open_liability`` NON si somma dalle righe (un back coperto da lay
      non e' back+lay): la calcola il servizio dalle posizioni nette
      (``engine.event_liability``) e la passa in ``open_liability``.
    * C3 — una riga 'pending' con esito ignoto (``place_exception_reconciling``)
      conta come APERTA: potrebbe essere un ordine reale vivo.
    """
    from Betfair.safe_strategy import execution as _X

    by_id = {r.get("id"): r for r in rows}

    def _placed_at(r: dict[str, Any]) -> Any:
        parent = by_id.get(r.get("closes_trade_id")) if r.get("closes_trade_id") else None
        return (parent or r).get("placed_at")

    def _in_day(ts: Any) -> bool:
        if day_start is None:
            return True
        try:
            t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return False
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t >= day_start

    realized = realized_today = 0.0
    won = lost = won_today = lost_today = 0
    open_n = 0
    cycles_today = 0
    events_today: set[str] = set()
    total_by_position: dict[Any, float] = {}
    for r in rows:
        status = str(r.get("status") or "")
        pnl = float(r.get("pnl") or 0.0)
        is_closer = bool(r.get("closes_trade_id"))
        reconciling = status == "pending" and _X.is_reconciling(r)
        day = _in_day(_placed_at(r))
        if status in ("won", "lost", "void"):
            realized += pnl
            if day:
                realized_today += pnl
            pos = r.get("closes_trade_id") or r.get("id")
            total_by_position[pos] = total_by_position.get(pos, 0.0) + pnl
        elif status in ("open", "hedged") or reconciling:
            if not is_closer:
                open_n += 1
        if not is_closer and status != "error" and (status != "pending" or reconciling) and day:
            cycles_today += 1
            if r.get("event_id"):
                events_today.add(str(r.get("event_id")))
    for pos, tot in total_by_position.items():
        row = by_id.get(pos) or {}
        day = _in_day(row.get("placed_at"))
        if tot > 0:
            won += 1
            won_today += 1 if day else 0
        elif tot < 0:
            lost += 1
            lost_today += 1 if day else 0
    return {
        "realized_total": round(realized, 2), "realized_today": round(realized_today, 2),
        "open_count": open_n, "open_liability": 0.0,
        "won": won, "lost": lost, "won_today": won_today, "lost_today": lost_today,
        "cycles_today": cycles_today, "events_today": len(events_today),
    }


def aggregates(now: Optional[datetime] = None) -> dict[str, Any]:
    """Aggregati per le stats. Prima prova la RPC SQL (una query, nessuna
    paginazione: H5), poi ripiega sulla lettura incrementale + funzione pura —
    cosi' il servizio funziona anche a migrazione ``mike_bot_v2.sql`` non applicata."""
    from Betfair.safe_strategy import risk as _risk

    if not _AGG_RPC.get("missing"):
        try:
            res = _sb().rpc("get_mike_aggregates", {}).execute()
            data = getattr(res, "data", None)
            if isinstance(data, dict) and data:
                return data
        except Exception as ex:  # noqa: BLE001 — migrazione non applicata: fallback
            # una volta sola: niente errore a raffica a ogni ciclo
            _AGG_RPC["missing"] = True
            logger.warning("[mike.db] get_mike_aggregates non disponibile (migrazione "
                           "mike_bot_v2.sql non applicata): %s", str(ex)[:120])
    # Fallback (migrazione non applicata): H5 — finestra INCREMENTALE per tutto
    # cio' che riguarda la giornata e le posizioni aperte; i CUMULATIVI di sempre
    # (realized_total, won, lost) da una scansione completa rinfrescata al
    # massimo ogni _TOTALS_TTL_S. Prima era una lettura paginata integrale di
    # mike_trades 1-2 volte per ciclo.
    day_start = _risk.operating_day_start(now)
    agg = aggregate_rows(live_trades(day_start.isoformat()), day_start)
    agg.update(_cumulative_totals(day_start))
    agg["totals_from"] = "full_scan_cache"
    return agg


def _cumulative_totals(day_start: datetime) -> dict[str, Any]:
    """{realized_total, won, lost} di SEMPRE, da una scansione completa messa in
    cache per ``_TOTALS_TTL_S`` (l'unico dato non calcolabile da una finestra)."""
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _TOTALS.get("v")
    if cached is not None and now_ts - float(_TOTALS.get("ts") or 0.0) < _TOTALS_TTL_S:
        return cached
    full = aggregate_rows(all_trades(), day_start)
    v = {k: full[k] for k in ("realized_total", "won", "lost")}
    _TOTALS.update({"ts": now_ts, "v": v})
    return v


# ---------------------------------------------------------------------------
# Requests (comandi dalla UI)
# ---------------------------------------------------------------------------
def pending_requests(limit: int = 50) -> list[dict[str, Any]]:
    return (_sb().table(T_REQUESTS).select("*").eq("status", "pending")
            .order("created_at", desc=False).limit(int(limit)).execute().data or [])


def set_request_status(req_id: int, status: str, result: Optional[dict[str, Any]] = None) -> None:
    """M1: ogni richiesta viene CHIUSA con un esito leggibile.

    ``status='rejected'`` esiste solo dopo ``mike_bot_v2.sql``: a migrazione non
    applicata il CHECK lo rifiuta e si ripiega su 'error' (l'esito nel campo
    ``result`` resta identico, la UI mostra lo stesso messaggio)."""
    fields: dict[str, Any] = {"status": status, "updated_at": _now_iso()}
    if result is not None:
        fields["result"] = result
    try:
        _sb().table(T_REQUESTS).update(fields).eq("id", int(req_id)).execute()
    except Exception as ex:  # noqa: BLE001
        if status != "rejected":
            raise
        logger.warning("[mike.db] status 'rejected' non ammesso (migrazione v2 assente): %s",
                       str(ex)[:120])
        fields["status"] = "error"
        _sb().table(T_REQUESTS).update(fields).eq("id", int(req_id)).execute()


def fail_stale_processing(max_age_min: int = 10) -> int:
    """Richieste rimaste in 'processing' (crash del servizio dopo la presa in
    carico): chiuse in errore. M2 — va chiamata a OGNI ciclo, altrimenti un
    crash blocca per sempre il cash out di quella partita."""
    n = 0
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
                set_request_status(int(r["id"]), "error",
                                   {"code": "processing_stale",
                                    "message": "richiesta interrotta (servizio riavviato): riprova"})
                n += 1
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike.db] fail_stale_processing KO: %s", str(ex)[:120])
    return n


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
