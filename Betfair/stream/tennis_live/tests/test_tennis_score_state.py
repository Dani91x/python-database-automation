"""Test della derivazione TennisScoreState (lib/tennis.ts) da un TennisScore."""

from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores
from Betfair.stream.tennis_live.tennis_runner import point_event, tennis_score_state


def _payload(*, ph="40", pa="30", gh=3, ga=2, sh=0, sa=0, home_serving=True,
             breaks_home=0, breaks_away=0, current_set=1):
    return [{
        "eventId": "35790084",
        "status": "InPlay",
        "matchStatus": "InPlay",
        "currentSet": current_set,
        "currentGame": 6,
        "score": {
            "home": {"score": ph, "games": gh, "sets": sh, "isServing": home_serving,
                     "serviceBreaks": breaks_home, "gameSequence": ["6", "3"]},
            "away": {"score": pa, "games": ga, "sets": sa, "isServing": not home_serving,
                     "serviceBreaks": breaks_away, "gameSequence": ["4", "6"]},
        },
    }]


def test_none_returns_none():
    assert tennis_score_state(None) is None


def test_basic_mapping_p1_home_p2_away():
    ts = parse_tennis_scores(_payload(), "35790084")
    st = tennis_score_state(ts)
    assert st["sets"] == {"p1": 0, "p2": 0}
    assert st["games"] == {"p1": 3, "p2": 2}
    assert st["points"] == {"p1": "40", "p2": "30"}
    assert st["server"] == 1                 # home serve → p1
    assert st["current_set"] == 1
    assert st["current_game"] == 6
    assert st["source"] == "ips"
    assert isinstance(st["updated_ms"], int)


def test_game_sequence_and_set_summary():
    ts = parse_tennis_scores(_payload(), "35790084")
    st = tennis_score_state(ts)
    assert st["game_sequence"] == {"p1": ["6", "3"], "p2": ["4", "6"]}
    assert st["set_summary"] == "6-4 3-6"


def test_pressure_break_point():
    # away serve, home (ribattitore) ha AD → break point
    ts = parse_tennis_scores(_payload(ph="AD", pa="40", home_serving=False), "35790084")
    st = tennis_score_state(ts)
    assert st["pressure"]["break_point"] is True
    assert st["pressure"]["game_point"] is True
    assert st["server"] == 2


def test_service_breaks_mapped():
    ts = parse_tennis_scores(_payload(breaks_home=1, breaks_away=2), "35790084")
    st = tennis_score_state(ts)
    assert st["service_breaks"] == {"p1": 1, "p2": 2}


def test_tiebreak_detection_on_six_all():
    ts = parse_tennis_scores(_payload(ph="5", pa="3", gh=6, ga=6), "35790084")
    st = tennis_score_state(ts)
    assert st["tiebreak"] is True


def test_win_prob_p1_in_range():
    ts = parse_tennis_scores(_payload(gh=5, ga=3, home_serving=True), "35790084")
    st = tennis_score_state(ts)
    assert st["win_prob_p1"] is None or 0.0 <= st["win_prob_p1"] <= 1.0


def test_win_prob_leader_above_half():
    # p1 avanti 1 set e 5-3 al servizio → win_prob_p1 alto
    ts = parse_tennis_scores(_payload(sh=1, sa=0, gh=5, ga=3, home_serving=True), "35790084")
    st = tennis_score_state(ts)
    assert st["win_prob_p1"] is not None
    assert st["win_prob_p1"] > 0.5


def test_point_event_winner_from_game_gain():
    prev = parse_tennis_scores(_payload(gh=3, ga=2), "35790084")
    cur = parse_tennis_scores(_payload(gh=4, ga=2, ph="0", pa="0"), "35790084")
    evt = point_event(prev, cur)
    assert evt is not None
    assert evt["winner"] == 1                # p1 ha guadagnato un game
    assert evt["score_after"] == "0-0"


def test_point_event_no_prev_has_no_winner():
    cur = parse_tennis_scores(_payload(), "35790084")
    evt = point_event(None, cur)
    assert evt is not None
    assert evt["winner"] is None
