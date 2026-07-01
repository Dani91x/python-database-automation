"""Unit test delle azioni worker 'dutch' e 'cashout_all'. NESSUNA rete/ordine reale:
Market e coda sono mock; build_order/dutching/greenup sono reali (logica pura)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from flumine import BaseStrategy

import Betfair.stream.live_order_worker as wk

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
    def __init__(self, market_id, runners=None, exposures=None, sel_exposure=0.0):
        self.market_id = market_id
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
    wk._ORDER_TS.clear()
    yield
    wk._SETTINGS.clear()
    wk._ORDER_TS.clear()


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
    # fix review MEDIUM: le gambe dutch passano dal rate-limit (una volta, all-or-nothing).
    wk._SETTINGS["max_orders_per_min"] = 1
    monkeypatch.setattr(wk, "_now_epoch", lambda: 1000.0)
    wk._record_order()  # raggiunge il tetto
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
