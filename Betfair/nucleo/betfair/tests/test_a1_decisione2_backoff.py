"""W1-A1 - decisione 2 dell'utente (10/10/2026): "sempre una sola connessione".

Anche ``segnala_errore`` (errore di sessione visto dallo stream) RISPETTA il
backoff del custode dopo un login fallito, come ``rifai_login``: l'errore e'
preso in carico (sessione segnata da rifare) e il relogin parte alla FINE
dell'attesa, mai prima. Fuori dal backoff resta come oggi (giro anticipato ad
adesso, ``auth.py:214-224``).

Client VERO (``auth.build_client``) sul trasporto HTTP finto, orologio finto
condiviso (``test_a1_finto_betfair``). Falsificazione: mutazioni D2a..D2d in
``ARCHITETTURA_2026-10/ondata1/W1-A1/mutazioni_a1.py``.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import threading

import pytest
from betfairlightweight.exceptions import APIError

from Betfair.nucleo.betfair import sessione as S
from Betfair.nucleo.betfair.tests.test_a1_finto_betfair import (
    OrologioFinto,
    ServerBetfairFinto,
    installa_finto,
)

#: primo gradino del backoff del custode di oggi (``auth._RITENTI_DEFAULT_S``)
ATTESA_S = 15.0


@pytest.fixture
def finto(monkeypatch):
    server = ServerBetfairFinto(OrologioFinto())
    installa_finto(monkeypatch, server)
    yield server
    S.chiudi_sessione_del_processo()


def _errore_sessione() -> APIError:
    return APIError({"error": {"code": -32099, "data": {"APINGException": {
        "errorCode": "INVALID_SESSION_INFORMATION"}}}}, method="SportsAPING/v1.0/listMarketBook")


def _sessione_in_backoff_dopo_login_fallito(server: ServerBetfairFinto) -> S.SessioneBetfair:
    """Sessione loggata, poi sessione morta e UN login rifiutato: backoff di 15 s."""
    s = S.SessioneBetfair(ora=server.ora)
    s.client()
    server.invalida_tutti()
    server.guasta("login", "INVALID_USERNAME_OR_PASSWORD")
    # fuori dal backoff: segnala_errore anticipa il giro ad adesso (come oggi)
    assert s.segnala_errore(_errore_sessione()) is True
    assert s.rinnova() == "ko"
    assert s.in_backoff() is True
    assert server.conta("login") == 2            # il primo riuscito, il secondo rifiutato
    return s


def test_cinque_thread_segnalano_durante_il_backoff_zero_login_prima_uno_dopo(finto):
    s = _sessione_in_backoff_dopo_login_fallito(finto)
    login_prima = finto.conta("login")
    generazione = s.generazione
    barriera = threading.Barrier(5)
    presi: list = []
    giri: list = []

    def _stream():
        barriera.wait()
        presi.append(s.segnala_errore(_errore_sessione()))
        giri.append(s.rinnova())                # il giro del custode s'intreccia con le segnalazioni

    fili = [threading.Thread(target=_stream) for _ in range(5)]
    for f in fili:
        f.start()
    for f in fili:
        f.join(10)
    assert presi == [True] * 5                  # ogni errore preso in carico
    assert giri == [None] * 5                   # nessun giro anticipato
    # giri del custode lungo l'attesa: nessun login prima della fine
    for passo in (0.0, 5.0, 9.9):
        finto.ora.avanza(passo)
        assert s.rinnova() is None
        assert finto.conta("login") == login_prima, "login partito durante il backoff"
    assert s.in_backoff() is True
    finto.ora.avanza(ATTESA_S - 14.9)            # fine dell'attesa (15 s dal fallimento)
    assert s.in_backoff() is False
    assert s.rinnova() == "relogin"
    assert finto.conta("login") == login_prima + 1      # UNO solo, a fine attesa
    assert s.generazione == generazione + 1
    # dopo il relogin altri giri non rifanno nulla
    for _ in range(5):
        assert s.rinnova() is None
    assert finto.conta("login") == login_prima + 1


def test_segnalazione_nel_backoff_dopo_un_keepalive_caduto_porta_al_login_non_al_keepalive(finto):
    """Presa in carico: il backoff nasce da un keepAlive caduto per rete (sessione ancora
    buona per il custode). Una segnalazione di sessione durante l'attesa la segna da
    rifare: a fine attesa il custode fa il LOGIN, non il keepAlive."""
    s = S.SessioneBetfair(ora=finto.ora, periodo_keepalive_s=480.0)
    s.client()
    finto.ora.avanza(480)
    finto.guasta("keepAlive", "rete")
    assert s.rinnova() == "ko" and s.in_backoff() is True
    n_login, n_ka = finto.conta("login"), finto.conta("keepAlive")
    assert s.segnala_errore(_errore_sessione()) is True
    assert s.rinnova() is None and finto.conta("login") == n_login
    assert s.stato()["custode"]["sessione_da_rifare"] is True
    finto.ora.avanza(ATTESA_S)
    assert s.rinnova() == "relogin"
    assert (finto.conta("login"), finto.conta("keepAlive")) == (n_login + 1, n_ka)


def test_errore_non_di_sessione_nel_backoff_non_e_preso_in_carico(finto):
    s = S.SessioneBetfair(ora=finto.ora, periodo_keepalive_s=480.0)
    s.client()
    finto.ora.avanza(480)
    finto.guasta("keepAlive", "rete")
    assert s.rinnova() == "ko" and s.in_backoff() is True
    rete = APIError(None, exception=ConnectionError("x"))
    assert s.segnala_errore(rete) is False
    assert s.stato()["custode"]["sessione_da_rifare"] is False
    finto.ora.avanza(ATTESA_S)
    n_login = finto.conta("login")
    assert s.rinnova() == "ok" and finto.conta("login") == n_login     # keepAlive, nessun login


def test_fuori_dal_backoff_segnala_anticipa_ad_adesso_come_oggi(finto):
    s = S.SessioneBetfair(ora=finto.ora, periodo_keepalive_s=480.0)
    s.client()
    finto.ora.avanza(10)
    assert s.in_backoff() is False
    assert s.rinnova() is None                       # non e' ora (480 s)
    assert s.segnala_errore(_errore_sessione()) is True
    assert s.rinnova() == "relogin" and finto.conta("login") == 2


def test_segnala_prima_del_primo_login_non_fa_nulla(finto):
    s = S.SessioneBetfair(ora=finto.ora)
    assert s.segnala_errore(_errore_sessione()) is False
    assert finto.richieste == []
