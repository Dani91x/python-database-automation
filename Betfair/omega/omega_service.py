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
            requested_size=requested_size, params=params,
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
    params: Optional[dict[str, Any]] = None,
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
        # DEMO=LIVE: se il gate flumine passa, il fill NON è istantaneo — si
        # accoda sulla coda del runner e la riserva resta 'pending' (conferma
        # dal fill reale simulato via poll_flumine_paper). Gate/enqueue KO →
        # percorso legacy INVARIATO qui sotto + log 'paper_fill_fallback'.
        req_size = requested_size if requested_size is not None else size
        use_flumine, gate_reason = _flumine_paper_gate(
            ev.event_id, db=db, mode=mode, params=params or {}, now=now)
        if use_flumine:
            rid = _flumine_enqueue_place(
                db=db, trade_id=trade_id, event_id=ev.event_id,
                market_id=cs.market_id, selection_id=sel.selection_id, side="lay",
                price=price, size=size,
                base_meta={"requested_size": req_size}, now=now)
            if rid:
                return 1  # riserva in attesa del fill flumine (mai posizioni nude: poll di ciclo)
            gate_reason = "enqueue_failed"
        if str((params or {}).get("execution_mode", "auto")) == "auto":
            db.log("paper_fill_fallback", {"event_id": ev.event_id,
                                           "trade_id": trade_id, "reason": gate_reason})
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
        # LIVE=DEMO (§6-bis v2): se il gate live passa, il place va sulla coda
        # flumine con FOK VERO (timeInForce=FILL_OR_KILL, lo esegue Betfair) e
        # l'esito arriva dall'order stream (poll di ciclo). Gate/enqueue KO →
        # percorso REST legacy INVARIATO qui sotto (mai bloccati).
        req_size = requested_size if requested_size is not None else size
        use_flumine, gate_reason = _flumine_gate(
            ev.event_id, db=db, mode=mode, params=params or {}, now=now)
        if use_flumine:
            rid = _flumine_enqueue_place(
                db=db, trade_id=trade_id, event_id=ev.event_id,
                market_id=cs.market_id, selection_id=sel.selection_id, side="lay",
                price=price, size=size,
                base_meta={"requested_size": req_size}, now=now, mode=mode)
            if rid:  # include _ENQUEUE_UNKNOWN: riserva pending, MAI place REST ora
                return 1
            gate_reason = "enqueue_failed"
        if _live_flumine_expected(params or {}):
            db.log("live_fok_fallback", {"event_id": ev.event_id,
                                         "trade_id": trade_id, "reason": gate_reason})
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
# ESECUZIONE VIA FLUMINE (COSTITUZIONE §6-bis).
# v1 (16/07, PAPER): quando il gate passa, il place paper NON usa il fill
# istantaneo su snapshot (E.paper_fill / paper_at_price): accoda un 'place'
# nella coda ESISTENTE ``betfair_live_order_requests`` (contratto di
# live_order_worker: claim atomico, client_ref UNIQUE) e la riserva resta
# 'pending' (reserve-first INVARIATO) con ``meta.flumine_request_id``. Il fill
# REALE simulato (coda al prezzo, liquidità, betDelay via flumine
# SimulatedExecution) torna dallo specchio ``betfair_live_orders``
# (client_order_ref = awlq<request_id>) ed è confermato dal poll di ciclo.
# v2 (17/07, LIVE): anche il place LIVE passa dalla coda quando il gate live
# passa (runner in order mode LIVE + kill-switch ``omega_live_via_flumine``):
# la richiesta porta ``time_in_force='FILL_OR_KILL'`` → il FOK VERO lo esegue
# BETFAIR (niente TTL software che lavora il book coi soldi veri) e l'esito
# torna dallo specchio alimentato dall'order stream. Hard deadline breve
# (``live_fill_deadline_s``) oltre la quale si riconcilia via REST per bet_id
# o si REVOCA la richiesta mai presa in carico — mai pending live zombie.
# INVARIANTE SUPREMO: il mode della richiesta accodata deriva SOLO dal mode
# del trade — un trade paper non produce MAI una richiesta 'live' (né viceversa).
# FALLBACK SEMPRE DISPONIBILE: gate KO in qualunque punto → percorso legacy
# invariato (fill snapshot in paper / place REST FOK in live) + log esplicito
# (il sistema non resta MAI bloccato per l'assenza del runner).
# ---------------------------------------------------------------------------
RUNNER_HB_MAX_AGE_S = 90       # heartbeat runner più vecchio → runner considerato giù
FLUMINE_CANCEL_GRACE_S = 60    # attesa esito cancel / letture KO oltre il TTL (solo paper)
_FLUMINE_TERMINAL = frozenset(
    {"EXECUTION_COMPLETE", "EXPIRED", "LAPSED", "VIOLATION", "VOIDED", "CANCELLED"}
)
# sentinella di _flumine_enqueue_place (solo LIVE): esito enqueue IGNOTO —
# la riserva resta 'pending' col marker (recovery del poll via client_ref),
# il chiamante NON deve ripiegare sul place REST (rischio doppio ordine reale).
_ENQUEUE_UNKNOWN = -1


def _flumine_gate(event_id: str, *, db, mode: str, params: dict[str, Any],
                  now: datetime) -> tuple[bool, str]:
    """Gate UNIFICATO paper/live per l'esecuzione via coda flumine (§6-bis).

    PAPER: runner in order mode PAPER. LIVE: kill-switch
    ``omega_live_via_flumine`` acceso + runner in order mode LIVE + contratto
    di revoca presente (anti-zombie). Comuni: ``execution_mode='auto'``, evento
    in follow STREAMING, heartbeat runner fresco ≤90s, contratto coda sul db.
    Il mode qui è SEMPRE quello del trade (mai input esterno): niente cross-mode.
    FAIL-CLOSED: qualunque dubbio/errore → (False, motivo) → percorso legacy
    (fill snapshot in paper / place REST FOK in live) — mai bloccati."""
    try:
        mode = str(mode)
        if mode == "paper":
            hb_required = "PAPER"
        elif mode == "live":
            if not params.get("omega_live_via_flumine",
                              omega_config.DEFAULTS["omega_live_via_flumine"]):
                return False, "live_via_flumine_off"  # kill-switch → legacy puro
            hb_required = "LIVE"
        else:
            return False, "mode_sconosciuto"
        if str(params.get("execution_mode", "auto")) != "auto":
            return False, "execution_mode_rest"
        fs = getattr(db, "live_follow_status", None)
        hb_fn = getattr(db, "runner_heartbeat", None)
        if not (callable(fs) and callable(hb_fn)
                and callable(getattr(db, "enqueue_live_order", None))
                and callable(getattr(db, "get_live_order_request", None))
                and callable(getattr(db, "get_live_order_mirror", None))):
            return False, "db_senza_coda"
        if mode == "live" and not callable(getattr(db, "revoke_live_order_request", None)):
            return False, "db_senza_revoca"  # senza revoca niente anti-zombie → legacy
        st = fs(str(event_id))
        if str(st or "").upper() != "STREAMING":
            return False, f"follow_{str(st or 'assente').lower()}"
        hb = hb_fn() or {}
        if str(hb.get("mode") or "").upper() != hb_required:
            return False, f"runner_mode_non_{hb_required.lower()}"
        ts = _parse_iso_dt(hb.get("ts"))
        if ts is None or (now - ts).total_seconds() > RUNNER_HB_MAX_AGE_S:
            return False, "runner_heartbeat_stantio"
        return True, "ok"
    except Exception as ex:  # noqa: BLE001 — FAIL-CLOSED: mai flumine su stato incerto
        return False, f"gate_error:{str(ex)[:80]}"


def _flumine_paper_gate(event_id: str, *, db, mode: str, params: dict[str, Any],
                        now: datetime) -> tuple[bool, str]:
    """(nome storico, v1) gate SOLO-PAPER: delega al gate unificato; qualunque
    mode != 'paper' resta chiuso qui con il motivo storico ``mode_non_paper``."""
    if str(mode) != "paper":
        return False, "mode_non_paper"
    return _flumine_gate(event_id, db=db, mode="paper", params=params, now=now)


def _live_flumine_expected(params: dict[str, Any]) -> bool:
    """True se il percorso LIVE via flumine era ATTESO (kill-switch acceso e
    execution_mode='auto'): solo allora il ripiego sul REST va loggato come
    fallback — con kill-switch spento o 'rest' è una scelta, non un degrado."""
    return (str(params.get("execution_mode", "auto")) == "auto"
            and bool(params.get("omega_live_via_flumine",
                                omega_config.DEFAULTS["omega_live_via_flumine"])))


def _flumine_enqueue_place(*, db, trade_id: int, event_id: str, market_id: str,
                           selection_id: int, side: str, price: float, size: float,
                           base_meta: Optional[dict], now: datetime,
                           mode: str = "paper") -> Optional[int]:
    """Accoda il place sulla coda del runner e marca la riserva in attesa
    (meta.phase='flumine_wait'). ``mode`` è SEMPRE il mode del trade (invariante
    supremo: mai una richiesta 'live' da un trade paper o viceversa); in LIVE la
    richiesta porta ``time_in_force='FILL_OR_KILL'`` (il FOK vero lo esegue
    Betfair). Best-effort: errore ACCERTATO → None e il chiamante fa fallback al
    percorso legacy (mai bloccati); esito enqueue IGNOTO in LIVE →
    ``_ENQUEUE_UNKNOWN`` (la riserva resta pending col marker: MAI il place REST
    subito, la richiesta potrebbe esistere → doppio ordine reale).

    ORDINE DELLE SCRITTURE (fix F1 review 16/07): il marker
    ``flumine_client_ref`` viene persistito PRIMA dell'enqueue — se il processo
    muore in mezzo, il trade pending resta riconoscibile (recovery nel poll via
    lookup per client_ref, idempotente) e NON può essere confermato due volte
    dal reconcile mentre un ordine (simulato o reale) vive nel runner."""
    mode = str(mode)
    if mode not in ("paper", "live"):  # INVARIANTE SUPREMO: mai un mode inventato
        logger.error("[omega] enqueue rifiutato: mode %r fuori whitelist", mode)
        return None
    ref = f"omega-t{trade_id}"  # deterministico: 1 richiesta per trade
    pre = dict(base_meta or {})
    pre.update({"phase": "flumine_wait", "flumine_client_ref": ref,
                "flumine_enqueued_at": now.isoformat()})
    try:
        db.update_trade(trade_id, meta=pre)  # marker PRIMA dell'enqueue (F1)
    except Exception as ex:  # noqa: BLE001 — nessun enqueue avvenuto: legacy sicuro
        logger.warning("[omega] pre-mark flumine KO (trade %s): %s", trade_id, str(ex)[:160])
        return None
    payload: dict[str, Any] = {
        "client_ref": ref,
        "action": "place",
        "mode": mode,  # deriva SOLO dal mode del trade (mai da input esterno)
        "market_id": str(market_id),
        "selection_id": int(selection_id),
        "side": str(side),
        "order_type": "LIMIT",
        "price": float(price),
        "size": float(size),
        "persistence": "LAPSE",
        "params": {"source": "omega", "trade_id": int(trade_id)},
    }
    if mode == "live":
        # FOK VERO: è Betfair a uccidere il residuo non matchato — NIENTE TTL
        # software che lavora il book coi soldi veri (quello resta solo paper).
        payload["time_in_force"] = "FILL_OR_KILL"
    try:
        rid = db.enqueue_live_order(payload)
        if not rid:
            raise RuntimeError("enqueue rifiutato (rid nullo)")
        meta = dict(pre)
        meta["flumine_request_id"] = int(rid)
        db.update_trade(trade_id, meta=meta)  # se fallisce: recovery via client_ref
        db.log("flumine_enqueue", {"trade_id": trade_id, "event_id": event_id,
                                   "request_id": int(rid), "price": price,
                                   "size": size, "mode": mode})
        return int(rid)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[omega] enqueue flumine KO (trade %s): %s", trade_id, str(ex)[:160])
        # la risposta può essersi persa DOPO l'insert (idempotente): prima di
        # tornare al legacy verifica se la richiesta esiste già per client_ref —
        # se sì va adottata (un ordine potrebbe già vivere nel runner).
        lookup_failed = False
        try:
            req = db.get_live_order_request_by_ref(ref)
        except Exception:  # noqa: BLE001
            req = None
            lookup_failed = True
        if req is not None and req.get("id") is not None:
            meta = dict(pre)
            meta["flumine_request_id"] = int(req["id"])
            try:
                db.update_trade(trade_id, meta=meta)
            except Exception:  # noqa: BLE001 — recovery al prossimo poll (client_ref)
                pass
            return int(req["id"])
        if mode == "live" and lookup_failed:
            # esito enqueue IGNOTO su SOLDI VERI: mai il place REST adesso (la
            # richiesta potrebbe esistere → doppio ordine reale). La riserva
            # resta pending col marker: il recovery del poll la adotta (se la
            # richiesta esiste) o la libera (se non è mai stata creata).
            logger.warning("[omega] enqueue LIVE esito IGNOTO (trade %s): riserva "
                           "in attesa di recovery, NESSUN place REST", trade_id)
            return _ENQUEUE_UNKNOWN
        # richiesta MAI creata (verificato): rimuovi il marker così il trade
        # resta nel perimetro legacy (reconcile); se anche questo fallisce, il
        # poll lo risolve comunque via client_ref (request_missing).
        try:
            db.update_trade(trade_id, meta=dict(base_meta or {}))
        except Exception:  # noqa: BLE001
            pass
        return None


def _flumine_enqueue_cancel(tr: dict[str, Any], *, db, bet_id: str,
                            meta: dict[str, Any], now: datetime) -> bool:
    """Accoda il cancel del residuo non matchato (TTL quasi-FOK scaduto) e passa
    la riserva a meta.phase='flumine_cancel'. False su qualunque errore (ritenta)."""
    try:
        crid = db.enqueue_live_order({
            "client_ref": f"omega-t{tr['id']}-cancel",  # idempotente
            "action": "cancel",
            "mode": "paper",
            "bet_id": str(bet_id),
            "market_id": tr.get("market_id"),
            "params": {"source": "omega", "trade_id": int(tr["id"])},
        })
        if not crid:
            return False
        meta.update({"phase": "flumine_cancel",
                     "flumine_cancel_request_id": int(crid),
                     "flumine_cancel_at": now.isoformat()})
        db.update_trade(tr["id"], meta=meta)
        db.log("flumine_cancel", {"trade_id": tr["id"], "bet_id": str(bet_id),
                                  "cancel_request_id": int(crid)})
        return True
    except Exception as ex:  # noqa: BLE001 — ritenta al prossimo ciclo
        logger.warning("[omega] cancel flumine KO (trade %s): %s", tr.get("id"), str(ex)[:160])
        return False


def _mirror_fill(mirror: Optional[dict], req: Optional[dict]) -> tuple[float, float, str]:
    """(size_matched, avg_price_matched, status) dallo SPECCHIO betfair_live_orders
    (autoritativo, scritto write-on-change da LiveTradingStrategy.process_orders);
    in sua assenza, dallo snapshot ``result`` della riga di coda (scritto al
    place, può essere più vecchio del fill)."""
    src: Any = mirror if mirror is not None else ((req or {}).get("result") or {})
    if not isinstance(src, dict):
        src = {}
    matched = float(src.get("size_matched") or 0.0)
    avg = float(src.get("average_price_matched") or 0.0)
    status = str(src.get("status") or "").upper()
    return matched, avg, status


def _flumine_confirm(tr: dict[str, Any], *, db, matched: float, avg: float,
                     bet_id: Any, min_stake: float, mode: str = "paper") -> int:
    """Conferma la riserva a 'open' con size/prezzo medio REALI (simulati in
    paper, dall'order stream in live). Qualunque matched>0 è contabilizzato
    (mai posizioni nude); sotto min_stake viene annotato ``below_min_stake``
    (scelta accounting-first)."""
    side = str(tr.get("side") or "lay")
    price = avg if avg and avg > 1.0 else float(tr.get("price") or 0.0)
    size = round(float(matched), 2)
    meta = dict(tr.get("meta") or {})
    meta.pop("phase", None)
    meta["fill"] = f"flumine_{mode}"
    if size + 1e-9 < float(min_stake):
        meta["below_min_stake"] = True
    _confirm_open_trade(
        db, tr["id"], event_id=tr["event_id"], price=price, size=size,
        liability=_back_liability(size, side, price),
        bet_id=str(bet_id) if bet_id else None, meta=meta, mode=mode,
    )
    db.log("flumine_fill", {"trade_id": tr["id"], "event_id": tr.get("event_id"),
                            "size": size, "price": price, "mode": mode,
                            "request_id": meta.get("flumine_request_id")})
    return 1


def _flumine_no_fill_error(tr: dict[str, Any], *, db, reason: str) -> int:
    """Nessun € matchato → libera la riserva a 'error' (stessa semantica di
    paper_no_fill: nessuna posizione aperta, la riga resta come storia)."""
    meta = dict(tr.get("meta") or {})
    meta["reason"] = f"flumine_{reason}"
    db.update_trade(tr["id"], status="error", meta=meta)
    db.log("flumine_no_fill", {"trade_id": tr["id"], "event_id": tr.get("event_id"),
                               "reason": reason})
    return 1


def _flumine_fallback_confirm(tr: dict[str, Any], *, db, reason: str) -> int:
    """FALLBACK legacy DICHIARATO: coda in errore / specchio inutilizzabile →
    conferma col fill istantaneo ai dati della RISERVA (stesso esito del percorso
    legacy / reconcile paper). Il sistema non resta MAI bloccato senza runner."""
    size = float(tr.get("size") or 0.0)
    price = float(tr.get("price") or 0.0)
    side = str(tr.get("side") or "lay")
    meta = dict(tr.get("meta") or {})
    meta.pop("phase", None)
    meta["fill"] = "paper_fill_fallback"
    meta["fallback_reason"] = reason
    db.log("paper_fill_fallback", {"trade_id": tr.get("id"),
                                   "event_id": tr.get("event_id"), "reason": reason})
    _confirm_open_trade(
        db, tr["id"], event_id=tr["event_id"], price=price, size=size,
        liability=float(tr.get("liability") or _back_liability(size, side, price)),
        bet_id=None, meta=meta, mode="paper",
    )
    return 1


def _poll_one_flumine_trade(tr: dict[str, Any], *, db, params: dict[str, Any],
                            now: datetime) -> int:
    """Fa avanzare di uno step UN trade paper in attesa del fill flumine.
    Ritorna 1 se risolto (open/error/fallback), 0 se ancora in attesa."""
    meta = dict(tr.get("meta") or {})
    rid = int(meta["flumine_request_id"])
    ttl_s = float(params.get("paper_fill_ttl_s", omega_config.DEFAULTS["paper_fill_ttl_s"]))
    min_stake = float(params.get("min_stake", omega_config.DEFAULTS["min_stake"]))
    res_size = float(tr.get("size") or 0.0)
    enq_at = _parse_iso_dt(meta.get("flumine_enqueued_at")) or _parse_iso_dt(tr.get("placed_at"))
    age = (now - enq_at).total_seconds() if enq_at is not None else None
    # fix F4 review 16/07: età NON calcolabile (riga malformata) = hard
    # deadline IMMEDIATA — mai un pending zombie escluso anche dal reconcile.
    hard_deadline = age is None or age >= ttl_s + FLUMINE_CANCEL_GRACE_S

    # 1) riga di coda: errore → nessun ordine simulato attivo → fallback dichiarato
    try:
        req = db.get_live_order_request(rid)
    except Exception:  # noqa: BLE001 — lettura KO transitoria
        req = None
    if req is None:
        # riga illeggibile: riprova fino alla hard deadline, poi fallback (mai bloccati)
        return _flumine_fallback_confirm(tr, db=db, reason="request_unreadable") if hard_deadline else 0
    if str(req.get("status")) == "error":
        return _flumine_fallback_confirm(
            tr, db=db, reason=f"request_error:{str(req.get('error') or '')[:80]}")

    # 2) fill dallo specchio (autoritativo) o dal result della coda
    try:
        mirror = db.get_live_order_mirror(f"awlq{rid}", "paper")
    except Exception:  # noqa: BLE001
        mirror = None
    matched, avg, status_name = _mirror_fill(mirror, req)
    bet_id = (mirror or {}).get("bet_id") or req.get("bet_id")
    terminal = status_name in _FLUMINE_TERMINAL
    fully = matched > 0 and matched + 0.005 >= res_size

    if str(meta.get("phase") or "flumine_wait") != "flumine_cancel":
        # --- attesa fill (quasi-FOK: fino al TTL l'ordine lavora il book reale) ---
        if fully or (terminal and matched > 0):
            return _flumine_confirm(tr, db=db, matched=matched, avg=avg,
                                    bet_id=bet_id, min_stake=min_stake)
        if terminal:  # terminale SENZA fill (lapsed/expired/violation)
            return _flumine_no_fill_error(tr, db=db,
                                          reason=f"terminal_{status_name.lower() or 'no_fill'}")
        if age is not None and age < ttl_s:
            return 0  # dentro il TTL: si aspetta il fill
        # TTL scaduto → cancel del residuo (serve il bet_id simulato)
        if bet_id and _flumine_enqueue_cancel(tr, db=db, bet_id=str(bet_id),
                                              meta=meta, now=now):
            return 0
        if not hard_deadline:
            return 0  # bet_id non ancora specchiato / enqueue KO: ritenta
        # oltre la hard deadline senza poter cancellare (runner giù / specchio muto)
        if matched > 0:
            return _flumine_confirm(tr, db=db, matched=matched, avg=avg,
                                    bet_id=bet_id, min_stake=min_stake)
        if mirror is None:
            return _flumine_fallback_confirm(tr, db=db, reason="no_mirror_after_ttl")
        return _flumine_no_fill_error(tr, db=db, reason="ttl_no_fill_no_cancel")

    # --- fase cancel: attende l'esito e conferma SOLO i € realmente matchati ---
    cancel_at = _parse_iso_dt(meta.get("flumine_cancel_at"))
    cancel_age = (now - cancel_at).total_seconds() if cancel_at is not None else None
    cancel_done = terminal
    crid = meta.get("flumine_cancel_request_id")
    if not cancel_done and crid:
        try:
            creq = db.get_live_order_request(int(crid))
        except Exception:  # noqa: BLE001
            creq = None
        if creq is not None and str(creq.get("status")) == "error":
            cancel_done = True  # cancel impossibile (ordine sparito/già chiuso): risolvi ora
    if not cancel_done and (cancel_age is None or cancel_age < FLUMINE_CANCEL_GRACE_S):
        return 0
    if not cancel_done:
        db.log("flumine_cancel_timeout", {"trade_id": tr.get("id"), "request_id": rid})
    if matched > 0:
        return _flumine_confirm(tr, db=db, matched=matched, avg=avg,
                                bet_id=bet_id, min_stake=min_stake)
    if mirror is None:
        return _flumine_fallback_confirm(tr, db=db, reason="no_mirror_after_cancel")
    return _flumine_no_fill_error(tr, db=db, reason="cancelled_no_fill")


def _recover_flumine_orphan(tr: dict[str, Any], *, db, now: datetime) -> int:
    """Trade pending con ``flumine_client_ref`` ma SENZA request_id (processo
    morto tra enqueue e persistenza — fix F1). Adotta la richiesta esistente
    per client_ref (idempotenza della coda); se non è mai stata creata:
    PAPER → fallback legacy (nessun ordine simulato può esistere);
    LIVE → LIBERA la riserva (nessun ordine reale può esistere — come il
    reconcile 'free': l'evento torna disponibile, MAI conferme inventate)."""
    meta = dict(tr.get("meta") or {})
    ref = str(meta.get("flumine_client_ref"))
    try:
        req = db.get_live_order_request_by_ref(ref)
    except Exception:  # noqa: BLE001 — lettura KO: riprova al prossimo ciclo
        return 0
    if req is not None and req.get("id") is not None:
        meta["flumine_request_id"] = int(req["id"])
        db.update_trade(tr["id"], meta=meta)
        db.log("flumine_recovered", {"trade_id": tr.get("id"),
                                     "request_id": int(req["id"])})
        return 0  # risolto dal poll normale al prossimo passaggio
    # nessuna richiesta con quel ref: l'enqueue non è mai avvenuto.
    if str(tr.get("mode")) == "live":
        db.delete_trade(tr["id"])
        db.log("flumine_live_freed", {"trade_id": tr.get("id"),
                                      "event_id": tr.get("event_id"),
                                      "reason": "request_missing"})
        return 1
    # PAPER: il fill legacy è l'esito corretto (identico al percorso pre-flumine).
    return _flumine_fallback_confirm(tr, db=db, reason="request_missing")


def _poll_one_flumine_live_trade(tr: dict[str, Any], *, db, market,
                                 params: dict[str, Any], now: datetime) -> int:
    """Fa avanzare di uno step UN trade LIVE in attesa dell'esito FOK dalla
    coda flumine. Il FOK VERO lo ha eseguito Betfair (timeInForce=FILL_OR_KILL):
    qui si LEGGE solo l'esito dallo specchio (order stream) — MAI conferme coi
    dati della riserva (soldi veri, mai esiti inventati). Ritorna 1 se risolto.

    Oltre la hard deadline (``live_fill_deadline_s``): con bet_id → verità da
    Betfair via REST (order_state_by_bet_id); richiesta MAI presa in carico →
    REVOCA atomica (il runner tornato vivo non piazzi un ordine stantio); esito
    davvero ignoto → alert CRITICAL una volta e resta pending in verifica
    (conta come vivo in aggregati/missione) — mai zombie silenzioso."""
    meta = dict(tr.get("meta") or {})
    rid = int(meta["flumine_request_id"])
    deadline_s = float(params.get("live_fill_deadline_s",
                                  omega_config.DEFAULTS["live_fill_deadline_s"]))
    min_stake = float(params.get("min_stake", omega_config.DEFAULTS["min_stake"]))
    enq_at = _parse_iso_dt(meta.get("flumine_enqueued_at")) or _parse_iso_dt(tr.get("placed_at"))
    age = (now - enq_at).total_seconds() if enq_at is not None else None
    overdue = age is None or age >= deadline_s  # età ignota = deadline immediata (F4)

    try:
        req = db.get_live_order_request(rid)
    except Exception:  # noqa: BLE001 — lettura KO transitoria: riprova
        req = None
    try:
        mirror = db.get_live_order_mirror(f"awlq{rid}", "live")
    except Exception:  # noqa: BLE001
        mirror = None
    matched, avg, status_name = _mirror_fill(mirror, req)
    bet_id = (mirror or {}).get("bet_id") or (req or {}).get("bet_id")

    # 1) esito TERMINALE dallo specchio (order stream: autoritativo, real-time)
    if status_name in _FLUMINE_TERMINAL:
        if matched > 0:
            return _flumine_confirm(tr, db=db, matched=matched, avg=avg,
                                    bet_id=bet_id, min_stake=min_stake, mode="live")
        # FOK ucciso da Betfair senza alcun fill: stesso esito del legacy
        # (live_not_matched) — riserva a 'error', evento consumato.
        return _flumine_no_fill_error(
            tr, db=db, reason=f"live_fok_{status_name.lower() or 'no_fill'}")

    if not overdue:
        # Dentro la deadline si aspetta SEMPRE lo specchio (order stream) —
        # anche con richiesta in 'error': se il worker è fallito DOPO il place
        # (rete KO su _write_done) l'ordine reale ESISTE e lo specchio sta per
        # arrivare. Liberare qui creerebbe un ordine reale orfano (fix 17/07,
        # review adversariale).
        return 0

    # 3) HARD DEADLINE — mai zombie. Con bet_id: la verità da Betfair via REST.
    if bet_id:
        state_fn = getattr(market, "order_state_by_bet_id", None) if market is not None else None
        state = None
        if callable(state_fn):
            try:
                state = state_fn(str(bet_id))
            except Exception:  # noqa: BLE001 — REST muto: MAI decidere al buio
                state = None
        if state is not None:
            if state.get("found"):
                if float(state.get("size_remaining") or 0.0) > 0:
                    return 0  # ancora vivo su Betfair (anomalo per un FOK): aspetta
                m2 = float(state.get("size_matched") or 0.0)
                if m2 > 0:
                    return _flumine_confirm(
                        tr, db=db, matched=m2,
                        avg=float(state.get("avg_price_matched") or 0.0),
                        bet_id=bet_id, min_stake=min_stake, mode="live")
                return _flumine_no_fill_error(tr, db=db, reason="live_rest_no_fill")
            # bet_id noto ma Betfair non lo conosce in NESSUNA lista → mai
            # matchato (ordine ucciso/void): riserva a 'error', mai un doppio.
            return _flumine_no_fill_error(tr, db=db, reason="live_rest_not_found")
        # REST non disponibile/KO: si riprova al ciclo dopo (mai al buio)
    else:
        req_status = str((req or {}).get("status") or "")
        if req_status == "error" and mirror is None:
            err_msg = str((req or {}).get("error") or "")
            if not err_msg.startswith("post_place:"):
                # 2) richiesta in ERRORE PRIMA del place (validazione/trading
                #    control/claim: contratto col worker — solo i fallimenti
                #    successivi al dispatch portano il prefisso ``post_place:``):
                #    nessun ordine reale esiste → stesso esito del FOK legacy
                #    non matchato. Deciso SOLO oltre la deadline: allo specchio
                #    è stato dato tutto il tempo di smentire.
                return _flumine_no_fill_error(
                    tr, db=db, reason=f"live_request_error:{err_msg[:80]}")
            # post_place: l'ordine reale è (quasi certamente) partito ma non
            # abbiamo né bet_id né specchio → esito IGNOTO su soldi veri: si
            # cade nel ramo CRITICAL sotto (alert + resta pending in verifica).
            # MAI liberare la riserva con un ordine potenzialmente vivo.
        elif req_status == "pending":
            # richiesta MAI presa in carico (runner giù): REVOCA atomica
            # pending→error — il runner tornato vivo ORE dopo non deve piazzare
            # un ordine reale stantio. Se la revoca perde la corsa col claim
            # del worker, si riprova (l'esito arriverà dallo specchio).
            revoked = False
            try:
                revoked = bool(db.revoke_live_order_request(rid))
            except Exception:  # noqa: BLE001
                revoked = False
            if revoked:
                return _flumine_no_fill_error(tr, db=db, reason="live_revoked_deadline")
            return 0

    # processing/done senza specchio né bet_id (o REST muto): esito IGNOTO su
    # soldi veri → MAI inventare: alert CRITICAL una volta, resta pending in
    # verifica (aggregati/missione lo contano come vivo; lo specchio, al
    # rientro del runner, lo risolverà).
    if not meta.get("live_orphan_alerted"):
        meta["live_orphan_alerted"] = True
        db.update_trade(tr["id"], meta=meta)
        logger.critical(
            "[omega] trade LIVE %s (event=%s) oltre la deadline flumine senza esito: "
            "VERIFICARE SU BETFAIR (request_id=%s, bet_id=%s)",
            tr.get("id"), tr.get("event_id"), rid, bet_id)
        db.log("flumine_live_orphan", {"trade_id": tr.get("id"),
                                       "event_id": tr.get("event_id"),
                                       "request_id": rid, "bet_id": bet_id})
    return 0


def poll_flumine_pending(*, db, params: Optional[dict[str, Any]] = None,
                         now: datetime, market=None) -> int:
    """Risolve i trade 'pending' in attesa dell'esito dalla coda flumine
    (PAPER e LIVE). Ritorna quanti ne ha risolti (open/error/fallback/free).

    PAPER — macchina a stati su meta.phase: 'flumine_wait' → (TTL)
    'flumine_cancel' → conferma/errore. Semantica quasi-FOK (COSTITUZIONE §6):
    fino a ``paper_fill_ttl_s`` l'ordine simulato lavora il book reale; scaduto
    il TTL si accoda il cancel del residuo e si confermano SOLO i € matchati;
    nessun fill → riserva liberata a 'error'. Mai posizioni nude.

    LIVE — il FOK vero lo esegue Betfair: qui si legge l'esito dallo specchio
    (order stream) e oltre ``live_fill_deadline_s`` si riconcilia via REST
    (bet_id) / si revoca la richiesta mai presa in carico. I pending LIVE SENZA
    marker flumine restano territorio di ``reconcile_pending`` (legacy)."""
    params = params or {}
    try:
        pendings = db.list_trades("pending")
    except Exception:  # noqa: BLE001 — lettura KO: riprova al prossimo ciclo
        return 0
    n = 0
    for tr in pendings:
        meta = tr.get("meta") or {}
        mode = str(tr.get("mode"))
        if mode not in ("paper", "live"):
            continue
        if mode == "live" and not (meta.get("flumine_request_id")
                                   or meta.get("flumine_client_ref")):
            continue  # pending live LEGACY: lo riconcilia reconcile_pending
        # RECOVERY F1 (review 16/07): marker presente ma request_id mai
        # persistito (crash tra enqueue e update) → adotta la richiesta per
        # client_ref se esiste; se non è mai stata creata → fallback (paper)
        # o riserva liberata (live).
        if not meta.get("flumine_request_id"):
            if meta.get("flumine_client_ref"):
                try:
                    n += _recover_flumine_orphan(tr, db=db, now=now)
                except Exception as ex:  # noqa: BLE001
                    db.log("flumine_poll_error",
                           {"trade_id": tr.get("id"), "err": str(ex)[:160]})
            continue
        try:
            if mode == "live":
                n += _poll_one_flumine_live_trade(tr, db=db, market=market,
                                                  params=params, now=now)
            else:
                n += _poll_one_flumine_trade(tr, db=db, params=params, now=now)
        except Exception as ex:  # noqa: BLE001 — un trade rotto non ferma gli altri (I6)
            db.log("flumine_poll_error", {"trade_id": tr.get("id"), "err": str(ex)[:160]})
    return n


# nome storico (v1, solo paper): stessa funzione — ora copre anche i LIVE via coda.
poll_flumine_paper = poll_flumine_pending


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
    # I pending IN ATTESA dell'esito flumine (meta.flumine_request_id) sono di
    # poll_flumine_pending: confermarli qui coi dati della riserva bypasserebbe la
    # coda; e un LIVE piazzato dal runner NON porta il customerOrderRef omega-*
    # né la strategy 'omega' → il reconcile REST lo darebbe per MAI PIAZZATO
    # ('free'/'error') mentre l'ordine reale esiste. Il poll (con hard deadline)
    # è il SOLO proprietario di quei pending — mai zombie, mai doppi.
    # (fix F1: escluso anche il solo marker client_ref — un crash tra enqueue e
    # persistenza del request_id NON deve far confermare/liberare qui un trade
    # il cui ordine potrebbe già vivere nel runner; lo risolve il poll.)
    def _is_flumine(t: dict) -> bool:
        m = t.get("meta") or {}
        return bool(m.get("flumine_request_id") or m.get("flumine_client_ref"))

    paper_pendings = [t for t in pendings
                      if str(t.get("mode")) == "paper" and not _is_flumine(t)]
    live = [t for t in pendings
            if str(t.get("mode")) != "paper" and not _is_flumine(t)]
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
        # LIVE=DEMO (§6-bis v2): stesso gate del path automatico — se passa, il
        # place va sulla coda flumine con FOK vero e la UI riceve pending_fill
        # (conferma dal poll, come il manuale paper). Gate/enqueue KO → REST
        # legacy INVARIATO qui sotto.
        use_flumine, gate_reason = _flumine_gate(
            event_id, db=db, mode=mode, params=params, now=now)
        if use_flumine:
            rid = _flumine_enqueue_place(
                db=db, trade_id=trade_id, event_id=event_id, market_id=market_id,
                selection_id=selection_id, side=side, price=price, size=size,
                base_meta={"manual": True}, now=now, mode=mode)
            if rid:  # include _ENQUEUE_UNKNOWN: riserva pending, MAI place REST ora
                db.log("manual_place", {"trade_id": trade_id, "event_id": event_id,
                                        "side": side, "price": price, "size": size,
                                        "mode": mode,
                                        "flumine_request_id": int(rid) if rid > 0 else None})
                return {"ok": True, "trade_id": trade_id, "pending_fill": True,
                        "flumine_request_id": int(rid) if rid > 0 else None}
            gate_reason = "enqueue_failed"
        if _live_flumine_expected(params):
            db.log("live_fok_fallback", {"event_id": event_id, "trade_id": trade_id,
                                         "reason": gate_reason})
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
    else:  # paper
        # DEMO=LIVE: gate flumine come per il path automatico — se passa, il
        # fill arriva dal runner (riserva 'pending' fino alla conferma del poll).
        use_flumine, gate_reason = _flumine_paper_gate(
            event_id, db=db, mode=mode, params=params, now=now)
        if use_flumine:
            rid = _flumine_enqueue_place(
                db=db, trade_id=trade_id, event_id=event_id, market_id=market_id,
                selection_id=selection_id, side=side, price=price, size=size,
                base_meta={"manual": True}, now=now)
            if rid:
                db.log("manual_place", {"trade_id": trade_id, "event_id": event_id,
                                        "side": side, "price": price, "size": size,
                                        "mode": mode, "flumine_request_id": rid})
                return {"ok": True, "trade_id": trade_id, "pending_fill": True,
                        "flumine_request_id": rid}
            gate_reason = "enqueue_failed"
        if str(params.get("execution_mode", "auto")) == "auto":
            db.log("paper_fill_fallback", {"event_id": event_id, "trade_id": trade_id,
                                           "reason": gate_reason})
        # LEGACY INVARIATO: fill simulato al prezzo scelto
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

    # 0-bis) coda flumine (PAPER e LIVE) — SEMPRE, anche a bot fermo/stopping:
    #    risolve i trade in attesa dell'esito dalla coda del runner (conferma
    #    con i € realmente matchati / cancel a TTL scaduto in paper / deadline
    #    REST+revoca in live / fallback dichiarato).
    try:
        poll_flumine_pending(db=db, params=params, now=now, market=market)
    except Exception as ex:  # noqa: BLE001
        db.log("error", {"reason": "flumine_poll_failed", "err": str(ex)[:160]})

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

# keepAlive PROATTIVO della sessione Betfair (~600s): il retry reattivo con
# re-login di omega_market.call() resta SOLO rete di sicurezza — il place LIVE
# non è idempotente oltre i 60s di de-dup Betfair, quindi il loop non deve MAI
# arrivare a un place con la sessione scaduta contando sul retry.
KEEPALIVE_EVERY_S = 600.0


def _maybe_keepalive(market, last_ts: float, *, now_ts: float) -> float:
    """Chiama ``market.keep_alive()`` se sono passati ≥KEEPALIVE_EVERY_S dal
    precedente. Ritorna il nuovo last_ts (invariato se non era ora). BEST-EFFORT:
    un KO non ferma il loop (log WARN; resta il retry reattivo di call())."""
    if now_ts - last_ts < KEEPALIVE_EVERY_S:
        return last_ts
    ka = getattr(market, "keep_alive", None)
    if callable(ka):
        try:
            ka()
        except Exception as ex:  # noqa: BLE001 — mai fermare il loop per un keepAlive
            logger.warning("[omega] keepAlive proattivo KO (retry reattivo resta): %s",
                           str(ex)[:160])
    return now_ts


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
    last_keepalive = float("-inf")  # primo ciclo: keepAlive subito (scalda la sessione)
    try:
        while True:
            interval = 20
            try:
                last_keepalive = _maybe_keepalive(
                    _real_market, last_keepalive, now_ts=time.monotonic())
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
