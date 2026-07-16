"""Test dei fix "registrazioni parziali" lato RECORDER (16/07).

1. Marker di copertura: il tee raw scrive il sidecar ``.recmeta.jsonl``
   (open/close di ogni sessione di registrazione) SENZA toccare il formato
   del ``.raw.jsonl`` (che deve restare replayabile da FlumineSimulation).
2. Stallo del flusso: matematica pura di ``raw_stall_seconds`` /
   ``stall_restart_due`` (escalation CRITICAL + auto-resubscribe nel runner).
"""
from __future__ import annotations

import json
import os

from Betfair.stream.raw_listener import _RawState
from Betfair.stream.runner_lifecycle import raw_stall_seconds, stall_restart_due

EVENT_ID = "777"
MARKET_ID = "1.999"


def _mcm_line(pt: int) -> str:
    return json.dumps({
        "op": "mcm", "clk": "1", "pt": pt,
        "mc": [{"id": MARKET_ID, "rc": [{"id": 1, "ltp": 2.0}]}],
    })


def _read_jsonl(path: str) -> list:
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# recmeta: marker open/close, raw intatto
# ---------------------------------------------------------------------------
def test_recmeta_open_close_and_raw_untouched(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, True)
    state.write_message(_mcm_line(1_000))
    state.write_message(_mcm_line(2_000))
    state.close()

    raw_path = os.path.join(str(tmp_path), EVENT_ID, f"{EVENT_ID}.raw.jsonl")
    meta_path = os.path.join(str(tmp_path), EVENT_ID, f"{EVENT_ID}.recmeta.jsonl")

    # il raw contiene SOLO messaggi mcm (formato nativo intatto)
    raw_rows = _read_jsonl(raw_path)
    assert len(raw_rows) == 2
    assert all(r["op"] == "mcm" for r in raw_rows)

    # il sidecar documenta la sessione: open (file nuovo) + close (ultimo pt)
    meta_rows = _read_jsonl(meta_path)
    assert [m["kind"] for m in meta_rows] == ["open", "close"]
    assert meta_rows[0]["raw_bytes_at_open"] == 0
    assert meta_rows[1]["last_pt_ms"] == 2_000
    assert meta_rows[1]["bytes_written"] > 0


def test_recmeta_reopen_marks_append_boundary(tmp_path):
    """Un restart del runner (nuova _RawState) riapre in APPEND: il nuovo
    record open ha raw_bytes_at_open > 0 → confine del possibile buco."""
    first = _RawState()
    first.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, True)
    first.write_message(_mcm_line(1_000))
    first.close()

    second = _RawState()
    second.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, True)
    second.write_message(_mcm_line(600_000))
    second.close()

    raw_path = os.path.join(str(tmp_path), EVENT_ID, f"{EVENT_ID}.raw.jsonl")
    meta_path = os.path.join(str(tmp_path), EVENT_ID, f"{EVENT_ID}.recmeta.jsonl")
    assert len(_read_jsonl(raw_path)) == 2  # append, mai troncato
    meta_rows = _read_jsonl(meta_path)
    assert [m["kind"] for m in meta_rows] == ["open", "close", "open", "close"]
    assert meta_rows[2]["raw_bytes_at_open"] > 0


def test_recmeta_disabled_writes_nothing(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), {MARKET_ID: EVENT_ID}, False)  # tee OFF
    state.write_message(_mcm_line(1_000))
    state.close()
    assert not os.path.exists(os.path.join(str(tmp_path), EVENT_ID))


# ---------------------------------------------------------------------------
# stallo: matematica pura
# ---------------------------------------------------------------------------
def test_raw_stall_seconds_from_last_write():
    assert raw_stall_seconds(10_000.0, 130_000.0, None) == 120.0


def test_raw_stall_seconds_never_written_uses_stream_age():
    # il caso 16/07: stream MAI connesso dopo il rebuild → last_write_ms==0
    assert raw_stall_seconds(0, 130_000.0, 300.0) == 300.0


def test_raw_stall_seconds_unknown():
    assert raw_stall_seconds(0, 130_000.0, None) is None


def test_stall_restart_due_thresholds():
    # sotto soglia / stall ignoto / meccanismo disattivato → mai
    assert stall_restart_due(500.0, 600.0, 0.0, 10_000.0, 900.0) is False
    assert stall_restart_due(None, 600.0, 0.0, 10_000.0, 900.0) is False
    assert stall_restart_due(9_999.0, 0.0, 0.0, 10_000.0, 900.0) is False
    # oltre soglia + intervallo minimo rispettato → restart
    assert stall_restart_due(601.0, 600.0, 0.0, 10_000.0, 900.0) is True
    # throttle: ultima ricostruzione troppo recente → no churn
    assert stall_restart_due(601.0, 600.0, 9_500.0, 10_000.0, 900.0) is False


# ---------------------------------------------------------------------------
# GUARDIA MONEY-CRITICAL sullo stall-restart (fix review 16/07): il recovery
# NON deve mai ricostruire il framework con ordini vivi nel blotter (stessa
# lezione del tennis audit #1: blotter nuovo e vuoto = esposizione orfana).
# ---------------------------------------------------------------------------
import threading
import time as _time
from types import SimpleNamespace


def _stall_env(monkeypatch, *, live_orders):
    from Betfair.stream import runner as R
    import Betfair.stream.raw_listener as RL

    monkeypatch.setattr(R, "_RAW_STALL_LAST_RESTART", 0.0)
    monkeypatch.setattr(R, "_RAW_STALL_ALERTED", True)  # niente ramo WARN
    monkeypatch.setattr(R, "_STREAM_KA_LAST", _time.monotonic())  # no keepAlive
    monkeypatch.setattr(R.db, "upsert_live_heartbeat", lambda **k: None)
    alerts = []
    monkeypatch.setattr(R.db, "insert_alert",
                        lambda lvl, code, msg: alerts.append((lvl, code, msg)))
    monkeypatch.setattr(RL.RAW_STATE, "health", lambda: {
        "enabled": True, "last_write_ms": {"E1": 1.0}, "write_errors": 0})
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
    return R, session, flumine, alerts, stopped


def test_stall_restart_rinviato_con_ordini_vivi(monkeypatch):
    R, session, flumine, alerts, stopped = _stall_env(monkeypatch, live_orders=[object()])
    R.heartbeat_worker({}, flumine, session)
    assert not session.restart_requested.is_set()      # MAI restart con esposizione
    assert stopped == []
    assert any(lvl == "CRITICAL" and "RINVIATO" in msg for lvl, _c, msg in alerts)


def test_stall_restart_parte_a_blotter_flat(monkeypatch):
    R, session, flumine, alerts, stopped = _stall_env(monkeypatch, live_orders=[])
    R.heartbeat_worker({}, flumine, session)
    assert session.restart_requested.is_set()
    assert stopped == [flumine]
    assert any(lvl == "CRITICAL" and "auto-recovery" in msg for lvl, _c, msg in alerts)
