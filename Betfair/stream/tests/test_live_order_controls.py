"""Test delle guardie Fase 6 nel live_order_worker: kill-switch DB, rate-limit,
max esposizione per selezione, audit. Nessuna rete: settings/blotter mockati."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import Betfair.stream.live_order_worker as wk


@pytest.fixture(autouse=True)
def _clean_state():
    wk._SETTINGS.clear()
    wk._ORDER_TS.clear()
    yield
    wk._SETTINGS.clear()
    wk._ORDER_TS.clear()


# ---------------------------------------------------------------------------
# kill-switch DB
# ---------------------------------------------------------------------------
def test_db_kill_switch_from_settings():
    assert wk._db_kill_switch() is False
    wk._SETTINGS["kill_switch"] = True
    assert wk._db_kill_switch() is True


# ---------------------------------------------------------------------------
# rate-limit (finestra scorrevole 60s)
# ---------------------------------------------------------------------------
def test_rate_limit_disabled_when_unset():
    assert wk._rate_limited() is False


def test_rate_limit_trips_at_cap(monkeypatch):
    wk._SETTINGS["max_orders_per_min"] = 2
    t = [1000.0]
    monkeypatch.setattr(wk, "_now_epoch", lambda: t[0])
    assert wk._rate_limited() is False
    wk._record_order()
    wk._record_order()
    assert wk._rate_limited() is True          # raggiunto il tetto
    t[0] += 61.0                                # oltre la finestra → si azzera
    assert wk._rate_limited() is False


# ---------------------------------------------------------------------------
# max esposizione per selezione
# ---------------------------------------------------------------------------
class _Blotter:
    def __init__(self, exposure):
        self._e = exposure

    def selection_exposure(self, _strat, _lookup):
        return self._e


def _market(exposure):
    return SimpleNamespace(market_id="1.1", blotter=_Blotter(exposure))


def test_exposure_guard_disabled_when_unset():
    # nessun cap → non blocca mai
    wk._check_exposure_guard(_market(1000.0), object(), 10, 0.0, 500.0)


def test_exposure_guard_blocks_over_cap():
    wk._SETTINGS["max_exposure_per_selection"] = 50.0
    with pytest.raises(ValueError):
        # esposizione corrente 40 + ordine 20 = 60 > 50
        wk._check_exposure_guard(_market(40.0), object(), 10, 0.0, 20.0)


def test_exposure_guard_allows_under_cap():
    wk._SETTINGS["max_exposure_per_selection"] = 50.0
    wk._check_exposure_guard(_market(20.0), object(), 10, 0.0, 20.0)  # 40 <= 50 → ok


def test_exposure_guard_defensive_on_error():
    wk._SETTINGS["max_exposure_per_selection"] = 50.0
    bad = SimpleNamespace(market_id="1.1", blotter=None)  # niente blotter
    wk._check_exposure_guard(bad, object(), 10, 0.0, 999.0)  # non solleva


# ---------------------------------------------------------------------------
# audit best-effort (non deve mai sollevare)
# ---------------------------------------------------------------------------
def test_audit_best_effort_swallows_errors():
    class _NoInsert:
        def table(self, _n):
            raise RuntimeError("boom")
    wk._audit(_NoInsert(), 1, {"action": "place", "mode": "paper"}, "done")  # nessuna eccezione


# ---------------------------------------------------------------------------
# #15 velocità runtime (throttle self-pacing)
# ---------------------------------------------------------------------------
def test_throttle_disabled_when_target_none(monkeypatch):
    wk._LAST_CYCLE.clear()
    assert wk._throttled("x", None) is False
    assert wk._throttled("x", 0) is False


def test_throttle_slows_to_target(monkeypatch):
    wk._LAST_CYCLE.clear()
    t = [1000.0]
    monkeypatch.setattr(wk, "_now_epoch", lambda: t[0])
    assert wk._throttled("y", 2.0) is False    # prima: passa e imposta last
    assert wk._throttled("y", 2.0) is True     # entro 2s: salta
    t[0] += 2.1
    assert wk._throttled("y", 2.0) is False     # oltre 2s: passa di nuovo


def test_poll_targets_from_settings():
    wk._SETTINGS.clear()
    assert wk._order_poll_target() is None and wk._risk_poll_target() is None
    wk._SETTINGS["order_poll_sec"] = 3.0
    wk._SETTINGS["risk_poll_sec"] = 1.5
    assert wk._order_poll_target() == 3.0 and wk._risk_poll_target() == 1.5
