"""service — BOT MIKE (Under 3.5 / Over 4.5), come il Safe bot: legge SOLO il feed unico.

Ciclo (``run_once``, iniettabile per i test):
  (a) richieste della UI (cashout / flatten / skip / resume) — SEMPRE;
  (b) per ogni partita seguita: Snapshot dal feed → ``engine.decide`` → azioni;
      protezioni/uscite SEMPRE, nuovi ingressi SOLO se status='running';
  (c) settlement a mercato chiuso (REST listMarketBook: 2 chiamate per partita, a fine gara);
  (d) stats + heartbeat su ``mike_control``.

Esecuzione = ``Betfair/safe_strategy/execution.place`` (reserve-first su ``mike_trades``,
paper = fill sul feed, live = REST FOK con la sessione condivisa). In PAPER e in-play
il fill viene DIFFERITO di ``bet_delay`` secondi (dal feed) e rieseguito al prezzo
allora disponibile: mai piu' ottimista del live. ``mode`` SOLO da ``mike_control``.

Uso: python -m Betfair.mike.service [--once] [--dry]
  --once  un ciclo e esce (collaudo);  --dry  nessun ordine (azioni loggate come would_place)
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import time
from datetime import datetime
from datetime import timedelta as _timedelta
from datetime import timezone
from typing import Any, Dict, List, Optional

from Betfair.safe_strategy import execution as X

from . import config as C
from . import db as _real_db
from . import dossier as D
from . import engine as E
from . import feed as F

logger = logging.getLogger("mike")

_LOCK_PORT = C.env_int("MIKE_LOCK_PORT", C.LOCK_PORT_DEFAULT)
_SCANNER_ALIVE_MAX_S = 30.0
_PENDING_STALE_S = 120.0          # gamba pending senza esito da troppo: esito noto → ritirata, ignoto → riconciliazione
_SETTLE_RETRY_S = 30.0            # ripiego se settle_confirm_s = 0 (fra due letture REST a mercato chiuso)
_SETTLE_MAX_WAIT_S = 2 * 3600.0   # oltre: fallback sull'ultimo punteggio noto o ERROR
_DAILY_STOP_LOGGED: Dict[str, str] = {}   # {"day": iso Rome} → lo stop giornaliero si logga una volta al giorno
_ROW_MISSING_GRACE_S = 600.0      # riga assente dal feed per meno di cosi' = transitoria (es. passaggio pre-KO → in-play)
_MATCH_OVER_S = 3 * 3600.0        # oltre 3h dal KO la partita e' finita comunque
_MATCH_LIKELY_OVER_S = 100 * 60.0 # vista in-play e KO + 100': la riga sparita = partita finita (regolamento subito)
_HEARTBEAT_MIN_S = 10.0           # H5: la UI ascolta mike_control in realtime → mai un battito a ogni ciclo
_STATS_MIN_S = 5.0                # M6: stats riscritte al massimo ogni 5 s anche se qualcosa cambia
_CRITICAL_LOG_EVERY_S = 45.0      # M7: i log CRITICI non vengono silenziati per 5 minuti
_STALE_REQUEST_MIN = 10           # richieste 'processing' piu' vecchie = crash: chiuse in errore (M2)
_STRATEGY_REF = C.CUSTOMER_STRATEGY_REF
_LAST_HEARTBEAT: Dict[str, float] = {}
_CONFIG_WARNED: Dict[str, str] = {}

ACTIVE_STATES = tuple(s for s in E.STATES if s not in E.TERMINAL_STATES)


# ---------------------------------------------------------------------------
# Market REST (solo settlement / fallback): sessione CONDIVISA di omega_market
# ---------------------------------------------------------------------------
class _RealMarket:
    @staticmethod
    def _bind_strategy_ref(omega_market: Any) -> None:
        """L1 — gli ordini LIVE di Mike devono portare il SUO customerStrategyRef.

        ``omega_market.place_order_live`` legge la costante di modulo: il servizio
        Mike e' un PROCESSO separato (lock 47319), quindi legare qui il ref
        'mike' marchia solo gli ordini di Mike e rende utilizzabili
        ``list_current_orders``/``listClearedOrders`` filtrate per Mike.
        Prima ogni ordine Mike usciva marchiato 'omega'.
        """
        if getattr(omega_market, "CUSTOMER_STRATEGY_REF", None) != _STRATEGY_REF:
            omega_market.CUSTOMER_STRATEGY_REF = _STRATEGY_REF

    @staticmethod
    def read_book(market_id: str, names: Dict[int, str]) -> Optional[dict]:
        from Betfair.omega import omega_market

        return omega_market.read_book(str(market_id), names)

    @staticmethod
    def place_order_live(**kw: Any) -> Any:
        from Betfair.omega import omega_market

        _RealMarket._bind_strategy_ref(omega_market)
        return omega_market.place_order_live(**kw)

    @staticmethod
    def list_current_orders() -> List[dict]:
        """Ordini VIVI marchiati 'mike' (riconciliazione C3)."""
        from Betfair.omega import omega_market

        _RealMarket._bind_strategy_ref(omega_market)
        return list(omega_market.list_current_orders(_STRATEGY_REF) or [])

    @staticmethod
    def list_cleared_orders() -> List[dict]:
        from Betfair.omega import omega_market

        _RealMarket._bind_strategy_ref(omega_market)
        return list(omega_market.list_cleared_orders(strategy_ref=_STRATEGY_REF) or [])


_real_market = _RealMarket()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: Optional[float]) -> Optional[str]:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat() if ts else None


# ---------------------------------------------------------------------------
# Serializzazione stato partita (mike_events) ⇄ MatchCtx
# ---------------------------------------------------------------------------
_CTX_FIELDS = ("last_green_at", "last_action_at", "attempts", "reentry_allowed", "reentry_done",
               "close_reason", "cover_skipped", "seq", "flatten_pending", "no_reentry")


def _legs_from_json(raw: Any, db: Any = None, event_id: Optional[str] = None) -> List[E.Leg]:
    """Gambe dal JSON di ``mike_events.positions``.

    M3 — una gamba MALFORMATA non viene piu' scartata in silenzio: e' una
    posizione che il bot non vedrebbe piu' (soldi invisibili) → log critico.
    """
    out: List[E.Leg] = []
    fields = {f.name for f in dataclasses.fields(E.Leg)}
    for d in raw or []:
        bad = None
        if not isinstance(d, dict):
            bad = "elemento non oggetto"
        else:
            try:
                out.append(E.Leg(**{k: v for k, v in d.items() if k in fields}))
                continue
            except (TypeError, ValueError) as ex:
                bad = str(ex)[:120]
        logger.critical("[mike] %s: gamba MALFORMATA scartata (%s): %s", event_id, bad,
                        str(d)[:200])
        if db is not None:
            try:
                db.log("error", {"reason": "leg_malformata", "err": bad, "raw": str(d)[:200],
                                 "critical": True}, event_id)
            except Exception:  # noqa: BLE001 — il log non deve mai fermare il ciclo
                pass
    return out


def _ctx_from_row(row: Dict[str, Any], db: Any = None) -> E.MatchCtx:
    extra = row.get("ctx") or {}
    ctx = E.MatchCtx(state=str(row.get("state") or "WATCH"),
                     legs=_legs_from_json(row.get("positions"), db, row.get("event_id")),
                     cycle_no=int(row.get("cycle_no") or 0),
                     entry_price_initial=row.get("entry_price_initial"))
    for k in _CTX_FIELDS:
        if k in extra and extra[k] is not None:
            setattr(ctx, k, extra[k])
    if row.get("settled_pnl") is not None:
        ctx.settled_pnl = float(row["settled_pnl"])       # colonna top-level (round-trip, review F1 #5)
    if ctx.entry_price_initial is not None:
        ctx.entry_price_initial = float(ctx.entry_price_initial)
    return ctx


def _row_from_ctx(row: Dict[str, Any], ctx: E.MatchCtx, extra: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["state"] = ctx.state
    out["cycle_no"] = int(ctx.cycle_no)
    out["entry_price_initial"] = ctx.entry_price_initial
    out["positions"] = [dataclasses.asdict(l) for l in ctx.legs]
    out["settled_pnl"] = ctx.settled_pnl
    # i campi dell'engine VINCONO sui valori stantii di extra (bug: last_green_at
    # sovrascritto dal ctx precedente → cooldown ignorato)
    keep = dict(extra)
    keep.update({k: getattr(ctx, k) for k in _CTX_FIELDS})
    out["ctx"] = keep
    return out


def _signature(row: Dict[str, Any]) -> str:
    import hashlib
    import json

    body = {k: v for k, v in row.items() if k not in ("updated_at",)}
    return hashlib.md5(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Esecuzione di UNA azione (place) via execution.place + riga mike_trades
# ---------------------------------------------------------------------------
def _trade_row(info: F.EventInfo, leg: E.Leg, mode: str, params: Dict[str, Any],
               minute: Optional[int], score: Optional[str],
               closes_trade_id: Optional[int] = None,
               close_reason: Optional[str] = None) -> Dict[str, Any]:
    sid = info.selection_id(leg.market, leg.selection)
    liability = round(leg.size * (leg.price - 1.0), 2) if leg.side == "lay" else round(leg.size, 2)
    meta: Dict[str, Any] = {"phase": "reserved", "leg_ref": leg.ref, "final": bool(leg.final)}
    if leg.role in E.CLOSING_ROLES:
        # H4: la riga di chiusura dice SEMPRE come si e' usciti (contratto UI)
        meta["exit_kind"] = E.exit_kind_for(leg.role, close_reason)
        meta["exit_reason"] = str(close_reason or leg.role)
        if leg.closes_ref:
            meta["closes_ref"] = leg.closes_ref
    row = {
        "event_id": info.event_id, "event_name": info.event_name, "sport": "calcio",
        "strategy": leg.role, "role": leg.role, "cycle_no": int(leg.cycle_no),
        "market_id": info.market_id(leg.market), "market_type": C.OU35 if leg.market == E.MARKET_OU35 else C.OU45,
        "selection_id": int(sid) if sid is not None else None,
        "selection_name": info.selection_name(leg.market, leg.selection),
        "side": leg.side, "mode": mode, "price": leg.price, "size": leg.size, "liability": liability,
        "commission": C.commission_rate(params), "persistence": leg.persistence,
        "minute_at_entry": minute, "score_at_entry": score, "status": "pending", "pnl": 0.0,
        "origin": "manual" if (leg.role == "manual_close" or close_reason == "manual") else "auto",
        "signal_key": leg.ref,
        "meta": meta,
    }
    if closes_trade_id is not None:
        row["closes_trade_id"] = int(closes_trade_id)
    return row


_SCHEMA_ERR_MARKERS = ("42703", "pgrst204", "does not exist", "unknown column", "schema cache")


def _is_missing_column_error(ex: Exception, column: str) -> bool:
    """True SOLO se l'errore dice che QUELLA COLONNA non esiste (C5).

    Un timeout o un errore di rete NON e' un errore di schema: ritentare
    l'insert su un'eccezione qualunque significa rischiare la riga DOPPIA
    (il primo insert potrebbe essere andato a buon fine).
    """
    msg = str(ex).lower()
    return column.lower() in msg and any(m in msg for m in _SCHEMA_ERR_MARKERS)


def _insert_trade_row(db: Any, row: Dict[str, Any], event_id: str) -> Optional[int]:
    """Inserimento tollerante: se la colonna ``closes_trade_id`` non esiste
    ancora (``mike_bot_v2.sql`` non applicata) la riga viene riscritta senza,
    con il riferimento conservato in ``meta.closes_trade_id_pending`` — mai un
    ordine perso per una migrazione mancante. Su QUALUNQUE altro errore
    l'eccezione RISALE: la riserva fallita e' gestita dal chiamante (nessun
    ordine), un retry cieco creerebbe righe doppie."""
    try:
        return db.insert_trade(row)
    except Exception as ex:  # noqa: BLE001
        if "closes_trade_id" not in row or not _is_missing_column_error(ex, "closes_trade_id"):
            raise
        fallback = {k: v for k, v in row.items() if k != "closes_trade_id"}
        meta = dict(fallback.get("meta") or {})
        meta["closes_trade_id_pending"] = row["closes_trade_id"]
        fallback["meta"] = meta
        db.log("schema_warn", {"reason": "closes_trade_id assente (migrazione mike_bot_v2 non applicata)",
                               "err": str(ex)[:120]}, event_id)
        return db.insert_trade(fallback)


def execute_place(*, db: Any, market: Any, info: F.EventInfo, leg: E.Leg, book: Optional[E.Book],
                  mode: str, params: Dict[str, Any], now: datetime, dry: bool,
                  minute: Optional[int] = None, score: Optional[str] = None,
                  feed_fresh: bool = True, closes_trade_id: Optional[int] = None,
                  close_reason: Optional[str] = None) -> str:
    """Piazza la gamba (reserve-first). Ritorna 'open' | 'cancelled' | 'pending'.

    Regola prezzo TAKER: il fill avviene al prezzo richiesto solo se ANCORA
    disponibile (back: best_back ≥ prezzo; lay: best_lay ≤ prezzo); altrimenti
    nessun fill (mai piu' ottimista del live). La size e' cappata alla size al best.

    M7 — FEDELTA' PAPER: con il feed STANTIO (riga vecchia e scanner muto) in
    paper non si simula NESSUN fill: i prezzi fermi darebbero un fill fantasma a
    un prezzo che il mercato non ha piu'. In live non cambia nulla (li' risponde
    l'exchange).
    """
    sid = info.selection_id(leg.market, leg.selection)
    mid = info.market_id(leg.market)
    if sid is None or mid is None:
        leg.status = "cancelled"
        db.log("skip", {"leg": leg.ref, "reason": "mercato/selezione assenti"}, info.event_id)
        return "cancelled"
    if book is None or book.status != "OPEN":
        leg.status = "cancelled"
        db.log("skip", {"leg": leg.ref, "reason": f"book non OPEN ({book.status if book else 'assente'})"},
               info.event_id)
        return "cancelled"
    if mode == "paper" and not feed_fresh:
        leg.status = "cancelled"
        db.log("no_fill", {"leg": leg.ref, "role": leg.role, "reason": "feed_stantio",
                           "wanted": leg.price, "side": leg.side}, info.event_id)
        return "cancelled"
    if leg.side == "back":
        avail_price, avail_size = book.best_back, book.back_size
        ok_price = avail_price is not None and avail_price >= leg.price - 1e-9
    else:
        avail_price, avail_size = book.best_lay, book.lay_size
        ok_price = avail_price is not None and avail_price <= leg.price + 1e-9
    if not ok_price:
        leg.status = "cancelled"
        db.log("no_fill", {"leg": leg.ref, "wanted": leg.price, "available": avail_price,
                           "side": leg.side}, info.event_id)
        return "cancelled"
    if dry:
        leg.status = "cancelled"
        db.log("would_place", {"leg": leg.ref, "role": leg.role, "side": leg.side, "price": leg.price,
                               "size": leg.size, "persistence": leg.persistence}, info.event_id)
        return "cancelled"
    if leg.side == "back" and not params.get("exact_sizes", True) and E.needs_submin(leg.side, leg.size):
        # importi esatti SPENTI: le aperture BACK vanno legalizzate (.it min 2.00, passo 0.50)
        # come fa l'engine per la copertura (review F1 #2). Con exact_sizes=True la size
        # resta al centesimo: in paper passa cosi', in live e' il place-and-trim (F6).
        legal, _ = E.legalize_back_size(leg.size, str(params.get("cover_rounding", "ceil")))
        db.log("size_legalized", {"leg": leg.ref, "from": leg.size, "to": legal}, info.event_id)
        leg.size = legal
    row = _trade_row(info, leg, mode, params, minute, score, closes_trade_id, close_reason)
    try:
        trade_id = _insert_trade_row(db, row, info.event_id)
    except Exception as ex:  # noqa: BLE001 — riserva fallita: nessun ordine
        leg.status = "cancelled"
        db.log("error", {"leg": leg.ref, "reason": "reserve_failed", "err": str(ex)[:160]}, info.event_id)
        return "cancelled"
    exec_params = dict(params)
    exec_params["execution_mode"] = "rest" if not C.env_bool("MIKE_USE_FLUMINE_QUEUE", False) else "auto"
    out = X.place(db=db, market=market, mode=mode, event_id=info.event_id, market_id=mid,
                  selection_id=int(sid), side=leg.side, price=leg.price, size=leg.size,
                  best_size=avail_size, ladder=(), client_ref=f"mike-t{trade_id}",
                  trade_id=int(trade_id), meta=dict(row["meta"]), now=now, params=exec_params)
    if out.status == "open":
        leg.matched = float(out.size)
        leg.avg_price = float(out.price or leg.price)
        leg.status = "open"
        try:
            db.update_trade(int(trade_id), status="open", price=out.price, size=out.size,
                            liability=X.liability_of(leg.side, out.size, out.price or 0.0),
                            bet_id=out.bet_id, meta={**row["meta"], "phase": "open", "fill": out.fill_note})
        except Exception as ex:  # noqa: BLE001
            logger.critical("[mike] conferma DB FALLITA (trade %s): %s", trade_id, str(ex)[:160])
        db.log("place", {"leg": leg.ref, "trade_id": trade_id, "role": leg.role, "side": leg.side,
                         "price": out.price, "size": out.size, "mode": mode, "note": out.fill_note},
               info.event_id)
        return "open"
    if out.status == "pending":
        # C3 — esito IGNOTO (eccezione dopo l'invio): la gamba NON e' "non
        # piazzata". Resta in riconciliazione: conta nel rischio, blocca i nuovi
        # ingressi, MAI cancellata per TTL.
        if str(out.fill_note or "").startswith("place_exception_reconciling"):
            leg.status = E.STATUS_RECONCILE
            logger.critical("[mike] %s: gamba %s con esito IGNOTO → riconciliazione (nessun rientro)",
                            info.event_id, leg.ref)
            db.log("reconcile_pending", {"leg": leg.ref, "trade_id": trade_id, "role": leg.role,
                                         "side": leg.side, "price": leg.price, "size": leg.size,
                                         "note": out.fill_note, "critical": True}, info.event_id)
            return "pending_reconcile"
        db.log("place_pending", {"leg": leg.ref, "trade_id": trade_id, "note": out.fill_note}, info.event_id)
        return "pending"
    leg.status = "cancelled"
    try:
        db.update_trade(int(trade_id), status="error", meta={**row["meta"], "reason": out.fill_note})
    except Exception:  # noqa: BLE001
        pass
    db.log("skip", {"leg": leg.ref, "trade_id": trade_id, "reason": out.fill_note}, info.event_id)
    return "cancelled"


# ---------------------------------------------------------------------------
# Settlement a mercato chiuso: REST listMarketBook (runner WINNER/LOSER)
# ---------------------------------------------------------------------------
def market_winner(book: Optional[dict], market: str, info: F.EventInfo) -> Optional[str]:
    """Selezione dichiarata WINNER dai runner del book, o None se non regolato."""
    if not book or str(book.get("status") or "").upper() != "CLOSED":
        return None
    for r in book.get("runners") or []:
        if str(r.get("status") or "").upper() == "WINNER":
            try:
                sid = int(r.get("selection_id"))
            except (TypeError, ValueError):
                continue
            if sid == info.selection_id(market, E.SEL_UNDER):
                return E.SEL_UNDER
            if sid == info.selection_id(market, E.SEL_OVER):
                return E.SEL_OVER
    return None


def final_total_from_books(b35: Optional[dict], b45: Optional[dict], info: F.EventInfo) -> Optional[int]:
    """Somma gol RAPPRESENTATIVA (3 | 4 | 5) dagli esiti dei runner, o None se non regolati."""
    w35 = market_winner(b35, E.MARKET_OU35, info)
    w45 = market_winner(b45, E.MARKET_OU45, info)
    if w35 == E.SEL_UNDER:
        return 3
    if w45 == E.SEL_OVER:
        return 5
    if w35 == E.SEL_OVER and w45 == E.SEL_UNDER:
        return 4
    return None


# Stati di mercato che Betfair usa per un mercato ANNULLATO. 'INACTIVE' NON c'e':
# e' il mercato non ancora attivo (pre-apertura), non un void — trattarlo come
# void azzerava il P&L di una partita viva (C4, review 11/09).
_VOID_MARKET_STATUS = ("VOID", "VOIDED")
_VOID_RUNNER_STATUS = ("REMOVED", "REMOVED_VACANT", "VOID", "VOIDED")


def market_voided(book: Optional[dict]) -> bool:
    """M9 — MERCATO annullato (partita abbandonata / mercato cancellato): Betfair
    non dichiara nessun vincitore e le scommesse su QUEL mercato sono nulle.

    Segnali: stato del mercato esplicitamente void, oppure mercato CLOSED senza
    NESSUN runner WINNER e con tutti i runner rimossi/annullati. Il giudizio e'
    PER MERCATO: l'altra linea viene regolata normalmente dai suoi runner (C4).
    """
    if not book:
        return False
    status = str(book.get("status") or "").upper()
    if status in _VOID_MARKET_STATUS:
        return True
    runners = book.get("runners") or []
    if status != "CLOSED" or not runners:
        return False
    states = [str(r.get("status") or "").upper() for r in runners]
    if any(s == "WINNER" for s in states):
        return False
    return all(s in _VOID_RUNNER_STATUS for s in states)


def settle_plan(b35: Optional[dict], b45: Optional[dict], info: F.EventInfo
                ) -> "tuple[Optional[Dict[str, Optional[str]]], Dict[str, Any]]":
    """(winners, telemetria) per il regolamento PER MERCATO (C4).

    ``winners[market]`` = selezione vincente, oppure ``None`` se il mercato e'
    ANNULLATO (solo le sue gambe valgono zero). Ritorna ``None`` se almeno un
    mercato non e' ne' regolato ne' annullato: in quel caso si aspetta ancora
    (nessun P&L inventato, nessun azzeramento globale).
    """
    books = {E.MARKET_OU35: b35, E.MARKET_OU45: b45}
    winners: Dict[str, Optional[str]] = {}
    voided: List[str] = []
    for market, book in books.items():
        if market_voided(book):
            winners[market] = None
            voided.append(market)
            continue
        w = market_winner(book, market, info)
        if w is None:
            return (None, {"voided": voided})
        winners[market] = w
    return (winners, {"voided": voided, "winners": dict(winners)})


# ---------------------------------------------------------------------------
# Ciclo
# ---------------------------------------------------------------------------
def _scanner_age(db: Any, now: float) -> Optional[float]:
    st = db.scanner_status()
    if not st:
        return None
    ts = F.parse_iso_epoch(st.get("updated_at"))
    return None if ts is None else max(0.0, now - ts)


def _params_for(params: Dict[str, Any], running: bool, mode: str = "paper") -> Dict[str, Any]:
    """A bot fermo: NESSUN nuovo ingresso, protezioni e uscite sempre attive.

    H3 — in LIVE la lay APPOGGIATA non e' cablata su NESSUN percorso: ne' REST
    (servirebbe un ordine senza FOK + polling) ne' coda flumine (la gamba
    resting non passa da ``execution.place``, viene solo riservata su
    ``mike_trades``). Finche' non esiste davvero (F6) in live si usa SEMPRE la
    chiusura taker: mai un fill simulato su soldi veri, con o senza
    ``MIKE_USE_FLUMINE_QUEUE``.
    """
    p = dict(params)
    if mode == "live" and p.get("pre_exit_mode") == "resting":
        p["pre_exit_mode"] = "taker"
    if running:
        return p
    p["pre_enabled"] = False
    p["reentry_enabled"] = False
    p["last_entry_persist"] = False
    return p


def _log_throttled(db: Any, extra: Dict[str, Any], params: Dict[str, Any], now_ts: float,
                   kind: str, payload: Dict[str, Any], event_id: Optional[str] = None) -> bool:
    """M3/H5 — ``skip_log_interval_s`` CABLATO: lo STESSO motivo sulla stessa
    partita non viene riscritto piu' di una volta ogni N secondi (prima i log
    ripetitivi riempivano ``mike_activity`` a ogni ciclo).

    M7 (review): un evento CRITICO (``payload['critical']``) usa un intervallo
    molto piu' corto (``_CRITICAL_LOG_EVERY_S``): una linea mancante o un ordine
    a esito ignoto non possono restare muti 5 minuti.
    """
    every = float(params.get("skip_log_interval_s") or 300)
    if payload.get("critical"):
        every = min(every, _CRITICAL_LOG_EVERY_S)
    seen: Dict[str, Any] = dict(extra.get("log_seen") or {})
    key = f"{kind}:{payload.get('reason') or payload.get('leg') or ''}"
    last = float(seen.get(key) or 0.0)
    if now_ts - last < every:
        return False
    seen[key] = now_ts
    # spurgo: mai un dizionario che cresce senza fine
    extra["log_seen"] = {k: v for k, v in seen.items() if now_ts - float(v or 0.0) < every * 4}
    db.log(kind, payload, event_id)
    return True


def _is_resting_leg(leg: E.Leg, params: Dict[str, Any]) -> bool:
    """Lay di green-up appoggiata sul book (take-profit): NON e' un ordine taker."""
    return (leg.side == "lay" and leg.role in ("under_green", "reentry_green")
            and str(params.get("pre_exit_mode")) == "resting" and not leg.final)


def _resting_filled(leg: E.Leg, book: Optional[E.Book]) -> bool:
    """Simulazione CONSERVATIVA della lay appoggiata a ``leg.price``: si considera
    abbinata SOLO quando il mercato ha scambiato SOTTO il suo prezzo (best back
    strettamente minore), mai perche' qualcuno laya allo stesso livello."""
    if book is None or book.status != "OPEN" or book.best_back is None:
        return False
    return float(book.best_back) < float(leg.price) - 1e-9


def _result(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    """M1 — esito standard di una richiesta UI: ``code`` per il codice, ``message``
    in ITALIANO per l'utente. ``ok`` presente solo sugli esiti positivi."""
    out: Dict[str, Any] = {"code": code, "message": message}
    out.update(extra)
    return out


# Esiti ATTESI (l'utente ha chiesto qualcosa che ora non si puo' fare): status
# 'rejected'. Tutto il resto e' 'error' = il servizio non ce l'ha fatta
# (``kind_non_valido`` compreso: significa contratto rotto fra UI e DB).
_REJECT_CODES = ("evento_non_seguito", "stato_terminale", "posizione_aperta", "stato_non_riprendibile",
                 "feed_assente", "snapshot_assente", "niente_da_chiudere", "feed_stantio")


def process_requests(*, db: Any, market: Any, events: Dict[str, Dict[str, Any]],
                     rows_by_event: Dict[str, Dict[str, Any]], params: Dict[str, Any],
                     now: datetime, dry: bool, scanner_age: Optional[float] = None,
                     eff: Optional[Dict[str, Any]] = None) -> int:
    # L3: le chiusure manuali usano i parametri EFFETTIVI del ciclo (in live la
    # lay appoggiata e' spenta: la chiusura deve essere taker)
    eff = eff if eff is not None else params
    n = 0
    try:
        reqs = db.pending_requests()
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "requests_failed", "err": str(ex)[:160]})
        return 0
    for req in reqs:
        rid = int(req["id"])
        kind = str(req.get("kind") or "")
        payload = req.get("payload") or {}
        eid = str(payload.get("event_id") or "")
        db.set_request_status(rid, "processing")
        res: Dict[str, Any]
        try:
            ev = events.get(eid)
            if ev is None:
                res = _result("evento_non_seguito", "Partita non seguita dal bot.")
            elif kind != "resume_event" and str(ev.get("state")) in ("SETTLED", "ERROR"):
                res = _result("stato_terminale",
                              f"Partita in stato {ev.get('state')}: nessuna operazione possibile.")
            elif kind in ("cashout", "flatten"):
                res = _request_flatten(db, market, ev, rows_by_event.get(eid), eff, now, dry,
                                       scanner_age=scanner_age, kind=kind)
            elif kind == "cancel":
                res = _request_cancel(db, ev, events, eid)
            elif kind == "skip_event":
                ctx = _ctx_from_row(ev, db)
                if E.open_selections(ctx.legs) or any(l.is_live or l.needs_reconcile for l in ctx.legs):
                    res = _result("posizione_aperta",
                                  "Posizione ancora aperta: prima chiudi con Cash out.")
                else:
                    ctx.state = "SKIPPED"
                    events[eid] = _row_from_ctx(ev, ctx, dict(ev.get("ctx") or {}))
                    events[eid]["skipped"] = True
                    db.upsert_event(events[eid])      # terminale: il ciclo partita non persiste
                    db.log("skip_event", {"by": "utente"}, eid)
                    res = _result("ok", "Partita saltata.", ok=True, state="SKIPPED")
            elif kind == "resume_event":
                ctx = _ctx_from_row(ev, db)
                extra = dict(ev.get("ctx") or {})
                if ctx.state == "SKIPPED":
                    ctx.state = "WATCH"
                    ctx.no_reentry = False            # H1/C3: l'utente riattiva la partita
                    ctx.flatten_pending = False
                    events[eid] = _row_from_ctx(ev, ctx, extra)
                    events[eid]["skipped"] = False
                    db.upsert_event(events[eid])
                    db.log("resume_event", {"by": "utente", "to": "WATCH"}, eid)
                    res = _result("ok", "Partita ripresa.", ok=True, state="WATCH")
                elif ctx.no_reentry or ctx.flatten_pending:
                    # C3: dopo un cash out manuale pre-KO il bot NON rientra da
                    # solo; "Riprendi" e' l'unico modo di riabilitarlo. Si azzera
                    # anche ``flatten_pending``, altrimenti il completamento
                    # della chiusura manuale rimetterebbe subito il divieto.
                    ctx.no_reentry = False
                    ctx.flatten_pending = False
                    events[eid] = _row_from_ctx(ev, ctx, extra)
                    db.upsert_event(events[eid])
                    db.log("resume_event", {"by": "utente", "no_reentry": False}, eid)
                    res = _result("ok", "Rientro riabilitato su questa partita.", ok=True,
                                  state=ctx.state)
                else:
                    res = _result("stato_non_riprendibile",
                                  f"Stato {ctx.state}: niente da riprendere.")
            else:
                res = _result("kind_non_valido", f"Comando non valido: {kind}.")
        except Exception as ex:  # noqa: BLE001
            res = _result("errore_interno", f"Errore interno: {str(ex)[:120]}")
        status = "done" if res.get("ok") else ("rejected" if res.get("code") in _REJECT_CODES else "error")
        db.set_request_status(rid, status, res)
        n += 1
    return n


def _request_cancel(db: Any, ev: Dict[str, Any], events: Dict[str, Dict[str, Any]],
                    eid: str) -> Dict[str, Any]:
    """Annulla gli ordini VIVI (resting) della partita, senza toccare la posizione.
    Una gamba in riconciliazione NON viene mai cancellata (C3)."""
    ctx = _ctx_from_row(ev, db)
    live = [l for l in ctx.legs if l.is_live]
    if not live:
        return _result("niente_da_chiudere", "Nessun ordine vivo da annullare.")
    for leg in live:
        leg.status = "open" if leg.matched > 0 else "cancelled"
        _mark_trade_cancelled(db, eid, leg, "cancelled_by_user")
        db.log("cancel", {"leg": leg.ref, "role": leg.role, "by": "utente"}, eid)
    events[eid] = _row_from_ctx(ev, ctx, dict(ev.get("ctx") or {}))
    db.upsert_event(events[eid])
    return _result("ok", f"Annullati {len(live)} ordini sul book.", ok=True, cancelled=len(live))


def _request_flatten(db: Any, market: Any, ev: Dict[str, Any], row: Optional[Dict[str, Any]],
                     params: Dict[str, Any], now: datetime, dry: bool,
                     scanner_age: Optional[float] = None, kind: str = "cashout") -> Dict[str, Any]:
    """Cash out / flatten MANUALE (H1, C2, M5).

    La richiesta ARMA la chiusura e annulla subito gli ordini vivi; la chiusura
    vera la guida l'ENGINE (``ctx.flatten_pending`` → ``_decide_flatten``) nello
    stesso ciclo e in quelli successivi, con i riprezzi. Cosi':
      1. prima si CANCELLA (una lay di green-up appoggiata che resta sul book
         lascerebbe una posizione netta LAY scoperta);
      2. poi si chiude la posizione netta delle sole selezioni ANCORA VIVE;
      3. C2 — finche' ``flatten_pending`` e' attivo il ciclo pre-match NON
         riappoggia la lay di green-up (prima, con ``pre_exit_mode='resting'``,
         cancellava e riappoggiava all'infinito: cash out impossibile);
      4. il contesto NON viene azzerato (ht_score, last_goals, deferred, selezioni);
      5. pre-KO: ciclo chiuso E ``no_reentry`` — il bot non rientra finche'
         l'utente non riabilita la partita con "Riprendi".
    """
    ctx = _ctx_from_row(ev, db)
    extra = dict(ev.get("ctx") or {})
    eid = str(ev["event_id"])
    info = F.event_info(eid, (row or {}).get("payload") or {})
    if row is None or not info.complete:
        return _result("feed_assente",
                       "Quote non disponibili nel feed per questa partita: chiusura impossibile ora.")
    snap = F.snapshot_from_row(row, info, now=now.timestamp(), params=params,
                              scanner_age_s=scanner_age)
    if snap is None:
        return _result("snapshot_assente", "Fotografia del mercato non disponibile: riprova.")
    if not snap.feed_fresh:
        return _result("feed_stantio",
                       "Feed non aggiornato: chiudere ora userebbe prezzi vecchi. Riprova tra qualche secondo.")
    reconciling = E.has_unknown_orders(ctx)
    cv = E.cashout_value(ctx.legs, snap.books, C.commission_rate(params),
                         int(params["cashout_place_at_ticks"]), goals=snap.goals)
    live = [l for l in ctx.legs if l.is_live]
    if not live and not E.live_open_selections(ctx.legs, snap.goals):
        # nulla da annullare e nulla da chiudere: si registra comunque il divieto
        # di rientro pre-KO (l'utente ha detto "chiudi questa partita")
        ctx.close_reason = "manual"
        if not snap.inplay:
            ctx.no_reentry = True
        ev.update(_row_from_ctx(ev, ctx, extra))
        db.upsert_event(ev)
        msg = "Nessuna posizione da chiudere."
        if not cv.complete:
            msg = "Prezzi non disponibili sulle selezioni ancora in gioco: nessuna chiusura possibile."
        return _result("niente_da_chiudere", msg, cashout=cv.net, complete=cv.complete)
    # 1) annullo immediato degli ordini vivi (la gamba a esito IGNOTO non si
    #    tocca mai: C3)
    cancelled = 0
    for leg in live:
        leg.status = "open" if leg.matched > 0 else "cancelled"
        extra["deferred"] = [x for x in (extra.get("deferred") or []) if x.get("ref") != leg.ref]
        _mark_trade_cancelled(db, eid, leg, "cancelled_manual")
        db.log("cancel", {"leg": leg.ref, "role": leg.role, "by": "utente"}, eid)
        cancelled += 1
    # 2) la chiusura la guida l'engine (stesso ciclo): mai un doppio percorso
    ctx.flatten_pending = True
    ctx.close_reason = "manual"
    ctx.attempts = 0
    if not snap.inplay:
        ctx.no_reentry = True
    ev.update(_row_from_ctx(ev, ctx, extra))
    db.upsert_event(ev)
    label = "Cash out" if kind == "cashout" else "Flatten"
    parts = []
    if cancelled:
        parts.append(f"annullati {cancelled} ordini sul book")
    parts.append(f"chiusura in corso (netto stimato {cv.net:.2f} EUR)")
    msg = f"{label}: " + ", ".join(parts) + "."
    if reconciling:
        msg += " ATTENZIONE: un ordine e' in riconciliazione, l'esposizione reale potrebbe differire."
    return _result("ok", msg, ok=True, cancelled=cancelled, phase="armed",
                   cashout_net=cv.net, complete=cv.complete,
                   warning="reconcile" if reconciling else None)


def run_once(*, db: Any = _real_db, market: Any = _real_market, now: Optional[datetime] = None,
             atlas: Optional[Dict[str, Any]] = None, rows: Optional[List[Dict[str, Any]]] = None,
             dry: bool = False) -> Dict[str, Any]:
    now = now or _now()
    now_ts = now.timestamp()
    try:
        control = db.read_control()
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] read_control KO: %s", str(ex)[:160])
        return {"skipped": "control_unreadable"}
    if control is None:
        return {"skipped": "no_control"}
    status = str(control.get("status") or "idle")
    mode = str(control.get("mode") or "paper")
    if mode not in ("paper", "live"):
        mode = "paper"
    params = C.merge_params(control.get("params"))
    running = status == "running"
    eff = _params_for(params, running, mode)
    _config_warn(db, params)

    # M2: richieste rimaste in 'processing' (crash) chiuse a OGNI ciclo, altrimenti
    # quella partita non accetta piu' nessun cash out.
    try:
        db.fail_stale_processing(_STALE_REQUEST_MIN)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] fail_stale_processing KO: %s", str(ex)[:120])

    # feed unico: UNA lettura per ciclo
    if rows is None:
        rows = list(db.fetch_scan_rows() or [])
    rows_by_event = {str(r.get("event_id")): r for r in rows if r.get("event_id")}
    scanner_age = _scanner_age(db, now_ts)

    # partite seguite (stato persistito): ANCHE le terminali recenti (SKIPPED/
    # SETTLED), così non vengono ri-armate come nuove candidate
    try:
        since = datetime.fromtimestamp(now_ts - 48 * 3600, tz=timezone.utc).isoformat()
        tracked = {str(e["event_id"]): e for e in (db.list_events(since_iso=since) or [])}
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "events_failed", "err": str(ex)[:160]})
        return {"skipped": "events_unreadable"}
    for ev in tracked.values():
        ev.setdefault("mode", mode)

    # STOP giornaliero (L3): P&L della giornata operativa (Europe/Rome, giorno di
    # PIAZZAMENTO — M6) = REGOLATO + BLOCCATO. Il bloccato sono i cicli già
    # chiusi/greenati non ancora pagati dal mercato: prima erano invisibili allo
    # stop e il bot continuava ad aprire dopo aver già perso il massimo.
    try:
        agg = db.aggregates(now)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] aggregates KO: %s", str(ex)[:160])
        agg = {}
    day_start_ts = _operating_day_start_ts(now)
    locked_open = _locked_open_pnl(tracked, params, day_start_ts)
    realized_today = float(agg.get("realized_today", 0.0))
    day_pnl = round(realized_today + locked_open, 2)
    stop = float(params.get("daily_loss_stop") or 0.0)
    daily_stop = stop > 0 and day_pnl <= -stop
    if daily_stop:
        # H1 (review): anche l'ULTIMO INGRESSO (PERSIST) e' un ingresso nuovo —
        # senza spegnerlo `_after_final_green` piazzava ancora `under_last`.
        eff = dict(eff, pre_enabled=False, reentry_enabled=False, last_entry_persist=False)
        day_key = _operating_day_key(now)
        if _DAILY_STOP_LOGGED.get("day") != day_key:
            _DAILY_STOP_LOGGED["day"] = day_key
            logger.warning("[mike] STOP giornaliero: P&L oggi %.2f (regolato %.2f + bloccato %.2f) <= -%.2f",
                           day_pnl, realized_today, locked_open, stop)
            db.log("daily_stop", {"day_pnl": day_pnl, "realized_today": round(realized_today, 2),
                                  "locked_open": round(locked_open, 2), "stop": stop,
                                  "day": day_key})

    n_requests = process_requests(db=db, market=market, events=tracked, rows_by_event=rows_by_event,
                                  params=params, eff=eff, now=now, dry=dry, scanner_age=scanner_age)
    open_refs = _open_refs_by_event(db)      # H5: una query per il pre-controllo H2

    # nuove candidate (solo a bot in esecuzione, sotto il tetto partite)
    n_new = 0
    if running and not daily_stop:
        # tetto = partite con POSIZIONE (o ordini): quelle solo osservate (WATCH) o
        # in-play senza posizione (IDLE_LIVE) non bloccano le nuove candidate
        active = sum(1 for e in tracked.values()
                     if e.get("state") not in E.TERMINAL_STATES and e.get("state") not in ("WATCH", "IDLE_LIVE"))
        for eid, row in rows_by_event.items():
            if eid in tracked or active >= int(params["max_open_matches"]):
                continue
            payload = row.get("payload") or {}
            info = F.event_info(eid, payload)
            if not F.is_candidate(info, payload, now=now_ts, params=params):
                continue
            dossier = D.build_prematch(eid, db)
            tracked[eid] = {
                "event_id": eid, "fixture_id": dossier.get("fixture_id"), "event_name": info.event_name,
                "competition": info.competition, "league_id": dossier.get("league_id"),
                "ko_at": _iso(info.ko_at), "markets": {m: {"market_id": info.market_id(m)} for m in info.markets},
                "state": "WATCH", "cycle_no": 0, "entry_price_initial": None, "dossier": dossier,
                "live": {}, "positions": [], "skipped": False, "settled_pnl": None, "mode": mode, "ctx": {},
            }
            active += 1
            n_new += 1
            db.log("armed", {"event": info.event_name, "ko": _iso(info.ko_at), "dossier": dossier}, eid)

    # ciclo per partita
    n_actions = n_settled = 0
    trades_cache: Dict[str, List[Dict[str, Any]]] = {}
    for eid, ev in list(tracked.items()):
        try:
            acted, settled = _run_event(db=db, market=market, ev=ev, row=rows_by_event.get(eid),
                                        params=eff, mode=str(ev.get("mode") or mode), now=now,
                                        scanner_age=scanner_age, atlas=atlas, dry=dry,
                                        cache=trades_cache, open_refs=open_refs)
            n_actions += acted
            n_settled += settled
        except Exception as ex:  # noqa: BLE001 — una partita rotta non ferma le altre
            logger.exception("[mike] evento %s KO: %s", eid, str(ex)[:160])
            db.log("error", {"reason": "event_cycle", "err": str(ex)[:160]}, eid)

    if status == "stopping":
        try:
            db.set_control(status="stopped", stopped_at=now.isoformat())
            db.log("stop", {})
        except Exception:  # noqa: BLE001
            pass
        status = "stopped"

    if n_actions or n_settled or n_requests:
        try:
            agg = db.aggregates(now)          # aggiornati dopo le azioni del ciclo
        except Exception as ex:  # noqa: BLE001
            logger.warning("[mike] aggregates KO: %s", str(ex)[:160])
        locked_open = _locked_open_pnl(tracked, params, day_start_ts)
    by_state: Dict[str, int] = {}
    for e in tracked.values():
        by_state[str(e.get("state"))] = by_state.get(str(e.get("state")), 0) + 1
    # M4 — capitale a rischio VERO: perdita peggiore delle posizioni NETTE
    # aperte, partita per partita (un back coperto da lay non e' back + lay).
    open_liability = _open_liability(tracked, params)
    realized_today = float(agg.get("realized_today", 0.0))
    stats = {
        "events_feed": len(rows_by_event), "events_tracked": len(tracked), "by_state": by_state,
        "trades_open": int(agg.get("open_count", 0)), "open_liability": open_liability,
        "open_liability_rows": round(float(agg.get("open_liability", 0.0)), 2),
        "realized_today": round(realized_today, 2),
        "realized_total": round(float(agg.get("realized_total", 0.0)), 2),
        "locked_open": round(locked_open, 2),
        "day_pnl": round(realized_today + locked_open, 2),
        "won_today": int(agg.get("won_today", 0)), "lost_today": int(agg.get("lost_today", 0)),
        "cycles_today": int(agg.get("cycles_today", 0)), "events_today": int(agg.get("events_today", 0)),
        "live_now": sum(1 for e in tracked.values() if (e.get("live") or {}).get("inplay")),
        "scanner_age_s": round(scanner_age, 1) if scanner_age is not None else None,
        "last_cycle": now.isoformat(), "dry": bool(dry), "mode": mode, "daily_stop": bool(daily_stop),
        "reconciling": sum(1 for e in tracked.values()
                           if any(str((l or {}).get("status")) == E.STATUS_RECONCILE
                                  for l in (e.get("positions") or []))),
    }
    # H5 — la UI ascolta mike_control in REALTIME: un battito a ogni ciclo la
    # faceva ricaricare ogni secondo. M6 (review): non basta "cambiato", perche'
    # una stat cambia quasi sempre (P&L, liability) → si scriveva comunque a
    # ogni ciclo. Regola: stats al massimo ogni _STATS_MIN_S (5 s) se qualcosa
    # e' cambiato, e comunque un battito ogni _HEARTBEAT_MIN_S (10 s).
    beat = {k: v for k, v in stats.items() if k not in ("last_cycle", "scanner_age_s")}
    changed = _LAST_HEARTBEAT.get("sig") != _signature(beat)
    elapsed = now_ts - float(_LAST_HEARTBEAT.get("ts") or 0.0)
    if (changed and elapsed >= _STATS_MIN_S) or elapsed >= _HEARTBEAT_MIN_S:
        _LAST_HEARTBEAT["sig"] = _signature(beat)
        _LAST_HEARTBEAT["ts"] = now_ts
        try:
            db.set_control(stats=stats, heartbeat_at=now.isoformat())
        except Exception as ex:  # noqa: BLE001
            logger.warning("[mike] set_control KO: %s", str(ex)[:160])
    return {"status": status, "new": n_new, "actions": n_actions, "settled": n_settled,
            "requests": n_requests, "stats": stats}


def _operating_day_start_ts(now: datetime) -> float:
    """Epoch della mezzanotte di Roma della giornata operativa corrente."""
    from Betfair.safe_strategy import risk as _risk

    return _risk.operating_day_start(now).timestamp()


def _operating_day_key(now: datetime) -> str:
    """Giorno operativo (Europe/Rome) in ISO: L2 — lo stop giornaliero si logga
    una volta per GIORNATA OPERATIVA, non per giorno UTC (alle 23:30 UTC a Roma
    e' gia' il giorno dopo)."""
    from Betfair.safe_strategy import risk as _risk

    start = _risk.operating_day_start(now)        # mezzanotte di Roma, in UTC
    return (start + _timedelta(hours=12)).date().isoformat()


def _ctx_legs_of(ev: Dict[str, Any]) -> List[E.Leg]:
    return _legs_from_json(ev.get("positions"))


def _open_liability(tracked: Dict[str, Dict[str, Any]], params: Dict[str, Any]) -> float:
    """Somma delle liability NETTE delle partite non terminali (M4)."""
    c = C.commission_rate(params)
    tot = 0.0
    for ev in tracked.values():
        if str(ev.get("state")) in E.TERMINAL_STATES:
            continue
        tot += E.event_liability(_ctx_legs_of(ev), c)
    return round(tot, 2)


def _first_placed_at(legs: List[E.Leg]) -> Optional[float]:
    """Epoch del PRIMO piazzamento della partita (giorno operativo della posizione)."""
    ts = [float(l.placed_at) for l in legs if float(l.placed_at or 0.0) > 0.0]
    return min(ts) if ts else None


def _locked_open_pnl(tracked: Dict[str, Dict[str, Any]], params: Dict[str, Any],
                     day_start_ts: Optional[float] = None) -> float:
    """P&L già BLOCCATO sulle partite non ancora regolate (L3): cicli chiusi in
    green o in perdita che il mercato non ha ancora pagato. Le partite con
    esposizione viva NON contano (nulla e' deciso).

    M1 (review): solo le partite della GIORNATA OPERATIVA corrente (primo
    piazzamento ≥ mezzanotte di Roma). La finestra degli eventi seguiti e' di
    48 h: sommare il bloccato di ieri nello stop di oggi lo faceva scattare per
    un P&L che non appartiene alla giornata.
    """
    c = C.commission_rate(params)
    tot = 0.0
    for ev in tracked.values():
        if str(ev.get("state")) in E.TERMINAL_STATES:
            continue
        legs = _ctx_legs_of(ev)
        if day_start_ts is not None:
            first = _first_placed_at(legs)
            if first is None or first < float(day_start_ts):
                continue
        v = E.locked_pnl(legs, c)
        if v is not None:
            tot += v
    return round(tot, 2)


def _config_warn(db: Any, params: Dict[str, Any]) -> None:
    """M8 — la finestra pre-match di Mike non puo' essere piu' ampia del ramo
    pre-KO dello scanner: oltre quell'ora le linee non sono nel feed e il bot
    vedrebbe 0 candidate SENZA dirlo."""
    scanner_h = C.env_float("SAFE_PRE_KO_OU_HOURS", 0.0)
    entry_h = float(params.get("entry_hours_before_ko") or 0.0)
    if scanner_h <= 0:
        msg = ("Il ramo pre-KO dello scanner e' SPENTO (SAFE_PRE_KO_OU_HOURS non impostata): "
               "nessuna linea Under 3.5 / Over 4.5 prima del calcio d'inizio, Mike non vedra' "
               "nessuna candidata.")
        key = "off"
    elif entry_h > scanner_h + 1e-9:
        msg = (f"Finestra di ingresso {entry_h:g} h piu' ampia del ramo pre-KO dello scanner "
               f"({scanner_h:g} h): fra {scanner_h:g} h e {entry_h:g} h prima del KO le linee non "
               f"sono nel feed e le partite non vengono armate. Allinea SAFE_PRE_KO_OU_HOURS "
               f"o entry_hours_before_ko.")
        key = f"{entry_h:g}>{scanner_h:g}"
    else:
        _CONFIG_WARNED.pop("key", None)
        return
    if _CONFIG_WARNED.get("key") == key:
        return
    _CONFIG_WARNED["key"] = key
    logger.warning("[mike] config: %s", msg)
    db.log("config_warn", {"message": msg, "entry_hours_before_ko": entry_h,
                           "scanner_pre_ko_hours": scanner_h, "critical": True})


def _run_event(*, db: Any, market: Any, ev: Dict[str, Any], row: Optional[Dict[str, Any]],
               params: Dict[str, Any], mode: str, now: datetime, scanner_age: Optional[float],
               atlas: Optional[Dict[str, Any]], dry: bool,
               cache: Optional[Dict[str, List[Dict[str, Any]]]] = None,
               open_refs: Optional[Dict[str, set]] = None) -> "tuple[int, int]":
    """Un giro per una partita: snapshot → decide → azioni → persistenza. (azioni, settled)."""
    now_ts = now.timestamp()
    if str(ev.get("state")) in E.TERMINAL_STATES:
        return (0, 0)
    ctx = _ctx_from_row(ev)
    extra = dict(ev.get("ctx") or {})
    before_sig = _signature(ev)
    payload = (row or {}).get("payload") or {}
    info = F.event_info(ev["event_id"], payload) if row is not None else None
    dossier = ev.get("dossier") or {}
    settled = 0

    # -- H2: specchio gambe <-> righe allineato a OGNI ciclo ----------------------
    _reconcile_trades(db, ev["event_id"], ctx, info, mode, params, cache, open_refs)

    # -- riga sparita dal feed o mercato chiuso: settlement via REST -------------
    # Una riga ASSENTE e' "chiusa" solo se manca da >= _ROW_MISSING_GRACE_S o se
    # la partita e' comunque finita (KO + 3h): al calcio d'inizio il feed passa dal
    # blocco pre-KO a quello in-play e la riga puo' sparire per qualche minuto
    # (refresh catalogo 300 s) — prima veniva scambiata per un regolamento.
    ko_ts = float(F.parse_iso_epoch(ev.get("ko_at")) or 0.0)
    status_closed = row is not None and str((F.ou_blocks(payload).get(E.MARKET_OU35) or {}).get("status") or
                                            payload.get("mo_status") or "").upper() == "CLOSED"
    if row is None:
        extra["row_missing_since"] = float(extra.get("row_missing_since") or now_ts)
        missing_for = now_ts - float(extra["row_missing_since"])
        absent_closed = missing_for >= _ROW_MISSING_GRACE_S or (ko_ts > 0 and (
            now_ts - ko_ts > _MATCH_OVER_S
            or (bool(extra.get("seen_inplay")) and now_ts - ko_ts >= _MATCH_LIKELY_OVER_S)))
    else:
        extra.pop("row_missing_since", None)
        absent_closed = False
    closed = status_closed or absent_closed
    if row is None and not closed and ctx.state not in E.TERMINAL_STATES:
        ev.update(_row_from_ctx(ev, ctx, extra))          # memorizza da quando manca
        _persist(db, ev, before_sig)
        return (0, 0)
    # falso regolamento gia' scattato (riga tornata, mercato aperto, partita in corso):
    # si torna nello stato coerente con le posizioni aperte
    if ctx.state == "SETTLING" and not closed and row is not None and (ko_ts <= 0 or now_ts - ko_ts < _MATCH_OVER_S):
        opens = E.open_selections(ctx.legs)
        inplay = bool(payload.get("inplay"))
        if (E.MARKET_OU45, E.SEL_OVER) in opens:
            back_to = "LIVE_COVERED"
        elif (E.MARKET_OU45, E.SEL_UNDER) in opens:
            back_to = "REENTRY_OPEN"
        elif (E.MARKET_OU35, E.SEL_UNDER) in opens:
            back_to = "LIVE_UNCOVERED" if inplay else "PRE_OPEN"
        else:
            back_to = "IDLE_LIVE" if inplay else "WATCH"
        extra.pop("settle_first_ts", None)
        extra.pop("settle_next_ts", None)
        db.log("settling_reverted", {"to": back_to, "reason": "riga tornata nel feed, mercato aperto"}, ev["event_id"])
        E.apply_decision(ctx, E.Decision(state=back_to, actions=[], reason="falso regolamento annullato"), now_ts)
    if closed and ctx.state not in E.TERMINAL_STATES:
        # throttle delle letture REST di regolamento (review F1 #3): mai un poll
        # stretto su un mercato chiuso; dopo troppo tempo si ripiega sull'ultimo
        # punteggio noto o si va in ERROR (mai SETTLING per sempre)
        if now_ts < float(extra.get("settle_next_ts") or 0.0):
            # L2: si persiste comunque (il throttle e le riparazioni H2 di questo
            # ciclo non devono andare perse)
            ev.update(_row_from_ctx(ev, ctx, extra))
            _persist(db, ev, before_sig)
            return (0, 0)
        # M3: ``settle_confirm_s`` CABLATO come intervallo fra due letture REST
        extra["settle_next_ts"] = now_ts + max(5.0, float(params.get("settle_confirm_s") or _SETTLE_RETRY_S))
        extra["settle_first_ts"] = float(extra.get("settle_first_ts") or now_ts)
        mkts = ev.get("markets") or {}
        names: Dict[int, str] = {}
        b35 = market.read_book(str((mkts.get(E.MARKET_OU35) or {}).get("market_id") or ""), names) \
            if (mkts.get(E.MARKET_OU35) or {}).get("market_id") else None
        b45 = market.read_book(str((mkts.get(E.MARKET_OU45) or {}).get("market_id") or ""), names) \
            if (mkts.get(E.MARKET_OU45) or {}).get("market_id") else None
        info_s = F.EventInfo(event_id=ev["event_id"], event_name=str(ev.get("event_name") or ""),
                             home=None, away=None, competition=ev.get("competition"),
                             ko_at=F.parse_iso_epoch(ev.get("ko_at")), open_date=ev.get("ko_at"),
                             markets={m: str(v.get("market_id")) for m, v in mkts.items() if v.get("market_id")},
                             selections={tuple(k.split("|")): int(v) for k, v in (extra.get("selections") or {}).items()})
        total = final_total_from_books(b35, b45, info_s)
        # M9 + C4 — mercato ANNULLATO: void PER MERCATO. Solo le gambe del
        # mercato annullato valgono zero; l'altra linea viene regolata dai suoi
        # runner (prima un solo mercato illeggibile azzerava tutta la partita e
        # con 4 gol la perdita reale sull'Under 3.5 spariva).
        if total is None:
            winners, tele = settle_plan(b35, b45, info_s)
            if winners is not None:
                res = E.settle_legs_by_market(ctx.legs, winners, C.commission_rate(params))
                settle = {"per_leg": res.per_leg, "per_market": res.per_market, "net": res.net,
                          "per_leg_gross": res.per_leg_gross,
                          "commission_by_market": res.commission_by_market,
                          "void": bool(tele.get("voided"))}
                E.apply_decision(ctx, E.Decision("SETTLED", [], "regolamento per mercato (void parziale)",
                                                 updates={"settled_pnl": res.net}), now_ts)
                _settle_trades(db, ev["event_id"], ctx, settle, params)
                db.log("settled", {"void": True, "reason": "mercato_annullato",
                                   "voided": tele.get("voided"), "winners": tele.get("winners"),
                                   "pnl": res.net, "legs": len(res.per_leg)}, ev["event_id"])
                ev.update(_row_from_ctx(ev, ctx, extra))
                _persist(db, ev, before_sig)
                return (0, 1)
        if total is None and now_ts - float(extra["settle_first_ts"]) > _SETTLE_MAX_WAIT_S:
            last_goals = extra.get("last_goals")
            if extra.get("seen_inplay") and last_goals is not None:
                total = int(last_goals)
                db.log("settle_fallback", {"reason": "book_non_leggibile", "total_from_feed": total},
                       ev["event_id"])
            else:
                db.log("error", {"reason": "settle_timeout", "critical": True}, ev["event_id"])
                d = E.Decision(state="ERROR", actions=[], reason="regolamento non determinabile")
                E.apply_decision(ctx, d, now_ts)
                ev.update(_row_from_ctx(ev, ctx, extra))
                _persist(db, ev, before_sig)
                return (0, 0)
        snap = E.Snapshot(now=now_ts, ko_at=info_s.ko_at or now_ts, books={}, inplay=True,
                          market_status="CLOSED", final_total=total)
        d = E.decide(ctx, snap, params)
        E.apply_decision(ctx, d, now_ts)
        if d.state == "SETTLING" and total is not None:
            d = E.decide(ctx, snap, params)      # stesso ciclo: SETTLING -> SETTLED
            E.apply_decision(ctx, d, now_ts)
        if d.state == "SETTLED":
            settled = 1
            _settle_trades(db, ev["event_id"], ctx, d.telemetry.get("settle") or {}, params)
            db.log("settled", {"total": total, "pnl": ctx.settled_pnl, **(d.telemetry.get("settle") or {})},
                   ev["event_id"])
        ev.update(_row_from_ctx(ev, ctx, extra))
        _persist(db, ev, before_sig)
        return (0, settled)
    if row is None or info is None or not info.complete:
        # C1 — la riga c'e' ma una delle due linee NON e' nel feed (tetto dei
        # mercati opportunita' dello scanner): con una posizione aperta questo
        # significa nessuna copertura, nessun cash out, nessuna uscita. Non si
        # inventa un prezzo: si GRIDA e lo si mostra sulla card.
        if info is not None and E.open_selections(ctx.legs):
            missing = [m for m in (E.MARKET_OU35, E.MARKET_OU45) if info.market_id(m) is None]
            _log_throttled(db, extra, params, now_ts, "feed_line_missing",
                           {"reason": "linee assenti dal feed", "markets": missing or ["selezioni"],
                            "state": ctx.state, "critical": True}, ev["event_id"])
            ev["live"] = {**(ev.get("live") or {}), "lines_missing": missing or ["selezioni"],
                          "feed_incomplete": True}
            ev.update(_row_from_ctx(ev, ctx, extra))
            _persist(db, ev, before_sig)
        return (0, 0)

    # -- snapshot dal feed --------------------------------------------------------
    goals = F.goals_from_payload(payload)
    if goals is not None and extra.get("last_goals") is not None and goals > int(extra["last_goals"]):
        extra["last_goal_ts"] = now_ts
    if goals is not None:
        extra["last_goals"] = goals
    if bool(payload.get("inplay")):
        extra["seen_inplay"] = True
    extra["selections"] = {f"{m}|{s}": sid for (m, s), sid in info.selections.items()}
    live = {}
    if bool(payload.get("inplay")):
        # punteggio dell'intervallo: fissato la prima volta che il feed dice "half time"
        if F.ht_active_from_payload(payload) and extra.get("ht_score") is None \
                and payload.get("score_home") is not None and payload.get("score_away") is not None:
            extra["ht_score"] = [int(payload["score_home"]), int(payload["score_away"])]
        ht_score = tuple(extra["ht_score"]) if extra.get("ht_score") else None
        empirical = D.get_empirical(dossier.get("league_id"), db, now_ts) if ht_score is not None else None
        live = D.live_frame(dossier, minute=payload.get("minute"), score_home=payload.get("score_home"),
                            score_away=payload.get("score_away"), red_home=payload.get("red_home") or 0,
                            red_away=payload.get("red_away") or 0, atlas=atlas, home=info.home, away=info.away,
                            payload=payload, wait_step_min=int(params.get("cover_wait_step_min", 5)),
                            ht_score=ht_score, empirical=empirical,
                            emp_min_n=int(params.get("loss_exit_emp_min_n", 200)))
    snap = F.snapshot_from_row(row, info, now=now_ts, params=params, scanner_age_s=scanner_age,
                               hazard=live.get("hazard"), p4_model=live.get("p4_model"),
                               last_goal_ts=extra.get("last_goal_ts"),
                               cover_gain_pct=live.get("cover_gain_pct"),
                               pressure=float(live.get("pressure") or 1.0),
                               model_probs=live.get("model_probs"),
                               p_total_model=live.get("p_total_model"), p_total_emp=live.get("p_total_emp"))
    if snap is None:
        return (0, 0)

    # -- C1: linee MANCANTI dal feed su una partita con posizione ------------------
    # Il tetto dei mercati opportunità dello scanner (20 eventi, i minuti più
    # avanzati) può lasciare una partita Mike senza blocco `ou`: senza la 4.5
    # non c'è copertura né cash out. Non si può inventare un prezzo: si GRIDA.
    if E.open_selections(ctx.legs):
        missing = [f"{m}|{s}" for (m, s) in E.live_open_selections(ctx.legs, snap.goals)
                   if snap.book(m, s) is None]
        if missing:
            _log_throttled(db, extra, params, now_ts, "feed_line_missing",
                           {"reason": "linee assenti dal feed", "selections": missing,
                            "state": ctx.state, "critical": True}, ev["event_id"])

    # -- gambe pending stantie (esito mai arrivato) --------------------------------
    # C3 — un ordine il cui esito e' IGNOTO (execution._reconciling →
    # meta.reason='place_exception_reconciling') NON viene MAI dato per "non
    # piazzato" e MAI marcato cancelled/error dal TTL: resta 'pending_reconcile'
    # (conta nel rischio, blocca il rientro) finche' non si riconcilia contro
    # Betfair. Solo le gambe con esito NOTO vengono ritirate.
    for leg in ctx.legs:
        if leg.is_live and now_ts - leg.placed_at > _PENDING_STALE_S and not _is_resting_leg(leg, params):
            # (la lay APPOGGIATA resta legittimamente sul book per ore: esclusa)
            if _trade_unknown_outcome(db, ev["event_id"], leg, cache):
                leg.status = E.STATUS_RECONCILE
                logger.critical("[mike] %s: gamba %s con esito REST IGNOTO → riconciliazione",
                                ev["event_id"], leg.ref)
                _log_throttled(db, extra, params, now_ts, "reconcile_pending",
                               {"leg": leg.ref, "reason": "pending_unknown_outcome",
                                "critical": True}, ev["event_id"])
                continue
            leg.status = "open" if leg.matched > 0 else "cancelled"
            _mark_trade_cancelled(db, ev["event_id"], leg, "pending_stale", cache)

    # -- C3/H8: gambe a esito IGNOTO -----------------------------------------------
    # Si tenta la riconciliazione con un THROTTLE (2 chiamate REST per evento:
    # senza freno erano 2 al secondo per evento) e il ciclo CONTINUA: restano
    # attive tutte le azioni che RIDUCONO il rischio (annulli, cash-out, uscite,
    # cap di perdita) — le APERTURE le toglie l'engine (`_strip_openings`).
    if E.has_unknown_orders(ctx):
        every = max(5.0, float(params.get("settle_confirm_s") or 30.0))
        if now_ts >= float(extra.get("reconcile_next_ts") or 0.0):
            extra["reconcile_next_ts"] = now_ts + every
            _reconcile_unknown(db, market, ev["event_id"], ctx, mode, now, cache)
        if E.has_unknown_orders(ctx):
            _log_throttled(db, extra, params, now_ts, "reconcile_pending",
                           {"legs": [l.ref for l in ctx.legs if l.needs_reconcile],
                            "state": ctx.state, "critical": True}, ev["event_id"])

    # -- lay APPOGGIATE (resting): fill simulato solo se il mercato scambia sotto ----
    # H3 — SOLO in paper: in live una lay appoggiata deve stare DAVVERO sul book
    # (REST senza FOK / coda flumine, F6). Simularla in live significherebbe
    # contabilizzare un profitto che non esiste.
    n_actions = 0
    for leg in ctx.legs:
        if leg.is_live and _is_resting_leg(leg, params):
            if mode != "paper":
                _log_throttled(db, extra, params, now_ts, "resting_live_unsupported",
                               {"leg": leg.ref, "role": leg.role,
                                "reason": "lay appoggiata non cablata in live: nessun fill simulato",
                                "critical": True}, ev["event_id"])
                continue
            book = snap.book(leg.market, leg.selection)
            if not snap.feed_fresh:
                continue        # M7: feed stantio = nessun fill simulato
            if _resting_filled(leg, book):
                leg.matched = float(leg.size)
                leg.avg_price = float(leg.price)
                leg.status = "open"
                r = _trade_row_for_leg(db, ev["event_id"], leg)
                if r is not None:
                    try:
                        db.update_trade(int(r["id"]), status="open", price=leg.price, size=leg.size,
                                        meta={**(r.get("meta") or {}), "phase": "open", "fill": "paper_resting"})
                    except Exception as ex:  # noqa: BLE001
                        logger.warning("[mike] conferma resting %s KO: %s", leg.ref, str(ex)[:120])
                db.log("fill_resting", {"leg": leg.ref, "role": leg.role, "price": leg.price, "size": leg.size,
                                        "best_back": book.best_back if book else None}, ev["event_id"])
                n_actions += 1

    # -- azioni differite (paper + in-play: betDelay) -------------------------------
    # H5: gli id delle righe servono SOLO per collegare una chiusura alla sua
    # apertura (closes_trade_id) → si leggono alla prima chiusura, non a ogni ciclo
    _ids_box: Dict[str, Dict[str, int]] = {}

    def closes_id(leg: E.Leg) -> Optional[int]:
        if not leg.closes_ref:
            return None
        if "v" not in _ids_box:
            _ids_box["v"] = _trade_ids_by_ref(db, ev["event_id"], cache)
        return _ids_box["v"].get(leg.closes_ref)

    score_str = f"{payload.get('score_home')}-{payload.get('score_away')}"
    deferred: List[Dict[str, Any]] = list(extra.get("deferred") or [])
    still: List[Dict[str, Any]] = []
    for item in deferred:
        leg = next((l for l in ctx.legs if l.ref == item["ref"]), None)
        if leg is None or not leg.is_live:
            continue
        if now_ts < float(item["earliest_at"]):
            still.append(item)
            continue
        book = snap.book(leg.market, leg.selection)
        if book is None:
            # buco momentaneo del feed: un ordine reale non sparirebbe → si ritenta
            # al ciclo dopo (review F1 #6), entro un limite di grazia
            if now_ts - float(item["earliest_at"]) < 30.0:
                still.append(item)
                continue
        execute_place(db=db, market=market, info=info, leg=leg, book=book,
                      mode=mode, params=params, now=now, dry=dry, minute=snap.minute,
                      score=score_str, feed_fresh=snap.feed_fresh,
                      close_reason=ctx.close_reason, closes_trade_id=closes_id(leg))
        n_actions += 1
    extra["deferred"] = still

    # -- decisione -----------------------------------------------------------------
    d = E.decide(ctx, snap, params)
    for a in d.actions:
        if a.kind == "cancel":
            leg = next((l for l in ctx.legs if l.ref == a.ref), None)
            if leg is not None and leg.is_live:
                leg.status = "open" if leg.matched > 0 else "cancelled"
                extra["deferred"] = [x for x in extra["deferred"] if x["ref"] != leg.ref]
                _mark_trade_cancelled(db, ev["event_id"], leg, "cancelled_by_engine", cache)
                db.log("cancel", {"leg": leg.ref, "role": leg.role}, ev["event_id"])
                n_actions += 1
    new_legs = E.apply_decision(ctx, d, now_ts)
    for leg in new_legs:
        book = snap.book(leg.market, leg.selection)
        delay = int(book.bet_delay) if (book and snap.inplay) else 0
        if _is_resting_leg(leg, params):
            # lay appoggiata: resta 'pending' sul book (riga riservata in mike_trades)
            # finche' il mercato non scambia sotto il suo prezzo (vedi _resting_filled)
            if dry:
                leg.status = "cancelled"
                db.log("would_place", {"leg": leg.ref, "role": leg.role, "side": "lay", "price": leg.price,
                                       "size": leg.size, "resting": True}, ev["event_id"])
            elif mode != "paper":
                # H3: in live non esiste una resting simulata (non ci si arriva:
                # _params_for forza 'taker') → mai una riga fantasma
                leg.status = "cancelled"
                db.log("resting_live_unsupported", {"leg": leg.ref, "role": leg.role,
                                                    "critical": True}, ev["event_id"])
            else:
                try:
                    _insert_trade_row(db, _trade_row(info, leg, mode, params, snap.minute, score_str,
                                                     closes_id(leg), ctx.close_reason),
                                      ev["event_id"])
                    db.log("place_resting", {"leg": leg.ref, "role": leg.role, "price": leg.price,
                                             "size": leg.size}, ev["event_id"])
                except Exception as ex:  # noqa: BLE001 — riserva fallita: nessun ordine
                    leg.status = "cancelled"
                    db.log("error", {"leg": leg.ref, "reason": "reserve_failed", "err": str(ex)[:160]}, ev["event_id"])
            n_actions += 1
            continue
        if mode == "paper" and delay > 0:
            extra["deferred"].append({"ref": leg.ref, "earliest_at": now_ts + delay})
            db.log("place_deferred", {"leg": leg.ref, "role": leg.role, "bet_delay": delay,
                                      "price": leg.price, "size": leg.size}, ev["event_id"])
        else:
            execute_place(db=db, market=market, info=info, leg=leg, book=book, mode=mode, params=params,
                          now=now, dry=dry, minute=snap.minute, score=score_str,
                          feed_fresh=snap.feed_fresh, close_reason=ctx.close_reason,
                          closes_trade_id=closes_id(leg))
        n_actions += 1
    if d.telemetry:
        for k, v in d.telemetry.items():
            # ``settle`` NON e' un kind di ATTIVITA': il regolamento lo scrive il
            # ramo "mercato chiuso" come 'settled', DOPO ``_settle_trades``.
            # Loggarlo da qui avrebbe prodotto un kind non dichiarato alla UI
            # (badge grigio in inglese) e un regolamento senza righe aggiornate.
            if k in ("pre_cycle", "cover", "cover_wait", "cashout", "close_retries_exhausted", "loss_exit"):
                if k == "cashout":
                    extra["last_cashout"] = v
                elif k == "cover_wait":
                    extra["last_cover_wait"] = v
                elif k == "loss_exit":
                    extra["last_loss_exit"] = v
                else:
                    db.log(k, v if isinstance(v, dict) else {"value": v}, ev["event_id"])
    # H5 — il log 'state' si scrive SOLO quando lo stato cambia davvero: prima
    # bastava un motivo con numeri diversi (prezzi, minuti) per riscriverlo a
    # ogni tick e riempire mike_activity.
    if d.state != ev.get("state"):
        db.log("state", {"from": ev.get("state"), "to": d.state, "reason": d.reason}, ev["event_id"])
    extra["last_reason"] = d.reason

    # -- persistenza (write-on-change) --------------------------------------------
    c_rate = C.commission_rate(params)
    cv_now = E.cashout_value(ctx.legs, snap.books, c_rate,
                             int(params["cashout_place_at_ticks"]), goals=snap.goals)
    base_now = E.cashout_base(ctx, params)
    # M5 — "se chiudo ora" SEMPRE netto commissione lato servizio: la UI non deve
    # piu' calcolare nulla (prima mescolava lordo del servizio e netto del client).
    cashout_live = {
        "net": cv_now.net, "gross": cv_now.gross, "base": round(base_now, 2),
        "complete": cv_now.complete, "commission": round(c_rate, 4),
        "per": {f"{m}|{s}": v for (m, s), v in cv_now.per_selection_net.items()},
        "per_gross": {f"{m}|{s}": v for (m, s), v in cv_now.per_selection.items()},
        "decided": [f"{m}|{s}" for (m, s) in cv_now.decided],
        "pct": round(100.0 * cv_now.net / base_now, 2) if base_now > 0 else None,
        "target_pct": float(params["cashout_profit_pct"]),
    }
    if extra.get("last_cashout"):
        cashout_live["smart"] = (extra.get("last_cashout") or {}).get("smart")
    ev["live"] = {"minute": snap.minute, "goals": snap.goals, "inplay": snap.inplay, "ht": snap.ht_active,
                  "score_home": payload.get("score_home"), "score_away": payload.get("score_away"),
                  # C1/H6 — diagnostica sempre visibile: eta' del feed per EVENTO,
                  # linee mancanti e riconciliazione in corso
                  "feed_age_s": round(max(0.0, now_ts - (F.parse_iso_epoch(row.get("updated_at")) or now_ts)), 1),
                  "scanner_age_s": round(scanner_age, 1) if scanner_age is not None else None,
                  "lines_missing": [f"{m}|{s}" for (m, s) in
                                    ((E.MARKET_OU35, E.SEL_UNDER), (E.MARKET_OU45, E.SEL_OVER),
                                     (E.MARKET_OU45, E.SEL_UNDER))
                                    if snap.book(m, s) is None],
                  "reconcile_pending": E.has_unknown_orders(ctx),
                  "liability": E.event_liability(ctx.legs, c_rate),
                  "locked": E.locked_pnl(ctx.legs, c_rate),
                  "no_reentry": bool(extra.get("no_reentry")),
                  "total_matched": snap.total_matched,
                  "red_home": payload.get("red_home") or 0, "red_away": payload.get("red_away") or 0,
                  "model_probs": live.get("model_probs"), "ht_score": extra.get("ht_score"),
                  "p_total_model": live.get("p_total_model"), "p_total_emp": live.get("p_total_emp"),
                  "loss_exit": extra.get("last_loss_exit"),
                  "hazard": snap.hazard, "hazard_atlas": live.get("hazard_atlas"),
                  "hazard_model": live.get("hazard_model"), "pressure": live.get("pressure"),
                  "cover_gain_pct": live.get("cover_gain_pct"), "p_over45_model": live.get("p_over45_model"),
                  "p4_market": snap.p4_market, "p4_model": snap.p4_model,
                  "cashout": cashout_live, "cover_wait": extra.get("last_cover_wait"),
                  "pnl_by_total": E.net_pnl_by_total(ctx.legs, C.commission_rate(params)),
                  "books": {f"{m}|{s}": dataclasses.asdict(b) for (m, s), b in snap.books.items()},
                  "feed_fresh": snap.feed_fresh}
    ev.update(_row_from_ctx(ev, ctx, extra))
    _persist(db, ev, before_sig)
    return (n_actions, settled)


def _event_rows(db: Any, event_id: str, cache: Optional[Dict[str, List[Dict[str, Any]]]] = None
                ) -> Optional[List[Dict[str, Any]]]:
    """Righe ``mike_trades`` della partita, lette UNA volta per ciclo (H5).

    C1 — ``None`` = LETTURA FALLITA, mai messa in cache e mai confusa con
    "nessuna riga": interpretare un errore di rete come tabella vuota portava la
    riconciliazione a REINSERIRE una riga per ogni gamba abbinata (righe doppie
    con lo stesso signal_key → P&L e stop giornaliero raddoppiati).
    """
    if cache is not None and str(event_id) in cache:
        return cache[str(event_id)]
    try:
        rows = list(db.trades_for_event(str(event_id)) or [])
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] trades_for_event %s KO: %s", event_id, str(ex)[:120])
        return None
    if cache is not None:
        cache[str(event_id)] = rows
    return rows


def _trade_ids_by_ref(db: Any, event_id: str,
                      cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Dict[str, int]:
    """{leg.ref: id della riga mike_trades} — serve a scrivere ``closes_trade_id`` (H4)."""
    out: Dict[str, int] = {}
    for r in _event_rows(db, event_id, cache) or []:
        key = r.get("signal_key")
        if key and r.get("id") is not None:
            out[str(key)] = int(r["id"])
    return out


def _trade_row_for_leg(db: Any, event_id: str, leg: E.Leg,
                       cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Optional[Dict[str, Any]]:
    for r in _event_rows(db, event_id, cache) or []:
        if str(r.get("signal_key")) == leg.ref:
            return r
    return None


def _trade_unknown_outcome(db: Any, event_id: str, leg: E.Leg,
                           cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> bool:
    """Esito dell'ordine IGNOTO? FAIL-CLOSED (H2): se la riga mirror non si riesce
    a leggere si risponde SI'. Un dubbio non si risolve mai cancellando una
    gamba che potrebbe essere un ordine reale vivo."""
    rows = _event_rows(db, event_id, cache)
    if rows is None:
        logger.critical("[mike] %s: righe illeggibili, gamba %s trattata come esito IGNOTO",
                        event_id, leg.ref)
        return True
    r = next((x for x in rows if str(x.get("signal_key")) == leg.ref), None)
    if r is None:
        return True                      # nessuno specchio: non si sa nulla dell'ordine
    meta = r.get("meta") or {}
    return str(meta.get("reason") or "") == "place_exception_reconciling"


def _open_refs_by_event(db: Any) -> Optional[Dict[str, set]]:
    """{event_id: {signal_key delle righe NON terminali}} con UNA query (H5).

    Serve come pre-controllo della riconciliazione: se lo specchio combacia non
    si legge nulla per quella partita. ``None`` se la lettura fallisce (allora
    si riconcilia leggendo partita per partita, come prima)."""
    try:
        rows = db.open_trades() or []
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] open_trades KO: %s", str(ex)[:120])
        return None
    out: Dict[str, set] = {}
    for r in rows:
        eid = str(r.get("event_id") or "")
        key = r.get("signal_key")
        if eid and key:
            out.setdefault(eid, set()).add(str(key))
    return out


def _mirror_is_aligned(ctx: E.MatchCtx, open_refs: Optional[Dict[str, set]], event_id: str) -> bool:
    """True se lo specchio righe/gambe combacia: nessuna lettura necessaria."""
    if open_refs is None:
        return False
    idx = open_refs.get(str(event_id), set())
    expected = {l.ref for l in ctx.legs
                if not l.archived and (float(l.matched) > 0 or l.needs_reconcile)}
    all_refs = {l.ref for l in ctx.legs}
    return not (expected - idx) and not (idx - all_refs)


def _reconcile_trades(db: Any, event_id: str, ctx: E.MatchCtx, info: Optional[F.EventInfo],
                      mode: str, params: Dict[str, Any],
                      cache: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                      open_refs: Optional[Dict[str, set]] = None) -> int:
    """H2 — riconciliazione ``mike_trades`` <-> ``mike_events.positions`` a OGNI ciclo.

    Due buchi possibili dopo un crash o una scrittura DB fallita:
      * GAMBA senza riga (la riserva non e' stata scritta ma l'ordine esiste):
        la riga viene RISCRITTA dalla gamba (mai una posizione invisibile);
      * RIGA senza gamba (stato partita perso): in paper e' una riga zombie e
        viene chiusa in errore; in live potrebbe essere una posizione REALE →
        marcata ``meta.orphan`` e loggata come critica, mai toccata in silenzio.

    H5: se l'indice delle righe non terminali (UNA query per ciclo) combacia con
    le gambe, non si legge nulla — nessuna query per partita.
    """
    if _mirror_is_aligned(ctx, open_refs, event_id):
        return 0
    rows = _event_rows(db, event_id, cache)
    if rows is None:
        # C1: lettura FALLITA != nessuna riga. Non si tocca NULLA: reinserire
        # righe su un errore di rete significava P&L doppio.
        db.log("reconcile_pending", {"reason": "righe_illeggibili",
                                     "note": "nessuna riparazione: si riprova al ciclo dopo",
                                     "critical": True}, event_id)
        return 0
    by_ref = {str(r.get("signal_key")): r for r in rows if r.get("signal_key")}
    fixed = 0
    for leg in ctx.legs:
        if leg.ref in by_ref or leg.archived:
            continue
        # Solo le gambe che portano un'esposizione REALE o un ordine di cui non
        # si conosce l'esito: la riserva si scrive PRIMA dell'ordine, quindi una
        # gamba pending senza riga (ordine differito dal betDelay, riserva
        # fallita) non ha nessun ordine dietro e non va ricostruita.
        if float(leg.matched) <= 0 and not leg.needs_reconcile:
            continue
        if info is None or not info.complete:
            continue
        row = _trade_row(info, leg, mode, params, None, None, None, ctx.close_reason)
        if leg.matched > 0:
            row.update({"status": "open", "size": round(float(leg.matched), 2),
                        "price": leg.fill_price})
        row["meta"] = {**row["meta"], "phase": "reconstructed", "reconciled": True}
        try:
            _insert_trade_row(db, row, event_id)
            fixed += 1
            db.log("reconcile_fix", {"leg": leg.ref, "action": "riga_ricostruita",
                                     "status": row["status"], "critical": True}, event_id)
        except Exception as ex:  # noqa: BLE001
            logger.warning("[mike] reconcile insert %s KO: %s", leg.ref, str(ex)[:120])
    refs = {l.ref for l in ctx.legs}
    for ref, r in by_ref.items():
        # M9: riferimento alla riga di apertura rimasto in meta perche' la colonna
        # non esisteva ancora → ora che c'e' si ribalta in colonna
        pending_link = (r.get("meta") or {}).get("closes_trade_id_pending")
        if pending_link and not r.get("closes_trade_id"):
            meta_l = {k: v for k, v in (r.get("meta") or {}).items()
                      if k != "closes_trade_id_pending"}
            try:
                db.update_trade(int(r["id"]), closes_trade_id=int(pending_link), meta=meta_l)
                fixed += 1
                db.log("reconcile_fix", {"leg": ref, "trade_id": r.get("id"),
                                         "action": "closes_trade_id_ripristinato",
                                         "closes_trade_id": int(pending_link)}, event_id)
            except Exception as ex:  # noqa: BLE001 — colonna ancora assente: si riprova
                logger.debug("[mike] ribaltamento closes_trade_id %s KO: %s", ref, str(ex)[:120])
        if ref in refs or r.get("closes_trade_id"):
            continue
        status = str(r.get("status") or "")
        if status not in ("pending", "open", "hedged"):
            continue
        meta = dict(r.get("meta") or {})
        if meta.get("orphan"):
            continue
        meta["orphan"] = True
        try:
            if mode == "paper":
                # M2: in PAPER non esiste nessun ordine reale dietro una riga
                # senza gamba: e' una zombie e va chiusa (anche 'open'/'hedged',
                # altrimenti resta per sempre nella liability e nei KPI).
                meta["reason"] = "orphan_paper"
                db.update_trade(int(r["id"]), status="error", meta=meta)
            else:
                # in LIVE potrebbe essere una posizione REALE: solo marcata
                db.update_trade(int(r["id"]), meta=meta)
        except Exception as ex:  # noqa: BLE001
            logger.warning("[mike] reconcile orphan %s KO: %s", ref, str(ex)[:120])
            continue
        fixed += 1
        db.log("reconcile_fix", {"leg": ref, "trade_id": r.get("id"), "action": "riga_orfana",
                                 "status": status, "mode": mode, "critical": True}, event_id)
    if fixed and cache is not None:
        cache.pop(str(event_id), None)
    return fixed


def _reconcile_unknown(db: Any, market: Any, event_id: str, ctx: E.MatchCtx, mode: str,
                       now: datetime, cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> int:
    """C3 — prova a chiudere il dubbio su una gamba a esito IGNOTO.

    PAPER: nessun ordine e' mai partito verso Betfair (l'eccezione viene dal
    fill simulato) → la gamba si risolve subito come non abbinata.
    LIVE: si interroga Betfair per ``customerOrderRef`` (``mike-t<id>``):
    confermata (abbinata), liberata (mai esistita) o si resta in attesa. Senza
    accesso a ``listCurrentOrders`` si RESTA in riconciliazione: mai un'ipotesi.
    """
    pend = [l for l in ctx.legs if l.needs_reconcile]
    if not pend:
        return 0
    current: List[dict] = []
    cleared: List[dict] = []
    if mode == "live":
        try:
            current = list(market.list_current_orders() or [])
            cleared = list(market.list_cleared_orders() or [])
        except Exception as ex:  # noqa: BLE001 — nessuna ipotesi: si resta in attesa
            db.log("reconcile_pending", {"reason": "betfair_non_raggiungibile",
                                         "err": str(ex)[:120], "critical": True}, event_id)
            return 0
    n = 0
    now_iso = now.isoformat()
    for leg in pend:
        r = _trade_row_for_leg(db, event_id, leg, cache)
        if r is None:
            continue
        if mode == "paper":
            dec = {"action": "free"}
        else:
            dec = X.reconcile_decision(r, current, cleared, now_iso, ref=f"mike-t{r['id']}")
        action = str(dec.get("action") or "keep")
        if action == "confirm":
            leg.matched = float(dec.get("size") or leg.size)
            leg.avg_price = float(dec.get("price") or leg.price)
            leg.status = "open"
            try:
                db.update_trade(int(r["id"]), status="open", price=leg.avg_price,
                                size=round(leg.matched, 2),
                                liability=X.liability_of(leg.side, leg.matched, leg.avg_price or 0.0),
                                bet_id=dec.get("bet_id"),
                                meta={**(r.get("meta") or {}), "phase": "open", "reason": "reconciled",
                                      "reconciled": True})
            except Exception as ex:  # noqa: BLE001
                logger.critical("[mike] conferma riconciliazione %s KO: %s", leg.ref, str(ex)[:120])
            db.log("reconcile_fix", {"leg": leg.ref, "action": "confermata", "size": leg.matched,
                                     "price": leg.avg_price, "critical": True}, event_id)
            n += 1
        elif action in ("free", "error"):
            leg.status = "cancelled"
            try:
                db.update_trade(int(r["id"]), status="error",
                                meta={**(r.get("meta") or {}), "phase": "cancelled",
                                      "reason": "reconciled_not_placed", "reconciled": True})
            except Exception as ex:  # noqa: BLE001
                logger.warning("[mike] chiusura riconciliazione %s KO: %s", leg.ref, str(ex)[:120])
            db.log("reconcile_fix", {"leg": leg.ref, "action": "mai_piazzata", "mode": mode},
                   event_id)
            n += 1
        else:
            db.log("reconcile_pending", {"leg": leg.ref, "action": "attesa", "critical": True},
                   event_id)
    if n and cache is not None:
        cache.pop(str(event_id), None)
    return n


def _mark_trade_cancelled(db: Any, event_id: str, leg: E.Leg, reason: str,
                          cache: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
    """Allinea la riga mike_trades a una gamba ritirata (review F1 #4): mai 'pending' per sempre."""
    r = _trade_row_for_leg(db, event_id, leg, cache)
    if not r or str(r.get("status")) not in ("pending",):
        return
    try:
        meta = dict(r.get("meta") or {})
        meta.update({"phase": "cancelled", "reason": reason})
        if leg.matched > 0:
            db.update_trade(int(r["id"]), status="open", size=round(leg.matched, 2),
                            price=leg.fill_price, meta=meta)
        else:
            db.update_trade(int(r["id"]), status="error", meta=meta)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] mark cancelled %s KO: %s", leg.ref, str(ex)[:120])


def _settle_trades(db: Any, event_id: str, ctx: E.MatchCtx, settle: Dict[str, Any],
                   params: Optional[Dict[str, Any]] = None) -> None:
    """Riporta l'esito per gamba sulle righe mike_trades (signal_key = leg.ref).

    H4 — il ``pnl`` scritto su ogni riga e' NETTO commissione (la somma delle
    righe = ``settled_pnl`` della partita).
    L-08 — ``meta.commission_paid`` viene SCRITTA davvero (quota di commissione
    del mercato attribuita alla riga): lo storico non deve piu' stimarla.
    """
    per_leg = {ref: (st, pnl) for ref, st, pnl in (settle.get("per_leg") or [])}
    gross_leg = {ref: pnl for ref, _st, pnl in (settle.get("per_leg_gross") or [])}
    comm_market = dict(settle.get("commission_by_market") or {})
    legs_by_ref = {l.ref: l for l in ctx.legs}
    try:
        rows = db.trades_for_event(str(event_id))
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "settle_rows_failed", "err": str(ex)[:160]}, event_id)
        return
    now_iso = _now().isoformat()
    # C1 — DEDUP per signal_key: se per qualunque motivo esistono due righe per
    # la stessa gamba, il P&L si scrive UNA volta sola (sulla piu' vecchia) e le
    # altre vengono chiuse in errore. Senza, realized/stop/storico raddoppiano.
    seen: Dict[str, Dict[str, Any]] = {}
    for r in sorted(rows, key=lambda x: int(x.get("id") or 0)):
        ref0 = str(r.get("signal_key") or "")
        if not ref0 or ref0 not in per_leg or str(r.get("status")) in ("won", "lost", "void", "error"):
            continue
        if ref0 in seen:
            meta_d = dict(r.get("meta") or {})
            meta_d.update({"duplicate_of": seen[ref0].get("id"), "reason": "duplicate_signal_key"})
            try:
                db.update_trade(int(r["id"]), status="error", pnl=0.0, meta=meta_d)
            except Exception as ex:  # noqa: BLE001
                logger.warning("[mike] dedup riga %s KO: %s", r.get("id"), str(ex)[:120])
            logger.critical("[mike] %s: riga DOPPIA per %s (id %s, tenuta %s)", event_id, ref0,
                            r.get("id"), seen[ref0].get("id"))
            db.log("error", {"reason": "duplicate_signal_key", "leg": ref0,
                             "trade_id": r.get("id"), "kept": seen[ref0].get("id"),
                             "critical": True}, event_id)
            continue
        seen[ref0] = r
    for r in rows:
        if str(r.get("status")) in ("won", "lost", "void", "error"):
            continue
        ref = str(r.get("signal_key"))
        res = per_leg.get(ref)
        if res is None or seen.get(ref) is not r:
            continue
        st, pnl = res
        meta = dict(r.get("meta") or {})
        gross = gross_leg.get(ref)
        if gross is not None:
            meta["pnl_gross"] = round(float(gross), 2)
            meta["commission_paid"] = round(max(0.0, float(gross) - float(pnl)), 2)
        leg = legs_by_ref.get(ref)
        if leg is not None and leg.market in comm_market:
            meta["commission_market"] = round(float(comm_market[leg.market]), 2)
        if settle.get("void"):
            meta["void_reason"] = "mercato_annullato"
        try:
            db.update_trade(int(r["id"]), status=st, pnl=round(float(pnl), 2), settled_at=now_iso,
                            meta=meta)
        except Exception as ex:  # noqa: BLE001
            db.log("error", {"reason": "settle_update_failed", "trade_id": r.get("id"), "err": str(ex)[:120]},
                   event_id)


def _persist(db: Any, ev: Dict[str, Any], before_sig: str) -> None:
    if _signature(ev) == before_sig:
        return
    try:
        db.upsert_event(ev)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] upsert_event %s KO: %s", ev.get("event_id"), str(ex)[:160])


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    from Betfair.stream.single_instance import acquire_single_instance_lock

    parser = argparse.ArgumentParser(description="Bot Mike (Under 3.5 / Over 4.5)")
    parser.add_argument("--once", action="store_true", help="un ciclo e esce")
    parser.add_argument("--dry", action="store_true", help="nessun ordine (would_place)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    lock = None
    if not args.once:
        lock = acquire_single_instance_lock(_LOCK_PORT, "mike")
    logger.info("[mike] servizio avviato (lock %s, dry=%s)", _LOCK_PORT, args.dry)
    atlas = D.load_atlas()
    try:
        while True:
            interval = 2.0
            try:
                ctrl = _real_db.read_control() or {}
                params = C.merge_params(ctrl.get("params"))
                interval = max(1.0, float(params.get("decide_min_interval_ms", 500)) / 1000.0 * 2)
                res = run_once(atlas=atlas, dry=args.dry)
                if res.get("new") or res.get("actions") or res.get("settled") or res.get("requests"):
                    logger.info("[mike] ciclo: %s", {k: res[k] for k in ("new", "actions", "settled", "requests")})
                if args.once:
                    logger.info("[mike] --once: %s", res)
                    break
            except KeyboardInterrupt:
                break
            except Exception as ex:  # noqa: BLE001 — il loop non deve morire
                logger.exception("[mike] errore di ciclo: %s", str(ex)[:200])
                try:
                    _real_db.log("error", {"reason": "cycle_exception", "err": str(ex)[:200]})
                except Exception:  # noqa: BLE001
                    pass
                if args.once:
                    break
            time.sleep(interval)
    finally:
        if lock is not None:
            try:
                lock.close()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    main()
