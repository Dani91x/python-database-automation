"""Unit test di ``Betfair/stream/db.upsert_live_ladder``.

NESSUNA rete, NESSUN login: il client Supabase e' un FAKE in-memory che modella l'indice
UNIQUE NON parziale della migrazione ``live_ladder.sql``:

  * ``idx_live_ladder_event_market`` → UNIQUE (event_id, market_id)   [NON parziale]

L'``on_conflict`` dell'upsert DEVE puntare a questo indice, altrimenti PostgREST/Postgres
rifiuta con 42P10 ("no unique or exclusion constraint matching the ON CONFLICT
specification") e la ladder non verrebbe MAI scritta. Una riga per (event_id, market_id),
aggiornata in place (write-on-change) → niente righe duplicate.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.db as db


class _FakeResp:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, store: List[Dict[str, Any]]) -> None:
        self._store = store
        self._payload: Dict[str, Any] = {}
        self._on_conflict: Optional[str] = None

    def upsert(self, payload: Dict[str, Any], on_conflict: Optional[str] = None) -> "_FakeTable":
        self._payload = dict(payload)
        self._on_conflict = on_conflict
        return self

    def execute(self) -> _FakeResp:
        keys = [k.strip() for k in (self._on_conflict or "").split(",") if k.strip()]
        # la chiave NON parziale della migrazione e' (event_id, market_id).
        assert keys == ["event_id", "market_id"], f"on_conflict inatteso: {self._on_conflict}"
        p = self._payload
        for r in self._store:
            if all(r.get(k) == p.get(k) for k in keys):
                r.update(p)                  # aggiorna in place (idempotente, no duplicati)
                return _FakeResp([dict(r)])
        self._store.append(dict(p))          # nuova riga
        return _FakeResp([dict(p)])


class _FakeSupabase:
    def __init__(self) -> None:
        self.tables: Dict[str, List[Dict[str, Any]]] = {}

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self.tables.setdefault(name, []))


@pytest.fixture
def fake_sb(monkeypatch) -> _FakeSupabase:
    sb = _FakeSupabase()
    monkeypatch.setattr(db, "get_supabase_client", lambda: sb)
    return sb


def _ladders(sb: _FakeSupabase) -> List[Dict[str, Any]]:
    return sb.tables.get("live_ladder", [])


def _row(**kw: Any) -> Dict[str, Any]:
    base = {
        "event_id": "31.999",
        "market_id": "1.1",
        "market_type": "MATCH_ODDS",
        "market_name": "Match Odds",
        "status": "OPEN",
        "ladder": {"updated_ms": 1, "selections": []},
    }
    base.update(kw)
    return base


def test_upsert_inserts_single_row_and_forces_updated_at(fake_sb):
    db.upsert_live_ladder(_row())
    rows = _ladders(fake_sb)
    assert len(rows) == 1
    assert rows[0]["market_id"] == "1.1"
    assert "updated_at" in rows[0]            # forzato ad ogni scrittura


def test_upsert_same_market_updates_in_place(fake_sb):
    db.upsert_live_ladder(_row(status="OPEN"))
    db.upsert_live_ladder(_row(status="SUSPENDED", ladder={"updated_ms": 2, "selections": []}))
    rows = _ladders(fake_sb)
    assert len(rows) == 1                      # stessa (event_id, market_id) → una sola riga
    assert rows[0]["status"] == "SUSPENDED"
    assert rows[0]["ladder"]["updated_ms"] == 2


def test_upsert_distinct_markets_remain_separate(fake_sb):
    db.upsert_live_ladder(_row(market_id="1.1"))
    db.upsert_live_ladder(_row(market_id="1.2"))
    rows = _ladders(fake_sb)
    assert len(rows) == 2
    assert {r["market_id"] for r in rows} == {"1.1", "1.2"}


def test_upsert_same_market_different_events_are_separate(fake_sb):
    db.upsert_live_ladder(_row(event_id="31.1", market_id="1.1"))
    db.upsert_live_ladder(_row(event_id="31.2", market_id="1.1"))
    rows = _ladders(fake_sb)
    assert len(rows) == 2                      # la chiave e' (event_id, market_id)
