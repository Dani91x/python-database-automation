"""Test del curator: write-on-change con throttle, ladder DB, minuto da timeline."""
from __future__ import annotations

import json
import os

from Betfair.stream.curator import curate_event, ladder_db_format


def _write_jsonl(tmp_path, lines):
    p = os.path.join(tmp_path, "ev.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        for obj in lines:
            fh.write(json.dumps(obj) + "\n")
    return p


def _book(market_id, pt, back, lay, status="OPEN", inplay=False):
    return {
        "market_id": market_id,
        "pt": pt,
        "status": status,
        "inplay": inplay,
        "tv": 100.0,
        "runners": {"11": {"b": [[back, 50.0]], "l": [[lay, 50.0]], "ltp": back, "tv": 10.0}},
    }


def test_first_snapshot_always_kept(tmp_path):
    p = _write_jsonl(tmp_path, [_book("1.1", 1000, 2.0, 2.02)])
    rows = curate_event(p, "ev1", cadence_sec=10)
    assert len(rows) == 1
    assert rows[0]["event_id"] == "ev1"
    assert rows[0]["market_id"] == "1.1"


def test_unchanged_within_cadence_is_dropped(tmp_path):
    # stesso prezzo a 1s di distanza, cadenza 10s → la 2a si scarta
    p = _write_jsonl(
        tmp_path,
        [_book("1.1", 1000, 2.0, 2.02), _book("1.1", 2000, 2.0, 2.02)],
    )
    rows = curate_event(p, "ev1", cadence_sec=10)
    assert len(rows) == 1


def test_price_change_is_kept(tmp_path):
    p = _write_jsonl(
        tmp_path,
        [_book("1.1", 1000, 2.0, 2.02), _book("1.1", 2000, 2.5, 2.52)],
    )
    rows = curate_event(p, "ev1", cadence_sec=10)
    assert len(rows) == 2
    # ladder convertito in formato DB
    assert rows[1]["ladder"]["11"]["back"] == [[2.5, 50.0]]
    assert rows[1]["ladder"]["11"]["lay"] == [[2.52, 50.0]]


def test_throttle_keeps_after_cadence_even_if_unchanged(tmp_path):
    # invariato ma a 11s → la cadenza (10s) ne forza la conservazione
    p = _write_jsonl(
        tmp_path,
        [_book("1.1", 1000, 2.0, 2.02), _book("1.1", 12000, 2.0, 2.02)],
    )
    rows = curate_event(p, "ev1", cadence_sec=10)
    assert len(rows) == 2


def test_independent_markets(tmp_path):
    p = _write_jsonl(
        tmp_path,
        [_book("1.1", 1000, 2.0, 2.02), _book("1.2", 1000, 1.5, 1.52)],
    )
    rows = curate_event(p, "ev1", cadence_sec=10)
    assert {r["market_id"] for r in rows} == {"1.1", "1.2"}


def test_minute_from_timeline(tmp_path):
    p = _write_jsonl(tmp_path, [_book("1.1", 5000, 2.0, 2.02, inplay=True)])
    timeline = [{"ts_ms": 1000, "minute": 0}, {"ts_ms": 4000, "minute": 36}, {"ts_ms": 9000, "minute": 50}]
    rows = curate_event(p, "ev1", cadence_sec=10, timeline=timeline)
    assert rows[0]["minute"] == 36  # ultimo <= 5000


def test_corrupted_line_skipped(tmp_path):
    p = os.path.join(tmp_path, "ev.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(_book("1.1", 1000, 2.0, 2.02)) + "\n")
        fh.write("{ this is not json\n")
        fh.write(json.dumps(_book("1.1", 2000, 3.0, 3.02)) + "\n")
    rows = curate_event(p, "ev1", cadence_sec=10)
    assert len(rows) == 2


def test_pt_none_unchanged_dropped(tmp_path):
    # pt ignoto + prezzo invariato → solo write-on-change: i duplicati si scartano
    p = _write_jsonl(
        tmp_path,
        [
            _book("1.1", None, 2.0, 2.02),
            _book("1.1", None, 2.0, 2.02),
            _book("1.1", None, 2.5, 2.52),
        ],
    )
    rows = curate_event(p, "ev1", cadence_sec=10)
    assert len(rows) == 2  # il primo + il cambio prezzo (il duplicato scartato)


def test_ladder_db_format():
    out = ladder_db_format({"7": {"b": [[2.0, 5.0]], "l": [[2.1, 5.0]], "ltp": 2.0, "tv": 9.0}})
    assert out == {"7": {"back": [[2.0, 5.0]], "lay": [[2.1, 5.0]], "ltp": 2.0, "tv": 9.0}}
