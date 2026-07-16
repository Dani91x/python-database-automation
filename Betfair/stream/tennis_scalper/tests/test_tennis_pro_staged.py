"""Fix 2026-07-09 — TennisProStrategy: niente DOPPIO HEDGE con lo staged pendente.

Col bet delay in-play del tennis (3s) l'hedge dello SCAGLIONE può essere ancora
PENDENTE quando scatta target/stop/scratch: il green finale — calcolato sulla sola
posizione MATCHED — ri-hedgerebbe l'intera size e, al fill di entrambi, la posizione
risulterebbe ROVESCIATA (over-hedge). Il fix: lo staged hedge viene TRACCIATO nel
trade e CANCELLATO prima del green finale (``_full_close``).
"""
from __future__ import annotations

from betfairlightweight import filters
from flumine.utils import price_ticks_away

from Betfair.stream.tennis_scalper.tennis_pro_bot import CLOSING, OPEN, TennisProStrategy


class _Ex:
    def __init__(self, back, lay):
        self.available_to_back = [{"price": back[0], "size": back[1]}] if back else []
        self.available_to_lay = [{"price": lay[0], "size": lay[1]}] if lay else []


class _Runner:
    def __init__(self, sel, back, lay, status="ACTIVE", ltp=None):
        self.selection_id = sel
        self.status = status
        self.last_price_traded = ltp
        self.ex = _Ex(back, lay)


class _Order:
    def __init__(self, sel, side, sm, ap):
        self.selection_id = sel
        self.side = side
        self.size_matched = sm
        self.average_price_matched = ap


class _Blotter:
    def __init__(self, orders=None):
        self.orders = orders or []

    def strategy_orders(self, _s):
        return self.orders


class _Market:
    def __init__(self, blotter=None):
        self.market_id = "1.1"
        self.blotter = blotter or _Blotter()
        self.placed = []
        self.cancelled = []

    def place_order(self, o):
        self.placed.append(o)

    def cancel_order(self, o):
        self.cancelled.append(o)


class _MB:
    def __init__(self, runners, tm=200000.0):
        self.runners = runners
        self.total_matched = tm
        self.status = "OPEN"
        self.market_id = "1.1"
        self.inplay = True
        self.publish_time_epoch = None


def _make(**p):
    return TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        pro_params={"dry_run": False, **p},
        name_to_sel={},
    )


def _open_trade(entry=1.80, target_ticks=4, stop_ticks=3, staged_done=False,
                staged_order=None):
    return {
        "state": OPEN, "sel": 111, "side": "BACK", "entry": entry,
        "target": price_ticks_away(entry, -target_ticks),
        "stop": price_ticks_away(entry, stop_ticks),
        "kind": "break_point", "staged_done": staged_done,
        "staged_order": staged_order, "order": None, "wait": 0,
        "entry_games": None,
    }


def test_staged_green_tracks_hedge_order():
    s = _make(staged=True, staged_frac=0.4)
    m = _Market(_Blotter([_Order(111, "BACK", 2.0, 1.80)]))
    s._trade["1.1"] = _open_trade()
    # a metà strada verso il target (2 tick favorevoli su 4): scatta lo scaglione
    mb = _MB([_Runner(111, (1.77, 100), (1.78, 100))])
    s.process_market_book(m, mb)
    trade = s._trade["1.1"]
    assert trade["staged_done"] is True
    assert trade["staged_order"] is not None, "hedge staged TRACCIATO nel trade"
    assert trade["state"] == OPEN, "trade ancora aperto (target non raggiunto)"


def test_final_close_cancels_pending_staged_hedge():
    s = _make(staged=True, staged_frac=0.4)
    staged = object()  # hedge staged ancora PENDENTE (bet delay 3s)
    m = _Market(_Blotter([_Order(111, "BACK", 2.0, 1.80)]))
    s._trade["1.1"] = _open_trade(staged_done=True, staged_order=staged)
    # target raggiunto (5 tick favorevoli >= 4): green TOTALE
    mb = _MB([_Runner(111, (1.74, 100), (1.75, 100))])
    s.process_market_book(m, mb)
    assert staged in m.cancelled, "staged hedge cancellato PRIMA del green finale"
    # fix audit #7: dopo il green finale la posizione va SORVEGLIATA (CLOSING),
    # mai FLAT dichiarato col solo hedge piazzato (delay 3s / cancel falliti).
    assert s._trade["1.1"]["state"] == CLOSING
    assert s.stats["greens"] == 1


def test_stop_also_cancels_pending_staged_hedge():
    s = _make(staged=True, staged_frac=0.4)
    staged = object()
    m = _Market(_Blotter([_Order(111, "BACK", 2.0, 1.80)]))
    s._trade["1.1"] = _open_trade(staged_done=True, staged_order=staged)
    # 3+ tick AVVERSI (quota su): stop
    mb = _MB([_Runner(111, (1.84, 100), (1.85, 100))])
    s.process_market_book(m, mb)
    assert staged in m.cancelled
    assert s.stats["stops"] == 1
