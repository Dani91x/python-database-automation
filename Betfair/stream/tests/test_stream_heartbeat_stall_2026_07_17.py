"""Test dei fix CANTIERE B 17/07 — lato stream/runner.

1. Stallo CIECO agli heartbeat (finding #1 HIGH): i messaggi mcm ct=HEARTBEAT
   ora aggiornano ``last_heartbeat_ms`` — heartbeat freschi + dati fermi =
   mercato QUIETO (metà tempo), NIENTE restart; heartbeat E dati vecchi =
   connessione morta → restart (comportamento 16/07 preservato).
2. TOCTOU stall-restart (finding #5 MEDIUM): ri-verifica dei blocker
   IMMEDIATAMENTE prima di ``_stop_framework``.
3. Marker ``resubscribe`` nel sidecar .recmeta.jsonl (finding #6 MEDIUM):
   i restart soft lasciano traccia, il raw resta byte-identico.
"""
from __future__ import annotations

import json
import os
import threading
import time as _time
from types import SimpleNamespace

from Betfair.stream.raw_listener import _RawState
from Betfair.stream.runner_lifecycle import (
    effective_stall_seconds,
    raw_stall_seconds,
)

EVENT_ID = "888"
MARKET_ID = "1.888"


def _mcm_line(pt: int) -> str:
    return json.dumps({
        "op": "mcm", "clk": "1", "pt": pt,
        "mc": [{"id": MARKET_ID, "rc": [{"id": 1, "ltp": 2.0}]}],
    })


def _heartbeat_line(pt: int) -> str:
    # heartbeat Betfair reale: op=mcm, ct=HEARTBEAT, NESSUN campo mc
    return json.dumps({"op": "mcm", "id": 2, "clk": "1", "pt": pt, "ct": "HEARTBEAT"})


def _read_jsonl(path: str) -> list:
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# raw_listener: tracking heartbeat separato dai write dati
# ---------------------------------------------------------------------------
def test_heartbeat_updates_only_heartbeat_ts(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, True)
    state.write_message(_heartbeat_line(5_000))

    assert state.last_heartbeat_ms == 5_000
    assert state.last_write_ms == {}                      # nessun write dati
    assert not os.path.exists(os.path.join(str(tmp_path), EVENT_ID))  # raw intatto

    h = state.health()
    assert h["last_heartbeat_ms"] == 5_000
    assert h["last_write_ms"] == {}


def test_data_write_does_not_touch_heartbeat_ts(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, True)
    state.write_message(_mcm_line(7_000))

    assert state.last_heartbeat_ms == 0
    assert state.last_write_ms == {EVENT_ID: 7_000}
    raw_rows = _read_jsonl(os.path.join(str(tmp_path), EVENT_ID, f"{EVENT_ID}.raw.jsonl"))
    assert len(raw_rows) == 1 and raw_rows[0]["op"] == "mcm"


def test_heartbeat_never_written_to_raw(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, True)
    state.write_message(_mcm_line(1_000))
    state.write_message(_heartbeat_line(2_000))
    state.write_message(_mcm_line(3_000))
    rows = _read_jsonl(os.path.join(str(tmp_path), EVENT_ID, f"{EVENT_ID}.raw.jsonl"))
    assert [r["pt"] for r in rows] == [1_000, 3_000]  # heartbeat MAI nel raw


def test_configure_resets_heartbeat_ts(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, True)
    state.write_message(_heartbeat_line(5_000))
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, True)  # rebuild subscription
    assert state.last_heartbeat_ms == 0


# ---------------------------------------------------------------------------
# runner_lifecycle: matematica pura dello stallo effettivo
# ---------------------------------------------------------------------------
def test_effective_stall_math():
    # dati non determinabili → None (nessuna azione)
    assert effective_stall_seconds(None, 999.0) is None
    # heartbeat mai osservati / età stream ignota → comportamento storico
    assert effective_stall_seconds(700.0, None) == 700.0
    # mercato QUIETO: dati fermi ma heartbeat freschi → stallo = heartbeat
    assert effective_stall_seconds(700.0, 3.0) == 3.0
    # connessione MORTA: entrambi vecchi → stallo = min (comunque sopra soglia)
    assert effective_stall_seconds(700.0, 650.0) == 650.0


def test_effective_stall_hard_cap_ignora_heartbeat_freschi():
    """Review 17/07 (seconda passata): l'heartbeat prova che il SOCKET è vivo,
    non che la subscription dati è sana. Oltre il cap di silenzio dati puro il
    restart deve scattare COMUNQUE (garanzia anti-16/07 preservata anche con
    heartbeat che 'mentono')."""
    # oltre il cap: heartbeat freschissimi ma i dati tornano a comandare
    assert effective_stall_seconds(2000.0, 3.0, 1800.0) == 2000.0
    # sotto il cap: la quiete legittima resta mascherata dagli heartbeat
    assert effective_stall_seconds(1200.0, 3.0, 1800.0) == 3.0
    # cap disattivo (None) → comportamento base invariato
    assert effective_stall_seconds(2000.0, 3.0, None) == 3.0
    # il cap non "inventa" stallo se i dati non sono determinabili
    assert effective_stall_seconds(None, 3.0, 1800.0) is None


def test_raw_stall_seconds_heartbeat_never_seen_uses_stream_age():
    # heartbeat mai visti (0) → età dello stream corrente (come i dati)
    assert raw_stall_seconds(0, 130_000.0, 300.0) == 300.0


# ---------------------------------------------------------------------------
# heartbeat_worker: quiete ≠ morte (scenari pinnati, finding #1)
# ---------------------------------------------------------------------------
def _stall_env(monkeypatch, *, live_orders, last_heartbeat_ms,
               last_write_ms=1.0):
    from Betfair.stream import runner as R
    import Betfair.stream.raw_listener as RL

    monkeypatch.setattr(R, "_RAW_STALL_LAST_RESTART", 0.0)
    monkeypatch.setattr(R, "_RAW_STALL_ALERTED", True)  # niente ramo WARN
    monkeypatch.setattr(R, "_STREAM_KA_LAST", _time.monotonic())  # no keepAlive
    monkeypatch.setattr(R.db, "upsert_live_heartbeat", lambda **k: None)
    alerts = []
    monkeypatch.setattr(R.db, "insert_alert",
                        lambda lvl, code, msg, *a: alerts.append((lvl, code, msg)))
    monkeypatch.setattr(RL.RAW_STATE, "health", lambda: {
        "enabled": True, "last_write_ms": {"E1": last_write_ms},
        "last_heartbeat_ms": last_heartbeat_ms, "write_errors": 0})
    markers = []
    monkeypatch.setattr(RL.RAW_STATE, "mark_resubscribe",
                        lambda reason: markers.append(reason))
    stopped = []
    monkeypatch.setattr(R, "_stop_framework", lambda fl: stopped.append(fl))
    session = SimpleNamespace(
        market_to_event={"1.1": "E1"},
        shutdown_requested=threading.Event(),
        restart_requested=threading.Event(),
        stream_started_monotonic=_time.monotonic() - 10_000,
        context_api_client=None,
    )
    blotter = SimpleNamespace(live_orders=live_orders)
    flumine = SimpleNamespace(markets=[SimpleNamespace(market_id="1.1",
                                                       blotter=blotter)])
    return R, session, flumine, alerts, stopped, markers


def test_quiet_market_fresh_heartbeats_no_restart(monkeypatch):
    """Dati fermi da 20 min (metà tempo) MA heartbeat freschi = mercato quieto
    → NIENTE restart. Il silenzio dati resta SOTTO l'hard-cap (30 min): oltre
    quello, per design, i dati tornano a comandare (test dedicato sotto)."""
    now_ms = _time.time() * 1000.0
    R, session, flumine, alerts, stopped, _mk = _stall_env(
        monkeypatch, live_orders=[], last_heartbeat_ms=now_ms - 2_000.0,
        last_write_ms=now_ms - 1_200_000.0)   # dati fermi da 20 min
    R.heartbeat_worker({}, flumine, session)
    assert not session.restart_requested.is_set()
    assert stopped == []
    assert alerts == []          # nemmeno il WARN: lo stream è VIVO


def test_fresh_heartbeats_but_data_beyond_hard_cap_restarts(monkeypatch):
    """Review 17/07 (seconda passata): heartbeat freschi con silenzio dati
    OLTRE l'hard-cap (subscription rotta a socket vivo) → restart COMUNQUE.
    Garanzia anti-16/07 preservata anche se gli heartbeat 'mentono'."""
    now_ms = _time.time() * 1000.0
    R, session, flumine, alerts, stopped, _mk = _stall_env(
        monkeypatch, live_orders=[], last_heartbeat_ms=now_ms - 2_000.0,
        last_write_ms=now_ms - 2_400_000.0)   # dati fermi da 40 min (> cap 30')
    R.heartbeat_worker({}, flumine, session)
    assert session.restart_requested.is_set()
    assert stopped == [flumine]


def test_dead_stream_stale_heartbeats_restarts(monkeypatch):
    """Dati fermi E heartbeat vecchi = connessione morta → restart (come 16/07)."""
    R, session, flumine, alerts, stopped, markers = _stall_env(
        monkeypatch, live_orders=[], last_heartbeat_ms=1.0)
    R.heartbeat_worker({}, flumine, session)
    assert session.restart_requested.is_set()
    assert stopped == [flumine]
    assert any(lvl == "CRITICAL" and "auto-recovery" in msg for lvl, _c, msg in alerts)
    # finding #6: il restart soft lascia il marker resubscribe nel recmeta
    assert markers and "stall-recovery" in markers[0]


def test_dead_stream_no_heartbeat_info_restarts(monkeypatch):
    """Heartbeat MAI visti (0) → età stream (retro-compat col caso 16/07)."""
    R, session, flumine, alerts, stopped, _mk = _stall_env(
        monkeypatch, live_orders=[], last_heartbeat_ms=0)
    R.heartbeat_worker({}, flumine, session)
    assert session.restart_requested.is_set()
    assert stopped == [flumine]


# ---------------------------------------------------------------------------
# TOCTOU (finding #5): blocker comparso TRA il primo check e lo stop
# ---------------------------------------------------------------------------
def test_stall_restart_toctou_recheck_blocks(monkeypatch):
    R, session, flumine, alerts, stopped, markers = _stall_env(
        monkeypatch, live_orders=[], last_heartbeat_ms=1.0)
    calls = {"n": 0}

    def _blockers_race(fl):
        calls["n"] += 1
        # 1° check (pre-alert): pulito; 2° check (dentro _request_soft_restart):
        # un ordine è comparso nel frattempo (live_order_worker concorrente).
        return None if calls["n"] == 1 else "1 ordini vivi sul mercato 1.1"

    monkeypatch.setattr(R, "_lifecycle_blockers", _blockers_race)
    R.heartbeat_worker({}, flumine, session)

    assert calls["n"] >= 2                          # doppio check eseguito
    assert not session.restart_requested.is_set()   # MAI restart con esposizione
    assert stopped == []
    assert markers == []                            # nessun marker: nessun restart
    assert any(lvl == "CRITICAL" and "ultimo check" in msg for lvl, _c, msg in alerts)


def test_lifecycle_worker_toctou_recheck_blocks(monkeypatch):
    """Stesso TOCTOU sull'auto-spegnimento: ricontrollo prima dello stop."""
    from Betfair.stream import runner as R

    monkeypatch.setattr(R.db, "list_pending_follows", lambda: [])
    monkeypatch.setattr(R.db, "insert_alert", lambda *a, **k: None)
    stopped = []
    monkeypatch.setattr(R, "_stop_framework", lambda fl: stopped.append(fl))
    calls = {"n": 0}

    def _blockers_race(fl):
        calls["n"] += 1
        return None if calls["n"] == 1 else "regole di rischio armate/innescate"

    monkeypatch.setattr(R, "_lifecycle_blockers", _blockers_race)
    session = R.LiveSession()
    session.started_monotonic -= (R._RUNNER_MAX_HOURS * 3600.0 + 60.0)
    fl = SimpleNamespace(_running=True, markets=[])

    R.lifecycle_worker({}, fl, session)

    assert calls["n"] == 2
    assert not session.shutdown_requested.is_set()
    assert stopped == []


# ---------------------------------------------------------------------------
# Marker resubscribe nel sidecar (finding #6): unit su _RawState
# ---------------------------------------------------------------------------
def test_mark_resubscribe_writes_recmeta_and_raw_untouched(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, True)
    state.write_message(_mcm_line(1_000))
    state.mark_resubscribe("stall-recovery: stream muto 700s")

    raw_path = os.path.join(str(tmp_path), EVENT_ID, f"{EVENT_ID}.raw.jsonl")
    meta_path = os.path.join(str(tmp_path), EVENT_ID, f"{EVENT_ID}.recmeta.jsonl")
    raw_rows = _read_jsonl(raw_path)
    assert len(raw_rows) == 1 and raw_rows[0]["op"] == "mcm"  # raw byte-identico

    meta_rows = _read_jsonl(meta_path)
    kinds = [m["kind"] for m in meta_rows]
    assert kinds == ["open", "resubscribe"]
    marker = meta_rows[-1]
    assert marker["reason"].startswith("stall-recovery")
    assert marker["last_pt_ms"] == 1_000
    assert marker["ts_ms"] > 0


def test_mark_resubscribe_covers_events_without_open_file(tmp_path):
    """Anche gli eventi ROUTED ma senza file aperto (mai un write in questa
    vita) ricevono il marker: il confine del buco è esplicito per tutti."""
    state = _RawState()
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID, "1.777": "777"}, True)
    state.write_message(_mcm_line(1_000))  # solo EVENT_ID ha un file
    state.mark_resubscribe("F3: 1 nuove partite GIOCATA")

    for ev in (EVENT_ID, "777"):
        meta_path = os.path.join(str(tmp_path), ev, f"{ev}.recmeta.jsonl")
        rows = _read_jsonl(meta_path)
        assert any(m["kind"] == "resubscribe" for m in rows)


def test_mark_resubscribe_disabled_noop(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, False)
    state.mark_resubscribe("qualunque")
    assert not os.path.exists(os.path.join(str(tmp_path), EVENT_ID))
