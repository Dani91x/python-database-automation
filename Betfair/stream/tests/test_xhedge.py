"""Test hedging cross-market (modello scoreline). Verifica risolutori mercati, P&L per
scoreline e il suggerimento di copertura sul Correct Score."""
from __future__ import annotations

import pytest

from Betfair.stream.trading import xhedge as x


# ---------------------------------------------------------------------------
# risolutori: la selezione vince nello scoreline?
# ---------------------------------------------------------------------------
def test_match_odds_resolver():
    assert x.selection_wins("MATCH_ODDS", "HOME", 1, 0) is True
    assert x.selection_wins("MATCH_ODDS", "HOME", 0, 0) is False
    assert x.selection_wins("MATCH_ODDS", "DRAW", 2, 2) is True
    assert x.selection_wins("MATCH_ODDS", "AWAY", 0, 1) is True


def test_over_under_resolver():
    assert x.selection_wins("OVER_UNDER", "OVER", 2, 1, line=2.5) is True   # 3 > 2.5
    assert x.selection_wins("OVER_UNDER", "OVER", 1, 1, line=2.5) is False  # 2 < 2.5
    assert x.selection_wins("OVER_UNDER", "UNDER", 1, 1, line=2.5) is True


def test_btts_resolver():
    assert x.selection_wins("BOTH_TEAMS_TO_SCORE", "YES", 1, 1) is True
    assert x.selection_wins("BOTH_TEAMS_TO_SCORE", "YES", 1, 0) is False
    assert x.selection_wins("BOTH_TEAMS_TO_SCORE", "NO", 3, 0) is True


def test_correct_score_resolver():
    assert x.selection_wins("CORRECT_SCORE", "2-1", 2, 1) is True
    assert x.selection_wins("CORRECT_SCORE", "2-1", 1, 2) is False
    assert x.selection_wins("CORRECT_SCORE", "0-0", 0, 0) is True


# ---------------------------------------------------------------------------
# P&L di una posizione
# ---------------------------------------------------------------------------
def test_position_pnl_back_and_lay():
    back = x.XPosition("MATCH_ODDS", "HOME", "back", 10.0, 2.0)
    assert x.position_pnl(back, 1, 0) == 10.0    # vince: +size*(odds-1)
    assert x.position_pnl(back, 0, 0) == -10.0   # perde: -size
    lay = x.XPosition("MATCH_ODDS", "HOME", "lay", 10.0, 2.0)
    assert x.position_pnl(lay, 1, 0) == -10.0    # vince: -size*(odds-1)
    assert x.position_pnl(lay, 0, 0) == 10.0     # perde: +size


def test_position_pnl_correct_score():
    cs = x.XPosition("CORRECT_SCORE", "2-1", "back", 10.0, 5.0)
    assert x.position_pnl(cs, 2, 1) == 40.0
    assert x.position_pnl(cs, 0, 0) == -10.0


# ---------------------------------------------------------------------------
# matrice P&L + sintesi
# ---------------------------------------------------------------------------
def test_pnl_by_scoreline_and_summary():
    # back HOME 10@2.0: +10 se casa vince, -10 altrimenti
    positions = [x.XPosition("MATCH_ODDS", "HOME", "back", 10.0, 2.0)]
    grid = x.pnl_by_scoreline(positions, max_goals=3)
    assert grid[(1, 0)] == 10.0 and grid[(0, 0)] == -10.0 and grid[(0, 1)] == -10.0
    s = x.exposure_summary(grid)
    assert s.best == 10.0 and s.worst == -10.0


def test_cross_market_nets_across_markets():
    # back HOME (MO) + lay OVER 2.5 → P&L combinato dipende da entrambi
    positions = [
        x.XPosition("MATCH_ODDS", "HOME", "back", 10.0, 2.0),
        x.XPosition("OVER_UNDER", "OVER", "lay", 10.0, 2.0, line=2.5),
    ]
    grid = x.pnl_by_scoreline(positions, max_goals=5)
    # 1-0 (casa vince, under): +10 (MO) + +10 (lay over vince perché under) = +20
    assert grid[(1, 0)] == 20.0
    # 3-1 (casa vince, over): +10 (MO) + -10 (lay over perde) = 0
    assert grid[(3, 1)] == 0.0


# ---------------------------------------------------------------------------
# suggerimento hedge sul Correct Score (alza il worst-case)
# ---------------------------------------------------------------------------
def test_suggest_hedge_flattens_single_bad_scoreline():
    # lay CS 0-0 10@8: worst = 0-0 accade (-70), tutti gli altri +10
    positions = [x.XPosition("CORRECT_SCORE", "0-0", "lay", 10.0, 8.0)]
    grid = x.pnl_by_scoreline(positions, max_goals=4)
    assert grid[(0, 0)] == -70.0
    sug = x.suggest_cs_hedge(grid, {(0, 0): 8.0})
    assert sug.actionable
    assert sug.scoreline == (0, 0) and sug.side == "back"
    assert sug.size == pytest.approx(10.0, abs=0.1)   # back 0-0 10@8 copre esattamente
    assert sug.new_worst == pytest.approx(0.0, abs=0.5)  # worst-case alzato a ~0


def test_suggest_hedge_not_actionable_when_balanced():
    # posizione a floor uniforme (back HOME): backare un CS non aiuta
    positions = [x.XPosition("MATCH_ODDS", "HOME", "back", 10.0, 2.0)]
    grid = x.pnl_by_scoreline(positions, max_goals=3)
    sug = x.suggest_cs_hedge(grid, {(0, 0): 10.0})
    assert not sug.actionable


def test_suggest_hedge_needs_cs_odds():
    positions = [x.XPosition("CORRECT_SCORE", "0-0", "lay", 10.0, 8.0)]
    grid = x.pnl_by_scoreline(positions, max_goals=3)
    sug = x.suggest_cs_hedge(grid, {})   # quota mancante
    assert not sug.actionable


# ---------------------------------------------------------------------------
# mapper catalogo Betfair → canonico
# ---------------------------------------------------------------------------
def test_canonical_market():
    assert x.canonical_market("MATCH_ODDS") == ("MATCH_ODDS", None)
    assert x.canonical_market("OVER_UNDER_25") == ("OVER_UNDER", 2.5)
    assert x.canonical_market("OVER_UNDER_35") == ("OVER_UNDER", 3.5)
    assert x.canonical_market("BOTH_TEAMS_TO_SCORE") == ("BOTH_TEAMS_TO_SCORE", None)
    assert x.canonical_market("CORRECT_SCORE") == ("CORRECT_SCORE", None)
    assert x.canonical_market("HALF_TIME") is None


def test_canonical_selection_mapping():
    assert x.canonical_selection("MATCH_ODDS", "Inter", 1) == "HOME"
    assert x.canonical_selection("MATCH_ODDS", "Milan", 2) == "AWAY"
    assert x.canonical_selection("MATCH_ODDS", "The Draw", 3) == "DRAW"
    assert x.canonical_selection("OVER_UNDER", "Over 2.5 Goals", 2) == "OVER"
    assert x.canonical_selection("OVER_UNDER", "Under 2.5 Goals", 1) == "UNDER"
    assert x.canonical_selection("BOTH_TEAMS_TO_SCORE", "Yes", 1) == "YES"
    assert x.canonical_selection("CORRECT_SCORE", "2 - 1", 5) == "2-1"
    assert x.canonical_selection("CORRECT_SCORE", "Any Other Home Win", 99) is None


def test_build_positions_skips_unmappable():
    orders = [
        {"market_id": "1.1", "selection_id": 10, "side": "back", "average_price_matched": 2.0, "size_matched": 10.0},
        {"market_id": "1.2", "selection_id": 30, "side": "lay", "average_price_matched": 8.0, "size_matched": 5.0},
        {"market_id": "1.9", "selection_id": 99, "side": "back", "average_price_matched": 2.0, "size_matched": 10.0},  # mercato non gestito
        {"market_id": "1.1", "selection_id": 10, "side": "back", "average_price_matched": 2.0, "size_matched": 0.0},   # non abbinato
    ]
    meta = {
        "1.1": {"market_type": "MATCH_ODDS", "selections": {10: {"name": "Inter", "sort_priority": 1}}},
        "1.2": {"market_type": "CORRECT_SCORE", "selections": {30: {"name": "0 - 0", "sort_priority": 1}}},
        "1.9": {"market_type": "HALF_TIME", "selections": {99: {"name": "X", "sort_priority": 1}}},
    }
    positions = x.build_positions(orders, meta)
    assert len(positions) == 2
    assert positions[0].market_type == "MATCH_ODDS" and positions[0].selection == "HOME"
    assert positions[1].market_type == "CORRECT_SCORE" and positions[1].selection == "0-0"


def test_compute_xhedge_end_to_end():
    orders = [
        {"market_id": "1.2", "selection_id": 30, "side": "lay", "average_price_matched": 8.0, "size_matched": 10.0},
    ]
    meta = {"1.2": {"market_type": "CORRECT_SCORE", "selections": {30: {"name": "0 - 0", "sort_priority": 1}}}}
    out = x.compute_xhedge(orders, meta, {(0, 0): 8.0}, max_goals=4)
    assert out["n_positions"] == 1
    assert out["summary"]["worst"] == -70.0
    assert out["suggestion"]["actionable"] is True
    assert out["suggestion"]["scoreline"] == [0, 0]
