"""Unit test di ``Betfair/stream/db.delete_event_rows``.

NESSUNA rete: client Supabase FAKE in-memory che modella select(id)+eq+limit e
delete+in_(id). Il punto della funzione: cancellare TUTTE le righe di un evento a
piccoli blocchi per PK, invece della delete monolitica ``delete().eq(event_id)``
che su eventi grandi supera lo ``statement_timeout`` di Postgres (57014). Qui
verifichiamo che:
  * cancella tutte le righe dell'evento anche su PIU' pagine (select_page piccola);
  * NON tocca le righe di altri eventi;
  * spezza la delete in blocchi <= delete_chunk (URL PostgREST ``id=in.(...)`` corto).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.db as db


class _FakeResp:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, store: List[Dict[str, Any]], delete_sizes: List[int]) -> None:
        self._store = store
        self._delete_sizes = delete_sizes  # traccia la dimensione di ogni delete (chunking)
        self._mode: Optional[str] = None
        self._eq: Dict[str, Any] = {}
        self._limit: Optional[int] = None
        self._in: Optional[tuple] = None

    def select(self, *_cols: str) -> "_FakeTable":
        self._mode = "select"
        return self

    def delete(self) -> "_FakeTable":
        self._mode = "delete"
        return self

    def eq(self, col: str, val: Any) -> "_FakeTable":
        self._eq[col] = val
        return self

    def limit(self, n: int) -> "_FakeTable":
        self._limit = n
        return self

    def in_(self, col: str, values: List[Any]) -> "_FakeTable":
        self._in = (col, list(values))
        return self

    def execute(self) -> _FakeResp:
        if self._mode == "select":
            rows = [r for r in self._store if all(r.get(k) == v for k, v in self._eq.items())]
            if self._limit is not None:
                rows = rows[: self._limit]
            return _FakeResp([{"id": r["id"]} for r in rows])
        if self._mode == "delete":
            assert self._in is not None, "delete deve usare in_(id, ...)"
            col, values = self._in
            self._delete_sizes.append(len(values))
            keep = [r for r in self._store if r.get(col) not in set(values)]
            removed = len(self._store) - len(keep)
            self._store[:] = keep
            return _FakeResp([{"id": v} for v in values][:removed])
        raise AssertionError("modo non impostato")


class _FakeSupabase:
    def __init__(self) -> None:
        self.tables: Dict[str, List[Dict[str, Any]]] = {}
        self.delete_sizes: List[int] = []

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self.tables.setdefault(name, []), self.delete_sizes)


@pytest.fixture
def fake_sb(monkeypatch) -> _FakeSupabase:
    sb = _FakeSupabase()
    monkeypatch.setattr(db, "get_supabase_client", lambda: sb)
    return sb


def _seed(sb: _FakeSupabase, table: str, event_id: str, n: int, start_id: int) -> None:
    store = sb.tables.setdefault(table, [])
    for i in range(n):
        store.append({"id": start_id + i, "event_id": event_id})


def test_deletes_all_rows_across_multiple_pages(fake_sb):
    _seed(fake_sb, "live_market_snapshots", "E1", 4500, start_id=1)
    deleted = db.delete_event_rows("live_market_snapshots", "E1", select_page=1000, delete_chunk=500)
    assert deleted == 4500
    assert fake_sb.tables["live_market_snapshots"] == []


def test_does_not_touch_other_events(fake_sb):
    _seed(fake_sb, "live_market_snapshots", "E1", 1200, start_id=1)
    _seed(fake_sb, "live_market_snapshots", "E2", 800, start_id=10_000)
    deleted = db.delete_event_rows("live_market_snapshots", "E1", select_page=500, delete_chunk=500)
    assert deleted == 1200
    remaining = fake_sb.tables["live_market_snapshots"]
    assert len(remaining) == 800
    assert {r["event_id"] for r in remaining} == {"E2"}


def test_delete_is_chunked_to_bound_url_length(fake_sb):
    _seed(fake_sb, "live_market_snapshots", "E1", 1100, start_id=1)
    db.delete_event_rows("live_market_snapshots", "E1", select_page=2000, delete_chunk=500)
    # 1100 righe con chunk 500 → delete da 500, 500, 100 (nessun blocco oltre delete_chunk)
    assert fake_sb.delete_sizes == [500, 500, 100]
    assert all(s <= 500 for s in fake_sb.delete_sizes)


def test_empty_event_no_delete_calls(fake_sb):
    fake_sb.tables.setdefault("live_score_timeline", [])
    deleted = db.delete_event_rows("live_score_timeline", "E404")
    assert deleted == 0
    assert fake_sb.delete_sizes == []
