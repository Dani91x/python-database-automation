"""Test degli helper di RIPRESA A6 (db.cleanup_paper_mirror / fail_stale_pending_requests).

MONEY-CRITICAL sotto test (fix review MEDIUM: la garanzia "mai righe LIVE"
dipendeva SOLO dai filtri delle query, senza alcun test):
  - cleanup_paper_mirror: delete SOLO con filtro mode='paper' su entrambe le tabelle;
  - fail_stale_pending_requests: pending stantie → error; processing stantie →
    error con esito INCERTO dichiarato, ESCLUSA l'azione place_submin (macchina
    a stati ripristinabile); cutoff applicato a requested_at.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

import Betfair.stream.db as db


class _Query:
    def __init__(self, log: List[Dict[str, Any]], table: str) -> None:
        self._log = log
        self._entry: Dict[str, Any] = {"table": table, "op": None, "filters": []}

    def delete(self):
        self._entry["op"] = "delete"
        return self

    def update(self, payload):
        self._entry["op"] = "update"
        self._entry["payload"] = dict(payload)
        return self

    def eq(self, k, v):
        self._entry["filters"].append(("eq", k, v))
        return self

    def neq(self, k, v):
        self._entry["filters"].append(("neq", k, v))
        return self

    def lt(self, k, v):
        self._entry["filters"].append(("lt", k, v))
        return self

    def execute(self):
        self._log.append(self._entry)
        return SimpleNamespace(data=[{"id": 1}])


class _Sb:
    def __init__(self) -> None:
        self.log: List[Dict[str, Any]] = []

    def table(self, name: str) -> _Query:
        return _Query(self.log, name)


@pytest.fixture()
def sb(monkeypatch) -> _Sb:
    fake = _Sb()
    monkeypatch.setattr(db, "get_supabase_client", lambda: fake)
    return fake


def test_cleanup_paper_mirror_deletes_only_paper_rows(sb):
    n_o, n_p = db.cleanup_paper_mirror()
    assert (n_o, n_p) == (1, 1)
    assert len(sb.log) == 2
    tables = {e["table"] for e in sb.log}
    assert tables == {"betfair_live_orders", "betfair_live_positions"}
    for e in sb.log:
        assert e["op"] == "delete"
        # UNICO filtro: mode='paper' — le righe LIVE non vengono MAI toccate.
        assert e["filters"] == [("eq", "mode", "paper")]


def test_fail_stale_pending_marks_pending_and_processing(sb):
    n = db.fail_stale_pending_requests(120.0)
    assert n == 2  # 1 pending + 1 processing (fake ritorna 1 riga per update)
    assert len(sb.log) == 2
    pend, proc = sb.log
    assert pend["op"] == "update" and pend["payload"]["status"] == "error"
    assert ("eq", "status", "pending") in pend["filters"]
    assert any(f[0] == "lt" and f[1] == "requested_at" for f in pend["filters"])
    # processing: esito INCERTO dichiarato + submin ESCLUSA
    assert proc["payload"]["status"] == "error"
    assert "INCERTO" in proc["payload"]["error"]
    assert ("eq", "status", "processing") in proc["filters"]
    assert ("neq", "action", "place_submin") in proc["filters"]
    assert any(f[0] == "lt" and f[1] == "requested_at" for f in proc["filters"])


def test_fail_stale_cutoff_respects_max_age(sb, monkeypatch):
    from datetime import datetime, timezone

    fixed = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

    class _FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(db, "datetime", _FixedDT)
    db.fail_stale_pending_requests(300.0)
    cutoffs = [f[2] for e in sb.log for f in e["filters"] if f[0] == "lt"]
    assert all(c == "2026-07-09T11:55:00+00:00" for c in cutoffs)
