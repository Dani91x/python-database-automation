"""Runner del TENNIS scalper — iscrizione Stream API + worker punteggio.

I PREZZI arrivano via **Stream API** (iscrizione al mercato, push in
``process_market_book``), esattamente come nel calcio. Il PUNTEGGIO arriva da un
worker che interroga l'InPlayService (poll leggero, come lo ``score_worker`` del
calcio) e alimenta la gap-guard (``strategy.point_pressure``).

Modalita':
  --paper (DEFAULT): ``BetfairClient(paper_trade=True)`` → fill SIMULATI su dati
     live, P&L simulato, ZERO soldi. Per osservare i cicli sul match delle 16:00.
  --live: ordini REALI (€2/lato). Da usare solo dopo paper OK + code-review.
  --dry-run: la strategia non piazza nulla (solo log decisionale).

Uso:
  python -m Betfair.stream.tennis_scalper.run_tennis_scalper --event-id 35790084 --paper
  python -m Betfair.stream.tennis_scalper.run_tennis_scalper --market-id 1.240... --paper
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional

from flumine import Flumine, clients
from flumine.worker import BackgroundWorker
from betfairlightweight import filters

from ..auth import build_client
from ..raw_listener import RawTeeMarketStream, configure_raw, close_raw
from .tennis_scalper_bot import TennisScalperStrategy, ticks_between
from .tennis_score import tennis_score_poll

logger = logging.getLogger(__name__)

TENNIS_EVENT_TYPE_ID = "2"  # Betfair: 1=calcio, 2=tennis

# Default TENNIS: gate ridotti per la liquidita' bassa dei challenger ITF.
# Sono di TEST (banco di prova), non l'habitat ideale (meglio ATP/WTA top).
TENNIS_PARAMS: Dict[str, Any] = {
    "mode": "auto",           # join su spread stretto, maker su spread largo
    "scalp_ticks": 1,         # target di chiusura (1 tick) -> fill piu' facile
    "stop_ticks": 3,          # stop avverso (tennis: piu' respiro del calcio)
    # ---- CALIBRAZIONE TENNIS (NON calcio): un punto muove il prezzo di 2-6
    # tick. Le soglie del calcio (4t = gol -> fuggi) qui bloccavano OGNI punto.
    "max_spread_ticks": 6,    # tennis in-play ha spread piu' larghi
    "join_max_spread": 3,     # join fino a 3 tick
    "capture_min_ticks": 2,
    "capture_max_ticks": 20,  # maker dentro spread larghi (in-play tennis)
    "signal_ticks": 1.0,
    "max_signal_ticks": 10.0, # ANTI-GAP ricalibrato: blocca i BREAK veri (>10t),
                              # NON l'oscillazione normale punto-per-punto (2-6t)
    "min_size": 5.0,          # liquidita' minima sui best
    "min_total_matched": 0.0,
    "price_min": 1.20,        # copre il favorito 2-runner senza quote-code enormi
    "price_max": 6.0,
    "min_flow": 2.0,          # EUR/lato minimi nella finestra
    "allow_inplay": True,     # in-play continuo (niente kickoff/HT)
    "warmup_ms": 30000,       # osservazione minima prima di quotare (30s)
    # ---- BLINDATURE BETFAIR .it (identiche a VALIDATED_PARAMS del calcio) ----
    # OBBLIGATORIE per il live: su .it lo stake e' a multipli di €0,50
    # (size_step) e il green-up sotto il minimo va over-hedgato a €2
    # (live_min_bet) invece di essere rifiutato -> mai posizioni scoperte.
    "live_min_bet": 2.0,      # over-hedge dei close sotto il minimo Betfair
    "size_step": 0.5,         # granularita' stake su .it (multipli di €0,50)
    "max_txn_hour": 300,      # cap transazioni/ora (limiti Betfair)
}


def _resolve_market_and_event(
    trading: Any, market_id: Optional[str], event_id: Optional[str]
) -> tuple[str, Optional[str]]:
    """Ritorna (market_id MATCH_ODDS, event_id numerico per l'IPS)."""
    if market_id:
        # risolvi l'event id (serve al feed punteggio) dal catalogo
        cat = trading.betting.list_market_catalogue(
            filter=filters.market_filter(market_ids=[market_id]),
            market_projection=["EVENT"],
            max_results=1,
        )
        ev = None
        if cat:
            ev_obj = getattr(cat[0], "event", None)
            ev = getattr(ev_obj, "id", None) if ev_obj else None
        return market_id, (str(ev) if ev else event_id)

    if not event_id:
        raise SystemExit("Serve --market-id oppure --event-id")

    cat = trading.betting.list_market_catalogue(
        filter=filters.market_filter(
            event_ids=[event_id],
            event_type_ids=[TENNIS_EVENT_TYPE_ID],
            market_type_codes=["MATCH_ODDS"],
        ),
        market_projection=["RUNNER_DESCRIPTION", "MARKET_START_TIME"],
        sort="MAXIMUM_TRADED",
        max_results=5,
    )
    if not cat:
        raise SystemExit(
            f"Nessun mercato MATCH_ODDS tennis trovato per event {event_id}"
        )
    mo = cat[0]
    names = ", ".join(getattr(r, "runner_name", "?") for r in (mo.runners or []))
    logger.info("MATCH_ODDS risolto: %s (%s)", mo.market_id, names)
    return mo.market_id, str(event_id)


def diag_worker(context: Dict[str, Any], flumine: Any, *, strategy: Any) -> None:
    """Logga lo STATO interno: cosa aspetta ogni runner e perche' (diagnostica).

    Read-only sulla strategia. Aiuta a capire se il bot e' fermo per gap-guard,
    spread troppo largo, o e' in un ciclo aperto.
    """
    slots = getattr(strategy, "_slots", {}) or {}
    pp = bool(getattr(strategy, "point_pressure", False))
    stats = getattr(strategy, "stats", None)
    parts = []
    for (mid, sid), s in slots.items():
        bb = getattr(s, "last_bb", None)
        bl = getattr(s, "last_bl", None)
        st_ticks = ticks_between(bb, bl) if (bb and bl) else None
        parts.append(f"sel={sid} stato={s.status} bb={bb} bl={bl} spread={st_ticks}t")
    logger.info("[diag] point_pressure=%s stats=%s | %s",
                pp, stats, "  ;  ".join(parts) or "(nessun runner osservato)")


def pnl_worker(context: Dict[str, Any], flumine: Any, *, strategy: Any,
               market_id: str) -> None:
    """Logga OGNI fill (prezzo+size) e il P&L netto per giocatore, live.

    Formato: [FILL] sel=X BACK €2.00 @3.45  |  [P&L sel=X] back .. lay .. se_vince/se_perde.
    """
    market = None
    for m in flumine.markets:
        if getattr(m, "market_id", None) == market_id:
            market = m
            break
    if market is None:
        return
    try:
        orders = market.blotter.strategy_orders(strategy)
    except Exception:  # noqa: BLE001
        return
    seen: Dict[Any, float] = context.setdefault("seen_matched", {})
    agg: Dict[int, Dict[str, float]] = {}
    for o in orders:
        sid = int(getattr(o, "selection_id", 0) or 0)
        sm = float(getattr(o, "size_matched", 0.0) or 0.0)
        ap = float(getattr(o, "average_price_matched", 0.0) or 0.0)
        side = (getattr(o, "side", "") or "").upper()
        d = agg.setdefault(sid, {"b": 0.0, "bw": 0.0, "l": 0.0, "lw": 0.0})
        if side == "BACK":
            d["b"] += sm; d["bw"] += sm * ap
        elif side == "LAY":
            d["l"] += sm; d["lw"] += sm * ap
        prev = seen.get(o.id, 0.0)
        if sm > prev + 1e-6 and ap > 0:
            logger.info("[FILL] sel=%s %s €%.2f @ %.3f", sid, side, sm - prev, ap)
            seen[o.id] = sm
    for sid, d in agg.items():
        if d["b"] < 1e-6 and d["l"] < 1e-6:
            continue
        avb = d["bw"] / d["b"] if d["b"] else 0.0
        avl = d["lw"] / d["l"] if d["l"] else 0.0
        win = d["b"] * (avb - 1.0) - d["l"] * (avl - 1.0)   # se la selezione VINCE
        lose = -d["b"] + d["l"]                              # se PERDE
        hedged = min(win, lose)  # profitto GARANTITO se le due gambe pareggiano
        logger.info(
            "[P&L sel=%s] BACK €%.2f@%.3f | LAY €%.2f@%.3f | se_vince=%+.2f se_perde=%+.2f | garantito=%+.2f",
            sid, d["b"], avb, d["l"], avl, win, lose, hedged)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Tennis scalper (market-making in-play)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--market-id", help="Market id MATCH_ODDS diretto (1.xxx)")
    g.add_argument("--event-id", help="Event id Betfair (risolve il MATCH_ODDS)")
    p.add_argument("--stake", type=float, default=2.0, help="Size per lato (>=2.0)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--paper", action="store_true", default=True,
                      help="Paper trade: fill simulati, zero soldi (DEFAULT)")
    mode.add_argument("--live", action="store_true",
                      help="Ordini REALI (solo dopo paper + code-review)")
    p.add_argument("--dry-run", action="store_true",
                   help="La strategia non piazza nulla (solo log)")
    p.add_argument("--score-interval", type=float, default=2.0,
                   help="Secondi tra i poll del punteggio (gap-guard)")
    p.add_argument("--no-score", action="store_true",
                   help="Disattiva il feed punteggio (solo anti-gap order-book)")
    p.add_argument("--record", metavar="DIR",
                   help="Registra lo stream NATIVO (.raw.jsonl) in DIR per il "
                        "backtest/tuning (stessa subscription, tee nel listener)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    args = build_parser().parse_args(argv)
    live = bool(args.live)
    stake = max(2.0, float(args.stake))

    trading = build_client(login=True)
    market_id, event_id = _resolve_market_and_event(
        trading, args.market_id, args.event_id
    )

    params = dict(TENNIS_PARAMS)
    params["stake"] = stake
    params["dry_run"] = bool(args.dry_run)
    if not live:
        # PAPER: flumine simula i fill a QUALSIASI size (la granularita' .it non
        # esiste in simulazione). Azzeriamo size_step/live_min_bet cosi' i
        # green-up chiudono ESATTI e i cicli si completano -> si osserva il P&L
        # vero. In LIVE restano i valori .it (0.5 / 2.0) di TENNIS_PARAMS.
        params["size_step"] = 0.0
        params["live_min_bet"] = 0.0

    # Telemetria: logga COSA apre/chiude e PERCHE' (place/cycle/stop/...).
    _LOG_KINDS = {
        "place", "cycle", "stop", "scratch", "flatten_done", "circuit_breaker",
        "target_raggiunto", "loss_cap", "min_bet_skip", "min_bet_adjust",
        "trend_surf", "txn_cap",
    }

    def _sink(kind: str, payload: Dict[str, Any]) -> None:
        if kind not in _LOG_KINDS:
            return
        bits = " ".join(f"{k}={v}" for k, v in payload.items())
        logger.info("[strategy] %s | %s", kind.upper(), bits)

    cap = stake * (float(params["price_max"]) - 1.0) * 2.0
    extra: Dict[str, Any] = {}
    if args.record:
        # tee del raw nativo: la STESSA subscription scrive .raw.jsonl
        extra["stream_class"] = RawTeeMarketStream
    strategy = TennisScalperStrategy(
        market_filter=filters.streaming_market_filter(market_ids=[market_id]),
        scalper_params=params,
        event_sink=_sink,
        max_selection_exposure=cap,
        max_order_exposure=cap,
        max_trade_count=int(1e6),
        max_live_trade_count=int(1e6),
        **extra,
    )

    # PREZZI via Stream API (come il calcio). PAPER = esecuzione simulata.
    if live:
        client = clients.BetfairClient(
            trading, min_bet_validation=False, order_stream=True,
        )
    else:
        client = clients.BetfairClient(
            trading, paper_trade=True, min_bet_validation=False,
        )
    framework = Flumine(client=client)
    framework.add_strategy(strategy)

    # PUNTEGGIO via worker (poll IPS), alimenta la gap-guard.
    if not args.no_score and event_id:
        framework.add_worker(BackgroundWorker(
            framework,
            function=tennis_score_poll,
            interval=float(args.score_interval),
            func_kwargs={"trading": trading, "event_id": event_id,
                         "strategy": strategy},
            name="tennis_score",
        ))
    elif not event_id:
        logger.warning("event_id non risolto: gap-guard SOLO order-book (cintura 1)")

    # diagnostica: stato interno ogni ~8s (cosa aspetta ogni runner e perche')
    framework.add_worker(BackgroundWorker(
        framework, function=diag_worker, interval=8.0,
        func_kwargs={"strategy": strategy}, name="tennis_diag",
    ))
    # P&L live: ogni fill (prezzo+size) e il netto per giocatore, ogni ~3s
    framework.add_worker(BackgroundWorker(
        framework, function=pnl_worker, interval=3.0,
        func_kwargs={"strategy": strategy, "market_id": market_id},
        name="tennis_pnl",
    ))

    if args.record and event_id:
        configure_raw(args.record, {market_id: str(event_id)}, True)
        logger.info("REC nativo ON -> %s/%s/%s.raw.jsonl",
                    args.record, event_id, event_id)

    banner = "LIVE (SOLDI VERI)" if live else "PAPER (fill simulati, zero soldi)"
    logger.info("=== TENNIS SCALPER === %s | market=%s event=%s stake=%.2f/lato",
                banner, market_id, event_id, stake)
    if live:
        logger.warning("MODALITA' LIVE: ordini reali €%.2f/lato in corso.", stake)

    try:
        framework.run()
    except KeyboardInterrupt:
        logger.info("interrotto da tastiera — chiusura")
    finally:
        if args.record:
            close_raw()
        try:
            stats = getattr(strategy, "stats", None)
            if stats is not None:
                logger.info("STATS finali: %s", stats)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
