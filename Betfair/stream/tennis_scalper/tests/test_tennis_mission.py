"""Test della MISSIONE '1 tick per fase' (one_tick_per_phase), del runner_filter
'favorite' e della TRANSIZIONE pre-match→in-play dello scalper tennis."""

import types

import pytest
from betfairlightweight import filters
from flumine.order.order import OrderStatus

from Betfair.stream.tennis_scalper.tennis_scalper_bot import (
    CANCELLING,
    QUOTING,
    QUOTING2,
    TennisScalperStrategy,
    _Slot,
)


# -------- fake flumine objects (formato dict, come lo stream lightweight) ----
class _Ex:
    def __init__(self, back, lay):
        self.available_to_back = [{"price": back[0], "size": back[1]}] if back else []
        self.available_to_lay = [{"price": lay[0], "size": lay[1]}] if lay else []
        self.traded_volume = []


class _Runner:
    def __init__(self, sel, back, lay, status="ACTIVE"):
        self.selection_id = sel
        self.status = status
        self.ex = _Ex(back, lay)
        self.total_matched = 100000.0


class _MB:
    def __init__(self, runners, inplay=False, pt=1_000_000):
        self.runners = runners
        self.inplay = inplay
        self.publish_time_epoch = pt
        self.market_id = "1.1"
        self.status = "OPEN"
        self.market_definition = None


class _Market:
    market_id = "1.1"

    def __init__(self):
        self.placed = []
        self.cancelled = []

    def place_order(self, o):
        self.placed.append(o)

    def cancel_order(self, o):
        self.cancelled.append(o)


def _make(**params):
    return TennisScalperStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        scalper_params={"stake": 2.0, **params},
    )


def _slot_cycle(inplay_cycle):
    s = _Slot()
    s.inplay_cycle = inplay_cycle
    return s


def _live_order(side="BACK", price=1.90, sel=1):
    return types.SimpleNamespace(
        status=OrderStatus.EXECUTABLE, size_remaining=2.0, size_matched=0.0,
        average_price_matched=0.0, side=side, selection_id=sel,
        order_type=types.SimpleNamespace(price=price, size=2.0),
    )


# ------------------------- contabilita' di fase + mission_done ---------------
def test_green_prematch_then_inplay_completes_mission():
    events = []
    s = _make(one_tick_per_phase=True)
    s.event_sink = lambda kind, payload: events.append((kind, payload))
    s._on_cycle_closed(_slot_cycle(False), 0.10)
    assert s.stats["greens_prematch"] == 1
    assert s.stats["pnl_prematch"] == pytest.approx(0.10)
    assert s.mission_done is False
    s._on_cycle_closed(_slot_cycle(True), 0.07)
    assert s.stats["greens_inplay"] == 1
    assert s.mission_done is True
    assert s.force_flat is True  # blocco totale + chiusura di ogni residuo
    kinds = [(k, p.get("phase")) for k, p in events if k == "mission"]
    assert ("mission", "prematch") in kinds
    assert ("mission", "inplay") in kinds
    assert ("mission", "done") in kinds


def test_small_or_negative_cycles_are_not_greens():
    s = _make(one_tick_per_phase=True)
    s._on_cycle_closed(_slot_cycle(False), 0.04)   # sotto la soglia green 0.05
    s._on_cycle_closed(_slot_cycle(False), -0.30)  # stop
    assert s.stats["greens_prematch"] == 0
    assert s.mission_done is False
    assert s.stats["pnl_prematch"] == pytest.approx(-0.26)


def test_mission_done_never_outside_mission_mode():
    s = _make(one_tick_per_phase=False)
    s._on_cycle_closed(_slot_cycle(False), 0.10)
    s._on_cycle_closed(_slot_cycle(True), 0.10)
    assert s.stats["greens_prematch"] == 1 and s.stats["greens_inplay"] == 1
    assert s.mission_done is False  # fuori missione il bot NON si ferma
    assert s.force_flat is False


# ------------------------------ gating dei nuovi ingressi --------------------
def _spy_try_enter(s, calls):
    def _spy(market, market_book, runner, slot, now, bb, bl, sb, sl, mp):  # noqa: ARG001
        calls.append(int(runner.selection_id))
    s._try_enter = _spy


def test_green_prematch_blocks_prematch_entries_but_not_inplay():
    s = _make(one_tick_per_phase=True)
    calls = []
    _spy_try_enter(s, calls)
    s.stats["greens_prematch"] = 1
    m = _Market()
    mb_pre = _MB([_Runner(1, (1.90, 100), (1.92, 100)),
                  _Runner(2, (2.10, 100), (2.14, 100))])
    s.process_market_book(m, mb_pre)
    assert calls == []  # fase pre-match verde: stop ingressi pre-match
    mb_in = _MB([_Runner(1, (1.90, 100), (1.92, 100)),
                 _Runner(2, (2.10, 100), (2.14, 100))], inplay=True)
    s.process_market_book(m, mb_in)
    assert calls  # in-play ancora operativo (fase non verde)


def test_green_phase_retires_unfilled_quotes():
    # A2: con la fase verde le quote INEVASE vengono ritirate (no fill tardivi)
    s = _make(one_tick_per_phase=True)
    s.stats["greens_prematch"] = 1
    m = _Market()
    slot = s._slot("1.1", 1)
    slot.status = QUOTING2
    eb = _live_order("BACK", 1.90)
    el = _live_order("LAY", 1.88)
    slot.entry_back, slot.entry_lay = eb, el
    mb = _MB([_Runner(1, (1.88, 100), (1.90, 100))])
    s.process_market_book(m, mb)
    assert slot.status == CANCELLING
    assert eb in m.cancelled and el in m.cancelled


# ------------------------- transizione pre-match → in-play -------------------
def test_prematch_cycle_flattened_on_inplay_flip(monkeypatch):
    s = _make()  # vale SEMPRE, non solo in missione
    m = _Market()
    flattened = []
    monkeypatch.setattr(s, "_begin_flatten", lambda slot: flattened.append(slot))
    slot = s._slot("1.1", 1)
    slot.status = QUOTING
    slot.inplay_cycle = False  # ciclo nato PRE-MATCH
    entry = _live_order("BACK", 1.90)
    slot.entry = entry
    slot.entry_side = "BACK"
    s._prev_inplay["1.1"] = False  # ultimo book visto: pre-match
    mb_in = _MB([_Runner(1, (1.90, 100), (1.92, 100))], inplay=True)
    s.process_market_book(m, mb_in)
    assert flattened == [slot]     # chiusura ASAP avviata (niente attesa stop)
    assert entry in m.cancelled    # resting inevaso cancellato


def test_inplay_cycle_untouched_on_flip(monkeypatch):
    s = _make()
    m = _Market()
    flattened = []
    monkeypatch.setattr(s, "_begin_flatten", lambda slot: flattened.append(slot))
    slot = s._slot("1.1", 1)
    slot.status = QUOTING
    slot.inplay_cycle = True   # ciclo gia' nato in-play: nessun gap di apertura
    slot.entry = _live_order("BACK", 1.90)
    slot.entry_side = "BACK"
    s._prev_inplay["1.1"] = False
    s.process_market_book(m, _MB([_Runner(1, (1.90, 100), (1.92, 100))],
                                 inplay=True))
    assert flattened == []


# ------------------------------- runner_filter -------------------------------
def test_runner_filter_favorite_enters_only_on_lowest_back():
    s = _make(runner_filter="favorite")
    calls = []
    _spy_try_enter(s, calls)
    mb = _MB([_Runner(1, (1.50, 100), (1.52, 100)),
              _Runner(2, (3.00, 100), (3.10, 100))])
    s.process_market_book(_Market(), mb)
    assert calls == [1]  # solo il favorito (best-back piu' basso)


def test_runner_filter_failsafe_when_best_back_missing():
    s = _make(runner_filter="favorite")
    calls = []
    _spy_try_enter(s, calls)
    mb = _MB([_Runner(1, (1.50, 100), (1.52, 100)),
              _Runner(2, None, (3.10, 100))])  # best-back mancante: ambiguo
    s.process_market_book(_Market(), mb)
    assert calls == []  # fail-safe: nessun ingresso su nessun runner


def test_runner_filter_all_enters_on_both():
    s = _make(runner_filter="all")
    calls = []
    _spy_try_enter(s, calls)
    mb = _MB([_Runner(1, (1.50, 100), (1.52, 100)),
              _Runner(2, (3.00, 100), (3.10, 100))])
    s.process_market_book(_Market(), mb)
    assert sorted(calls) == [1, 2]
