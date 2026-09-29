"""PIANO MIKE 29/09, P5 blocco 3: ``_riduzione_verificata`` del motore ordini
guarda il MERCATO quando il mercato ha due esiti.

Con la copertura come banca Under 4,5 la chiusura e' una banca Over 4,5: sulla
selezione Over non c'e' niente, ma la posizione del mercato si riduce. Prima il
runner (paper sul canale) con kill-switch o guardia d'avvio la RIFIUTAVA: una
differenza fra paper e live (il live REST non passa di qui). Paper = specchio.

Finti: il fixture vero del motore (``amb``: canale vero, motore vero, flumine
finto fedele) piu' un ``MarketBook`` VERO di betfairlightweight con i due runner.
Le esposizioni del blotter si leggono con la stessa funzione del motore
(``LOW._read_matched_exposures``), sostituita con i numeri per selezione.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import pytest
from betfairlightweight.resources.bettingresources import MarketBook

from Betfair.stream import motore_ordini as MO
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401 - fixture
    LOW, _ack, _cmd, _manda, amb)

UNDER, OVER = 1222344, 1222345


def _book(*ids: int) -> MarketBook:
    return MarketBook(marketId="1.234", isMarketDataDelayed=False, status="OPEN", betDelay=5,
                      bspReconciled=False, complete=True, inplay=True, numberOfWinners=1,
                      numberOfRunners=len(ids), numberOfActiveRunners=len(ids),
                      totalMatched=0, totalAvailable=0, crossMatching=False,
                      runnersVoidable=False, version=1,
                      runners=[{"selectionId": i, "status": "ACTIVE", "handicap": 0.0}
                               for i in ids])


def _esposizioni(per_sel: Dict[int, Tuple[float, float]]):
    return lambda _f, _m, _s, sid, _h: per_sel.get(int(sid), (0.0, 0.0))


@pytest.fixture
def kill(amb, monkeypatch):
    monkeypatch.setattr(LOW, "_SETTINGS", {"kill_switch": True})
    return amb


def test_altro_runner_solo_con_due_esiti():
    class M:
        market_book = _book(UNDER, OVER)
    assert MO.altro_runner_due_esiti(M(), OVER) == (UNDER, 0.0)
    assert MO.altro_runner_due_esiti(M(), UNDER) == (OVER, 0.0)
    assert MO.altro_runner_due_esiti(M(), 999) is None

    class M3:
        market_book = _book(1, 2, 3)
    assert MO.altro_runner_due_esiti(M3(), 1) is None

    class Senza:
        pass
    assert MO.altro_runner_due_esiti(Senza(), 1) is None


def test_banca_over_che_annulla_la_banca_under_e_una_riduzione(kill, monkeypatch):
    kill.market.market_book = _book(UNDER, OVER)
    # banca Under 4,5 12,63 a 1,18 abbinata: se vince l'Under -2,27, se perde +12,63
    monkeypatch.setattr(LOW, "_read_matched_exposures",
                        _esposizioni({UNDER: (-2.2734, 12.63)}))
    ws = kill.ch.collega("mike")
    _manda(kill, ws, _cmd("mike", 1, selection_id=OVER, side="LAY", price=21.0, size=0.71,
                          reduces_liability=True))
    assert _ack(kill, ws)["accettato"] is True
    assert len(kill.market.calls) == 1


def test_banca_over_che_AUMENTA_la_posizione_resta_rifiutata(kill, monkeypatch):
    kill.market.market_book = _book(UNDER, OVER)
    # posizione gia' lunga sull'Over (punta Over): un'altra banca Under la aumenta
    monkeypatch.setattr(LOW, "_read_matched_exposures",
                        _esposizioni({OVER: (12.66, -2.26)}))
    ws = kill.ch.collega("mike")
    _manda(kill, ws, _cmd("mike", 1, selection_id=UNDER, side="LAY", price=1.18, size=12.63,
                          reduces_liability=True))
    assert _ack(kill, ws)["motivo"].startswith(MO.M_RIDUZIONE)
    assert kill.market.calls == []


def test_con_tre_esiti_nessuna_somma_come_prima(kill, monkeypatch):
    kill.market.market_book = _book(UNDER, OVER, 7)
    monkeypatch.setattr(LOW, "_read_matched_exposures",
                        _esposizioni({UNDER: (-2.2734, 12.63)}))
    ws = kill.ch.collega("mike")
    _manda(kill, ws, _cmd("mike", 1, selection_id=OVER, side="LAY", price=21.0, size=0.71,
                          reduces_liability=True))
    assert _ack(kill, ws)["motivo"].startswith(MO.M_RIDUZIONE)
