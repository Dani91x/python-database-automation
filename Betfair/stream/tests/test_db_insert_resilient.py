"""Unit test di ``Betfair/stream/db.insert_rows_resilient``.

NESSUNA rete: client Supabase FAKE che simula lo ``statement_timeout`` (SQLSTATE
57014) quando un blocco di insert supera una soglia. Verifichiamo che la funzione:
  * dimezzi la dimensione del blocco al timeout e prosegua con quella piu' piccola;
  * inserisca comunque TUTTE le righe;
  * ri-sollevi errori che NON sono timeout (es. tabella mancante) senza mascherarli;
  * fallisca in modo pulito se nemmeno il blocco da 1 riga passa.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

import Betfair.stream.db as db


def _timeout_error() -> Exception:
    # stessa forma con cui postgrest solleva il timeout (dict con code/message)
    return db.APIError({"message": "canceling statement due to statement timeout", "code": "57014"})


def _other_error() -> Exception:
    return db.APIError({"message": 'relation "x" does not exist', "code": "42P01"})


class _FakeResp:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, store: List[Dict[str, Any]], calls: List[int], max_ok: int, err) -> None:
        self._store = store
        self._calls = calls
        self._max_ok = max_ok
        self._err = err
        self._chunk: List[Dict[str, Any]] = []

    def insert(self, chunk: List[Dict[str, Any]]) -> "_FakeTable":
        self._chunk = chunk
        return self

    def execute(self) -> _FakeResp:
        self._calls.append(len(self._chunk))
        if len(self._chunk) > self._max_ok:
            raise self._err()
        self._store.extend(self._chunk)
        return _FakeResp(list(self._chunk))


class _FakeSupabase:
    def __init__(self, max_ok: int, err) -> None:
        self.store: List[Dict[str, Any]] = []
        self.calls: List[int] = []
        self._max_ok = max_ok
        self._err = err

    def table(self, _name: str) -> _FakeTable:
        return _FakeTable(self.store, self.calls, self._max_ok, self._err)


def _install(monkeypatch, max_ok: int, err) -> _FakeSupabase:
    sb = _FakeSupabase(max_ok, err)
    monkeypatch.setattr(db, "get_supabase_client", lambda: sb)
    return sb


def _rows(n: int) -> List[Dict[str, Any]]:
    return [{"event_id": "E1", "k": i} for i in range(n)]


def test_shrinks_on_timeout_and_inserts_everything(monkeypatch):
    sb = _install(monkeypatch, max_ok=250, err=_timeout_error)
    inserted = db.insert_rows_resilient("live_market_snapshots", _rows(1000), start_chunk=500)
    assert inserted == 1000
    assert len(sb.store) == 1000
    # primo tentativo da 500 fallisce, poi prosegue a 250
    assert sb.calls[0] == 500
    assert all(c <= 250 for c in sb.calls[1:])
    # nessuna riga persa o duplicata
    assert sorted(r["k"] for r in sb.store) == list(range(1000))


def test_fast_path_when_chunk_fits(monkeypatch):
    sb = _install(monkeypatch, max_ok=500, err=_timeout_error)
    db.insert_rows_resilient("live_market_snapshots", _rows(1000), start_chunk=500)
    # nessun timeout → blocchi pieni da 500, due sole insert
    assert sb.calls == [500, 500]


def test_non_timeout_error_propagates(monkeypatch):
    sb = _install(monkeypatch, max_ok=250, err=_other_error)
    with pytest.raises(db.APIError):
        db.insert_rows_resilient("live_market_snapshots", _rows(1000), start_chunk=500)
    assert sb.store == []  # non maschera l'errore reale


def test_gives_up_if_single_row_still_times_out(monkeypatch):
    # max_ok=0 → nemmeno una riga passa: dopo aver ridotto a 1, ri-solleva
    _install(monkeypatch, max_ok=0, err=_timeout_error)
    with pytest.raises(db.APIError):
        db.insert_rows_resilient("live_market_snapshots", _rows(10), start_chunk=4)
