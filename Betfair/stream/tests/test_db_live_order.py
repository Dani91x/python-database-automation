"""Unit test di ``Betfair/stream/db.upsert_live_order``.

Money-critical: NESSUNA rete, NESSUN login, NESSUN ordine reale. Il client Supabase è un
FAKE in-memory che modella l'UNICO indice UNIQUE NON parziale della migrazione
``betfair_live_order_queue.sql``:

  * ``idx_blo_order_key`` → UNIQUE (mode, client_order_ref)   [NON parziale]

Scelta money-critical: l'``on_conflict`` dell'upsert DEVE puntare a un indice NON parziale,
altrimenti PostgREST/Postgres rifiuta con 42P10 ("no unique or exclusion constraint matching
the ON CONFLICT specification") e lo specchio non viene MAI scritto (bug osservato in paper).
``client_order_ref`` (awlq<id>) è sempre presente e unico per ordine → una sola riga per
ordine, aggiornata in place. ``bet_id`` è solo una colonna (NON una chiave) → niente ghost.

Scenari:
  - PENDING (bet_id NULL) → poi bet_id assegnato = SEMPRE una sola riga (la stessa), no ghost;
  - upsert idempotente: ri-scritture successive restano una sola riga aggiornata;
  - primo write già con bet_id → un solo insert;
  - client_order_ref distinti → righe separate.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.db as db


# ---------------------------------------------------------------------------
# Fake Supabase con UNICO indice UNIQUE (mode, client_order_ref), NON parziale
# ---------------------------------------------------------------------------
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
        # money-critical: il codice deve usare la chiave NON parziale (mode, client_order_ref).
        assert keys == ["mode", "client_order_ref"], f"on_conflict inatteso: {self._on_conflict}"
        p = self._payload
        for r in self._store:
            if all(r.get(k) == p.get(k) for k in keys):
                r.update(p)               # aggiorna la riga esistente (idempotente, no ghost)
                return _FakeResp([dict(r)])
        self._store.append(dict(p))       # nuova riga
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


def _orders(sb: _FakeSupabase) -> List[Dict[str, Any]]:
    return sb.tables.get("betfair_live_orders", [])


def _row(**kw: Any) -> Dict[str, Any]:
    base = {
        "client_order_ref": "awlq1",
        "request_id": 1,
        "mode": "paper",
        "event_id": "31.999",
        "market_id": "1.1",
        "selection_id": 47999,
        "handicap": 0.0,
        "side": "back",
        "order_type": "LIMIT",
        "price": 3.0,
        "size": 5.0,
        "size_matched": 0.0,
        "status": "PENDING",
        "bet_id": None,
    }
    base.update(kw)
    return base


# ===========================================================================
# PENDING (bet_id NULL) → bet_id assegnato = UNA sola riga (no ghost), chiave su cref
# ===========================================================================
def test_pending_then_betid_single_row_no_ghost(fake_sb):
    db.upsert_live_order(_row(bet_id=None, status="PENDING", size_matched=0.0))
    assert len(_orders(fake_sb)) == 1
    assert _orders(fake_sb)[0]["bet_id"] is None

    # bet_id assegnato (+ fill): stessa chiave (mode, client_order_ref) → AGGIORNA la riga.
    db.upsert_live_order(
        _row(bet_id="B1", status="EXECUTABLE", size_matched=2.0, size_remaining=3.0)
    )
    rows = _orders(fake_sb)
    assert len(rows) == 1                       # ← niente riga GHOST
    assert rows[0]["bet_id"] == "B1"
    assert rows[0]["client_order_ref"] == "awlq1"
    assert rows[0]["status"] == "EXECUTABLE"
    assert rows[0]["size_matched"] == 2.0
    assert "updated_at" in rows[0]              # forzato ad ogni scrittura


def test_upsert_is_idempotent_single_row(fake_sb):
    db.upsert_live_order(_row(bet_id=None, status="PENDING"))
    db.upsert_live_order(_row(bet_id="B1", status="EXECUTABLE", size_matched=2.0))
    db.upsert_live_order(_row(bet_id="B1", status="EXECUTION_COMPLETE", size_matched=5.0))
    db.upsert_live_order(_row(bet_id="B1", status="EXECUTION_COMPLETE", size_matched=5.0))
    rows = _orders(fake_sb)
    assert len(rows) == 1
    assert rows[0]["status"] == "EXECUTION_COMPLETE"
    assert rows[0]["size_matched"] == 5.0


def test_first_write_with_betid_inserts_single_row(fake_sb):
    db.upsert_live_order(_row(bet_id="B9", status="EXECUTABLE", size_matched=1.0))
    rows = _orders(fake_sb)
    assert len(rows) == 1
    assert rows[0]["bet_id"] == "B9"


def test_distinct_crefs_remain_separate_rows(fake_sb):
    db.upsert_live_order(_row(client_order_ref="awlq1", bet_id="B1", status="EXECUTABLE"))
    db.upsert_live_order(_row(client_order_ref="awlq2", bet_id="B2", status="EXECUTABLE"))
    rows = _orders(fake_sb)
    assert len(rows) == 2
    assert {r["bet_id"] for r in rows} == {"B1", "B2"}
