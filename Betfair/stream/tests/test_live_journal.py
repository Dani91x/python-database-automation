"""Test del trade journal AUTOMATICO (E37) in live_order_worker.

NESSUNA rete: supabase/flumine/db sono fake. Garanzie sotto test:
  - una riga journal per ogni richiesta ESEGUITA, col contesto del momento
    (minuto/score da live_now, book top-3 + LTP dal market_book, segnale attivo);
  - origin: 'risk_rule' se params.risk_rule_id, altrimenti 'manual';
  - il journal è BEST-EFFORT: un errore NON solleva mai (ordini non impattati)
    e produce al massimo UN alert WARN al giorno;
  - il loop principale journala SOLO i dispatch riusciti, mai i falliti.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.live_order_worker as wk


# ---------------------------------------------------------------------------
# Fake supabase: dispatch per tabella
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _SelectQuery:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *_a: Any) -> "_SelectQuery":
        return self

    def eq(self, k: str, v: Any) -> "_SelectQuery":
        self._rows = [r for r in self._rows if r.get(k) == v]
        return self

    def limit(self, n: int) -> "_SelectQuery":
        self._rows = self._rows[:n]
        return self

    def execute(self) -> _Resp:
        return _Resp([dict(r) for r in self._rows])


class _FakeSb:
    def __init__(
        self,
        queue_rows: Optional[List[Dict[str, Any]]] = None,
        live_now: Optional[List[Dict[str, Any]]] = None,
        signals: Optional[List[Dict[str, Any]]] = None,
        journal_raises: bool = False,
    ) -> None:
        self.queue_rows = queue_rows or []
        self.live_now = live_now or []
        self.signals = signals or []
        # BUG FIX cert 10/07: il journal ora passa dal *sb del ciclo* (mai piu' il
        # client reale nei test) -> il fake lo raccoglie qui.
        self.journal: List[Dict[str, Any]] = []
        self.alerts: List[Dict[str, Any]] = []
        self._journal_raises = journal_raises

    def table(self, name: str) -> Any:
        if name == wk._TABLE:
            return _SelectQuery(self.queue_rows)
        if name == "live_now":
            return _SelectQuery(self.live_now)
        if name == "live_signals":
            return _SelectQuery(self.signals)
        if name == "live_alerts":
            outer = self

            class _AIns:
                def insert(self, row):
                    self._row = dict(row)
                    return self

                def execute(self):
                    outer.alerts.append(self._row)
                    return _Resp([self._row])

            return _AIns()
        if name == "betfair_live_journal":
            sink = self.journal
            raises = self._journal_raises

            class _Ins:
                def insert(self, row):
                    self._row = dict(row)
                    return self

                def execute(self):
                    if raises:
                        raise RuntimeError("insert KO")
                    sink.append(self._row)
                    return _Resp([self._row])

            return _Ins()
        raise AssertionError(f"tabella inattesa: {name}")


# ---------------------------------------------------------------------------
# Fake flumine market
# ---------------------------------------------------------------------------
def _market(market_id: str = "1.1", event_id: str = "31.5", sel: int = 111) -> Any:
    ex = SimpleNamespace(
        available_to_back=[
            {"price": 2.0, "size": 100.0},
            {"price": 1.99, "size": 50.0},
            {"price": 1.98, "size": 25.0},
            {"price": 1.97, "size": 10.0},  # oltre il top-3: deve essere troncato
        ],
        available_to_lay=[{"price": 2.02, "size": 80.0}],
    )
    runner = SimpleNamespace(selection_id=sel, handicap=0.0, ex=ex, last_price_traded=2.01)
    return SimpleNamespace(
        market_id=market_id,
        event_id=event_id,
        market_book=SimpleNamespace(runners=[runner]),
    )


def _flumine(*markets: Any) -> Any:
    return SimpleNamespace(markets=SimpleNamespace(markets={m.market_id: m for m in markets}))


@pytest.fixture()
def sink(monkeypatch):
    state = {"journal": [], "alerts": []}
    import Betfair.stream.db as dbmod

    monkeypatch.setattr(dbmod, "insert_live_journal", lambda row: state["journal"].append(dict(row)))
    monkeypatch.setattr(
        dbmod, "insert_alert",
        lambda level, code, message, event_id=None: state["alerts"].append((level, code, message)),
    )
    monkeypatch.setattr(wk, "_JOURNAL_WARNED_DAY", {})
    return state


def _request(**over: Any) -> Dict[str, Any]:
    base = {
        "id": 42,
        "action": "place",
        "market_id": "1.1",
        "selection_id": 111,
        "handicap": 0.0,
        "side": "back",
        "price": 2.0,
        "size": 5.0,
        "persistence": "LAPSE",
        "params": None,
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Contesto completo
# ---------------------------------------------------------------------------
def test_journal_captures_full_context(sink):
    sb = _FakeSb(
        queue_rows=[{"id": 42, "bet_id": "B99"}],
        live_now=[{"event_id": "31.5", "minute": 63, "score_home": 1, "score_away": 2, "inplay": True}],
        signals=[{
            "event_id": "31.5",
            "signals": {"signals": [
                {"market_id": "1.1", "selection_id": 111, "direction": "BACK",
                 "kelly_stake": 2.4, "edge": 0.06},
                {"market_id": "1.2", "selection_id": 111, "direction": "LAY"},
            ]},
        }],
    )
    wk._journal_done(sb, _flumine(_market()), _request(), "paper")
    assert len(sb.journal) == 1
    row = sb.journal[0]
    assert row["mode"] == "paper"
    assert row["request_id"] == 42
    assert row["bet_id"] == "B99"
    assert row["event_id"] == "31.5"
    assert row["origin"] == "manual"
    assert (row["minute"], row["score_home"], row["score_away"], row["inplay"]) == (63, 1, 2, True)
    assert row["ltp"] == pytest.approx(2.01)
    assert row["best_back"] == pytest.approx(2.0)
    assert row["best_lay"] == pytest.approx(2.02)
    assert len(row["book"]["back"]) == 3  # top-3, mai di più
    assert row["book"]["back"][0] == [2.0, 100.0]
    assert row["signals"]["kelly_stake"] == pytest.approx(2.4)
    assert row["signals"]["market_id"] == "1.1"


def test_journal_origin_risk_rule(sink):
    sb = _FakeSb(queue_rows=[{"id": 42, "bet_id": None}])
    req = _request(action="greenup", params={"risk_rule_id": 7, "fraction": 1.0})
    wk._journal_done(sb, _flumine(_market()), req, "live")
    assert sb.journal[0]["origin"] == "risk_rule"
    assert sb.journal[0]["params"] == {"risk_rule_id": 7, "fraction": 1.0}


def test_journal_without_market_still_writes_row(sink):
    sb = _FakeSb(queue_rows=[{"id": 42, "bet_id": None}])
    wk._journal_done(sb, _flumine(), _request(market_id="1.404"), "paper")
    row = sb.journal[0]
    assert row["market_id"] == "1.404"
    assert row["book"] is None and row["ltp"] is None and row["event_id"] is None


def test_journal_dutch_without_selection(sink):
    sb = _FakeSb(queue_rows=[{"id": 42, "bet_id": None}])
    req = _request(action="dutch", selection_id=None,
                   params={"selections": [111, 222], "total_stake": 20})
    wk._journal_done(sb, _flumine(_market()), req, "paper")
    row = sb.journal[0]
    assert row["action"] == "dutch"
    assert row["selection_id"] is None
    assert row["book"] is None
    assert row["params"]["total_stake"] == 20


def test_journal_errors_never_raise_and_warn_once(sink, monkeypatch):
    sb = _FakeSb(queue_rows=[{"id": 42, "bet_id": None}], journal_raises=True)
    wk._journal_done(sb, _flumine(_market()), _request(), "paper")   # nessuna eccezione
    wk._journal_done(sb, _flumine(_market()), _request(), "paper")
    warns = [a for a in sb.alerts if a.get("level") == "WARN" and a.get("code") == "JOURNAL"]
    assert len(warns) == 1  # anti-spam: una volta al giorno


def test_signal_not_matched_for_other_selection(sink):
    sb = _FakeSb(
        queue_rows=[{"id": 42, "bet_id": None}],
        signals=[{
            "event_id": "31.5",
            "signals": {"signals": [{"market_id": "1.1", "selection_id": 999}]},
        }],
    )
    wk._journal_done(sb, _flumine(_market()), _request(), "paper")
    assert sb.journal[0]["signals"] is None


# ---------------------------------------------------------------------------
# Integrazione col loop: journal SOLO su dispatch riuscito
# ---------------------------------------------------------------------------
def test_loop_journals_only_successful_dispatch(monkeypatch, sink):
    calls: List[int] = []
    monkeypatch.setattr(wk, "_journal_done", lambda _sb, _fl, r, _m: calls.append(r["id"]))
    monkeypatch.setattr(wk, "_claim", lambda _sb, _rid: True)
    monkeypatch.setattr(wk, "_write_error", lambda *_a, **_k: None)
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "PAPER")
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_refresh_settings", lambda _sb: None)
    monkeypatch.setattr(wk, "_db_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_throttled", lambda *_a: False)
    monkeypatch.setattr(wk, "_sweep_fok_ttls", lambda _fl: None)
    monkeypatch.setattr(wk, "_advance_inflight_submins", lambda *_a: 0)
    monkeypatch.setattr(wk, "_fail_cross_mode", lambda *_a: 0)

    def _dispatch(_sb, _fl, r, _mode, _strategy):
        if r["id"] == 2:
            raise ValueError("boom")

    monkeypatch.setattr(wk, "_dispatch", _dispatch)

    rows = [
        {"id": 1, "action": "place", "mode": "paper", "status": "pending"},
        {"id": 2, "action": "place", "mode": "paper", "status": "pending"},
    ]

    class _QueueSelect(_SelectQuery):
        pass

    class _Sb:
        def table(self, name: str) -> Any:
            assert name == wk._TABLE
            return _QueueSelect([dict(r) for r in rows])

    class _WithOrder(_QueueSelect):
        pass

    # la select del loop usa .order(): estendo il fake al volo
    def _order(self, _k):
        return self

    _QueueSelect.order = _order  # type: ignore[attr-defined]

    wk._process_once(_Sb(), _flumine(), None, None)
    assert calls == [1]  # solo la richiesta riuscita è journalata
