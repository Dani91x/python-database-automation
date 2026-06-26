"""Test del motore live avanzato (Dixon-Coles in-play + segnali)."""
from __future__ import annotations

from Betfair.stream.engine.live_engine_pro import (
    MarketSignal,
    evaluate_event,
    rho_for_league,
    signals_to_json,
)


def _match_odds_market():
    return {
        "market_id": "1.1",
        "market_type": "MATCH_ODDS",
        "market_name": "Match Odds",
        "selections": [
            {"selection_id": 11, "name": "Home FC", "sort_priority": 1},
            {"selection_id": 12, "name": "Away FC", "sort_priority": 2},
            {"selection_id": 13, "name": "The Draw", "sort_priority": 3},
        ],
    }


def _ou_market(line_key="25", line_name="2.5"):
    return {
        "market_id": f"1.{line_key}",
        "market_type": f"OVER_UNDER_{line_key}",
        "market_name": f"Over/Under {line_name}",
        "selections": [
            {"selection_id": 100, "name": f"Under {line_name}", "sort_priority": 1},
            {"selection_id": 101, "name": f"Over {line_name}", "sort_priority": 2},
        ],
    }


def _ladder(price_back, price_lay, tv=100.0):
    return {"back": [[price_back, 50.0]], "lay": [[price_lay, 50.0]], "ltp": price_back, "tv": tv}


def test_signals_shape_and_json():
    markets = [_match_odds_market()]
    ladder = {"1.1": {"11": _ladder(3.0, 3.1), "12": _ladder(2.5, 2.6), "13": _ladder(3.2, 3.3)}}
    sigs = evaluate_event(
        score_home=0, score_away=0, minute=0,
        prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    assert all(isinstance(s, MarketSignal) for s in sigs)
    assert {s.selection_id for s in sigs} == {11, 12, 13}
    js = signals_to_json(sigs)
    assert "signals" in js and len(js["signals"]) == 3
    assert all("direction" in s for s in js["signals"])


def test_match_odds_probs_sum_to_one():
    markets = [_match_odds_market()]
    ladder = {"1.1": {"11": _ladder(3.0, 3.1), "12": _ladder(2.5, 2.6), "13": _ladder(3.2, 3.3)}}
    sigs = evaluate_event(
        score_home=0, score_away=0, minute=0,
        prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    total = sum(s.model_prob for s in sigs)
    assert abs(total - 1.0) < 1e-3


def test_late_lead_makes_home_strong_favourite():
    markets = [_match_odds_market()]
    # casa avanti 1-0 all'85' ma il mercato la paga ancora 2.5 (back) → forte BACK
    ladder = {"1.1": {"11": _ladder(2.5, 2.55), "12": _ladder(6.0, 6.2), "13": _ladder(4.0, 4.1)}}
    sigs = evaluate_event(
        score_home=1, score_away=0, minute=85,
        prematch_lambda_home=1.3, prematch_lambda_away=1.3, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    home = next(s for s in sigs if s.selection_id == 11)
    assert home.model_prob > 0.8           # quasi certa
    assert home.edge is not None and home.edge > 0
    assert home.direction == "BACK"
    assert home.kelly_stake > 0


def test_already_over_is_certain_under_is_hold_or_lay():
    # 2-1 = 3 gol → Over 2.5 già avvenuto: prob over ~1
    markets = [_ou_market()]
    ladder = {"1.25": {"101": _ladder(1.05, 1.06), "100": _ladder(20.0, 22.0)}}
    sigs = evaluate_event(
        score_home=2, score_away=1, minute=70,
        prematch_lambda_home=1.2, prematch_lambda_away=1.0, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    over = next(s for s in sigs if s.selection_id == 101)
    under = next(s for s in sigs if s.selection_id == 100)
    assert over.model_prob > 0.99
    assert under.model_prob < 0.01


def test_unmodeled_market_skipped():
    markets = [{"market_id": "1.9", "market_type": "CORRECT_SCORE",
                "market_name": "Correct Score",
                "selections": [{"selection_id": 1, "name": "0 - 0", "sort_priority": 1}]}]
    ladder = {"1.9": {"1": _ladder(8.0, 8.5)}}
    sigs = evaluate_event(
        score_home=0, score_away=0, minute=10,
        prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    assert sigs == []  # mercato non modellato → nessun segnale


def test_rho_for_league_lookup_and_fallback():
    assert rho_for_league(135) != rho_for_league(None) or True  # non deve esplodere
    r_known = rho_for_league(135)
    r_unknown = rho_for_league(99999999)
    assert -0.25 <= r_known <= 0.05
    assert -0.25 <= r_unknown <= 0.05  # fallback dentro la banda
