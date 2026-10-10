"""W1-A1 - decisione 2: le prove della revisione indipendente di 2d38504f (riscritte qui).

Casi che ``test_a1_decisione2_backoff`` non copre:
* 5 thread che segnalano e fanno girare il custode IN CORSA mentre l'orologio
  avanza a passi di 1 s: nessun login durante i 15 s, UN relogin dopo;
* fuori dal backoff ``segnala_errore`` lascia il custode nello STESSO stato
  interno del custode di oggi (``auth.CustodeSessione.segnala_errore``,
  ``auth.py:214-224``), per un errore di sessione e per uno di rete;
* ``segnala_errore`` prende il lucchetto del custode: con un keepAlive in volo
  ASPETTA che torni (misurati ~0,4 s col keepAlive lento 0,5 s). La prova e' sulla
  proprieta' (nessun keepAlive in volo quando ritorna), non sul tempo: e' la
  mutazione R7 (``segnala_errore`` senza lucchetto) che la fa diventare rossa.

Attese deterministiche (``_attendi`` su una condizione), mai sleep fissi prima di
un'asserzione su un altro thread.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

import pytest
from betfairlightweight.exceptions import APIError

from Betfair.nucleo.betfair import sessione as S
from Betfair.nucleo.betfair.tests.test_a1_decisione2_backoff import (
    _errore_sessione,
    _sessione_in_backoff_dopo_login_fallito,
)
from Betfair.nucleo.betfair.tests.test_a1_finto_betfair import (
    OrologioFinto,
    ServerBetfairFinto,
    installa_finto,
)


@pytest.fixture
def finto(monkeypatch):
    server = ServerBetfairFinto(OrologioFinto())
    installa_finto(monkeypatch, server)
    yield server
    S.chiudi_sessione_del_processo()


def _attendi(cond: Callable[[], bool], secondi: float = 10.0) -> bool:
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.005)
    return bool(cond())


@pytest.mark.parametrize("giro", range(3))
def test_cinque_thread_in_corsa_mentre_l_orologio_avanza(finto, giro):
    s = _sessione_in_backoff_dopo_login_fallito(finto)
    base = finto.conta("login")
    fermi = threading.Event()
    esiti: list = []
    barriera = threading.Barrier(6)
    presi: list = []

    def _stream_e_custode():
        barriera.wait()
        presi.append(s.segnala_errore(_errore_sessione()))
        while not fermi.is_set():
            r = s.rinnova()
            if r is not None:
                esiti.append(r)
            time.sleep(0.001)

    fili = [threading.Thread(target=_stream_e_custode) for _ in range(5)]
    for f in fili:
        f.start()
    barriera.wait()
    try:
        assert _attendi(lambda: len(presi) == 5)
        assert presi == [True] * 5
        for passo in range(14):                       # 14 s dei 15 di attesa, a passi di 1 s
            finto.ora.avanza(1.0)
            assert finto.conta("login") == base, "login durante l'attesa (t=+%d s)" % (passo + 1)
        finto.ora.avanza(2.0)                         # oltre i 15 s
        assert _attendi(lambda: finto.conta("login") == base + 1), "nessun relogin a fine attesa"
        assert _attendi(lambda: esiti == ["relogin"])
    finally:
        fermi.set()
        for f in fili:
            f.join(10)
    assert finto.conta("login") == base + 1 and esiti == ["relogin"]


def test_fuori_dal_backoff_stato_interno_identico_al_custode_di_oggi(finto):
    nuova = S.SessioneBetfair(ora=finto.ora, periodo_keepalive_s=480.0)
    oggi = S.SessioneBetfair(ora=finto.ora, periodo_keepalive_s=480.0)
    nuova.client()
    oggi.client()
    finto.ora.avanza(100)
    for exc in (_errore_sessione(), APIError(None, exception=ConnectionError("x"))):
        assert nuova.segnala_errore(exc) == oggi._custode.segnala_errore(exc)   # auth.py:214-224
        c1, c2 = nuova._custode, oggi._custode
        assert (c1._sessione_morta, c1._prossimo) == (c2._sessione_morta, c2._prossimo)
    assert nuova.rinnova() == oggi.rinnova() == "relogin"
    assert finto.conta("login") == 4


def test_segnala_errore_aspetta_il_keepalive_in_volo(finto):
    """Contratto d'uso per il thread dello stream: ``segnala_errore`` puo' aspettare un
    keepAlive o un login gia' in volo (lucchetto del custode)."""
    s = S.SessioneBetfair(ora=finto.ora, periodo_keepalive_s=480.0)
    s.client()
    finto.ora.avanza(500)
    finto.ritardo_s["keepAlive"] = 0.5
    t = threading.Thread(target=s.rinnova)
    t.start()
    try:
        assert _attendi(lambda: finto.in_volo["keepAlive"] == 1), "keepAlive mai partito"
        t0 = time.monotonic()
        assert s.segnala_errore(_errore_sessione()) is True
        atteso = time.monotonic() - t0
        assert finto.in_volo["keepAlive"] == 0, "segnala_errore e' tornato col keepAlive in volo"
        print("segnala_errore ha atteso %.2f s il keepAlive in volo" % atteso)
    finally:
        t.join(5)
    assert s.rinnova() == "relogin"                  # presa in carico dopo il keepAlive riuscito
