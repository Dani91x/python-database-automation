"""D1-quater (29/09) - il banco dichiara ANCHE il tetto d'ambiente dei freni.

Reperto: un checkout di prova FUORI dal repo non trova il ``.env`` (``load_dotenv``
risale dalla cartella del modulo), ``LIVE_ORDER_MODE`` vale OFF e ogni apertura
live del replay muore ``live_order_mode_non_live:OFF`` (Mike 35760084: 254 righe
``error``). ``certifica._freni_da_banco`` ora dichiara ``LIVE_ORDER_MODE=LIVE`` e
``LIVE_KILL_SWITCH=false`` per la durata del replay, per tutti i bot.

Qui: (1) senza variabili nell'ambiente il freno live e' aperto come nel checkout
principale; (2) nel checkout principale (``.env`` gia' LIVE) nulla cambia: stesso
freno, stesse variabili dentro e dopo; (3) uno scenario che TIRA il freno lo tira
sopra la dichiarazione; (4) all'uscita, anche su eccezione, le variabili tornano
com'erano (assenti comprese). Le funzioni sono quelle di produzione
(``execution._live_brake``), nessun finto.
"""
from __future__ import annotations

import os

import pytest

from Betfair.safe_strategy import execution as X
from Betfair.stream.backtest import certifica as CE

CHIAVI = ("LIVE_ORDER_MODE", "LIVE_KILL_SWITCH")


def _niente_db(monkeypatch):
    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)


def test_checkout_fuori_dal_repo_freno_aperto_come_nel_principale(monkeypatch):
    _niente_db(monkeypatch)
    for k in CHIAVI:
        monkeypatch.delenv(k, raising=False)
    assert X._live_brake() == "live_order_mode_non_live:OFF"   # il reperto
    with CE._freni_da_banco():
        assert X._live_brake() is None
    for k in CHIAVI:
        assert k not in os.environ, f"{k} lasciata nell'ambiente dopo il replay"


def test_checkout_principale_nulla_cambia(monkeypatch):
    _niente_db(monkeypatch)
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    prima = {k: os.environ[k] for k in CHIAVI}
    with CE._freni_da_banco():
        assert X._live_brake() is None
        assert {k: os.environ[k] for k in CHIAVI} == prima
    assert {k: os.environ[k] for k in CHIAVI} == prima


def test_lo_scenario_del_freno_lo_tira_sopra_la_dichiarazione(monkeypatch):
    _niente_db(monkeypatch)
    for k in CHIAVI:
        monkeypatch.delenv(k, raising=False)
    with CE._freni_da_banco():
        os.environ["LIVE_KILL_SWITCH"] = "true"       # come trasporto_rapido (R7)
        try:
            assert X._live_brake() is not None
        finally:
            os.environ["LIVE_KILL_SWITCH"] = "false"
        assert X._live_brake() is None
    assert "LIVE_KILL_SWITCH" not in os.environ


def test_ripristino_anche_su_eccezione(monkeypatch):
    _niente_db(monkeypatch)
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    monkeypatch.delenv("LIVE_KILL_SWITCH", raising=False)
    with pytest.raises(RuntimeError):
        with CE._freni_da_banco():
            assert os.environ["LIVE_ORDER_MODE"] == "LIVE"
            raise RuntimeError("replay caduto")
    assert os.environ["LIVE_ORDER_MODE"] == "PAPER"
    assert "LIVE_KILL_SWITCH" not in os.environ
