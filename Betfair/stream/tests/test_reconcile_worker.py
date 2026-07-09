"""Test ADVERSARIALI del reconcile_worker (A2 — riconciliazione col CONTO Betfair + A6 ripresa).

NESSUNA rete: session (APIClient betfairlightweight), supabase e db sono fake
in-memory. Sotto test le garanzie money-critical:
  - il CONTO Betfair vince SEMPRE sullo specchio (divergenze corrette dal conto);
  - ordini ESTERNI (piazzati dal sito) entrano nello specchio con source='account';
  - mai silenzioso (alert WARN una volta per bet, INFO di ripresa una volta per avvio);
  - REST KO → mai crash, la riconciliazione ordini prosegue anche senza saldo;
  - retry SOLO su errori transitori di rete (net_retry REALE).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.reconcile_worker as rw


# ---------------------------------------------------------------------------
# Fake Supabase (pattern _SelectQuery/_FakeSb di test_daily_stop_worker)
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    """select/update filtrabile con eq() a catena su una tabella in-memory."""

    def __init__(self, table: "_FakeTable", op: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self._table = table
        self._op = op
        self._payload = dict(payload) if payload else None
        self._filters: Dict[str, Any] = {}

    def eq(self, key: str, value: Any) -> "_Query":
        self._filters[key] = value
        return self

    def execute(self) -> _Resp:
        matched = [
            r for r in self._table.rows
            if all(r.get(k) == v for k, v in self._filters.items())
        ]
        if self._op == "select":
            return _Resp([dict(r) for r in matched])
        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
            self._table.updates.append((dict(self._filters), dict(self._payload or {})))
            return _Resp(None)
        raise AssertionError(f"op inattesa: {self._op}")


class _Upsert:
    def __init__(self, table: "_FakeTable", payload: Dict[str, Any], on_conflict: Optional[str]) -> None:
        self._table = table
        self._payload = dict(payload)
        self._on_conflict = on_conflict

    def execute(self) -> _Resp:
        self._table.upserts.append((dict(self._payload), self._on_conflict))
        keys = (self._on_conflict or "").split(",")
        for r in self._table.rows:
            if keys and all(r.get(k) == self._payload.get(k) for k in keys):
                r.update(self._payload)
                return _Resp(None)
        self._table.rows.append(dict(self._payload))
        return _Resp(None)


class _FakeTable:
    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        self.rows: List[Dict[str, Any]] = [dict(r) for r in (rows or [])]
        self.upserts: List[Any] = []
        self.updates: List[Any] = []

    def select(self, *_cols: Any) -> _Query:
        return _Query(self, "select")

    def update(self, payload: Dict[str, Any]) -> _Query:
        return _Query(self, "update", payload)

    def upsert(self, payload: Dict[str, Any], on_conflict: Optional[str] = None) -> _Upsert:
        return _Upsert(self, payload, on_conflict)


class _FakeSb:
    def __init__(
        self,
        orders: Optional[List[Dict[str, Any]]] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.orders = _FakeTable(orders)
        self.rules = _FakeTable(rules)

    def table(self, name: str) -> _FakeTable:
        if name == "betfair_live_orders":
            return self.orders
        if name == "betfair_live_risk_rules":
            return self.rules
        raise AssertionError(f"tabella inattesa: {name}")


# ---------------------------------------------------------------------------
# Fake APIClient betfairlightweight (session.context_api_client)
# ---------------------------------------------------------------------------
class _FakeAccount:
    def __init__(self, available: float = 100.0, exposure: float = -5.0) -> None:
        self.funds = SimpleNamespace(available_to_bet_balance=available, exposure=exposure)
        self.calls = 0
        self.raises: Optional[BaseException] = None      # errore PERMANENTE (ogni chiamata)
        self.fail_times = 0                              # solleva le prime N chiamate poi ok
        self.fail_with: Optional[BaseException] = None   # errore delle prime N chiamate

    def get_account_funds(self) -> Any:
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.fail_with or OSError("[WinError 10035] boom")
        if self.raises is not None:
            raise self.raises
        return self.funds


class _FakeBetting:
    """list_current_orders paginabile per from_record + list_cleared_orders groupBy MARKET."""

    def __init__(
        self,
        current_batches: Optional[List[List[Any]]] = None,
        cleared_groups: Optional[List[Any]] = None,
    ) -> None:
        self.current_batches = current_batches or [[]]
        self.cleared_groups = cleared_groups or []
        self.current_calls: List[int] = []
        self.cleared_calls: List[Dict[str, Any]] = []

    def list_current_orders(self, from_record: int = 0, record_count: int = 1000) -> Any:
        self.current_calls.append(from_record)
        offset = 0
        for i, batch in enumerate(self.current_batches):
            if from_record == offset:
                return SimpleNamespace(
                    orders=list(batch),
                    more_available=i < len(self.current_batches) - 1,
                )
            offset += len(batch)
        return SimpleNamespace(orders=[], more_available=False)

    def list_cleared_orders(self, **kwargs: Any) -> Any:
        self.cleared_calls.append(dict(kwargs))
        return SimpleNamespace(orders=list(self.cleared_groups), more_available=False)


def _co(
    bet_id: str,
    *,
    market_id: str = "1.100",
    selection_id: int = 111,
    side: str = "BACK",
    status: str = "EXECUTABLE",
    size_matched: Optional[float] = 0.0,
    size_remaining: float = 2.0,
    price: float = 2.0,
    size: float = 2.0,
) -> Any:
    """CurrentOrder fake con la shape betfairlightweight."""
    return SimpleNamespace(
        bet_id=bet_id,
        market_id=market_id,
        selection_id=selection_id,
        handicap=0.0,
        side=side,
        status=status,
        size_matched=size_matched,
        size_remaining=size_remaining,
        size_cancelled=0.0,
        size_lapsed=0.0,
        size_voided=0.0,
        average_price_matched=None,
        price_size=SimpleNamespace(price=price, size=size),
        placed_date=datetime(2026, 7, 9, 10, 0, tzinfo=timezone.utc),
        customer_order_ref=None,
        order_type="LIMIT",
        persistence_type="LAPSE",
    )


def _group(market_id: str, profit: float, bet_count: int) -> Any:
    return SimpleNamespace(market_id=market_id, profit=profit, bet_count=bet_count)


def _session(account: Optional[_FakeAccount] = None, betting: Optional[_FakeBetting] = None) -> Any:
    return SimpleNamespace(
        context_api_client=SimpleNamespace(
            account=account or _FakeAccount(),
            betting=betting or _FakeBetting(),
        )
    )


# ---------------------------------------------------------------------------
# Fixture: mode + cattura db.* e alert + reset dei global del worker
# ---------------------------------------------------------------------------
@pytest.fixture()
def env(monkeypatch):
    state = {
        "mode": "LIVE",
        "alerts": [],
        "account_writes": [],
        "settled_writes": [],
    }
    monkeypatch.setattr(rw.low, "_live_order_mode", lambda: state["mode"])

    import Betfair.stream.db as dbmod

    monkeypatch.setattr(
        dbmod, "insert_alert",
        lambda level, code, message, event_id=None: state["alerts"].append((level, code, message)),
    )
    monkeypatch.setattr(
        dbmod, "upsert_live_account",
        lambda available, exposure: state["account_writes"].append((available, exposure)),
    )
    monkeypatch.setattr(
        dbmod, "upsert_live_settled",
        lambda row: state["settled_writes"].append(dict(row)),
    )
    # reset dei global anti-spam/write-on-change del worker
    monkeypatch.setattr(rw, "_ALERTED_BETS", set())
    monkeypatch.setattr(rw, "_STARTUP_DONE", {})
    monkeypatch.setattr(rw, "_MISSING_SEEN", {})
    monkeypatch.setattr(rw, "_LAST_ACCOUNT_SIG", None)
    monkeypatch.setattr(rw, "_LAST_CLEARED_SIG", {})
    return state


def _cycle(sb: Any, session: Any) -> None:
    rw._process_once(sb, session, rw.low._live_order_mode().lower())


def _warns(env) -> List[str]:
    return [m for (lvl, _c, m) in env["alerts"] if lvl == "WARN"]


def _infos(env) -> List[str]:
    return [m for (lvl, _c, m) in env["alerts"] if lvl == "INFO"]


# ---------------------------------------------------------------------------
# 1) mode OFF → nessuna chiamata REST
# ---------------------------------------------------------------------------
def test_off_mode_no_rest_calls(env):
    env["mode"] = "OFF"
    account, betting = _FakeAccount(), _FakeBetting()
    _cycle(_FakeSb(), _session(account, betting))
    assert account.calls == 0
    assert betting.current_calls == []
    assert betting.cleared_calls == []
    assert env["account_writes"] == []


# ---------------------------------------------------------------------------
# 2) PAPER → SOLO il saldo (il conto è reale), mai current/cleared
# ---------------------------------------------------------------------------
def test_paper_writes_only_balance(env):
    env["mode"] = "PAPER"
    account = _FakeAccount(available=250.5, exposure=-10.0)
    betting = _FakeBetting(current_batches=[[_co("B1")]])
    sb = _FakeSb()
    _cycle(sb, _session(account, betting))
    assert env["account_writes"] == [(250.5, -10.0)]
    assert betting.current_calls == []       # mai current orders in PAPER
    assert betting.cleared_calls == []       # mai cleared orders in PAPER
    assert sb.orders.upserts == []


# ---------------------------------------------------------------------------
# 3) saldo write-on-change
# ---------------------------------------------------------------------------
def test_balance_write_on_change(env):
    env["mode"] = "PAPER"
    account = _FakeAccount(available=100.0, exposure=0.0)
    session = _session(account)
    sb = _FakeSb()
    _cycle(sb, session)
    _cycle(sb, session)
    assert env["account_writes"] == [(100.0, 0.0)]  # stesso saldo → 1 sola scrittura
    account.funds = SimpleNamespace(available_to_bet_balance=90.0, exposure=-8.0)
    _cycle(sb, session)
    assert env["account_writes"] == [(100.0, 0.0), (90.0, -8.0)]


# ---------------------------------------------------------------------------
# 4) ordine ESTERNO (dal sito) → specchio con ref extN + source account + WARN una volta
# ---------------------------------------------------------------------------
def test_external_order_upserted_with_source_account(env):
    betting = _FakeBetting(current_batches=[[
        _co("777", market_id="1.234", side="BACK", size_matched=1.5, price=3.0, size=2.0),
    ]])
    session = _session(betting=betting)
    sb = _FakeSb()
    _cycle(sb, session)

    ext = [r for r in sb.orders.rows if r.get("bet_id") == "777"]
    assert len(ext) == 1
    row = ext[0]
    assert row["client_order_ref"] == "ext777"
    assert row["source"] == "account"
    assert row["mode"] == "live"
    assert row["market_id"] == "1.234"
    assert row["side"] == "back"
    assert row["price"] == 3.0
    assert row["size"] == 2.0
    assert row["size_matched"] == 1.5
    assert row["status"] == "EXECUTABLE"
    assert row["placed_at"] == "2026-07-09T10:00:00+00:00"
    # upsert idempotente sulla chiave dello specchio
    assert sb.orders.upserts[0][1] == "mode,client_order_ref"

    warns = [m for m in _warns(env) if "ESTERNO" in m and "777" in m]
    assert len(warns) == 1
    # secondo ciclo: il bet è ormai nello specchio → nessun duplicato, nessun nuovo WARN
    _cycle(sb, session)
    assert len([r for r in sb.orders.rows if r.get("bet_id") == "777"]) == 1
    assert len([m for m in _warns(env) if "ESTERNO" in m and "777" in m]) == 1


# ---------------------------------------------------------------------------
# 5) divergenza size_matched → il CONTO vince: update dello specchio + WARN una volta
# ---------------------------------------------------------------------------
def test_divergence_corrected_from_account(env):
    mirror = [{
        "mode": "live", "bet_id": "888", "client_order_ref": "awlq1",
        "size_matched": 1.0, "status": "EXECUTABLE", "source": "runner",
    }]
    betting = _FakeBetting(current_batches=[[
        _co("888", size_matched=3.0, status="EXECUTION_COMPLETE", size_remaining=0.0),
    ]])
    session = _session(betting=betting)
    sb = _FakeSb(orders=mirror)
    _cycle(sb, session)

    row = [r for r in sb.orders.rows if r.get("bet_id") == "888"][0]
    assert row["size_matched"] == 3.0                    # valore del CONTO
    assert row["status"] == "EXECUTION_COMPLETE"         # valore del CONTO
    assert sb.orders.updates and sb.orders.updates[0][0] == {"mode": "live", "bet_id": "888"}
    warns = [m for m in _warns(env) if "divergente" in m]
    assert len(warns) == 1
    assert "1.0" in warns[0] and "3.0" in warns[0]       # "matched X→Y"
    # secondo ciclo: specchio ormai allineato → nessun nuovo update né WARN
    _cycle(sb, session)
    assert len(sb.orders.updates) == 1
    assert len([m for m in _warns(env) if "divergente" in m]) == 1


# ---------------------------------------------------------------------------
# 6) specchio EXECUTABLE assente dal conto → WARN solo se persiste 2 cicli
# ---------------------------------------------------------------------------
def test_missing_from_account_warns_only_after_two_cycles(env):
    mirror = [{
        "mode": "live", "bet_id": "999", "client_order_ref": "awlq2",
        "size_matched": 0.0, "status": "EXECUTABLE", "source": "runner",
    }]
    session = _session(betting=_FakeBetting(current_batches=[[]]))
    sb = _FakeSb(orders=mirror)
    _cycle(sb, session)
    assert [m for m in _warns(env) if "999" in m] == []  # 1° ciclo: lo stream può essere avanti
    _cycle(sb, session)
    warns = [m for m in _warns(env) if "999" in m]
    assert len(warns) == 1                               # 2° ciclo: persiste → WARN
    # la riga NON viene MAI toccata
    assert sb.orders.updates == []
    assert sb.orders.rows[0]["status"] == "EXECUTABLE"
    # 3° ciclo: nessuno spam
    _cycle(sb, session)
    assert len([m for m in _warns(env) if "999" in m]) == 1


# ---------------------------------------------------------------------------
# 7) cleared groupBy MARKET → upsert_live_settled write-on-change
# ---------------------------------------------------------------------------
def test_cleared_orders_settled_write_on_change(env):
    betting = _FakeBetting(cleared_groups=[_group("1.200", -3.456, 2)])
    session = _session(betting=betting)
    sb = _FakeSb()
    _cycle(sb, session)
    assert env["settled_writes"] == [{
        "mode": "live", "market_id": "1.200", "event_id": None,
        "profit": -3.46, "orders": 2, "source": "cleared",
    }]
    # la finestra è la giornata locale (settled_date_range presente)
    assert betting.cleared_calls[0]["group_by"] == "MARKET"
    assert betting.cleared_calls[0]["bet_status"] == "SETTLED"
    assert betting.cleared_calls[0]["settled_date_range"] is not None
    # write-on-change: stesso gruppo → nessuna seconda scrittura
    _cycle(sb, session)
    assert len(env["settled_writes"]) == 1
    # profit cambiato (nuovo mercato settled nel gruppo) → nuova scrittura
    betting.cleared_groups = [_group("1.200", -5.0, 3)]
    _cycle(sb, session)
    assert len(env["settled_writes"]) == 2
    assert env["settled_writes"][1]["profit"] == -5.0


# ---------------------------------------------------------------------------
# 8) paginazione current orders (more_available)
# ---------------------------------------------------------------------------
def test_current_orders_pagination(env):
    betting = _FakeBetting(current_batches=[[_co("1")], [_co("2", market_id="1.101")]])
    session = _session(betting=betting)
    sb = _FakeSb()
    _cycle(sb, session)
    assert betting.current_calls == [0, 1]               # from_record avanzato
    bets = {r.get("bet_id") for r in sb.orders.rows}
    assert bets == {"1", "2"}                            # tutti gli ordini visti


# ---------------------------------------------------------------------------
# 9) getAccountFunds KO → il saldo salta ma la riconciliazione LIVE prosegue
# ---------------------------------------------------------------------------
def test_account_funds_failure_does_not_block_reconciliation(env):
    account = _FakeAccount()
    account.raises = RuntimeError("api KO")              # NON transitorio: nessun retry
    betting = _FakeBetting(current_batches=[[_co("55")]])
    session = _session(account, betting)
    sb = _FakeSb()
    _cycle(sb, session)                                  # nessun crash
    assert env["account_writes"] == []                   # saldo saltato
    assert account.calls == 1                            # errore applicativo: 1 solo tentativo
    assert {r.get("bet_id") for r in sb.orders.rows} == {"55"}  # ordini riconciliati comunque


# ---------------------------------------------------------------------------
# 10) ripresa (A6): report INFO una volta per avvio + regole armate orfane
# ---------------------------------------------------------------------------
def test_startup_report_once_and_orphan_armed_rule_warns(env):
    rules = [
        {"id": 7, "entry_bet_id": "BX", "market_id": "1.1", "status": "armed", "mode": "live"},
        {"id": 8, "entry_bet_id": "44", "market_id": "1.2", "status": "armed", "mode": "live"},
    ]
    betting = _FakeBetting(current_batches=[[_co("44")]])
    session = _session(betting=betting)
    sb = _FakeSb(rules=rules)
    _cycle(sb, session)

    infos = [m for m in _infos(env) if "ripresa LIVE" in m]
    assert len(infos) == 1
    # regola 7: bet BX né sul conto né nello specchio → WARN; regola 8: bet 44 sul conto → ok
    orphan = [m for m in _warns(env) if "regola 7" in m and "BX" in m]
    assert len(orphan) == 1
    assert not any("regola 8" in m for m in _warns(env))
    assert "resta armata" in orphan[0]
    # secondo ciclo: nessun nuovo INFO di ripresa
    _cycle(sb, session)
    assert len([m for m in _infos(env) if "ripresa LIVE" in m]) == 1


# ---------------------------------------------------------------------------
# 11) retry transitorio (net_retry REALE): WinError 10035 poi ok → saldo scritto
# ---------------------------------------------------------------------------
def test_transient_error_retried_then_balance_written(env, monkeypatch):
    env["mode"] = "PAPER"
    monkeypatch.setattr(rw.time, "sleep", lambda _s: None)  # niente attese reali nel test
    account = _FakeAccount(available=42.0, exposure=0.0)
    account.fail_times = 1
    account.fail_with = OSError("[WinError 10035] operazione su socket non bloccante")
    _cycle(_FakeSb(), _session(account))
    assert account.calls == 2                            # 1 fallito (transitorio) + 1 ok
    assert env["account_writes"] == [(42.0, 0.0)]


# ---------------------------------------------------------------------------
# entry robusta: mai far cadere il runner
# ---------------------------------------------------------------------------
def test_entry_never_raises(env, monkeypatch):
    monkeypatch.setattr(rw, "_process_once", lambda *_a, **_k: 1 / 0)
    monkeypatch.setattr("db_client.get_supabase_client", lambda: _FakeSb(), raising=False)
    rw.reconcile_worker({}, object(), _session(), None)  # nessuna eccezione
