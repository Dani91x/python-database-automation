"""Verifica la RI-ABITAZIONE tennis: il modello-tempo calcio e' neutralizzato."""

import pytest

from betfairlightweight import filters

from Betfair.stream.tennis_scalper.tennis_scalper_bot import (
    TennisScalperStrategy,
    MIN_STAKE,
)


def _make(**params):
    return TennisScalperStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        scalper_params={"stake": 2.0, **params},
    )


def test_min_stake_is_two():
    assert MIN_STAKE == 2.0


def test_football_timing_neutralized():
    s = _make()
    # in-play continuo, niente kickoff/HT
    assert s.allow_inplay is True
    assert s.inplay_from_s == 0.0
    assert s.inplay_to_s == 0.0
    assert s.max_inplay_slots == 0        # gate concorrenza in-play spento
    assert s.entry_stop_before_s == 0.0   # niente buffer pre-KO
    assert s.flatten_before_s == 0.0      # niente force-flat pre-KO


def test_point_pressure_defaults_false():
    s = _make()
    assert s.point_pressure is False


def test_stake_floored_at_two():
    s = _make(stake=0.5)      # sotto il minimo -> clampato
    assert s.stake >= MIN_STAKE


def test_allow_inplay_overridable():
    s = _make(allow_inplay=False)
    assert s.allow_inplay is False
