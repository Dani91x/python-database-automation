"""Test finding #2 (17/07) — validatore CIECO oltre KO+115'.

Prima: finestra attesa fissa [KO, KO+115'] → una partita andata ai
SUPPLEMENTARI con la fase decisiva assente veniva dichiarata COMPLETE.
Ora la fine vera viene dai marcatori nel raw:
  * CLOSED di un mercato PRINCIPALE → fine reale nota (finestra = [KO, closed]);
  * attività oltre KO+115' senza CLOSED → finestra estesa all'ultima attività;
  * NESSUN CLOSED principale → mai COMPLETE (fine non confermata, motivo esplicito).

In coda: guardia sui PATH raw (lab tennis) + ``complete_event_ids`` (fix #4).
"""
from __future__ import annotations

import pytest

from Betfair.stream.tests.test_validate_recordings import (
    _lines,
    _md,
    _mcm,
    _min,
    _write_raw,
)
from Betfair.stream.tools.validate_recordings import (
    VERDICT_COMPLETE,
    VERDICT_PARTIAL,
    check_raw_paths_for_backtest,
    complete_event_ids,
    validate_event,
    validate_raw_file,
)


# ---------------------------------------------------------------------------
# (a) supplementari / fine non confermata → MAI COMPLETE
# ---------------------------------------------------------------------------
def test_no_closed_high_coverage_not_complete(tmp_path):
    """Registrazione fino al 110' SENZA CLOSED: prima era COMPLETE (95.7%),
    ora la fine non è confermata (recupero lungo/supplementari possibili)."""
    _write_raw(str(tmp_path), "300", _lines([(-5, 110)], closed_at_end=False))
    rep = validate_event(str(tmp_path), "300")
    assert rep.verdict == VERDICT_PARTIAL
    assert rep.closed_seen is False
    assert any("fine NON confermata" in r for r in rep.reasons)


def test_extra_time_activity_extends_window_not_complete(tmp_path):
    """Attività fino al 120' senza CLOSED (supplementari in corso): la
    finestra si estende e il verdetto resta NON complete."""
    _write_raw(str(tmp_path), "301", _lines([(-5, 120)], closed_at_end=False))
    rep = validate_event(str(tmp_path), "301")
    assert rep.verdict == VERDICT_PARTIAL
    assert any("finestra estesa" in r for r in rep.reasons)
    assert any("fine NON confermata" in r for r in rep.reasons)


def test_extra_time_decisive_phase_missing_partial(tmp_path):
    """Supplementari con buco sulla fase decisiva (100'→125') e CLOSED al 126':
    la finestra reale è [KO, 126'] → il buco pesa → PARTIAL."""
    _write_raw(str(tmp_path), "302",
               _lines([(-5, 100), (125, 126)], closed_at_end=True))
    rep = validate_event(str(tmp_path), "302")
    assert rep.verdict == VERDICT_PARTIAL
    assert rep.closed_seen is True
    # buco 100'→125' dentro la finestra estesa dal CLOSED
    assert rep.gap_in_window_min == pytest.approx(25.0, abs=0.5)
    assert rep.coverage_pct is not None and rep.coverage_pct < 90.0


def test_extra_time_fully_recorded_complete(tmp_path):
    """Supplementari registrati fino in fondo + CLOSED al 126' → COMPLETE."""
    _write_raw(str(tmp_path), "303", _lines([(-5, 126)], closed_at_end=True))
    rep = validate_event(str(tmp_path), "303")
    assert rep.verdict == VERDICT_COMPLETE
    assert rep.coverage_pct is not None and rep.coverage_pct >= 99.0


# ---------------------------------------------------------------------------
# (b) partita regolare con CLOSED → COMPLETE legittimo
# ---------------------------------------------------------------------------
def test_regular_match_closed_before_115_complete(tmp_path):
    """Partita chiusa al 100' (CLOSED nel raw): la fine vera è nota → COMPLETE.
    (Prima: coverage 100/115 = 87% → PARTIAL a torto.)"""
    _write_raw(str(tmp_path), "304", _lines([(-5, 100)], closed_at_end=True))
    rep = validate_event(str(tmp_path), "304")
    assert rep.verdict == VERDICT_COMPLETE
    assert rep.coverage_pct is not None and rep.coverage_pct >= 99.0
    assert rep.closed_seen is True


def test_half_time_market_closed_does_not_confirm_end(tmp_path):
    """CLOSED di un mercato di PRIMO TEMPO (chiude all'intervallo) NON prova
    la fine della partita → fine non confermata, mai COMPLETE."""
    lines = _lines([(-5, 110)], closed_at_end=False)
    ht_md = dict(_md("CLOSED"))
    ht_md["marketType"] = "FIRST_HALF_GOALS_25"
    lines.append(_mcm(_min(110) + 1_000, ht_md))
    _write_raw(str(tmp_path), "305", lines)
    rep = validate_event(str(tmp_path), "305")
    assert rep.verdict == VERDICT_PARTIAL
    assert rep.closed_seen is True                  # un CLOSED c'è, ma non principale
    assert any("fine NON confermata" in r for r in rep.reasons)


# ---------------------------------------------------------------------------
# Guardia sui PATH raw (lab tennis: tune/lab_grid/flb/validate — fix #4)
# ---------------------------------------------------------------------------
def _make_paths(tmp_path):
    p_ok = _write_raw(str(tmp_path), "400", _lines([(-10, 118)], closed_at_end=True))
    p_bad = _write_raw(str(tmp_path), "401", _lines([(60, 118)], closed_at_end=True))
    return p_ok, p_bad


def test_check_raw_paths_default_warns_keeps_all(tmp_path, caplog):
    p_ok, p_bad = _make_paths(tmp_path)
    with caplog.at_level("WARNING"):
        kept = check_raw_paths_for_backtest([p_ok, p_bad], None)
    assert kept == [p_ok, p_bad]  # default: nessun filtro, solo warning visibile
    assert any("401" in rec.message and "PARTIAL" in rec.message
               for rec in caplog.records)


def test_check_raw_paths_min_coverage_filters(tmp_path):
    p_ok, p_bad = _make_paths(tmp_path)
    assert check_raw_paths_for_backtest([p_ok, p_bad], 90.0) == [p_ok]


def test_check_raw_paths_all_filtered_raises(tmp_path):
    _p_ok, p_bad = _make_paths(tmp_path)
    with pytest.raises(ValueError, match="copertura"):
        check_raw_paths_for_backtest([p_bad], 90.0)


def test_validate_raw_file_missing(tmp_path):
    rep = validate_raw_file(str(tmp_path / "nope" / "nope.raw.jsonl"))
    assert rep.verdict == "NO_RAW"


def test_validate_raw_file_flat_layout(tmp_path):
    """Layout flat (file direttamente in data_dir, come alcuni raw tennis)."""
    path = tmp_path / "500.raw.jsonl"
    path.write_text("\n".join(_lines([(-10, 118)], closed_at_end=True)) + "\n",
                    encoding="utf-8")
    rep = validate_raw_file(str(path))
    assert rep.event_id == "500"
    assert rep.verdict == VERDICT_COMPLETE


# ---------------------------------------------------------------------------
# complete_event_ids: filtro a RUNTIME che sostituisce le liste hardcoded
# ---------------------------------------------------------------------------
def test_complete_event_ids_runtime_filter(tmp_path):
    _write_raw(str(tmp_path), "600", _lines([(-10, 118)], closed_at_end=True))
    _write_raw(str(tmp_path), "601", _lines([(60, 118)], closed_at_end=True))
    _write_raw(str(tmp_path), "602", _lines([(-5, 110)], closed_at_end=False))
    assert complete_event_ids(str(tmp_path)) == ["600"]
