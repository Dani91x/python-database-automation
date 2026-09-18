"""Test ADVERSARIALI del reconcile_worker (A2 — riconciliazione col CONTO Betfair + A6 ripresa).

NESSUNA rete: session (APIClient betfairlightweight), supabase e db sono fake
in-memory. Sotto test le garanzie money-critical:
  - il CONTO Betfair vince SEMPRE sullo specchio (divergenze corrette dal conto);
  - ordini ESTERNI (piazzati dal sito) entrano nello specchio con source='account';
  - mai silenzioso (alert WARN una volta per bet, INFO di ripresa una volta per avvio);
  - REST KO → mai crash, la riconciliazione ordini prosegue anche senza saldo;
  - retry SOLO su errori transitori di rete (net_retry REALE).

18/09 (fix saldo sempre aggiornato): il saldo (``_sync_account`` /
``sync_account_worker``) e la riconciliazione ORDINI (``_process_once`` /
``reconcile_worker``) sono ora DUE responsabilita' separate — vedi la sezione
"SYNC_ACCOUNT_WORKER" in coda per i test dedicati al saldo (cadenza fissa 20s,
QUALUNQUE mode, publish sul canale locale). Le sezioni sopra coprono SOLO la
riconciliazione ordini, che resta identica a prima ma parte da ``_process_once``
senza piu' toccare il saldo.
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
    """list_current_orders paginabile per from_record + list_cleared_orders
    groupBy MARKET (``cleared_groups``, storico) o bet-level paginato
    (``cleared_pages``, Parte B — manuale: from_record REALE, moreAvailable)."""

    def __init__(
        self,
        current_batches: Optional[List[List[Any]]] = None,
        cleared_groups: Optional[List[Any]] = None,
        cleared_pages: Optional[List[List[Any]]] = None,
    ) -> None:
        self.current_batches = current_batches or [[]]
        self.cleared_groups = cleared_groups or []
        self.cleared_pages = cleared_pages  # None -> comportamento storico (cleared_groups)
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

    def list_cleared_orders(self, from_record: int = 0, record_count: int = 1000, **kwargs: Any) -> Any:
        self.cleared_calls.append({"from_record": from_record, "record_count": record_count, **kwargs})
        if self.cleared_pages is not None:
            offset = 0
            for i, page in enumerate(self.cleared_pages):
                if from_record == offset:
                    return SimpleNamespace(
                        orders=list(page),
                        more_available=i < len(self.cleared_pages) - 1,
                    )
                offset += len(page)
            return SimpleNamespace(orders=[], more_available=False)
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


def _cleared(
    bet_id: str,
    *,
    profit: float = 0.0,
    commission: Optional[float] = 0.0,
    customer_strategy_ref: Optional[str] = None,
    customer_order_ref: Optional[str] = None,
    market_id: str = "1.100",
) -> Any:
    """``ClearedOrder`` fake CON GLI STESSI attributi snake_case reali
    dell'oggetto betfairlightweight (verificati in
    ``betfairlightweight/resources/bettingresources.py::ClearedOrder.__init__``:
    ``self.profit``, ``self.commission``, ``self.customer_strategy_ref``,
    ``self.customer_order_ref`` — mai un dict/camelCase a mano, precedente
    15/09 customerOrderRef/customer_order_ref)."""
    return SimpleNamespace(
        bet_id=bet_id,
        bet_count=1,
        bet_outcome="WON",
        market_id=market_id,
        profit=profit,
        commission=commission,
        customer_strategy_ref=customer_strategy_ref,
        customer_order_ref=customer_order_ref,
        settled_date=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
    )


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
        "manual_pnl_writes": [],
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
    monkeypatch.setattr(
        dbmod, "upsert_live_account_manual_pnl",
        lambda **kw: state["manual_pnl_writes"].append(dict(kw)),
    )
    # reset dei global anti-spam/write-on-change del worker
    monkeypatch.setattr(rw, "_ALERTED_BETS", set())
    monkeypatch.setattr(rw, "_STARTUP_DONE", {})
    monkeypatch.setattr(rw, "_MISSING_SEEN", {})
    monkeypatch.setattr(rw, "_LAST_ACCOUNT_SIG", None)
    monkeypatch.setattr(rw, "_LAST_ACCOUNT_TS", 0.0)
    monkeypatch.setattr(rw, "_LAST_CLEARED_SIG", {})
    # 18/09 sera (Parte B): reset dei global write-on-change/cadenza del manuale
    # — SEPARATI da _LAST_ACCOUNT_TS: run_account_sync_if_due ora chiama anche
    # _run_manual_pnl_if_due, che senza questo reset erediterebbe stato dal
    # test precedente (stessi globals di modulo).
    monkeypatch.setattr(rw, "_LAST_MANUAL_PNL_TS", 0.0)
    monkeypatch.setattr(rw, "_LAST_MANUAL_PNL_SIG", None)
    return state


def _cycle(sb: Any, session: Any) -> None:
    """Un giro della SOLA riconciliazione ordini (18/09: il saldo e' un worker
    separato, ``sync_account_worker`` — vedi la sezione dedicata in coda)."""
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
# 2) PAPER → _process_once e' un no-op TOTALE (18/09: niente saldo qui, niente
#    ordini in paper — il saldo e' sync_account_worker, sempre separato)
# ---------------------------------------------------------------------------
def test_paper_is_a_full_noop_for_process_once(env):
    env["mode"] = "PAPER"
    account = _FakeAccount(available=250.5, exposure=-10.0)
    betting = _FakeBetting(current_batches=[[_co("B1")]])
    sb = _FakeSb()
    _cycle(sb, _session(account, betting))
    assert account.calls == 0                # 18/09: il saldo NON e' piu' qui
    assert env["account_writes"] == []
    assert betting.current_calls == []       # mai current orders in PAPER
    assert betting.cleared_calls == []       # mai cleared orders in PAPER
    assert sb.orders.upserts == []




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
# 9) _process_once NON tocca MAI il conto (18/09: e' sync_account_worker, worker
#    separato) — la riconciliazione ORDINI prosegue indipendentemente dal saldo,
#    anche se getAccountFunds sarebbe rotto (qui: mai nemmeno chiamato).
# ---------------------------------------------------------------------------
def test_account_funds_failure_does_not_block_reconciliation(env):
    account = _FakeAccount()
    account.raises = RuntimeError("api KO")              # NON transitorio: nessun retry
    betting = _FakeBetting(current_batches=[[_co("55")]])
    session = _session(account, betting)
    sb = _FakeSb()
    _cycle(sb, session)                                  # nessun crash
    assert env["account_writes"] == []                   # saldo saltato
    assert account.calls == 0                            # 18/09: _process_once non lo chiama piu'
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
# entry robusta: mai far cadere il runner
# ---------------------------------------------------------------------------
def test_entry_never_raises(env, monkeypatch):
    monkeypatch.setattr(rw, "_process_once", lambda *_a, **_k: 1 / 0)
    monkeypatch.setattr("db_client.get_supabase_client", lambda: _FakeSb(), raising=False)
    rw.reconcile_worker({}, object(), _session(), None)  # nessuna eccezione


def test_reconcile_worker_entry_skips_paper_no_supabase_client(env, monkeypatch):
    """18/09: l'entry ora esce su ``mode != LIVE`` PRIMA di costruire il client
    supabase (in PAPER _process_once sarebbe comunque un no-op) — nessuna
    chiamata get_supabase_client sprecata a ogni tick PAPER."""
    env["mode"] = "PAPER"
    calls = {"n": 0}

    def _boom():
        calls["n"] += 1
        raise AssertionError("get_supabase_client NON va chiamato in PAPER")

    monkeypatch.setattr("db_client.get_supabase_client", _boom, raising=False)
    rw.reconcile_worker({}, object(), _session(), None)
    assert calls["n"] == 0


# =============================================================================
# RUN_ACCOUNT_SYNC_IF_DUE (18/09, poi 18/09 sera) — saldo del conto, SEMPRE,
# cadenza fissa 20s, chiamato da DUE posti (worker + ciclo idle di runner.py)
# =============================================================================
# ``run_account_sync_if_due`` e' il nucleo condiviso: gira in QUALUNQUE
# LIVE_ORDER_MODE (OFF/PAPER/LIVE) E in QUALUNQUE fase del runner (stream
# attivo O ciclo idle senza follow), a differenza di reconcile_worker/
# _process_once sopra (che fanno SOLO riconciliazione ordini, SOLO LIVE,
# SOLO dentro framework.run()). Nessuna rete: session e db/local_channel sono
# fake/mockati come sopra. ``sync_account_worker`` (BackgroundWorker) e' un
# thin wrapper: i test sotto chiamano direttamente il nucleo condiviso, tranne
# quelli che verificano esplicitamente la delega.
# =============================================================================
def test_run_account_sync_if_due_runs_with_no_mode_dependency(env, monkeypatch):
    """La chiamata NON consulta affatto LIVE_ORDER_MODE: gira uguale se il
    runner calcio e' OFF/senza follow, mentre magari un altro bot
    (Omega/Mike/tennis) e' LIVE sullo stesso conto."""
    monkeypatch.setattr(rw.low, "_live_order_mode", lambda: (_ for _ in ()).throw(
        AssertionError("run_account_sync_if_due non deve consultare la mode")))
    account = _FakeAccount(available=77.0, exposure=-1.0)
    session = _session(account)
    rw.run_account_sync_if_due(session)
    assert account.calls == 1
    assert env["account_writes"] == [(77.0, -1.0)]


def test_run_account_sync_if_due_no_session_no_client_is_silent(env):
    assert rw.run_account_sync_if_due(None) is None
    assert rw.run_account_sync_if_due(SimpleNamespace(context_api_client=None)) is None
    assert env["account_writes"] == []


def test_run_account_sync_if_due_fixed_20s_cadence_regardless_of_mode(env, monkeypatch):
    """Cadenza FISSA 20s (18/09), non piu' 60s PAPER / 20s LIVE: due giri
    ravvicinati -> UNA sola chiamata REST, qualunque sia env['mode']."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    account = _FakeAccount(available=10.0, exposure=0.0)
    session = _session(account)
    rw.run_account_sync_if_due(session)   # prima lettura
    assert account.calls == 1
    clock["t"] += 5.0
    rw.run_account_sync_if_due(session)   # +5s: troppo presto
    assert account.calls == 1
    clock["t"] += 14.9
    rw.run_account_sync_if_due(session)   # +19.9s totali: ancora presto
    assert account.calls == 1
    clock["t"] += 0.2
    rw.run_account_sync_if_due(session)   # +20.1s: seconda lettura
    assert account.calls == 2


def test_run_account_sync_if_due_balance_unchanged_no_db_write(env, monkeypatch):
    """Saldo invariato -> nessuna scrittura DB (write-on-change), anche a
    cadenza rispettata (chiamate REST distinte, valore identico)."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    account = _FakeAccount(available=55.0, exposure=-2.0)
    session = _session(account)
    rw.run_account_sync_if_due(session)
    clock["t"] += 21.0
    rw.run_account_sync_if_due(session)
    assert account.calls == 2                     # letto due volte...
    assert env["account_writes"] == [(55.0, -2.0)]  # ...ma scritto una sola


def test_run_account_sync_if_due_get_account_funds_ko_never_raises_retries_next_tick(env, monkeypatch):
    """KO permanente di getAccountFunds -> nessuna eccezione, nessuna scrittura,
    e al giro successivo (dopo la cadenza) si ritenta."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    account = _FakeAccount()
    account.raises = RuntimeError("api KO")
    session = _session(account)
    rw.run_account_sync_if_due(session)   # non deve sollevare
    assert env["account_writes"] == []
    assert account.calls == 1
    clock["t"] += 21.0
    account.raises = None
    account.funds = SimpleNamespace(available_to_bet_balance=5.0, exposure=0.0)
    rw.run_account_sync_if_due(session)   # ritenta al giro dopo
    assert account.calls == 2
    assert env["account_writes"] == [(5.0, 0.0)]


def test_run_account_sync_if_due_transient_error_retried_within_same_tick(env, monkeypatch):
    """Errore TRANSITORIO (net_retry REALE, WinError 10035) -> ritentato nello
    STESSO giro (2 tentativi), poi saldo scritto."""
    monkeypatch.setattr(rw.time, "sleep", lambda _s: None)  # niente attese reali
    account = _FakeAccount(available=42.0, exposure=0.0)
    account.fail_times = 1
    account.fail_with = OSError("[WinError 10035] operazione su socket non bloccante")
    session = _session(account)
    rw.run_account_sync_if_due(session)
    assert account.calls == 2                     # 1 fallito (transitorio) + 1 ok
    assert env["account_writes"] == [(42.0, 0.0)]


def test_run_account_sync_if_due_publishes_local_channel_on_every_successful_check(env, monkeypatch):
    """18/09: publish sul canale locale ad OGNI lettura riuscita, anche quando il
    saldo NON cambia (write-on-change resta solo per il DB) — e' la freschezza
    che il frontend mostra ad app aperta. Il topic 'account' porta ANCHE (dal
    18/09 sera) i messaggi del manuale (Parte B): si filtra sul payload."""
    import Betfair.stream.local_channel as lc

    published: List[Any] = []
    monkeypatch.setattr(lc, "publish", lambda topic, payload: published.append((topic, dict(payload))))
    clock = {"t": 1000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    account = _FakeAccount(available=30.0, exposure=-1.5)
    session = _session(account)
    rw.run_account_sync_if_due(session)
    clock["t"] += 21.0
    rw.run_account_sync_if_due(session)   # saldo identico
    balance_msgs = [(t, p) for t, p in published if "available" in p]
    assert len(balance_msgs) == 2                            # publish del SALDO ENTRAMBE le volte
    assert all(t == "account" for t, _p in balance_msgs)
    assert all(p["available"] == 30.0 and p["exposure"] == -1.5 for _t, p in balance_msgs)
    assert all("checked_at" in p for _t, p in balance_msgs)
    assert len(env["account_writes"]) == 1                  # DB: 1 sola scrittura (invariato)


def test_run_account_sync_if_due_local_channel_publish_failure_does_not_block_db_write(env, monkeypatch):
    """Il canale locale e' best-effort: se ``publish`` solleva, il saldo va
    comunque su DB (mai bloccare il dato money-critical per un canale display)."""
    import Betfair.stream.local_channel as lc

    def _boom(_topic, _payload):
        raise RuntimeError("canale KO")

    monkeypatch.setattr(lc, "publish", _boom)
    account = _FakeAccount(available=12.0, exposure=0.0)
    session = _session(account)
    rw.run_account_sync_if_due(session)
    assert env["account_writes"] == [(12.0, 0.0)]


def test_run_account_sync_if_due_never_raises_on_unexpected_exception(env, monkeypatch):
    """Contratto: chiamata sia dal thread del BackgroundWorker sia dal thread
    principale del ciclo idle — un guasto interno inatteso (non gia' catturato
    da ``_sync_account``) deve restare confinato qui, mai propagare a chi
    chiama (fermerebbe il worker flumine, o interromperebbe il ciclo idle)."""
    monkeypatch.setattr(rw, "_sync_account", lambda _session: (_ for _ in ()).throw(RuntimeError("boom")))
    session = _session()
    assert rw.run_account_sync_if_due(session) is None  # nessuna eccezione


# ---------------------------------------------------------------------------
# sync_account_worker (BackgroundWorker, thin wrapper) — delega al nucleo
# condiviso con LO STESSO orologio usato dal ciclo idle (test critico del
# reperto 18/09 sera: "passaggio idle->run entro 20s -> UNA sola chiamata REST")
# ---------------------------------------------------------------------------
def test_sync_account_worker_delegates_to_shared_clock(env, monkeypatch):
    """sync_account_worker(...) e run_account_sync_if_due(...) condividono lo
    STESSO _LAST_ACCOUNT_TS: chiamarli uno dopo l'altro entro 20s equivale a
    UNA sola chiamata REST, qualunque sia l'ordine (idle poi worker, o
    worker poi idle) — questo e' esattamente il passaggio idle<->run."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    account = _FakeAccount(available=88.0, exposure=0.0)
    session = _session(account)

    # scenario A: ciclo idle sincronizza, poi (senza che passino 20s) lo
    # stream parte e il BackgroundWorker fa il suo primo giro.
    rw.run_account_sync_if_due(session)         # "ciclo idle"
    assert account.calls == 1
    clock["t"] += 3.0
    rw.sync_account_worker({}, object(), session=session)   # "framework.run() appena partito"
    assert account.calls == 1                   # NESSUNA seconda chiamata REST


def test_sync_account_worker_delegates_to_shared_clock_reverse_order(env, monkeypatch):
    """Stesso scenario, ordine INVERTITO: il worker gira mentre lo stream e'
    su, poi lo stream si ferma (restart F3/fine partite) e il runner torna
    nel ciclo idle — entro 20s, ancora UNA sola chiamata REST."""
    clock = {"t": 2000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    account = _FakeAccount(available=99.0, exposure=0.0)
    session = _session(account)

    rw.sync_account_worker({}, object(), session=session)   # "stream attivo"
    assert account.calls == 1
    clock["t"] += 10.0
    rw.run_account_sync_if_due(session)          # "tornato in idle"
    assert account.calls == 1                    # NESSUNA seconda chiamata REST
    clock["t"] += 10.1                            # ora 20.1s dalla prima lettura
    rw.run_account_sync_if_due(session)
    assert account.calls == 2                    # cadenza rispettata, si ritenta


# =============================================================================
# MANUALE (Parte B, 18/09 sera) — P&L di oggi delle operazioni NON dei bot
# =============================================================================
# NOTA SULL'AMBIGUITA' (dichiarata nel CHECKPOINT): "nessun ref affatto ->
# 'manual'" CONFERMATA dal coordinatore (18/09 sera, secondo giro): e' la
# lettura giusta.
#
# TERZO GIRO (18/09 sera) — 'manual_app': audit puntuale (file per file, vedi
# CHECKPOINT §16-17) ha trovato che il ref "live" (calcio) e "tennis" NON sono
# MAI usati da un bot autonomo: sono il ref del terminale di trading MANUALE
# della nostra app (ladder + place/cashout/greenup RPC + chiusure di risk_rule
# su posizioni aperte a mano). Per l'utente ("tutto cio' che non e' bot: dal
# sito O dalla nostra app") questi ordini sono MANUALE, sotto-classe separata
# 'manual_app' (calcio+tennis insieme: non sono ulteriormente distinguibili
# fra ladder-click e risk-rule, e non serve — sono comunque manuali).
# ATTENZIONE (dichiarato, non risolto qui): i bot AUTONOMI veri (scalper/
# sniper calcio in Betfair/stream/scalper/, i 4 bot tennis in
# Betfair/stream/tennis_scalper/) NON passano ALCUN customerStrategyRef a
# market.place_order — le loro righe cadono OGGI nel bucket 'manual' (nessun
# ref, indistinguibili da una vera scommessa del sito). Non e' leggibile da
# qui: la modifica minima proposta (NON applicata, sono file di strategia) e'
# nel CHECKPOINT §17.
# =============================================================================
def test_classify_cleared_order_our_bot_strategy_ref_is_ours():
    order = _cleared("1", customer_strategy_ref="omega")
    assert rw._classify_cleared_order(order) == "ours"


def test_classify_cleared_order_our_order_ref_prefix_is_ours_when_strategy_ref_missing():
    """Safe eredita il customerStrategyRef di Omega ma il SUO customerOrderRef
    inizia sempre per 'safe-t': seconda rete difensiva."""
    order = _cleared("2", customer_strategy_ref=None, customer_order_ref="safe-t42")
    assert rw._classify_cleared_order(order) == "ours"


def test_classify_cleared_order_no_ref_at_all_is_manual():
    order = _cleared("3", customer_strategy_ref=None, customer_order_ref=None)
    assert rw._classify_cleared_order(order) == "manual"


def test_classify_cleared_order_unrecognized_order_ref_is_ambiguous():
    order = _cleared("4", customer_strategy_ref=None, customer_order_ref="qualcosa-mai-visto")
    assert rw._classify_cleared_order(order) == "ambiguous"


def test_classify_cleared_order_calcio_ladder_ref_is_manual_app():
    """ref 'live' (Betfair/stream/live_order_worker.py:53) = terminale MANUALE
    calcio (ladder + place/cashout/greenup RPC + chiusure risk_rule) — MAI un
    bot (verificato: nessun file sotto Betfair/stream/scalper/ lo usa)."""
    order = _cleared("5", customer_strategy_ref="live", customer_order_ref=None)
    assert rw._classify_cleared_order(order) == "manual_app"


def test_classify_cleared_order_tennis_ladder_ref_is_manual_app():
    """ref 'tennis' (tennis_live_order_worker.py:34, drena SOLO
    tennis_live_order_queue = 'ordini MANUALI della ladder tennis' per
    dichiarazione esplicita del modulo) = terminale MANUALE tennis — MAI un
    bot (i 4 bot autonomi sono in Betfair/stream/tennis_scalper/, che non usa
    questo ref)."""
    order = _cleared("6", customer_strategy_ref="tennis", customer_order_ref=None)
    assert rw._classify_cleared_order(order) == "manual_app"


def test_classify_cleared_order_calcio_ladder_ref_is_manual_app_case_and_space_insensitive():
    order = _cleared("7", customer_strategy_ref="  LIVE  ", customer_order_ref=None)
    assert rw._classify_cleared_order(order) == "manual_app"


def test_classify_cleared_order_future_bot_ref_is_ours():
    """Regola GENERALE (non specifica a un nome): qualunque customerStrategyRef
    presente e NON manual_app e' 'ours' — questo copre AUTOMATICAMENTE il
    giorno in cui scalper/sniper calcio o i 4 bot tennis riceveranno un loro
    ref proprio (proposto, non applicato: es. 'scalper' — vedi CHECKPOINT
    §17), senza dover toccare _classify_cleared_order di nuovo."""
    order = _cleared("8", customer_strategy_ref="scalper", customer_order_ref=None)
    assert rw._classify_cleared_order(order) == "ours"


def test_sync_manual_pnl_sums_manual_orders_net_when_commission_readable(env):
    betting = _FakeBetting(cleared_pages=[[
        _cleared("10", profit=5.0, commission=0.25, customer_strategy_ref=None, customer_order_ref=None),
        _cleared("11", profit=-2.0, commission=0.10, customer_strategy_ref=None, customer_order_ref=None),
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    assert len(env["manual_pnl_writes"]) == 1
    w = env["manual_pnl_writes"][0]
    assert w["pnl_eur"] == round((5.0 - 2.0) - (0.25 + 0.10), 2)
    assert w["is_net"] is True
    assert w["orders"] == 2
    assert w["excluded"] == 0


def test_sync_manual_pnl_gross_and_declared_when_commission_missing_on_any_order(env):
    betting = _FakeBetting(cleared_pages=[[
        _cleared("20", profit=5.0, commission=0.25, customer_strategy_ref=None, customer_order_ref=None),
        _cleared("21", profit=3.0, commission=None, customer_strategy_ref=None, customer_order_ref=None),
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    w = env["manual_pnl_writes"][0]
    assert w["is_net"] is False              # dichiarato LORDO, mai finto netto
    assert w["pnl_eur"] == round(5.0 + 3.0, 2)  # somma profit SENZA sottrarre commissione


def test_sync_manual_pnl_excludes_bot_orders_from_total(env):
    betting = _FakeBetting(cleared_pages=[[
        _cleared("30", profit=100.0, customer_strategy_ref="omega"),      # bot: escluso
        _cleared("31", profit=7.0, customer_strategy_ref=None, customer_order_ref=None),  # manuale
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    w = env["manual_pnl_writes"][0]
    assert w["orders"] == 1
    assert w["excluded"] == 0            # riconosciuto come NOSTRO, non "ambiguo"
    assert w["pnl_eur"] == 7.0 - (0.0)  # commission default 0.0 nel fake


def test_sync_manual_pnl_excludes_and_counts_ambiguous_orders(env):
    betting = _FakeBetting(cleared_pages=[[
        _cleared("40", profit=7.0, customer_strategy_ref=None, customer_order_ref=None),
        _cleared("41", profit=999.0, customer_strategy_ref=None, customer_order_ref="mai-visto-prima"),
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    w = env["manual_pnl_writes"][0]
    assert w["orders"] == 1
    assert w["excluded"] == 1
    assert w["pnl_eur"] == 7.0            # il 999.0 ambiguo NON entra nel totale


def test_sync_manual_pnl_separates_site_and_app_totals(env):
    """Terzo giro: due totali SEPARATI nella STESSA scrittura — un ordine dal
    sito (nessun ref) e uno dal ladder calcio (ref 'live') non si mescolano."""
    betting = _FakeBetting(cleared_pages=[[
        _cleared("100", profit=10.0, commission=0.0, customer_strategy_ref=None, customer_order_ref=None),
        _cleared("101", profit=3.0, commission=0.0, customer_strategy_ref="live"),
        _cleared("102", profit=200.0, customer_strategy_ref="omega"),  # bot: fuori da entrambi
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    w = env["manual_pnl_writes"][0]
    assert w["pnl_eur"] == 10.0
    assert w["orders"] == 1
    assert w["app_pnl_eur"] == 3.0
    assert w["app_orders"] == 1
    assert w["excluded"] == 0


def test_sync_manual_pnl_tennis_ladder_also_counts_in_app_total(env):
    betting = _FakeBetting(cleared_pages=[[
        _cleared("110", profit=4.0, commission=0.0, customer_strategy_ref="tennis"),
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    w = env["manual_pnl_writes"][0]
    assert w["app_pnl_eur"] == 4.0
    assert w["app_orders"] == 1
    assert w["orders"] == 0        # niente nel bucket sito


def test_sync_manual_pnl_app_gross_when_commission_missing(env):
    betting = _FakeBetting(cleared_pages=[[
        _cleared("120", profit=5.0, commission=None, customer_strategy_ref="live"),
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    w = env["manual_pnl_writes"][0]
    assert w["app_is_net"] is False
    assert w["app_pnl_eur"] == 5.0


def test_sync_manual_pnl_write_on_change_app_total_alone_triggers_write(env):
    """Il saldo del sito resta invariato ma l'app cambia -> comunque una nuova
    scrittura (la firma copre ENTRAMBI i totali)."""
    betting = _FakeBetting(cleared_pages=[[
        _cleared("130", profit=1.0, commission=0.0, customer_strategy_ref=None, customer_order_ref=None),
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    assert len(env["manual_pnl_writes"]) == 1
    betting.cleared_pages = [[
        _cleared("130", profit=1.0, commission=0.0, customer_strategy_ref=None, customer_order_ref=None),
        _cleared("131", profit=9.0, commission=0.0, customer_strategy_ref="live"),
    ]]
    rw._sync_manual_pnl(session)
    assert len(env["manual_pnl_writes"]) == 2
    assert env["manual_pnl_writes"][1]["orders"] == 1        # sito invariato
    assert env["manual_pnl_writes"][1]["app_orders"] == 1    # app e' cambiato


def test_sync_manual_pnl_pagination_reads_second_page(env):
    betting = _FakeBetting(cleared_pages=[
        [_cleared("50", profit=1.0, customer_strategy_ref=None, customer_order_ref=None)],
        [_cleared("51", profit=2.0, customer_strategy_ref=None, customer_order_ref=None)],
    ])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    assert [c["from_record"] for c in betting.cleared_calls] == [0, 1]  # pagina due letta
    w = env["manual_pnl_writes"][0]
    assert w["orders"] == 2
    assert w["pnl_eur"] == 3.0


def test_sync_manual_pnl_write_on_change_second_run_no_change_no_write(env):
    betting = _FakeBetting(cleared_pages=[[
        _cleared("60", profit=4.0, customer_strategy_ref=None, customer_order_ref=None),
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    assert len(env["manual_pnl_writes"]) == 1
    rw._sync_manual_pnl(session)   # stessi ordini, stesso giorno -> nessuna nuova scrittura
    assert len(env["manual_pnl_writes"]) == 1


def test_sync_manual_pnl_rest_ko_never_raises_and_never_writes_zero(env):
    """Un KO REST non deve MAI azzerare il totale gia' scritto: si esce PRIMA
    di toccare la firma write-on-change, la riga DB resta quella di prima."""
    good = _FakeBetting(cleared_pages=[[
        _cleared("70", profit=9.0, customer_strategy_ref=None, customer_order_ref=None),
    ]])
    session = _session(betting=good)
    rw._sync_manual_pnl(session)
    assert len(env["manual_pnl_writes"]) == 1
    assert env["manual_pnl_writes"][0]["pnl_eur"] == 9.0

    class _BoomBetting:
        def list_cleared_orders(self, **_kw):
            raise RuntimeError("REST KO")

    session_ko = SimpleNamespace(context_api_client=SimpleNamespace(betting=_BoomBetting()))
    rw._sync_manual_pnl(session_ko)   # non deve sollevare
    assert len(env["manual_pnl_writes"]) == 1   # NESSUNA nuova scrittura (tanto meno a zero)


def test_sync_manual_pnl_upsert_ko_migration_not_applied_logs_and_retries(env, monkeypatch):
    """Prima che la migrazione sia applicata l'upsert fallisce (colonne
    assenti): WARNING dichiarato, nessuna eccezione, la firma write-on-change
    NON avanza -> al giro dopo si ritenta (non resta bloccato per sempre)."""
    import Betfair.stream.db as dbmod

    def _boom(**_kw):
        raise Exception("column betfair_live_account.manual_pnl_eur does not exist")

    monkeypatch.setattr(dbmod, "upsert_live_account_manual_pnl", _boom)
    betting = _FakeBetting(cleared_pages=[[
        _cleared("80", profit=1.0, customer_strategy_ref=None, customer_order_ref=None),
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)   # non deve sollevare
    assert rw._LAST_MANUAL_PNL_SIG is None   # firma NON avanzata: ritentera'


def test_sync_manual_pnl_publishes_local_channel(env, monkeypatch):
    import Betfair.stream.local_channel as lc

    published: List[Any] = []
    monkeypatch.setattr(lc, "publish", lambda topic, payload: published.append((topic, dict(payload))))
    betting = _FakeBetting(cleared_pages=[[
        _cleared("90", profit=6.0, customer_strategy_ref=None, customer_order_ref=None),
        _cleared("91", profit=2.0, commission=0.0, customer_strategy_ref="live"),
    ]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)
    assert len(published) == 1
    assert published[0][0] == "account"
    assert published[0][1]["manual_pnl_eur"] == 6.0
    assert published[0][1]["manual_app_pnl_eur"] == 2.0
    assert published[0][1]["manual_app_pnl_orders"] == 1


def test_sync_manual_pnl_never_consults_live_order_mode(env, monkeypatch):
    """MAI in paper: il conto e' reale per definizione — la funzione non deve
    dipendere in alcun modo dalla LIVE_ORDER_MODE del runner calcio."""
    monkeypatch.setattr(rw.low, "_live_order_mode", lambda: (_ for _ in ()).throw(
        AssertionError("_sync_manual_pnl non deve consultare la mode")))
    betting = _FakeBetting(cleared_pages=[[]])
    session = _session(betting=betting)
    rw._sync_manual_pnl(session)  # non deve sollevare l'AssertionError sopra


# ---------------------------------------------------------------------------
# _run_manual_pnl_if_due: cadenza bassa (60s) + trigger immediato su cambio saldo
# ---------------------------------------------------------------------------
def test_run_manual_pnl_if_due_low_cadence_60s(env, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    betting = _FakeBetting(cleared_pages=[[
        _cleared("100", profit=1.0, customer_strategy_ref=None, customer_order_ref=None),
    ]])
    session = _session(betting=betting)
    rw._run_manual_pnl_if_due(session)
    assert len(betting.cleared_calls) == 1
    clock["t"] += 30.0
    rw._run_manual_pnl_if_due(session)      # +30s: troppo presto (cadenza 60s)
    assert len(betting.cleared_calls) == 1
    clock["t"] += 30.1
    rw._run_manual_pnl_if_due(session)      # +60.1s totali: si ritenta
    assert len(betting.cleared_calls) == 2


def test_run_manual_pnl_if_due_forced_bypasses_cadence(env, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    betting = _FakeBetting(cleared_pages=[[]])
    session = _session(betting=betting)
    rw._run_manual_pnl_if_due(session)
    assert len(betting.cleared_calls) == 1
    clock["t"] += 1.0   # ben sotto i 60s
    rw._run_manual_pnl_if_due(session, force=True)   # forzato: gira comunque
    assert len(betting.cleared_calls) == 2


def test_run_account_sync_if_due_forces_manual_pnl_immediately_on_balance_change(env, monkeypatch):
    """Integrazione: run_account_sync_if_due (saldo) fa scattare SUBITO il
    manuale quando il saldo e' appena cambiato, anche se i 60s non sono
    passati — 'a cadenza bassa (60s) e SUBITO dopo un cambio di saldo'."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    account = _FakeAccount(available=100.0, exposure=0.0)
    betting = _FakeBetting(cleared_pages=[[]])
    session = _session(account, betting)
    rw.run_account_sync_if_due(session)             # prima lettura: saldo "cambia" (era None)
    assert len(betting.cleared_calls) == 1           # scattato SUBITO (force=True)
    clock["t"] += 21.0                                # 20s dopo: nuovo giro saldo, INVARIATO
    rw.run_account_sync_if_due(session)
    assert len(betting.cleared_calls) == 1            # non forzato, e 60s non passati: niente


def test_run_account_sync_if_due_manual_pnl_not_forced_when_balance_unchanged(env, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    account = _FakeAccount(available=50.0, exposure=0.0)
    betting = _FakeBetting(cleared_pages=[[]])
    session = _session(account, betting)
    rw.run_account_sync_if_due(session)
    rw._LAST_MANUAL_PNL_TS = clock["t"]  # simula: il manuale e' appena girato per conto suo
    clock["t"] += 20.1
    rw.run_account_sync_if_due(session)  # saldo invariato -> niente force
    assert len(betting.cleared_calls) == 1  # nessun secondo giro (60s non passati, non forzato)
