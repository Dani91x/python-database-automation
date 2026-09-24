# -*- coding: utf-8 -*-
"""Ambiente dei test della Safe Strategy.

CERT. 13/09 — i FRENI GLOBALI del live (``LIVE_ORDER_MODE``, ``LIVE_KILL_SWITCH``)
valgono adesso anche per il percorso REST della Safe Strategy
(``execution._live_brake``). Senza questo file i test che esercitano la via live
erediterebbero il ``.env`` della macchina — dove oggi c'e' ``LIVE_ORDER_MODE=PAPER``
— e verrebbero fermati dal freno, misurando la configurazione dello sviluppatore
invece del codice.

Qui l'ambiente e' DICHIARATO: freni aperti per difetto, cosi' i test della via
live esercitano davvero il place. I test che verificano i freni li richiudono a
mano con ``monkeypatch`` (vedi ``test_execution.py``).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def freni_live_aperti(monkeypatch):
    # 24/09: il modo ordini e' anche una riga di controllo (scelta dalla Control
    # Room, ``Betfair/stream/modo_ordini.py``): la si dichiara in memoria come
    # il tetto dell'ambiente, mai letta da un DB.
    from Betfair.stream import modo_ordini as _mo

    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    # F5 (24/09): la porta a comandi e' SPENTA per difetto anche nei test, qualunque
    # cosa dica il .env della macchina; chi la prova la accende a mano.
    monkeypatch.delenv("SAFE_ORDINI_VIA_CANALE", raising=False)
    monkeypatch.delenv("SAFE_TENNIS_ORDINI_VIA_CANALE", raising=False)
    with _mo.dichiara_per_banco("LIVE"):
        yield


@pytest.fixture(autouse=True)
def indice_eventi_chiusi_pulito():
    """Ogni test parte come un servizio APPENA AVVIATO.

    ``bot_service._EVENTI_CHIUSI`` e' la cache di processo del marcatore
    «partita chiusa dall'utente» (la fonte di verita' sono le righe:
    ``meta.chiuso_dall_utente``). In produzione la RICOSTRUISCE
    ``build_risk_ctx`` a ogni ciclo dalle posizioni vive appena lette; in un
    test che chiama una singola funzione quel ciclo non gira, e la cache si
    porterebbe dietro la partita chiusa dal test precedente. Lo stesso vale per
    ``_CONTO_LETTO_A`` (cadenza della lettura di conto).
    """
    from Betfair.safe_strategy import bot_service as _S

    _S._EVENTI_CHIUSI.clear()
    _S._CONTO_LETTO_A.clear()
    yield
    _S._EVENTI_CHIUSI.clear()
    _S._CONTO_LETTO_A.clear()
