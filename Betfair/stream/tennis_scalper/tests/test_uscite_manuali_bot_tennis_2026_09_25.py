# -*- coding: utf-8 -*-
"""USCITE AUTOMATICHE / MANUALI dei bot tennis (25/09).

Con ``uscite_automatiche = False`` (interruttore del bot in Control Room, letto
a caldo dal runner) si spengono SOLO le prese di profitto discrezionali:
  * swing: il target (``hit``);
  * pro: scaglione e target;
  * FLB: il green sullo swing.
Le protezioni restano: stop a tick (swing, pro), time-stop (swing), uscita
strutturale (pro), chiudi-ora D3 (tutti). Ogni test ha il suo contrario
(``uscite_automatiche = True`` = com'era): se il cancello non ci fosse, i test
«manuale» diventerebbero rossi; se bloccasse anche le protezioni, i test
«stop» diventerebbero rossi.

I finti sono quelli gia' in uso nelle suite dei bot (stesse chiavi del vero).
ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import pytest

from Betfair.stream.tennis_scalper.tennis_flb_bot import OPEN as FLB_OPEN
from Betfair.stream.tennis_scalper.tennis_flb_bot import TennisFLBStrategy
from Betfair.stream.tennis_scalper.tennis_pro_bot import CLOSING as PRO_CLOSING
from Betfair.stream.tennis_scalper.tennis_pro_bot import OPEN as PRO_OPEN
from Betfair.stream.tennis_scalper.tennis_pro_bot import TennisProStrategy
from Betfair.stream.tennis_scalper.tennis_scalper_bot import TennisScalperStrategy
from Betfair.stream.tennis_scalper.tennis_swing_bot import TennisSwingStrategy, _tki
from Betfair.stream.tennis_scalper.tests import test_tennis_flb_hybrid as FH
from Betfair.stream.tennis_scalper.tests import test_tennis_pro_staged as PS
from Betfair.stream.tennis_scalper.tests import test_tennis_swing as SW


def test_di_classe_le_uscite_sono_automatiche():
    """Replay, backtest e runner di prima non toccano l'attributo: il default
    DEVE essere il comportamento di sempre."""
    for cls in (TennisSwingStrategy, TennisProStrategy, TennisFLBStrategy):
        assert cls.uscite_automatiche is True
    # lo scalper non ha il cancello (la sua uscita e' la strategia)
    assert "uscite_automatiche" not in vars(TennisScalperStrategy)


# ---------------------------------------------------------------- SWING
def _swing_in_target(auto: bool):
    s = SW._make(stop_ticks=200, maker=False, tmax=10_000, target_frac=0.5)
    s.uscite_automatiche = auto
    m = SW._Market(SW._Blotter([SW._Order(111, "BACK", 2.0, 1.50)]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(1.50),
                    "anchor": _tki(1.40), "order": None, "held": 0,
                    "wait": 0, "t0": 1_000}
    # la quota e' scesa verso l'ancora oltre meta' strada: TARGET
    mb = SW._MB([SW._Runner(111, (1.42, 100), (1.43, 100), ltp=1.42)], pt=2_000)
    s.process_market_book(m, mb)
    return s, m


def test_swing_automatico_prende_il_target():
    s, m = _swing_in_target(True)
    assert s._tr["1.1"].get("closing") is True and m.placed


def test_swing_manuale_NON_prende_il_target():
    s, m = _swing_in_target(False)
    assert not s._tr["1.1"].get("closing"), "a uscite manuali il target non chiude"
    assert m.placed == [], "nessun ordine di chiusura"


def test_swing_manuale_lo_STOP_resta():
    s = SW._make(stop_ticks=2, maker=False, tmax=10_000)
    s.uscite_automatiche = False
    m = SW._Market(SW._Blotter([SW._Order(111, "BACK", 2.0, 1.50)]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(1.50),
                    "anchor": _tki(1.40), "order": None, "held": 0,
                    "wait": 0, "t0": 1_000}
    mb = SW._MB([SW._Runner(111, (1.60, 100), (1.62, 100), ltp=1.61)], pt=2_000)
    s.process_market_book(m, mb)
    assert s._tr["1.1"].get("closing") is True, "lo stop e' una protezione"
    assert m.placed


def test_swing_manuale_il_TIME_STOP_resta():
    s = SW._make(tmax=90, stop_ticks=50, target_frac=0.5, maker=False)
    s.uscite_automatiche = False
    m = SW._Market(SW._Blotter([SW._Order(111, "BACK", 2.0, 2.00)]))
    t0 = 1_000_000
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(2.00),
                    "anchor": _tki(1.80), "order": None, "held": 0,
                    "wait": 0, "t0": t0}
    s.process_market_book(m, SW._MB([SW._Runner(111, (2.00, 100), (2.02, 100))],
                                    pt=t0 + 91_000))
    assert s._tr["1.1"].get("closing") is True


# ---------------------------------------------------------------- PRO
def _pro(auto: bool, back: float, lay: float, **trade):
    s = PS._make(staged=True, staged_frac=0.4)
    s.uscite_automatiche = auto
    m = PS._Market(PS._Blotter([PS._Order(111, "BACK", 2.0, 1.80)]))
    s._trade["1.1"] = PS._open_trade(**trade)
    s.process_market_book(m, PS._MB([PS._Runner(111, (back, 100), (lay, 100))]))
    return s, m


def test_pro_automatico_scaglione_e_target():
    s, _m = _pro(True, 1.77, 1.78)
    assert s._trade["1.1"]["staged_done"] is True
    s2, _m2 = _pro(True, 1.74, 1.75)
    assert s2._trade["1.1"]["state"] == PRO_CLOSING and s2.stats["greens"] == 1


def test_pro_manuale_niente_scaglione():
    s, m = _pro(False, 1.77, 1.78)
    assert s._trade["1.1"]["staged_done"] is False and m.placed == []


def test_pro_manuale_niente_target():
    s, m = _pro(False, 1.74, 1.75)
    assert s._trade["1.1"]["state"] == PRO_OPEN
    assert s.stats["greens"] == 0 and m.placed == []


def test_pro_manuale_lo_STOP_resta():
    s, m = _pro(False, 1.84, 1.85)
    assert s.stats["stops"] == 1 and m.placed


# ---------------------------------------------------------------- FLB
def _flb_swing(auto: bool):
    s = TennisFLBStrategy(
        market_filter=FH.filters.streaming_market_filter(market_ids=["1.1"]),
        flb_params={"exit_mode": "hybrid", "green_ticks": 2, "green_frac": 0.5,
                    "lay_max": 1.10, "min_lay_size": 5.0, "dry_run": False},
    )
    s.uscite_automatiche = auto
    m = FH._Market()
    s.process_market_book(m, FH._MB([FH._Runner(111, (1.04, 200), (1.05, 200), ltp=1.05)]))
    m.blotter.orders.append(FH._Order(111, "LAY", 2.0, 1.05))
    s.process_market_book(m, FH._MB([FH._Runner(111, (1.07, 200), (1.08, 200), ltp=1.07)]))
    return s, m


def test_flb_automatico_greena_sullo_swing():
    s, m = _flb_swing(True)
    assert s._pos_state[("1.1", 111)]["greened"] is True and len(m.placed) == 2


def test_flb_manuale_NON_greena():
    s, m = _flb_swing(False)
    st = s._pos_state[("1.1", 111)]
    assert st["greened"] is False and st["state"] == FLB_OPEN
    assert len(m.placed) == 1, "solo l'ingresso: nessun green"


@pytest.mark.parametrize("auto", [True, False])
def test_flb_rimettere_automatico_riprende_il_green(auto):
    """A caldo: spento e poi riacceso, al book dopo il green scatta."""
    s, m = _flb_swing(False)
    s.uscite_automatiche = auto
    s.process_market_book(m, FH._MB([FH._Runner(111, (1.07, 200), (1.08, 200), ltp=1.07)]))
    assert s._pos_state[("1.1", 111)]["greened"] is auto
