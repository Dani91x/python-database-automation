"""08/10/2026 (controllo finale) - il banco riparte, a ogni scenario, con la
memoria W3a del conto di un processo NUOVO, per Mike, Omega e Safe.

Reperto del controllo finale: con `certifica --worker 1` gli scenari girano
nello stesso processo; la memoria «di chi e' questo ordine»
(`SorveglianzaConto.proprietari`) e le selezioni in verifica passavano allo
scenario dopo e, siccome il finto Betfair rida' gli STESSI bet_id in ogni
scenario, il secondo non chiedeva piu' i proprietari (Mike 35760084
`ridotto-fuori-app`: nota `proprietari_bot_conto` presente con `--worker 3`,
assente con `--worker 1`). Safe in piu': l'avviso «scanner che non dichiara il
flusso» (una volta per processo) e la cache dei lambda a orologio di parete
(reperto D-13). Solo banco: il servizio di produzione non cambia.
"""
from __future__ import annotations

import os

from Betfair.mike import service as MS
from Betfair.mike.tools import replay_registrazioni as MR
from Betfair.omega import omega_service as OS
from Betfair.omega.tools import replay_registrazioni as OR
from Betfair.safe_strategy import bot_service as BS
from Betfair.safe_strategy.tools import replay_registrazioni as SR
from Betfair.stream import flusso_prezzi as FP


def _sporca(conto) -> None:
    conto.proprietari._esiti[("live", "100000000001")] = "ref:altro-bot"
    conto.proprietari._errori[("live", "100000000002")] = ("db giu'", 1.0)
    conto.verifica["35760084"] = {"OU35|UNDER": {"verdetto": "in_verifica"}}


def _pulita(conto) -> bool:
    st = conto.proprietari.stato()
    return st["esiti"] == 0 and st["errori"] == 0 and not conto.verifica


def test_mike_ogni_scenario_riparte_con_la_memoria_del_conto_vuota(tmp_path):
    _sporca(MS._CONTO)
    ref = MR._certifica_evento("99999999", data_dir=str(tmp_path))   # registrazione assente
    assert any("registrazione assente" in n for n in ref.note)
    assert _pulita(MS._CONTO)


def test_omega_processo_nuovo_svuota_la_memoria_del_conto():
    _sporca(OS._CONTO)
    OR._processo_nuovo()
    assert _pulita(OS._CONTO)


def test_safe_ogni_scenario_riparte_pulito(tmp_path):
    _sporca(BS._CONTO)
    FP._NON_NOTO_AVVISATO.add("safe")
    OS._LAMBDA_CACHE["99999999"] = ((1.2, 1.1, None, "fixture"), 0.0)
    ref = SR._certifica_evento("99999999", data_dir=str(tmp_path))
    assert any("registrazione assente" in n for n in ref.note)
    assert _pulita(BS._CONTO)
    assert "safe" not in FP._NON_NOTO_AVVISATO
    assert "99999999" not in OS._LAMBDA_CACHE
    assert not os.listdir(tmp_path)          # il banco non scrive nella cartella dati
