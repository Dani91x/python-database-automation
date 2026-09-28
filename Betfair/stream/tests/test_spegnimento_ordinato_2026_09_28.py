"""CANTIERE K (28/09) - watchdog.py, parte residua dopo il riallineamento
con arresto_ordinato.py (cantiere A, su master).

L'arresto ORDINATO dell'app non passa piu' dal watchdog: ogni figlio
(runner calcio/tennis, servizi bot, ponte tennis, scalper-service) legge da
SOLO il file condiviso ``Betfair/stream/arresto_ordinato.py`` ed esce con 0
(vedi i rispettivi moduli e ``test_arresto_ordinato_servizi_bot_2026_09_28.py``);
il watchdog vede semplicemente un rc=0 e non rilancia — comportamento GIA'
esistente di ``classify_exit`` (0 = 'clean'), zero righe nuove qui.

Quello che RESTA di competenza del watchdog (SPEC_WATCHDOG_SCALPER_PONTE_
2026-09-26.md §5): con scalper-service e ponte tennis ora sotto watchdog
(28/09), il battito condiviso (``betfair_live_heartbeat.watchdog_ts/pid``)
smetterebbe di dire qualcosa sul watchdog del runner di default se OGNI
istanza lo scrivesse — qui si prova che lo scrive SOLO lui, salvo override.
"""
from __future__ import annotations

from typing import Any

import pytest

import Betfair.stream.watchdog as wd
from Betfair.stream.tests.test_watchdog import _run


class TestDeveScrivereBattito:
    def test_default_solo_target_di_default(self):
        assert wd.deve_scrivere_battito("Betfair.stream.runner") is True
        assert wd.deve_scrivere_battito("Betfair.stream.scalper.scalper_service") is False
        assert wd.deve_scrivere_battito("Betfair.stream.tennis_live.tennis_bot_service") is False
        assert wd.deve_scrivere_battito("Betfair.omega.omega_service") is False
        assert wd.deve_scrivere_battito("Betfair.mike.service") is False
        assert wd.deve_scrivere_battito("Betfair.safe_strategy.service") is False
        assert wd.deve_scrivere_battito("Betfair.safe_strategy.bot_service") is False

    @pytest.mark.parametrize("val", ["1", "true", "True", "si", "on", "yes"])
    def test_override_acceso(self, val):
        assert wd.deve_scrivere_battito("Betfair.omega.omega_service", val) is True

    @pytest.mark.parametrize("val", ["0", "false", "False", "no", "off"])
    def test_override_spento(self, val):
        assert wd.deve_scrivere_battito("Betfair.stream.runner", val) is False

    def test_override_illeggibile_lascia_il_default(self):
        assert wd.deve_scrivere_battito("Betfair.stream.runner", "boh") is True
        assert wd.deve_scrivere_battito("Betfair.omega.omega_service", "boh") is False


def test_battito_spento_per_target_non_default_durante_esecuzione_normale(monkeypatch: Any):
    rc, _a, _t, heartbeats, _popen, _c = _run(
        monkeypatch, spawns=[[None, 0]], hb_sec=30.0,
        argv=["--", "Betfair.omega.omega_service"],
    )
    assert rc == 0
    assert heartbeats == [], "il battito non e' del runner di default: non si scrive"


def test_battito_acceso_per_il_target_di_default(monkeypatch: Any):
    rc, _a, _t, heartbeats, _popen, _c = _run(
        monkeypatch, spawns=[[None, 0]], hb_sec=30.0,
    )
    assert rc == 0
    assert len(heartbeats) >= 1, "il target di default scrive il battito come sempre"


def test_battito_override_accende_anche_per_target_non_default(monkeypatch: Any):
    monkeypatch.setenv("WATCHDOG_BATTITO", "1")
    rc, _a, _t, heartbeats, _popen, _c = _run(
        monkeypatch, spawns=[[None, 0]], hb_sec=30.0,
        argv=["--", "Betfair.omega.omega_service"],
    )
    assert rc == 0
    assert len(heartbeats) >= 1


def test_battito_override_spegne_anche_per_il_target_di_default(monkeypatch: Any):
    monkeypatch.setenv("WATCHDOG_BATTITO", "0")
    rc, _a, _t, heartbeats, _popen, _c = _run(
        monkeypatch, spawns=[[None, 0]], hb_sec=30.0,
    )
    assert rc == 0
    assert heartbeats == []
