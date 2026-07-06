"""Invariante del green-up copiato: profitto UGUALE su entrambi gli esiti."""

import pytest

from Betfair.stream.tennis_scalper.tennis_scalper_bot import compute_green


def _apply(net_win, net_lose, side, size, price):
    """Applica un ordine di chiusura e ritorna (win', lose')."""
    if side == "LAY":
        return net_win - size * (price - 1.0), net_lose + size
    return net_win + size * (price - 1.0), net_lose - size


def test_green_equalizes_long_position():
    # posizione "lunga": BACK 2 @ 1.90, nessun lay
    net_win = 2 * (1.90 - 1.0)     # +1.8 se vince
    net_lose = -2.0                # -2.0 se perde
    res = compute_green(net_win, net_lose, 1.88)
    assert res is not None
    side, size, locked = res
    assert side == "LAY"
    w2, l2 = _apply(net_win, net_lose, side, size, 1.88)
    assert w2 == pytest.approx(l2, abs=1e-9)       # esiti pareggiati
    assert w2 == pytest.approx(locked, abs=1e-9)   # = profitto bloccato


def test_green_equalizes_short_position():
    # posizione "corta": LAY 2 @ 1.90
    net_win = -2 * (1.90 - 1.0)    # -1.8 se vince
    net_lose = 2.0                 # +2.0 se perde
    res = compute_green(net_win, net_lose, 1.92)
    assert res is not None
    side, size, locked = res
    assert side == "BACK"
    w2, l2 = _apply(net_win, net_lose, side, size, 1.92)
    assert w2 == pytest.approx(l2, abs=1e-9)
    assert w2 == pytest.approx(locked, abs=1e-9)


def test_green_none_when_flat():
    assert compute_green(1.0, 1.0, 1.90) is None      # gia' pareggiato
    assert compute_green(1.0, 0.5, 1.0) is None       # prezzo non valido


def test_scalp_back_then_lay_locks_positive():
    # scalp 1 tick: BACK 2 @ 1.90 poi green a 1.89 -> profitto > 0
    net_win = 2 * (1.90 - 1.0)
    net_lose = -2.0
    side, size, locked = compute_green(net_win, net_lose, 1.89)
    assert side == "LAY"
    assert locked > 0.0
