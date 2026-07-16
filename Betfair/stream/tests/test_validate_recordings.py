"""Test della validazione registrazioni raw (COMPLETE/PARTIAL, fix 16/07).

Fixture: file ``.raw.jsonl`` SINTETICI (righe mcm minime con pt +
marketDefinition openDate/status) in una dir temporanea, uno scenario per ogni
fenomeno osservato nei dati reali: completa, inizio tardivo, buco interno,
troncata a fine, solo pre-match, raw mancante, vuota, kickoff ignoto.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest

from Betfair.stream.tools.validate_recordings import (
    VERDICT_COMPLETE,
    VERDICT_EMPTY,
    VERDICT_NO_RAW,
    VERDICT_PARTIAL,
    VERDICT_UNKNOWN,
    check_events_for_backtest,
    iter_event_ids,
    main as validate_main,
    validate_all,
    validate_event,
)

KO_ISO = "2026-07-01T15:00:00.000Z"
KO_MS = int(datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)


def _min(minutes: float) -> int:
    """Offset in ms dal kickoff."""
    return KO_MS + int(minutes * 60_000)


def _md(status: str = "OPEN", inplay: bool = True) -> Dict[str, Any]:
    return {
        "marketType": "MATCH_ODDS",
        "openDate": KO_ISO,
        "marketTime": KO_ISO,
        "status": status,
        "inPlay": inplay,
    }


def _mcm(pt: int, md: Optional[Dict[str, Any]] = None) -> str:
    change: Dict[str, Any] = {"id": "1.234", "rc": [{"id": 111, "ltp": 2.0}]}
    if md is not None:
        change["marketDefinition"] = md
    return json.dumps({"op": "mcm", "clk": "1", "pt": pt, "mc": [change]},
                      separators=(",", ":"))


def _write_raw(data_dir: str, event_id: str, lines: List[str]) -> str:
    ev_dir = os.path.join(data_dir, event_id)
    os.makedirs(ev_dir, exist_ok=True)
    path = os.path.join(ev_dir, f"{event_id}.raw.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    return path


def _span(a_min: float, b_min: float, step_s: float = 30.0) -> List[int]:
    """Sequenza di pt da ko+a_min a ko+b_min a passo step_s."""
    out: List[int] = []
    t = _min(a_min)
    end = _min(b_min)
    while t <= end:
        out.append(t)
        t += int(step_s * 1000)
    return out


def _lines(spans: List[Tuple[float, float]], closed_at_end: bool = False,
           with_md: bool = True) -> List[str]:
    """Righe mcm per una lista di intervalli [(da_min, a_min)] dal kickoff."""
    pts: List[int] = []
    for a, b in spans:
        pts.extend(_span(a, b))
    lines = []
    for i, pt in enumerate(pts):
        md = None
        if with_md and i == 0:
            md = _md("OPEN", inplay=False)
        if closed_at_end and i == len(pts) - 1:
            md = _md("CLOSED")
        lines.append(_mcm(pt, md))
    return lines


# ---------------------------------------------------------------------------
# Classificazione per scenario
# ---------------------------------------------------------------------------
def test_complete_recording(tmp_path):
    _write_raw(str(tmp_path), "100", _lines([(-10, 118)], closed_at_end=True))
    rep = validate_event(str(tmp_path), "100")
    assert rep.verdict == VERDICT_COMPLETE
    assert rep.coverage_pct is not None and rep.coverage_pct >= 99.0
    assert rep.kickoff_ms == KO_MS
    assert rep.closed_seen is True
    assert rep.gaps_in_window == []
    assert rep.reasons == []


def test_late_start_is_partial(tmp_path):
    _write_raw(str(tmp_path), "101", _lines([(60, 118)], closed_at_end=True))
    rep = validate_event(str(tmp_path), "101")
    assert rep.verdict == VERDICT_PARTIAL
    # copre solo [ko+60, ko+115] su 115' attesi → ~47.8%
    assert rep.coverage_pct == pytest.approx(47.8, abs=1.0)
    assert rep.start_delay_min == pytest.approx(60.0, abs=0.1)
    assert any("inizio tardivo" in r for r in rep.reasons)


def test_internal_gap_is_partial(tmp_path):
    _write_raw(str(tmp_path), "102",
               _lines([(-5, 30), (70, 118)], closed_at_end=True))
    rep = validate_event(str(tmp_path), "102")
    assert rep.verdict == VERDICT_PARTIAL
    assert len(rep.gaps_in_window) == 1
    assert rep.gap_in_window_min == pytest.approx(40.0, abs=0.5)
    # 115' - 40' di buco → ~65%
    assert rep.coverage_pct == pytest.approx(65.2, abs=1.0)
    assert any("buchi interni" in r for r in rep.reasons)


def test_truncated_end_is_partial(tmp_path):
    _write_raw(str(tmp_path), "103", _lines([(-5, 40)], closed_at_end=False))
    rep = validate_event(str(tmp_path), "103")
    assert rep.verdict == VERDICT_PARTIAL
    assert rep.closed_seen is False
    assert any("fine troncata" in r for r in rep.reasons)
    assert rep.coverage_pct == pytest.approx(34.8, abs=1.0)


def test_prematch_only_zero_coverage(tmp_path):
    _write_raw(str(tmp_path), "104", _lines([(-30, -5)]))
    rep = validate_event(str(tmp_path), "104")
    assert rep.verdict == VERDICT_PARTIAL
    assert rep.coverage_pct == 0.0
    assert any("solo pre-match" in r for r in rep.reasons)


def test_missing_raw_with_scores(tmp_path):
    ev_dir = tmp_path / "105"
    ev_dir.mkdir()
    (ev_dir / "105.scores.jsonl").write_text('{"minute":10}\n', encoding="utf-8")
    rep = validate_event(str(tmp_path), "105")
    assert rep.verdict == VERDICT_NO_RAW
    assert rep.coverage_pct == 0.0
    assert rep.has_scores is True


def test_empty_raw(tmp_path):
    _write_raw(str(tmp_path), "106", [])
    rep = validate_event(str(tmp_path), "106")
    assert rep.verdict == VERDICT_EMPTY
    assert rep.coverage_pct == 0.0


def test_unknown_kickoff(tmp_path):
    # nessuna marketDefinition → kickoff non determinabile
    _write_raw(str(tmp_path), "107", _lines([(0, 30)], with_md=False))
    rep = validate_event(str(tmp_path), "107")
    assert rep.verdict == VERDICT_UNKNOWN
    assert rep.coverage_pct is None


def test_corrupt_lines_tolerated(tmp_path):
    lines = _lines([(-5, 118)], closed_at_end=True)
    lines.insert(3, "{corrotto???")
    lines.insert(7, '{"op":"status","statusCode":"FAILURE"}')
    _write_raw(str(tmp_path), "108", lines)
    rep = validate_event(str(tmp_path), "108")
    assert rep.verdict == VERDICT_COMPLETE


def test_recmeta_sessions_loaded(tmp_path):
    _write_raw(str(tmp_path), "109", _lines([(-5, 118)], closed_at_end=True))
    meta = tmp_path / "109" / "109.recmeta.jsonl"
    meta.write_text(
        '{"kind":"open","ts_ms":1,"raw_bytes_at_open":0}\n'
        '{"kind":"close","ts_ms":2,"last_pt_ms":3}\n', encoding="utf-8")
    rep = validate_event(str(tmp_path), "109")
    assert len(rep.sessions) == 2
    assert rep.sessions[0]["kind"] == "open"


# ---------------------------------------------------------------------------
# Enumerazione + guardia backtest
# ---------------------------------------------------------------------------
def _make_pair(tmp_path) -> None:
    """Un evento COMPLETE (200) e uno PARTIAL (201)."""
    _write_raw(str(tmp_path), "200", _lines([(-10, 118)], closed_at_end=True))
    _write_raw(str(tmp_path), "201", _lines([(60, 118)], closed_at_end=True))


def test_iter_event_ids_skips_reserved_dirs(tmp_path):
    _make_pair(tmp_path)
    (tmp_path / "_synth_x").mkdir()
    (tmp_path / ".ruff_cache").mkdir()
    (tmp_path / "no_sidecar").mkdir()
    assert iter_event_ids(str(tmp_path)) == ["200", "201"]


def test_validate_all(tmp_path):
    _make_pair(tmp_path)
    reports = {r.event_id: r for r in validate_all(str(tmp_path))}
    assert reports["200"].verdict == VERDICT_COMPLETE
    assert reports["201"].verdict == VERDICT_PARTIAL


def test_check_events_default_keeps_all_with_warning(tmp_path, caplog):
    _make_pair(tmp_path)
    with caplog.at_level("WARNING"):
        kept = check_events_for_backtest(["200", "201"], str(tmp_path), None)
    assert kept == ["200", "201"]  # zero regressioni: nessun filtro di default
    assert any("201" in rec.message and "PARTIAL" in rec.message
               for rec in caplog.records)


def test_check_events_min_coverage_filters(tmp_path):
    _make_pair(tmp_path)
    kept = check_events_for_backtest(["200", "201"], str(tmp_path), 90.0)
    assert kept == ["200"]


def test_check_events_min_coverage_all_filtered_raises(tmp_path):
    _write_raw(str(tmp_path), "201", _lines([(60, 118)], closed_at_end=True))
    with pytest.raises(ValueError, match="copertura"):
        check_events_for_backtest(["201"], str(tmp_path), 90.0)


def test_check_events_unknown_kept_with_min_coverage(tmp_path):
    _write_raw(str(tmp_path), "202", _lines([(0, 30)], with_md=False))
    kept = check_events_for_backtest(["202"], str(tmp_path), 90.0)
    assert kept == ["202"]  # kickoff ignoto: incluso per prudenza


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_text_and_ids_only(tmp_path, capsys):
    _make_pair(tmp_path)
    assert validate_main(["--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "COMPLETE" in out and "PARTIAL" in out
    assert "1 COMPLETE" in out

    assert validate_main(["--data-dir", str(tmp_path), "--ids-only"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["200"]


def test_cli_json(tmp_path, capsys):
    _make_pair(tmp_path)
    assert validate_main(["--data-dir", str(tmp_path), "--json", "201"]) == 0
    row = json.loads(capsys.readouterr().out.strip())
    assert row["event_id"] == "201"
    assert row["verdict"] == VERDICT_PARTIAL
