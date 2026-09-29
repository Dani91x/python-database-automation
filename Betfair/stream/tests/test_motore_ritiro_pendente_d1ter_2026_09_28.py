"""D1-ter (28/09) - BLOCCO 3 (M1): il motore non abbandona un place-and-trim
finche' l'ordine non e' confermato MORTO.

Difetto: al timeout della sequenza ``_abbandona_submin`` annullava l'ordine; se
l'ordine non aveva ancora il ``bet_id`` flumine solleva ``OrderUpdateError``
(``flumine/order/order.py``: «Order does not currently have a betId»),
l'eccezione era presa e il motore emetteva comunque il terminale ``errore``: il
parcheggio da 2,00 EUR poteva nascere dopo e restare a mercato senza nessuno che
lo seguisse. Ora: «ritiro pendente», ritentato a ogni giro, terminale solo a
ordine terminale.

Ambiente: lo stesso del test del motore (``amb``: canale vero, motore vero,
ordini flumine VERI, mercato finto con la borsa), piu' il ``cancel_order`` che
solleva come flumine su un ordine senza ``bet_id``.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest
from flumine.exceptions import OrderUpdateError

from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401
    LOW, _ack, _cmd, _manda, amb)


def _cancel_come_flumine(market: Any) -> None:
    """``Market.cancel_order`` -> ``order.cancel`` di flumine: senza bet_id
    solleva ``OrderUpdateError`` (stesso tipo e stesso testo)."""
    vero = market.cancel_order

    def _cancel(order: Any, size_reduction: Optional[float] = None) -> bool:
        if not getattr(order, "bet_id", None):
            market.calls.append(("cancel_ko", order, size_reduction))
            raise OrderUpdateError("Order does not currently have a betId")
        return vero(order, size_reduction)
    market.cancel_order = _cancel


def _fasi(amb: Any, ws: Any) -> list:
    return [m["d"]["fase"] for m in amb.ch.per_ws(ws, "order")]


def _avvia(amb: Any, monkeypatch) -> tuple:
    amb.market.borsa = True
    _cancel_come_flumine(amb.market)
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, size=1.0, price=3.0))
    assert _ack(amb, ws)["accettato"] is True
    ordine = amb.market.calls[0][0]
    monkeypatch.setattr(LOW, "_submin_timeout_sec", lambda: -1.0)
    return ws, ordine


def test_timeout_senza_bet_id_non_emette_il_terminale_e_ritenta(amb, monkeypatch):
    ws, ordine = _avvia(amb, monkeypatch)
    # il pacchetto e' ancora nel bet delay: nessun bet_id, ordine in attesa
    ordine.bet_id = None
    ordine.placing()
    for _ in range(3):
        amb.motore.avanza_submin()
    assert "errore" not in _fasi(amb, ws), "terminale emesso su un ordine forse vivo"
    assert amb.motore._submin, "sequenza abbandonata con il ritiro non riuscito"
    # arriva il bet_id, l'ordine e' a mercato: il giro dopo lo ritira davvero
    ordine.bet_id = "31242609999"
    amb.market.blotter.ordini[ordine.bet_id] = ordine
    ordine.executable()
    amb.motore.avanza_submin()
    assert ("cancel", ordine, None) in amb.market.calls
    assert _fasi(amb, ws)[-1] == "errore"
    assert not amb.motore._submin


def test_cancel_che_solleva_non_chiude_la_sequenza(amb, monkeypatch):
    """Anche con il bet_id, un annullo che solleva (rete, stato transitorio)
    non chiude: si ritenta al giro dopo."""
    ws, ordine = _avvia(amb, monkeypatch)
    vero = amb.market.cancel_order
    n = {"k": 0}

    def _una_volta_ko(order: Any, size_reduction: Optional[float] = None) -> bool:
        n["k"] += 1
        if n["k"] == 1:
            raise OrderUpdateError("stato transitorio")
        return vero(order, size_reduction)
    amb.market.cancel_order = _una_volta_ko
    amb.motore.avanza_submin()
    assert "errore" not in _fasi(amb, ws) and amb.motore._submin
    amb.motore.avanza_submin()
    assert _fasi(amb, ws)[-1] == "errore" and not amb.motore._submin
    assert n["k"] == 2


def test_ordine_gia_terminale_si_chiude_senza_annullo(amb, monkeypatch):
    ws, ordine = _avvia(amb, monkeypatch)
    ordine.execution_complete()
    prima = len(amb.market.calls)
    amb.motore.avanza_submin()
    assert len(amb.market.calls) == prima, "annullo chiesto su un ordine gia' morto"
    assert _fasi(amb, ws)[-1] == "errore" and not amb.motore._submin


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_vale_in_paper_e_in_live(amb, monkeypatch, mode):
    amb.market.borsa = True
    _cancel_come_flumine(amb.market)
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode=mode, size=1.0, price=3.0))
    ordine = amb.market.calls[0][0]
    monkeypatch.setattr(LOW, "_submin_timeout_sec", lambda: -1.0)
    ordine.bet_id = None
    ordine.placing()
    amb.motore.avanza_submin()
    assert "errore" not in _fasi(amb, ws) and amb.motore._submin
