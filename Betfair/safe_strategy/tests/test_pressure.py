"""Test dell'indice di pressione (pressure.py), modulo puro. File ASCII-only."""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import pressure as PR


def _payload(minute=60, corners=None, yellows=None, booking=None, timeline=None):
    home, away = {}, {}
    if corners is not None:
        home["numberOfCorners"], away["numberOfCorners"] = corners
    if yellows is not None:
        home["numberOfYellowCards"], away["numberOfYellowCards"] = yellows
    if booking is not None:
        home["bookingPoints"], away["bookingPoints"] = booking
    p = {"minute": minute, "score_raw": {"score": {"home": home, "away": away}}}
    if timeline is not None:
        p["timeline"] = timeline
    return p


def _corner(team, minute):
    return {"type": "Corner", "team": team, "minute": minute}


def test_neutro_senza_dati_o_troppo_presto():
    assert PR.pressure_from_payload(None) == (1.0, 1.0)
    assert PR.pressure_from_payload({}) == (1.0, 1.0)
    assert PR.pressure_from_payload({"minute": 60, "score_raw": None}) == (1.0, 1.0)
    assert PR.pressure_from_payload(_payload(minute=3, corners=(6, 0))) == (1.0, 1.0)
    assert PR.pressure_index(_payload(minute=60)) is None


def test_corner_totali_ips():
    # 6-0 al 60': edge corner = 1 -> idx 0.75 -> casa 1 + 0.25*0.75 = 1.1875, ospite clip 0.85
    mh, ma = PR.pressure_from_payload(_payload(minute=60, corners=(6, 0)))
    assert mh == pytest.approx(1.1875) and ma == 0.85
    # simmetrico
    mh2, ma2 = PR.pressure_from_payload(_payload(minute=60, corners=(0, 6)))
    assert (mh2, ma2) == (ma, mh)
    # 3-3: neutro esatto
    assert PR.pressure_from_payload(_payload(minute=60, corners=(3, 3))) == (1.0, 1.0)
    # campione piccolo smorzato: 1-0 -> edge 1/2 -> idx 0.375 -> 1.09375
    assert PR.pressure_from_payload(_payload(minute=60, corners=(1, 0)))[0] == pytest.approx(1.09375, abs=1e-4)
    # valori stringa (IPS li manda cosi')
    assert PR.pressure_from_payload(_payload(minute=60, corners=("6", "0")))[0] == pytest.approx(1.1875)


def test_timeline_finestra_mobile_ha_la_precedenza_sui_totali():
    # totali a favore della casa, ma negli ultimi 10' tutti i corner sono ospiti
    tl = [_corner("home", 5), _corner("home", 12), _corner("away", 55), _corner("away", 58)]
    mh, ma = PR.pressure_from_payload(_payload(minute=60, corners=(5, 2), timeline=tl))
    assert ma > 1.0 > mh
    assert PR.rolling_corners(tl, 60) == (0, 2)
    # corner al minuto 50 esatto: fuori dalla finestra (50 < m <= 60)
    assert PR.rolling_corners([_corner("home", 50), _corner("home", 51)], 60) == (1, 0)
    # timeline senza corner attribuibili -> si torna ai totali
    assert PR.rolling_corners([{"type": "Goal", "team": "home", "minute": 10}], 60) is None
    assert PR.rolling_corners([_corner(None, 55)], 60) is None
    assert PR.pressure_from_payload(_payload(minute=60, corners=(6, 0),
                                             timeline=[{"type": "Goal"}]))[0] == pytest.approx(1.1875)


def test_cartellini_gialli_avversari_sono_pressione():
    # 0 gialli casa, 3 ospiti -> card_edge 1 -> idx 0.25 -> casa 1.0625
    mh, ma = PR.pressure_from_payload(_payload(minute=60, yellows=(0, 3)))
    assert mh == pytest.approx(1.0625) and ma == pytest.approx(0.9375)
    # riserva: bookingPoints per lato (10 punti = un giallo)
    assert PR.pressure_from_payload(_payload(minute=60, booking=(0, 30))) == (mh, ma)
    # corner e cartellini in direzioni opposte si compensano parzialmente
    mh2, _ = PR.pressure_from_payload(_payload(minute=60, corners=(6, 0), yellows=(3, 0)))
    assert 1.0 < mh2 < 1.1875


def test_moltiplicatori_sempre_nel_range():
    for corners in ((20, 0), (0, 20), (9, 1), (2, 2)):
        for yellows in ((5, 0), (0, 5), (1, 1)):
            mh, ma = PR.pressure_from_payload(_payload(minute=70, corners=corners, yellows=yellows))
            assert PR.MULT_MIN <= mh <= PR.MULT_MAX and PR.MULT_MIN <= ma <= PR.MULT_MAX
