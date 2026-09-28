"""SNIPER: la piattezza vista dallo STOP della sessione (cantiere D2, 28/09).

Reperto e2e del 26/09 (freno tirato 11:42Z): force-flat dello scalper in 2 s,
poi "posizione NON flat dopo 30 s" col micro-residuo sniper 0,085 EUR, che il
bot ha ACCETTATO per costruzione (``sniper_bot._drive_flatten``, residuo
<= 0,30). Causa radice: ``SniperStrategy.is_flat`` misurava |stake back - stake
lay| > 0,02, che non e' la piattezza: un green-up riuscito ha stake diverse
(back 10 @3,0 + lay 12 @2,5 = +2,00 EUR su entrambi gli esiti) e restava "non
flat" per sempre; lo stop della sessione (``scalper_session._all_flat``)
aspettava 30 s a vuoto e dichiarava aperta una posizione chiusa. Uguale in
paper e in live (stesso codice, stessi ordini).

Ora ``is_flat`` usa la misura con cui il bot DECIDE (|se vince - se perde|)
e la sua tolleranza (0,02, o il residuo accettato + 0,02). I finti sono
quelli del test sniper esistente (stesse chiavi degli ordini flumine:
``side``, ``size_matched``, ``average_price_matched``, ``status`` Enum).
"""
from __future__ import annotations

from Betfair.stream.tests.test_sniper_bot_2026_07_10 import _FakeOrder, _strategy


def _pos_con(s, *ordini, residuo: float = 0.0):
    pos = s._p("1.234", 1221385)
    pos.flatten_orders = list(ordini)
    pos.residual_accepted = residuo
    return pos


def test_green_riuscito_e_piatto_anche_con_stake_diverse():
    s = _strategy()
    _pos_con(s, _FakeOrder("BACK", price=3.0, size=10.0, size_matched=10.0, avg=3.0),
             _FakeOrder("LAY", price=2.5, size=12.0, size_matched=12.0, avg=2.5))
    nw, nl = s._real_net(s._p("1.234", 1221385))
    assert abs(nw - nl) < 1e-9 and abs(nw - 2.0) < 1e-9      # +2 su entrambi
    assert s.is_flat() is True


def test_micro_residuo_accettato_dal_bot_e_piatto():
    s = _strategy()
    # |se vince - se perde| = 30 - 2,5 * 11,966 = 0,085 (il residuo del 26/09)
    _pos_con(s, _FakeOrder("BACK", price=3.0, size=10.0, size_matched=10.0, avg=3.0),
             _FakeOrder("LAY", price=2.5, size=11.966, size_matched=11.966, avg=2.5),
             residuo=0.085)
    assert s.is_flat() is True


def test_gamba_scoperta_non_e_piatta():
    s = _strategy()
    _pos_con(s, _FakeOrder("BACK", price=3.0, size=10.0, size_matched=10.0, avg=3.0))
    assert s.is_flat() is False


def test_sbilancio_oltre_il_residuo_accettato_non_e_piatto():
    s = _strategy()
    # 30 - 2,5 * 11,8 = 0,50 > 0,085 + 0,02
    _pos_con(s, _FakeOrder("BACK", price=3.0, size=10.0, size_matched=10.0, avg=3.0),
             _FakeOrder("LAY", price=2.5, size=11.8, size_matched=11.8, avg=2.5),
             residuo=0.085)
    assert s.is_flat() is False


def test_micro_residuo_NON_accettato_non_e_piatto():
    """Senza l'accettazione del bot vale la tolleranza stretta 0,02."""
    s = _strategy()
    _pos_con(s, _FakeOrder("BACK", price=3.0, size=10.0, size_matched=10.0, avg=3.0),
             _FakeOrder("LAY", price=2.5, size=11.966, size_matched=11.966, avg=2.5))
    assert s.is_flat() is False


def test_ordine_vivo_non_e_mai_piatto():
    s = _strategy()
    _pos_con(s, _FakeOrder("BACK", price=3.0, size=10.0, size_matched=10.0, avg=3.0),
             _FakeOrder("LAY", price=2.5, size=12.0, size_matched=12.0, avg=2.5),
             _FakeOrder("LAY", price=2.4, size=2.0, live=True))
    assert s.is_flat() is False
