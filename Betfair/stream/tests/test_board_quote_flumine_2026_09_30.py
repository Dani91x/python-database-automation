"""Board del giorno (board_worker): quote REST lette anche con flumine importato.

Difetto del 30/09: nel processo del runner calcio flumine e' importato e
``flumine/__init__.py`` sostituisce ``bettingresources.RunnerBookEX`` con la
classe "pigra" ``flumine.patching.EX``, che lascia i livelli come dizionari.
``_best`` faceva ``levels[0].price`` -> eccezione -> None: 46 righe su 47 del
"Programma di oggi" senza back/lay (solo quella coperta dallo scanner li aveva).

I libri sono OGGETTI VERI di betfairlightweight costruiti dalla risposta grezza
di ``listMarketBook`` (catturata il 30/09 dalla sonda
``AUDIT_2026-09-30/sonda_board_rest.py``): stesse chiavi e stessi tipi del vero.
"""
from __future__ import annotations

import pytest
from betfairlightweight.resources import bettingresources

from Betfair.stream import board_worker as bw

# risposta grezza di listMarketBook (1.262865434, 30/09 ~14:00), EX_BEST_OFFERS
_RAW = {
    "marketId": "1.262865434", "isMarketDataDelayed": False, "status": "OPEN",
    "betDelay": 0, "bspReconciled": False, "complete": True, "inplay": False,
    "numberOfWinners": 1, "numberOfRunners": 3, "numberOfActiveRunners": 3,
    "lastMatchTime": "2026-09-30T12:00:08.114Z", "totalMatched": 288.8,
    "totalAvailable": 1499.0, "crossMatching": True, "runnersVoidable": False,
    "version": 7646641232,
    "runners": [
        {"selectionId": 9459683, "handicap": 0.0, "status": "ACTIVE", "lastPriceTraded": 3.2,
         "totalMatched": 1.99,
         "ex": {"availableToBack": [{"price": 3.05, "size": 96.59}, {"price": 3.0, "size": 3.6}],
                "availableToLay": [{"price": 3.2, "size": 15.0}, {"price": 3.25, "size": 41.5}],
                "tradedVolume": []}},
        {"selectionId": 328191, "handicap": 0.0, "status": "ACTIVE", "totalMatched": 0.0,
         "ex": {"availableToBack": [{"price": 2.46, "size": 5.0}],
                "availableToLay": [{"price": 2.56, "size": 17.0}],
                "tradedVolume": []}},
        {"selectionId": 58805, "handicap": 0.0, "status": "ACTIVE", "lastPriceTraded": 3.6,
         "totalMatched": 286.8,
         "ex": {"availableToBack": [{"price": 3.4, "size": 56.76}],
                "availableToLay": [{"price": 3.6, "size": 3.0}],
                "tradedVolume": []}},
    ],
}
_META = {
    "market_id": "1.262865434", "event_id": "36081505", "event_name": "Torque v Penarol",
    "open_date": "2026-09-30T23:00:00+00:00",
    "runners": {9459683: "Torque", 328191: "Penarol", 58805: "The Draw"},
}
_ATTESO = [(9459683, 3.05, 3.2, 3.2), (328191, 2.46, 2.56, None), (58805, 3.4, 3.6, 3.6)]


def _libro():
    return bettingresources.MarketBook(**_RAW)


@pytest.fixture()
def ex_di_flumine(monkeypatch):
    """Il processo del runner: RunnerBookEX/SP sostituiti da flumine.

    Gli originali si registrano PRIMA dell'import (che li sostituisce per tutto
    il processo) cosi' il monkeypatch li rimette a posto a fine test."""
    monkeypatch.setattr(bettingresources, "RunnerBookEX", bettingresources.RunnerBookEX)
    monkeypatch.setattr(bettingresources, "RunnerBookSP", bettingresources.RunnerBookSP)
    from flumine.patching import EX, SP

    monkeypatch.setattr(bettingresources, "RunnerBookEX", EX)
    monkeypatch.setattr(bettingresources, "RunnerBookSP", SP)
    return EX


def _coppie(riga):
    return [(s["selection_id"], s["back"], s["lay"], s["ltp"]) for s in riga["selections"]]


def test_quote_con_flumine_importato(ex_di_flumine):
    libro = _libro()
    # la forma e' davvero quella del runner: livelli come dizionari
    assert type(libro.runners[0].ex) is ex_di_flumine
    assert isinstance(libro.runners[0].ex.available_to_back[0], dict)
    riga = bw._row_from_book(_META, libro)
    assert _coppie(riga) == _ATTESO
    assert riga["status"] == "OPEN" and riga["total_matched"] == 288.8


def _libro_forma_originale():
    """Il libro nella forma di betfairlightweight SENZA flumine: livelli come
    ``PriceSize`` (la classe vera). Il conftest importa gia' flumine, e la
    classe RunnerBookEX originale non e' piu' raggiungibile per nome: si
    riportano i livelli alla forma PriceSize che quella classe produce."""
    libro = _libro()
    for r in libro.runners:
        for campo in ("available_to_back", "available_to_lay"):
            livelli = getattr(r.ex, campo) or []
            setattr(r.ex, campo, [
                lv if isinstance(lv, bettingresources.PriceSize)
                else bettingresources.PriceSize(**lv) for lv in livelli])
    return libro


def test_quote_senza_flumine():
    libro = _libro_forma_originale()
    assert isinstance(libro.runners[0].ex.available_to_back[0], bettingresources.PriceSize)
    assert _coppie(bw._row_from_book(_META, libro)) == _ATTESO


def test_poll_rest_con_flumine(ex_di_flumine):
    """Il giro REST intero (_poll_books_rest) con un client finto che restituisce
    i MarketBook veri costruiti dalla risposta grezza, come betfairlightweight."""
    chiamate = []

    class _Betting:
        def list_market_book(self, market_ids, price_projection=None, **kw):
            chiamate.append((list(market_ids), price_projection))
            return [_libro()]

    class _Client:
        betting = _Betting()

    rows = bw._poll_books_rest(_Client(), {_META["market_id"]: _META})
    assert _coppie(rows[_META["market_id"]]) == _ATTESO
    assert chiamate[0][1]["priceData"] == ["EX_BEST_OFFERS"]


def test_livelli_vuoti_restano_none(ex_di_flumine):
    raw = dict(_RAW)
    raw["runners"] = [dict(r, ex={"availableToBack": [], "availableToLay": [], "tradedVolume": []})
                      for r in _RAW["runners"]]
    riga = bw._row_from_book(_META, bettingresources.MarketBook(**raw))
    assert all(s["back"] is None and s["lay"] is None for s in riga["selections"])
