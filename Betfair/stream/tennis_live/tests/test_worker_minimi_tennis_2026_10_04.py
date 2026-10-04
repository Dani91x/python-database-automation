# -*- coding: utf-8 -*-
"""WORKER ORDINI TENNIS e regola delle punte dell'utente (04/10/2026).

Prima (`tennis_live_order_worker._do_place` / `_do_greenup`): la punta veniva
arrotondata per difetto al multiplo di 0,50 SENZA dichiarare il resto, e un hedge
del green-up sotto 1,00 sollevava ValueError («size hedge non valida»).
Ora, con la regola UNICA `minimi_it.importo_piazzabile`:
  * punta diretta per difetto, il resto dichiarato nel campo `punta_050` (come il
    motore calcio: chiesto, piazzato, residuo) e nella `detail`;
  * hedge fra 0,50 e 1,00: place-and-trim (la macchina dei bot tennis), avanzato dal
    giro del worker;
  * hedge sotto 0,50: nessun ordine, esito non riuscito con il residuo DICHIARATO.

Finti: il banco del runner paper VERO (`test_tennis_iscrizione_a_caldo`): Flumine,
capture della modalita', blotter, book e ordini veri; esecuzione simulata sincrona.
"""
from __future__ import annotations

from typing import Any, List

import pytest
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.stream.tennis_live import tennis_live_order_worker as TOW
from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_esatte_2026_09_28 import (  # noqa: F401
    esecuzione_sincrona,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _follow,
    banchi,
    db,
)

MID = "1.101"


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")     # il runner paper
    TOW._ESATTE.clear()
    yield
    TOW._ESATTE.clear()


def _prepara(db: Any, banchi: Any, lato: str, prezzo: float, size: float):
    db.controls = []
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    cap = TOW._capture_strategy(b.session, MID, "paper")
    assert cap is not None
    market = b.fw.markets.markets[MID]
    o = Trade(MID, 11, 0, cap).create_order(lato, LimitOrder(prezzo, size))
    o.update_client(b.client)
    o.simulated.matched = [[0, prezzo, size]]
    o.simulated.size_matched = size
    o.simulated.average_price_matched = prezzo
    o.execution_complete()
    market.blotter[o.id] = o
    return b, cap, market


def _greenup() -> dict:
    return {"action": "greenup", "mode": "paper", "market_id": MID, "selection_id": 11,
            "handicap": 0.0, "params": {}}


def _ordini(market: Any, cap: Any) -> List[Any]:
    return list(market.blotter.strategy_orders(cap))


def test_hedge_sotto_il_floor_non_esplode_residuo_dichiarato(db, banchi, esecuzione_sincrona):
    """LAY 0,30 @2,10: hedge BACK 0,32 al best-back 2,00. Nessun ordine (sotto 0,50
    nessun ordine .it), esito non riuscito col residuo dichiarato; prima ValueError."""
    b, cap, market = _prepara(db, banchi, "LAY", 2.10, 0.30)
    n = len(_ordini(market, cap))
    res = TOW._dispatch(b.fw, b.session, _greenup(), "awtq9001")
    assert res["ok"] is False and "RESIDUO_NON_PIAZZABILE" in res["error"]
    r = res["residuo_non_piazzabile"]
    assert r["lato"] == "BACK" and r["importo"] == 0.32 and r["prezzo"] == 2.0
    assert len(_ordini(market, cap)) == n                      # nessun ordine


def test_hedge_fra_050_e_1_va_col_place_and_trim(db, banchi, esecuzione_sincrona):
    """LAY 0,80 @2,10: hedge BACK 0,84. Parte il parcheggio 1,00 a quota non
    abbinabile, il giro del worker lo taglia e lo riprezza: alla fine un BACK 0,84
    a 2,00, nessun ordine vivo sopra 0,84 a quota vera."""
    b, cap, market = _prepara(db, banchi, "LAY", 2.10, 0.80)
    res = TOW._dispatch(b.fw, b.session, _greenup(), "awtq9002")
    assert res["ok"] is True and res["place_and_trim"]["importo"] == 0.84
    park = [o for o in _ordini(market, cap) if float(o.order_type.price) == 1000.0]
    assert len(park) == 1 and float(park[0].order_type.size) == 1.0
    for _ in range(6):
        TOW._avanza_uscite_esatte(b.fw)
    vere = [o for o in _ordini(market, cap)
            if o.side == "BACK" and float(o.order_type.price) == 2.0]
    assert [round(float(o.order_type.size), 2) for o in vere] == [0.84]
    assert not any(ue.attive for ue in TOW._ESATTE.values())


def test_hedge_punta_diretta_per_difetto_col_residuo_dichiarato(db, banchi,
                                                               esecuzione_sincrona):
    """LAY 3,00 @2,10: hedge BACK 3,15 -> parte 3,00, residuo 0,15 dichiarato."""
    b, cap, market = _prepara(db, banchi, "LAY", 2.10, 3.0)
    res = TOW._dispatch(b.fw, b.session, _greenup(), "awtq9003")
    assert res["ok"] is True
    assert res["punta_050"] == {"chiesto": 3.15, "piazzato": 3.0, "residuo": 0.15,
                                "motivo": res["punta_050"]["motivo"]}
    assert "residuo 0.15 NON piazzato" in res["detail"]
    nuovi = [o for o in _ordini(market, cap) if o.side == "BACK"]
    assert [float(o.order_type.size) for o in nuovi] == [3.0]


def test_place_punta_per_difetto_dichiarata(db, banchi, esecuzione_sincrona):
    b, cap, market = _prepara(db, banchi, "LAY", 2.10, 3.0)
    cmd = {"action": "place", "mode": "paper", "market_id": MID, "selection_id": 11,
           "handicap": 0.0, "side": "back", "price": 2.0, "size": 2.37}
    res = TOW._dispatch(b.fw, b.session, cmd, "awtq9004")
    assert res["ok"] is True and float(res["size"]) == 2.0
    assert res["punta_050"]["residuo"] == 0.37 and res["punta_050"]["chiesto"] == 2.37
    cmd2 = dict(cmd, size=2.5)
    assert "punta_050" not in TOW._dispatch(b.fw, b.session, cmd2, "awtq9005")
