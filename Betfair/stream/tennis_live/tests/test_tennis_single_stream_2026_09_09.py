"""STREAM UNICO CROSS-EVENTO tennis (audit 09/09).

Prima: una capture per evento con filtro ``market_ids=[market_id]`` → flumine
apriva UNA CONNESSIONE BETFAIR PER MATCH SEGUITO (5 match = 5 delle 10
connessioni per app key). Ora una sola capture con TUTTI i mercati e bot con lo
stesso filtro, SCOPATI sul proprio mercato (money-critical: su uno stream
condiviso flumine consegna a ogni strategia i book di tutti i mercati).
"""
from __future__ import annotations

import types
from types import SimpleNamespace

from betfairlightweight.filters import streaming_market_data_filter

from Betfair.stream.tennis_live import tennis_runner


def _fake_flumine_for_streams():
    return types.SimpleNamespace(SIMULATED=False)


def _df():
    return streaming_market_data_filter(
        fields=list(tennis_runner.STREAM_FIELDS), ladder_levels=tennis_runner.LADDER_DEPTH
    )


def _book(market_id: str, status: str = "OPEN"):
    return SimpleNamespace(market_id=market_id, status=status, runners=[SimpleNamespace(selection_id=1)])


def test_una_sola_stream_per_due_eventi_e_due_bot():
    from flumine.streams.streams import Streams

    df = _df()
    ids = ["1.111", "1.222"]
    cap = tennis_runner._make_capture(ids[0], "*", market_ids=ids)
    cap.market_data_filter = df
    bot_a = tennis_runner._instantiate_bot(
        "tennis_scalper", {"stake": 2.0, "dry_run": True, "params": {}},
        "1.111", {}, lambda *a, **k: None, df, "PAPER", market_ids=ids,
    )
    bot_b = tennis_runner._instantiate_bot(
        "tennis_flb", {"stake": 2.0, "dry_run": True, "params": {}},
        "1.222", {}, lambda *a, **k: None, df, "PAPER", market_ids=ids,
    )
    streams = Streams(_fake_flumine_for_streams())
    streams(cap)
    streams(bot_a)
    streams(bot_b)
    assert len(streams) == 1                       # UNA subscription Betfair per tutti
    assert set(bot_a.stream_ids) == set(cap.stream_ids) == set(bot_b.stream_ids)
    assert sorted(cap.market_filter["marketIds"]) == ids


def test_bot_scopato_ignora_i_book_degli_altri_mercati():
    df = _df()
    ids = ["1.111", "1.222"]
    bot = tennis_runner._instantiate_bot(
        "tennis_flb", {"stake": 2.0, "dry_run": True, "params": {}},
        "1.111", {}, lambda *a, **k: None, df, "PAPER", market_ids=ids,
    )
    assert bot._tennis_scoped_market_id == "1.111"
    assert bot.check_market_book(None, _book("1.111")) is True
    assert bot.check_market_book(None, _book("1.222")) is False      # altro match: MAI
    assert bot.check_market_book(None, _book("1.111", "SUSPENDED")) is False  # gate originale conservato
    # il disarm resta più forte dello scoping (check → False costante)
    tennis_runner._disable_strategy(bot)
    assert bot.check_market_book(None, _book("1.111")) is False


def test_capture_condivisa_latest_for_isola_il_mercato():
    ids = ["1.111", "1.222"]
    cap = tennis_runner._make_capture(ids[0], "*", market_ids=ids)
    cap.market_data_filter = _df()
    # simula due book di eventi diversi sulla stessa capture
    for mid in ids:
        mb = SimpleNamespace(
            market_id=mid, status="OPEN", inplay=True, total_matched=1.0,
            market_definition=None, publish_time_epoch=0, runners=[],
        )
        cap.process_market_book(None, mb)
    assert set(cap.latest().keys()) == set(ids)
    assert list(cap.latest_for("1.111").keys()) == ["1.111"]
    assert cap.latest_for("1.999") == {}


def test_make_capture_compatibile_singolo_mercato():
    cap = tennis_runner._make_capture("1.234", "ev1")
    assert cap.market_filter["marketIds"] == ["1.234"]
    assert cap.event_id == "ev1" and cap.market_id == "1.234"
