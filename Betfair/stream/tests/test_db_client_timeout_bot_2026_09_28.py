"""D1 (28/09) - timeout PostgREST del profilo BOT in ``db_client``.

Il default della libreria (120 s su connessione, lettura e scrittura) teneva
appeso un giro di Safe o Mike per minuti con la rete «a buco nero». Il profilo
bot (connessione 5 s, lettura 20 s) si accende SOLO nel processo del bot
(``usa_timeout_bot`` dal suo ``main``); tutti gli altri processi (runner,
backfill, action) tengono il default, perche' alcune loro RPC alzano il limite
del server a 60-600 s.

Il client e' quello VERO di ``supabase`` (``create_client``) con URL e chiave
finti: creare il client non apre connessioni, e il test legge il timeout dal
``httpx.Client`` che PostgREST usera' davvero (``client.postgrest.session``).
"""
from __future__ import annotations

import threading

import httpx
import pytest

import db_client


@pytest.fixture(autouse=True)
def _client_pulito(monkeypatch):
    monkeypatch.setattr(db_client, "SUPABASE_URL", "https://esempio.supabase.co")
    monkeypatch.setattr(db_client, "SUPABASE_SERVICE_ROLE_KEY", "x" * 40)
    monkeypatch.setattr(db_client, "_TLS", threading.local())
    monkeypatch.setattr(db_client, "_STATO", {"timeout": None})
    monkeypatch.delenv("SUPABASE_BOT_CONNECT_S", raising=False)
    monkeypatch.delenv("SUPABASE_BOT_LETTURA_S", raising=False)


def _timeout(client) -> httpx.Timeout:
    return client.postgrest.session.timeout


def test_il_default_resta_quello_di_sempre_per_tutti_gli_altri_processi():
    assert _timeout(db_client.get_supabase_client()) == httpx.Timeout(120)
    assert db_client.timeout_corrente() is None


def test_il_profilo_bot_arriva_al_client_httpx_di_postgrest():
    db_client.usa_timeout_bot()
    t = _timeout(db_client.get_supabase_client())
    assert (t.connect, t.read, t.write, t.pool) == (5.0, 20.0, 20.0, 5.0)


def test_il_client_gia_creato_nel_thread_viene_sostituito():
    prima = db_client.get_supabase_client()
    db_client.usa_timeout_bot()
    dopo = db_client.get_supabase_client()
    assert dopo is not prima
    assert _timeout(dopo).read == 20.0
    assert db_client.get_supabase_client() is dopo, "poi si riusa (un client per thread)"


def test_vale_per_ogni_thread_del_processo():
    db_client.usa_timeout_bot()
    visti = []
    th = threading.Thread(target=lambda: visti.append(_timeout(db_client.get_supabase_client())))
    th.start()
    th.join()
    assert visti[0].read == 20.0 and visti[0].connect == 5.0


@pytest.mark.parametrize("valore,atteso", [("12", 12.0), ("", 20.0), ("abc", 20.0),
                                           ("0", 20.0), ("-3", 20.0)])
def test_override_da_ambiente_mai_zero(monkeypatch, valore, atteso):
    monkeypatch.setenv("SUPABASE_BOT_LETTURA_S", valore)
    assert db_client.timeout_bot().read == atteso


def test_resta_sotto_il_default_e_sopra_il_tetto_del_server():
    """Il server uccide ogni query oltre 8 s (``authenticator``): la lettura
    del profilo deve lasciare margine sopra 8 s e stare sotto i 120 s."""
    t = db_client.timeout_bot()
    assert 8.0 * 2 <= t.read < 120.0
    assert t.connect < t.read
