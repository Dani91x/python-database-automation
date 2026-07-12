"""omega_service — supervisore/loop del bot Omega (COSTITUZIONE_OMEGA.md §8).

Un unico processo locale: legge ``omega_control`` (singleton), conta gli eventi
del giorno, calcola il target dinamico per match, e per ogni partita in finestra
piazza UN lay sul Correct Score (I1). Poi regola i trade aperti al settlement.

Testabilità: ``run_once`` accetta i moduli ``market`` e ``db`` (dependency
injection) → il ciclo è verificabile con fake, senza Betfair né Supabase reali.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from Betfair.omega import omega_config, omega_engine as E
from Betfair.omega import omega_db as _real_db
from Betfair.omega import omega_market as _real_market

logger = logging.getLogger("omega.service")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Stima del minuto di gioco (punteggio CONDIVISO da live_now, fallback clock — §4/§5)
# ---------------------------------------------------------------------------
SCORE_MAX_AGE_S = 180  # oltre questa età il dato live_now è considerato stantio → clock


@dataclass(frozen=True)
class LiveScore:
    """Minuto+punteggio letti da live_now (condivisi col runner calcio)."""

    minute: Optional[int]
    score_home: Optional[int]
    score_away: Optional[int]
    updated_at: Optional[str]
    inplay: Optional[bool] = None


def _is_fresh(updated_at: Optional[str], now: datetime, max_age_s: int = SCORE_MAX_AGE_S) -> bool:
    """True se il timestamp è recente (o assente: best-effort). Evita dati congelati."""
    if not updated_at:
        return True  # nessun timestamp: usa comunque (best-effort)
    try:
        ts = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False  # FIX review: timestamp corrotto → NON fidarti (fallback clock)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() <= max_age_s


def estimate_minute(
    *,
    market_start: Optional[datetime],
    now: datetime,
    event_id: str,
    source: str,
    score_lookup: Any = None,
) -> tuple[Optional[int], Optional[str]]:
    """Ritorna (minute, score_str). Con source='score' usa il minuto+punteggio da
    live_now (condiviso), MA solo se FRESCO; altrimenti degrada al clock (I6)."""
    if source == "score" and score_lookup is not None:
        try:
            snap = score_lookup(event_id)
        except Exception as ex:  # noqa: BLE001
            logger.warning("[omega] score_lookup KO %s → clock: %s", event_id, str(ex)[:120])
            snap = None
        if snap is not None:
            minute = getattr(snap, "minute", None)
            upd = getattr(snap, "updated_at", None)
            if minute is not None and _is_fresh(upd, now):
                sh = getattr(snap, "score_home", None)
                sa = getattr(snap, "score_away", None)
                score_str = f"{sh}-{sa}" if sh is not None and sa is not None else None
                return int(minute), score_str
    # fallback: clock da marketStartTime (partite non seguite dal runner)
    if market_start is not None:
        return E.minute_from_clock(market_start, now), None
    return None, None


# ---------------------------------------------------------------------------
# Calcolo dei match ancora eleggibili (per il target dinamico — §2)
# ---------------------------------------------------------------------------
def matches_remaining(
    events: list[Any],
    traded_ids: set[str],
    *,
    now: datetime,
    entry_minute_max: int,
    max_events: int,
    traded_count: int,
) -> int:
    """Eventi non ancora piazzati la cui finestra è ancora aperta o futura."""
    count = 0
    for ev in events:
        if ev.event_id in traded_ids:
            continue
        if ev.open_date is None:
            count += 1
            continue
        minute = E.minute_from_clock(ev.open_date, now)
        if minute <= entry_minute_max:  # ancora giocabile ora o in futuro
            count += 1
    if max_events and max_events > 0:
        count = min(count, max(max_events - traded_count, 0))
    return max(count, 1)


# ---------------------------------------------------------------------------
# Fase SCAN + PLACE (un lay per match in finestra)
# ---------------------------------------------------------------------------
def scan_and_place(
    *,
    control: dict[str, Any],
    params: dict[str, Any],
    events: list[Any],
    traded_ids: set[str],
    aggregates: dict[str, float],
    market,
    db,
    now: datetime,
    score_lookup: Any = None,
) -> int:
    """Scansiona gli eventi e piazza UN lay sui match in finestra. Ritorna n. piazzati."""
    goal = float(control.get("daily_goal") or omega_config.DEFAULT_DAILY_GOAL)
    mode = control.get("mode", "paper")
    realized = float(aggregates.get("realized_profit", 0.0))
    traded_count = int(aggregates.get("matches_traded", 0))
    goal_reached = params["stop_on_goal"] and realized >= goal

    # STOP-LOSS giornaliero (default OFF): se il P&L realizzato scende sotto −cap,
    # niente NUOVI ingressi per il resto della giornata (i trade aperti si regolano).
    if params["daily_loss_cap"] and params["daily_loss_cap"] > 0 and realized <= -params["daily_loss_cap"]:
        db.log("loss_stop", {"realized": round(realized, 2), "cap": params["daily_loss_cap"]})
        return 0

    placed = 0
    for ev in events:
        if ev.event_id in traded_ids:
            continue
        # pre-filtro clock (frugale su API): scarta i match chiaramente fuori finestra.
        # Con sorgente 'score' il minuto vero può divergere dal clock (recuperi lunghi,
        # KO ritardato) → margine ampio per NON scartare match che il feed direbbe eleggibili.
        if ev.open_date is not None:
            margin = 25 if params["entry_window_source"] == "score" else 5
            clock_minute = E.minute_from_clock(ev.open_date, now)
            if clock_minute < params["entry_minute_min"] - margin or clock_minute > params["entry_minute_max"] + margin:
                continue

        try:
            cs = market.get_correct_score_market(ev)
        except Exception as ex:  # noqa: BLE001
            db.log("skip", {"event_id": ev.event_id, "reason": "catalogue_error", "err": str(ex)[:160]})
            continue
        if cs is None:
            db.log("skip", {"event_id": ev.event_id, "reason": "no_correct_score_market"})
            continue

        snapshot = None
        try:
            snapshot = market.read_market(cs)
        except Exception as ex:  # noqa: BLE001
            db.log("skip", {"event_id": ev.event_id, "reason": "book_error", "err": str(ex)[:160]})
            continue
        if snapshot is None or snapshot.closed:
            continue

        minute, score_str = estimate_minute(
            market_start=cs.market_start_time or ev.open_date,
            now=now,
            event_id=ev.event_id,
            source=params["entry_window_source"],
            score_lookup=score_lookup,
        )

        if not E.is_eligible(
            inplay=snapshot.inplay,
            minute=minute,
            entry_minute_min=params["entry_minute_min"],
            entry_minute_max=params["entry_minute_max"],
            already_traded=False,
            traded_count=traded_count,
            max_events=params["max_events"],
            goal_reached=goal_reached,
            stop_on_goal=params["stop_on_goal"],
        ):
            continue

        sel = E.select_lay_runner(
            snapshot.runners,
            price_min=params["price_min"],
            price_max=params["price_max"],
            min_liquidity=params["min_lay_liquidity"],
            include_aggregate=params["include_aggregate"],
        )
        if sel is None:
            db.log("skip", {"event_id": ev.event_id, "reason": "no_runner_in_range", "minute": minute})
            continue

        # target dinamico + sizing
        m_rem = matches_remaining(
            events, traded_ids, now=now,
            entry_minute_max=params["entry_minute_max"],
            max_events=params["max_events"], traded_count=traded_count,
        )
        commission = params["commission_pct"] / 100.0
        target = E.dynamic_target(goal, realized, m_rem)
        if target <= 0:
            db.log("skip", {"event_id": ev.event_id, "reason": "target_zero_goal_reached"})
            continue
        size = E.lay_size_from_target(
            target, commission=commission, min_stake=params["min_stake"]
        )
        size = E.apply_liability_cap(size, sel.price, params["max_liability_per_match"])
        # cap alla LIQUIDITÀ disponibile al best lay: evita fill parziali (che
        # lascerebbero esposizione reale non tracciata / cap elusi). Meglio un lay
        # più piccolo ma COMPLETO che uno parziale.
        if sel.lay_size_available and size > sel.lay_size_available:
            size = round(sel.lay_size_available, 2)
        if size < params["min_stake"]:
            db.log("skip", {"event_id": ev.event_id, "reason": "insufficient_liquidity",
                            "avail": sel.lay_size_available})
            continue
        liability = E.liability_from_lay(size, sel.price)

        # cap liability aperta totale (default OFF)
        if params["max_open_liability"] and params["max_open_liability"] > 0:
            if aggregates.get("open_liability", 0.0) + liability > params["max_open_liability"]:
                db.log("skip", {"event_id": ev.event_id, "reason": "max_open_liability"})
                continue

        # FIX review: catturare l'esito DELLA SINGOLA chiamata (non il totale
        # cumulato): altrimenti dopo il 1° piazzamento ogni evento successivo del
        # ciclo verrebbe erroneamente contato come piazzato (traded_ids/liability).
        did_place = _place_one(
            ev=ev, cs=cs, sel=sel, snapshot=snapshot, size=size, price=sel.price,
            target=target, minute=minute, score_str=score_str, mode=mode,
            commission=commission, market=market, db=db, now=now,
        )
        placed += did_place
        if did_place:
            traded_ids.add(ev.event_id)
            traded_count += 1
            # aggiorna liability aperta stimata per il cap nello stesso ciclo
            aggregates["open_liability"] = aggregates.get("open_liability", 0.0) + liability
    return placed


def _confirm_open_trade(
    db, trade_id: int, *, event_id: str, price: float, size: float,
    liability: float, bet_id: Optional[str], meta: dict, mode: str,
) -> None:
    """Conferma la riga a 'open' in modo ROBUSTO (I3/I8). Se l'update DB fallisce
    DOPO un ordine reale già piazzato, l'ordine è LIVE ma la riga resterebbe
    'pending': si ritenta, e in caso di fallimento totale si logga CRITICAL con il
    bet_id (recuperabile a video) + traccia in omega_activity per riconciliazione.
    """
    last_err: Optional[Exception] = None
    for _ in range(3):
        try:
            db.update_trade(trade_id, status="open", price=price, size=size,
                            liability=liability, bet_id=bet_id, meta=dict(meta or {}))
            return
        except Exception as ex:  # noqa: BLE001
            last_err = ex
    if mode == "live":
        logger.critical(
            "[omega] CONFERMA DB FALLITA dopo ordine LIVE (event=%s bet_id=%s): riga "
            "resta 'pending', RICONCILIARE MANUALMENTE. err=%s",
            event_id, bet_id, str(last_err)[:160],
        )
    else:
        logger.warning("[omega] conferma DB fallita (paper, event=%s): riga resta pending", event_id)
    try:
        db.log("confirm_failed", {"event_id": event_id, "trade_id": trade_id,
                                  "bet_id": bet_id, "size": size, "price": price,
                                  "liability": liability, "mode": mode,
                                  "critical": mode == "live"})
    except Exception:  # noqa: BLE001
        pass


def _place_one(
    *, ev, cs, sel, snapshot, size, price, target, minute, score_str, mode,
    commission, market, db, now,
) -> int:
    """Piazza il lay con pattern RESERVE-FIRST (I1/I3). 0/1 piazzati.

    1) RISERVA una riga 'pending' → l'unique index su event_id fa da lock (impedisce
       il doppio lay reale anche cross-processo e oltre i 60s di de-dup Betfair).
    2) ESEGUE (PAPER simulato / LIVE reale).
    3) AGGIORNA la riga a 'open' (fill reale) o 'error' (nessun ordine reale attivo).
    Così un ordine LIVE non può mai raddoppiarsi né restare orfano non tracciato.
    """
    runner = next((r for r in snapshot.runners if r.selection_id == sel.selection_id), None)
    ladder = runner.lay_ladder if runner else ()

    reserve: dict[str, Any] = {
        "event_id": ev.event_id,
        "event_name": cs.event_name,
        "market_id": cs.market_id,
        "selection_id": sel.selection_id,
        "runner_name": sel.name,
        "side": "lay",
        "mode": mode,
        "origin": "auto",
        "price": price,
        "size": size,
        "liability": E.liability_from_lay(size, price),
        "commission": commission,  # FISSATA ora: il settlement userà questa, non il param corrente
        "target": round(target, 2),
        "minute_at_entry": minute,
        "score_at_entry": score_str,
        "kickoff": cs.market_start_time.isoformat() if cs.market_start_time else None,
        "status": "pending",
        "pnl": 0.0,
        "meta": {"phase": "reserved", "requested_size": size},
    }

    # 1) RISERVA (il conflitto su event_id = già riservato/piazzato → skip pulito, I1)
    try:
        trade_id = db.insert_trade(reserve)
    except Exception as ex:  # noqa: BLE001
        db.log("skip", {"event_id": ev.event_id, "reason": "already_reserved", "err": str(ex)[:120]})
        return 0
    if not trade_id:
        db.log("skip", {"event_id": ev.event_id, "reason": "reserve_no_id"})
        return 0

    # 2) ESEGUE
    if mode == "paper":
        fill = E.paper_fill(size, best_price=price, lay_ladder=ladder)
        if fill is None or fill.matched_size <= 0:
            db.update_trade(trade_id, status="error", meta={"reason": "paper_no_fill"})
            db.log("skip", {"event_id": ev.event_id, "reason": "paper_no_fill"})
            return 0
        final_price, final_size = fill.avg_price, fill.matched_size
        meta = {"fully_matched": fill.fully_matched, "requested_size": size}
        bet_id = None
    else:  # live — soldi veri
        try:
            res = market.place_lay_live(
                market_id=cs.market_id, selection_id=sel.selection_id,
                price=price, size=size, event_id=ev.event_id,
            )
        except Exception as ex:  # noqa: BLE001 — ordine reale ESITO IGNOTO: marca error, NON ripiazza
            db.update_trade(trade_id, status="error", meta={"reason": "place_exception", "err": str(ex)[:160]})
            db.log("error", {"event_id": ev.event_id, "trade_id": trade_id, "reason": "place_exception"})
            return 0
        if not res.ok or res.size_matched <= 0:
            db.update_trade(trade_id, status="error",
                            meta={"reason": "live_not_matched", "order_status": res.order_status})
            db.log("skip", {"event_id": ev.event_id, "reason": "live_not_matched",
                            "order_status": res.order_status})
            return 0
        final_price = float(res.avg_price_matched or price)
        final_size = res.size_matched
        meta = {"order_status": res.order_status, "requested_size": size}
        bet_id = res.bet_id

    # 3) CONFERMA → 'open' (robusta: un ordine LIVE non deve mai restare non tracciato)
    _confirm_open_trade(
        db, trade_id, event_id=ev.event_id, price=final_price, size=final_size,
        liability=E.liability_from_lay(final_size, final_price), bet_id=bet_id, meta=meta, mode=mode,
    )
    db.log("place", {
        "event_id": ev.event_id, "trade_id": trade_id, "runner": sel.name,
        "price": final_price, "size": final_size,
        "liability": E.liability_from_lay(final_size, final_price),
        "target": round(target, 2), "minute": minute, "mode": mode,
    })
    return 1


# ---------------------------------------------------------------------------
# Fase SETTLEMENT (regola i trade aperti — §6, I3)
# ---------------------------------------------------------------------------
def reconcile_pending(*, market, db, now: datetime) -> int:
    """Riallinea i trade 'pending' ORFANI con la realtà (I3). Ritorna n. riconciliati.

    Un 'pending' resta solo se la conferma DB è fallita DOPO l'esecuzione (o il
    processo è morto a metà). PAPER: nessun ordine reale → conferma con i dati
    riservati. LIVE: interroga Betfair (listCurrentOrders/listClearedOrders) e
    apre (fill reale) / lascia in attesa / libera (mai piazzato, recente) / marca
    error (vecchio e non trovato). Così NESSUN ordine reale resta non tracciato.
    """
    pendings = db.list_trades("pending")
    if not pendings:
        return 0
    n = 0
    # FAIL-SAFE: solo mode ESPLICITAMENTE 'paper' va nel ramo paper; qualsiasi altro
    # valore (live/None/ignoto) → ramo LIVE (verifica su Betfair), mai il contrario.
    paper_pendings = [t for t in pendings if str(t.get("mode")) == "paper"]
    live = [t for t in pendings if str(t.get("mode")) != "paper"]
    # PAPER: nessun ordine reale a mercato → conferma con i dati della riserva.
    for tr in paper_pendings:
        size = float(tr.get("size") or 0.0)
        price = float(tr.get("price") or 0.0)
        _confirm_open_trade(
            db, tr["id"], event_id=tr["event_id"], price=price, size=size,
            liability=float(tr.get("liability") or _back_liability(size, tr.get("side", "lay"), price)),
            bet_id=None, meta={"reconciled": "paper"}, mode="paper",
        )
        n += 1
    if not live:
        return n
    try:
        current = market.list_current_orders()
        cleared = market.list_cleared_orders()
    except Exception as ex:  # noqa: BLE001 — senza dati NON decidere (si ritenta al prossimo ciclo)
        db.log("reconcile_error", {"reason": "fetch_failed", "err": str(ex)[:160]})
        return n
    for tr in live:
        try:
            d = E.reconcile_decision(tr, current, cleared, now.isoformat())
            act = d.get("action")
            if act == "confirm":
                size = float(d["size"])
                price = float(d["price"])
                _confirm_open_trade(
                    db, tr["id"], event_id=tr["event_id"], price=price, size=size,
                    liability=_back_liability(size, tr.get("side", "lay"), price),
                    bet_id=d.get("bet_id"), meta={"reconciled": "live"}, mode="live",
                )
                db.log("reconciled_open", {"trade_id": tr["id"], "event_id": tr["event_id"], "bet_id": d.get("bet_id")})
                n += 1
            elif act == "free":
                db.delete_trade(tr["id"])
                db.log("reconciled_free", {"trade_id": tr["id"], "event_id": tr["event_id"]})
                n += 1
            elif act == "error":
                db.update_trade(tr["id"], status="error", meta={"reason": "reconcile_orphan_old"})
                db.log("reconciled_error", {"trade_id": tr["id"], "event_id": tr["event_id"]})
                n += 1
            # 'keep' → ordine reale ancora non matchato: non toccare
        except Exception as ex:  # noqa: BLE001
            db.log("reconcile_error", {"trade_id": tr.get("id"), "err": str(ex)[:160]})
    return n


def settle_open(*, params: dict[str, Any], market, db, now: datetime) -> int:
    """Per ogni trade aperto legge il mercato; se CLOSED calcola P&L. Ritorna n. settled."""
    settled = 0
    fallback_commission = params["commission_pct"] / 100.0
    for tr in db.open_trades():
        # FIX review: l'INTERO corpo per-trade è protetto → una riga malformata
        # (chiave mancante/tipo errato) NON blocca il settlement di tutti gli altri.
        try:
            cs = _real_market.CorrectScoreMarket(
                market_id=tr["market_id"], event_id=tr["event_id"],
                event_name=tr.get("event_name") or "", market_start_time=None, runner_names={},
            )
            snap = market.read_market(cs)
            if snap is None or not snap.closed:
                continue
            # commissione FISSATA al piazzamento (coerenza P&L anche se il param cambia)
            tr_commission = tr.get("commission")
            tr_commission = float(tr_commission) if tr_commission is not None else fallback_commission
            status, pnl = E.settle_pnl(
                our_selection_id=int(tr["selection_id"]),
                winner_selection_id=snap.winner_selection_id,
                size=float(tr["size"]), price=float(tr["price"]),
                commission=tr_commission, voided=snap.voided,
                side=tr.get("side", "lay"),
            )
            db.update_trade(
                tr["id"], status=status, pnl=round(pnl, 2), settled_at=now.isoformat()
            )
            db.log("settle", {
                "trade_id": tr["id"], "event_id": tr["event_id"], "status": status,
                "pnl": round(pnl, 2), "runner": tr.get("runner_name"),
            })
            settled += 1
        except Exception as ex:  # noqa: BLE001
            db.log("settle_error", {"trade_id": tr.get("id"), "err": str(ex)[:160]})
            continue
    return settled


# ---------------------------------------------------------------------------
# MODALITÀ MANUALE (COSTITUZIONE §7-bis): coda comandi dalla UI, eseguiti dal
# servizio indipendentemente dallo stato dell'automatico.
# ---------------------------------------------------------------------------
def refresh_events(*, market, db) -> int:
    """Aggiorna la cache eventi calcio di oggi (menu Manuale). Ritorna n. eventi."""
    events = market.list_today_football_events()
    rows = [{
        "event_id": e.event_id,
        "name": e.name,
        "open_date": e.open_date.isoformat() if e.open_date else None,
    } for e in events]
    db.upsert_events(rows)
    return len(rows)


def process_manual(*, market, db, now: datetime) -> int:
    """Esegue le richieste manuali pendenti. Ritorna quante ne ha processate."""
    reqs = db.pending_manual_requests()
    n = 0
    for r in reqs:
        db.set_manual_status(r["id"], "processing")
        kind = r.get("kind")
        payload = r.get("payload") or {}
        try:
            if kind == "refresh_events":
                res = {"events": refresh_events(market=market, db=db)}
            elif kind == "load_markets":
                res = _manual_load_markets(market=market, db=db, event_id=str(payload.get("event_id")))
            elif kind == "load_book":
                res = _manual_load_book(market=market, db=db,
                                        market_id=str(payload.get("market_id")),
                                        event_id=str(payload.get("event_id") or ""))
            elif kind == "place":
                res = _manual_place(market=market, db=db, payload=payload, now=now)
            else:
                res = {"error": f"kind_sconosciuto:{kind}"}
            db.set_manual_status(r["id"], "error" if res.get("error") else "done", res)
        except Exception as ex:  # noqa: BLE001
            db.set_manual_status(r["id"], "error", {"err": str(ex)[:200]})
        n += 1
    return n


def _manual_load_markets(*, market, db, event_id: str) -> dict:
    markets = market.list_event_markets(event_id)
    db.update_event_markets(event_id, markets)
    return {"markets": len(markets)}


def _manual_load_book(*, market, db, market_id: str, event_id: str) -> dict:
    # nomi runner dalla cache mercati dell'evento (se disponibile)
    runner_names: dict[int, str] = {}
    event_name = ""
    market_name = ""
    ev = db.get_event(event_id) if event_id else None
    if ev:
        event_name = ev.get("name") or ""
        for mk in ev.get("markets") or []:
            if str(mk.get("market_id")) == str(market_id):
                market_name = mk.get("market_name") or ""
                rn = mk.get("runner_names") or {}
                runner_names = {int(k): v for k, v in rn.items()}
                break
    snap = market.read_book(market_id, runner_names)
    if snap is None:
        return {"error": "book_vuoto"}
    db.upsert_market_snapshot({
        "market_id": market_id,
        "event_id": event_id or None,
        "event_name": event_name,
        "market_name": market_name,
        "inplay": snap.get("inplay", False),
        "minute": None,
        "runners": snap.get("runners", []),
        "updated_at": now_iso(),
    })
    return {"runners": len(snap.get("runners", []))}


def _back_liability(size: float, side: str, price: float) -> float:
    """Rischio massimo: LAY = size·(price−1); BACK = stake (size)."""
    return E.liability_from_lay(size, price) if side == "lay" else round(float(size), 2)


def _manual_place(*, market, db, payload: dict, now: datetime) -> dict:
    """Piazza UN ordine manuale con reserve-first (I1), lay/back, paper/live.

    FAIL-SAFE (review sicurezza): mode/side validati contro whitelist; commissione
    e caps di rischio presi dai parametri di ``omega_control`` (stessa barriera del
    path automatico); LIVE solo se mode=='live' ESPLICITO; conferma robusta.
    """
    market_id = str(payload.get("market_id") or "")
    event_id = str(payload.get("event_id") or market_id)
    selection_id = payload.get("selection_id")
    if not market_id or selection_id is None:
        return {"error": "market_id/selection_id mancanti"}
    selection_id = int(selection_id)

    # --- validazione FAIL-SAFE di mode e side (mai fail-open sul LIVE) ---
    mode = str(payload.get("mode", "paper")).lower()
    if mode not in ("paper", "live"):
        return {"error": f"mode non valido: {mode}"}
    side = str(payload.get("side", "lay")).lower()
    if side not in ("lay", "back"):
        return {"error": f"side non valido: {side}"}

    # --- parametri/caps dalla stessa whitelist del path automatico ---
    control = db.read_control() or {}
    params = omega_config.resolve_params(control.get("params"))
    # commissione: payload override ma CLAMPATA come nel path automatico [0,20]%
    raw_comm = payload.get("commission_pct", params["commission_pct"])
    commission = omega_config.resolve_params({"commission_pct": raw_comm})["commission_pct"] / 100.0
    min_stake = params["min_stake"]

    price = payload.get("price")
    size = payload.get("size")
    target = payload.get("target")
    runner_name = payload.get("runner_name")

    # legge il book per prezzo/fill mancanti
    snap = market.read_book(market_id, {})
    runner = None
    if snap:
        runner = next((r for r in snap["runners"] if r["selection_id"] == selection_id), None)
    if price in (None, "", 0):
        if runner is None:
            return {"error": "prezzo assente e book non disponibile"}
        price = runner["lay_price"] if side == "lay" else runner["back_price"]
    if price in (None, "", 0):
        return {"error": "prezzo non disponibile sul book"}
    price = float(price)
    if price <= 1.0:
        return {"error": "prezzo non valido (<=1.0)"}
    price = E.round_to_tick(price)  # tick Betfair valido: prezzo salvato == prezzo piazzato

    # --- sizing: BACK e LAY hanno matematica DIVERSA a "target" (money-critical) ---
    explicit_stake = size not in (None, "", 0)
    if explicit_stake:
        size = float(size)  # STAKE esplicito: rispettato ESATTAMENTE (nessun rimaneggiamento)
    else:
        if target in (None, "", 0):
            return {"error": "specifica size oppure target"}
        t = float(target)
        if side == "back":
            # profit_win = size·(price−1)·(1−c) = target → size = target/((price−1)(1−c))
            denom = (price - 1.0) * (1.0 - commission)
            size = (t / denom) if denom > 0 else 0.0
            size = max(size, min_stake)
        else:
            # profit_win = size·(1−c) = target → size = target/(1−c)
            size = E.lay_size_from_target(t, commission=commission, min_stake=min_stake)
    size = round(float(size), 2)  # centesimo Betfair; l'ordine userà ESATTAMENTE questa size
    if size <= 0:
        return {"error": "size non valida"}
    if explicit_stake and size < min_stake:
        return {"error": f"stake sotto il minimo .it (min €{min_stake:.2f})"}

    # --- caps di rischio (stessi del path automatico; default OFF) ---
    cap_match = params["max_liability_per_match"]
    if cap_match and cap_match > 0:
        if side == "lay":
            size = E.apply_liability_cap(size, price, cap_match)
        elif size > cap_match:
            size = round(cap_match, 2)  # BACK: rischio = stake
        size = round(size, 2)
        # il cap non deve mai portare sotto il minimo piazzabile .it
        if size < min_stake:
            return {"error": f"cap troppo basso: size sotto il minimo €{min_stake:.2f}"}

    # cap alla LIQUIDITÀ disponibile sul lato scelto → niente fill parziali
    # (esposizione reale non tracciata). Meglio completo che parziale.
    avail = None
    if runner:
        avail = runner.get("lay_size") if side == "lay" else runner.get("back_size")
    if avail and size > float(avail):
        size = round(float(avail), 2)
    if size < min_stake:
        return {"error": f"liquidità insufficiente per lo stake minimo €{min_stake:.2f}"}
    liability = _back_liability(size, side, price)
    cap_open = params["max_open_liability"]
    if cap_open and cap_open > 0:
        agg = db.aggregates()
        if float(agg.get("open_liability", 0.0)) + liability > cap_open:
            return {"error": "max_open_liability_superato"}

    reserve = {
        "event_id": event_id,
        "event_name": (snap or {}).get("event_name") or payload.get("event_name"),
        "market_id": market_id,
        "selection_id": selection_id,
        "runner_name": runner_name or (runner or {}).get("name"),
        "side": side,
        "mode": mode,
        "origin": "manual",
        "price": price,
        "size": size,
        "liability": liability,
        "commission": commission,
        "target": round(float(target), 2) if target else None,
        "status": "pending",
        "pnl": 0.0,
        "meta": {"phase": "reserved", "manual": True},
    }
    try:
        trade_id = db.insert_trade(reserve)
    except Exception as ex:  # noqa: BLE001
        return {"error": "gia_piazzato_su_evento", "detail": str(ex)[:120]}
    if not trade_id:
        return {"error": "reserve_no_id"}

    if mode == "live":  # soldi veri — ramo ESPLICITO
        try:
            res = market.place_order_live(
                market_id=market_id, selection_id=selection_id, price=price,
                size=size, event_id=event_id, side=side,
            )
        except Exception as ex:  # noqa: BLE001
            db.update_trade(trade_id, status="error", meta={"reason": "place_exception", "err": str(ex)[:160]})
            return {"error": "place_exception", "trade_id": trade_id}
        if not res.ok or res.size_matched <= 0:
            db.update_trade(trade_id, status="error", meta={"reason": "live_not_matched", "order_status": res.order_status})
            return {"error": "live_not_matched", "trade_id": trade_id}
        avg = float(res.avg_price_matched or price)
        _confirm_open_trade(
            db, trade_id, event_id=event_id, price=avg, size=res.size_matched,
            liability=_back_liability(res.size_matched, side, avg), bet_id=res.bet_id,
            meta={"manual": True, "order_status": res.order_status}, mode="live",
        )
    else:  # paper — fill simulato al prezzo scelto
        _confirm_open_trade(
            db, trade_id, event_id=event_id, price=price, size=size, liability=liability,
            bet_id=None, meta={"manual": True, "fill": "paper_at_price"}, mode="paper",
        )
    db.log("manual_place", {"trade_id": trade_id, "event_id": event_id, "side": side,
                            "price": price, "size": size, "mode": mode})
    return {"ok": True, "trade_id": trade_id}


def now_iso() -> str:
    return _now().isoformat()


# ---------------------------------------------------------------------------
# UN ciclo completo (testabile con fake market/db)
# ---------------------------------------------------------------------------
def run_once(*, market=_real_market, db=_real_db, now: Optional[datetime] = None,
             score_lookup: Any = None) -> dict[str, Any]:
    now = now or _now()
    control = db.read_control()
    if control is None:
        return {"skipped": "no_control"}

    status = control.get("status")
    params = omega_config.resolve_params(control.get("params"))

    # 0) RICONCILIAZIONE dei 'pending' orfani con la realtà Betfair (I3) — SEMPRE e
    #    per prima: un ordine reale non deve mai restare non tracciato (kill a metà
    #    piazzamento / conferma DB fallita). Toglie il gate LIVE.
    n_reconciled = reconcile_pending(market=market, db=db, now=now)

    # 1) settlement dei trade aperti — SEMPRE, anche a bot fermo: fermare il bot
    #    blocca i NUOVI ingressi, non la regolazione dei lay già piazzati (I3).
    n_settled = settle_open(params=params, market=market, db=db, now=now)

    # 2) MODALITÀ MANUALE — SEMPRE (indipendente dallo stato dell'automatico):
    #    esegue le richieste della UI (refresh eventi, carica mercati/quote, piazza).
    try:
        n_manual = process_manual(market=market, db=db, now=now)
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "manual_failed", "err": str(ex)[:160]})
        n_manual = 0

    if status == "stopping":
        db.set_control(status="stopped", stopped_at=now.isoformat())
        db.log("stop", {})
        return {"stopped": True, "settled": n_settled, "manual": n_manual}
    if status != "running":
        return {"idle": True, "status": status, "settled": n_settled, "manual": n_manual}

    # 2) universo eventi del giorno + aggregati freschi
    try:
        events = market.list_today_football_events()
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "list_events_failed", "err": str(ex)[:160]})
        events = []
    traded_ids = db.traded_event_ids()
    agg = db.aggregates()

    # 3) scan + place
    n_placed = scan_and_place(
        control=control, params=params, events=events, traded_ids=traded_ids,
        aggregates=agg, market=market, db=db, now=now, score_lookup=score_lookup,
    )

    # 4) heartbeat + stats per la dashboard
    goal = float(control.get("daily_goal") or omega_config.DEFAULT_DAILY_GOAL)
    agg2 = db.aggregates()
    m_rem = matches_remaining(
        events, db.traded_event_ids(), now=now,
        entry_minute_max=params["entry_minute_max"],
        max_events=params["max_events"], traded_count=int(agg2.get("matches_traded", 0)),
    )
    stats = {
        "events_total": len(events),
        "matches_traded": int(agg2.get("matches_traded", 0)),
        "matches_open": int(agg2.get("matches_open", 0)),
        "realized_profit": round(float(agg2.get("realized_profit", 0.0)), 2),
        "open_liability": round(float(agg2.get("open_liability", 0.0)), 2),
        "matches_remaining": m_rem,
        "target_match": round(E.dynamic_target(goal, float(agg2.get("realized_profit", 0.0)), m_rem), 2),
        "goal": goal,
        "goal_pct": round(min(float(agg2.get("realized_profit", 0.0)) / goal * 100.0, 100.0), 1) if goal > 0 else 0.0,
        "last_cycle": now.isoformat(),
    }
    db.set_control(stats=stats, heartbeat_at=now.isoformat())
    return {"placed": n_placed, "settled": n_settled, "events": len(events), "stats": stats}


# ---------------------------------------------------------------------------
# Loop principale
# ---------------------------------------------------------------------------
_SINGLE_INSTANCE_PORT = 47313  # lock single-instance (come tennis 47312)


def _acquire_single_instance_lock():
    """Impedisce due servizi Omega insieme (difesa in profondità oltre l'unique index).

    Ritorna il socket da tenere vivo, oppure None se un'altra istanza è già attiva.
    """
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        s.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    lock = _acquire_single_instance_lock()
    if lock is None:
        logger.error("[omega] un'altra istanza è già in esecuzione (porta %s) — esco.", _SINGLE_INSTANCE_PORT)
        return
    logger.info("[omega] servizio avviato")
    score_lookup = _build_score_lookup()
    try:
        while True:
            interval = 20
            try:
                ctrl = _real_db.read_control()
                params = omega_config.resolve_params((ctrl or {}).get("params"))
                interval = int(params["poll_interval_s"])
                result = run_once(score_lookup=score_lookup)
                if result.get("placed") or result.get("settled"):
                    logger.info("[omega] ciclo: %s", {k: result[k] for k in ("placed", "settled", "events") if k in result})
            except KeyboardInterrupt:
                logger.info("[omega] interrotto")
                break
            except Exception as ex:  # noqa: BLE001 - il loop non deve morire
                logger.exception("[omega] errore di ciclo: %s", str(ex)[:200])
                try:
                    _real_db.log("error", {"reason": "cycle_exception", "err": str(ex)[:200]})
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(max(interval, 5))
    finally:
        try:
            lock.close()  # rilascia esplicitamente il lock socket 47313
        except Exception:  # noqa: BLE001
            pass


def _build_score_lookup(db=_real_db) -> Any:
    """Lookup punteggio live CONDIVISO dal runner calcio via ``live_now`` (§5).

    Legge minuto+punteggio dalla tabella ``live_now`` (scritta dal runner ogni ~5s),
    ESATTAMENTE come lo scalper: pura lettura Supabase, ZERO sessioni Betfair extra.
    Copertura = solo eventi seguiti dal runner (``live_follow``); per gli altri
    ritorna None e ``estimate_minute`` degrada al clock (I6). Il controllo di
    freschezza (``updated_at``) è in ``estimate_minute``: mai dati congelati.
    """

    def _lookup(event_id: str) -> Optional[LiveScore]:
        row = db.read_live_now(str(event_id))
        if not row:
            return None
        return LiveScore(
            minute=row.get("minute"),
            score_home=row.get("score_home"),
            score_away=row.get("score_away"),
            updated_at=row.get("updated_at"),
            inplay=row.get("inplay"),
        )

    return _lookup


if __name__ == "__main__":
    main()
