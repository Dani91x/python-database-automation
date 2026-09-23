"""23/09 - Omega, annullo: l'abbinato IGNOTO dopo l'annullo va dichiarato.

Prima: in ``cancel_order_live`` un'eccezione di rete nella rilettura
(``order_state_by_bet_id``) lasciava ``riletto=False`` con matched/residuo
None e un solo warning: nessun secondo tentativo, e nessun segno esplicito
per il chiamante. Adesso: fino a 2 riletture di RISERVA con attesa breve; se
l'abbinato resta ignoto l'esito porta ``abbinato_ignoto=True``. Quando la
prima rilettura riesce non parte nessuna chiamata in piu'.

Rete finta A LIVELLO DI TRASPORTO (fixture ``betfair`` di
``Betfair/tests/test_consapevolezza_ordine_2026_09_16.py``): le funzioni di
``omega_market`` sono quelle vere e le risposte hanno le chiavi grezze di
Betfair (``currentOrders``/``sizeMatched``/...). Il guasto si inietta sul
trasporto di lettura (``call``) con un ``ConnectionError``.
"""
from __future__ import annotations

import pytest

from Betfair.omega import omega_market as OM
from Betfair.tests.test_consapevolezza_ordine_2026_09_16 import (  # noqa: F401
    betfair, cancel_report, current_orders)


@pytest.fixture()
def rete_che_cade(betfair, monkeypatch):
    """Il trasporto di lettura cade le prime ``k`` volte, poi risponde vero."""
    monkeypatch.setattr(OM, "_RILETTURA_ATTESA_S", 0.0, raising=False)
    stato = {"cadute": 0, "letture": 0}
    vero = OM.call

    def legge(fn):
        stato["letture"] += 1
        if stato["cadute"] > 0:
            stato["cadute"] -= 1
            raise ConnectionError("Remote end closed connection without response")
        return vero(fn)

    monkeypatch.setattr(OM, "call", legge)
    betfair.cancel = cancel_report(tagliato=3.0)
    betfair.current = current_orders(bet_id="B1", matched=2.0, residuo=0.0, prezzo=2.10)
    return stato


def test_rilettura_al_primo_colpo_nessuna_chiamata_in_piu(rete_che_cade):
    ann = OM.cancel_order_live("B1", "1.234")
    assert rete_che_cade["letture"] == 1
    assert ann.riletto is True and ann.abbinato_ignoto is False
    assert ann.size_matched == 2.0


def test_rilettura_di_riserva_recupera_l_abbinato(rete_che_cade):
    rete_che_cade["cadute"] = 1
    ann = OM.cancel_order_live("B1", "1.234")
    assert rete_che_cade["letture"] == 2
    assert ann.riletto is True and ann.abbinato_ignoto is False
    assert ann.size_matched == 2.0 and ann.avg_price_matched == 2.10


def test_se_resta_ignoto_lo_dichiara(rete_che_cade):
    rete_che_cade["cadute"] = 99
    ann = OM.cancel_order_live("B1", "1.234")
    assert rete_che_cade["letture"] == 3, "1 lettura + al massimo 2 di riserva"
    assert ann.riletto is False
    assert ann.abbinato_ignoto is True
    assert ann.size_matched is None and ann.size_remaining is None
