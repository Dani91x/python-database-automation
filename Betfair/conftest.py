# -*- coding: utf-8 -*-
"""Marcatori della suite Betfair.

``cert`` — i test che fanno girare il BANCO COMUNE (replay flumine sulle
registrazioni reali) su un campione ridotto, per ogni bot registrato. Stanno
nella suite di default proprio perche' una modifica a un bot deve rilanciare la
sua certificazione senza che nessuno se lo ricordi; per isolarli:

    python -m pytest Betfair/ -q -m cert          # solo la certificazione
    python -m pytest Betfair/ -q -m "not cert"    # tutto il resto
"""
from __future__ import annotations

import sys

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "cert: certificazione sul banco comune (replay flumine su registrazioni reali)",
    )


@pytest.fixture(autouse=True)
def _ripristina_flumine_config():
    """R-4 (25/09, ``AUDIT_2026-09-25/TENNIS_UNIFICAZIONE_E_SAFE_CANALE.md``):
    ``flumine.config`` e' un MODULO, cioe' uno stato GLOBALE DI PROCESSO — non per
    istanza — e diversi punti di produzione ci scrivono direttamente senza mai
    ripristinare (perche' in produzione non serve: un solo bot, una sola modalita',
    per tutta la vita del processo):

        Betfair/stream/tennis_live/tennis_runner.py:159   build_order_client(PAPER)
            imposta ``flumine_config.place_latency = TENNIS_PAPER_LATENCY_MS/1000``
            (default 600 ms).
        Betfair/stream/tennis_live/guardie_tennis.py:178  stessa scrittura, stesso
            campo, dalle guardie a caldo.
        Betfair/stream/runner.py:1537 e :1580              lo stesso per il runner
            calcio (PAPER_SIMULATED_LATENCY_MS).

    Un test che fa girare questo codice di produzione (es.
    ``Betfair/stream/tennis_live/tests/test_tennis_iscrizione_a_caldo_2026_09_25.py``)
    lascia ``place_latency = 0.6`` per TUTTO il processo pytest. Il test successivo
    che si aspetta il default di flumine (0.12) — es.
    ``Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py::
    test_profilo_rapido_verde_sulla_registrazione_vera[omega]``, che passa dal
    profilo rapido del banco comune e confronta i tempi attesi contro
    ``place_latency + betDelay`` — vede una latenza diversa da quella con cui e'
    stato scritto e cade. Da solo e' verde perche' nessuno ha ancora toccato
    ``flumine.config`` in quella sessione.

    Riprodotto a comando (falsificato disattivando questa fixture, vedi
    ``AUDIT_2026-09-25/FIX_R4_STATO_GLOBALE_TEST.md``):

        python -m pytest \
          Betfair/stream/tennis_live/tests/test_tennis_iscrizione_a_caldo_2026_09_25.py \
          "Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py::test_profilo_rapido_verde_sulla_registrazione_vera[omega]" \
          -q -p no:cacheprovider

    Fotografa TUTTI gli attributi pubblici di ``flumine.config`` prima di ogni test
    e li ripristina dopo: nessun test — tennis, calcio o altro — puo' piu' sporcare
    quello che gira dopo di lui nella stessa sessione pytest. Scritture dirette su
    ``flumine.config`` (come quelle sopra) NON passano da ``monkeypatch`` — restano
    finche' qualcosa non le tocca di nuovo — quindi solo uno snapshot/ripristino
    esplicito del modulo le neutralizza."""
    import flumine.config as _fconf

    _prima = {
        _nome: getattr(_fconf, _nome)
        for _nome in vars(_fconf)
        if not _nome.startswith("__")
    }
    yield
    for _nome, _valore in _prima.items():
        setattr(_fconf, _nome, _valore)


@pytest.fixture(autouse=True)
def _kill_switch_del_db_senza_rete(monkeypatch):
    """O1 (24/09): ``controls.motivo_kill_switch`` legge anche
    ``betfair_live_settings`` (RPC, cache 2 s). Nei test la rete non c'e'
    (SUPABASE_URL finto): senza questo ogni apertura REST pagherebbe ~2 s di
    connessione rifiutata. Lo snapshot resta quello "mai letto" ({}), cioe'
    esattamente cio' che il codice vedrebbe con il DB irraggiungibile; chi
    collauda il freno del DB lo imposta da se' (monkeypatch di
    ``get_live_settings`` o della cache). Non importa ``controls`` se nessuno
    l'ha gia' importato: nessun modulo pesante entra per colpa di questo."""
    ctl = sys.modules.get("Betfair.stream.trading.controls")
    if ctl is not None and hasattr(ctl, "_SETTINGS_CACHE"):
        monkeypatch.setitem(ctl._SETTINGS_CACHE, "data", {})
        monkeypatch.setitem(ctl._SETTINGS_CACHE, "ts", float("inf"))
    yield
