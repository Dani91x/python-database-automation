"""Test del feed punteggio tennis e della gap-guard (break/set point)."""

import pytest

from Betfair.stream.tennis_scalper.tennis_score import (
    TennisScore,
    parse_tennis_scores,
    _rank,
)


def _payload(event_id="35790084", *, ph="40", pa="30", gh=3, ga=2,
             sh=0, sa=0, home_serving=True):
    return [{
        "eventId": event_id,
        "status": "InPlay",
        "matchStatus": "InPlay",
        "currentSet": 1,
        "score": {
            "home": {"score": ph, "games": gh, "sets": sh,
                     "isServing": home_serving, "serviceBreaks": 0},
            "away": {"score": pa, "games": ga, "sets": sa,
                     "isServing": not home_serving, "serviceBreaks": 0},
        },
    }]


def test_rank_basic():
    assert _rank("0") == 0
    assert _rank("15") == 1
    assert _rank("30") == 2
    assert _rank("40") == 3
    assert _rank("AD") == 4
    assert _rank("7") == 7      # tie-break
    assert _rank(None) is None
    assert _rank("xx") is None


def test_parse_basic_fields():
    ts = parse_tennis_scores(_payload(), "35790084")
    assert ts is not None
    assert ts.event_id == "35790084"
    assert ts.games_home == 3 and ts.games_away == 2
    assert ts.point_home == "40" and ts.point_away == "30"
    assert ts.server == "home"


def test_parse_empty_returns_none():
    assert parse_tennis_scores([], "1") is None
    assert parse_tennis_scores(None, "1") is None


def test_break_point_returner_has_ad():
    # away serve, home (ribattitore) e' in vantaggio AD -> BREAK POINT
    ts = parse_tennis_scores(
        _payload(ph="AD", pa="40", home_serving=False), "35790084")
    bp, sp, gp = ts.pressures()
    assert gp is True
    assert bp is True          # il leader (home) NON serve -> break
    assert ts.point_pressure is True


def test_server_game_point_is_not_pressure():
    # home serve ed e' a 40-30 (game point in battuta): NON deve attivare la guardia
    ts = parse_tennis_scores(_payload(ph="40", pa="30", home_serving=True),
                             "35790084")
    bp, sp, gp = ts.pressures()
    assert gp is True
    assert bp is False
    assert ts.point_pressure is False


def test_deuce_no_pressure():
    ts = parse_tennis_scores(_payload(ph="40", pa="40"), "35790084")
    bp, sp, gp = ts.pressures()
    assert (bp, sp, gp) == (False, False, False)
    assert ts.point_pressure is False


def test_set_point():
    # home avanti 5-3, 40-30: set point (a un game dal set)
    ts = parse_tennis_scores(
        _payload(ph="40", pa="30", gh=5, ga=3, home_serving=True), "35790084")
    bp, sp, gp = ts.pressures()
    assert sp is True
    assert ts.point_pressure is True   # set point attiva la guardia


def test_currentpoint_fallback():
    # senza score per-lato, si usa currentPoint "H-A"
    raw = [{
        "eventId": "1", "status": "InPlay",
        "currentPoint": "40-15",
        "score": {"home": {"games": 2, "isServing": True},
                  "away": {"games": 1, "isServing": False}},
    }]
    ts = parse_tennis_scores(raw, "1")
    assert ts.point_home == "40" and ts.point_away == "15"
