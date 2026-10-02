# -*- coding: utf-8 -*-
"""Plugin pytest minimo (02/10): rimescola l'ordine dei test raccolti.

pytest-randomly e pytest-reverse NON sono installati nel .venv; questo plugin
fa la stessa cosa senza installare nulla. Si carica con
``-p ordine_test_plugin`` e ``PYTHONPATH=AUDIT_2026-10-02``.

    ORDINE_TEST=inverso      -> ordine inverso
    ORDINE_TEST=casuale:<n>  -> rimescolamento con seme <n> (riproducibile)
    (assente)                -> ordine di pytest, invariato
"""
from __future__ import annotations

import os
import random


def pytest_collection_modifyitems(session, config, items):
    modo = (os.getenv("ORDINE_TEST") or "").strip()
    if not modo:
        return
    if modo == "inverso":
        items.reverse()
    elif modo.startswith("casuale:"):
        random.Random(int(modo.split(":", 1)[1])).shuffle(items)
    else:
        raise ValueError(f"ORDINE_TEST sconosciuto: {modo!r}")


def pytest_report_header(config):
    return f"ordine_test_plugin: ORDINE_TEST={os.getenv('ORDINE_TEST') or '(pytest)'}"
