"""omega_db — I/O Supabase per Omega (service_role, bypassa RLS).

Il servizio locale legge ``omega_control`` (singleton, id=1) per stato/parametri
e scrive ``omega_trades`` (mirror dei lay) + ``omega_activity`` (log). La UI legge
gli stessi dati via RPC owner-only (migrations/omega_bot.sql).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from db_client import get_supabase_client

logger = logging.getLogger("omega.db")

CONTROL_ID = 1


_MONEY_HINTS = ("realized", "liability", "locked", "pnl", "profit")


def _is_money_key(key: str) -> bool:
    """Chiavi degli aggregati che sono IMPORTI (euro): restano float. Le altre
    (conteggi) tornano int. Regola per nome: `locked_pnl_open_today`,
    `reconciling_liability`, `realized_*`… non perdono mai i centesimi."""
    k = str(key).lower()
    return any(h in k for h in _MONEY_HINTS)


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
    """Righe di ``omega_trades`` (opzionalmente per status), PAGINATE.

    AUDIT 11/09 (L-06): PostgREST tronca in silenzio a max-rows (1000) — con la
    tabella che cresce ~200 righe/giorno, dopo ~5 giorni ``list_trades(None)``
    (usata dal fallback degli aggregati e dal settlement) perdeva righe:
    posizioni vive invisibili = liability sottostimata. Si pagina per id e si
    riordina per placed_at (l'ordine atteso dai chiamanti)."""
    rows = _select_all("omega_trades", "*",
                       build=(lambda q: q.eq("status", status)) if status else None)
    # review L2: ordine per ISTANTE, non per stringa ('...Z' vs '...+00:00' e i
    # fusi diversi si ordinavano male; una riga senza placed_at finiva in testa).
    return sorted(rows, key=lambda r: (_ts_key(r.get("placed_at")), int(r.get("id") or 0)))


_TS_FAR_FUTURE = 4102444800.0   # 2100-01-01: le righe senza data vanno IN CODA


def _ts_key(v: Any) -> float:
    """Epoch di un timestamp ISO per l'ORDINAMENTO (review L2). Valore mancante o
    non parsabile → in coda (non in testa: una riga rotta non deve sembrare la
    più vecchia)."""
    if not v:
        return _TS_FAR_FUTURE
    try:
        txt = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError):
        return _TS_FAR_FUTURE


def failed_legs(since_iso: Optional[str] = None) -> dict[tuple[str, str], tuple[int, float]]:
    """``(event_id, gamba) → (quante volte è fallita, epoch dell'ultimo tentativo)``
    dalle righe con ``meta.leg_failed`` (esiti CERTI negativi: FOK ucciso, paper
    senza fill, richiesta di coda mai creata).

    review H4: il budget dei tentativi di gamba (3× a ≥30 s) stava SOLO in memoria
    — dopo l'esclusione di ``meta.leg_failed`` dall'unique (v5) un riavvio del
    servizio azzerava il contatore e la stessa gamba poteva essere ritentata
    all'infinito. Query FILTRATA (poche righe, indice ``idx_omega_trades_leg_failed``
    della migrazione v5): nessuna lettura in più della tabella intera."""
    def build(q):
        q = q.eq("meta->>leg_failed", "true")
        return q.gte("placed_at", since_iso) if since_iso else q

    try:
        rows = _select_all("omega_trades", "id,event_id,phase,closes_trade_id,placed_at,meta",
                           build=build)
    except Exception as ex:  # noqa: BLE001 — senza il DB resta il conteggio in memoria
        logger.warning("[omega.db] failed_legs KO: %s", str(ex)[:120])
        return {}
    out: dict[tuple[str, str], tuple[int, float]] = {}
    for r in rows or []:
        if r.get("closes_trade_id"):
            continue                       # una chiusura non è una gamba d'ingresso
        meta = r.get("meta") or {}
        if not meta.get("leg_failed"):
            continue                       # difesa se il filtro lato DB non è disponibile
        ph = r.get("phase")
        key = (str(r.get("event_id") or ""), str(ph) if ph in ("ht_cs", "ft_cs") else "")
        ts = _ts_key(meta.get("error_at") or meta.get("no_fill_at") or r.get("placed_at"))
        if ts >= _TS_FAR_FUTURE:
            ts = 0.0
        n, last = out.get(key, (0, 0.0))
        out[key] = (n + 1, max(last, ts))
    return out


def _select_all(table: str, columns: str, build=None, page: int = 1000) -> list[dict[str, Any]]:
    """Lettura PAGINATA per id (PostgREST tronca a max-rows=1000 in silenzio —
    review C3: dopo ~10 giorni il set di idempotenza delle gambe si troncava)."""
    out: list[dict[str, Any]] = []
    start = 0
    while True:
        q = _sb().table(table).select(columns)
        if build is not None:
            q = build(q)
        chunk = q.order("id").range(start, start + page - 1).execute().data or []
        out.extend(chunk)
        if len(chunk) < page:
            return out
        start += page


def traded_event_ids() -> set[str]:
    """event_id già piazzati (idempotenza I1). Le righe con ``meta.leg_failed``
    (esito CERTO negativo: nessun ordine reale è mai esistito) NON contano —
    altrimenti un FOK ucciso brucerebbe l'evento per tutta la partita
    (AUDIT 11/09 H-13)."""
    rows = _select_all("omega_trades", "id,event_id,meta")
    return {str(r["event_id"]) for r in rows
            if r.get("event_id") and not (r.get("meta") or {}).get("leg_failed")}


def manual_event_ids(since_iso: Optional[str] = None) -> set[str]:
    """event_id con almeno un trade MANUALE vivo o regolato (non 'error'): l'evento
    è territorio dell'utente, l'automatico non aggiunge esposizione (§8, review H2).
    ``since_iso``: solo righe piazzate da allora (finestra operativa, MEDIUM-2)."""
    def build(q):
        q = q.eq("origin", "manual").neq("status", "error")
        return q.gte("placed_at", since_iso) if since_iso else q
    rows = _select_all("omega_trades", "id,event_id", build=build)
    return {str(r["event_id"]) for r in rows if r.get("event_id")}


def traded_legs(since_iso: Optional[str] = None) -> set[tuple[str, str]]:
    """(event_id, gamba) già riservati/piazzati (v2, idempotenza per gamba).
    I trade senza gamba (motore v1, o manuali senza fase) valgono per ENTRAMBE:
    mai una seconda esposizione automatica su un evento già in posizione."""
    # ANCHE le righe in 'error' contano (§16): l'unique del DB uq_omega_trades_auto_leg
    # non le esclude — una gamba automatica andata in errore (ordine reale a esito
    # ignoto) NON si ripiazza sullo stesso evento; prima il servizio ci riprovava a
    # ogni ciclo e il DB rifiutava l'insert (un errore loggato ogni 5 s per tutta
    # la partita).
    # ECCEZIONE (AUDIT 11/09 H-13): le righe con ``meta.leg_failed`` sono esiti
    # CERTI negativi (FOK ucciso, paper senza fill, richiesta mai creata) — nessun
    # ordine reale esiste, la gamba è ritentabile col budget di _leg_retry_allowed.
    # L'unique le esclude dalla migrazione omega_models_v5.sql: senza quella
    # migrazione l'insert viene rifiutato e il ciclo logga 'already_reserved'
    # (comportamento di oggi, nessun danno).
    rows = _select_all("omega_trades", "id,event_id,phase,closes_trade_id,meta",
                       build=(lambda q: q.gte("placed_at", since_iso)) if since_iso else None)
    out: set[tuple[str, str]] = set()
    for r in rows or []:
        if r.get("closes_trade_id"):
            continue
        if (r.get("meta") or {}).get("leg_failed"):
            continue
        eid = str(r.get("event_id") or "")
        if not eid:
            continue
        ph = r.get("phase")
        if ph in ("ht_cs", "ft_cs"):
            out.add((eid, ph))
        elif ph is None:
            out.update({(eid, "ht_cs"), (eid, "ft_cs")})
    return out


def open_trades() -> list[dict[str, Any]]:
    return list_trades(status="open")


def get_trade(trade_id: int) -> Optional[dict[str, Any]]:
    """Una singola riga per id (cash-out: serve il trade da chiudere)."""
    rows = (
        _sb().table("omega_trades").select("*")
        .eq("id", int(trade_id)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def hedged_trades() -> list[dict[str, Any]]:
    """Gambe CHIUSE a mercato (cash-out/green-up, migrations/omega_cashout.sql):
    il P&L è bloccato ma NON ancora realizzato — si regolano insieme alla loro
    gamba di chiusura quando il mercato si chiude."""
    return list_trades(status="hedged")


def closing_trades_for(trade_ids: list[int]) -> list[dict[str, Any]]:
    """Righe di CHIUSURA (``closes_trade_id``) delle aperture indicate."""
    if not trade_ids:
        return []
    out: list[dict[str, Any]] = []
    ids = [int(i) for i in trade_ids]
    for i in range(0, len(ids), 200):          # URL corta e nessun troncamento (review M13)
        chunk = ids[i:i + 200]
        out.extend(_select_all("omega_trades", "*", build=lambda q, ch=chunk: q.in_("closes_trade_id", ch)))
    return out


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
    # §14 (11/09): ``id`` + ``closes_trade_id`` servono per (a) escludere le gambe
    # di chiusura dai conteggi partita/liability e (b) attribuire il loro P&L al
    # GIORNO dell'apertura che chiudono (giornata = partite di quel giorno).
    # VELOCE (§14): i numeri li calcola il DB in UNA query (RPC get_omega_aggregates,
    # migrazione omega_daily_v2) — nessuna lettura di tutta la tabella ogni ciclo.
    # Fallback al percorso legacy solo se la RPC non esiste ancora.
    if day_start is not None:
        try:
            res = _sb().rpc("get_omega_aggregates", {}).execute()
            data = getattr(res, "data", None)
            if isinstance(data, dict) and "realized_today" in data:
                # i campi in EURO restano float (AUDIT 11/09: locked_pnl_open e
                # reconciling_liability sono importi — con int() si perdevano i
                # centesimi e un −0,80 bloccato diventava 0)
                # (§17 review: anche ``locked_pnl_open_today``; regola per NOME, così
                # una chiave nuova in euro non torna mai intera per sbaglio)
                return {k: (float(v) if _is_money_key(k) else int(v))
                        for k, v in data.items() if v is not None}
        except Exception as ex:  # noqa: BLE001 - RPC assente (migrazione) o DB KO → legacy
            logger.debug("[omega.db] get_omega_aggregates KO → legacy: %s", str(ex)[:120])
    # LEGACY, PAGINATO: PostgREST tronca a max-rows (1000) — una pagina persa farebbe
    # attribuire il P&L delle chiusure al giorno sbagliato (review 11/09 MED-2)
    rows: list[dict[str, Any]] = []
    page = 1000
    start = 0
    while True:
        chunk = (
            _sb().table("omega_trades")
            .select("id,status,pnl,liability,bet_id,placed_at,settled_at,meta,mode,closes_trade_id")
            .order("id").range(start, start + page - 1)
            .execute().data or []
        )
        rows.extend(chunk)
        if len(chunk) < page:
            break
        start += page
    from Betfair.omega import omega_engine as E

    return E.aggregate_trades(rows, day_start)  # logica PURA e testata (§I8: pending+bet_id contano)


# ---------------------------------------------------------------------------
# §14 (11/09): due gambe SEMPRE, giornata = partite del giorno, risultati reali.
# Tutte best-effort e tolleranti alla migrazione ``omega_daily_v2.sql`` non
# ancora applicata (colonna/tabella/RPC assenti → None/[]/no-op, mai un crash).
# ---------------------------------------------------------------------------
def event_lambda_hint(event_id: str) -> Optional[dict[str, Any]]:
    """λ pre-match già calcolati per l'evento e salvati sul blocco ``meta.model``
    di un trade precedente (tipicamente la gamba 1T): ``{lambda_pre, lambda_source}``.
    Sopravvive ai riavvii del servizio e dello scanner. None se nessuno."""
    try:
        rows = (
            _sb().table("omega_trades").select("id,meta")
            .eq("event_id", str(event_id)).neq("status", "error")
            .order("id", desc=True).limit(5).execute().data or []
        )
    except Exception as ex:  # noqa: BLE001
        logger.debug("[omega.db] event_lambda_hint KO %s: %s", event_id, str(ex)[:120])
        return None
    for r in rows:
        model = (r.get("meta") or {}).get("model")
        lam = model.get("lambda_pre") if isinstance(model, dict) else None
        if isinstance(lam, (list, tuple)) and len(lam) == 2:
            return {"lambda_pre": [lam[0], lam[1]], "lambda_source": model.get("lambda_source")}
    return None


def save_event_model(event_id: str, model: dict[str, Any]) -> bool:
    """Persiste i λ risolti sulla cache eventi (``omega_events.model``, colonna
    della migrazione omega_daily_v2). UPDATE (mai insert): se la riga o la
    colonna mancano non succede nulla. True se scritto."""
    try:
        res = (
            _sb().table("omega_events").update({"model": model})
            .eq("event_id", str(event_id)).execute()
        )
        return bool(res.data)
    except Exception as ex:  # noqa: BLE001 - colonna assente (migrazione) o DB KO
        logger.debug("[omega.db] save_event_model KO %s: %s", event_id, str(ex)[:120])
        return False


def positions_for_results(since_iso: str) -> list[dict[str, Any]]:
    """Aperture recenti (piazzate da ``since_iso``, mai gambe di chiusura, mai
    'error') con il meta: servono a scrivere i risultati reali 1T/2T."""
    try:
        return (
            _sb().table("omega_trades")
            .select("id,event_id,phase,status,placed_at,meta,closes_trade_id")
            .is_("closes_trade_id", "null").neq("status", "error")
            .gte("placed_at", since_iso).order("placed_at", desc=True).limit(500).execute().data or []
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("[omega.db] positions_for_results KO: %s", str(ex)[:120])
        return []


def upsert_daily_goal(day: str, goal: float) -> bool:
    """Snapshot dell'obiettivo della GIORNATA (tabella ``omega_daily_goal``):
    lo storico mostra l'obiettivo che valeva quel giorno, non quello corrente."""
    try:
        _sb().table("omega_daily_goal").upsert(
            {"day": str(day), "goal": float(goal),
             "updated_at": datetime.now(timezone.utc).isoformat()}, on_conflict="day"
        ).execute()
        return True
    except Exception as ex:  # noqa: BLE001 - tabella assente (migrazione) o DB KO
        logger.debug("[omega.db] upsert_daily_goal KO %s: %s", day, str(ex)[:120])
        return False


def ht_ft_transitions(league_id: Optional[int]) -> Optional[list[dict[str, Any]]]:
    """Righe ``{league_id, ht, ft, n}`` della tabella HT→FT (globale + lega) via
    RPC ``get_omega_ht_ft``. [] = tabella vuota; None = ERRORE (timeout/RPC assente):
    il chiamante non deve mettere in cache un errore (review M2)."""
    try:
        res = _sb().rpc("get_omega_ht_ft", {"p_league_id": int(league_id) if league_id is not None else None}).execute()
        data = getattr(res, "data", None)
        return list(data) if isinstance(data, list) else []
    except Exception as ex:  # noqa: BLE001
        logger.warning("[omega.db] ht_ft_transitions KO (%s): %s", league_id, str(ex)[:120])
        return None


def minute_transitions(league_id: Optional[int], bucket: int, target: str) -> Optional[list[dict[str, Any]]]:
    """Righe ``{league_id, bucket, score, target, result, n}`` della tabella PER
    MINUTO (globale + lega, un bucket, un target) via RPC ``get_omega_minute_ft``
    (migrazione omega_models_v3.sql). [] = vuota; None = ERRORE (mai in cache)."""
    try:
        res = _sb().rpc("get_omega_minute_ft", {
            "p_league_id": int(league_id) if league_id is not None else None,
            "p_bucket": int(bucket), "p_target": str(target),
        }).execute()
        data = getattr(res, "data", None)
        return list(data) if isinstance(data, list) else []
    except Exception as ex:  # noqa: BLE001
        logger.warning("[omega.db] minute_transitions KO (%s,%s,%s): %s", league_id, bucket, target, str(ex)[:120])
        return None
