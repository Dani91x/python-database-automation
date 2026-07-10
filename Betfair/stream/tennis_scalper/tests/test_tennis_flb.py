"""Test della TennisFLBStrategy (lay del favorito estremo, no stop)."""

import pytest
from betfairlightweight import filters

from Betfair.stream.tennis_scalper.tennis_flb_bot import (
    TennisFLBStrategy, OPEN,
)


# -------- fake flumine objects (formato dict, come lo stream lightweight) --------
class _Ex:
    def __init__(self, back, lay):
        self.available_to_back = [{"price": back[0], "size": back[1]}] if back else []
        self.available_to_lay = [{"price": lay[0], "size": lay[1]}] if lay else []


class _Runner:
    def __init__(self, sel, back, lay, status="ACTIVE", ltp=None):
        self.selection_id = sel; self.status = status
        self.last_price_traded = ltp; self.ex = _Ex(back, lay)


class _Blotter:
    def strategy_orders(self, _s): return []


class _Market:
    market_id = "1.1"; blotter = _Blotter()
    def place_order(self, o): pass
    def cancel_order(self, o): pass


class _MB:
    def __init__(self, runners, tm=100000.0, status="OPEN", inplay=True):
        self.runners = runners; self.total_matched = tm
        self.status = status; self.market_id = "1.1"
        # tesi FLB validata IN-PLAY (require_inplay default True): i book dei
        # test di ingresso sono in-play; il gate pre-match ha un test dedicato.
        self.inplay = inplay


def _make(**p):
    return TennisFLBStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        flb_params={"dry_run": True, **p})


def test_net_math():
    # LAY 2 @ 1.10: se vince -2*.1=-0.2 ; se perde +2
    nw, nl = TennisFLBStrategy._net(0.0, 0.0, 2.0, 1.10)
    assert nw == pytest.approx(-0.2)
    assert nl == pytest.approx(2.0)


def test_lays_extreme_favourite():
    s = _make(lay_max=1.10, min_lay_size=5.0)
    mb = _MB([_Runner(111, (1.09, 200), (1.10, 200), ltp=1.10),
              _Runner(222, (5.0, 50), (5.5, 50), ltp=5.2)])
    s.process_market_book(_Market(), mb)
    assert s.stats["entries"] == 1
    st = s._pos_state[("1.1", 111)]
    assert st["state"] == OPEN and st["entry"] == 1.10


def test_skips_non_extreme():
    s = _make(lay_max=1.10)
    mb = _MB([_Runner(111, (1.28, 200), (1.30, 200), ltp=1.30)])
    s.process_market_book(_Market(), mb)
    assert s.stats["entries"] == 0


def test_skips_thin_liquidity():
    s = _make(lay_max=1.10, min_lay_size=50.0)
    mb = _MB([_Runner(111, (1.09, 10), (1.10, 10), ltp=1.10)])  # size 10 < 50
    s.process_market_book(_Market(), mb)
    assert s.stats["entries"] == 0


def test_skips_low_matched():
    s = _make(lay_max=1.10, min_matched=50000.0)
    mb = _MB([_Runner(111, (1.09, 200), (1.10, 200), ltp=1.10)], tm=5000.0)
    s.process_market_book(_Market(), mb)
    assert s.stats["entries"] == 0


def test_rearm_only_after_leaving_zone():
    s = _make(lay_max=1.10, rearm_mult=1.10)
    m = _Market()
    s.process_market_book(m, _MB([_Runner(111, (1.09, 200), (1.10, 200), ltp=1.10)]))
    assert s.stats["entries"] == 1
    # marca il trade come chiuso, resta disarmato finche' il prezzo non esce dalla zona
    s._pos_state[("1.1", 111)] = {"state": "DONE"}
    s.process_market_book(m, _MB([_Runner(111, (1.10, 200), (1.11, 200), ltp=1.11)]))
    assert s.stats["entries"] == 1        # ancora disarmato (1.11 < 1.10*1.10=1.21)
    s.process_market_book(m, _MB([_Runner(111, (1.24, 200), (1.25, 200), ltp=1.25)]))
    # ora e' uscito dalla zona -> ri-armato; torna in zona -> ri-laya
    s._pos_state.pop(("1.1", 111), None)
    s.process_market_book(m, _MB([_Runner(111, (1.09, 200), (1.10, 200), ltp=1.10)]))
    assert s.stats["entries"] == 2


def test_liability_is_small_at_short_odds():
    # a 1.10 con stake 2: liability = 2*0.10 = 0.20 (asimmetria FLB)
    s = _make(lay_max=1.10, stake=2.0)
    assert round(s.stake * (1.10 - 1.0), 2) == 0.20


def test_require_inplay_blocks_prematch_entry():
    # default require_inplay=True: nessun ingresso su book PRE-MATCH
    s = _make(lay_max=1.10, min_lay_size=5.0)
    mb = _MB([_Runner(111, (1.09, 200), (1.10, 200), ltp=1.10)], inplay=False)
    s.process_market_book(_Market(), mb)
    assert s.stats["entries"] == 0


def test_require_inplay_off_allows_prematch_entry():
    s = _make(lay_max=1.10, min_lay_size=5.0, require_inplay=False)
    mb = _MB([_Runner(111, (1.09, 200), (1.10, 200), ltp=1.10)], inplay=False)
    s.process_market_book(_Market(), mb)
    assert s.stats["entries"] == 1
