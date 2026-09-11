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
from datetime import datetime, timezone
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
_PENDING_STALE_S = 120.0          # gamba pending senza esito da troppo → cancellata (mai zombie)
_SETTLE_RETRY_S = 30.0            # fra due letture REST di regolamento (mercato gia' chiuso)
_SETTLE_MAX_WAIT_S = 2 * 3600.0   # oltre: fallback sull'ultimo punteggio noto o ERROR
_DAILY_STOP_LOGGED: Dict[str, str] = {}   # {"day": iso} → lo stop giornaliero si logga una volta al giorno
_STRATEGY_REF = C.CUSTOMER_STRATEGY_REF

ACTIVE_STATES = tuple(s for s in E.STATES if s not in E.TERMINAL_STATES)


# ---------------------------------------------------------------------------
# Market REST (solo settlement / fallback): sessione CONDIVISA di omega_market
# ---------------------------------------------------------------------------
class _RealMarket:
    @staticmethod
    def read_book(market_id: str, names: Dict[int, str]) -> Optional[dict]:
        from Betfair.omega import omega_market

        return omega_market.read_book(str(market_id), names)

    @staticmethod
    def place_order_live(**kw: Any) -> Any:
        from Betfair.omega import omega_market

        return omega_market.place_order_live(**kw)


_real_market = _RealMarket()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: Optional[float]) -> Optional[str]:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat() if ts else None


# ---------------------------------------------------------------------------
# Serializzazione stato partita (mike_events) ⇄ MatchCtx
# ---------------------------------------------------------------------------
def _legs_from_json(raw: Any) -> List[E.Leg]:
    out: List[E.Leg] = []
    for d in raw or []:
        if not isinstance(d, dict):
            continue
        try:
            fields = {f.name for f in dataclasses.fields(E.Leg)}
            out.append(E.Leg(**{k: v for k, v in d.items() if k in fields}))
        except TypeError:
            continue
    return out


def _ctx_from_row(row: Dict[str, Any]) -> E.MatchCtx:
    extra = row.get("ctx") or {}
    ctx = E.MatchCtx(state=str(row.get("state") or "WATCH"), legs=_legs_from_json(row.get("positions")),
                     cycle_no=int(row.get("cycle_no") or 0),
                     entry_price_initial=row.get("entry_price_initial"))
    for k in ("last_green_at", "last_action_at", "attempts", "reentry_allowed", "reentry_done",
              "close_reason", "cover_skipped", "seq"):
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
    keep.update({k: getattr(ctx, k) for k in ("last_green_at", "last_action_at", "attempts", "reentry_allowed",
                                               "reentry_done", "close_reason", "cover_skipped", "seq")})
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
               minute: Optional[int], score: Optional[str]) -> Dict[str, Any]:
    sid = info.selection_id(leg.market, leg.selection)
    liability = round(leg.size * (leg.price - 1.0), 2) if leg.side == "lay" else round(leg.size, 2)
    return {
        "event_id": info.event_id, "event_name": info.event_name, "sport": "calcio",
        "strategy": leg.role, "role": leg.role, "cycle_no": int(leg.cycle_no),
        "market_id": info.market_id(leg.market), "market_type": C.OU35 if leg.market == E.MARKET_OU35 else C.OU45,
        "selection_id": int(sid) if sid is not None else None,
        "selection_name": info.selection_name(leg.market, leg.selection),
        "side": leg.side, "mode": mode, "price": leg.price, "size": leg.size, "liability": liability,
        "commission": C.commission_rate(params), "persistence": leg.persistence,
        "minute_at_entry": minute, "score_at_entry": score, "status": "pending", "pnl": 0.0,
        "origin": "auto", "signal_key": leg.ref,
        "meta": {"phase": "reserved", "leg_ref": leg.ref, "final": bool(leg.final)},
    }


def execute_place(*, db: Any, market: Any, info: F.EventInfo, leg: E.Leg, book: Optional[E.Book],
                  mode: str, params: Dict[str, Any], now: datetime, dry: bool,
                  minute: Optional[int] = None, score: Optional[str] = None) -> str:
    """Piazza la gamba (reserve-first). Ritorna 'open' | 'cancelled' | 'pending'.

    Regola prezzo TAKER: il fill avviene al prezzo richiesto solo se ANCORA
    disponibile (back: best_back ≥ prezzo; lay: best_lay ≤ prezzo); altrimenti
    nessun fill (mai piu' ottimista del live). La size e' cappata alla size al best.
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
    row = _trade_row(info, leg, mode, params, minute, score)
    try:
        trade_id = db.insert_trade(row)
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
def final_total_from_books(b35: Optional[dict], b45: Optional[dict], info: F.EventInfo) -> Optional[int]:
    """Somma gol RAPPRESENTATIVA (3 | 4 | 5) dagli esiti dei runner, o None se non regolati."""
    def winner(book: Optional[dict], market: str) -> Optional[str]:
        if not book or str(book.get("status") or "").upper() != "CLOSED":
            return None
        for r in book.get("runners") or []:
            if str(r.get("status") or "").upper() == "WINNER":
                sid = int(r.get("selection_id"))
                if sid == info.selection_id(market, E.SEL_UNDER):
                    return E.SEL_UNDER
                if sid == info.selection_id(market, E.SEL_OVER):
                    return E.SEL_OVER
        return None
    w35, w45 = winner(b35, E.MARKET_OU35), winner(b45, E.MARKET_OU45)
    if w35 == E.SEL_UNDER:
        return 3
    if w45 == E.SEL_OVER:
        return 5
    if w35 == E.SEL_OVER and w45 == E.SEL_UNDER:
        return 4
    return None


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
    In LIVE senza coda flumine la lay appoggiata (resting) non e' ancora cablata
    (REST senza FOK + polling: F6) → si ripiega sulla chiusura taker."""
    p = dict(params)
    if mode == "live" and p.get("pre_exit_mode") == "resting" and not C.env_bool("MIKE_USE_FLUMINE_QUEUE", False):
        p["pre_exit_mode"] = "taker"
    if running:
        return p
    p["pre_enabled"] = False
    p["reentry_enabled"] = False
    p["last_entry_persist"] = False
    return p


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


def process_requests(*, db: Any, market: Any, events: Dict[str, Dict[str, Any]],
                     rows_by_event: Dict[str, Dict[str, Any]], params: Dict[str, Any],
                     now: datetime, dry: bool) -> int:
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
                res = {"error": "evento_non_seguito"}
            elif kind in ("skip_event", "resume_event", "cashout", "flatten") and \
                    str(ev.get("state")) in ("SETTLED", "ERROR") and kind != "resume_event":
                res = {"error": f"stato terminale {ev.get('state')}"}
            elif kind in ("cashout", "flatten"):
                res = _request_flatten(db, market, ev, rows_by_event.get(eid), params, now, dry)
            elif kind == "skip_event":
                ctx = _ctx_from_row(ev)
                if E.open_selections(ctx.legs) or any(l.is_live for l in ctx.legs):
                    res = {"error": "posizione_aperta: prima chiudi (cashout)"}
                else:
                    ctx.state = "SKIPPED"
                    events[eid] = _row_from_ctx(ev, ctx, dict(ev.get("ctx") or {}))
                    events[eid]["skipped"] = True
                    db.upsert_event(events[eid])      # terminale: il ciclo partita non persiste
                    res = {"ok": True, "state": "SKIPPED"}
            elif kind == "resume_event":
                ctx = _ctx_from_row(ev)
                if ctx.state == "SKIPPED":
                    ctx.state = "WATCH"
                    events[eid] = _row_from_ctx(ev, ctx, dict(ev.get("ctx") or {}))
                    events[eid]["skipped"] = False
                    db.upsert_event(events[eid])
                    res = {"ok": True, "state": "WATCH"}
                else:
                    res = {"error": f"stato {ctx.state} non riprendibile"}
            else:
                res = {"error": f"kind_non_valido:{kind}"}
        except Exception as ex:  # noqa: BLE001
            res = {"error": str(ex)[:160]}
        db.set_request_status(rid, "error" if res.get("error") else "done", res)
        n += 1
    return n


def _request_flatten(db: Any, market: Any, ev: Dict[str, Any], row: Optional[Dict[str, Any]],
                     params: Dict[str, Any], now: datetime, dry: bool) -> Dict[str, Any]:
    ctx = _ctx_from_row(ev)
    info = F.event_info(ev["event_id"], (row or {}).get("payload") or {})
    if row is None or not info.complete:
        return {"error": "feed_assente"}
    snap = F.snapshot_from_row(row, info, now=now.timestamp(), params=params, scanner_age_s=0.0)
    if snap is None:
        return {"error": "snapshot_assente"}
    actions = E.force_flat_actions(ctx, snap.books, params)
    if not actions:
        return {"ok": True, "note": "nulla da chiudere"}
    ctx.close_reason = "manual"
    d = E.Decision(state="LIVE_CLOSING" if snap.inplay else "PRE_GREEN_PENDING", actions=actions,
                   reason="chiusura manuale", updates={"close_reason": "manual", "attempts": 0})
    new_legs = E.apply_decision(ctx, d, snap.now)
    results = []
    for leg in new_legs:
        leg.role = "manual_close" if leg.role in ("under_close", "over_close") else leg.role
        results.append(execute_place(db=db, market=market, info=info, leg=leg,
                                     book=snap.book(leg.market, leg.selection), mode=str(ev.get("mode") or "paper"),
                                     params=params, now=now, dry=dry, minute=snap.minute))
    ev.update(_row_from_ctx(ev, ctx, {}))
    return {"ok": True, "legs": len(new_legs), "results": results}


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

    # STOP giornaliero: P&L realizzato della giornata operativa <= -daily_loss_stop
    # → nessuna partita nuova, nessun ingresso pre-match ne' re-ingresso; le
    # chiusure (cash-out, uscite, regolamento, richieste UI) restano attive.
    try:
        agg = db.aggregates(now)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] aggregates KO: %s", str(ex)[:160])
        agg = {}
    stop = float(params.get("daily_loss_stop") or 0.0)
    daily_stop = stop > 0 and float(agg.get("realized_today", 0.0)) <= -stop
    if daily_stop:
        eff = dict(eff, pre_enabled=False, reentry_enabled=False)
        day_key = now.date().isoformat()
        if _DAILY_STOP_LOGGED.get("day") != day_key:
            _DAILY_STOP_LOGGED["day"] = day_key
            logger.warning("[mike] STOP giornaliero: P&L oggi %.2f <= -%.2f", float(agg.get("realized_today", 0.0)), stop)
            db.log("daily_stop", {"realized_today": round(float(agg.get("realized_today", 0.0)), 2), "stop": stop})

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

    n_requests = process_requests(db=db, market=market, events=tracked, rows_by_event=rows_by_event,
                                  params=params, now=now, dry=dry)

    # nuove candidate (solo a bot in esecuzione, sotto il tetto partite)
    n_new = 0
    if running and not daily_stop:
        active = sum(1 for e in tracked.values() if e.get("state") not in E.TERMINAL_STATES)
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
    for eid, ev in list(tracked.items()):
        try:
            acted, settled = _run_event(db=db, market=market, ev=ev, row=rows_by_event.get(eid),
                                        params=eff, mode=str(ev.get("mode") or mode), now=now,
                                        scanner_age=scanner_age, atlas=atlas, dry=dry)
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
    by_state: Dict[str, int] = {}
    for e in tracked.values():
        by_state[str(e.get("state"))] = by_state.get(str(e.get("state")), 0) + 1
    stats = {
        "events_feed": len(rows_by_event), "events_tracked": len(tracked), "by_state": by_state,
        "trades_open": int(agg.get("open_count", 0)), "open_liability": round(float(agg.get("open_liability", 0.0)), 2),
        "realized_today": round(float(agg.get("realized_today", 0.0)), 2),
        "realized_total": round(float(agg.get("realized_total", 0.0)), 2),
        "scanner_age_s": round(scanner_age, 1) if scanner_age is not None else None,
        "last_cycle": now.isoformat(), "dry": bool(dry), "mode": mode, "daily_stop": bool(daily_stop),
    }
    try:
        db.set_control(stats=stats, heartbeat_at=now.isoformat())
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] set_control KO: %s", str(ex)[:160])
    return {"status": status, "new": n_new, "actions": n_actions, "settled": n_settled,
            "requests": n_requests, "stats": stats}


def _run_event(*, db: Any, market: Any, ev: Dict[str, Any], row: Optional[Dict[str, Any]],
               params: Dict[str, Any], mode: str, now: datetime, scanner_age: Optional[float],
               atlas: Optional[Dict[str, Any]], dry: bool) -> "tuple[int, int]":
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

    # -- riga sparita dal feed o mercato chiuso: settlement via REST -------------
    closed = row is None or str((F.ou_blocks(payload).get(E.MARKET_OU35) or {}).get("status") or
                                payload.get("mo_status") or "").upper() == "CLOSED"
    if closed and ctx.state not in E.TERMINAL_STATES:
        if row is None and not extra.get("seen_inplay") and (F.parse_iso_epoch(ev.get("ko_at")) or 0) > now_ts:
            # non ancora iniziata e uscita dal feed (fuori finestra?) → attendo
            return (0, 0)
        # throttle delle letture REST di regolamento (review F1 #3): mai un poll
        # stretto su un mercato chiuso; dopo troppo tempo si ripiega sull'ultimo
        # punteggio noto o si va in ERROR (mai SETTLING per sempre)
        if now_ts < float(extra.get("settle_next_ts") or 0.0):
            return (0, 0)
        extra["settle_next_ts"] = now_ts + _SETTLE_RETRY_S
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
            _settle_trades(db, ev["event_id"], ctx, d.telemetry.get("settle") or {})
            db.log("settled", {"total": total, "pnl": ctx.settled_pnl, **(d.telemetry.get("settle") or {})},
                   ev["event_id"])
        ev.update(_row_from_ctx(ev, ctx, extra))
        _persist(db, ev, before_sig)
        return (0, settled)
    if row is None or info is None or not info.complete:
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

    # -- gambe pending stantie (esito mai arrivato): mai zombie ---------------------
    # FAIL-CLOSED (review F1 #1): un ordine LIVE il cui esito REST e' IGNOTO
    # (execution._reconciling → meta.reason='place_exception_reconciling') NON viene
    # mai dato per "non piazzato": potrebbe essere abbinato su Betfair. La partita
    # va in ERROR (nessun nuovo ordine) e si riconcilia a mano — finche' non esiste
    # un reconcile_pending come quello del Safe bot (F6).
    for leg in ctx.legs:
        if leg.is_live and now_ts - leg.placed_at > _PENDING_STALE_S and not _is_resting_leg(leg, params):
            # (la lay APPOGGIATA resta legittimamente sul book per ore: esclusa)
            if _trade_unknown_outcome(db, ev["event_id"], leg):
                logger.critical("[mike] %s: gamba %s con esito REST IGNOTO → ERROR, riconciliare a mano",
                                ev["event_id"], leg.ref)
                db.log("error", {"reason": "pending_unknown_outcome", "leg": leg.ref,
                                 "critical": True}, ev["event_id"])
                d = E.Decision(state="ERROR", actions=[], reason="esito ordine ignoto: riconciliazione manuale")
                E.apply_decision(ctx, d, now_ts)
                ev.update(_row_from_ctx(ev, ctx, extra))
                _persist(db, ev, before_sig)
                return (0, 0)
            leg.status = "open" if leg.matched > 0 else "cancelled"
            _mark_trade_cancelled(db, ev["event_id"], leg, "pending_stale")

    # -- lay APPOGGIATE (resting): fill simulato solo se il mercato scambia sotto ----
    n_actions = 0
    for leg in ctx.legs:
        if leg.is_live and _is_resting_leg(leg, params):
            book = snap.book(leg.market, leg.selection)
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
                      score=f"{payload.get('score_home')}-{payload.get('score_away')}")
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
                _mark_trade_cancelled(db, ev["event_id"], leg, "cancelled_by_engine")
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
            else:
                try:
                    db.insert_trade(_trade_row(info, leg, mode, params, snap.minute,
                                               f"{payload.get('score_home')}-{payload.get('score_away')}"))
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
                          now=now, dry=dry, minute=snap.minute,
                          score=f"{payload.get('score_home')}-{payload.get('score_away')}")
        n_actions += 1
    if d.telemetry:
        for k, v in d.telemetry.items():
            if k in ("pre_cycle", "cover", "settle", "cover_wait", "cashout", "close_retries_exhausted", "loss_exit"):
                if k == "cashout":
                    extra["last_cashout"] = v
                elif k == "cover_wait":
                    extra["last_cover_wait"] = v
                elif k == "loss_exit":
                    extra["last_loss_exit"] = v
                else:
                    db.log(k, v if isinstance(v, dict) else {"value": v}, ev["event_id"])
    if d.state != ev.get("state") or d.reason != extra.get("last_reason"):
        db.log("state", {"from": ev.get("state"), "to": d.state, "reason": d.reason}, ev["event_id"])
    extra["last_reason"] = d.reason

    # -- persistenza (write-on-change) --------------------------------------------
    ev["live"] = {"minute": snap.minute, "goals": snap.goals, "inplay": snap.inplay, "ht": snap.ht_active,
                  "score_home": payload.get("score_home"), "score_away": payload.get("score_away"),
                  "red_home": payload.get("red_home") or 0, "red_away": payload.get("red_away") or 0,
                  "model_probs": live.get("model_probs"), "ht_score": extra.get("ht_score"),
                  "p_total_model": live.get("p_total_model"), "p_total_emp": live.get("p_total_emp"),
                  "loss_exit": extra.get("last_loss_exit"),
                  "hazard": snap.hazard, "hazard_atlas": live.get("hazard_atlas"),
                  "hazard_model": live.get("hazard_model"), "pressure": live.get("pressure"),
                  "cover_gain_pct": live.get("cover_gain_pct"), "p_over45_model": live.get("p_over45_model"),
                  "p4_market": snap.p4_market, "p4_model": snap.p4_model,
                  "cashout": extra.get("last_cashout"), "cover_wait": extra.get("last_cover_wait"),
                  "pnl_by_total": E.net_pnl_by_total(ctx.legs, C.commission_rate(params)),
                  "books": {f"{m}|{s}": dataclasses.asdict(b) for (m, s), b in snap.books.items()},
                  "feed_fresh": snap.feed_fresh}
    ev.update(_row_from_ctx(ev, ctx, extra))
    _persist(db, ev, before_sig)
    return (n_actions, settled)


def _trade_row_for_leg(db: Any, event_id: str, leg: E.Leg) -> Optional[Dict[str, Any]]:
    try:
        for r in db.trades_for_event(str(event_id)) or []:
            if str(r.get("signal_key")) == leg.ref:
                return r
    except Exception as ex:  # noqa: BLE001
        logger.warning("[mike] trades_for_event %s KO: %s", event_id, str(ex)[:120])
    return None


def _trade_unknown_outcome(db: Any, event_id: str, leg: E.Leg) -> bool:
    """True se la riga mirror della gamba porta il marker di esito REST ignoto."""
    r = _trade_row_for_leg(db, event_id, leg)
    meta = (r or {}).get("meta") or {}
    return str(meta.get("reason") or "") == "place_exception_reconciling"


def _mark_trade_cancelled(db: Any, event_id: str, leg: E.Leg, reason: str) -> None:
    """Allinea la riga mike_trades a una gamba ritirata (review F1 #4): mai 'pending' per sempre."""
    r = _trade_row_for_leg(db, event_id, leg)
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


def _settle_trades(db: Any, event_id: str, ctx: E.MatchCtx, settle: Dict[str, Any]) -> None:
    """Riporta l'esito per gamba sulle righe mike_trades (signal_key = leg.ref)."""
    per_leg = {ref: (st, pnl) for ref, st, pnl in (settle.get("per_leg") or [])}
    try:
        rows = db.trades_for_event(str(event_id))
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "settle_rows_failed", "err": str(ex)[:160]}, event_id)
        return
    now_iso = _now().isoformat()
    for r in rows:
        if str(r.get("status")) in ("won", "lost", "void", "error"):
            continue
        res = per_leg.get(str(r.get("signal_key")))
        if res is None:
            continue
        st, pnl = res
        try:
            db.update_trade(int(r["id"]), status=st, pnl=round(float(pnl), 2), settled_at=now_iso)
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
