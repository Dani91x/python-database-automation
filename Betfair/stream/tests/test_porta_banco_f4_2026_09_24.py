"""24/09 - F4: la porta del banco passa dal MOTORE VERO (``_dispatch`` di produzione).

Contratto: un bot certificato «via canale» nel replay deve attraversare lo
stesso codice del vivo. Qui si prova che ``PortaBanco``:
  * chiama ``live_order_worker._dispatch`` (quello vero, spiato, non sostituito);
  * risponde con l'ack del motore (stesse chiavi, dedup per ref con
    ``ref_gia_visto``);
  * produce eventi ``order`` con le chiavi dello specchio ``betfair_live_orders``
    costruite dalla funzione di produzione ``LiveTradingStrategy._order_row``;
  * serve il place-and-trim sotto il minimo con la stessa macchina del vivo;
  * funziona a .env OFF (il banco e' PAPER per costruzione, client simulato).

Finti: client = ``cliente_simulato()`` del banco (SimulatedClient VERO) nel
registro VERO ``flumine.clients.Clients``; strategia ``BaseStrategy`` vera;
ordini ``BetfairOrder`` veri costruiti da ``build_order``; Market doppio con la
regola ``Market.transaction`` di flumine (stesso finto del test del motore).
"""
from __future__ import annotations

import time
from typing import Any, List

import pytest
from flumine import BaseStrategy, clients

from Betfair.stream import live_order_worker as LOW
from Betfair.stream import motore_ordini as MO
from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest.porta_banco import PortaBanco
from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import _Framework, _Market

_STRAT = BaseStrategy(market_filter={}, name="banco_f4")


@pytest.fixture()
def banco(monkeypatch, tmp_path):
    monkeypatch.setenv("LIVE_ORDER_MODE", "OFF")      # il .env della macchina non conta
    monkeypatch.setattr(LOW, "_kill_switch", lambda: False)
    monkeypatch.setattr(LOW, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(LOW, "_max_stake", lambda: None)
    monkeypatch.setattr(LOW, "_SETTINGS", {})
    registro = clients.Clients()
    sim = B.cliente_simulato()
    sim.eseguiti = []                  # spia del Market doppio (come _ClientSpia)
    registro.add_client(sim)
    market = _Market("1.234", registro)
    market.borsa = True
    fl = _Framework({"1.234": market}, registro)
    chiamate: List[Any] = []
    vero = LOW._dispatch

    def _spia(*a: Any, **k: Any) -> Any:
        chiamate.append(a[2]["action"])
        return vero(*a, **k)
    monkeypatch.setattr(LOW, "_dispatch", _spia)
    porta = PortaBanco(fl, _STRAT, attore="safe", cartella_diario=str(tmp_path))
    return porta, market, sim, chiamate


def _cmd(n: int, **kw: Any):
    d = {"ref": f"safe-t{n}", "attore": "safe", "azione": "place", "mode": "paper",
         "market_id": "1.234", "selection_id": 47972, "side": "BACK", "price": 2.5,
         "size": 3.0, "persistence": "LAPSE", "strategy_ref": "safe",
         "creato_ms": int(time.time() * 1000), "max_eta_ms": 3000}
    d.update(kw)
    return d


def test_porta_banco_passa_dal_dispatch_vero_col_client_simulato(banco):
    porta, market, sim, chiamate = banco
    ack = porta.invia(_cmd(1))
    assert set(ack) == {"ref", "seq", "accettato", "motivo", "ricevuto_ms"}
    assert ack["accettato"] is True
    assert porta.esiti("safe-t1")[0]["fase"] == "inviato"   # nessun errore post-place
    assert chiamate == ["place"]                          # il _dispatch VERO
    order, sref, client = market.calls[0]
    assert client is sim and sref == "safe"
    assert order.trade.strategy is _STRAT


def test_eventi_con_le_chiavi_dello_specchio_di_produzione(banco):
    porta, market, _sim, _ = banco
    porta.invia(_cmd(1))
    ev = porta.esiti("safe-t1")
    assert [e["fase"] for e in ev] == ["inviato", "accettato_betfair"]
    chiavi_prod = set(LiveTradingStrategy._order_row(
        type("S", (), {"mode": "paper"})(), market.calls[0][0], event_id="E1",
        market_id="1.234")) | {"updated_at"}
    assert chiavi_prod == set(MO.CHIAVI_SPECCHIO)          # nessuna deriva dal vivo
    for e in ev:
        assert set(MO.CHIAVI_SPECCHIO) <= set(e)
        assert {"ref", "seq", "fase", "esito_ms"} <= set(e)
    assert ev[-1]["bet_id"] == market.calls[0][0].bet_id
    assert ev[-1]["mode"] == "paper"


def test_dedup_e_rifiuti_come_dal_vivo(banco):
    porta, market, _sim, chiamate = banco
    primo = porta.invia(_cmd(1))
    secondo = porta.invia(_cmd(1, price=9.0))
    assert secondo == dict(primo, motivo=MO.MOTIVO_REF_GIA_VISTO)
    rif = porta.invia(_cmd(2, side="back"))
    assert rif["accettato"] is False and rif["motivo"].startswith(MO.M_PARAM)
    assert chiamate == ["place"] and len(market.calls) == 1


def test_place_and_trim_nel_banco_stessa_macchina(banco):
    porta, market, _sim, chiamate = banco
    ack = porta.invia(_cmd(1, size=1.0, price=3.0))
    assert ack["accettato"] is True and chiamate == ["place_submin"]
    for _ in range(6):
        porta.aggiorna()
    fasi = [e["fase"] for e in porta.esiti("safe-t1")]
    assert fasi[:4] == ["inviato", "parcheggiato", "ridotto", "accettato_betfair"]
    ordine = market.calls[0][0]
    assert ordine.order_type.size == 1.0 and ordine.order_type.price == 3.0
