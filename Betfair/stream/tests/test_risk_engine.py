"""Test matematica risk_engine (offset / stop-loss / trailing / take-profit).

Verifiche money-critical: direzione dei tick, size di greening che PAREGGIA gli esiti,
soglie di stop nella direzione avversa corretta, cricchetto del trailing.
"""
from __future__ import annotations

import math

import pytest

from Betfair.stream.trading import risk_engine as re


# ---------------------------------------------------------------------------
# helper tick / prezzo
# ---------------------------------------------------------------------------
def test_snap_and_move_ticks_direction():
    assert re.snap(3.001) == 3.0
    # n>0 = quota più alta, n<0 = più bassa
    assert re.move_ticks(3.0, 1) == 3.05  # incremento 0.05 nella fascia 3-4
    assert re.move_ticks(3.0, -1) == 2.98  # incremento 0.02 nella fascia 2-3
    assert re.move_ticks(2.0, 10) == 2.20
    assert re.move_ticks(2.0, -10) == 1.90


def test_ticks_between_signed():
    assert re.ticks_between(2.0, 2.20) == 10
    assert re.ticks_between(2.20, 2.0) == -10
    assert re.ticks_between(3.0, 3.0) == 0


def test_move_ticks_clamps_at_ladder_bounds():
    assert re.move_ticks(1.01, -100) == re.MIN_PRICE
    assert re.move_ticks(1000, 100) == re.MAX_PRICE


# ---------------------------------------------------------------------------
# OFFSET target price
# ---------------------------------------------------------------------------
def test_offset_target_back_first_goes_lower():
    # back-first chiude LAY più in basso (profitto se quota accorcia)
    assert re.offset_target_price("back", 3.0, offset_ticks=10) == 2.80


def test_offset_target_lay_first_goes_higher():
    assert re.offset_target_price("lay", 3.0, offset_ticks=10) == 3.50  # 10 tick da 3.0 (step 0.05)


def test_offset_target_pct():
    # 2% sotto 3.0 = 2.94 → snap
    p = re.offset_target_price("back", 3.0, offset_pct=0.02)
    assert p == re.snap(3.0 * 0.98)
    p2 = re.offset_target_price("lay", 3.0, offset_pct=0.02)
    assert p2 == re.snap(3.0 * 1.02)


def test_offset_requires_exactly_one_param():
    with pytest.raises(ValueError):
        re.offset_target_price("back", 3.0)
    with pytest.raises(ValueError):
        re.offset_target_price("back", 3.0, offset_ticks=5, offset_pct=0.02)


# ---------------------------------------------------------------------------
# OFFSET order — non greening = size uguale, lato opposto
# ---------------------------------------------------------------------------
def test_offset_order_non_greening_same_size_opposite_side():
    o = re.offset_order("back", 3.0, 10.0, offset_ticks=10)
    assert o.actionable
    assert o.side == "lay"
    assert o.price == 2.80
    assert o.size == 10.0

    o2 = re.offset_order("lay", 3.0, 10.0, offset_ticks=10)
    assert o2.side == "back"
    assert o2.price == 3.50
    assert o2.size == 10.0


# ---------------------------------------------------------------------------
# OFFSET greening — la size DEVE pareggiare W' e L' entro l'arrotondamento
# ---------------------------------------------------------------------------
def _apply(side: str, price: float, size: float, w: float, l: float):
    """Applica un ordine (side@price, size) alle esposizioni (W,L) → (W',L')."""
    if side == "lay":
        return w - size * (price - 1.0), l + size
    return w + size * (price - 1.0), l - size


@pytest.mark.parametrize("entry_side,pe,se,ticks", [
    ("back", 3.0, 10.0, 10),
    ("back", 5.0, 25.0, 6),
    ("lay", 3.0, 10.0, 10),
    ("lay", 2.5, 40.0, 8),
])
def test_offset_greening_levels_win_lose(entry_side, pe, se, ticks):
    o = re.offset_order(entry_side, pe, se, offset_ticks=ticks, greening=True)
    assert o.actionable
    # esposizioni d'ingresso pieno
    if entry_side == "back":
        w, l = se * (pe - 1.0), -se
    else:
        w, l = -se * (pe - 1.0), se
    w2, l2 = _apply(o.side, o.price, o.size, w, l)
    assert abs(w2 - l2) <= 0.05, f"greening non pareggia: W'={w2} L'={l2}"


def test_offset_greening_uses_supplied_exposures():
    # con esposizioni fornite (fill parziale) usa quelle
    o = re.offset_order("back", 3.0, 10.0, offset_ticks=10, greening=True,
                        matched_if_win=12.0, matched_if_lose=-6.0)
    assert o.actionable and o.side == "lay"
    w2, l2 = _apply(o.side, o.price, o.size, 12.0, -6.0)
    assert abs(w2 - l2) <= 0.05


# ---------------------------------------------------------------------------
# STOP-LOSS trigger + should_fire
# ---------------------------------------------------------------------------
def test_stop_trigger_direction():
    # back-first: avverso è più in ALTO
    assert re.stop_trigger_price("back", 3.0, trigger_ticks=10) == 3.50
    # lay-first: avverso è più in BASSO
    assert re.stop_trigger_price("lay", 3.0, trigger_ticks=10) == 2.80


def test_stop_should_fire_back():
    trg = re.stop_trigger_price("back", 3.0, trigger_ticks=10)  # 3.50
    assert re.stop_should_fire("back", trg, 3.55) is True
    assert re.stop_should_fire("back", trg, 3.50) is True
    assert re.stop_should_fire("back", trg, 3.40) is False


def test_stop_should_fire_lay():
    trg = re.stop_trigger_price("lay", 3.0, trigger_ticks=10)  # 2.80
    assert re.stop_should_fire("lay", trg, 2.75) is True
    assert re.stop_should_fire("lay", trg, 2.80) is True
    assert re.stop_should_fire("lay", trg, 2.90) is False


def test_stop_close_order_at_best_opposite_flatten():
    # back-first stop → LAY al best_lay; flatten pareggia W/L
    o = re.stop_close_order("back", 10.0, best_back_price=3.10, best_lay_price=3.15,
                            greening=True, matched_if_win=20.0, matched_if_lose=-10.0)
    assert o.actionable and o.side == "lay" and o.price == 3.15
    w2, l2 = _apply(o.side, o.price, o.size, 20.0, -10.0)
    assert abs(w2 - l2) <= 0.05


def test_stop_close_order_non_greening_uses_entry_size():
    o = re.stop_close_order("lay", 8.0, best_back_price=3.10, best_lay_price=3.15, greening=False)
    assert o.actionable and o.side == "back" and o.price == 3.10 and o.size == 8.0


def test_stop_close_order_no_price_not_actionable():
    o = re.stop_close_order("back", 10.0, best_back_price=None, best_lay_price=None)
    assert not o.actionable


# ---------------------------------------------------------------------------
# TRAILING
# ---------------------------------------------------------------------------
def test_trailing_extreme_ratchets():
    # back-first: estremo = minimo visto
    e = re.update_trailing_extreme("back", None, 3.0)
    assert e == 3.0
    e = re.update_trailing_extreme("back", e, 2.90)
    assert e == 2.90
    e = re.update_trailing_extreme("back", e, 2.95)  # non peggiora
    assert e == 2.90
    # lay-first: estremo = massimo visto
    e2 = re.update_trailing_extreme("lay", None, 3.0)
    e2 = re.update_trailing_extreme("lay", e2, 3.10)
    assert e2 == 3.10
    e2 = re.update_trailing_extreme("lay", e2, 3.05)
    assert e2 == 3.10


def test_trailing_stop_price_and_fire_back():
    # estremo minimo 2.80, trail 5 tick → stop 5 tick sopra
    stop = re.trailing_stop_price("back", 2.80, trail_ticks=5)
    assert stop == re.move_ticks(2.80, 5)
    assert re.trailing_should_fire("back", stop, stop) is True
    assert re.trailing_should_fire("back", stop, re.move_ticks(stop, -1)) is False


def test_trailing_stop_price_lay():
    stop = re.trailing_stop_price("lay", 3.20, trail_ticks=5)
    assert stop == re.move_ticks(3.20, -5)


# ---------------------------------------------------------------------------
# mark-to-market + soglie P&L
# ---------------------------------------------------------------------------
def test_mark_to_market_matches_greenup_locked():
    # diff>0 → lay al best_lay: locked = L + diff/best_lay
    mtm = re.mark_to_market(20.0, -10.0, best_back_price=2.9, best_lay_price=3.0)
    assert mtm == round(-10.0 + 30.0 / 3.0, 2)  # 0.0
    # diff<0 → back al best_back
    mtm2 = re.mark_to_market(-10.0, 20.0, best_back_price=3.0, best_lay_price=2.9)
    assert mtm2 == round(20.0 + (-10.0 - 20.0) / 3.0, 2)


def test_mark_to_market_flat_position():
    assert re.mark_to_market(5.0, 5.0, 3.0, 3.0) == 5.0


def test_pnl_threshold_stop_wins_over_target():
    assert re.pnl_threshold_fires(-6.0, stop_amount=5.0, target_amount=10.0) == "stop"
    assert re.pnl_threshold_fires(12.0, stop_amount=5.0, target_amount=10.0) == "target"
    assert re.pnl_threshold_fires(0.0, stop_amount=5.0, target_amount=10.0) is None
    assert re.pnl_threshold_fires(None, stop_amount=5.0) is None


def test_hedge_size_at_flat_returns_none():
    side, size = re.hedge_size_at(5.0, 5.0, 3.0)
    assert side is None and size == 0.0


def test_favorable_reached():
    # back-first: favorevole = quota più bassa
    assert re.favorable_reached("back", 2.80, 2.75) is True
    assert re.favorable_reached("back", 2.80, 2.85) is False
    # lay-first: favorevole = quota più alta
    assert re.favorable_reached("lay", 3.20, 3.25) is True
    assert re.favorable_reached("lay", 3.20, 3.15) is False


# ---------------------------------------------------------------------------
# evaluate_rule (decisione della regola armata)
# ---------------------------------------------------------------------------
def test_evaluate_stop_loss_price_fires():
    dec = re.evaluate_rule(
        rule_type="stop_loss", entry_side="back", entry_price=3.0,
        params={"trigger_ticks": 10}, current_price=3.55,
        matched_if_win=20.0, matched_if_lose=-10.0,
        best_back_price=3.5, best_lay_price=3.55, trail_extreme=None,
    )
    assert dec.fire is True


def test_evaluate_stop_loss_price_no_fire():
    dec = re.evaluate_rule(
        rule_type="stop_loss", entry_side="back", entry_price=3.0,
        params={"trigger_ticks": 10}, current_price=3.40,
        matched_if_win=20.0, matched_if_lose=-10.0,
        best_back_price=3.35, best_lay_price=3.4, trail_extreme=None,
    )
    assert dec.fire is False


def test_evaluate_stop_loss_pnl_fires():
    # mtm negativo oltre lo stop_amount
    dec = re.evaluate_rule(
        rule_type="stop_loss", entry_side="back", entry_price=3.0,
        params={"stop_amount": 5.0}, current_price=3.0,
        matched_if_win=-6.0, matched_if_lose=-6.0,  # posizione uniformemente -6
        best_back_price=3.0, best_lay_price=3.0, trail_extreme=None,
    )
    assert dec.fire is True


def test_evaluate_take_profit_price_fires():
    dec = re.evaluate_rule(
        rule_type="take_profit", entry_side="back", entry_price=3.0,
        params={"offset_ticks": 10}, current_price=2.75,
        matched_if_win=20.0, matched_if_lose=-10.0,
        best_back_price=2.75, best_lay_price=2.8, trail_extreme=None,
    )
    assert dec.fire is True


def test_evaluate_trailing_updates_extreme_and_fires():
    # back-first, trail 5 tick. estremo minimo scende, poi il prezzo rimbalza oltre lo stop.
    dec1 = re.evaluate_rule(
        rule_type="trailing_stop", entry_side="back", entry_price=3.0,
        params={"trail_ticks": 5}, current_price=2.80,
        matched_if_win=20.0, matched_if_lose=-10.0,
        best_back_price=2.78, best_lay_price=2.8, trail_extreme=None,
    )
    assert dec1.fire is False and dec1.trail_extreme == 2.80
    stop = re.trailing_stop_price("back", 2.80, trail_ticks=5)  # 5 tick sopra 2.80
    dec2 = re.evaluate_rule(
        rule_type="trailing_stop", entry_side="back", entry_price=3.0,
        params={"trail_ticks": 5}, current_price=stop,
        matched_if_win=20.0, matched_if_lose=-10.0,
        best_back_price=stop, best_lay_price=stop, trail_extreme=2.80,
    )
    assert dec2.fire is True


# ---------------------------------------------------------------------------
# STOP-ENTRY (C23) — matematica pura
# ---------------------------------------------------------------------------
def test_stop_entry_fires_directions():
    from Betfair.stream.trading.risk_engine import stop_entry_fires
    assert stop_entry_fires("at_or_above", 3.0, 3.0)
    assert stop_entry_fires("at_or_above", 3.0, 3.05)
    assert not stop_entry_fires("at_or_above", 3.0, 2.98)
    assert stop_entry_fires("at_or_below", 3.0, 3.0)
    assert stop_entry_fires("at_or_below", 3.0, 2.9)
    assert not stop_entry_fires("at_or_below", 3.0, 3.05)


def test_stop_entry_no_ltp_never_fires():
    from Betfair.stream.trading.risk_engine import stop_entry_fires
    assert not stop_entry_fires("at_or_above", 3.0, None)
    assert not stop_entry_fires("at_or_above", 3.0, float("nan"))


def test_stop_entry_invalid_params_raise():
    import pytest as _pt
    from Betfair.stream.trading.risk_engine import stop_entry_fires
    with _pt.raises(ValueError):
        stop_entry_fires("sopra", 3.0, 3.0)          # direzione sconosciuta
    with _pt.raises(ValueError):
        stop_entry_fires("at_or_above", 0.5, 3.0)    # soglia fuori scala
    with _pt.raises(ValueError):
        stop_entry_fires("at_or_above", float("nan"), 3.0)


# ---------------------------------------------------------------------------
# CHASE (C25) — matematica pura
# ---------------------------------------------------------------------------
def test_chase_target_price_back_and_lay():
    from Betfair.stream.trading.risk_engine import chase_target_price
    # offset 0 = join del best
    assert chase_target_price("back", 3.0, 3.05, 0) == 3.0
    assert chase_target_price("lay", 3.0, 3.05, 0) == 3.05
    # offset 2: back 2 tick PIU' IN ALTO, lay 2 tick PIU' IN BASSO (meno aggressivi)
    assert chase_target_price("back", 3.0, 3.05, 2) == 3.1
    assert chase_target_price("lay", 3.0, 3.05, 2) == 2.98


def test_chase_target_price_missing_best_is_none():
    from Betfair.stream.trading.risk_engine import chase_target_price
    assert chase_target_price("back", None, 3.05, 0) is None
    assert chase_target_price("lay", 3.0, None, 0) is None


def test_chase_invalid_params_raise():
    import pytest as _pt
    from Betfair.stream.trading.risk_engine import chase_target_price
    with _pt.raises(ValueError):
        chase_target_price("back", 3.0, 3.05, -1)
    with _pt.raises(ValueError):
        chase_target_price("banana", 3.0, 3.05, 0)


def test_chase_should_requote():
    from Betfair.stream.trading.risk_engine import chase_should_requote
    assert chase_should_requote(3.0, 3.05)
    assert not chase_should_requote(3.0, 3.0)
    assert not chase_should_requote(None, 3.0)
    assert not chase_should_requote(3.0, None)


# ---------------------------------------------------------------------------
# FIX audit #2 — take_profit tick/%: trigger_* accettati come ALIAS di offset_*
# ---------------------------------------------------------------------------
def test_take_profit_trigger_ticks_alias_fires():
    """La UI storica armava il take-profit con trigger_ticks: prima veniva IGNORATO
    (si leggeva solo offset_ticks) e la regola non scattava MAI. Ora è un alias."""
    from Betfair.stream.trading.risk_engine import evaluate_rule
    # back a 3.0, take-profit 10 tick → target 2.80; LTP 2.80 = raggiunto.
    d = evaluate_rule(
        rule_type="take_profit", entry_side="back", entry_price=3.0,
        params={"trigger_ticks": 10}, current_price=2.80,
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.78, best_lay_price=2.80, trail_extreme=None,
    )
    assert d.fire and d.error is None


def test_take_profit_trigger_pct_alias_fires():
    from Betfair.stream.trading.risk_engine import evaluate_rule
    # back a 3.0, −10% → target snap(2.7); LTP 2.7 = raggiunto.
    d = evaluate_rule(
        rule_type="take_profit", entry_side="back", entry_price=3.0,
        params={"trigger_pct": 0.10}, current_price=2.7,
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.68, best_lay_price=2.70, trail_extreme=None,
    )
    assert d.fire and d.error is None


def test_take_profit_offset_ticks_canonico_vince_sull_alias():
    """offset_* resta il nome canonico: se presente, l'alias non interferisce."""
    from Betfair.stream.trading.risk_engine import evaluate_rule
    d = evaluate_rule(
        rule_type="take_profit", entry_side="back", entry_price=3.0,
        params={"offset_ticks": 10, "trigger_ticks": 40}, current_price=2.80,
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.78, best_lay_price=2.80, trail_extreme=None,
    )
    assert d.fire  # target dal canonico (2.80), non dall'alias (2.20)


# ---------------------------------------------------------------------------
# FIX audit #1 — bracket senza gamba STOP = errore PERMANENTE dichiarato
# ---------------------------------------------------------------------------
def test_bracket_missing_stop_flags_error():
    from Betfair.stream.trading.risk_engine import bracket_missing_stop
    msg = bracket_missing_stop({"offset_ticks": 3, "greening": True})
    assert msg is not None and "gamba STOP" in msg
    assert bracket_missing_stop({}) is not None
    assert bracket_missing_stop(None) is not None


def test_bracket_missing_stop_ok_with_any_stop_param():
    from Betfair.stream.trading.risk_engine import bracket_missing_stop
    assert bracket_missing_stop({"offset_ticks": 3, "trigger_ticks": 5}) is None
    assert bracket_missing_stop({"offset_pct": 2, "trigger_pct": 1.5}) is None
    assert bracket_missing_stop({"offset_ticks": 3, "stop_amount": 5.0}) is None
    assert bracket_missing_stop({"offset_ticks": 3, "trail_ticks": 4}) is None
