"""Test whitelist parametri Mike (config.PARAM_SPEC / merge_params).

Nessuna rete. File ASCII-only.
"""
from __future__ import annotations

from Betfair.mike import config as C


def test_every_spec_default_is_inside_bounds():
    for key, spec in C.PARAM_SPEC.items():
        default, cast, lo, hi, choices = spec
        if choices is not None:
            assert default in choices, key
            continue
        if cast in (int, float):
            if lo is not None:
                assert default >= lo, key
            if hi is not None:
                assert default <= hi, key


def test_defaults_match_plan():
    d = C.DEFAULTS
    assert d["stake"] == 10.0
    assert d["entry_hours_before_ko"] == 3.0
    assert d["pre_green_ticks"] == 2
    assert d["cover_profit_factor"] == 1.2
    assert d["cashout_profit_pct"] == 5.0
    assert d["ht_loss_pct"] == 25.0
    assert d["h2_loss_pct"] == 25.0
    assert d["pre_exit_mode"] == "taker"
    assert d["exact_sizes"] is True
    assert d["cover_policy"] == "auto"
    assert d["max_matches"] == 40


def test_merge_clamps_and_casts():
    p = C.merge_params({"stake": "1000", "pre_green_ticks": "0", "commission_pct": -3, "stake_x": 1,
                        "pre_enabled": "false", "cover_policy": "wait"})
    assert p["stake"] == 500.0
    assert p["pre_green_ticks"] == 1
    assert p["commission_pct"] == 0.0
    assert p["pre_enabled"] is False
    assert p["cover_policy"] == "wait"


def test_merge_drops_unknown_and_mode_is_never_a_param():
    p = C.merge_params({"mode": "live", "foo": 1, "stake": 10})
    assert "mode" not in p
    assert "foo" not in p
    assert p["stake"] == 10.0
    # tutte le chiavi note sono presenti
    assert set(p.keys()) == set(C.PARAM_SPEC.keys())


def test_merge_invalid_choice_falls_back_to_default():
    p = C.merge_params({"pre_exit_mode": "banana", "cover_rounding": "up"})
    assert p["pre_exit_mode"] == "taker"
    assert p["cover_rounding"] == "ceil"


def test_merge_none_returns_defaults():
    assert C.merge_params(None) == C.DEFAULTS


def test_env_helpers(monkeypatch):
    monkeypatch.setenv("MIKE_TEST_INT", "  7 ")
    monkeypatch.setenv("MIKE_TEST_EMPTY", "")
    assert C.env_int("MIKE_TEST_INT", 3) == 7
    assert C.env_int("MIKE_TEST_EMPTY", 3) == 3
    assert C.env_int("MIKE_TEST_MISSING", 3) == 3
    assert C.env_str("MIKE_TEST_EMPTY", "x") == "x"


def test_inverted_min_max_pairs_fall_back_to_defaults():
    p = C.merge_params({"pre_entry_price_min": 2.5, "pre_entry_price_max": 1.5,
                        "h2_loss_from_min": 80, "h2_loss_to_min": 60})
    assert (p["pre_entry_price_min"], p["pre_entry_price_max"]) == (1.30, 3.00)
    assert (p["h2_loss_from_min"], p["h2_loss_to_min"]) == (46, 85)
    ok = C.merge_params({"pre_entry_price_min": 1.4, "pre_entry_price_max": 2.0})
    assert (ok["pre_entry_price_min"], ok["pre_entry_price_max"]) == (1.4, 2.0)


def test_stake_floor_is_half_euro_but_any_amount_above():
    assert C.merge_params({"stake": 0.1})["stake"] == 0.5
    assert C.merge_params({"stake": 1.23})["stake"] == 1.23


def test_constants():
    assert C.OU35 == "OVER_UNDER_35"
    assert C.OU45 == "OVER_UNDER_45"
    assert C.EXPECTED_SEL["UNDER_35"] == 1222344
    assert C.EXPECTED_SEL["OVER_45"] == 1222346
    assert C.LOCK_PORT_DEFAULT == 47319
