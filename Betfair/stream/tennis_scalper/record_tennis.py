"""Registra lo stream di UN match tennis su JSONL, per il tuning offline.

Riusa ``MarketRecorderStrategy`` (recorder gia' collaudato del calcio) senza
modificarlo. Cattura ogni MarketBook con il volume tradato per-prezzo (``trd``):
e' esattamente cio' che serve per replayare i fill maker nel backtest e tarare
i parametri del tennis_scalper in modo DETERMINISTICO su dati reali.

Uso:
  python -m Betfair.stream.tennis_scalper.record_tennis --market-id 1.259742079 \
      --event-id 35790054 --out C:/.../tennis_rec
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from flumine import Flumine, clients
from betfairlightweight import filters

from ..auth import build_client
from ..recorder import MarketRecorderStrategy

logger = logging.getLogger(__name__)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    p = argparse.ArgumentParser(description="Recorder stream di un match tennis")
    p.add_argument("--market-id", required=True, help="Market id MATCH_ODDS (1.xxx)")
    p.add_argument("--event-id", required=True, help="Event id Betfair")
    p.add_argument("--out", required=True, help="Cartella radice output JSONL")
    p.add_argument("--depth", type=int, default=3, help="Livelli ladder (trd sempre full)")
    args = p.parse_args(argv)

    trading = build_client(login=True)
    framework = Flumine(client=clients.BetfairClient(trading))

    mid = args.market_id
    ev = str(args.event_id)
    strategy = MarketRecorderStrategy(
        market_filter=filters.streaming_market_filter(market_ids=[mid]),
        context={
            "data_dir": args.out,
            "market_to_event": {mid: ev},
            "event_markets": {ev: {mid}},
            "market_type_by_id": {mid: "MATCH_ODDS"},
            "depth": int(args.depth),
        },
    )
    framework.add_strategy(strategy)
    logger.info("=== RECORDER TENNIS === market=%s event=%s out=%s", mid, ev, args.out)
    try:
        framework.run()
    except KeyboardInterrupt:
        logger.info("interrotto — chiusura file")
    finally:
        try:
            logger.info("righe scritte: %s", strategy.counts())
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
