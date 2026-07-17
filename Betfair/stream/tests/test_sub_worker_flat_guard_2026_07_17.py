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
        sub_restart_defer_alert_interval=0.0,  # backoff alert (fix 17/07 v3)
        # aggancio rapido (fix 17/07 "Trading = streaming immediato")
        attach_attempted=set(),
        last_first_attach_bypass_ts=-1e9,
        last_resolve_ts=0.0,
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

    def _blockers_race(fl, **kw):  # fresh kwarg (fix 17/07)
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


# ----------------------------------------------------------------------------
# Fix 17/07 "Trading = streaming immediato" — bypass del throttle al PRIMO
# aggancio di un evento mai sottoscritto + anti-churn + resolve throttled.
# ----------------------------------------------------------------------------

def test_first_attach_bypasses_throttle(monkeypatch):
    """Evento MAI visto + throttle standard non scaduto → il rebuild parte
    comunque (bypass primo-aggancio): il click Trading non aspetta 60s."""
    R, session, flumine, alerts, stopped, markers = _env(
        monkeypatch, live_orders=[])
    # ultimo rebuild 20s fa: sotto MIN_RESUBSCRIBE_INTERVAL (60s) ma oltre il
    # minimo assoluto FIRST_ATTACH_MIN_INTERVAL (8s).
    session.last_resubscribe_ts = _time.monotonic() - 20.0

    R.subscription_worker({"rest": object()}, flumine, session)

    assert session.restart_requested.is_set()
    assert stopped == [flumine]
    assert "E9" in session.attach_attempted          # non è più "mai visto"
    # finestra "gratis" consumata: prossimo bypass solo dopo l'intervallo pieno
    assert session.last_first_attach_bypass_ts > 0


def test_first_attach_respects_absolute_minimum(monkeypatch):
    """Anti-loop: anche il primo aggancio rispetta il minimo ASSOLUTO tra due
    rebuild (FIRST_ATTACH_MIN_INTERVAL_SEC) — mai rebuild back-to-back."""
    R, session, flumine, alerts, stopped, _mk = _env(
        monkeypatch, live_orders=[])
    session.last_resubscribe_ts = _time.monotonic() - 2.0  # rebuild 2s fa

    R.subscription_worker({"rest": object()}, flumine, session)

    assert not session.restart_requested.is_set()
    assert stopped == []
    assert session.attach_attempted == set()         # nessun tentativo marcato


def test_retry_of_attempted_event_pays_full_throttle(monkeypatch):
    """Un evento GIÀ tentato (es. restart rinviato/riprovato) NON bypassa: il
    retry paga il throttle standard — il bypass è solo per il primo aggancio."""
    R, session, flumine, alerts, stopped, _mk = _env(
        monkeypatch, live_orders=[])
    session.attach_attempted = {"E9"}
    session.last_resubscribe_ts = _time.monotonic() - 20.0  # < 60s

    R.subscription_worker({"rest": object()}, flumine, session)

    assert not session.restart_requested.is_set()
    assert stopped == []


def test_three_new_events_in_30s_one_extra_rebuild(monkeypatch):
    """Anti-churn (pin del cantiere): 3 nuovi eventi in ~30s = UN solo rebuild
    aggiuntivo via bypass, non tre. Gli altri si accodano al giro normale."""
    R, session, flumine, alerts, stopped, _mk = _env(
        monkeypatch, live_orders=[])
    follows = [[{"event_id": "E1", "status": "PENDING"}]]
    monkeypatch.setattr(R.db, "list_pending_follows", lambda: follows[0])

    # t0: arriva E1 con throttle standard attivo (rebuild 20s fa) → bypass OK.
    now = _time.monotonic()
    session.last_resubscribe_ts = now - 20.0
    R.subscription_worker({"rest": object()}, flumine, session)
    assert stopped == [flumine]                      # 1° rebuild (bypass)

    # E1 catalogato dal main loop; il framework è ripartito.
    session.cataloged_events.add("E1")
    session.restart_requested.clear()

    # t0+10s: arriva E2 (mai visto). Ultimo bypass 10s fa → NIENTE 2° bypass.
    follows[0] = [{"event_id": "E2", "status": "PENDING"}]
    session.last_resubscribe_ts = _time.monotonic() - 10.0
    session.last_first_attach_bypass_ts = _time.monotonic() - 10.0
    R.subscription_worker({"rest": object()}, flumine, session)
    assert stopped == [flumine]                      # ancora UN solo rebuild

    # t0+20s: arriva anche E3. Bypass ancora in finestra → niente rebuild.
    follows[0] = [{"event_id": "E2", "status": "PENDING"},
                  {"event_id": "E3", "status": "PENDING"}]
    session.last_resubscribe_ts = _time.monotonic() - 20.0
    session.last_first_attach_bypass_ts = _time.monotonic() - 20.0
    R.subscription_worker({"rest": object()}, flumine, session)
    assert stopped == [flumine]                      # churn EVITATO

    # t0+70s: throttle standard scaduto → rebuild normale aggancia E2+E3 insieme.
    session.last_resubscribe_ts = _time.monotonic() - 70.0
    session.last_first_attach_bypass_ts = _time.monotonic() - 70.0
    R.subscription_worker({"rest": object()}, flumine, session)
    assert stopped == [flumine, flumine]             # 2° rebuild, cumulativo
    assert {"E2", "E3"} <= session.attach_attempted


def test_flat_guard_unchanged_with_bypass_window(monkeypatch):
    """La guardia flat resta INTATTA anche quando il bypass aprirebbe il
    throttle: ordini vivi → rinvio, nessuno stop, finestra bypass NON consumata."""
    R, session, flumine, alerts, stopped, markers = _env(
        monkeypatch, live_orders=[object()])
    session.last_resubscribe_ts = _time.monotonic() - 20.0  # bypass eleggibile

    R.subscription_worker({"rest": object()}, flumine, session)

    assert not session.restart_requested.is_set()
    assert stopped == []
    assert markers == []
    assert session.sub_restart_deferred_since is not None
    assert session.last_first_attach_bypass_ts == -1e9  # niente finestra bruciata
    assert session.attach_attempted == set()


def test_resolve_throttled_and_nonblocking(monkeypatch):
    """resolve_and_register (REST pesante) gira al massimo una volta per
    WATCHLIST_POLL_SEC anche col worker a ~2s; un suo errore NON blocca più
    il check dei follow (l'aggancio da click Trading è indipendente)."""
    R, session, flumine, alerts, stopped, _mk = _env(
        monkeypatch, live_orders=[])
    calls = {"n": 0}

    def _resolve_boom(rest):
        calls["n"] += 1
        raise RuntimeError("REST giù")

    monkeypatch.setattr(R, "resolve_and_register", _resolve_boom)

    R.subscription_worker({"rest": object()}, flumine, session)
    # nonostante il resolve KO, il follow E9 è stato agganciato (restart chiesto)
    assert stopped == [flumine]
    assert calls["n"] == 1

    # secondo giro subito dopo: resolve NON richiamato (throttle interno)
    session.cataloged_events.add("E9")
    R.subscription_worker({"rest": object()}, flumine, session)
    assert calls["n"] == 1
