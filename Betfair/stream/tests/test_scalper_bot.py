"""Test unitari della matematica pura dello scalper (no flumine runtime)."""
from __future__ import annotations

import pytest

from Betfair.stream.scalper.scalper_bot import (
    compute_green,
    micro_price,
    ticks_between,
    wom_imbalance,
)


# --------------------------------------------------------------- micro_price
def test_micro_price_pende_verso_lato_meno_liquido():
    # piu' liquidita' lato lay -> micro vicino al best_back
    mp = micro_price(2.00, 100.0, 2.02, 900.0)
    assert 2.00 < mp < 2.02
    assert mp < 2.01  # sbilanciato verso il back (lay piu' "pesante")


def test_micro_price_bilanciato_e_mid():
    assert micro_price(2.00, 500.0, 2.02, 500.0) == pytest.approx(2.01)


def test_micro_price_none_se_manca_un_lato():
    assert micro_price(None, 100, 2.0, 100) is None
    assert micro_price(2.0, 100, None, 100) is None


def test_micro_price_size_zero_fallback_mid():
    assert micro_price(2.0, 0, 2.02, 0) == pytest.approx(2.01)


# ------------------------------------------------------------ wom_imbalance
def test_wom_imbalance_range_e_segno():
    assert wom_imbalance(100, 0) == 1.0
    assert wom_imbalance(0, 100) == -1.0
    assert wom_imbalance(50, 50) == 0.0
    assert wom_imbalance(None, None) == 0.0


# ------------------------------------------------------------- ticks_between
def test_ticks_between_un_tick_banda_2_3():
    # banda 2.00-3.00: step 0.02 -> 2.00->2.02 = 1 tick
    assert ticks_between(2.00, 2.02) == 1


def test_ticks_between_zero_se_uguali():
    assert ticks_between(2.50, 2.50) == 0


def test_ticks_between_banda_1_2():
    # banda 1.01-2.00: step 0.01 -> 1.50->1.55 = 5 tick
    assert ticks_between(1.50, 1.55) == 5


def test_ticks_between_invalido():
    assert ticks_between(2.02, 2.00) is None  # ordine invertito
    assert ticks_between(None, 2.0) is None


# -------------------------------------------------------------- compute_green
def test_green_scalp_back_blocca_profitto_positivo():
    # back 2 @ 2.02 ; chiudo a 2.00 (1 tick sotto)
    sb, ob = 2.0, 2.02
    net_win = sb * (ob - 1.0)   # = 2.04
    net_lose = -sb              # = -2.0
    res = compute_green(net_win, net_lose, 2.00)
    assert res is not None
    side, size, locked = res
    assert side == "LAY"
    # size = (net_win-net_lose)/P = (2.04+2)/2 = 2.02
    assert size == pytest.approx(2.02)
    # locked = SB*(OB-OL)/OL = 2*(2.02-2.00)/2.00 = 0.02
    assert locked == pytest.approx(0.02)
    assert locked > 0


def test_green_scalp_lay_blocca_profitto_positivo():
    # lay 2 @ 2.00 ; chiudo BACK a 2.02 (1 tick sopra)
    sl, ol = 2.0, 2.00
    net_win = -sl * (ol - 1.0)  # = -2.0
    net_lose = sl               # = 2.0
    res = compute_green(net_win, net_lose, 2.02)
    assert res is not None
    side, size, locked = res
    assert side == "BACK"
    # locked = SL*(B-OL)/B = 2*(2.02-2.00)/2.02
    assert locked == pytest.approx(2.0 * 0.02 / 2.02)
    assert locked > 0


def test_green_none_se_gia_piatto():
    assert compute_green(1.0, 1.0, 2.0) is None


def test_green_none_prezzo_invalido():
    assert compute_green(5.0, -2.0, 1.0) is None
    assert compute_green(5.0, -2.0, None) is None


def test_green_equalizza_i_due_esiti():
    # verifica che dopo il green i due esiti diano lo stesso P&L
    sb, ob = 3.0, 3.50
    net_win = sb * (ob - 1.0)   # 7.5
    net_lose = -sb              # -3.0
    P = 3.40
    side, size, locked = compute_green(net_win, net_lose, P)
    assert side == "LAY"
    win_after = net_win - size * (P - 1.0)
    lose_after = net_lose + size
    assert win_after == pytest.approx(lose_after)
    assert win_after == pytest.approx(locked)


# ----------------------------------------------------- flusso tradato (v2)
class _Ex:
    """Finto runner.ex con la ladder traded_volume cumulata."""

    def __init__(self, trd):
        self.traded_volume = [{"price": p, "size": s} for p, s in trd]


def _make_strategy(**params):
    from Betfair.stream.scalper.scalper_bot import ScalperStrategy

    return ScalperStrategy(market_filter={}, scalper_params=params)


def test_update_flow_classifica_i_lati():
    from Betfair.stream.scalper.scalper_bot import _Slot

    s = _make_strategy(flow_window_ms=60_000)
    slot = _Slot()
    # prima osservazione: solo snapshot, nessun print contato
    s._update_flow(slot, 1_000, _Ex([(2.20, 100.0)]))
    assert not slot.flow
    # best del tick precedente: bb=2.20, bl=2.24
    slot.last_bb, slot.last_bl = 2.20, 2.24
    # print a 2.20 (lato back, aggressione backer) e a 2.24 (lato lay)
    s._update_flow(slot, 2_000, _Ex([(2.20, 130.0), (2.24, 50.0)]))
    fb, fl = s._flow_sums(slot, 2_000)
    assert fb == pytest.approx(30.0)
    assert fl == pytest.approx(50.0)
    # print DENTRO lo spread (2.22): meta' e meta'
    s._update_flow(slot, 3_000, _Ex([(2.20, 130.0), (2.24, 50.0), (2.22, 10.0)]))
    fb, fl = s._flow_sums(slot, 3_000)
    assert fb == pytest.approx(35.0)
    assert fl == pytest.approx(55.0)


def test_flow_sums_rispetta_la_finestra():
    from Betfair.stream.scalper.scalper_bot import _Slot

    s = _make_strategy(flow_window_ms=10_000)
    slot = _Slot()
    slot.flow.append((0, 100.0, 100.0))       # fuori finestra
    slot.flow.append((95_000, 20.0, 10.0))    # dentro
    fb, fl = s._flow_sums(slot, 100_000)
    assert fb == pytest.approx(20.0)
    assert fl == pytest.approx(10.0)


# ------------------------------------------------------- join pricing (v2)
class _FakeMarket:
    market_id = "1.234"

    def __init__(self):
        self.orders = []

    def place_order(self, order):
        self.orders.append(order)

    def cancel_order(self, order):  # pragma: no cover - non usato qui
        pass


class _FakeRunner:
    selection_id = 42


def _join_prices(strategy, bb, bl, sz_b, sz_l, st):
    from Betfair.stream.scalper.scalper_bot import _Slot

    market = _FakeMarket()
    slot = _Slot()
    strategy._enter_join(market, _FakeRunner(), slot, 1_000, bb, bl,
                         sz_b, sz_l, (bb + bl) / 2, st)
    prices = {o.side: o.order_type.price for o in market.orders}
    return prices, slot


def test_join_spread1_si_mette_in_coda_ai_touch():
    s = _make_strategy(stake=25.0)
    prices, slot = _join_prices(s, 2.22, 2.24, 500.0, 500.0, st=1)
    assert prices["BACK"] == pytest.approx(2.24)  # back al best lay
    assert prices["LAY"] == pytest.approx(2.22)   # lay al best back
    assert slot.status == "QUOTING2"


def test_join_spread2_migliora_il_lato_con_coda_peggiore():
    s = _make_strategy(stake=25.0, improve_inside=True)
    # coda back (atb) piu' lunga -> la NOSTRA lay migliora di 1 tick dentro
    prices, _ = _join_prices(s, 2.20, 2.24, 900.0, 100.0, st=2)
    assert prices["LAY"] == pytest.approx(2.22)
    assert prices["BACK"] == pytest.approx(2.24)
    # coda lay (atl) piu' lunga -> il NOSTRO back migliora di 1 tick dentro
    prices, _ = _join_prices(s, 2.20, 2.24, 100.0, 900.0, st=2)
    assert prices["LAY"] == pytest.approx(2.20)
    assert prices["BACK"] == pytest.approx(2.22)


def test_join_spread3_migliora_entrambi_i_lati():
    s = _make_strategy(stake=25.0, improve_inside=True)
    prices, _ = _join_prices(s, 2.20, 2.26, 500.0, 500.0, st=3)
    assert prices["BACK"] == pytest.approx(2.24)  # 1 tick dentro dal lay
    assert prices["LAY"] == pytest.approx(2.22)   # 1 tick dentro dal back
