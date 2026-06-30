"""Unit test della matematica green-up/cash-out (`Betfair/stream/trading/greenup.py`).

Logica PURA: nessun I/O, nessun mock. Verifica money-critical chiave:
  * green-up TOTALE → profit-se-vince == profit-se-perde entro 1 cent (azzeramento);
  * direzione corretta (W>L → LAY @ best lay; L>W → BACK @ best back);
  * cash-out PARZIALE (frazione) → chiude la quota richiesta dello sbilancio;
  * no-op robusti: posizione piatta, frazione 0, prezzo lato richiesto assente.
"""
from __future__ import annotations

import math

import pytest

from Betfair.stream.trading.greenup import FLAT_EPS, compute_greenup


def _residual(plan) -> float:
    """|profit-se-vince − profit-se-perde| dopo l'hedge (0 = perfettamente piatto)."""
    return abs(plan.expected_if_win - plan.expected_if_lose)


# ---------------------------------------------------------------------------
# Direzione + azzeramento (green-up totale)
# ---------------------------------------------------------------------------
def test_back_led_position_lays_to_green():
    """Posizione da BACK (vinco di più se la selezione VINCE) → si LAYa per pareggiare."""
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=3.0, best_lay_price=3.0, fraction=1.0,
    )
    assert plan.actionable
    assert plan.side == "lay"
    assert plan.price == 3.0
    # size = (W−L)/p = 15/3 = 5.00
    assert plan.size == pytest.approx(5.0, abs=1e-9)
    # profitto bloccato identico su ogni esito (entro 1 cent)
    assert _residual(plan) <= 0.01


def test_lay_led_position_backs_to_green():
    """Posizione da LAY (vinco di più se la selezione PERDE) → si BACKa per pareggiare."""
    plan = compute_greenup(
        matched_if_win=-8.0, matched_if_lose=6.0,
        best_back_price=4.0, best_lay_price=4.0, fraction=1.0,
    )
    assert plan.actionable
    assert plan.side == "back"
    assert plan.price == 4.0
    # size = (L−W)/p = 14/4 = 3.50
    assert plan.size == pytest.approx(3.5, abs=1e-9)
    assert _residual(plan) <= 0.01


def test_locked_value_matches_hedge_formula():
    """Il valore bloccato = L + (W−L)/p (stessa formula del display lockedPnlAt)."""
    w, l, p = 20.0, -4.0, 5.0
    plan = compute_greenup(
        matched_if_win=w, matched_if_lose=l,
        best_back_price=p, best_lay_price=p, fraction=1.0,
    )
    expected_locked = l + (w - l) / p  # = -4 + 24/5 = 0.8
    assert plan.expected_if_win == pytest.approx(expected_locked, abs=0.01)
    assert plan.expected_if_lose == pytest.approx(expected_locked, abs=0.01)


@pytest.mark.parametrize("p", [1.5, 2.0, 3.4, 6.2, 11.0, 26.0, 100.0, 500.0])
def test_full_green_equalises_across_price_ladder(p):
    """Su tutta la scala dei prezzi, il green-up totale azzera lo sbilancio entro il
    residuo d'arrotondamento della size (≤ mezzo tick di size * p)."""
    plan = compute_greenup(
        matched_if_win=37.5, matched_if_lose=-12.0,
        best_back_price=p, best_lay_price=p, fraction=1.0,
    )
    assert plan.actionable
    # il residuo è solo dovuto all'arrotondamento size a 2 decimali: ≤ 0.005 * p (lato vince)
    assert _residual(plan) <= 0.005 * p + 0.01


# ---------------------------------------------------------------------------
# Cash-out parziale
# ---------------------------------------------------------------------------
def test_partial_halves_the_imbalance():
    """Frazione 0.5 → size dimezzata e sbilancio residuo ~ metà dell'originale."""
    full = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=3.0, best_lay_price=3.0, fraction=1.0,
    )
    half = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=3.0, best_lay_price=3.0, fraction=0.5,
    )
    assert half.side == "lay"
    assert half.size == pytest.approx(full.size / 2.0, abs=0.01)
    # dopo mezzo green resta circa metà dello sbilancio iniziale (15 → ~7.5)
    assert _residual(half) == pytest.approx(7.5, abs=0.05)


def test_fraction_clamped_above_one():
    """Frazione > 1 è clampata a 1 (= green totale): nessun over-hedge."""
    over = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=3.0, best_lay_price=3.0, fraction=2.5,
    )
    full = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=3.0, best_lay_price=3.0, fraction=1.0,
    )
    assert over.size == full.size


# ---------------------------------------------------------------------------
# No-op robusti
# ---------------------------------------------------------------------------
def test_flat_position_is_noop():
    plan = compute_greenup(
        matched_if_win=4.0, matched_if_lose=4.0,
        best_back_price=3.0, best_lay_price=3.0, fraction=1.0,
    )
    assert not plan.actionable
    assert plan.side is None
    assert "piatta" in plan.note


def test_tiny_imbalance_below_cent_is_noop():
    plan = compute_greenup(
        matched_if_win=5.005, matched_if_lose=5.0,
        best_back_price=3.0, best_lay_price=3.0, fraction=1.0,
    )
    assert abs(5.005 - 5.0) < FLAT_EPS
    assert not plan.actionable


def test_zero_fraction_is_noop():
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=3.0, best_lay_price=3.0, fraction=0.0,
    )
    assert not plan.actionable


def test_missing_lay_price_when_lay_needed_is_noop():
    """W>L richiede un best LAY: se assente → niente ordine (mai alla cieca)."""
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=3.0, best_lay_price=None, fraction=1.0,
    )
    assert not plan.actionable
    assert "LAY" in plan.note


def test_missing_back_price_when_back_needed_is_noop():
    plan = compute_greenup(
        matched_if_win=-8.0, matched_if_lose=6.0,
        best_back_price=None, best_lay_price=4.0, fraction=1.0,
    )
    assert not plan.actionable
    assert "BACK" in plan.note


def test_invalid_price_le_one_is_noop():
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=3.0, best_lay_price=1.0, fraction=1.0,
    )
    assert not plan.actionable
