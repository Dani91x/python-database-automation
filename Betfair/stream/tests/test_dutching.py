"""Test matematica dutching / bookmaking. Verifica il PROFITTO UGUALE su ogni esito."""
from __future__ import annotations

import pytest

from Betfair.stream.trading import dutching as d


def test_book_percentage():
    # 1/2 + 1/4 + 1/4 = 1.0 → 100%
    assert d.book_percentage([(1, 2.0), (2, 4.0), (3, 4.0)]) == 100.0
    # book < 100 → margine
    assert d.book_percentage([(1, 3.0), (2, 3.0), (3, 3.0)]) == pytest.approx(100.0, abs=0.01)


def test_dutch_back_equal_profit():
    plan = d.dutch_back([(1, 4.0), (2, 4.0), (3, 4.0)], total_stake=30.0)
    assert plan.actionable and plan.side == "back"
    # book = 3*(1/4)=0.75 → 75% → profitto = 30*(1-0.75)/0.75 = 10
    profits = [leg.profit_if_wins for leg in plan.legs]
    for p in profits:
        assert p == pytest.approx(10.0, abs=0.05)
    assert plan.total_stake == pytest.approx(30.0, abs=0.05)


def test_dutch_back_unequal_prices_still_equal_profit():
    plan = d.dutch_back([(1, 2.0), (2, 5.0), (3, 8.0)], total_stake=100.0)
    profits = [leg.profit_if_wins for leg in plan.legs]
    # tutti i profitti uguali entro arrotondamento
    assert max(profits) - min(profits) <= 0.10
    # stake proporzionale a 1/p: il favorito (2.0) ha lo stake maggiore
    sizes = {leg.selection_id: leg.size for leg in plan.legs}
    assert sizes[1] > sizes[2] > sizes[3]


def test_dutch_back_for_target():
    plan = d.dutch_back_for_target([(1, 4.0), (2, 4.0), (3, 4.0)], target_profit=10.0)
    assert plan.actionable
    for leg in plan.legs:
        assert leg.profit_if_wins == pytest.approx(10.0, abs=0.10)


def test_dutch_back_for_target_impossible_when_book_over_100():
    plan = d.dutch_back_for_target([(1, 2.0), (2, 2.0)], target_profit=10.0)  # book 100%
    assert not plan.actionable
    assert "100" in plan.note


def test_dutch_lay_equal_profit():
    plan = d.dutch_lay([(1, 4.0), (2, 4.0), (3, 4.0)], total_lay_stake=30.0)
    assert plan.actionable and plan.side == "lay"
    profits = [leg.profit_if_wins for leg in plan.legs]
    # book 75% < 100 → bookmaking in perdita garantita (worst<0); profitti uguali comunque
    assert max(profits) - min(profits) <= 0.10


def test_dutch_lay_profitable_when_book_over_100():
    # prezzi bassi → book > 100% → bookmaker in profitto
    plan = d.dutch_lay([(1, 1.5), (2, 3.0), (3, 3.0)], total_lay_stake=100.0)
    profits = [leg.profit_if_wins for leg in plan.legs]
    assert min(profits) > 0
    assert max(profits) - min(profits) <= 0.20


def test_dutch_variable_weights_profit_ratio():
    # peso doppio sulla selezione 1 → profitto ~doppio
    plan = d.dutch_variable([(1, 4.0, 2.0), (2, 4.0, 1.0), (3, 4.0, 1.0)], total_stake=30.0)
    by_id = {leg.selection_id: leg.profit_if_wins for leg in plan.legs}
    assert by_id[1] == pytest.approx(2.0 * by_id[2], abs=0.20)
    assert by_id[2] == pytest.approx(by_id[3], abs=0.10)


def test_dutch_back_invalid_inputs():
    assert not d.dutch_back([], 30.0).actionable
    assert not d.dutch_back([(1, 4.0)], 0.0).actionable
    # prezzo non valido scartato
    plan = d.dutch_back([(1, 4.0), (2, 1.0)], 30.0)  # 1.0 non valido
    assert len(plan.legs) == 1
