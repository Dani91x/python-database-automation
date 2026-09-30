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


@pytest.fixture
def forma_di_prima():
    """29/09 (piano Mike P5, blocco 5): il valore di serie di ``cover_form`` e'
    diventato ``lay_under45`` (copertura come BANCA Under 4,5). I test scritti per
    la forma di prima (PUNTA Over 4,5) si FISSANO su ``back_over45`` con questa
    fixture: restano a provare che l'interruttore di sicurezza dell'utente
    funziona ancora, con le stesse asserzioni di prima. Elenco nel referto
    ``AUDIT_2026-09-29/MIKE_P5_5.md``."""
    prima = C.DEFAULTS.get("cover_form")
    C.DEFAULTS["cover_form"] = "back_over45"
    try:
        yield
    finally:
        C.DEFAULTS["cover_form"] = prima


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
