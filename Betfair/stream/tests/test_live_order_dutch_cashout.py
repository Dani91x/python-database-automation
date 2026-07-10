"""Unit test delle azioni worker 'dutch' e 'cashout_all'. NESSUNA rete/ordine reale:
Market e coda sono mock; build_order/dutching/greenup sono reali (logica pura)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from flumine import BaseStrategy

import Betfair.stream.live_order_worker as wk
import Betfair.stream.trading.controls as ctl

_STRAT = BaseStrategy(market_filter={}, name="live_trading")


class _Query:
    def __init__(self, store: List[Dict[str, Any]]) -> None:
        self._store = store
        self._payload: Dict[str, Any] = {}
        self._filters: List[tuple] = []
        self._op = None

    def update(self, payload):
        self._op = "update"
        self._payload = dict(payload)
        return self

    def select(self, *_a):
        self._op = "select"
        return self

    def eq(self, k, v):
        self._filters.append((k, v))
        return self

    def execute(self):
        rows = [r for r in self._store if all(r.get(k) == v for k, v in self._filters)]
        if self._op == "update":
            for r in rows:
                r.update(self._payload)
        return SimpleNamespace(data=[dict(r) for r in rows])


class _Sb:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _n):
        return _Query(self.rows)


def _runner(sel, bb, bl):
    ex = SimpleNamespace(
        available_to_back=[SimpleNamespace(price=bb, size=100.0)],
        available_to_lay=[SimpleNamespace(price=bl, size=100.0)],
    )
    return SimpleNamespace(selection_id=sel, handicap=0.0, last_price_traded=bb, ex=ex)


class _Market:
    def __init__(self, market_id, runners=None, exposures=None, sel_exposure=0.0, event_id=None):
        self.market_id = market_id
        self.event_id = event_id
        self.placed: List[Any] = []
        self.market_book = SimpleNamespace(runners=runners or [])
        self._exp = exposures or {}
        self._sel_exp = sel_exposure
        self.blotter = self

    def place_order(self, order, customer_strategy_ref=None):
        self.placed.append(order)

    def get_exposures(self, _strat, lookup):
        return self._exp.get(lookup[1], {"matched_profit_if_win": 0.0, "matched_profit_if_lose": 0.0})

    def selection_exposure(self, _strat, _lookup):
        return self._sel_exp


@pytest.fixture(autouse=True)
def _clean_controls_state():
    wk._SETTINGS.clear()
    ctl.reset_rate_window()
    yield
    wk._SETTINGS.clear()
    ctl.reset_rate_window()


class _Markets:
    def __init__(self, m):
        self.markets = m

    def __iter__(self):
        return iter(self.markets.values())


def _fl(market):
    return SimpleNamespace(markets=_Markets({market.market_id: market}))


# ---------------------------------------------------------------------------
# dutch
# ---------------------------------------------------------------------------
def test_dutch_places_equal_profit_legs():
    row = {
        "id": 1, "market_id": "1.1", "handicap": 0, "action": "dutch",
        "params": {"selections": [{"selection_id": 10, "price": 4.0},
                                  {"selection_id": 20, "price": 4.0},
                                  {"selection_id": 30, "price": 4.0}],
                   "total_stake": 30.0, "side": "back", "mode": "equal"},
    }
    sb = _Sb([row])
    market = _Market("1.1")
    wk._do_dutch(sb, _fl(market), row, "paper", _STRAT)
    assert len(market.placed) == 3
    assert row["status"] == "done"
    legs = row["result"]["legs"]
    # profitti uguali entro arrotondamento
    profits = [leg["profit_if_wins"] for leg in legs]
    assert max(profits) - min(profits) <= 0.10
    assert sum(leg["size"] for leg in legs) == pytest.approx(30.0, abs=0.1)


def test_dutch_no_selections_errors():
    row = {"id": 2, "market_id": "1.1", "handicap": 0, "action": "dutch",
           "params": {"selections": [], "total_stake": 30.0}}
    sb = _Sb([row])
    with pytest.raises(ValueError):
        wk._do_dutch(sb, _fl(_Market("1.1")), row, "paper", _STRAT)


def test_dutch_rate_limited_places_nothing(monkeypatch):
    # fix review MEDIUM + §7.2: le gambe dutch chiedono capacità per TUTTE le gambe
    # sulla finestra CONDIVISA (all-or-nothing) prima di piazzarne una.
    wk._SETTINGS["max_orders_per_min"] = 1
    monkeypatch.setattr(ctl, "_now_epoch", lambda: 1000.0)
    ctl.record_place()  # raggiunge il tetto
    row = {"id": 5, "market_id": "1.1", "handicap": 0, "action": "dutch",
           "params": {"selections": [{"selection_id": 10, "price": 4.0},
                                     {"selection_id": 20, "price": 4.0}],
                      "total_stake": 30.0, "side": "back", "mode": "equal"}}
    market = _Market("1.1")
    with pytest.raises(ValueError):
        wk._do_dutch(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert market.placed == []  # nessuna gamba piazzata


def test_dutch_exposure_guard_all_or_nothing(monkeypatch):
    # fix review MEDIUM: pre-check esposizione di TUTTE le gambe PRIMA di piazzarne una.
    wk._SETTINGS["max_exposure_per_selection"] = 5.0  # tetto basso
    monkeypatch.setattr(wk, "_now_epoch", lambda: 1000.0)
    row = {"id": 6, "market_id": "1.1", "handicap": 0, "action": "dutch",
           "params": {"selections": [{"selection_id": 10, "price": 4.0},
                                     {"selection_id": 20, "price": 4.0}],
                      "total_stake": 30.0, "side": "back", "mode": "equal"}}
    # esposizione corrente 0 ma ogni gamba ~15 > tetto 5 → il pre-check solleva, 0 piazzati
    market = _Market("1.1", sel_exposure=0.0)
    with pytest.raises(ValueError):
        wk._do_dutch(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert market.placed == []


# ---------------------------------------------------------------------------
# cashout_all
# ---------------------------------------------------------------------------
def test_cashout_all_flattens_open_selections():
    runners = [_runner(10, 3.0, 3.05), _runner(20, 2.0, 2.02)]
    exposures = {
        10: {"matched_profit_if_win": 20.0, "matched_profit_if_lose": -10.0},  # aperta
        20: {"matched_profit_if_win": 0.0, "matched_profit_if_lose": 0.0},     # piatta
    }
    market = _Market("1.1", runners=runners, exposures=exposures)
    row = {"id": 3, "market_id": "1.1", "handicap": 0, "action": "cashout_all", "params": {"fraction": 1.0}}
    sb = _Sb([row])
    wk._do_cashout_all(sb, _fl(market), row, "paper", _STRAT)
    # solo la selezione aperta viene chiusa
    assert len(market.placed) == 1
    assert row["status"] == "done"
    assert len(row["result"]["legs"]) == 1
    assert row["result"]["legs"][0]["selection_id"] == 10


def test_cashout_all_requires_strategy():
    market = _Market("1.1", runners=[_runner(10, 3.0, 3.05)])
    row = {"id": 4, "market_id": "1.1", "handicap": 0, "action": "cashout_all", "params": {}}
    with pytest.raises(ValueError):
        wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", None)


def _fl_multi(markets):
    return SimpleNamespace(markets=_Markets({m.market_id: m for m in markets}))


def _price_of(order):
    return order.order_type.price


# ---------------------------------------------------------------------------
# #7 dutching v2 — target-profit + modalità prezzo
# ---------------------------------------------------------------------------
def test_dutch_target_profit_mode():
    row = {"id": 10, "market_id": "1.1", "handicap": 0, "action": "dutch",
           "params": {"selections": [{"selection_id": 10, "price": 4.0},
                                     {"selection_id": 20, "price": 4.0},
                                     {"selection_id": 30, "price": 4.0}],
                      "mode": "target", "target_profit": 10.0, "side": "back"}}
    sb = _Sb([row])
    market = _Market("1.1")
    wk._do_dutch(sb, _fl(market), row, "paper", _STRAT)
    assert len(market.placed) == 3
    for leg in row["result"]["legs"]:
        assert leg["profit_if_wins"] == pytest.approx(10.0, abs=0.20)


def test_dutch_pricing_best_uses_book():
    # prezzo fornito 5.0 ma pricing=best → usa best_back del book (4.0)
    runners = [_runner(10, 4.0, 4.05), _runner(20, 4.0, 4.05)]
    market = _Market("1.1", runners=runners)
    row = {"id": 11, "market_id": "1.1", "handicap": 0, "action": "dutch",
           "params": {"selections": [{"selection_id": 10, "price": 5.0},
                                     {"selection_id": 20, "price": 5.0}],
                      "total_stake": 20.0, "side": "back", "mode": "equal", "pricing": "best"}}
    wk._do_dutch(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert all(_price_of(o) == 4.0 for o in market.placed)   # book, non 5.0


def test_dutch_pricing_in_front_moves_one_tick():
    runners = [_runner(10, 4.0, 4.05), _runner(20, 4.0, 4.05)]
    market = _Market("1.1", runners=runners)
    row = {"id": 12, "market_id": "1.1", "handicap": 0, "action": "dutch",
           "params": {"selections": [{"selection_id": 10, "price": 4.0},
                                     {"selection_id": 20, "price": 4.0}],
                      "total_stake": 20.0, "side": "back", "mode": "equal", "pricing": "in_front"}}
    wk._do_dutch(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert all(_price_of(o) == 4.1 for o in market.placed)   # 1 tick sopra 4.0 (fascia 0.1)


# ---------------------------------------------------------------------------
# #8 cashout_event — flatten di TUTTI i mercati dell'evento
# ---------------------------------------------------------------------------
def test_cashout_event_flattens_all_markets():
    exp = {10: {"matched_profit_if_win": 20.0, "matched_profit_if_lose": -10.0}}
    m1 = _Market("1.1", runners=[_runner(10, 3.0, 3.05)], exposures=exp, event_id="EVT1")
    m2 = _Market("1.2", runners=[_runner(10, 3.0, 3.05)], exposures=exp, event_id="EVT1")
    m3 = _Market("1.9", runners=[_runner(10, 3.0, 3.05)], exposures=exp, event_id="OTHER")
    row = {"id": 20, "market_id": "1.1", "handicap": 0, "action": "cashout_event", "params": {}}
    sb = _Sb([row])
    wk._do_cashout_event(sb, _fl_multi([m1, m2, m3]), row, "paper", _STRAT)
    # chiude solo i mercati dell'evento EVT1 (m1, m2), NON m3 (evento diverso)
    assert len(m1.placed) == 1 and len(m2.placed) == 1 and len(m3.placed) == 0
    assert row["result"]["scope"] == "event" and row["result"]["markets"] == 2
    assert len(row["result"]["legs"]) == 2


def test_cashout_all_is_single_market_scope():
    exp = {10: {"matched_profit_if_win": 20.0, "matched_profit_if_lose": -10.0}}
    m1 = _Market("1.1", runners=[_runner(10, 3.0, 3.05)], exposures=exp, event_id="EVT1")
    row = {"id": 21, "market_id": "1.1", "handicap": 0, "action": "cashout_all", "params": {}}
    sb = _Sb([row])
    wk._do_cashout_all(sb, _fl(m1), row, "paper", _STRAT)
    assert row["result"]["scope"] == "market"
    assert len(row["result"]["legs"]) == 1
