"""Unit test di ``Betfair/stream/db.upsert_live_order`` — ANTI-GHOST (HIGH-2).

Money-critical: NESSUNA rete, NESSUN login, NESSUN ordine reale. Il client Supabase è un
FAKE in-memory che modella FEDELMENTE i due indici UNIQUE PARZIALI della migrazione
``betfair_live_order_queue.sql``:

  * ``idx_blo_mode_bet``  → UNIQUE (mode, bet_id)           WHERE bet_id IS NOT NULL
  * ``idx_blo_mode_cref`` → UNIQUE (mode, client_order_ref) WHERE bet_id IS NULL

Con questa semantica un upsert ``on_conflict='mode,bet_id'`` NON vede una riga con
``bet_id IS NULL`` (vive nell'altro indice): il vecchio codice inseriva quindi una riga
DUPLICATA lasciando viva la riga PENDING → ordine GHOST. Il fix promuove prima la riga
PENDING (UPDATE) e poi fa l'upsert idempotente: UNA sola riga.

Scenari:
  - transizione bet_id NULL → bet_id assegnato produce UNA sola riga (no ghost);
  - promozione idempotente: ri-scritture successive restano una sola riga;
  - ramo solo-bet_id (nessuna riga PENDING precedente) → un singolo insert;
  - ramo solo-cref (ordine PENDING) → upsert sull'indice per-cref.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.db as db


# ---------------------------------------------------------------------------
# Fake Supabase che rispetta i DUE indici UNIQUE PARZIALI
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, store: List[Dict[str, Any]]) -> None:
        self._store = store
        self._op: Optional[str] = None
        self._payload: Dict[str, Any] = {}
        self._on_conflict: Optional[str] = None
        self._eq: List[tuple] = []
        self._is_null: List[str] = []

    def upsert(self, payload: Dict[str, Any], on_conflict: Optional[str] = None) -> "_FakeTable":
        self._op = "upsert"
        self._payload = dict(payload)
        self._on_conflict = on_conflict
        return self

    def update(self, payload: Dict[str, Any]) -> "_FakeTable":
        self._op = "update"
        self._payload = dict(payload)
        return self

    def eq(self, k: str, v: Any) -> "_FakeTable":
        self._eq.append((k, v))
        return self

    def is_(self, k: str, _v: Any) -> "_FakeTable":
        # nei nostri usi è sempre IS NULL
        self._is_null.append(k)
        return self

    def execute(self) -> _FakeResp:
        if self._op == "update":
            return self._do_update()
        if self._op == "upsert":
            return self._do_upsert()
        raise NotImplementedError(self._op)

    def _do_update(self) -> _FakeResp:
        out: List[Dict[str, Any]] = []
        for r in self._store:
            if all(r.get(k) == v for k, v in self._eq) and all(
                r.get(c) is None for c in self._is_null
            ):
                r.update(self._payload)
                out.append(dict(r))
        return _FakeResp(out)

    def _do_upsert(self) -> _FakeResp:
        keys = [k.strip() for k in (self._on_conflict or "").split(",")]
        p = self._payload
        by_bet = "bet_id" in keys
        match: Optional[Dict[str, Any]] = None
        for r in self._store:
            # semantica indice PARZIALE: per (mode,bet_id) solo righe con bet_id NOT NULL;
            # per (mode,client_order_ref) solo righe con bet_id NULL.
            if by_bet and r.get("bet_id") is None:
                continue
            if not by_bet and r.get("bet_id") is not None:
                continue
            if all(r.get(k) == p.get(k) for k in keys):
                match = r
                break
        if match is not None:
            match.update(p)
            return _FakeResp([dict(match)])
        self._store.append(dict(p))
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
# HIGH-2: transizione bet_id NULL → bet_id assegnato = UNA sola riga (no ghost)
# ===========================================================================
def test_pending_then_betid_promotes_single_row_no_ghost(fake_sb):
    # 1) ordine PENDING: bet_id NULL → vive nell'indice per-cref
    db.upsert_live_order(_row(bet_id=None, status="PENDING", size_matched=0.0))
    assert len(_orders(fake_sb)) == 1
    assert _orders(fake_sb)[0]["bet_id"] is None

    # 2) bet_id assegnato (+ fill): DEVE promuovere la riga NULL, non crearne una nuova
    db.upsert_live_order(
        _row(bet_id="B1", status="EXECUTABLE", size_matched=2.0, size_remaining=3.0)
    )

    rows = _orders(fake_sb)
    assert len(rows) == 1                      # ← niente riga GHOST
    assert rows[0]["bet_id"] == "B1"           # riga promossa
    assert rows[0]["client_order_ref"] == "awlq1"
    assert rows[0]["status"] == "EXECUTABLE"
    assert rows[0]["size_matched"] == 2.0
    # nessuna riga residua con bet_id NULL
    assert not any(r["bet_id"] is None for r in rows)


def test_promotion_is_idempotent_single_row(fake_sb):
    db.upsert_live_order(_row(bet_id=None, status="PENDING"))
    db.upsert_live_order(_row(bet_id="B1", status="EXECUTABLE", size_matched=2.0))
    # ulteriori fill sullo stesso bet_id → sempre una sola riga aggiornata
    db.upsert_live_order(_row(bet_id="B1", status="EXECUTION_COMPLETE", size_matched=5.0))
    db.upsert_live_order(_row(bet_id="B1", status="EXECUTION_COMPLETE", size_matched=5.0))

    rows = _orders(fake_sb)
    assert len(rows) == 1
    assert rows[0]["status"] == "EXECUTION_COMPLETE"
    assert rows[0]["size_matched"] == 5.0


def test_first_write_with_betid_inserts_single_row(fake_sb):
    # nessun PENDING precedente: ordine nasce già con bet_id → un solo insert
    db.upsert_live_order(_row(bet_id="B9", status="EXECUTABLE", size_matched=1.0))
    rows = _orders(fake_sb)
    assert len(rows) == 1
    assert rows[0]["bet_id"] == "B9"


def test_pending_only_writes_one_row_on_cref_index(fake_sb):
    db.upsert_live_order(_row(bet_id=None, status="PENDING"))
    # ri-scrittura PENDING (es. ancora senza bet_id) → resta una sola riga
    db.upsert_live_order(_row(bet_id=None, status="PENDING", size=6.0))
    rows = _orders(fake_sb)
    assert len(rows) == 1
    assert rows[0]["bet_id"] is None
    assert rows[0]["size"] == 6.0


def test_distinct_crefs_remain_separate_rows(fake_sb):
    db.upsert_live_order(_row(client_order_ref="awlq1", bet_id="B1", status="EXECUTABLE"))
    db.upsert_live_order(_row(client_order_ref="awlq2", bet_id="B2", status="EXECUTABLE"))
    rows = _orders(fake_sb)
    assert len(rows) == 2
    assert {r["bet_id"] for r in rows} == {"B1", "B2"}
