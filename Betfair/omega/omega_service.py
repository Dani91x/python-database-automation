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
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from Betfair.omega import omega_advisor, omega_config, omega_engine as E
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
    # §2: R e i contatori di gate sono della GIORNATA operativa (realized_today/
    # matches_traded_today), NON cumulativi a vita: altrimenti stop_on_goal,
    # max_events e daily_loss_cap resterebbero scattati per sempre dal 2° giorno.
    realized = float(aggregates.get("realized_today", aggregates.get("realized_profit", 0.0)))
    traded_count = int(aggregates.get("matches_traded_today", aggregates.get("matches_traded", 0)))
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
        # più piccolo ma COMPLETO che uno parziale. §6: la riduzione va LOGGATA
        # (requested_size = size PRIMA del taglio, per audit target vs effettivo).
        requested_size = size
        if sel.lay_size_available and size > sel.lay_size_available:
            size = round(sel.lay_size_available, 2)
            db.log("size_reduced", {"event_id": ev.event_id, "requested": requested_size,
                                    "available": sel.lay_size_available, "size": size})
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
            requested_size=requested_size,
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
    commission, market, db, now, requested_size: Optional[float] = None,
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
        # requested_size = size PRIMA del cap di liquidità (audit: quanto il trade
        # è rimasto sotto target per colpa del book, §6).
        "meta": {"phase": "reserved",
                 "requested_size": requested_size if requested_size is not None else size},
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
        meta = {"fully_matched": fill.fully_matched,
                "requested_size": requested_size if requested_size is not None else size}
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
        meta = {"order_status": res.order_status,
                "requested_size": requested_size if requested_size is not None else size}
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


# trade 'open' il cui mercato non è più leggibile: si traccia DA QUANDO è
# sparito (meta.market_gone_since) e si agisce solo se resta sparito per
# ORPHAN_GONE_MAX_H CONSECUTIVE (review 16/07: l'età dal piazzamento non basta —
# un weekend di servizio spento avrebbe voidato al PRIMO ciclo esiti reali).
ORPHAN_GONE_MAX_H = 48


def _maybe_void_orphan(tr: dict[str, Any], *, db, now: datetime) -> bool:
    """Gestisce un trade 'open' orfano di mercato (read_market → None).

    1° avvistamento: marca meta.market_gone_since e basta. Dopo ORPHAN_GONE_MAX_H
    di sparizione continua: PAPER → void pnl=0 (nessun soldo vero, sblocca la
    contabilità e l'auto-close missione); LIVE → MAI void automatico (l'esito
    vero — vinto/perso — è su Betfair: registrare pnl=0 corromperebbe aggregati,
    daily_loss_cap e curva equity) → alert CRITICAL una sola volta, resta open
    per verifica manuale. Il marker si azzera se il mercato torna leggibile."""
    try:
        meta = dict(tr.get("meta") or {})
        gone_since = _parse_iso_dt(meta.get("market_gone_since"))
        if gone_since is None:
            meta["market_gone_since"] = now.isoformat()
            db.update_trade(tr["id"], meta=meta)
            return False
        if (now - gone_since).total_seconds() < ORPHAN_GONE_MAX_H * 3600:
            return False
        if str(tr.get("mode")) == "live":
            if not meta.get("orphan_alerted"):
                meta["orphan_alerted"] = True
                db.update_trade(tr["id"], meta=meta)
                logger.critical(
                    "[omega] trade LIVE %s orfano di mercato da %sh: VERIFICARE SU BETFAIR "
                    "(nessun void automatico sui soldi veri)", tr.get("id"), ORPHAN_GONE_MAX_H)
                db.log("orphan_live_alert", {
                    "trade_id": tr.get("id"), "event_id": tr.get("event_id"),
                    "market_id": tr.get("market_id"), "bet_id": tr.get("bet_id"),
                })
            return False
        db.update_trade(tr["id"], status="void", pnl=0.0, settled_at=now.isoformat(), meta=meta)
        db.log("settle_orphan", {
            "trade_id": tr.get("id"), "event_id": tr.get("event_id"),
            "reason": f"market_gone_{ORPHAN_GONE_MAX_H}h_consecutive", "mode": tr.get("mode"),
        })
        return True
    except Exception as ex:  # noqa: BLE001
        db.log("settle_error", {"trade_id": tr.get("id"), "err": str(ex)[:160]})
        return False


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
            if snap is None:
                # mercato sparito da Betfair (evento rimosso/void)
                if _maybe_void_orphan(tr, db=db, now=now):
                    settled += 1
                continue
            # mercato di nuovo leggibile: azzera l'eventuale marker di sparizione
            if (tr.get("meta") or {}).get("market_gone_since"):
                meta = dict(tr.get("meta") or {})
                meta.pop("market_gone_since", None)
                meta.pop("orphan_alerted", None)
                db.update_trade(tr["id"], meta=meta)
            if not snap.closed:
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
def _enrich_events_with_fixtures(events: list, db, now: datetime) -> dict[str, dict]:
    """event_id -> {fixture_id, league_id, home_team_id, away_team_id} abbinando
    in BATCH gli eventi Betfair alle fixture del DB (stesso matcher money-critical
    dell'advisor: Betfair/betfair_match.resolve_matches, assegnazione 1:1).
    Serve alla UI per loghi squadre/lega (media.api-sports.io). BEST-EFFORT:
    su qualsiasi errore torna {} — il refresh eventi non deve mai fallire per
    colpa dei metadati."""
    try:
        fn = getattr(db, "fixtures_for_window", None)
        if not callable(fn) or not events:
            return {}
        from Betfair.betfair_match import load_name_map, resolve_matches

        dates = [e.open_date for e in events if e.open_date]
        lo = (min(dates) if dates else now) - timedelta(hours=12)
        hi = (max(dates) if dates else now) + timedelta(hours=12)
        fixtures = fn(lo.isoformat(), hi.isoformat()) or []
        ev_dicts = [{
            "id": e.event_id,
            "name": e.name,
            "openDate": e.open_date.isoformat() if e.open_date else None,
        } for e in events]
        matched, _ = resolve_matches(ev_dicts, fixtures, name_map=load_name_map())
        out: dict[str, dict] = {}
        for m in matched:
            fx = m.get("fixture") or {}
            eid = str((m.get("event") or {}).get("id") or "")
            if eid:
                out[eid] = {
                    "fixture_id": fx.get("fixture_id"),
                    "league_id": fx.get("league_id"),
                    "home_team_id": fx.get("home_team_id"),
                    "away_team_id": fx.get("away_team_id"),
                }
        return out
    except Exception as ex:  # noqa: BLE001
        logger.warning("[omega] enrichment fixture fallito (loghi assenti): %s", str(ex)[:160])
        return {}


def refresh_events(*, market, db, now: Optional[datetime] = None) -> int:
    """Aggiorna la cache eventi calcio di oggi (menu Manuale + tab Missione).

    La cache è SOSTITUITA (upsert + purge dei non più presenti): senza purge
    gli eventi di giorni passati restavano in lista senza data visibile e
    l'utente poteva attivare missioni su partite già finite (bug 16/07)."""
    now = now or _now()
    try:
        events = market.list_today_football_events(with_competitions=True)
    except TypeError:
        # fake/market legacy senza il parametro: lista senza competizioni
        events = market.list_today_football_events()
    enrich = _enrich_events_with_fixtures(events, db, now)
    rows = []
    for e in events:
        ex = enrich.get(e.event_id) or {}
        rows.append({
            "event_id": e.event_id,
            "name": e.name,
            "open_date": e.open_date.isoformat() if e.open_date else None,
            "country_code": getattr(e, "country_code", None),
            "competition_id": getattr(e, "competition_id", None),
            "competition_name": getattr(e, "competition_name", None),
            "fixture_id": ex.get("fixture_id"),
            "league_id": ex.get("league_id"),
            "home_team_id": ex.get("home_team_id"),
            "away_team_id": ex.get("away_team_id"),
            "updated_at": now.isoformat(),
        })
    db.replace_events(rows)
    return len(rows)


def process_manual(*, market, db, now: datetime) -> int:
    """Esegue le richieste manuali pendenti. Ritorna quante ne ha processate."""
    # richieste orfane in 'processing' (crash a metà) → error, mai perse in silenzio
    fail_stale = getattr(db, "fail_stale_processing", None)
    if callable(fail_stale):
        try:
            fail_stale()
        except Exception as ex:  # noqa: BLE001
            logger.debug("[omega] fail_stale_processing KO: %s", str(ex)[:120])
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
    # gamba della missione (opzionale): whitelist rigida, mai valori liberi
    phase = payload.get("phase")
    if phase is not None:
        phase = str(phase).lower()
        if phase not in ("ht_cs", "ft_cs", "scalp"):
            return {"error": f"phase non valida: {phase}"}

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

    # legge il book: prezzo/fill mancanti + GUARDIA DI STATO (audit H4 16/07).
    # Mai piazzare su book assente o non OPEN: in PAPER il fill simulato al
    # prezzo congelato su mercato sospeso/chiuso = piazzare "a risultato noto"
    # (corrompe il P&L paper); in LIVE produce solo una riga error da rigetto.
    snap = market.read_book(market_id, {})
    if snap is None:
        return {"error": "book_non_disponibile"}
    book_status = str(snap.get("status") or "OPEN").upper()
    if book_status != "OPEN":
        return {"error": f"mercato_{book_status.lower()}"}
    runner = next((r for r in snap["runners"] if r["selection_id"] == selection_id), None)
    if runner is None:
        return {"error": "selezione_non_sul_book"}
    runner_status = str(runner.get("status") or "ACTIVE").upper()
    if runner_status != "ACTIVE":
        return {"error": f"selezione_{runner_status.lower()}"}
    if price in (None, "", 0):
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
        "phase": phase,
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
            # ref PER-GAMBA (omega-m<trade_id>): due ordini manuali sullo stesso
            # evento (o manuale+auto) NON devono mai condividere il customerOrderRef,
            # altrimenti la riconciliazione li confonderebbe (I3). Derivabile dalla
            # riga stessa → reconcile_decision lo ricostruisce senza storage extra.
            res = market.place_order_live(
                market_id=market_id, selection_id=selection_id, price=price,
                size=size, event_id=event_id, side=side,
                customer_ref=E.expected_customer_ref({"origin": "manual", "id": trade_id,
                                                      "event_id": event_id}),
            )
        except Exception as ex:  # noqa: BLE001
            # ESITO IGNOTO (review 16/07): l'eccezione può arrivare DOPO che
            # Betfair ha accettato l'ordine. Con l'indice per-gamba parziale una
            # riga 'error' sarebbe SUBITO ripiazzabile → doppio ordine reale.
            # La riserva resta 'pending': reconcile_pending la risolve contro
            # Betfair (match forte su customerOrderRef omega-m<id>) o la libera
            # dopo il GRACE se l'ordine non esiste davvero.
            db.update_trade(trade_id, meta={"phase": "reserved", "manual": True,
                                            "reason": "place_exception_reconciling",
                                            "err": str(ex)[:160]})
            db.log("manual_place_exception", {"trade_id": trade_id, "event_id": event_id,
                                              "err": str(ex)[:160]})
            return {"error": "place_exception_in_riconciliazione", "trade_id": trade_id}
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
# MISSIONI — centro di controllo per partita (tab MISSIONE).
# Il servizio AGGIORNA punteggio/fase e PROPONE le gambe; non piazza mai da
# solo: ogni ordine parte da un click utente (coda manuale, con `phase`).
# ---------------------------------------------------------------------------
_MISSION_MARKET_LABEL = {
    "HALF_TIME_SCORE": "Half Time Score",
    "CORRECT_SCORE": "Correct Score",
}


def _parse_iso_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _sugg_equal(a: Optional[dict], b: Optional[dict]) -> bool:
    """Confronto suggerimenti IGNORANDO updated_at (write-on-change)."""
    if a is None or b is None:
        return a is b
    ka = {k: v for k, v in a.items() if k != "updated_at"}
    kb = {k: v for k, v in b.items() if k != "updated_at"}
    return ka == kb


# distanza minima (gol AGGIUNTIVI dal punteggio corrente) di una proposta CS
# in-play: 2 = mai il punteggio corrente ne' quello a un solo gol di distanza
CS_MIN_GOAL_DISTANCE = 2


def _cs_suggestion(*, market, mission: dict, market_type: str, params: dict,
                   now: datetime, min_score: Optional[tuple] = None,
                   db: Any = None) -> Optional[dict]:
    """Suggerimento lay CS (HT o FT): il runner MENO PROBABILE IN ASSOLUTO
    (quota lay più alta) con liquidità minima. id+nome dal medesimo catalogo.

    ``min_score``=(home,away): esclude i punteggi ormai IRRAGGIUNGIBILI (es. a
    1-0 il runner "0 - 0" non può più uscire). Betfair li rimuove da solo, ma la
    cintura evita di proporre un runner stantio se il book è in ritardo.

    ``db`` (opzionale) abilita il blocco ``advisor`` (CONSULENTE DATI): segnali
    INFORMATIVI best-effort — Poisson interno, frequenza lega, H2H — che NON
    toccano mai id/prezzi e NON bloccano mai la proposta (errore -> None)."""
    cs = market.get_event_market_by_type(
        mission["event_id"], mission.get("event_name") or "", market_type)
    if cs is None:
        return None
    snap = market.read_market(cs)
    if snap is None or snap.closed:
        return None
    runners = snap.runners
    if min_score is not None:
        mh, ma = int(min_score[0]), int(min_score[1])
        reachable = []
        for r in runners:
            parsed = E.parse_scoreline(r.name)
            if parsed is None:
                reachable.append(r)   # aggregati: li governa include_aggregate
                continue
            if parsed[0] < mh or parsed[1] < ma:
                continue              # IRRAGGIUNGIBILE (es. 0-0 quando e' 1-0)
            # DISTANZA MINIMA in gol (caso reale 16/07: sullo 0-1 il book
            # sottile quotava il lay "0-2" in fascia [20,120] — il punteggio
            # ADIACENTE piu' probabile di tutti... ed e' USCITO davvero.
            # La fascia quote non basta sui book sottili in-play: servono
            # almeno CS_MIN_GOAL_DISTANCE gol AGGIUNTIVI dal punteggio
            # corrente perche' un lay abbia senso "da punteggio improbabile".
            if (parsed[0] - mh) + (parsed[1] - ma) < CS_MIN_GOAL_DISTANCE:
                continue
            reachable.append(r)
        runners = reachable
    # FASCIA QUOTE dai params (default [20,120]) — EVIDENZA backtest 26 partite
    # (15/07): senza pavimento, sui book sottili dei minori l'unico runner con
    # liquidità è il FAVORITO → "meno probabile in assoluto" si ribalta e
    # propone di layare lo 0-0 a 3.35 (6 degli 8 colpi del backtest venivano
    # da lì). Fuori fascia → nessun candidato → la gamba si SALTA (I6).
    sel = E.select_lay_runner(
        runners,
        price_min=params["price_min"], price_max=params["price_max"],
        min_liquidity=params["min_lay_liquidity"],
        include_aggregate=False,               # mai gli aggregati "Any Other/Unquoted"
    )
    if sel is None:
        return None
    return {
        "market_id": cs.market_id,
        "market_name": _MISSION_MARKET_LABEL.get(market_type, market_type),
        "market_type": market_type,
        "selection_id": sel.selection_id,
        "runner_name": sel.name,
        "lay_price": sel.price,
        "lay_size": sel.lay_size_available,
        # CONSULENTE DATI: blocco informativo (o None dichiarato). Calcolato
        # DOPO la selezione: non influenza MAI quale runner viene proposto.
        "advisor": omega_advisor.advisor_for_suggestion(
            mission=mission, market_type=market_type, runner_name=sel.name,
            db=db, now=now),
        "updated_at": now.isoformat(),
    }


def _scalp_suggestion(*, market, mission: dict, total_goals: int,
                      params: dict, now: datetime) -> Optional[dict]:
    """Suggerimento scalp: BACK 'Under X.5 Goals' (linea = gol+2.5, fallback
    linea sopra). Runner scelto PER NOME (mai per posizione)."""
    for mtype in E.scalp_market_types(total_goals):
        cs = market.get_event_market_by_type(
            mission["event_id"], mission.get("event_name") or "", mtype)
        if cs is None:
            continue
        book = market.read_book(cs.market_id, cs.runner_names)
        if not book or book.get("status") == "CLOSED":
            continue
        from types import SimpleNamespace

        runners = [SimpleNamespace(**r) for r in book.get("runners", [])]
        under = E.pick_under_runner(runners)
        if under is None or not getattr(under, "back_price", None):
            continue
        return {
            "market_id": cs.market_id,
            "market_name": f"Over/Under {mtype[-2]}.5 Goals",
            "market_type": mtype,
            "selection_id": int(under.selection_id),
            "runner_name": str(under.name),
            "back_price": float(under.back_price),
            "back_size": float(getattr(under, "back_size", 0.0) or 0.0),
            "line": f"{mtype[-2]}.5",
            "updated_at": now.isoformat(),
        }
    return None


def _process_one_mission(m: dict, snap: Any, *, market, db, now: datetime,
                         params: Optional[dict] = None) -> int:
    updates: dict[str, Any] = {}
    phase = E.mission_phase(
        status=getattr(snap, "status", None),
        minute=getattr(snap, "minute", None),
        kickoff=_parse_iso_dt(m.get("kickoff")),
        now=now,
        prev=str(m.get("phase_now") or "pre"),
    )
    # AUDIT M6 (review 16/07): la verifica del "finita da solo orologio" va fatta
    # QUI, prima della logica suggerimenti — se fatta dopo, i suggerimenti
    # venivano azzerati con phase='finita' e mai più riproposti sulla missione
    # tenuta deliberatamente viva (partita rinviata/non coperta dal provider).
    if phase == "finita":
        clock_only = getattr(snap, "status", None) is None and m.get("score_status") is None
        if clock_only and not _event_really_over_cached(m, market, now):
            phase = str(m.get("phase_now") or "pre")
    if snap is not None:
        for field, val in (("minute", getattr(snap, "minute", None)),
                           ("score_home", getattr(snap, "score_home", None)),
                           ("score_away", getattr(snap, "score_away", None)),
                           ("score_status", getattr(snap, "status", None))):
            if val is not None and m.get(field) != val:
                updates[field] = val
    if phase != m.get("phase_now"):
        updates["phase_now"] = phase

    if params is None:
        control = db.read_control() or {}
        params = omega_config.resolve_params(control.get("params"))
    trades = db.trades_for_event(m["event_id"])
    # una gamba conta come "già fatta" se ha un trade NON-error (pending incluso:
    # reserve-first → mai proporre di nuovo una gamba con riserva in corso)
    have = {t.get("phase") for t in trades if t.get("phase") and t.get("status") != "error"}

    # punteggio corrente (per filtro punteggi irraggiungibili e linea scalp)
    sh0 = getattr(snap, "score_home", None) if snap is not None else m.get("score_home")
    sa0 = getattr(snap, "score_away", None) if snap is not None else m.get("score_away")
    min_score = (sh0, sa0) if sh0 is not None and sa0 is not None else None

    # gamba 1T (HT CS): proponibile in pre e 1T; finestra chiusa dopo.
    # Stesso filtro irraggiungibili del FT (nel 1T il punteggio corrente è il
    # minimo anche per il mercato HALF_TIME_SCORE) — review 15/07.
    if phase in ("pre", "1t") and "ht_cs" not in have:
        sugg = _cs_suggestion(market=market, mission=m,
                              market_type="HALF_TIME_SCORE", params=params, now=now,
                              min_score=min_score if phase == "1t" else None, db=db)
        if not _sugg_equal(sugg, m.get("suggestion_ht")):
            updates["suggestion_ht"] = sugg
    elif m.get("suggestion_ht") is not None and (phase not in ("pre", "1t") or "ht_cs" in have):
        updates["suggestion_ht"] = None

    # gamba 2T (FT CS): proposta all'INTERVALLO (o nel 2T se non ancora fatta);
    # esclude i punteggi irraggiungibili dato il risultato corrente
    if phase in ("ht", "2t") and "ft_cs" not in have:
        sugg = _cs_suggestion(market=market, mission=m,
                              market_type="CORRECT_SCORE", params=params, now=now,
                              min_score=min_score, db=db)
        if not _sugg_equal(sugg, m.get("suggestion_ft")):
            updates["suggestion_ft"] = sugg
    elif m.get("suggestion_ft") is not None and (phase not in ("ht", "2t") or "ft_cs" in have):
        updates["suggestion_ft"] = None

    # scalp: solo a palla in gioco, punteggio noto e NESSUNA gamba scalp già
    # fatta (CRITICAL review 15/07: dopo un gol la linea cambia MERCATO → senza
    # questa guardia la scheda riproporrebbe un secondo back sulla stessa
    # missione, non bloccato dall'unique per-gamba → doppio stake reale).
    # Multi-scalp iterativo = v2, quando ci sarà la gamba di chiusura.
    if phase in ("1t", "2t") and sh0 is not None and sa0 is not None and "scalp" not in have:
        sugg = _scalp_suggestion(market=market, mission=m,
                                 total_goals=int(sh0) + int(sa0), params=params, now=now)
        if not _sugg_equal(sugg, m.get("suggestion_scalp")):
            updates["suggestion_scalp"] = sugg
    elif m.get("suggestion_scalp") is not None and (phase not in ("1t", "2t") or "scalp" in have):
        updates["suggestion_scalp"] = None

    # auto-chiusura: partita finita e nessun trade ancora vivo. Un 'pending'
    # LIVE conta come vivo ANCHE senza bet_id persistito (conferma DB fallita:
    # l'ordine reale può esistere — mai riaprire l'evento all'automatico
    # chiudendo la missione prima della riconciliazione) — review 15/07.
    alive = any(t.get("status") in ("open",) or
                (t.get("status") == "pending" and
                 (t.get("bet_id") or str(t.get("mode")) == "live"))
                for t in trades if t.get("phase"))
    if phase == "finita" and not alive:
        # la verifica clock-only è già stata fatta in testa (M6): se siamo qui
        # con 'finita', la partita è finita davvero (provider o book chiuso).
        updates["status"] = "closed"

    if updates:
        updates["updated_at"] = now.isoformat()
        db.update_mission(m["event_id"], **updates)
        return 1
    return 0


# cache TTL della verifica "davvero finita": senza, una missione su partita
# rinviata costerebbe 2 chiamate Betfair OGNI ciclo (~8.600/die) solo per
# ri-sentirsi dire "non ancora" (review 16/07). False = ricontrolla tra TTL;
# True chiude la missione e la cache non serve più.
_REALLY_OVER_TTL_S = 600
_REALLY_OVER_CACHE: dict[str, tuple[datetime, bool]] = {}


def _event_really_over_cached(m: dict, market, now: datetime) -> bool:
    eid = str(m.get("event_id") or "")
    hit = _REALLY_OVER_CACHE.get(eid)
    if hit is not None and (now - hit[0]).total_seconds() < _REALLY_OVER_TTL_S:
        return hit[1]
    res = _event_really_over(m, market)
    _REALLY_OVER_CACHE[eid] = (now, res)
    if len(_REALLY_OVER_CACHE) > 500:  # bound: mai crescita illimitata
        _REALLY_OVER_CACHE.pop(next(iter(_REALLY_OVER_CACHE)))
    return res


def _event_really_over(m: dict, market) -> bool:
    """Conferma da Betfair che l'evento è davvero concluso, usata SOLO quando la
    fase 'finita' deriva dal fallback orologio (kickoff+3h senza alcun dato del
    provider). Mercato CS assente o CLOSED (o errore di lettura) → finita davvero
    (fail-closed: meglio chiudere che tenere missioni zombie). Book ancora vivo
    (OPEN/SUSPENDED, anche non inplay = partita rinviata/spostata) → NON finita."""
    try:
        ev = _real_market.EventInfo(str(m.get("event_id") or ""), m.get("event_name") or "", None)
        cs = market.get_correct_score_market(ev)
        if cs is None:
            return True
        book = market.read_market(cs)
        return book is None or book.closed
    except Exception as ex:  # noqa: BLE001
        logger.debug("[omega] verifica fine evento fallita per %s: %s", m.get("event_id"), str(ex)[:120])
        return True


def process_missions(*, market, db, now: datetime) -> int:
    """Aggiorna punteggio/fase/suggerimenti di ogni missione attiva. Ritorna
    quante ne ha aggiornate. Un errore su una missione non ferma le altre (I6)."""
    missions = db.active_missions()
    if not missions:
        return 0
    try:
        scores = market.get_inplay_scores([m["event_id"] for m in missions])
    except Exception as ex:  # noqa: BLE001 — senza punteggi si degrada (kickoff/prev)
        db.log("mission_scores_error", {"err": str(ex)[:160]})
        scores = {}
    control = db.read_control() or {}
    params = omega_config.resolve_params(control.get("params"))
    n = 0
    for m in missions:
        try:
            n += _process_one_mission(m, scores.get(str(m["event_id"])),
                                      market=market, db=db, now=now, params=params)
        except Exception as ex:  # noqa: BLE001
            db.log("mission_error", {"event_id": m.get("event_id"), "err": str(ex)[:160]})
    return n


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

    # 2-bis) MISSIONI — SEMPRE: punteggio live, fase, suggerimenti per gamba.
    try:
        n_missions = process_missions(market=market, db=db, now=now)
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "missions_failed", "err": str(ex)[:160]})
        n_missions = 0

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
    day_start = E.day_start_utc(now)  # §2: giornata operativa Europe/Rome
    agg = db.aggregates(day_start)

    # GUARDIA MISSIONI: gli eventi con missione ATTIVA sono territorio
    # dell'utente — l'automatico NON deve mai aggiungere esposizione lì.
    # FAIL-SAFE: se la lettura fallisce NON si piazza nulla in questo ciclo
    # (meglio un ciclo fermo che un lay doppio su una missione).
    try:
        mission_ids = db.mission_event_ids()
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "mission_ids_failed", "err": str(ex)[:160]})
        return {"skipped": "mission_ids_failed", "settled": n_settled,
                "manual": n_manual, "missions": n_missions}
    traded_ids = traded_ids | mission_ids

    # 3) scan + place
    n_placed = scan_and_place(
        control=control, params=params, events=events, traded_ids=traded_ids,
        aggregates=agg, market=market, db=db, now=now, score_lookup=score_lookup,
    )

    # 4) heartbeat + stats per la dashboard (obiettivo/target = GIORNATA operativa;
    #    realized_profit resta il cumulato storico per trasparenza)
    goal = float(control.get("daily_goal") or omega_config.DEFAULT_DAILY_GOAL)
    agg2 = db.aggregates(day_start)
    realized_today = float(agg2.get("realized_today", agg2.get("realized_profit", 0.0)))
    traded_today = int(agg2.get("matches_traded_today", agg2.get("matches_traded", 0)))
    m_rem = matches_remaining(
        events, db.traded_event_ids(), now=now,
        entry_minute_max=params["entry_minute_max"],
        max_events=params["max_events"], traded_count=traded_today,
    )
    stats = {
        "events_total": len(events),
        "matches_traded": int(agg2.get("matches_traded", 0)),
        "matches_traded_today": traded_today,
        "matches_open": int(agg2.get("matches_open", 0)),
        "realized_profit": round(float(agg2.get("realized_profit", 0.0)), 2),
        "realized_today": round(realized_today, 2),
        "open_liability": round(float(agg2.get("open_liability", 0.0)), 2),
        "matches_remaining": m_rem,
        "target_match": round(E.dynamic_target(goal, realized_today, m_rem), 2),
        "goal": goal,
        "goal_pct": round(min(realized_today / goal * 100.0, 100.0), 1) if goal > 0 else 0.0,
        "last_cycle": now.isoformat(),
    }
    db.set_control(stats=stats, heartbeat_at=now.isoformat())
    return {"placed": n_placed, "settled": n_settled, "events": len(events),
            "missions": n_missions, "stats": stats}


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
