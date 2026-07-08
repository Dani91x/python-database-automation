"""Test del fix 2026-07-08: runner MAI più duplicati né attivi per giorni.

  * single_instance: il bind della porta è il lock — la 2ª istanza esce SUBITO;
  * runner_lifecycle (puro): vita massima + rilevamento eventi vivi/imminenti;
  * lifecycle_worker calcio: spegne su inattività, MAI su dato ambiguo/illeggibile.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import Betfair.stream.runner as rn
from Betfair.stream.runner_lifecycle import (
    any_follow_alive, event_is_alive, parse_open_date, uptime_exceeded,
)
from Betfair.stream.single_instance import acquire_single_instance_lock

_NOW = datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc)


def _follow(open_iso: str) -> dict:
    return {"event_id": "e", "open_date": open_iso, "status": "PENDING"}


# ---------------------------------------------------------------------------
# single_instance — il lock della porta è ATOMICO e auto-rilasciato
# ---------------------------------------------------------------------------
def test_second_instance_exits_immediately():
    port = 47399  # porta di test dedicata
    lock = acquire_single_instance_lock(port, "test")
    try:
        with pytest.raises(SystemExit, match="ISTANZA GIA' ATTIVA"):
            acquire_single_instance_lock(port, "test")
    finally:
        lock.close()
    # rilasciato il lock, una nuova istanza può ripartire
    lock2 = acquire_single_instance_lock(port, "test")
    lock2.close()


# ---------------------------------------------------------------------------
# runner_lifecycle — matematica pura
# ---------------------------------------------------------------------------
def test_parse_open_date_handles_z_and_garbage():
    assert parse_open_date("2026-07-08T18:00:00Z") == _NOW
    assert parse_open_date("2026-07-08T18:00:00+00:00") == _NOW
    naive = parse_open_date("2026-07-08T18:00:00")
    assert naive is not None and naive.tzinfo is not None  # normalizzato UTC
    assert parse_open_date("boh") is None
    assert parse_open_date(None) is None


def test_event_alive_windows():
    # in corso da 1h (< 3h stale) → vivo
    assert event_is_alive(_NOW - timedelta(hours=1), _NOW, 45, 3)
    # finita da oltre 3h → morta
    assert not event_is_alive(_NOW - timedelta(hours=4), _NOW, 45, 3)
    # inizia tra 30 min (< 45 imminente) → viva
    assert event_is_alive(_NOW + timedelta(minutes=30), _NOW, 45, 3)
    # inizia tra 2h → NON imminente
    assert not event_is_alive(_NOW + timedelta(hours=2), _NOW, 45, 3)
    # open_date non parsabile → PRUDENZA: vivo (mai spegnere su dato ambiguo)
    assert event_is_alive(None, _NOW, 45, 3)


def test_any_follow_alive():
    dead = _follow((_NOW - timedelta(hours=5)).isoformat())
    live = _follow((_NOW - timedelta(minutes=30)).isoformat())
    late = _follow((_NOW + timedelta(hours=3)).isoformat())
    assert not any_follow_alive([dead, late], _NOW, imminent_min=45, stale_hours=3)
    assert any_follow_alive([dead, live], _NOW, imminent_min=45, stale_hours=3)
    assert not any_follow_alive([], _NOW, imminent_min=45, stale_hours=3)


def test_uptime_exceeded():
    assert uptime_exceeded(0.0, 19 * 3600.0, 18)
    assert not uptime_exceeded(0.0, 17 * 3600.0, 18)
    assert not uptime_exceeded(0.0, 1e9, 0)  # 0 = backstop disattivato


# ---------------------------------------------------------------------------
# lifecycle_worker calcio — spegnimento e prudenza
# ---------------------------------------------------------------------------
def _mk_session(only_event=None):
    s = rn.LiveSession()
    s.only_event = only_event
    return s


def test_lifecycle_shuts_down_when_idle(monkeypatch):
    dead = _follow((datetime.now(timezone.utc) - timedelta(hours=6)).isoformat())
    monkeypatch.setattr(rn.db, "list_pending_follows", lambda: [dead])
    monkeypatch.setattr(rn.db, "insert_alert", lambda *a, **k: None)
    session = _mk_session()
    fl = SimpleNamespace(_running=True, markets=[])

    rn.lifecycle_worker({}, fl, session)

    assert session.shutdown_requested.is_set()
    assert fl._running is False


def test_lifecycle_stays_up_with_live_match(monkeypatch):
    live = _follow((datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat())
    monkeypatch.setattr(rn.db, "list_pending_follows", lambda: [live])
    session = _mk_session()
    fl = SimpleNamespace(_running=True, markets=[])

    rn.lifecycle_worker({}, fl, session)

    assert not session.shutdown_requested.is_set()
    assert fl._running is True


def test_lifecycle_stays_up_when_db_unreadable(monkeypatch):
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(rn.db, "list_pending_follows", _boom)
    session = _mk_session()
    fl = SimpleNamespace(_running=True, markets=[])

    rn.lifecycle_worker({}, fl, session)

    assert not session.shutdown_requested.is_set()  # MAI spegnere al buio


def test_lifecycle_max_hours_backstop(monkeypatch):
    monkeypatch.setattr(rn.db, "list_pending_follows", lambda: [])
    monkeypatch.setattr(rn.db, "insert_alert", lambda *a, **k: None)
    session = _mk_session()
    session.started_monotonic -= (rn._RUNNER_MAX_HOURS * 3600.0 + 60.0)  # vita superata
    fl = SimpleNamespace(_running=True, markets=[])

    rn.lifecycle_worker({}, fl, session)

    assert session.shutdown_requested.is_set()
    assert fl._running is False

# ---------------------------------------------------------------------------
# GUARDIE money-critical (fix review CRITICAL): mai spegnere con esposizione
# ---------------------------------------------------------------------------
def _market_with_live_orders():
    blotter = SimpleNamespace(live_orders=[object()])
    return SimpleNamespace(market_id="1.9", blotter=blotter)


def test_lifecycle_deferred_with_live_orders_even_on_max_hours(monkeypatch):
    """Ordini VIVI nel blotter -> NIENTE spegnimento, nemmeno a vita massima superata."""
    monkeypatch.setattr(rn.db, "list_pending_follows", lambda: [])
    session = _mk_session()
    session.started_monotonic -= (rn._RUNNER_MAX_HOURS * 3600.0 + 60.0)
    fl = SimpleNamespace(_running=True, markets=[_market_with_live_orders()])

    rn.lifecycle_worker({}, fl, session)

    assert not session.shutdown_requested.is_set()
    assert fl._running is True


def test_lifecycle_deferred_when_blotter_unreadable(monkeypatch):
    """Blotter illeggibile -> prudenza: resta acceso (mai spegnere al buio)."""
    dead = _follow((datetime.now(timezone.utc) - timedelta(hours=6)).isoformat())
    monkeypatch.setattr(rn.db, "list_pending_follows", lambda: [dead])

    class _BadMarkets:
        def __iter__(self):
            raise RuntimeError("boom")

    session = _mk_session()
    fl = SimpleNamespace(_running=True, markets=_BadMarkets())

    rn.lifecycle_worker({}, fl, session)

    assert not session.shutdown_requested.is_set()
