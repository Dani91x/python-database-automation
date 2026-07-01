"""Unit test del risk_engine_worker. NESSUNA rete/ordine reale: coda Supabase, framework
flumine, market_book e blotter sono mock in-memory. La matematica usa risk_engine reale.

Scenari:
  - offset → accoda un 'place' opposto al target + regola 'done';
  - stop_loss che scatta → accoda un 'greenup' (flatten) + regola 'triggered';
  - stop_loss che NON scatta → nessun accodamento, regola resta 'armed';
  - trailing che non scatta → aggiorna trail_extreme;
  - kill-switch attivo → nessun accodamento anche se la condizione è vera;
  - posizione piatta al fire → regola 'done' senza ordine.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.risk_engine_worker as rw

_REAL_KILL = rw.low._kill_switch
_REAL_MODE = rw.low._live_order_mode


# ---------------------------------------------------------------------------
# Fake Supabase (regole + cattura enqueue via rpc)
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: List[Dict[str, Any]]) -> None:
        self._store = store
        self._op: Optional[str] = None
        self._payload: Dict[str, Any] = {}
        self._filters: List[tuple] = []
        self._limit: Optional[int] = None
        self._order: Optional[str] = None

    def select(self, *_a: Any) -> "_Query":
        self._op = "select"
        return self

    def update(self, payload: Dict[str, Any]) -> "_Query":
        self._op = "update"
        self._payload = dict(payload)
        return self

    def eq(self, k: str, v: Any) -> "_Query":
        self._filters.append((k, v))
        return self

    def order(self, k: str) -> "_Query":
        self._order = k
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def _match(self, row: Dict[str, Any]) -> bool:
        return all(row.get(k) == v for k, v in self._filters)

    def execute(self) -> _Resp:
        rows = [r for r in self._store if self._match(r)]
        if self._order:
            rows.sort(key=lambda r: r.get(self._order))
        if self._op == "select":
            if self._limit is not None:
                rows = rows[: self._limit]
            return _Resp([dict(r) for r in rows])
        for r in rows:
            r.update(self._payload)
        return _Resp([dict(r) for r in rows])


class _FakeSb:
    def __init__(self, rules: List[Dict[str, Any]]) -> None:
        self.rules = rules
        self.enqueued: List[Dict[str, Any]] = []
        self._next_req_id = 1000

    def table(self, _name: str) -> _Query:
        return _Query(self.rules)

    def rpc(self, name: str, args: Dict[str, Any]) -> "_RpcCall":
        assert name == "request_betfair_live_order"
        self.enqueued.append(args["p"])
        self._next_req_id += 1
        return _RpcCall(self._next_req_id)


class _RpcCall:
    def __init__(self, req_id: int) -> None:
        self._req_id = req_id

    def execute(self) -> _Resp:
        return _Resp(self._req_id)


# ---------------------------------------------------------------------------
# Fake flumine (market_book runner + blotter esposizioni)
# ---------------------------------------------------------------------------
def _runner(sel: int, ltp: float, best_back: float, best_lay: float) -> Any:
    ex = SimpleNamespace(
        available_to_back=[SimpleNamespace(price=best_back, size=100.0)],
        available_to_lay=[SimpleNamespace(price=best_lay, size=100.0)],
    )
    return SimpleNamespace(selection_id=sel, handicap=0.0, last_price_traded=ltp, ex=ex)


class _Blotter:
    def __init__(self, w: float, l: float) -> None:
        self._w, self._l = w, l

    def get_exposures(self, _strategy: Any, _lookup: Any) -> Dict[str, float]:
        return {"matched_profit_if_win": self._w, "matched_profit_if_lose": self._l}


def _market(market_id: str, sel: int, ltp: float, bb: float, bl: float, w: float, l: float) -> Any:
    mb = SimpleNamespace(runners=[_runner(sel, ltp, bb, bl)])
    return SimpleNamespace(market_id=market_id, market_book=mb, blotter=_Blotter(w, l))


class _Markets:
    def __init__(self, m: Dict[str, Any]) -> None:
        self.markets = m

    def __iter__(self):
        return iter(self.markets.values())


def _flumine(market: Any) -> Any:
    return SimpleNamespace(markets=_Markets({market.market_id: market}))


@pytest.fixture(autouse=True)
def _force_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rw.low, "_live_order_mode", lambda: "PAPER")
    monkeypatch.setattr(rw.low, "_kill_switch", lambda: False)


def _rule(**kw: Any) -> Dict[str, Any]:
    base = {
        "id": 1, "mode": "paper", "status": "armed", "market_id": "1.1",
        "selection_id": 47973, "handicap": 0, "entry_side": "back",
        "entry_price": 3.0, "entry_size": 10.0, "params": {}, "trail_extreme": None,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
def test_offset_enqueues_place_and_marks_done():
    rule = _rule(rule_type="offset", params={"offset_ticks": 10})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.0, 2.98, 3.0, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert len(sb.enqueued) == 1
    p = sb.enqueued[0]
    assert p["action"] == "place" and p["side"] == "lay" and p["price"] == 2.80 and p["size"] == 10.0
    assert p["client_ref"] == "risk1"
    assert rule["status"] == "done" and rule["enqueued_request_id"]


def test_stop_loss_fires_enqueues_greenup():
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10})
    sb = _FakeSb([rule])
    # LTP 3.55 >= trigger 3.50 → scatta; posizione non piatta
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert len(sb.enqueued) == 1
    assert sb.enqueued[0]["action"] == "greenup"
    assert rule["status"] == "triggered"


def test_stop_loss_no_fire_stays_armed():
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.40, 3.35, 3.4, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "armed"


def test_trailing_no_fire_updates_extreme():
    rule = _rule(rule_type="trailing_stop", params={"trail_ticks": 5}, trail_extreme=None)
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 2.80, 2.78, 2.80, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["trail_extreme"] == 2.80 and rule["status"] == "armed"


def test_kill_switch_blocks_fire(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rw.low, "_kill_switch", lambda: True)
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "armed"  # tenuta armata, riprende a freno tolto


def test_flat_position_marks_done_without_order():
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10})
    sb = _FakeSb([rule])
    # condizione di prezzo vera ma posizione piatta (W==L)
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 0.0, 0.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "done"


def test_transient_error_keeps_rule_armed():
    # fix review MEDIUM: un errore transitorio (mercato momentaneamente assente) NON deve
    # disarmare la regola protettiva → resta 'armed' e ritenta al giro dopo.
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10}, market_id="1.999")
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 20.0, -10.0))  # mercato "1.999" assente
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "armed"  # NON 'error'
