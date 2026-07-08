"""C22 — Fill-or-Kill SOFTWARE con timer (registro TTL del worker ordini).

Fix review CRITICAL: il registro NON tiene riferimenti a market/order (morti dopo un
restart di routine dello stream) ma (market_id, cust_ref, bet_id) e RI-RISOLVE
l'ordine sul framework CORRENTE a ogni sweep. Ordine scaduto e non più risolvibile →
alert CRITICAL una volta e voce rimossa (mai un retry muto all'infinito).
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Dict, List

import Betfair.stream.live_order_worker as wk


class _Market:
    def __init__(self, market_id: str = "1.1", fail: bool = False) -> None:
        self.market_id = market_id
        self.cancels: List[Any] = []
        self._fail = fail

    def cancel_order(self, order: Any) -> bool:
        if self._fail:
            raise RuntimeError("rete KO")
        self.cancels.append(order)
        return True


def _order(status: str = "EXECUTABLE", rem: float = 5.0, bet_id: str = "B1") -> Any:
    return SimpleNamespace(bet_id=bet_id, status=SimpleNamespace(name=status), size_remaining=rem)


def _fl(market: "_Market") -> Any:
    return SimpleNamespace(markets=SimpleNamespace(markets={market.market_id: market}))


def _row(rid: int = 7, ttl: Any = 5) -> Dict[str, Any]:
    return {"id": rid, "market_id": "1.1", "params": {"fok_ttl_sec": ttl}}


def _reset() -> None:
    wk._FOK_TTLS[:] = []


def _patch_resolvers(monkeypatch, order: Any) -> None:
    monkeypatch.setattr(wk, "_find_order_by_bet_id", lambda *a: order)
    monkeypatch.setattr(wk, "_find_order_by_cust_ref", lambda *a: order)


def _warp(monkeypatch, secs: float) -> None:
    real = time.monotonic  # cattura PRIMA del patch (wk.time e' lo stesso modulo)
    monkeypatch.setattr(wk.time, "monotonic", lambda: real() + secs)


def test_register_requires_positive_ttl():
    _reset()
    m = _Market()
    wk._register_fok_ttl({"id": 1, "market_id": "1.1", "params": {}}, m, _order())
    wk._register_fok_ttl({"id": 2, "market_id": "1.1", "params": None}, m, _order())
    wk._register_fok_ttl(_row(3, ttl=0), m, _order())   # 0 = FoK OFF (convenzione codebase)
    assert wk._FOK_TTLS == []
    wk._register_fok_ttl(_row(4, ttl=5), m, _order())
    assert len(wk._FOK_TTLS) == 1
    assert wk._FOK_TTLS[0]["cust_ref"] == wk._cust_ref(4)
    _reset()


def test_sweep_cancels_expired_unmatched(monkeypatch):
    _reset()
    m = _Market()
    o = _order(rem=5.0)
    wk._register_fok_ttl(_row(ttl=3), m, o)
    _patch_resolvers(monkeypatch, o)
    fl = _fl(m)
    wk._sweep_fok_ttls(fl)              # non scaduto: nessun cancel
    assert m.cancels == []
    _warp(monkeypatch, 10.0)
    wk._sweep_fok_ttls(fl)              # scaduto -> cancel sull'ordine RISOLTO ora
    assert m.cancels == [o]
    assert len(wk._FOK_TTLS) == 1       # voce tenuta finche' non e' terminale (retry-safe)
    o.status = SimpleNamespace(name="CANCELLED")
    wk._sweep_fok_ttls(fl)
    assert wk._FOK_TTLS == []
    _reset()


def test_sweep_drops_matched_without_cancel(monkeypatch):
    _reset()
    m = _Market()
    o = _order(status="EXECUTION_COMPLETE", rem=0.0)
    wk._register_fok_ttl(_row(ttl=1), m, o)
    _patch_resolvers(monkeypatch, o)
    _warp(monkeypatch, 10.0)
    wk._sweep_fok_ttls(_fl(m))
    assert m.cancels == []              # abbinato: MAI cancellare
    assert wk._FOK_TTLS == []
    _reset()


def test_sweep_retries_failed_cancel(monkeypatch):
    _reset()
    m = _Market(fail=True)
    o = _order(rem=5.0)
    wk._register_fok_ttl(_row(ttl=1), m, o)
    _patch_resolvers(monkeypatch, o)
    _warp(monkeypatch, 10.0)
    wk._sweep_fok_ttls(_fl(m))          # cancel KO -> voce mantenuta, nessun crash
    assert len(wk._FOK_TTLS) == 1
    _reset()


def test_sweep_unresolvable_after_deadline_alerts_once_and_drops(monkeypatch):
    """Fix review CRITICAL: dopo un restart l'ordine puo' non essere piu' risolvibile —
    scaduto e irrisolvibile -> alert CRITICAL una volta, voce rimossa (mai loop muto)."""
    _reset()
    m = _Market()
    wk._register_fok_ttl(_row(ttl=1), m, _order())
    _patch_resolvers(monkeypatch, None)  # blotter nuovo: ordine sparito
    alerts: List[str] = []

    def _fake_alert(entry: Dict[str, Any], why: str) -> None:
        alerts.append(why)
        entry["alerted"] = True

    monkeypatch.setattr(wk, "_fok_alert", _fake_alert)
    fl = _fl(m)
    wk._sweep_fok_ttls(fl)               # non scaduto: resta in attesa (appena piazzato)
    assert wk._FOK_TTLS and alerts == []
    _warp(monkeypatch, 10.0)
    wk._sweep_fok_ttls(fl)               # scaduto e irrisolvibile -> escalation + drop
    assert wk._FOK_TTLS == []
    assert len(alerts) == 1
    _reset()


def test_register_clamps_malformed_ttl():
    _reset()
    m = _Market()
    wk._register_fok_ttl(_row(ttl=99999), m, _order())  # oltre 1h
    assert len(wk._FOK_TTLS) == 1
    deadline = wk._FOK_TTLS[0]["deadline"]
    assert deadline - time.monotonic() <= wk._FOK_MAX_TTL_SEC + 1.0  # clampato
    _reset()
