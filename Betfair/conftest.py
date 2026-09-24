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
