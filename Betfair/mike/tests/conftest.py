"""Ogni test parte da un servizio che non si ricorda niente, e senza cache.

Dal 13/09 il servizio tiene in memoria feed, partite e aggregati per non
massacrare il database (``service.svuota_le_cache``, COSTITUZIONE §17). Sono
variabili di modulo: senza azzerarle un test erediterebbe lo stato del
precedente e gli assert diventerebbero casuali.

E le cache vanno anche SPENTE di default nei test. Quasi tutti simulano piu'
cicli consecutivi nello STESSO istante (`now` costruito a mano), cosa che nella
realta' non succede mai: con le cache accese il secondo giro rileggerebbe la
copia in memoria e il test misurerebbe la cache invece del comportamento che
vuole misurare. Chi vuole provare le cache lo fa apposta, passando i parametri —
vedi ``test_mike_respiro_db_2026_09_13.py``.
"""
from __future__ import annotations

import pytest

from Betfair.mike import config as C
from Betfair.mike import service as S

# i parametri che governano il respiro: nei test valgono zero (nessuna cache)
_CACHE_KEYS = ("feed_cache_s", "events_reload_s", "aggregates_cache_s", "reconcile_every_s")


@pytest.fixture(autouse=True)
def runner():
    """D1 (29/09): in paper Mike passa dal RUNNER (canale di comando). Ogni test
    ha il suo runner finto, che parla il protocollo vero (``runner_finto``)."""
    from Betfair.mike import porta_ordini as MP
    from Betfair.mike.tests.runner_finto import RunnerFinto

    r = RunnerFinto()
    MP.installa(r)
    try:
        yield r
    finally:
        MP.installa(None)


@pytest.fixture(autouse=True)
def _servizio_senza_memoria():
    originali = {k: C.DEFAULTS[k] for k in _CACHE_KEYS if k in C.DEFAULTS}
    for k in originali:
        C.DEFAULTS[k] = 0.0
    S.svuota_le_cache()
    try:
        yield
    finally:
        C.DEFAULTS.update(originali)
        S.svuota_le_cache()
