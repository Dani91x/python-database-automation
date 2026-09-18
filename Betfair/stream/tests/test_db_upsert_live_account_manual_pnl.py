"""Unit test di ``Betfair/stream/db.upsert_live_account_manual_pnl`` (Parte B,
18/09 sera; DUE totali separati dal "terzo giro", stessa sera).

Money-critical: NESSUNA rete, NESSUN login. Verifica che la funzione scriva
SOLO le colonne ``manual_pnl_*``/``manual_app_pnl_*`` (additive, migrazione
``migrations/betfair_live_account_manual_pnl.sql``) sulla riga singleton id=1
di ``betfair_live_account`` — MAI ``available``/``exposure`` (quelle le scrive
SOLO ``upsert_live_account``, un upsert separato: le due funzioni non si
devono mai pestare i piedi sulla stessa riga).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

import Betfair.stream.db as db


class _FakeResp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeTable:
    def __init__(self) -> None:
        self.payload: Optional[Dict[str, Any]] = None
        self.on_conflict: Optional[str] = None

    def upsert(self, payload: Dict[str, Any], on_conflict: Optional[str] = None) -> "_FakeTable":
        self.payload = dict(payload)
        self.on_conflict = on_conflict
        return self

    def execute(self) -> _FakeResp:
        return _FakeResp([dict(self.payload or {})])


class _FakeSb:
    def __init__(self) -> None:
        self.tables: Dict[str, _FakeTable] = {}

    def table(self, name: str) -> _FakeTable:
        return self.tables.setdefault(name, _FakeTable())


@pytest.fixture()
def fake_sb(monkeypatch) -> _FakeSb:
    sb = _FakeSb()
    monkeypatch.setattr(db, "get_supabase_client", lambda: sb)
    return sb


def test_upsert_manual_pnl_writes_only_manual_columns_on_singleton_row(fake_sb):
    db.upsert_live_account_manual_pnl(
        pnl_eur=12.345, is_net=True, orders=3, excluded=1, day="2026-09-18",
        app_pnl_eur=7.891, app_is_net=False, app_orders=2,
    )
    tbl = fake_sb.tables["betfair_live_account"]
    assert tbl.on_conflict == "id"
    assert tbl.payload["id"] == 1
    assert tbl.payload["manual_pnl_eur"] == 12.35   # arrotondato a 2 decimali
    assert tbl.payload["manual_pnl_is_net"] is True
    assert tbl.payload["manual_pnl_orders"] == 3
    assert tbl.payload["manual_pnl_excluded"] == 1
    assert tbl.payload["manual_pnl_day"] == "2026-09-18"
    assert "manual_pnl_updated_at" in tbl.payload
    # terzo giro: totale SEPARATO del terminale manuale della nostra app.
    assert tbl.payload["manual_app_pnl_eur"] == 7.89  # arrotondato
    assert tbl.payload["manual_app_pnl_is_net"] is False
    assert tbl.payload["manual_app_pnl_orders"] == 2
    assert tbl.payload["manual_app_pnl_day"] == "2026-09-18"
    assert "manual_app_pnl_updated_at" in tbl.payload
    # MAI available/exposure: quelle le scrive upsert_live_account (funzione
    # separata) — un payload che le tocca clobbererebbe l'ultimo saldo scritto.
    assert "available" not in tbl.payload
    assert "exposure" not in tbl.payload


def test_upsert_manual_pnl_is_net_false_gross_declared(fake_sb):
    db.upsert_live_account_manual_pnl(
        pnl_eur=-4.0, is_net=False, orders=2, excluded=0, day="2026-09-18",
        app_pnl_eur=0.0, app_is_net=False, app_orders=0,
    )
    tbl = fake_sb.tables["betfair_live_account"]
    assert tbl.payload["manual_pnl_is_net"] is False
    assert tbl.payload["manual_pnl_eur"] == -4.0
