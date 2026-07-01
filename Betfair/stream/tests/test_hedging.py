"""Test planner hedging / global cash-out (flatten multi-posizione)."""
from __future__ import annotations

from Betfair.stream.trading import hedging as h


def _pos(mkt, sel, w, l, bb=3.0, bl=3.05):
    return h.PositionInput(
        market_id=mkt, selection_id=sel, handicap=0.0,
        matched_if_win=w, matched_if_lose=l, best_back_price=bb, best_lay_price=bl,
    )


def test_plan_flatten_one_leg_per_position():
    positions = [_pos("1.1", 10, 20.0, -10.0), _pos("1.2", 20, -5.0, 8.0)]
    plan = h.plan_flatten(positions)
    assert len(plan.legs) == 2
    assert plan.actionable
    # ogni gamba actionable pareggia W/L (via greenup)
    for leg in plan.actionable_legs:
        p = leg.plan
        assert abs(p.expected_if_win - p.expected_if_lose) <= 0.05


def test_plan_flatten_skips_flat_positions():
    positions = [_pos("1.1", 10, 5.0, 5.0), _pos("1.2", 20, 20.0, -10.0)]
    plan = h.plan_flatten(positions)
    assert len(plan.legs) == 2
    assert len(plan.actionable_legs) == 1  # la prima è piatta


def test_plan_flatten_partial_fraction():
    positions = [_pos("1.1", 10, 20.0, -10.0)]
    full = h.plan_flatten(positions, fraction=1.0).actionable_legs[0].plan
    half = h.plan_flatten(positions, fraction=0.5).actionable_legs[0].plan
    assert half.size is not None and full.size is not None
    assert half.size < full.size


def test_net_open_pnl_locked_after_flatten():
    # posizione chiudibile → worst≈best (bloccato)
    positions = [_pos("1.1", 10, 20.0, -10.0, bb=3.0, bl=3.0)]
    worst, best = h.net_open_pnl(positions)
    assert abs(best - worst) <= 0.05


def test_net_open_pnl_uncloseable_stays_exposed():
    positions = [_pos("1.1", 10, 20.0, -10.0, bb=None, bl=None)]
    worst, best = h.net_open_pnl(positions)
    assert worst == -10.0 and best == 20.0
