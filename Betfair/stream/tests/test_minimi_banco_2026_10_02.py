"""02/10 - TEST UNITARI DELLA GUARDIA DEI MINIMI .it DEL BANCO (``minimi_banco``).

Buco trovato dal coordinatore: la mutazione ``sotto_minimo -> return False`` non era
colta dal replay di Ashdod (il motore corretto non manda piu' ordini sotto minimo,
quindi la guardia non viene mai esercitata). Qui la guardia si prova da sola:
``minimi_it_su_flumine()`` montato sopra un'esecuzione simulata FINTA che fa cio'
che fa flumine (``SimulatedExecution.execute_place``: ``order.simulated.place``
per ogni ordine del pacchetto; ``execute_replace``:
``order.trade.create_order_replacement`` e poi ``simulated.place`` del nuovo).
Finti con le chiavi e i tipi veri: ``order_package`` iterabile di ordini,
``order.side`` "BACK"/"LAY", ``order.order_type.size``, ``order.notes`` dict,
``order.simulated`` con ``size_remaining``/``size_voided``/``size_matched`` e
``_create_place_response(bet_id, status=..., error_code=...)``. ASCII-only.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from Betfair.stream.backtest import minimi_banco as MB


class SimulatoFinto:
    """``flumine.simulation.simulatedorder.SimulatedOrder``: abbina tutto al place."""

    def __init__(self, size: float) -> None:
        self.size_remaining = float(size)
        self.size_voided = 0.0
        self.size_matched = 0.0

    def _create_place_response(self, bet_id: Any, status: str = "SUCCESS",
                               error_code: Any = None) -> Any:
        return SimpleNamespace(bet_id=bet_id, status=status, error_code=error_code)

    def place(self, order_package: Any, market_book: Any, instruction: Any, bet_id: int) -> Any:
        self.size_matched = self.size_remaining
        self.size_remaining = 0.0
        return self._create_place_response(bet_id, status="SUCCESS")


class TradeFinto:
    def create_order_replacement(self, order: Any, new_price: float, size: float,
                                 date_time_created: Any) -> Any:
        return ordine(order.side, size, prezzo=new_price, notes=order.notes, trade=self)


def ordine(side: str, size: float, prezzo: float = 2.0, notes: Any = None,
           trade: Any = None) -> Any:
    o = SimpleNamespace(side=side, order_type=SimpleNamespace(size=float(size), price=prezzo),
                        notes=notes if notes is not None else {},
                        simulated=SimulatoFinto(size), trade=trade or TradeFinto(),
                        risposta=None)
    return o


def _esegui_place(self: Any, order_package: Any, http_session: Any = None) -> None:
    """Il corpo di ``SimulatedExecution.execute_place`` ridotto all'osso."""
    for i, o in enumerate(order_package):
        o.risposta = o.simulated.place(order_package, None, {}, i + 1)


def _esegui_replace(self: Any, order_package: Any, http_session: Any = None) -> None:
    for i, o in enumerate(order_package):
        resto = o.simulated.size_remaining
        nuovo = o.trade.create_order_replacement(o, 3.0, resto, None)
        nuovo.risposta = nuovo.simulated.place(order_package, None, {}, 100 + i)
        o.nuovo = nuovo


@pytest.fixture
def esecuzione(monkeypatch):
    from flumine.execution.simulatedexecution import SimulatedExecution

    monkeypatch.setattr(SimulatedExecution, "execute_place", _esegui_place)
    monkeypatch.setattr(SimulatedExecution, "execute_replace", _esegui_replace)
    return SimulatedExecution


def _piazza(esec: Any, *ordini: Any) -> List[Any]:
    with MB.minimi_it_su_flumine():
        esec.execute_place(None, list(ordini), None)
    return list(ordini)


def _rifiutato(o: Any) -> bool:
    return (o.risposta.status == "FAILURE" and o.risposta.error_code == "INVALID_BET_SIZE"
            and o.simulated.size_matched == 0.0)


@pytest.mark.parametrize("side", ["LAY", "BACK"])
def test_diretto_0_99_rifiutato_invalid_bet_size(esecuzione, side):
    [o] = _piazza(esecuzione, ordine(side, 0.99))
    assert _rifiutato(o) and o.simulated.size_voided == 0.99
    assert MB.REGISTRO.rifiutati[-1]["codice"] == "INVALID_BET_SIZE"
    assert MB.abbinati_sotto_minimo() == []


@pytest.mark.parametrize("side", ["LAY", "BACK"])
def test_diretto_1_00_passa(esecuzione, side):
    [o] = _piazza(esecuzione, ordine(side, 1.00))
    assert o.risposta.status == "SUCCESS" and o.simulated.size_matched == 1.00
    assert MB.REGISTRO.rifiutati == []


def test_place_and_trim_finale_0_49_rifiutato_0_50_passa(esecuzione):
    a = ordine("BACK", 0.49, notes={MB.NOTA_PLACE_AND_TRIM: True})
    b = ordine("LAY", 0.50, notes={MB.NOTA_PLACE_AND_TRIM: True})
    _piazza(esecuzione, a, b)
    assert _rifiutato(a)
    assert b.risposta.status == "SUCCESS" and b.simulated.size_matched == 0.50
    assert MB.abbinati_sotto_minimo() == []


@pytest.mark.parametrize("resto,passa", [(0.49, False), (0.50, True)])
def test_replace_sotto_0_50_rifiutato(esecuzione, resto, passa):
    vecchio = ordine("BACK", 1.00)
    vecchio.simulated.size_remaining = resto
    with MB.minimi_it_su_flumine():
        esecuzione.execute_replace(None, [vecchio], None)
    nuovo = vecchio.nuovo
    if passa:
        assert nuovo.risposta.status == "SUCCESS" and nuovo.simulated.size_matched == resto
    else:
        assert _rifiutato(nuovo)
        assert MB.REGISTRO.rifiutati[-1]["tipo"] == MB.SOSTITUZIONE
    # il metodo di classe del trade torna com'era
    assert "create_order_replacement" not in vars(vecchio.trade)


def test_a_guardia_spenta_il_controllo_trova_l_abbinato(esecuzione, monkeypatch):
    """Il controllo di certificazione legge gli ordini eseguiti, non la regola."""
    monkeypatch.setattr(MB, "ATTIVO", False)
    [o] = _piazza(esecuzione, ordine("LAY", 0.43))
    assert o.simulated.size_matched == 0.43
    fuori = MB.abbinati_sotto_minimo()
    assert len(fuori) == 1 and fuori[0]["size"] == 0.43 and fuori[0]["minimo"] == 1.00


def test_la_regola_si_smonta_all_uscita(esecuzione):
    with MB.minimi_it_su_flumine():
        pass
    assert esecuzione.execute_place is _esegui_place
    assert esecuzione.execute_replace is _esegui_replace
