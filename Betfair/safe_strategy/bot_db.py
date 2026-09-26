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
from Betfair.stream import canale_bot as _cb

logger = logging.getLogger("safe.bot.db")

# --- F3 (18/09): le righe che Safe scrive escono ANCHE sul canale 47335 ------
# Il database resta il registro: si pubblica DOPO la scrittura riuscita e si
# pubblica la riga che la scrittura ha RESTITUITO (PostgREST torna di serie la
# rappresentazione: nessuna lettura in piu'). Interruttore
# ``SAFE_CANALE_POSIZIONI`` nel ``.env``, DEFAULT SPENTO.
# Safe e' l'unico bot su DUE sport: calcio e tennis hanno topic SEPARATI e il
# topic lo decide il campo ``sport`` DELLA RIGA (invariante B12).
_CANALE_ACCESO = _cb.acceso(_cb.ENV_SAFE)

#: Dallo sport della riga al topic. Uno sport assente o sconosciuto non esce su
#: nessun topic: meglio nessun messaggio che il messaggio sul topic sbagliato.
_TOPIC_PER_SPORT = {
    "calcio": _cb.TOPIC["safe_posizioni_calcio"],
    "tennis": _cb.TOPIC["safe_posizioni_tennis"],
}


def _topic_posizione(riga: dict[str, Any]) -> Optional[str]:
    """Il topic di UNA riga di trade, deciso dal suo ``sport``."""
    return _TOPIC_PER_SPORT.get(str(riga.get("sport") or "").strip().lower())


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
        res = _sb().table("safe_strategy_activity").insert(
            {"kind": kind, "payload": payload or {}}
        ).execute()
        if _CANALE_ACCESO:      # F3: DOPO la scrittura riuscita, mai prima
            _cb.pubblica_scritte(_cb.TOPIC["safe_attivita"], res)
    except Exception as ex:  # noqa: BLE001 — il log non deve mai fermare il bot
        logger.warning("[safe.db] log '%s' fallito: %s", kind, str(ex)[:120])


# ---------------------------------------------------------------------------
# Trades (mirror)
# ---------------------------------------------------------------------------
def insert_trade(trade: dict[str, Any]) -> Optional[int]:
    res = _sb().table("safe_strategy_trades").insert(trade).execute()
    if _CANALE_ACCESO:          # F3: DOPO la scrittura riuscita, mai prima
        _cb.pubblica_scritte_per(_topic_posizione, res)
    rows = res.data or []
    return rows[0].get("id") if rows else None


def update_trade(trade_id: int, **fields: Any) -> None:
    if not fields:
        return
    res = _sb().table("safe_strategy_trades").update(fields).eq("id", int(trade_id)).execute()
    if _CANALE_ACCESO:          # F3: la riga INTERA come il database l'ha scritta
        _cb.pubblica_scritte_per(_topic_posizione, res)


def delete_trade(trade_id: int) -> None:
    """Elimina SOLO una riserva ancora 'pending' (mai una posizione reale)."""
    res = (
        _sb().table("safe_strategy_trades").delete()
        .eq("id", int(trade_id)).eq("status", "pending").execute()
    )
    # C6(c): la sparizione della riserva esce SUBITO sul canale (prima la
    # vedeva solo il poll a 30s). Lo sport della riga decide il topic, come
    # per insert/update (invariante B12: calcio e tennis non si mischiano).
    if _CANALE_ACCESO:
        _cb.pubblica_cancellazione_per(_topic_posizione, res)


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


# ---------------------------------------------------------------- modalita'
# CERT. 13/09 — SEPARAZIONE NETTA PAPER / LIVE.
# La colonna ``mode`` esisteva dal primo giorno e non la leggeva NESSUNA query:
# P&L, KPI, storico, cap di rischio e idempotenza mescolavano le posizioni finte
# con quelle vere. Conseguenze reali, tutte e due pericolose:
#   · una settimana di paper vincente gonfia il "P&L totale" di un conto che non
#     ha guadagnato un euro;
#   · una giornata paper negativa consuma ``daily_loss_stop`` e FERMA il live —
#     e, al contrario, profitti paper possono mascherare perdite vere e tenere
#     aperto il rubinetto.
# Da qui in poi ogni lettura che alimenta numeri o decisioni accetta ``mode``.
# ``mode=None`` = tutte le modalita' (usato solo dove serve davvero, es. il
# settlement, che deve regolare anche le posizioni della modalita' non attiva).
_VALID_MODES = ("paper", "live")


def _norm_mode(mode: Optional[str]) -> Optional[str]:
    """Modalita' normalizzata, o None se assente/non valida (= nessun filtro)."""
    m = str(mode or "").strip().lower()
    return m if m in _VALID_MODES else None


def row_mode(row: dict[str, Any]) -> str:
    """Modalita' della riga. Una riga senza ``mode`` e' trattata come LIVE:
    fail-safe: meglio contarla fra i soldi veri (e vederla nei cap) che
    nasconderla fra quelli finti."""
    return _norm_mode(row.get("mode")) or "live"


def open_trades(mode: Optional[str] = None) -> list[dict[str, Any]]:
    """Posizioni vive: 'open' e 'hedged' (chiuse a mercato ma non ancora
    regolate — il P&L si realizza quando il mercato si chiude).

    ``mode`` filtra paper/live: passarlo quando il risultato alimenta i cap di
    rischio o i numeri a schermo, ometterlo quando serve gestire TUTTE le
    posizioni vive (uscite e settlement di entrambe le modalita')."""
    q = (
        _sb().table("safe_strategy_trades").select("*")
        .in_("status", ["open", "hedged"])
    )
    m = _norm_mode(mode)
    if m:
        q = q.eq("mode", m)
    return q.order("placed_at", desc=False).execute().data or []


def trades_pending_o_aperti(mode: Optional[str] = None) -> list[dict[str, Any]]:
    """Trade 'pending' o 'open' (QUALUNQUE origine, anche 'manual'): sono gli
    ordini ancora vivi sul mercato. 18/09 — ORDINE DELL'UTENTE («se ho
    approvato o rifiutato un segnale deve essere coerente con gli ordini»):
    una proposta di opportunita' (modello/tennis/anomalia/combo) approvata e
    ancora viva (in coda o abbinata, non ancora regolata) NON deve tornare a
    proporsi — vedi ``bot_service._opp_keys_con_ordine_vivo``, che filtra
    queste righe per ``meta.opp_key``.

    Diversa da ``open_trades()`` (che torna SOLO 'open'/'hedged', per il
    contesto di rischio): qui serve anche 'pending' — un ordine mandato in
    coda flumine e non ancora confermato e' vivo a tutti gli effetti, e
    ``open_trades()`` non lo vedrebbe."""
    q = (
        _sb().table("safe_strategy_trades").select("*")
        .in_("status", ["pending", "open"])
    )
    m = _norm_mode(mode)
    if m:
        q = q.eq("mode", m)
    return q.order("placed_at", desc=False).execute().data or []


def trades_for_event(event_id: str) -> list[dict[str, Any]]:
    """TUTTE le righe di UNA partita, ogni stato, gambe di chiusura comprese.

    Serve al cash-out globale e al «Riprendi»: quelli ragionano per PARTITA e
    devono vedere anche le riserve 'pending' (che ``open_trades`` non torna) e
    le righe gia' regolate (che portano il marcatore). E' una query per
    ``event_id``, non la tabella intera: ``list_trades()`` non e' paginata e
    oltre 1000 righe ne perderebbe in silenzio — cioe' il cash-out globale
    lascerebbe fuori proprio le posizioni che deve chiudere."""
    return _fetch_all(lambda: (
        _sb().table("safe_strategy_trades").select("*")
        .eq("event_id", str(event_id)).order("id", desc=False)
    ))


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


def trade_by_idempotency_key(key: str, mode: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Trade NON in errore con ``meta.idempotency_key == key`` (dedupe del manuale).

    Il dedupe e' PER MODALITA': senza il filtro, un "Investi" gia' fatto in
    paper faceva rispondere ``deduplicated: true`` con l'id del trade PAPER a
    chi premeva lo stesso bottone in LIVE — la UI diceva "fatto" e in banca non
    succedeva nulla."""
    q = (
        _sb().table("safe_strategy_trades").select("id,status,meta,mode")
        .contains("meta", {"idempotency_key": str(key)})
        .neq("status", "error")
    )
    m = _norm_mode(mode)
    if m:
        q = q.eq("mode", m)
    rows = q.limit(1).execute().data or []
    return rows[0] if rows else None


def traded_signal_keys(mode: Optional[str] = None) -> set[tuple[str, str]]:
    """(event_id, signal_key) già riservati/piazzati dall'AUTOMATICO: idempotenza
    per segnale (le righe 'error' non bloccano il ripiazzamento). Paginata:
    oltre ~1000 righe una SELECT nuda perderebbe chiavi → doppi piazzamenti.

    PER MODALITA' (13/09): senza filtro, passando da paper a live il bot vero
    saltava in silenzio TUTTI i segnali gia' provati in paper — cioe' non
    entrava su niente di quello che aveva appena finito di collaudare."""
    m = _norm_mode(mode)

    def _q():
        q = (
            _sb().table("safe_strategy_trades").select("event_id,signal_key")
            .eq("origin", "auto").neq("status", "error")
            # allineato all'indice unico del DB ``uq_safe_trades_signal``, che
            # e' parziale anche su ``closes_trade_id IS NULL``: i due guardiani
            # dello stesso invariante devono filtrare le STESSE righe, altrimenti
            # una gamba di chiusura che eredita il ``signal_key`` del padre
            # risulterebbe "gia' tradata" per Python e libera per il DB.
            .is_("closes_trade_id", "null")
        )
        if m:
            q = q.eq("mode", m)
        return q.order("id", desc=False)

    rows = _fetch_all(_q)
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

#: i numeri su cui i CAP DEL BOT decidono: gli stessi, contati sulle sole
#: posizioni del bot (16/09). La RPC li porta solo con la migrazione
#: ``safe_strategy_cap_solo_automatico_2026-09-16.sql``: finche' non e'
#: applicata, la scansione Python li calcola comunque e il servizio ripiega
#: sui completi (piu' alti, quindi piu' prudenti).
_AGG_KEYS_AUTO = tuple(f"{k}_auto" for k in _AGG_KEYS)


def aggregates(now: Optional[datetime] = None,
               mode: Optional[str] = None) -> dict[str, float]:
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
    m = _norm_mode(mode)
    if now_ts - float(_AGG_RPC["ko_ts"]) >= _AGG_RPC_RETRY_S:
        try:
            # con una modalita' richiesta la RPC DEVE accettarla: se la
            # migrazione non e' applicata la vecchia firma solleva e si ripiega
            # sulla scansione filtrata. MAI accettare un aggregato non filtrato
            # spacciandolo per quello della modalita' chiesta (sommerebbe paper
            # e live in un unico P&L, che e' il difetto che stiamo chiudendo).
            res = _sb().rpc("get_safe_aggregates", {"p_mode": m} if m else {}).execute()
            data = getattr(res, "data", None)
            if isinstance(data, dict) and "open_liability" in data:
                _AGG_RPC["ko_ts"] = 0.0
                out = {k: data.get(k, 0) for k in _AGG_KEYS}
                # i numeri "solo bot" solo se la RPC li porta davvero: mai un
                # campo inventato a zero, che spegnerebbe i cap in silenzio
                out.update({k: data[k] for k in _AGG_KEYS_AUTO if k in data})
                return out
            logger.info("[safe.db] get_safe_aggregates risposta inattesa (%s): "
                        "scansione Python", type(data).__name__)
        except Exception as ex:  # noqa: BLE001 — migrazione non applicata / RPC KO
            logger.info("[safe.db] get_safe_aggregates non disponibile (%s): scansione Python",
                        str(ex)[:120])
        # L3: si arriva qui SOLO se la RPC non ha dato un risultato usabile
        # (eccezione O risposta non-dict): in entrambi i casi si apre la finestra
        # di attesa, altrimenti ogni ciclo (2 s) pagherebbe un round-trip inutile
        _AGG_RPC["ko_ts"] = now_ts
    def _q():
        q = (
            _sb().table("safe_strategy_trades")
            .select("id,event_id,status,pnl,liability,settled_at,placed_at,strategy,"
                    "bet_id,meta,closes_trade_id,mode,origin")
        )
        if m:
            q = q.eq("mode", m)
        return q.order("id", desc=False)

    rows = _fetch_all(_q)
    return aggregate_rows(rows, day_start=_risk.operating_day_start(now))


def open_trades_auto(mode: Optional[str] = None) -> list[dict[str, Any]]:
    """Le posizioni vive DEL BOT (``origin='auto'``): quelle su cui i cap
    contano. Le manuali del trader restano in ``open_trades`` per i numeri di
    pagina e per la protezione, ma non entrano nei tetti del bot."""
    return [t for t in open_trades(mode)
            if str(t.get("origin") or "auto").lower() != "manual"]


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


def righe_del_bot(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Le righe che appartengono alle POSIZIONI DEL BOT: le aperture
    ``origin='auto'`` e TUTTE le loro gambe di chiusura, qualunque sia
    l'origine della chiusura.

    ⚠️ ORDINE DELL'UTENTE 16/09 h18 — «il bot gestisce le SUE operazioni e
    ignora le mie manuali». I cap del bot devono contare il bot: fino a ieri
    ``aggregate_rows`` non guardava ``origin`` e le righe che il trader apriva
    a mano dalla scheda entravano nella responsabilita' di giornata e nei cap
    (misurati 32,80 EUR di responsabilita' manuale dentro i cap del bot).
    La gamba di chiusura MANUALE di una posizione AUTOMATICA resta dentro: e'
    il cash-out che il trader ha fatto SULLA posizione del bot, e il suo P&L e'
    P&L del bot. Escluderla darebbe un realizzato falso."""
    # ``origin`` e' NOT NULL DEFAULT 'auto' nel database: una riga senza origine
    # e' del bot per costruzione, e in dubbio la si CONTA nei cap.
    auto_ids = {r.get("id") for r in rows or []
                if not r.get("closes_trade_id")
                and str(r.get("origin") or "auto").lower() != "manual"
                and r.get("id") is not None}
    out: list[dict[str, Any]] = []
    for r in rows or []:
        pid = r.get("closes_trade_id")
        if pid is None:
            if str(r.get("origin") or "auto").lower() != "manual":
                out.append(r)
            continue
        if pid in auto_ids:
            out.append(r)
    return out


def aggregate_rows(rows: list[dict[str, Any]], day_start: Optional[datetime] = None,
                   mode: Optional[str] = None) -> dict[str, float]:
    """I numeri della Safe, in DUE serie sugli stessi trade.

    · chiavi SENZA suffisso = TUTTO (bot + operazioni manuali del trader): sono
      i totali di pagina, e restano completi — il trader vuole vedere anche le
      sue;
    · chiavi con suffisso ``_auto`` = SOLO le posizioni del bot
      (``righe_del_bot``): sono quelle su cui i CAP decidono.
    Due serie dichiarate, mai una sola mescolata: e' la stessa lezione della
    separazione paper/live del 13/09."""
    completi = _aggrega(rows, day_start, mode)
    _m = _norm_mode(mode)
    righe = [r for r in (rows or []) if row_mode(r) == _m] if _m else list(rows or [])
    solo_bot = _aggrega(righe_del_bot(righe), day_start, None)
    return {**completi, **{f"{k}_auto": v for k, v in solo_bot.items()}}


def _aggrega(rows: list[dict[str, Any]], day_start: Optional[datetime] = None,
             mode: Optional[str] = None) -> dict[str, float]:
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
    # CERT. 13/09 — filtro di MODALITA' prima di ogni conteggio: un P&L che
    # somma paper e live e' una bugia, e un cap giornaliero consumato da
    # posizioni finte blocca quelle vere.
    _m = _norm_mode(mode)
    if _m:
        rows = [r for r in rows if row_mode(r) == _m]
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


REQUEST_STATES = ("proposed", "pending", "processing", "done", "rejected", "error")


def richiesta_per_id(request_id: int) -> Optional[dict[str, Any]]:
    """UNA richiesta per id (sola lettura): serve a sapere com'e' finita una
    proposta di copertura (rifiutata, approvata, decaduta) - 24/09."""
    rows = (
        _sb().table("safe_strategy_requests").select("id,kind,status,result")
        .eq("id", int(request_id)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def proposta_di_chiusura_viva(trade_id: int) -> Optional[dict[str, Any]]:
    """La proposta di chiusura ancora IN ATTESA DI APPROVAZIONE per questo trade.

    Serve a non creare un duplicato a ogni ciclo: finche' la condizione di
    uscita regge, la proposta e' UNA e si aggiorna (prezzo, liquidita', motivo).
    E' quello che la rende viva sotto gli occhi di chi deve decidere."""
    rows = (
        _sb().table("safe_strategy_requests").select("*")
        .eq("status", "proposed").eq("payload->>trade_id", str(int(trade_id)))
        .limit(1).execute().data or []
    )
    return rows[0] if rows else None


def scrivi_proposta_di_chiusura(trade_id: int, payload: dict[str, Any]) -> Optional[int]:
    """Crea o AGGIORNA la proposta di chiusura di ``trade_id``.

    Non passa da ``safe_request``: quella nasce 'pending' ed e' per le richieste
    manuali dell'utente, che vanno eseguite subito. Questa nasce 'proposed' e
    resta ferma finche' un essere umano non la promuove.
    Ritorna l'id, oppure None se la scrittura non e' riuscita (il chiamante NON
    deve interpretarlo come "proposta fatta": senza id non c'e' proposta)."""
    corpo = {**payload, "trade_id": int(trade_id)}
    viva = proposta_di_chiusura_viva(trade_id)
    if viva is not None:
        res = (
            _sb().table("safe_strategy_requests")
            .update({"payload": corpo, "updated_at": _now_iso()})
            .eq("id", int(viva["id"])).execute()
        )
        if _CANALE_ACCESO:      # F3: la proposta VIVA, aggiornata, sullo schermo
            _cb.pubblica_scritte(_cb.TOPIC["safe_proposta"], res)
        return int(viva["id"])
    res = (
        _sb().table("safe_strategy_requests")
        .insert({"kind": "cashout", "status": "proposed", "payload": corpo}).execute()
    )
    if _CANALE_ACCESO:          # F3: DOPO la scrittura riuscita, mai prima
        _cb.pubblica_scritte(_cb.TOPIC["safe_proposta"], res)
    dati = getattr(res, "data", None) or []
    return int(dati[0]["id"]) if dati and dati[0].get("id") is not None else None


def chiudi_proposta(trade_id: int, motivo: str) -> None:
    """La condizione di uscita non regge piu': la proposta viva decade.

    Non e' un rifiuto dell'utente — e' il mercato che e' cambiato. Si marca
    'rejected' col motivo, cosi' resta la traccia di una chiusura PROPOSTA e mai
    avvenuta: senza, sparirebbe e nessuno saprebbe che era stata offerta."""
    viva = proposta_di_chiusura_viva(trade_id)
    if viva is None:
        return
    res = (
        _sb().table("safe_strategy_requests")
        .update({"status": "rejected",
                 "result": {**(viva.get("result") or {}), "decaduta": True,
                            "motivo": str(motivo)[:200]},
                 "updated_at": _now_iso()})
        .eq("id", int(viva["id"])).execute()
    )
    if _CANALE_ACCESO:          # F3: la proposta decaduta sparisce anche a video
        _cb.pubblica_scritte(_cb.TOPIC["safe_proposta"], res)


# ---------------------------------------------------------------------------
# PROPOSTE DI OPPORTUNITA' DI MODELLO (17/09) — stessa coda, stesso cancelletto
#
# Una proposta e' una riga 'proposed' con kind='place' e ``payload.opp_key``.
# Le proposte di CHIUSURA (14/09) sono kind='cashout': i due mondi non si
# toccano, e la Control Room li distingue dalla presenza di ``opp_key``.
# ---------------------------------------------------------------------------
def proposte_opportunita(ore: int = 24, limit: int = 300) -> list[dict[str, Any]]:
    """Proposte di opportunita' VIVE ('proposed') e gia' DECISE ('rejected')
    delle ultime ``ore``.

    Le rifiutate servono quanto le vive: una proposta che l'utente ha scartato
    non deve tornare finche' la chiave resta uguale, e senza rileggerle il
    servizio la riscriverebbe al ciclo dopo — cioe' il rifiuto non esisterebbe.
    Una sola SELECT per ciclo (13/09: il DB ha un budget di IO)."""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=int(ore))).isoformat()
    righe = (
        _sb().table("safe_strategy_requests").select("*")
        .eq("kind", "place").in_("status", ["proposed", "rejected"])
        .gte("created_at", cutoff)
        .order("created_at", desc=True).limit(int(limit)).execute().data or []
    )
    return [r for r in righe if isinstance(r.get("payload"), dict)
            and r["payload"].get("opp_key")]


def scrivi_proposta_opportunita(opp_key: str, payload: dict[str, Any],
                                req_id: Optional[int] = None) -> Optional[int]:
    """Crea (o AGGIORNA, se ``req_id`` e' noto) la proposta di ``opp_key``.

    Non passa da ``safe_request``: quella nasce 'pending' ed e' per le richieste
    manuali dell'utente, che vanno eseguite subito. Questa nasce 'proposed' e
    resta ferma finche' un essere umano non la promuove.
    Ritorna l'id, oppure None: senza id NON c'e' proposta, e il chiamante non
    deve raccontare il contrario."""
    corpo = {**payload, "opp_key": str(opp_key)}
    if req_id is not None:
        res = (
            _sb().table("safe_strategy_requests")
            .update({"payload": corpo, "updated_at": _now_iso()})
            .eq("id", int(req_id)).eq("status", "proposed").execute()
        )
        if _CANALE_ACCESO:      # F3: la proposta VIVA, aggiornata, sullo schermo
            _cb.pubblica_scritte(_cb.TOPIC["safe_proposta"], res)
        return int(req_id)
    res = (
        _sb().table("safe_strategy_requests")
        .insert({"kind": "place", "status": "proposed", "payload": corpo}).execute()
    )
    if _CANALE_ACCESO:          # F3: DOPO la scrittura riuscita, mai prima
        _cb.pubblica_scritte(_cb.TOPIC["safe_proposta"], res)
    dati = getattr(res, "data", None) or []
    return int(dati[0]["id"]) if dati and dati[0].get("id") is not None else None


def chiudi_proposta_opportunita(req_id: int, motivo: str) -> None:
    """L'opportunita' non c'e' piu' (sparita dal feed, partita finita): la
    proposta DECADE.

    Non e' un rifiuto dell'utente — e' il mercato che e' cambiato. Si marca
    'rejected' con ``decaduta``, cosi' resta la traccia di un ordine PROPOSTO e
    mai partito: senza, sparirebbe e nessuno saprebbe che era stato offerto."""
    res = (
        _sb().table("safe_strategy_requests")
        .update({"status": "rejected",
                 "result": {"decaduta": True, "motivo": str(motivo)[:200]},
                 "updated_at": _now_iso()})
        .eq("id", int(req_id)).eq("status", "proposed").execute()
    )
    if _CANALE_ACCESO:          # F3: la proposta decaduta sparisce anche a video
        _cb.pubblica_scritte(_cb.TOPIC["safe_proposta"], res)


def scadi_proposte_opportunita(ore: float) -> list[dict[str, Any]]:
    """26/09 (F-6, e2e fase 3) - le proposte di opportunita' ancora 'proposed'
    piu' vecchie di ``ore`` DECADONO, con la stessa marca di
    ``chiudi_proposta_opportunita`` ('rejected' + ``decaduta``; lo stato
    'expired' non esiste nel CHECK di ``safe_strategy_requests``).

    Perche': ``proposte_opportunita`` legge solo le ultime 24 ore. Una proposta
    rimasta viva mentre il servizio era spento (la #257 del 24/09, partita
    finita) usciva dalla finestra e non decadeva MAI: la Control Room la
    mostrava due giorni dopo con «Piazza». Un solo UPDATE filtrato dal DB."""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=float(ore))).isoformat()
    res = (
        _sb().table("safe_strategy_requests")
        .update({"status": "rejected",
                 "result": {"decaduta": True, "scaduta": True,
                            "motivo": f"proposta scaduta: piu' vecchia di {ore:g} ore"},
                 "updated_at": _now_iso()})
        .eq("kind", "place").eq("status", "proposed").lt("created_at", cutoff).execute()
    )
    if _CANALE_ACCESO:          # F3: la proposta scaduta sparisce anche a video
        _cb.pubblica_scritte(_cb.TOPIC["safe_proposta"], res)
    return list(res.data or [])


def marca_proposta_opportunita_annotata(req_id: int,
                                        result: dict[str, Any]) -> None:
    """Segna che il RIFIUTO dell'utente e' gia' finito in attivita'.

    Il rifiuto lo scrive la RPC ``safe_request_ignore`` (il servizio non c'e'
    in quel momento): l'attivita' la scrive il servizio al primo ciclo utile, e
    questo flag evita di riscriverla a ogni giro."""
    (
        _sb().table("safe_strategy_requests")
        .update({"result": {**(result or {}), "attivita_scritta": True},
                 "updated_at": _now_iso()})
        .eq("id", int(req_id)).execute()
    )


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
