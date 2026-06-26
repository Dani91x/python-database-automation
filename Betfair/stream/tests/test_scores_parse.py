"""Test dei parser punteggio (Betfair in-play difensivo + API-Football)."""
from __future__ import annotations

from Betfair.stream.scores.api_football import parse_fixture_response
from Betfair.stream.scores.betfair_inplay import parse_score_dict


def test_betfair_parse_standard_shape():
    raw = {
        "eventId": "31_123",
        "matchStatus": "FirstHalf",
        "timeElapsed": 36,
        "score": {"home": {"score": "1"}, "away": {"score": "0"}},
    }
    snap = parse_score_dict("31_123", raw)
    assert snap.source == "betfair"
    assert snap.minute == 36
    assert snap.score_home == 1
    assert snap.score_away == 0
    assert snap.status == "FirstHalf"
    assert snap.payload is raw  # raw conservato per audit


def test_betfair_parse_alternative_fulltime_shape():
    raw = {
        "eventId": "e",
        "status": "SecondHalf",
        "elapsedRegularTime": 70,
        "score": {"fullTime": {"home": 2, "away": 2}},
    }
    snap = parse_score_dict("e", raw)
    assert (snap.score_home, snap.score_away) == (2, 2)
    assert snap.minute == 70


def test_betfair_parse_missing_score_is_tolerant():
    snap = parse_score_dict("e", {"matchStatus": "X"})
    assert snap.score_home is None
    assert snap.score_away is None
    assert snap.status == "X"


def test_apifootball_parse():
    data = {
        "response": [
            {
                "fixture": {"id": 999, "status": {"short": "2H", "elapsed": 55}},
                "goals": {"home": 1, "away": 2},
            }
        ]
    }
    snap = parse_fixture_response("e", data)
    assert snap is not None
    assert snap.source == "api_football"
    assert snap.minute == 55
    assert (snap.score_home, snap.score_away) == (1, 2)
    assert snap.status == "2H"


def test_apifootball_empty_response():
    assert parse_fixture_response("e", {"response": []}) is None
    assert parse_fixture_response("e", {}) is None
