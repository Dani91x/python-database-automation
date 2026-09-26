"""26/09 - l'alert/Telegram di crash del watchdog dice QUALE modulo e' caduto.

Reperto del coordinatore: «RUNNER CRASHATO: exit code 1, uptime 611s» (alert
510, runner tennis 15:04:20Z) non nominava il processo; sotto watchdog girano
runner calcio, runner tennis e quattro servizi. Stessi finti di test_watchdog
(nessun processo reale, nessuna rete).
"""
from __future__ import annotations

from typing import Any

import Betfair.stream.watchdog as wd
from Betfair.stream.tests.test_watchdog import _run


def test_messaggio_crash_puro_nomina_il_modulo() -> None:
    msg = wd.messaggio_crash("Betfair.stream.tennis_live.tennis_runner", 1, 611.4)
    assert msg == ("RUNNER CRASHATO [Betfair.stream.tennis_live.tennis_runner]: "
                   "exit code 1, uptime 611s.")


def test_alert_e_telegram_di_crash_nominano_il_tennis(monkeypatch: Any) -> None:
    rc, alerts, telegrams, _hb, _popen, _clock = _run(
        monkeypatch, spawns=[[None, None, 1], [0]], hb_sec=30.0,
        argv=["--", "Betfair.stream.tennis_live.tennis_runner"],
    )
    assert rc == 0
    critici = [m for lv, m in alerts if lv == "CRITICAL"]
    assert len(critici) == 1
    assert "[Betfair.stream.tennis_live.tennis_runner]" in critici[0]
    assert "exit code 1" in critici[0]
    assert len(telegrams) == 1
    assert "[Betfair.stream.tennis_live.tennis_runner]" in telegrams[0]


def test_default_nomina_il_runner_calcio(monkeypatch: Any) -> None:
    _rc, alerts, telegrams, _hb, _popen, _clock = _run(
        monkeypatch, spawns=[[2], [0]], grace=0.0)
    critici = [m for lv, m in alerts if lv == "CRITICAL"]
    assert "[Betfair.stream.runner]" in critici[0]
    assert "[Betfair.stream.runner]" in telegrams[0]


def test_tetto_riavvii_nomina_il_modulo(monkeypatch: Any) -> None:
    _rc, alerts, telegrams, _hb, _popen, _clock = _run(
        monkeypatch, spawns=[[2], [2]], grace=0.0, max_per_hour=1,
        argv=["--", "Betfair.safe_strategy.service"],
    )
    manuali = [m for lv, m in alerts if lv == "CRITICAL" and "MANUALE" in m]
    assert manuali and "[Betfair.safe_strategy.service]" in manuali[0]
    assert any("[Betfair.safe_strategy.service]" in t and "MANUALE" in t for t in telegrams)
