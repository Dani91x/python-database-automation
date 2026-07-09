"""Test ADVERSARIALI per trading/daily_pnl.py (E34 — stop giornaliero di conto).

Regole money-critical sotto test:
  - MAI un falso scatto col limite spento (None/0/negativo/non-finito).
  - MAI un mancato scatto: al limite esatto scatta; prezzi mancanti → worst-case
    conservativo (anticipa, mai ritarda).
  - MAI errori silenziosi: dati settled corrotti → ValueError, non 0.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from Betfair.stream.trading.daily_pnl import (
    DailyStopDecision,
    OpenPosition,
    day_window_utc,
    evaluate_daily_stop,
    open_mtm,
    realized_pnl,
)


# ---------------------------------------------------------------------------
# realized_pnl — somma dei profit settled (fonte: betfair_live_settled)
# ---------------------------------------------------------------------------
def test_realized_sums_profits():
    rows = [{"profit": -12.5}, {"profit": 4.0}, {"profit": 0.0}]
    assert realized_pnl(rows) == pytest.approx(-8.5)


def test_realized_empty_is_zero():
    assert realized_pnl([]) == 0.0


def test_realized_accepts_numeric_strings():
    # supabase/PostgREST può serializzare NUMERIC come stringa.
    assert realized_pnl([{"profit": "-3.25"}, {"profit": "1.00"}]) == pytest.approx(-2.25)


def test_realized_missing_profit_raises():
    with pytest.raises(ValueError):
        realized_pnl([{"market_id": "1.1"}])


def test_realized_none_profit_raises():
    with pytest.raises(ValueError):
        realized_pnl([{"profit": None}])


def test_realized_nan_raises():
    with pytest.raises(ValueError):
        realized_pnl([{"profit": float("nan")}])


def test_realized_garbage_string_raises():
    with pytest.raises(ValueError):
        realized_pnl([{"profit": "boh"}])


# ---------------------------------------------------------------------------
# open_mtm — mark-to-market posizioni aperte (blotter flumine)
# ---------------------------------------------------------------------------
def test_open_mtm_flat_positions_are_zero():
    total, degraded = open_mtm([OpenPosition(0.0, 0.0, 2.0, 2.02)])
    assert total == 0.0
    assert degraded is False


def test_open_mtm_uses_mark_to_market():
    # W=10, L=-10, best_lay=2.0 → locked = L + (W-L)/p = -10 + 20/2 = 0.0
    total, degraded = open_mtm([OpenPosition(10.0, -10.0, 1.98, 2.0)])
    assert total == pytest.approx(0.0)
    assert degraded is False


def test_open_mtm_sums_multiple_positions():
    p1 = OpenPosition(10.0, -10.0, 1.98, 2.0)      # 0.0
    p2 = OpenPosition(-6.0, 3.0, 3.0, 3.05)        # diff<0 → L + diff/back = 3 + (-9)/3 = 0.0
    total, _ = open_mtm([p1, p2])
    assert total == pytest.approx(0.0)


def test_open_mtm_missing_prices_falls_back_to_worst_case():
    # Nessun best price → si usa il worst-case (conservativo), MAI si ignora.
    pos = OpenPosition(10.0, -10.0, None, None, worst_if_win=8.0, worst_if_lose=-14.0)
    total, degraded = open_mtm([pos])
    assert total == pytest.approx(-14.0)
    assert degraded is True


def test_open_mtm_invalid_price_falls_back_to_worst_case():
    pos = OpenPosition(5.0, -5.0, 1.0, 0.0, worst_if_win=5.0, worst_if_lose=-9.0)
    total, degraded = open_mtm([pos])
    assert total == pytest.approx(-9.0)
    assert degraded is True


def test_open_mtm_nonfinite_exposures_raise():
    with pytest.raises(ValueError):
        open_mtm([OpenPosition(float("nan"), 0.0, 2.0, 2.02)])


def test_open_mtm_nonfinite_worst_case_raises_when_needed():
    pos = OpenPosition(5.0, -5.0, None, None, worst_if_win=float("inf"), worst_if_lose=float("nan"))
    with pytest.raises(ValueError):
        open_mtm([pos])


# ---------------------------------------------------------------------------
# evaluate_daily_stop — la decisione (mai falso scatto, mai mancato scatto)
# ---------------------------------------------------------------------------
def test_stop_off_when_limit_none():
    d = evaluate_daily_stop(-1000.0, -1000.0, None)
    assert d.fire is False
    assert d.reason == "limit_off"


@pytest.mark.parametrize("bad", [0.0, -50.0, float("nan"), float("inf")])
def test_stop_off_when_limit_invalid(bad):
    d = evaluate_daily_stop(-1000.0, 0.0, bad)
    assert d.fire is False
    assert d.reason in ("limit_off", "limit_invalid")


def test_stop_does_not_fire_above_limit():
    d = evaluate_daily_stop(-30.0, -19.99, 50.0)
    assert d.fire is False
    assert d.total == pytest.approx(-49.99)


def test_stop_fires_exactly_at_limit():
    d = evaluate_daily_stop(-30.0, -20.0, 50.0)
    assert d.fire is True
    assert d.total == pytest.approx(-50.0)


def test_stop_fires_beyond_limit():
    d = evaluate_daily_stop(-80.0, 10.0, 50.0)
    assert d.fire is True


def test_stop_fires_despite_float_noise_at_boundary():
    # -50 con rumore float in eccesso di 1e-12 NON deve salvare dallo scatto.
    d = evaluate_daily_stop(-25.0, -25.0 + 1e-12, 50.0)
    assert d.fire is True


def test_stop_never_fires_on_profit():
    d = evaluate_daily_stop(120.0, 30.0, 50.0)
    assert d.fire is False


def test_stop_propagates_degraded_flag():
    d = evaluate_daily_stop(-10.0, -45.0, 50.0, degraded=True)
    assert d.fire is True
    assert d.degraded is True


def test_stop_nonfinite_inputs_raise():
    with pytest.raises(ValueError):
        evaluate_daily_stop(float("nan"), 0.0, 50.0)
    with pytest.raises(ValueError):
        evaluate_daily_stop(0.0, float("inf"), 50.0)


def test_decision_is_frozen_dataclass():
    d = evaluate_daily_stop(0.0, 0.0, 50.0)
    assert isinstance(d, DailyStopDecision)
    with pytest.raises(Exception):
        d.fire = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# day_window_utc — la "giornata" è quella LOCALE del runner, espressa in UTC
# ---------------------------------------------------------------------------
def test_day_window_utc_rome_summer():
    rome = timezone(timedelta(hours=2))
    now = datetime(2026, 7, 8, 15, 30, tzinfo=rome)
    start, end = day_window_utc(now)
    assert start == datetime(2026, 7, 7, 22, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 8, 22, 0, tzinfo=timezone.utc)


def test_day_window_utc_covers_exactly_24h():
    rome = timezone(timedelta(hours=1))
    now = datetime(2026, 1, 15, 0, 0, 1, tzinfo=rome)
    start, end = day_window_utc(now)
    assert (end - start) == timedelta(days=1)
    assert start <= now.astimezone(timezone.utc) < end


def test_day_window_utc_naive_datetime_raises():
    with pytest.raises(ValueError):
        day_window_utc(datetime(2026, 7, 8, 12, 0))
