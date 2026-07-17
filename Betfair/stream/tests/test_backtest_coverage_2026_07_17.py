"""Test finding #3 (17/07) — warning coverage INVISIBILE → nei risultati.

CONTRATTO col cantiere frontend: i campi si chiamano ESATTAMENTE
``coverage_pct`` (float 0-100) e ``coverage_verdict`` (str) dentro il jsonb
``metrics`` delle righe risultato (run_backtest / run_theta / run_scalper),
con dettaglio per-evento in ``coverage_events``. Verdetto non-COMPLETE →
``db.insert_alert('WARN', 'BACKTEST_COVERAGE', ...)`` (pannello Alert).

Finding #4: run_scalper ora passa dalla stessa guardia (min_coverage opzionale).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import Betfair.stream.db as db_mod
from Betfair.stream.backtest.run_backtest import (
    attach_coverage,
    build_coverage_meta,
    run_backtest,
)
from Betfair.stream.tests.test_validate_recordings import _lines, _write_raw


@pytest.fixture()
def alerts(monkeypatch):
    captured = []
    monkeypatch.setattr(
        db_mod, "insert_alert",
        lambda level, code, message, event_id=None: captured.append(
            (level, code, message, event_id)))
    return captured


def _make_data(tmp_path) -> str:
    """Evento 200 COMPLETE, evento 201 PARTIAL (inizio tardivo)."""
    _write_raw(str(tmp_path), "200", _lines([(-10, 118)], closed_at_end=True))
    _write_raw(str(tmp_path), "201", _lines([(60, 118)], closed_at_end=True))
    return str(tmp_path)


def _fake_report(pct, verdict, reasons=()):
    return SimpleNamespace(coverage_pct=pct, verdict=verdict, reasons=list(reasons))


# ---------------------------------------------------------------------------
# helper puri
# ---------------------------------------------------------------------------
def test_build_coverage_meta_exact_field_names():
    reports = {"1": _fake_report(100.0, "COMPLETE"),
               "2": _fake_report(47.8, "PARTIAL")}
    meta = build_coverage_meta(reports, ["1", "2"])
    # CONTRATTO: nomi campo esatti, aggregato worst-case
    assert meta["coverage_pct"] == 47.8
    assert meta["coverage_verdict"] == "PARTIAL"
    assert meta["coverage_events"]["1"] == {
        "coverage_pct": 100.0, "coverage_verdict": "COMPLETE"}
    assert meta["coverage_events"]["2"] == {
        "coverage_pct": 47.8, "coverage_verdict": "PARTIAL"}


def test_build_coverage_meta_none_pct_and_missing_report():
    reports = {"1": _fake_report(None, "UNKNOWN")}
    meta = build_coverage_meta(reports, ["1", "2"])  # "2" senza report
    assert meta["coverage_pct"] == 0.0
    assert meta["coverage_verdict"] == "UNKNOWN"
    assert meta["coverage_events"]["2"]["coverage_verdict"] == "UNKNOWN"
    assert isinstance(meta["coverage_events"]["1"]["coverage_pct"], float)


def test_build_coverage_meta_worst_verdict_no_raw():
    reports = {"1": _fake_report(100.0, "COMPLETE"),
               "2": _fake_report(0.0, "NO_RAW")}
    meta = build_coverage_meta(reports, ["1", "2"])
    assert meta["coverage_verdict"] == "NO_RAW"


def test_attach_coverage_updates_every_row():
    rows = [{"scope": "ALL", "grp": "ALL", "metrics": {"n_back": 1}},
            {"scope": "MARKET_TYPE", "grp": "MATCH_ODDS", "metrics": {}}]
    attach_coverage(rows, {"coverage_pct": 50.0, "coverage_verdict": "PARTIAL",
                           "coverage_events": {}})
    for row in rows:
        assert row["metrics"]["coverage_pct"] == 50.0
        assert row["metrics"]["coverage_verdict"] == "PARTIAL"
    assert rows[0]["metrics"]["n_back"] == 1  # metriche esistenti preservate


# ---------------------------------------------------------------------------
# run_backtest: coverage nei risultati + alert WARN (senza flumine)
# ---------------------------------------------------------------------------
def test_run_backtest_writes_coverage_and_alert(tmp_path, monkeypatch, alerts):
    from importlib import import_module
    RB = import_module("Betfair.stream.backtest.run_backtest")

    data_dir = _make_data(tmp_path)
    monkeypatch.setattr(RB, "_run_one_event", lambda ev, params, root: [])

    rows = run_backtest({"event_ids": ["200", "201"]}, data_dir=data_dir)

    all_row = next(r for r in rows if r["scope"] == "ALL")
    m = all_row["metrics"]
    assert m["coverage_verdict"] == "PARTIAL"           # worst-case aggregato
    assert 0.0 <= m["coverage_pct"] <= 100.0
    assert m["coverage_events"]["200"]["coverage_verdict"] == "COMPLETE"
    assert m["coverage_events"]["201"]["coverage_verdict"] == "PARTIAL"
    # alert WARN SOLO per l'evento non-COMPLETE, nel pannello Alert esistente
    assert [(a[0], a[1], a[3]) for a in alerts] == [
        ("WARN", "BACKTEST_COVERAGE", "201")]
    assert "PARTIAL" in alerts[0][2]


def test_run_backtest_all_complete_no_alert(tmp_path, monkeypatch, alerts):
    from importlib import import_module
    RB = import_module("Betfair.stream.backtest.run_backtest")

    _write_raw(str(tmp_path), "200", _lines([(-10, 118)], closed_at_end=True))
    monkeypatch.setattr(RB, "_run_one_event", lambda ev, params, root: [])

    rows = run_backtest({"event_ids": ["200"]}, data_dir=str(tmp_path))

    m = rows[0]["metrics"]
    assert m["coverage_verdict"] == "COMPLETE"
    assert m["coverage_pct"] >= 99.0
    assert alerts == []


def test_run_backtest_min_coverage_filters_events(tmp_path, monkeypatch, alerts):
    from importlib import import_module
    RB = import_module("Betfair.stream.backtest.run_backtest")

    data_dir = _make_data(tmp_path)
    ran = []
    monkeypatch.setattr(RB, "_run_one_event",
                        lambda ev, params, root: ran.append(ev) or [])

    rows = run_backtest({"event_ids": ["200", "201"], "min_coverage": 90.0},
                        data_dir=data_dir)

    assert ran == ["200"]                               # 201 ESCLUSO dal replay
    m = rows[0]["metrics"]
    assert list(m["coverage_events"]) == ["200"]
    assert m["coverage_verdict"] == "COMPLETE"


# ---------------------------------------------------------------------------
# run_theta / run_scalper: stessa guardia + stesso contratto (finding #3/#4)
# ---------------------------------------------------------------------------
def test_run_theta_writes_coverage_and_alert(tmp_path, monkeypatch, alerts):
    import Betfair.stream.scalper.run_theta as RT

    data_dir = _make_data(tmp_path)
    monkeypatch.setattr(RT, "_run_one_event",
                        lambda ev, params, root, atlas: [])

    rows = RT.run_theta({"event_ids": ["200", "201"], "theta": {"atlas": {}}},
                        data_dir=data_dir)

    m = rows[0]["metrics"]
    assert m["coverage_verdict"] == "PARTIAL"
    assert m["coverage_events"]["201"]["coverage_verdict"] == "PARTIAL"
    assert [(a[0], a[1], a[3]) for a in alerts] == [
        ("WARN", "BACKTEST_COVERAGE", "201")]
    assert alerts[0][2].startswith("theta:")


def test_run_scalper_guard_and_coverage(tmp_path, monkeypatch, alerts):
    import Betfair.stream.scalper.run_scalper as RS

    data_dir = _make_data(tmp_path)
    ran = []
    monkeypatch.setattr(RS, "_run_one_event",
                        lambda ev, params, root: ran.append(ev) or [])

    # default: warning-only, TUTTI gli eventi girano, coverage nei risultati
    rows = RS.run_scalper({"event_ids": ["200", "201"]}, data_dir=data_dir)
    assert ran == ["200", "201"]
    m = rows[0]["metrics"]
    assert m["coverage_verdict"] == "PARTIAL"
    assert [(a[0], a[1], a[3]) for a in alerts] == [
        ("WARN", "BACKTEST_COVERAGE", "201")]

    # min_coverage: filtro attivo (finding #4: run_scalper non era guardato)
    ran.clear()
    rows = RS.run_scalper({"event_ids": ["200", "201"], "min_coverage": 90.0},
                          data_dir=data_dir)
    assert ran == ["200"]

    # filtro che svuota la lista → ValueError esplicito (mai "verde" su zero eventi)
    with pytest.raises(ValueError, match="copertura"):
        RS.run_scalper({"event_ids": ["201"], "min_coverage": 90.0},
                       data_dir=data_dir)
