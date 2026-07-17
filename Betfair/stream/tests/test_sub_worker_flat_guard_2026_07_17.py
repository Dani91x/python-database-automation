"""Test finding #7 (17/07) — parità calcio/tennis sulla guardia flat del
restart F3: ``subscription_worker`` NON deve mai forzare la ricostruzione della
subscription (blotter nuovo e VUOTO) con ordini vivi o regole armate. Il
restart è RINVIATO finché non si è flat; se il rinvio persiste → alert
CRITICAL visibile. A blotter flat il flusso storico è invariato (INFO alert +
restart + marker resubscribe).
"""
from __future__ import annotations

import threading
import time as _time
from types import SimpleNamespace


def _env(monkeypatch, *, live_orders):
    from Betfair.stream import runner as R
    import Betfair.stream.raw_listener as RL

    monkeypatch.setattr(R, "resolve_and_register", lambda rest: None)
    monkeypatch.setattr(R.db, "list_pending_follows",
                        lambda: [{"event_id": "E9", "status": "PENDING"}])
    alerts = []
    monkeypatch.setattr(R.db, "insert_alert",
                        lambda lvl, code, msg, *a: alerts.append((lvl, code, msg)))
    stopped = []
    monkeypatch.setattr(R, "_stop_framework", lambda fl: stopped.append(fl))
    markers = []
    monkeypatch.setattr(RL.RAW_STATE, "mark_resubscribe",
                        lambda reason: markers.append(reason))
    session = SimpleNamespace(
        cataloged_events=set(),
        finished_events=set(),
        last_resubscribe_ts=-1e9,          # throttle F3 già scaduto
        restart_requested=threading.Event(),
        sub_restart_deferred_since=None,
        sub_restart_defer_alert_ts=0.0,
    )
    blotter = SimpleNamespace(live_orders=live_orders)
    flumine = SimpleNamespace(markets=[SimpleNamespace(market_id="1.1",
                                                       blotter=blotter)])
    return R, session, flumine, alerts, stopped, markers


def test_restart_deferred_with_live_orders(monkeypatch):
    R, session, flumine, alerts, stopped, markers = _env(
        monkeypatch, live_orders=[object()])

    R.subscription_worker({"rest": object()}, flumine, session)

    assert not session.restart_requested.is_set()   # MAI forzare in live
    assert stopped == []
    assert markers == []
    assert session.sub_restart_deferred_since is not None  # rinvio tracciato
    assert alerts == []                             # primo rinvio: solo log


def test_persistent_deferral_raises_critical_alert(monkeypatch):
    R, session, flumine, alerts, stopped, _mk = _env(
        monkeypatch, live_orders=[object()])
    # rinvio che PERSISTE oltre la grazia → alert CRITICAL visibile
    session.sub_restart_deferred_since = (
        _time.monotonic() - R._SUB_RESTART_DEFER_ALERT_SEC - 60.0)

    R.subscription_worker({"rest": object()}, flumine, session)

    assert not session.restart_requested.is_set()
    assert stopped == []
    assert any(lvl == "CRITICAL" and c == "NEW_MATCHES" and "RINVIATO" in msg
               for lvl, c, msg in alerts)
    # anti-spam: un secondo giro nella stessa grazia NON duplica l'alert
    n_before = len(alerts)
    R.subscription_worker({"rest": object()}, flumine, session)
    assert len(alerts) == n_before


def test_restart_proceeds_when_flat(monkeypatch):
    R, session, flumine, alerts, stopped, markers = _env(
        monkeypatch, live_orders=[])

    R.subscription_worker({"rest": object()}, flumine, session)

    assert session.restart_requested.is_set()
    assert stopped == [flumine]
    assert session.last_resubscribe_ts > 0          # throttle consumato SOLO al via
    assert any(lvl == "INFO" and c == "NEW_MATCHES" for lvl, c, _m in alerts)
    assert markers and "F3" in markers[0]           # finding #6: marker resubscribe


def test_deferral_cleared_once_flat_then_restart(monkeypatch):
    """Sequenza reale: rinvio con ordini vivi → posizione chiusa → restart."""
    R, session, flumine, alerts, stopped, _mk = _env(
        monkeypatch, live_orders=[object()])
    R.subscription_worker({"rest": object()}, flumine, session)
    assert session.sub_restart_deferred_since is not None

    flumine.markets[0].blotter.live_orders = []     # ora flat
    R.subscription_worker({"rest": object()}, flumine, session)

    assert session.restart_requested.is_set()
    assert stopped == [flumine]
    assert session.sub_restart_deferred_since is None  # rinvio azzerato


def test_toctou_recheck_in_sub_worker(monkeypatch):
    """Ordine comparso TRA il check flat e lo stop → rinvio, mai stop."""
    R, session, flumine, alerts, stopped, markers = _env(
        monkeypatch, live_orders=[])
    calls = {"n": 0}

    def _blockers_race(fl):
        calls["n"] += 1
        return None if calls["n"] == 1 else "1 ordini vivi sul mercato 1.1"

    monkeypatch.setattr(R, "_lifecycle_blockers", _blockers_race)
    R.subscription_worker({"rest": object()}, flumine, session)

    assert calls["n"] == 2
    assert not session.restart_requested.is_set()
    assert stopped == []
    assert markers == []                            # niente marker senza restart
    assert session.sub_restart_deferred_since is not None
    assert session.last_resubscribe_ts == -1e9      # throttle NON consumato
