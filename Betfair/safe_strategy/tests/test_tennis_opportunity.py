"""Test del modello OPPORTUNITA' tennis (Betfair/safe_strategy/tennis_opportunity.py).

Tutto PURO: nessuna rete, nessun DB; dati di servizio iniettati via monkeypatch.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import tennis_opportunity as TO
from Betfair.safe_strategy.tennis_opportunity import (
    DEFAULT_TENNIS_OPP_PARAMS,
    TennisOpportunityModel,
    detect_best_of,
    devig_pair,
    hold_from_serve_point,
)
from Betfair.stream.tennis_scalper import tennis_serve_data as sd
from Betfair.stream.tennis_scalper.tennis_winprob import estimate_holds

NOW = 1_000_000.0
KEYS = {
    "market_type", "market_name", "line", "market_id", "selection_id", "selection_name",
    "side", "price", "size_available", "p_model", "p_implied", "edge", "ev", "confidence",
    "rationale", "minute", "score", "kind", "extra",
}


@pytest.fixture(autouse=True)
def _no_serve_csv(monkeypatch):
    """Nessun dato di servizio di default (fallback sul prior)."""
    monkeypatch.setattr(sd, "_cache", {})


def _raw(sets=(1, 0), games=(5, 1), server="home", pts=("30", "15")):
    return {
        "eventId": "e1",
        "score": {
            "home": {"sets": sets[0], "games": games[0], "score": pts[0],
                     "isServing": server == "home"},
            "away": {"sets": sets[1], "games": games[1], "score": pts[1],
                     "isServing": server == "away"},
        },
    }


def payload(sets=(1, 0), games=(5, 1), server="home", **over) -> dict:
    """Leader p1 con un set e doppio break: back a 1.05 con 320 EUR."""
    base = {
        "event_id": "e1",
        "event_name": "Anna Rossi v Bea Verdi",
        "p1": "Anna Rossi", "p2": "Bea Verdi",
        "competition": "WTA Roma",
        "open_date": "2026-09-10T10:00:00Z",
        "inplay": True,
        "mo_market_id": "1.100",
        "mo_status": "OPEN",
        "odds": {
            "p1": {"back": 1.05, "lay": 1.06, "back_size": 320.0, "lay_size": 80.0,
                   "selection_id": 11, "ltp": 1.05},
            "p2": {"back": 16.0, "lay": 24.0, "back_size": 30.0, "lay_size": 40.0,
                   "selection_id": 22, "ltp": 17.0},
        },
        "sets": {"p1": sets[0], "p2": sets[1]},
        "games": {"p1": games[0], "p2": games[1]},
        "score_raw": _raw(sets, games, server),
        "media": {"video": True, "viz": True},
        "updated_at": NOW - 2.0,
    }
    base.update(over)
    return base


# ------------------------------------------------------------------ back leader
def test_back_leader_set_and_break():
    m = TennisOpportunityModel()
    out = m.evaluate(payload(), NOW)
    assert len(out) == 1
    o = out[0]
    assert set(o) == KEYS
    assert o["side"] == "back" and o["selection_name"] == "Anna Rossi"
    assert o["selection_id"] == 11 and o["market_id"] == "1.100"
    assert o["market_type"] == "MATCH_ODDS" and o["kind"] == "tennis"
    assert o["line"] is None and o["minute"] is None
    assert o["price"] == 1.05 and o["size_available"] == 320.0
    assert o["p_model"] >= DEFAULT_TENNIS_OPP_PARAMS["min_prob_back"]
    assert o["edge"] >= DEFAULT_TENNIS_OPP_PARAMS["min_edge"]
    assert o["ev"] > 0 and 0 < o["confidence"] <= 1
    assert o["score"] == "set 1-0 · game 5-1"
    assert o["rationale"].startswith("Back Anna Rossi a 1.05: 1 set e doppio break")
    assert "ritiro 2% incluso" in o["rationale"] and "320 EUR abbinabili" in o["rationale"]
    assert o["extra"]["retire_risk"] == 0.02
    assert o["extra"]["p_model_raw"] > o["p_model"]
    assert o["extra"]["best_of"] == 3 and o["extra"]["server"] == "p1"


def test_no_edge_no_opportunity():
    """Prezzo giusto (1.02 su p~0.97): edge sotto soglia -> niente."""
    p = payload()
    p["odds"]["p1"]["back"] = 1.02
    assert TennisOpportunityModel().evaluate(p, NOW) == []


def test_min_back_price_gate():
    p = payload()
    p["odds"]["p1"]["back"] = 1.01
    assert TennisOpportunityModel().evaluate(p, NOW) == []
    # anche senza la soglia: a 1.01 la commissione rende l'EV negativo
    assert TennisOpportunityModel({"min_back_price": 1.0, "min_edge": 0.0}).evaluate(p, NOW) == []


def test_min_size_gate():
    p = payload()
    p["odds"]["p1"]["back_size"] = 10.0
    assert TennisOpportunityModel().evaluate(p, NOW) == []


# ------------------------------------------------------------------ lay trailer
def test_lay_trailer():
    p = payload()
    p["odds"]["p2"]["lay"] = 7.0         # mercato che sopravvaluta chi insegue
    out = TennisOpportunityModel().evaluate(p, NOW)
    lays = [o for o in out if o["side"] == "lay"]
    assert len(lays) == 1
    o = lays[0]
    assert o["selection_name"] == "Bea Verdi" and o["selection_id"] == 22
    assert o["p_model"] <= DEFAULT_TENNIS_OPP_PARAMS["max_prob_lay"]
    assert o["price"] == 7.0 and o["size_available"] == 40.0
    assert o["edge"] == pytest.approx(1 / 7.0 - o["p_model"], abs=1e-6)
    assert o["ev"] > 0
    assert o["rationale"].startswith("Lay Bea Verdi a 7.00: sotto 0-1 nei set e sotto 1-5 nel set")


def test_lay_trailer_price_too_high():
    p = payload()
    p["odds"]["p2"]["lay"] = 9.0
    assert all(o["side"] != "lay" for o in TennisOpportunityModel().evaluate(p, NOW))


def test_sort_and_cap():
    p = payload()
    p["odds"]["p2"]["lay"] = 7.0
    out = TennisOpportunityModel().evaluate(p, NOW)
    assert len(out) == 2
    scores = [o["ev"] * o["confidence"] for o in out]
    assert scores == sorted(scores, reverse=True)
    assert len(TennisOpportunityModel({"max_per_event": 1}).evaluate(p, NOW)) == 1


# ------------------------------------------------------------------ gate
def test_tiebreak_gate():
    m = TennisOpportunityModel()
    p = payload(games=(6, 6))
    assert m.evaluate(p, NOW) == []
    assert m._gates_ok(p, m._state(p)) is False
    m2 = TennisOpportunityModel({"allow_tiebreak": True})
    assert m2._gates_ok(p, m2._state(p)) is True


def test_deciding_set_late_gate():
    m = TennisOpportunityModel()
    p = payload(sets=(1, 1), games=(5, 2))
    assert m._gates_ok(p, m._state(p)) is False
    p2 = payload(sets=(1, 1), games=(4, 1))
    assert m._gates_ok(p2, m._state(p2)) is True
    m3 = TennisOpportunityModel({"allow_deciding_late": True})
    assert m3._gates_ok(p, m3._state(p)) is True


def test_doubles_excluded():
    p = payload(p1="Rossi / Bianchi", p2="Verdi / Neri")
    assert TennisOpportunityModel().evaluate(p, NOW) == []
    assert TennisOpportunityModel({"exclude_doubles": False}).evaluate(p, NOW)


def test_competition_excluded():
    m = TennisOpportunityModel({"exclude_competitions": ["itf", "Roma"]})
    assert m.evaluate(payload(), NOW) == []
    assert m.evaluate(payload(competition="ATP Torino"), NOW)


def test_market_closed_or_not_inplay():
    m = TennisOpportunityModel()
    assert m.evaluate(payload(mo_status="SUSPENDED"), NOW) == []
    assert m.evaluate(payload(inplay=False), NOW) == []
    assert m.evaluate(payload(sets=(2, 0), games=(0, 0)), NOW) == []   # match finito


def test_stale_odds():
    m = TennisOpportunityModel()
    assert m.evaluate(payload(updated_at=NOW - 40.0), NOW) == []
    fresh = m.evaluate(payload(updated_at=NOW - 1.0), NOW)[0]
    aged = m.evaluate(payload(updated_at=NOW - 20.0), NOW)[0]
    assert aged["confidence"] < fresh["confidence"]
    assert aged["extra"]["price_age_s"] == 20.0
    # ISO ed epoch ms accettati
    assert m.evaluate(payload(updated_at="2026-09-10T12:00:00+00:00"), 1789041601.0)
    assert m.evaluate(payload(updated_at=(NOW - 3) * 1000), NOW)


def test_missing_score_returns_nothing():
    p = payload()
    p["sets"] = None
    p["games"] = None
    p["score_raw"] = None
    m = TennisOpportunityModel()
    assert m.evaluate(p, NOW) == []
    assert m.p_win(p, "p1") is None


def test_score_from_raw_only():
    """sets/games assenti ma score_raw IPS presente: si usa il parser tennis."""
    p = payload()
    p["sets"] = None
    p["games"] = None
    assert TennisOpportunityModel().p_win(p, "p1") == pytest.approx(
        TennisOpportunityModel().p_win(payload(), "p1"))


# ------------------------------------------------------------------ modello
def test_p_win_symmetric():
    m = TennisOpportunityModel()
    for sets, games in ((0, 0), (0, 0)), ((1, 0), (5, 1)), ((0, 1), (2, 4)), ((1, 1), (3, 3)):
        p = payload(sets=sets, games=games)
        assert m.p_win(p, "p1") + m.p_win(p, "p2") == pytest.approx(1.0, abs=1e-5)
    assert m.p_win(payload(), "px") is None


def test_server_matters():
    m = TennisOpportunityModel()
    serve = m.p_win(payload(sets=(0, 0), games=(3, 2), server="home"), "p1")
    ret = m.p_win(payload(sets=(0, 0), games=(3, 2), server="away"), "p1")
    unk = m.p_win(payload(sets=(0, 0), games=(3, 2), server=None), "p1")
    assert serve > unk > ret


def test_retirement_adjustment():
    p = payload()
    m0 = TennisOpportunityModel({"retire_risk": 0.0})
    m2 = TennisOpportunityModel()
    assert m0.p_win(p, "p1") - m2.p_win(p, "p1") == pytest.approx(0.02, abs=1e-6)
    assert m2.p_win(p, "p2") - m0.p_win(p, "p2") == pytest.approx(0.02, abs=1e-6)
    o = m2.evaluate(p, NOW)[0]
    assert o["extra"]["p_model_raw"] - o["p_model"] == pytest.approx(0.02, abs=1e-5)
    # best-of-5: rischio maggiore
    m5 = TennisOpportunityModel({"best_of": 5})
    p5 = payload(sets=(2, 0), games=(5, 1))
    p5["odds"]["p1"]["back"] = 1.06
    o5 = m5.evaluate(p5, NOW)[0]
    assert o5["extra"]["retire_risk"] == 0.03 and o5["extra"]["best_of"] == 5
    assert "ritiro 3% incluso" in o5["rationale"]


def _pl(games, **over):
    """Come payload() ma con back del leader a 1.10 (edge anche sul 5-3)."""
    p = payload(games=games, **over)
    p["odds"]["p1"]["back"] = 1.10
    return p


def test_momentum_penalty_from_prev_payload():
    base = TennisOpportunityModel().evaluate(payload(), NOW)[0]
    cur = _pl((5, 3), prev_payload=payload(games=(5, 1)))   # il leader ha perso 2 game
    hit = TennisOpportunityModel().evaluate(cur, NOW)[0]
    ref = TennisOpportunityModel().evaluate(_pl((5, 3)), NOW)[0]
    assert hit["extra"]["momentum_against"] is True and ref["extra"]["momentum_against"] is False
    assert hit["confidence"] == pytest.approx(ref["confidence"] * 0.5, abs=1e-3)
    assert base["extra"]["momentum_against"] is False


def test_momentum_penalty_from_internal_memory():
    m = TennisOpportunityModel()
    m.evaluate(_pl((5, 1)), NOW)
    m.evaluate(_pl((5, 2), updated_at=NOW + 59), NOW + 60)
    o = m.evaluate(_pl((5, 3), updated_at=NOW + 119), NOW + 120)[0]
    assert o["extra"]["momentum_against"] is True
    assert m.evaluate(_pl((0, 0), sets=(2, 0), updated_at=NOW + 179), NOW + 180) == []  # finito
    # il leader vince l'ultimo game: nessuna penalita'
    m2 = TennisOpportunityModel()
    m2.evaluate(_pl((4, 1)), NOW)
    m2.evaluate(_pl((4, 2), updated_at=NOW + 59), NOW + 60)
    o3 = m2.evaluate(_pl((5, 2), updated_at=NOW + 119), NOW + 120)[0]
    assert o3["extra"]["momentum_against"] is False


def test_devig():
    p1, p2 = devig_pair(1.05, 16.0)
    assert p1 + p2 == pytest.approx(1.0)
    assert p1 == pytest.approx((1 / 1.05) / (1 / 1.05 + 1 / 16.0))
    assert devig_pair(1.05, None) == (pytest.approx(1 / 1.05), None)
    assert devig_pair(None, None) == (None, None)
    o = TennisOpportunityModel().evaluate(payload(), NOW)[0]
    assert o["p_implied"] == pytest.approx(p1, abs=1e-6)
    assert o["p_implied"] < 1 / 1.05


def test_serve_data_fallback(monkeypatch):
    m = TennisOpportunityModel()
    p = payload(sets=(0, 0), games=(3, 2))
    prior = m.p_win(p, "p1")
    ha, hb = m._holds(p)
    assert ha == hb == pytest.approx(estimate_holds(0, 0, 0, 0, prior=0.75)[0])
    monkeypatch.setattr(sd, "_cache", {"anna rossi": 0.70, "bea verdi": 0.58})
    ha2, hb2 = m._holds(p)
    assert ha2 == pytest.approx(hold_from_serve_point(0.70)) and ha2 > hb2
    assert m.p_win(p, "p1") > prior
    monkeypatch.setattr(sd, "_cache", {"anna rossi": 0.70})   # solo un giocatore
    ha3, hb3 = m._holds(p)
    assert ha3 == ha2 and hb3 == hb


def test_hold_from_serve_point():
    assert hold_from_serve_point(0.5) == pytest.approx(0.5)
    assert hold_from_serve_point(0.65) > 0.8
    assert hold_from_serve_point(0.0) == 0.0 and hold_from_serve_point(1.0) == 1.0


def test_best_of_detection():
    prm = DEFAULT_TENNIS_OPP_PARAMS
    assert detect_best_of("Wimbledon 2026", (0, 0), prm) == 5
    assert detect_best_of("Wimbledon 2026 - Women's", (0, 0), prm) == 3
    assert detect_best_of("US Open 2026 Qualifying", (0, 0), prm) == 3
    assert detect_best_of("ATP Torino", (0, 0), prm) == 3
    assert detect_best_of("ATP Torino", (2, 1), prm) == 5      # gia' 3 set giocati
    assert detect_best_of("Wimbledon 2026", (0, 0), {**prm, "best_of": 3}) == 3
    assert detect_best_of(None, (0, 0), prm) == 3
    m = TennisOpportunityModel()
    assert m._state(payload(competition="Roland Garros 2026")).best_of == 5
    # 1 set avanti in un best-of-5 vale meno che in un best-of-3
    assert m.p_win(payload(competition="Roland Garros 2026"), "p1") < m.p_win(payload(), "p1")


def test_params_merge_and_clock():
    m = TennisOpportunityModel({"min_edge": 0.05, "min_size": None}, clock=lambda: NOW)
    assert m.params["min_edge"] == 0.05
    assert m.params["min_size"] == DEFAULT_TENNIS_OPP_PARAMS["min_size"]
    assert m._clock() == NOW
    assert DEFAULT_TENNIS_OPP_PARAMS["min_edge"] == 0.015    # default non toccato


def test_winners_between():
    w = TennisOpportunityModel._winners_between
    assert w((1, 0), (5, 1), (1, 0), (5, 3)) == ["p2", "p2"]
    assert w((1, 0), (5, 1), (1, 0), (6, 2)) == ["p1", "p2"]
    assert w((0, 0), (5, 3), (1, 0), (0, 1)) == ["p1", "p2"]
    assert w((1, 0), (5, 3), (1, 0), (4, 3)) == []          # incoerente
    assert TO._age_s(None, NOW) is None
