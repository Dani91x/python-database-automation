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


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "cert: certificazione sul banco comune (replay flumine su registrazioni reali)",
    )
