"""FIX CRITICAL doppio runner — tennis_bot_service.run() e lock di singola istanza.

L'app desktop avvia SIA il watchdog (→ tennis_runner) SIA tennis_bot_service:
senza lock entrambi ospitavano gli stessi bot (stake DOPPIO). Ora run() acquisisce
il lock del runner PRIMA di setup_and_run(): porta occupata → solo ensure-follows.
"""
from __future__ import annotations

import types

from Betfair.stream.tennis_live import tennis_bot_service as svc
from Betfair.stream.tennis_live import tennis_runner


def test_run_skips_hosting_when_lock_busy(monkeypatch):
    calls = {"ensure": 0, "setup": 0}
    monkeypatch.setattr(
        svc, "ensure_follows_for_bots",
        lambda: calls.__setitem__("ensure", calls["ensure"] + 1) or [])

    def _busy(port, name):  # noqa: ARG001 - firma di acquire_single_instance_lock
        raise SystemExit("istanza gia' attiva")
    monkeypatch.setattr(svc, "acquire_single_instance_lock", _busy)
    monkeypatch.setattr(
        tennis_runner, "setup_and_run",
        lambda *a, **k: calls.__setitem__("setup", calls["setup"] + 1))

    svc.run()

    assert calls["ensure"] == 1   # il ponte follow lavora comunque
    assert calls["setup"] == 0    # runner gia' attivo: NESSUN secondo hosting


def test_run_hosts_and_releases_lock_when_free(monkeypatch):
    calls = {"setup": 0}
    closed = []
    monkeypatch.setattr(svc, "ensure_follows_for_bots", lambda: [])
    lock = types.SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(svc, "acquire_single_instance_lock",
                        lambda port, name: lock)
    monkeypatch.setattr(
        tennis_runner, "setup_and_run",
        lambda *a, **k: calls.__setitem__("setup", calls["setup"] + 1))

    svc.run()

    assert calls["setup"] == 1
    assert closed == [True]       # lock rilasciato quando l'hosting termina


def test_run_releases_lock_even_on_runner_crash(monkeypatch):
    closed = []
    monkeypatch.setattr(svc, "ensure_follows_for_bots", lambda: [])
    lock = types.SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(svc, "acquire_single_instance_lock",
                        lambda port, name: lock)

    def _boom(*a, **k):
        raise RuntimeError("runner caduto")
    monkeypatch.setattr(tennis_runner, "setup_and_run", _boom)

    try:
        svc.run()
    except RuntimeError:
        pass

    assert closed == [True]       # mai un lock orfano che blocca il watchdog
