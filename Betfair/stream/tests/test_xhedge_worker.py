"""Unit test dell'xhedge_worker: calcola l'analisi cross-market e la scrive (upsert).
NESSUNA rete: session, recorder e coda sono mock; la matematica usa trading/xhedge reale."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

import Betfair.stream.xhedge_worker as xw


class _Sel:
    def __init__(self, store, filters=None):
        self._store = store
        self._filters = filters or []
        self._op = None
        self._payload = None
        self._conflict = None

    def select(self, *_a):
        self._op = "select"
        return self

    def eq(self, k, v):
        self._filters.append((k, v))
        return self

    def upsert(self, payload, on_conflict=None):
        self._op = "upsert"
        self._payload = payload
        self._conflict = on_conflict
        return self

    def execute(self):
        if self._op == "select":
            rows = [r for r in self._store["orders"] if all(r.get(k) == v for k, v in self._filters)]
            return SimpleNamespace(data=[dict(r) for r in rows])
        if self._op == "upsert":
            self._store["upserts"].append(self._payload)
            return SimpleNamespace(data=[self._payload])
        return SimpleNamespace(data=[])


class _Sb:
    def __init__(self, orders):
        self.store = {"orders": orders, "upserts": []}

    def table(self, name):
        return _Sel(self.store)


class _Recorder:
    def __init__(self, books):
        self._books = books

    def latest_books(self):
        return self._books


def _session(orders_event="EVT1"):
    markets = [
        {"market_id": "1.1", "market_type": "MATCH_ODDS",
         "selections": [{"selection_id": 10, "name": "Inter", "sort_priority": 1},
                        {"selection_id": 11, "name": "Milan", "sort_priority": 2},
                        {"selection_id": 12, "name": "The Draw", "sort_priority": 3}]},
        {"market_id": "1.2", "market_type": "CORRECT_SCORE",
         "selections": [{"selection_id": 30, "name": "0 - 0", "sort_priority": 1}]},
    ]
    books = {"1.2": {"runners": {"30": {"b": [[8.0, 100.0]]}}}}
    return SimpleNamespace(
        markets_by_event={orders_event: markets},
        finished_events=set(),
        recorder=_Recorder(books),
    )


@pytest.fixture(autouse=True)
def _paper(monkeypatch):
    monkeypatch.setattr(xw.low, "_live_order_mode", lambda: "PAPER")


def test_xhedge_worker_computes_and_upserts():
    orders = [
        {"event_id": "EVT1", "mode": "paper", "market_id": "1.2", "selection_id": 30,
         "side": "lay", "average_price_matched": 8.0, "size_matched": 10.0,
         "client_order_ref": "awlq7"},
    ]
    sb = _Sb(orders)
    n = xw._process_once(sb, _session())
    assert n == 1
    assert len(sb.store["upserts"]) == 1
    up = sb.store["upserts"][0]
    assert up["event_id"] == "EVT1" and up["mode"] == "paper"
    analysis = up["analysis"]
    assert analysis["n_positions"] == 1
    assert analysis["summary"]["worst"] == -70.0        # lay 0-0 10@8 → worst se 0-0
    assert analysis["suggestion"]["actionable"] is True  # copertura suggerita (quota CS 8.0 dal book)


def test_xhedge_worker_skips_event_without_matched_orders():
    sb = _Sb(orders=[])   # nessun ordine abbinato
    n = xw._process_once(sb, _session())
    assert n == 0 and sb.store["upserts"] == []


def test_xhedge_worker_skips_finished_event():
    sess = _session()
    sess.finished_events = {"EVT1"}
    orders = [{"event_id": "EVT1", "mode": "paper", "market_id": "1.2", "selection_id": 30,
               "side": "lay", "average_price_matched": 8.0, "size_matched": 10.0,
               "client_order_ref": "awlq7"}]
    sb = _Sb(orders)
    assert xw._process_once(sb, sess) == 0 and sb.store["upserts"] == []


def test_xhedge_worker_esclude_gli_ordini_dei_bot_scalper():
    """Review 16/07 (2ª passata): il mirror delle sessioni scalper scrive nello
    specchio ordini con ref hash flumine (non-awlq). L'xhedge NON deve sommarli:
    è esposizione dei BOT (gestita dai bot) — sommarla gonfierebbe il worst e
    l'auto-hedge piazzerebbe coperture REALI sul libro dei bot."""
    orders = [
        # ordine manuale/coda: incluso
        {"event_id": "EVT1", "mode": "paper", "market_id": "1.2", "selection_id": 30,
         "side": "lay", "average_price_matched": 8.0, "size_matched": 10.0,
         "client_order_ref": "awlq7"},
        # ordine del mirror scalper (ref hash flumine): ESCLUSO
        {"event_id": "EVT1", "mode": "paper", "market_id": "1.1", "selection_id": 10,
         "side": "back", "average_price_matched": 2.0, "size_matched": 500.0,
         "client_order_ref": "scalper-1.1-abcdef"},
    ]
    sb = _Sb(orders)
    n = xw._process_once(sb, _session())
    assert n == 1
    analysis = sb.store["upserts"][0]["analysis"]
    assert analysis["n_positions"] == 1                  # SOLO l'ordine awlq
    assert analysis["summary"]["worst"] == -70.0         # invariato: il bot non pesa


def test_xhedge_worker_solo_bot_niente_analisi():
    """Evento con SOLI ordini bot: nessuna analisi (status-quo-ante, prima del
    16/07 quelle righe non esistevano nello specchio)."""
    orders = [
        {"event_id": "EVT1", "mode": "paper", "market_id": "1.1", "selection_id": 10,
         "side": "back", "average_price_matched": 2.0, "size_matched": 500.0,
         "client_order_ref": "scalper-1.1-abcdef"},
    ]
    sb = _Sb(orders)
    assert xw._process_once(sb, _session()) == 0
    assert sb.store["upserts"] == []
