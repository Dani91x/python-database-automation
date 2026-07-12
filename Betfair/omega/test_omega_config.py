"""Test whitelist parametri (COSTITUZIONE_OMEGA.md §7)."""
from __future__ import annotations

from Betfair.omega import omega_config as C


def test_defaults_completi():
    p = C.resolve_params(None)
    for k in C.DEFAULTS:
        assert k in p
    assert p["price_min"] == 20.0
    assert p["price_max"] == 120.0
    assert p["stop_on_goal"] is True


def test_chiavi_sconosciute_ignorate():
    p = C.resolve_params({"hack": 999, "price_min": 30})
    assert "hack" not in p
    assert p["price_min"] == 30.0


def test_clamp_min_max():
    p = C.resolve_params({"price_max": 5000, "commission_pct": 99})
    assert p["price_max"] == 1000.0
    assert p["commission_pct"] == 20.0


def test_swap_price_invertiti():
    p = C.resolve_params({"price_min": 100, "price_max": 20})
    assert p["price_min"] == 20.0
    assert p["price_max"] == 100.0


def test_swap_minuti_invertiti():
    p = C.resolve_params({"entry_minute_min": 60, "entry_minute_max": 30})
    assert p["entry_minute_min"] == 30
    assert p["entry_minute_max"] == 60


def test_bool_da_stringa():
    p = C.resolve_params({"include_aggregate": "true", "stop_on_goal": "false"})
    assert p["include_aggregate"] is True
    assert p["stop_on_goal"] is False


def test_entry_window_source_valida():
    assert C.resolve_params({"entry_window_source": "clock"})["entry_window_source"] == "clock"
    assert C.resolve_params({"entry_window_source": "xxx"})["entry_window_source"] == "score"  # default


def test_valore_non_numerico_torna_default():
    assert C.resolve_params({"price_min": "abc"})["price_min"] == 20.0
