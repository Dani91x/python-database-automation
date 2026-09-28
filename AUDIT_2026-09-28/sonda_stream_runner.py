"""Sonda (CANTIERE B, 28/09): quante MarketStream apre flumine con la combinazione di
strategie del runner calcio. Nessuna rete, nessun DB: si costruisce il framework e si
chiama add_strategy come in ``runner.setup_and_run``, SENZA ``run()``.

Uso (dalla radice del repo):  python AUDIT_2026-09-28/sonda_stream_runner.py
"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_KEY", "x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import betfairlightweight  # noqa: E402
from betfairlightweight.filters import streaming_market_data_filter, streaming_market_filter  # noqa: E402
from flumine import Flumine, clients  # noqa: E402
from flumine.streams.marketstream import MarketStream  # noqa: E402

from Betfair.stream.config_stream import STREAM_FIELDS, LADDER_DEPTH, STREAM_CONFLATE_MS  # noqa: E402
from Betfair.stream.recorder import MarketRecorderStrategy  # noqa: E402
from Betfair.stream.raw_listener import RawTeeMarketStream  # noqa: E402
from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy  # noqa: E402

api = betfairlightweight.APIClient("u", "p", app_key="k", lightweight=False)
client = clients.BetfairClient(api, order_stream=True, paper_trade=True, min_bet_validation=False)
fw = Flumine(client=client)
ids = ["1.1", "1.2"]
rec = MarketRecorderStrategy(
    market_filter=streaming_market_filter(market_ids=ids),
    market_data_filter=streaming_market_data_filter(fields=list(STREAM_FIELDS),
                                                    ladder_levels=LADDER_DEPTH),
    conflate_ms=STREAM_CONFLATE_MS or None, stream_class=RawTeeMarketStream,
    context={"data_dir": ".", "market_to_event": {}, "market_type_by_id": {},
             "event_markets": {}, "depth": LADDER_DEPTH, "record_events": lambda: None})
fw.add_strategy(rec)
live = LiveTradingStrategy(market_filter=streaming_market_filter(market_ids=ids),
                           session=None, mode="paper")
fw.add_strategy(live)
ms = [s for s in fw.streams if isinstance(s, MarketStream)]
print("STREAM_FIELDS", STREAM_FIELDS, "LADDER_DEPTH", LADDER_DEPTH, "CONFLATE", STREAM_CONFLATE_MS)
print("recorder mdf", rec.market_data_filter)
print("live mdf    ", live.market_data_filter)
print("MarketStream aperte:", len(ms), [(type(s).__name__, s.stream_id) for s in ms])
print("strategie -> stream:", [(s.name, [x.stream_id for x in s.streams]) for s in fw.strategies])
print("tutti gli stream:", [type(s).__name__ for s in fw.streams])
