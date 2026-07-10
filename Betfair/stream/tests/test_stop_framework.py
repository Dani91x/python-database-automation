"""BUG FIX cert PAPER 10/07: _stop_framework deve accodare un TerminationEvent.

flumine 2.13.11: ``Flumine.run()`` è ``while True: event = handler_queue.get()``
e esce SOLO estraendo un TERMINATOR — ``_running=False`` non è mai testato nel
loop. Senza il TerminationEvent, resubscribe/auto-spegnimento/daily-stop NON
fermavano il runner calcio a stream quieto (visto in certificazione: il
sub-worker chiedeva la ricostruzione ogni 2 minuti senza alcun effetto).
"""
from __future__ import annotations

import queue
from types import SimpleNamespace

from flumine.events.events import TerminationEvent


def _fake_framework():
    return SimpleNamespace(handler_queue=queue.Queue(), _running=True)


def test_runner_stop_framework_enqueues_terminator():
    from Betfair.stream.runner import _stop_framework

    fl = _fake_framework()
    _stop_framework(fl)
    assert fl._running is False
    ev = fl.handler_queue.get_nowait()
    assert isinstance(ev, TerminationEvent)


def test_tennis_stop_framework_enqueues_terminator():
    from Betfair.stream.tennis_live.tennis_runner import _stop_framework

    fl = _fake_framework()
    _stop_framework(fl)
    assert fl._running is False
    ev = fl.handler_queue.get_nowait()
    assert isinstance(ev, TerminationEvent)


def test_lifecycle_keep_alive_skips_idle_exit(monkeypatch):
    """BUG FIX cert 10/07: col keep-alive desktop il ramo IDLE del lifecycle non
    spegne (il runner resta in attesa); la vita massima resta attiva."""
    import Betfair.stream.runner as rn

    calls = {"insert": 0}
    monkeypatch.setenv("LIVE_RUNNER_KEEP_ALIVE", "1")
    monkeypatch.setattr(rn.db, "insert_alert", lambda *a, **k: calls.__setitem__("insert", calls["insert"] + 1))
    monkeypatch.setattr(rn.db, "list_pending_follows", lambda: [])  # 0 follow = idle
    import time as _t
    from types import SimpleNamespace
    session = SimpleNamespace(
        shutdown_requested=SimpleNamespace(is_set=lambda: False),
        started_monotonic=_t.monotonic(),  # appena partito: vita massima NON superata
        only_event=None,
    )
    rn.lifecycle_worker({}, SimpleNamespace(), session)
    assert calls["insert"] == 0  # nessun auto-stop col keep-alive
