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


# ---------------------------------------------------------------------------
# place_at_ticks — stop a 2 parametri: chiude N tick più a fondo nel book (fill sicuro)
# ---------------------------------------------------------------------------
def test_place_at_lay_moves_price_up_into_book():
    base = compute_greenup(matched_if_win=20.0, matched_if_lose=-10.0,
                           best_back_price=2.9, best_lay_price=3.0, fraction=1.0)
    pat = compute_greenup(matched_if_win=20.0, matched_if_lose=-10.0,
                          best_back_price=2.9, best_lay_price=3.0, fraction=1.0, place_at_ticks=2)
    assert base.side == "lay" and pat.side == "lay"
    assert pat.price > base.price  # LAY più in alto = offre odds migliori ai backer = match sicuro


def test_place_at_back_moves_price_down_into_book():
    pat = compute_greenup(matched_if_win=-10.0, matched_if_lose=20.0,
                          best_back_price=3.0, best_lay_price=2.9, fraction=1.0, place_at_ticks=2)
    assert pat.side == "back"
    assert pat.price < 3.0  # BACK più in basso = offre odds migliori ai layer = match sicuro


def test_place_at_zero_is_noop():
    a = compute_greenup(matched_if_win=20.0, matched_if_lose=-10.0,
                        best_back_price=2.9, best_lay_price=3.0, place_at_ticks=0)
    b = compute_greenup(matched_if_win=20.0, matched_if_lose=-10.0,
                        best_back_price=2.9, best_lay_price=3.0)
    assert a.price == b.price


# ---------------------------------------------------------------------------
# target_price ("greening column": chiudi A QUEL prezzo, non al best opposto)
# ---------------------------------------------------------------------------
def test_target_price_lay_closes_at_that_level():
    """W>L: LAY al TARGET (non al best): l'ordine puo' restare sul book (take-profit)."""
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.9, best_lay_price=3.0,
        fraction=1.0, target_price=2.5,
    )
    assert plan.actionable
    assert plan.side == "lay"
    assert plan.price == 2.5              # il livello cliccato, non il best (3.0)
    assert plan.size == pytest.approx(15.0 / 2.5, abs=1e-9)
    assert _residual(plan) <= 0.01        # pareggio valido a QUALUNQUE prezzo


def test_target_price_back_closes_at_that_level():
    """L>W: BACK al TARGET (non al best)."""
    plan = compute_greenup(
        matched_if_win=-8.0, matched_if_lose=6.0,
        best_back_price=4.0, best_lay_price=4.1,
        fraction=1.0, target_price=5.0,
    )
    assert plan.actionable
    assert plan.side == "back"
    assert plan.price == 5.0
    assert plan.size == pytest.approx(14.0 / 5.0, abs=1e-9)
    assert _residual(plan) <= 0.01


def test_target_price_snaps_to_nearest_tick():
    """Un target off-tick viene agganciato al tick Betfair piu' vicino."""
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.9, best_lay_price=3.0,
        fraction=1.0, target_price=2.513,   # banda 0.02 -> 2.52
    )
    assert plan.actionable
    assert plan.price == pytest.approx(2.52, abs=1e-9)


def test_target_price_works_without_best_prices():
    """Col target il best opposto non serve (book vuoto/sospeso): si piazza comunque."""
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=None, best_lay_price=None,
        fraction=1.0, target_price=2.0,
    )
    assert plan.actionable
    assert plan.side == "lay"
    assert plan.price == 2.0


def test_target_price_partial_fraction():
    """fraction + target: chiude la sola quota richiesta dello sbilancio al livello dato."""
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.9, best_lay_price=3.0,
        fraction=0.5, target_price=2.5,
    )
    assert plan.actionable
    assert plan.size == pytest.approx(0.5 * 15.0 / 2.5, abs=1e-9)


@pytest.mark.parametrize("bad", [0.0, 1.0, -3.0, 1001.0, float("nan"), float("inf")])
def test_target_price_invalid_is_noop(bad):
    """Target non valido -> NESSUN ordine (mai ripiegare in silenzio sul best)."""
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.9, best_lay_price=3.0,
        fraction=1.0, target_price=bad,
    )
    assert not plan.actionable
    assert "target_price non valido" in plan.note


def test_target_price_flat_position_still_noop():
    """Posizione piatta + target -> nessun ordine (il target non forza un place)."""
    plan = compute_greenup(
        matched_if_win=3.0, matched_if_lose=3.0,
        best_back_price=2.9, best_lay_price=3.0,
        fraction=1.0, target_price=2.5,
    )
    assert not plan.actionable


@pytest.mark.parametrize("edge", [1.01, 1000.0])
def test_target_price_valid_at_domain_edges(edge):
    """I bordi VALIDI della scala Betfair (1.01 e 1000) sono accettati e usati com'e'.

    NB sul residuo: la size e' arrotondata al CENTESIMO (unita' minima Betfair), quindi il
    pareggio ha un errore massimo di 0.005*(p-1) sull'esito vince — trascurabile a quote
    normali, fino a ~5 EUR a quota 1000 su questo sbilancio. E' il vincolo dei centesimi
    (identico nei tool pro), non un difetto della matematica: il bound va rispettato.
    """
    plan = compute_greenup(
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.9, best_lay_price=3.0,
        fraction=1.0, target_price=edge,
    )
    assert plan.actionable
    assert plan.price == pytest.approx(edge, abs=1e-9)
    assert _residual(plan) <= 0.005 * (edge - 1.0) + 0.01
