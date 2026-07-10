"""Missione '1 tick per fase' nel runner live + fail-safe gap-guard del worker.

  * bot_control_worker: strategy con ``mission_done=True`` → come il disarm:
    _disable_strategy + flat verificato dal blotter + status DB 'done'
    (nessun restart del framework: il bot disabilitato resta inerte).
  * score_and_now_worker: ts None (feed KO) → point_pressure INVARIATO.
"""
from __future__ import annotations

import queue
import types

from Betfair.stream.tennis_live import tennis_runner


class _MissionBot:
    """Scalper a missione compiuta (mission_done alzato dal bot stesso)."""

    def __init__(self, mission_done=True):
        self.dry_run = False
        self.max_order_exposure = 100.0
        self.max_selection_exposure = 100.0
        self.max_market_exposure = None
        self.stats = {"greens_prematch": 1, "greens_inplay": 1}
        self.mission_done = mission_done
        self.force_flat = mission_done
        self.point_pressure = True
        self.score = None

    def check_market_book(self, market, market_book):  # noqa: ARG002
        return True


def _controls_running(bot_key="tennis_scalper"):
    def _list(event_id, statuses=None, **k):  # noqa: ARG001
        if statuses and "stopping" in statuses:
            return []
        return [{"bot_key": bot_key, "status": "running"}]
    return _list


def _session_with(strat):
    session = tennis_runner.TennisLiveSession(trading=object())
    session.market_meta = {"ev1": {"market_id": "1.1"}}
    session.hosted = {("ev1", "tennis_scalper"): strat}
    return session


def test_mission_done_flat_marks_done_without_restart(monkeypatch):
    statuses = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: statuses.append((a, k)))
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_running())
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: True)

    strat = _MissionBot()
    session = _session_with(strat)
    fl = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.bot_control_worker({}, fl, session)

    assert strat._tennis_disabled is True
    written = [a[2] for (a, k) in statuses]
    assert "done" in written
    assert "running" not in written                 # heartbeat non sovrascrive
    assert not session.restart_requested.is_set()   # nessun restart necessario


def test_mission_done_not_flat_keeps_bot_working(monkeypatch):
    statuses = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: statuses.append((a, k)))
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_running())
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    strat = _MissionBot()
    session = _session_with(strat)
    fl = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.bot_control_worker({}, fl, session)

    # posizione NON flat: il bot resta attivo (force_flat interno la chiude)
    assert not getattr(strat, "_tennis_disabled", False)
    written = [a[2] for (a, k) in statuses]
    assert "done" not in written
    assert "running" in written        # heartbeat normale finche' lavora


def test_bot_without_mission_untouched(monkeypatch):
    statuses = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: statuses.append((a, k)))
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_running())
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: True)

    strat = _MissionBot(mission_done=False)
    session = _session_with(strat)
    fl = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.bot_control_worker({}, fl, session)

    assert not getattr(strat, "_tennis_disabled", False)
    written = [a[2] for (a, k) in statuses]
    assert written == ["running"]      # solo heartbeat, nessun 'done'


# ---------------------------------------------------------------------------
# score_and_now_worker: ts None → point_pressure INVARIATO (fail-safe)
# ---------------------------------------------------------------------------
def test_score_worker_keeps_point_pressure_on_feed_error(monkeypatch):
    monkeypatch.setattr(tennis_runner.tennis_db, "upsert_tennis_now",
                        lambda *a, **k: None)

    class _FailingIPS:
        def get_scores(self, **kw):  # noqa: ARG002
            raise RuntimeError("feed KO")

    trading = types.SimpleNamespace(in_play_service=_FailingIPS())
    session = tennis_runner.TennisLiveSession(trading=trading)
    session.market_meta = {"ev1": {"market_id": "1.1"}}
    strat = _MissionBot(mission_done=False)
    strat.point_pressure = True        # guardia ALZATA prima del blackout
    session.hosted = {("ev1", "tennis_scalper"): strat}

    tennis_runner.score_and_now_worker({}, None, session)

    assert strat.point_pressure is True  # invariata: MAI fail-open
