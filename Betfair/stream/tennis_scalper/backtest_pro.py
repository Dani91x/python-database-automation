"""Backtest DETERMINISTICO della TennisProStrategy su dati registrati.

Rigioca il book NATIVO (.raw.jsonl) via FlumineSimulation e INIETTA il punteggio
sincronizzato (.score.jsonl) allineandolo al publish_time del book. Cosi' la
strategia score-driven puo' essere validata coi numeri veri. Fill simulati solo
sul volume realmente scambiato (coda reale). P&L = settlement simulato flumine.

Uso:
  python -m Betfair.stream.tennis_scalper.backtest_pro --event-id 35790695 \
      --dir <scratch>/tennis_rec --market-id 1.259749820 --surface grass
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import flumine.config
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware
from betfairlightweight import filters

from ..auth import build_client
from .tennis_pro_bot import TennisProStrategy
from .tennis_score import parse_tennis_scores, TennisScore

logger = logging.getLogger(__name__)
_MAX_EXPOSURE = 1_000_000.0


class BacktestProStrategy(TennisProStrategy):
    """Come TennisProStrategy ma il punteggio arriva dalla TIMELINE registrata,
    allineata al publish_time del book (invece che dal worker live)."""

    def set_timeline(self, timeline: List[Tuple[float, TennisScore]]) -> None:
        self._tl = timeline
        self._ti = 0
        self.settled_pnl = 0.0

    def process_market_book(self, market: Any, market_book: Any) -> None:
        pt = getattr(market_book, "publish_time_epoch", None)
        tl = getattr(self, "_tl", None)
        if pt is not None and tl:
            while self._ti + 1 < len(tl) and tl[self._ti + 1][0] <= pt:
                self._ti += 1
            if tl[self._ti][0] <= pt:
                self.score = tl[self._ti][1]
        super().process_market_book(market, market_book)

    def process_closed_market(self, market: Any, market_book: Any) -> None:
        try:
            for o in market.blotter.strategy_orders(self):
                sim = getattr(o, "simulated", None)
                self.settled_pnl += float(getattr(sim, "profit", 0.0) or 0.0)
        except Exception:  # noqa: BLE001
            pass


def load_timeline(score_path: str, event_id: str) -> List[Tuple[float, TennisScore]]:
    tl: List[Tuple[float, TennisScore]] = []
    if not os.path.isfile(score_path):
        return tl
    with open(score_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            ts = parse_tennis_scores([rec.get("score")], event_id)
            if ts is not None and rec.get("t") is not None:
                tl.append((float(rec["t"]) * 1000.0, ts))
    tl.sort(key=lambda x: x[0])
    return tl


def _names(market_id: str) -> Dict[str, int]:
    try:
        t = build_client(login=True)
        cat = t.betting.list_market_catalogue(
            filter=filters.market_filter(market_ids=[market_id]),
            market_projection=["RUNNER_DESCRIPTION"], max_results=1)
        if cat:
            return {r.runner_name: r.selection_id for r in (cat[0].runners or [])}
    except Exception as exc:  # noqa: BLE001
        logger.warning("catalogo non risolto (%s), uso fallback", exc)
    return {"Dimitrov": 3120166, "Ar Fery": 26402980}   # fallback noto


def run(raw: str, score: str, event_id: str, market_id: str,
        surface: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    timeline = load_timeline(score, event_id)
    name_to_sel = _names(market_id)
    tally: Dict[str, Dict[str, Any]] = {}

    def _sink(kind: str, payload: Dict[str, Any]) -> None:
        if kind == "entry":
            k = payload.get("kind")
            tally.setdefault(k, {"n": 0, "pnl": 0.0, "green": 0, "stop": 0, "scratch": 0})
            tally[k]["n"] += 1
        elif kind == "exit":
            k = payload.get("kind")
            d = tally.setdefault(k, {"n": 0, "pnl": 0.0, "green": 0, "stop": 0, "scratch": 0})
            d["pnl"] += float(payload.get("locked") or 0.0)
            d[payload.get("outcome", "green")] = d.get(payload.get("outcome", "green"), 0) + 1

    p = {"surface": surface, "size_step": 0.0, "live_min_bet": 0.0,
         "dry_run": False, "min_matched": 10_000.0, **(params or {})}
    prev_sim = getattr(flumine.config, "simulated", False)
    flumine.config.simulated = True
    flumine.config.simulation_available_prices = False
    try:
        client = clients.SimulatedClient(min_bet_validation=False)
        try:
            client.commission_base = 0.0
        except (TypeError, ValueError):
            pass
        framework = FlumineSimulation(client=client)
        framework.add_market_middleware(SimulatedMiddleware())
        strat = BacktestProStrategy(
            market_filter={"markets": [raw]}, pro_params=p,
            name_to_sel=name_to_sel, event_sink=_sink,
            max_selection_exposure=_MAX_EXPOSURE, max_order_exposure=_MAX_EXPOSURE,
            max_trade_count=int(1e9), max_live_trade_count=int(1e9))
        strat.set_timeline(timeline)
        framework.add_strategy(strat)
        framework.run()
    finally:
        flumine.config.simulated = prev_sim
    return {"stats": strat.stats, "settled_pnl": strat.settled_pnl,
            "tally": tally, "timeline_len": len(timeline)}


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")
    p = argparse.ArgumentParser(description="Backtest deterministico TennisPro")
    p.add_argument("--event-id", required=True)
    p.add_argument("--dir", required=True, help="cartella con <event>/<event>.raw.jsonl+.score.jsonl")
    p.add_argument("--market-id", required=True)
    p.add_argument("--surface", default="grass")
    args = p.parse_args(argv)

    ev = str(args.event_id)
    raw = os.path.join(args.dir, ev, f"{ev}.raw.jsonl")
    score = os.path.join(args.dir, ev, f"{ev}.score.jsonl")
    print(f"# Backtest PRO  event={ev}  surface={args.surface}")
    print(f"# raw={os.path.getsize(raw) if os.path.isfile(raw) else 0}B  "
          f"score={os.path.getsize(score) if os.path.isfile(score) else 0}B")
    res = run(raw, score, ev, args.market_id, args.surface)
    print(f"\ntimeline punteggi: {res['timeline_len']}")
    print(f"STATS: {res['stats']}")
    print(f"\n===== P&L per SETUP =====")
    for k, d in sorted(res["tally"].items(), key=lambda x: x[1]["pnl"], reverse=True):
        print(f"  {k:16s}  n={d['n']:2d}  pnl={d['pnl']:+.3f}  "
              f"(green={d.get('green',0)} stop={d.get('stop',0)} scratch={d.get('scratch',0)})")
    print(f"\n>>> P&L SETTLEMENT (vero, flumine): {res['settled_pnl']:+.3f} EUR <<<")
    return 0


if __name__ == "__main__":
    sys.exit(main())
