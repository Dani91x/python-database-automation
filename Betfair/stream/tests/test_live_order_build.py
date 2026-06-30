"""Unit test di live_order_build (build + validazione ordine flumine).

Money-critical: nessuna rete, nessun login. Il Market è un mock leggero (solo
`market_id`); le classi ordine usate sono quelle NATIVE di flumine. I vettori numerici
(tick, lay size<->liability, regole .it) sono verificati a mano contro flumine.utils.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
from flumine import BaseStrategy

from Betfair.stream.live_order_build import (
    INVALID_PROFIT_RATIO_MAX,
    INVALID_PROFIT_RATIO_MIN,
    BuiltOrder,
    MinStakeVerdict,
    build_order,
    lay_size_from_liability,
    liability_from_lay_size,
    min_stake_rules,
    round_to_tick,
    ticks_away,
)


def _market(market_id: str = "1.234567890"):
    """Mock minimale di flumine Market: solo l'attributo usato (market_id)."""
    return SimpleNamespace(market_id=market_id)


# Strategy registrata "tipo": un'istanza reale di BaseStrategy (come la
# LiveTradingStrategy del runner) sotto cui i Trade vengono creati.
_STRATEGY = BaseStrategy(market_filter={}, name="live_trading")


def _base_kwargs(**over):
    kw = dict(
        strategy=_STRATEGY,
        selection_id=47999,
        handicap=0.0,
        side="back",
        order_type="LIMIT",
        price=3.0,
        size=5.0,
        liability=None,
        persistence="LAPSE",
        time_in_force=None,
        min_fill_size=None,
        jurisdiction="it",
        max_stake=10.0,
        customer_order_ref="awlq123",
    )
    kw.update(over)
    return kw


# ===========================================================================
# round_to_tick — vettori verificati contro flumine.utils.get_nearest_price
# ===========================================================================
@pytest.mark.parametrize(
    "raw, expected",
    [
        (3.03, 3.05),
        (1.185, 1.19),
        (2.07, 2.08),
        (4.04, 4.0),
        (11.3, 11.5),
        (5.3, 5.3),
        (23.0, 23.0),
        (1.005, 1.01),   # clamp <= MIN_PRICE
        (999.5, 1000.0),
        (1500, 1000.0),  # clamp > MAX_PRICE
    ],
)
def test_round_to_tick_vectors(raw, expected):
    assert round_to_tick(raw) == expected


def test_round_to_tick_none_raises():
    with pytest.raises(ValueError):
        round_to_tick(None)


# ===========================================================================
# ticks_away — passa per round_to_tick (evita ValueError su non-ladder)
# ===========================================================================
@pytest.mark.parametrize(
    "price, n, expected",
    [
        (2.0, 1, 2.02),
        (2.0, -1, 1.99),
        (3.0, 2, 3.1),
        (10.0, 1, 10.5),
        (1.98, 2, 2.0),
        (1.01, -5, 1.01),   # floor (new_index<0)
        (1000.0, 5, 1000),  # IndexError -> 1000
    ],
)
def test_ticks_away_vectors(price, n, expected):
    assert ticks_away(price, n) == expected


def test_ticks_away_non_ladder_input_does_not_crash():
    # 3.03 NON è un tick valido: round_to_tick lo porta a 3.05, poi +1 -> 3.1
    assert ticks_away(3.03, 1) == 3.1


# ===========================================================================
# lay size <-> liability
# ===========================================================================
@pytest.mark.parametrize(
    "liab, price, size",
    [
        (10.0, 3.0, 5.0),
        (20.0, 5.0, 5.0),
        (7.5, 2.5, 5.0),
    ],
)
def test_lay_size_from_liability(liab, price, size):
    assert lay_size_from_liability(liab, price) == size


@pytest.mark.parametrize(
    "size, price, liab",
    [
        (5.0, 3.0, 10.0),
        (4.0, 6.0, 20.0),
        (5.0, 2.5, 7.5),
    ],
)
def test_liability_from_lay_size(size, price, liab):
    assert liability_from_lay_size(size, price) == liab


def test_lay_conversion_roundtrip():
    size = lay_size_from_liability(10.0, 3.0)
    assert liability_from_lay_size(size, 3.0) == 10.0


def test_lay_conversion_bad_price_raises():
    with pytest.raises(ValueError):
        lay_size_from_liability(10.0, 1.0)
    with pytest.raises(ValueError):
        liability_from_lay_size(5.0, 1.0)


# ===========================================================================
# min_stake_rules — .it BACK (min 2.00, floor 0.50)
# ===========================================================================
@pytest.mark.parametrize(
    "size, ok, legal",
    [
        (1.5, False, None),
        (2.0, True, 2.0),
        (2.3, True, 2.0),
        (2.5, True, 2.5),
        (2.7, True, 2.5),
        (3.0, True, 3.0),
        (4.99, True, 4.5),
    ],
)
def test_min_stake_it_back(size, ok, legal):
    v = min_stake_rules("it", "back", 3.0, size)
    assert v.valid is ok
    assert v.legalized_size == legal
    if not ok:
        assert v.reason is not None


# ===========================================================================
# min_stake_rules — .it LAY (min size 0.50, no floor a 0.50)
# ===========================================================================
@pytest.mark.parametrize(
    "size, ok, legal",
    [
        (0.3, False, None),
        (0.5, True, 0.5),
        (0.75, True, 0.75),
        (2.0, True, 2.0),
    ],
)
def test_min_stake_it_lay(size, ok, legal):
    v = min_stake_rules("it", "lay", 3.0, size)
    assert v.valid is ok
    assert v.legalized_size == legal


def test_min_stake_reduces_liability_allows_submin():
    # green-up/hedge: sotto-minimo consentito (size accettata, round 2dp)
    v = min_stake_rules("it", "back", 3.0, 0.37, reduces_liability=True)
    assert v.valid is True
    assert v.legalized_size == 0.37
    v2 = min_stake_rules("it", "lay", 5.0, 0.12, reduces_liability=True)
    assert v2.valid is True
    assert v2.legalized_size == 0.12


def test_min_stake_invalid_inputs():
    assert min_stake_rules("it", "back", 3.0, 0).valid is False
    assert min_stake_rules("it", "back", 3.0, -1).valid is False
    assert min_stake_rules("it", "back", 3.0, math.nan).valid is False
    assert min_stake_rules("it", "spam", 3.0, 5.0).valid is False
    assert min_stake_rules("xx", "back", 3.0, 5.0).valid is False


def test_min_stake_com_min_bet_payout():
    # .com: size sotto €2 ammessa solo se Min Bet Payout (size*price >= 20)
    assert min_stake_rules("com", "back", 11.0, 2.0).valid is True   # size>=2
    assert min_stake_rules("com", "back", 11.0, 1.9).valid is True   # 1.9*11=20.9 >= 20
    assert min_stake_rules("com", "back", 11.0, 1.5).valid is False  # 1.5<2 e 16.5<20
    assert min_stake_rules("com", "back", 3.0, 3.0).valid is True    # size>=2


def test_invalid_profit_ratio_band_constants():
    assert INVALID_PROFIT_RATIO_MIN == -0.20
    assert INVALID_PROFIT_RATIO_MAX == 0.25


# ===========================================================================
# build_order — BACK LIMIT happy path
# ===========================================================================
def test_build_back_limit_basic():
    b = build_order(_market(), **_base_kwargs(price=3.0, size=5.0))
    assert isinstance(b, BuiltOrder)
    assert b.side == "BACK"
    assert b.price == 3.0
    assert b.size == 5.0
    assert b.liability is None
    # ordine flumine nativo
    assert b.order.side == "BACK"
    assert b.order.order_type.price == 3.0
    assert b.order.order_type.size == 5.0
    assert b.order.order_type.persistence_type == "LAPSE"
    assert b.order.selection_id == 47999
    assert b.order.notes["customer_order_ref"] == "awlq123"


# ===========================================================================
# build_order — legame Trade↔strategia REGISTRATA (FIX specchio process_orders)
# ===========================================================================
def test_build_order_created_under_registered_strategy():
    """Il Trade dell'ordine è legato ESATTAMENTE alla strategy passata (l'istanza
    registrata nel framework): è questo legame che fa instradare process_orders."""
    b = build_order(_market(), **_base_kwargs(price=3.0, size=5.0))
    assert b.order.trade.strategy is _STRATEGY


def test_build_order_requires_strategy():
    with pytest.raises(ValueError, match="strategy"):
        build_order(_market(), **_base_kwargs(strategy=None))


def test_build_order_ref_in_context_and_notes():
    """Il NOSTRO ref awlq<id> è salvato sia in notes sia in context (lo specchio lo
    rilegge da lì, non dall'attributo flumine customer_order_ref)."""
    b = build_order(_market(), **_base_kwargs(customer_order_ref="awlq777"))
    assert b.order.notes["customer_order_ref"] == "awlq777"
    assert b.order.context["customer_order_ref"] == "awlq777"


def test_build_back_rounds_price_to_tick():
    b = build_order(_market(), **_base_kwargs(price=3.03, size=5.0))
    assert b.price == 3.05
    assert b.order.order_type.price == 3.05


def test_build_back_floors_size_to_step():
    b = build_order(_market(), **_base_kwargs(price=3.0, size=4.99))
    assert b.size == 4.5
    assert "legalize" in b.note


def test_build_back_below_min_raises():
    with pytest.raises(ValueError, match="minimo"):
        build_order(_market(), **_base_kwargs(price=3.0, size=1.5))


def test_build_back_requires_size():
    with pytest.raises(ValueError, match="BACK richiede size"):
        build_order(_market(), **_base_kwargs(size=None))


# ===========================================================================
# build_order — LAY LIMIT (size e liability)
# ===========================================================================
def test_build_lay_from_size():
    b = build_order(_market(), **_base_kwargs(side="lay", price=3.0, size=5.0))
    assert b.side == "LAY"
    assert b.order.side == "LAY"
    assert b.size == 5.0
    assert b.liability == 10.0  # 5*(3-1)


def test_build_lay_from_liability():
    b = build_order(
        _market(),
        **_base_kwargs(side="lay", price=3.0, size=None, liability=10.0, max_stake=20.0),
    )
    assert b.size == 5.0
    assert b.liability == 10.0
    assert "lay size da liability" in b.note


def test_build_lay_submin_size_raises():
    with pytest.raises(ValueError, match="minimo"):
        build_order(_market(), **_base_kwargs(side="lay", price=3.0, size=0.3))


def test_build_lay_requires_size_or_liability():
    with pytest.raises(ValueError, match="size oppure liability"):
        build_order(_market(), **_base_kwargs(side="lay", size=None, liability=None))


# ===========================================================================
# build_order — cap max_stake / payout / range prezzo
# ===========================================================================
def test_build_back_cap_max_stake():
    with pytest.raises(ValueError, match="cap max_stake"):
        build_order(_market(), **_base_kwargs(price=3.0, size=20.0, max_stake=10.0))


def test_build_lay_cap_uses_liability():
    # size 3 @ 5.0 -> liability 12 > cap 10 -> rifiuto
    with pytest.raises(ValueError, match="cap max_stake"):
        build_order(_market(), **_base_kwargs(side="lay", price=5.0, size=3.0, max_stake=10.0))


def test_build_back_payout_cap():
    # size 5000 @ 3.0 -> profit 10000 ok; spingiamo oltre con price 4.0 -> 15000
    with pytest.raises(ValueError, match="vincita potenziale"):
        build_order(
            _market(),
            **_base_kwargs(price=4.0, size=5000.0, max_stake=None),
        )


def test_build_price_out_of_range():
    with pytest.raises(ValueError, match="fuori range"):
        build_order(_market(), **_base_kwargs(price=1000.5, size=5.0))


def test_build_limit_requires_price():
    with pytest.raises(ValueError, match="LIMIT richiede price"):
        build_order(_market(), **_base_kwargs(price=None, size=5.0))


# ===========================================================================
# build_order — FILL_OR_KILL / min_fill_size / persistence / side / type
# ===========================================================================
def test_build_fok_ok():
    b = build_order(
        _market(),
        **_base_kwargs(time_in_force="FILL_OR_KILL", min_fill_size=2.0, size=5.0),
    )
    assert b.time_in_force == "FILL_OR_KILL"
    assert b.order.order_type.time_in_force == "FILL_OR_KILL"
    assert b.order.order_type.min_fill_size == 2.0


def test_build_min_fill_requires_fok():
    with pytest.raises(ValueError, match="min_fill_size richiede"):
        build_order(_market(), **_base_kwargs(time_in_force=None, min_fill_size=2.0))


def test_build_min_fill_gt_size_raises():
    with pytest.raises(ValueError, match="min_fill_size"):
        build_order(
            _market(),
            **_base_kwargs(time_in_force="FILL_OR_KILL", min_fill_size=9.0, size=5.0),
        )


def test_build_fok_only_limit():
    with pytest.raises(ValueError, match="FILL_OR_KILL ammesso solo"):
        build_order(
            _market(),
            **_base_kwargs(order_type="LIMIT_ON_CLOSE", time_in_force="FILL_OR_KILL",
                           price=3.0, liability=5.0),
        )


def test_build_bad_side():
    with pytest.raises(ValueError, match="side non valido"):
        build_order(_market(), **_base_kwargs(side="buy"))


def test_build_bad_order_type():
    with pytest.raises(ValueError, match="order_type non valido"):
        build_order(_market(), **_base_kwargs(order_type="STOP"))


def test_build_bad_persistence():
    with pytest.raises(ValueError, match="persistence non valida"):
        build_order(_market(), **_base_kwargs(persistence="GTC"))


def test_build_bad_time_in_force():
    with pytest.raises(ValueError, match="time_in_force non valido"):
        build_order(_market(), **_base_kwargs(time_in_force="GOOD_TILL_CANCEL"))


def test_build_persist_passes_through():
    b = build_order(_market(), **_base_kwargs(persistence="PERSIST"))
    assert b.persistence == "PERSIST"
    assert b.order.order_type.persistence_type == "PERSIST"


def test_build_missing_market_id():
    with pytest.raises(ValueError, match="market_id"):
        build_order(SimpleNamespace(market_id=None), **_base_kwargs())


# ===========================================================================
# build_order — SP orders (LIMIT_ON_CLOSE / MARKET_ON_CLOSE)
# ===========================================================================
def test_build_limit_on_close():
    b = build_order(
        _market(),
        **_base_kwargs(order_type="LIMIT_ON_CLOSE", price=3.03, size=None, liability=8.0),
    )
    assert b.price == 3.05  # prezzo SP snap a tick
    assert b.liability == 8.0
    assert b.size is None
    assert b.order.order_type.liability == 8.0
    assert b.order.order_type.price == 3.05


def test_build_market_on_close():
    b = build_order(
        _market(),
        **_base_kwargs(order_type="MARKET_ON_CLOSE", price=None, size=None, liability=7.0),
    )
    assert b.price is None
    assert b.liability == 7.0
    assert b.order.order_type.liability == 7.0


def test_build_market_on_close_cap():
    with pytest.raises(ValueError, match="cap max_stake"):
        build_order(
            _market(),
            **_base_kwargs(order_type="MARKET_ON_CLOSE", price=None, size=None,
                           liability=50.0, max_stake=10.0),
        )


def test_min_stake_verdict_is_frozen():
    v = MinStakeVerdict(True, 2.0, None)
    with pytest.raises(Exception):
        v.valid = False  # type: ignore[misc]
