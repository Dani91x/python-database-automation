"""Test della serializzazione MarketBook → dict compatto (recorder)."""
from __future__ import annotations

from Betfair.stream.recorder import serialize_book


class _PS:
    def __init__(self, price, size):
        self.price = price
        self.size = size


class _Ex:
    def __init__(self, back, lay, traded=None):
        self.available_to_back = [_PS(p, s) for p, s in back]
        self.available_to_lay = [_PS(p, s) for p, s in lay]
        self.traded_volume = [_PS(p, s) for p, s in (traded or [])]


class _Runner:
    def __init__(self, selection_id, back, lay, ltp, tv, traded=None):
        self.selection_id = selection_id
        self.ex = _Ex(back, lay, traded)
        self.last_price_traded = ltp
        self.total_matched = tv


class _Book:
    def __init__(self, market_id, pt, status, inplay, tv, runners):
        self.market_id = market_id
        self.publish_time_epoch = pt
        self.status = status
        self.inplay = inplay
        self.total_matched = tv
        self.runners = runners


def test_serialize_basic():
    book = _Book(
        "1.23",
        1700000000000,
        "OPEN",
        True,
        500.0,
        [_Runner(11, [(2.0, 50.0), (1.99, 100.0)], [(2.02, 40.0)], 2.0, 80.0)],
    )
    out = serialize_book(book, depth=3)
    assert out["market_id"] == "1.23"
    assert out["pt"] == 1700000000000
    assert out["status"] == "OPEN"
    assert out["inplay"] is True
    r = out["runners"]["11"]
    assert r["b"] == [[2.0, 50.0], [1.99, 100.0]]
    assert r["l"] == [[2.02, 40.0]]
    assert r["ltp"] == 2.0


def test_serialize_depth_limit():
    book = _Book(
        "1.1", 1, "OPEN", False, 0.0,
        [_Runner(1, [(2.0, 1), (1.9, 1), (1.8, 1), (1.7, 1)], [], None, None)],
    )
    out = serialize_book(book, depth=2)
    assert len(out["runners"]["1"]["b"]) == 2


def test_serialize_empty_ladder():
    book = _Book("1.1", 1, "SUSPENDED", False, 0.0, [_Runner(1, [], [], None, None)])
    out = serialize_book(book, depth=3)
    assert out["runners"]["1"]["b"] == []
    assert out["runners"]["1"]["l"] == []
    assert "trd" not in out["runners"]["1"]  # nessun traded → chiave assente


def test_serialize_traded_volume_full():
    # il volume tradato per-prezzo è FULL (non limitato da `depth`)
    book = _Book(
        "1.5", 1, "OPEN", True, 300.0,
        [_Runner(7, [(2.0, 10), (1.9, 10), (1.8, 10)], [(2.1, 5)], 2.0, 300.0,
                 traded=[(1.95, 100), (2.0, 150), (2.05, 50), (2.1, 20)])],
    )
    out = serialize_book(book, depth=2)
    r = out["runners"]["7"]
    assert len(r["b"]) == 2                       # b/l limitati a depth=2
    assert r["trd"] == [[1.95, 100.0], [2.0, 150.0], [2.05, 50.0], [2.1, 20.0]]  # trd full
