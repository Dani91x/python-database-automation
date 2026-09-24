# -*- coding: utf-8 -*-
"""REPERTO D (24/09): `run_scalper_live` e' un avvio manuale da riga di comando
senza riga `scalper_control`, specchio ordini, heartbeat, guardia `avvio_app`,
modalita' paper ne' `VALIDATED_PARAMS`: due copie = ordini reali doppi.

Che cosa si difende (fail-closed):
  1. senza `SCALPER_LIVE_CLI=consentito` `main()` esce con SystemExit PRIMA di
     importare flumine o il client Betfair (qui resi inimportabili: se il
     codice ci arrivasse uscirebbe un ImportError, non il SystemExit);
  2. anche il solo import del modulo non tocca flumine ne' il client;
  3. col consenso si PROSEGUE (fino al client Betfair, qui una sentinella);
  4. col lock di istanza singola occupato si esce, e il client non parte.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import importlib
import socket
import sys
from typing import Any, List

import pytest

import Betfair.stream.auth as AUTH
from Betfair.stream.scalper import run_scalper_live as RSL


class _Sentinella(Exception):
    """Il client Betfair e' stato chiamato: la guardia e' stata superata."""


def _porta_libera() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    porta = int(s.getsockname()[1])
    s.close()
    return porta


@pytest.fixture
def argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_scalper_live", "--market-ids", "1.100"])


@pytest.fixture
def client_sentinella(monkeypatch) -> List[Any]:
    chiamate: List[Any] = []

    def _build_client(*a: Any, **k: Any) -> Any:
        chiamate.append((a, k))
        raise _Sentinella("build_client chiamato")

    monkeypatch.setattr(AUTH, "build_client", _build_client)
    return chiamate


@pytest.mark.parametrize("valore", [None, "", "1", "true", "Consentito", "si"])
def test_senza_consenso_esce_prima_di_flumine_e_del_client(monkeypatch, argv,
                                                           client_sentinella, valore):
    if valore is None:
        monkeypatch.delenv(RSL.CLI_ENV, raising=False)
    else:
        monkeypatch.setenv(RSL.CLI_ENV, valore)
    # flumine e il client INIMPORTABILI: un import prima della guardia
    # darebbe ImportError, non SystemExit
    monkeypatch.setitem(sys.modules, "flumine", None)
    monkeypatch.setitem(sys.modules, "Betfair.stream.auth", None)
    with pytest.raises(SystemExit) as exc:
        RSL.main()
    assert "DISATTIVATO" in str(exc.value)
    assert "solo dalla UI" in str(exc.value)
    assert client_sentinella == []


def test_l_import_del_modulo_non_tocca_flumine_ne_il_client(monkeypatch):
    monkeypatch.setitem(sys.modules, "flumine", None)
    monkeypatch.setitem(sys.modules, "Betfair.stream.auth", None)
    monkeypatch.setitem(sys.modules, "Betfair.stream.scalper.scalper_bot", None)
    mod = importlib.reload(RSL)
    assert callable(mod.main)


def test_col_consenso_prosegue_fino_al_client(monkeypatch, argv, client_sentinella):
    monkeypatch.setenv(RSL.CLI_ENV, " consentito ")
    monkeypatch.setenv(RSL.CLI_LOCK_PORT_ENV, str(_porta_libera()))
    with pytest.raises(_Sentinella):
        RSL.main()
    assert len(client_sentinella) == 1


def test_col_lock_occupato_esce_e_il_client_non_parte(monkeypatch, argv, client_sentinella):
    occupante = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupante.bind(("127.0.0.1", 0))
    occupante.listen(1)
    try:
        monkeypatch.setenv(RSL.CLI_ENV, "consentito")
        monkeypatch.setenv(RSL.CLI_LOCK_PORT_ENV, str(occupante.getsockname()[1]))
        with pytest.raises(SystemExit) as exc:
            RSL.main()
        assert "ISTANZA GIA' ATTIVA" in str(exc.value)
        assert client_sentinella == []
    finally:
        occupante.close()


def test_il_lock_di_default_e_quello_del_supervisore(monkeypatch):
    """Un solo padrone degli ordini dello scalper per PC: la porta di default
    e' la stessa del supervisore (`scalper_service`, 47314)."""
    import inspect

    from Betfair.stream.scalper import scalper_service as SVC

    sorgente = inspect.getsource(SVC)
    assert '"SCALPER_SVC_LOCK_PORT", "47314"' in sorgente
    assert RSL.CLI_LOCK_PORT_ENV == "SCALPER_SVC_LOCK_PORT"
    assert RSL.CLI_LOCK_PORT_DEFAULT == "47314"
