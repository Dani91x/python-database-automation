# -*- coding: utf-8 -*-
"""FLB e SWING col residuo sotto 0,50 (decisione 1 dell'utente, 04/10/2026).

Domanda del coordinatore: senza il ramo «esci col residuo» FLB e swing restano
bloccati in chiusura? Qui il bot VERO, nel banco del runner paper (Flumine, blotter
e book veri, esecuzione sincrona), con una posizione la cui chiusura richiede un
ordine sotto 0,50 EUR (LAY 0,30 @2,10 -> punta 0,32 al best-back 2,00):
  * prima: FLB ripeteva `green_fallito` a ogni book e la posizione restava OPEN;
    SWING restava `closing` per sempre (mai dimenticato, mai riaperto);
  * ora: il residuo e' DICHIARATO una volta (CRITICAL con la proposta), RICORDATO
    nelle `stats`, e il bot torna libero di operare.
"""
from __future__ import annotations

from typing import Any, List

import pytest

from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_esatte_2026_09_28 import (  # noqa: F401
    esecuzione_sincrona,
)
from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_via_bot_2026_09_28 import (
    _nessun_vivo,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _control,
    _follow,
    banchi,
    db,
)
from Betfair.stream.tennis_scalper import tennis_flb_bot as FLB


def _prepara(db: Any, banchi: Any, bot: str):
    db.controls = [_control("101", bot, status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    strat = b.session.hosted[("101", bot)]
    eventi: List[tuple] = []
    strat.event_sink = lambda k, p: eventi.append((k, dict(p)))
    market = b.fw.markets.markets["1.101"]
    o = b.posizione("101", bot, lato="LAY", prezzo=2.10, size=0.30)
    return b, strat, market, eventi, o


def _crit(eventi: List[tuple]) -> List[dict]:
    return [p for k, p in eventi if k == "residuo_non_piazzabile"]


def test_flb_residuo_dichiarato_una_volta_e_posizione_libera(db, banchi, esecuzione_sincrona):
    b, strat, market, eventi, o = _prepara(db, banchi, "tennis_flb")
    strat.exit_mode = "green"
    key = ("1.101", 11)
    st = {"state": FLB.OPEN, "entry": 1.9, "order": o, "wait": 0, "greened": False,
          "t0": 0}
    strat._pos_state[key] = st
    for _ in range(6):
        b.book("101")
        st = strat._pos_state.get(key) or {}
        if st.get("state") == FLB.OPEN:
            strat._manage(market, 11, key, st, 2.0, 2.1, 0)
    assert strat._pos_state[key]["state"] == FLB.DONE
    assert [k for k, _ in eventi].count("green_fallito") == 0
    crit = _crit(eventi)
    assert len(crit) == 1 and crit[0]["importo"] == 0.32 and crit[0]["lato"] == "BACK"
    assert strat.stats["residui_ricordati"][0]["importo"] == 0.32
    assert _nessun_vivo(market, strat) == []
    strat.process_closed_market(market, market.market_book)
    assert strat.stats["residui_ricordati"] == []


def test_swing_residuo_dichiarato_una_volta_trade_chiuso(db, banchi, esecuzione_sincrona):
    b, strat, market, eventi, o = _prepara(db, banchi, "tennis_swing")
    mid = "1.101"
    strat._tr[mid] = {"sel": 11, "side": "LAY", "etk": 0, "anchor": 0.0, "order": o,
                      "held": 0, "wait": 0, "px": 2.1, "t0": None, "closing": True,
                      "close_order": None, "close_wait": 0, "t_close": None}
    for _ in range(6):
        b.book("101")
        tr = strat._tr.get(mid)
        if tr is not None:
            strat._manage_trade(market, market.market_book, mid, tr)
    assert mid not in strat._tr, "il trade non deve restare in chiusura per sempre"
    crit = _crit(eventi)
    assert len(crit) == 1 and crit[0]["importo"] == 0.32 and crit[0]["lato"] == "BACK"
    assert strat.stats["residui_ricordati"][0]["importo"] == 0.32
    assert _nessun_vivo(market, strat) == []
    strat.process_closed_market(market, market.market_book)
    assert strat.stats["residui_ricordati"] == []
