"""Runner della TennisProStrategy (bot best-practice guidato dal punteggio).

Risolve il mercato MATCH_ODDS + la mappa nome->selection (per capire chi serve),
avvia lo stream prezzi + il worker punteggio, e opzionalmente REGISTRA book+score
SINCRONIZZATI (per il backtest deterministico futuro).

Uso (paper, default):
  python -m Betfair.stream.tennis_scalper.run_tennis_pro --event-id 35790054 --paper
  python -m Betfair.stream.tennis_scalper.run_tennis_pro --event-id X --paper --record DIR
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from flumine import Flumine, clients
from flumine.worker import BackgroundWorker
from betfairlightweight import filters

from ..auth import build_client
from ..raw_listener import RawTeeMarketStream, configure_raw, close_raw
from .tennis_pro_bot import TennisProStrategy
from .tennis_score import tennis_score_poll_full

logger = logging.getLogger(__name__)
TENNIS_EVENT_TYPE_ID = "2"

# Parametri best-practice (dalla ricerca). Gate liquidita' ALTO: solo main tour.
PRO_PARAMS: Dict[str, Any] = {
    "stake": 2.0,
    "surface": "grass",          # Wimbledon = erba (servizio domina)
    "min_matched": 50_000.0,     # MAI challenger/ITF sottili
    "min_book_size": 10.0,
    "price_min": 1.08, "price_max": 3.6,
    "enable_break_point": True, "bp_target_ticks": 5, "bp_stop_ticks": 3,
    "enable_fade": True, "fade_jump_ticks": 8, "fade_target_ticks": 4,
    "fade_stop_ticks": 4, "fade_max_game": 3,
    "staged": True,
}


def _resolve(trading: Any, market_id: Optional[str], event_id: Optional[str]):
    """Ritorna (market_id, event_id, name_to_sel)."""
    filt = (filters.market_filter(market_ids=[market_id]) if market_id
            else filters.market_filter(event_ids=[event_id],
                                       event_type_ids=[TENNIS_EVENT_TYPE_ID],
                                       market_type_codes=["MATCH_ODDS"]))
    cat = trading.betting.list_market_catalogue(
        filter=filt, market_projection=["RUNNER_DESCRIPTION", "EVENT"],
        sort="MAXIMUM_TRADED", max_results=5)
    if not cat:
        raise SystemExit("Nessun mercato MATCH_ODDS trovato")
    mo = cat[0]
    name_to_sel = {r.runner_name: r.selection_id for r in (mo.runners or [])}
    ev = getattr(getattr(mo, "event", None), "id", None) or event_id
    logger.info("mercato %s | %s | runners=%s", mo.market_id,
                getattr(getattr(mo, "event", None), "name", "?"), name_to_sel)
    return mo.market_id, (str(ev) if ev else None), name_to_sel


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    p = argparse.ArgumentParser(description="Tennis PRO bot (score-driven)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--market-id")
    g.add_argument("--event-id")
    p.add_argument("--stake", type=float, default=2.0)
    m = p.add_mutually_exclusive_group()
    m.add_argument("--paper", action="store_true", default=True)
    m.add_argument("--live", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--record", metavar="DIR",
                   help="Registra book NATIVO + punteggio sincronizzato in DIR")
    p.add_argument("--score-interval", type=float, default=2.0)
    p.add_argument("--min-matched", type=float, default=None,
                   help="Soglia liquidita' (default 50k; abbassa per vederlo entrare di piu')")
    p.add_argument("--surface", choices=["grass", "fast", "clay", "wta"], default=None,
                   help="Superficie: erba/fast=back servitore al BP; clay/wta=back ribattitore")
    args = p.parse_args(argv)

    live = bool(args.live)
    stake = max(2.0, float(args.stake))
    trading = build_client(login=True)
    market_id, event_id, name_to_sel = _resolve(trading, args.market_id, args.event_id)

    params = dict(PRO_PARAMS)
    params["stake"] = stake
    params["dry_run"] = bool(args.dry_run)
    if args.min_matched is not None:
        params["min_matched"] = float(args.min_matched)
    if args.surface is not None:
        params["surface"] = args.surface

    def _sink(kind: str, payload: Dict[str, Any]) -> None:
        if kind in ("entry", "exit", "staged_green"):
            bits = " ".join(f"{k}={v}" for k, v in payload.items())
            logger.info("[PRO-EVENT] %s | %s", kind.upper(), bits)

    cap = stake * (float(params["price_max"]) + 2.0) * 3.0
    extra: Dict[str, Any] = {}
    if args.record:
        extra["stream_class"] = RawTeeMarketStream
    strategy = TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=[market_id]),
        pro_params=params, name_to_sel=name_to_sel, event_sink=_sink,
        max_selection_exposure=cap, max_order_exposure=cap,
        max_trade_count=int(1e6), max_live_trade_count=int(1e6), **extra,
    )

    if live:
        client = clients.BetfairClient(trading, min_bet_validation=False, order_stream=True)
    else:
        client = clients.BetfairClient(trading, paper_trade=True, min_bet_validation=False)
    framework = Flumine(client=client)
    framework.add_strategy(strategy)

    # registrazione book + punteggio sincronizzati
    score_fh = None
    if args.record and event_id:
        ev_dir = os.path.join(args.record, str(event_id))
        os.makedirs(ev_dir, exist_ok=True)
        configure_raw(args.record, {market_id: str(event_id)}, True)
        score_fh = open(os.path.join(ev_dir, f"{event_id}.score.jsonl"), "a",
                        encoding="utf-8")  # noqa: SIM115
        logger.info("REC book+score -> %s", ev_dir)

    if event_id:
        framework.add_worker(BackgroundWorker(
            framework, function=tennis_score_poll_full,
            interval=float(args.score_interval),
            func_kwargs={"trading": trading, "event_id": event_id,
                         "strategy": strategy, "record_fh": score_fh},
            name="score_full"))

    banner = "LIVE (SOLDI VERI)" if live else "PAPER (zero soldi)"
    logger.info("=== TENNIS PRO === %s | market=%s event=%s stake=%.2f | segnali: "
                "break_point=%s fade=%s staged=%s", banner, market_id, event_id,
                stake, params["enable_break_point"], params["enable_fade"],
                params["staged"])
    try:
        framework.run()
    except KeyboardInterrupt:
        logger.info("interrotto")
    finally:
        if args.record:
            close_raw()
        if score_fh:
            score_fh.close()
        logger.info("STATS finali: %s", getattr(strategy, "stats", None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
