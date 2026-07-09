"""Test ADVERSARIALI del daily_stop_worker (E34 — stop giornaliero di conto).

NESSUNA rete: supabase, flumine, blotter e db sono fake in-memory. La matematica
usa trading/daily_pnl REALE. Sotto test le garanzie money-critical:
  - mai un falso scatto (limite off/invalido, P&L entro soglia, mode OFF);
  - mai un mancato scatto (al limite esatto, worst-case su prezzi mancanti,
    retry dopo RPC fallita, ri-scatto se l'utente riattiva col P&L oltre soglia);
  - mai silenzioso (alert CRITICAL su scatto/RPC fallita/dati corrotti; audit).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.daily_stop_worker as dsw


# ---------------------------------------------------------------------------
# Fake Supabase
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _SettledQuery:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *_a: Any) -> "_SettledQuery":
        return self

    def eq(self, k: str, v: Any) -> "_SettledQuery":
        self._rows = [r for r in self._rows if r.get(k) == v]
        return self

    def gte(self, _k: str, _v: Any) -> "_SettledQuery":
        return self  # la finestra temporale è testata in test_daily_pnl (day_window_utc)

    def lt(self, _k: str, _v: Any) -> "_SettledQuery":
        return self

    def execute(self) -> _Resp:
        return _Resp([dict(r) for r in self._rows])


class _InsertQuery:
    def __init__(self, sink: List[Dict[str, Any]]) -> None:
        self._sink = sink
        self._payload: Optional[Dict[str, Any]] = None

    def insert(self, payload: Dict[str, Any]) -> "_InsertQuery":
        self._payload = dict(payload)
        return self

    def execute(self) -> _Resp:
        if self._payload is not None:
            self._sink.append(self._payload)
        return _Resp(None)


class _Rpc:
    def __init__(self, fn) -> None:
        self._fn = fn

    def execute(self) -> _Resp:
        return _Resp(self._fn())


class _FakeSb:
    """Supabase fake: settled rows + cattura kill-switch RPC e audit insert."""

    def __init__(self, settled: Optional[List[Dict[str, Any]]] = None) -> None:
        # righe senza mode esplicito → 'paper' (la mode di default dei test)
        self.settled = [{"mode": "paper", **r} for r in (settled or [])]
        self.audit: List[Dict[str, Any]] = []
        self.kill_calls: List[Dict[str, Any]] = []
        self.kill_response: Any = {"kill_switch": True}
        self.kill_raises: bool = False

    def table(self, name: str) -> Any:
        if name == "betfair_live_settled":
            return _SettledQuery(self.settled)
        if name == "betfair_live_audit":
            return _InsertQuery(self.audit)
        raise AssertionError(f"tabella inattesa: {name}")

    def rpc(self, name: str, args: Dict[str, Any]) -> _Rpc:
        assert name == "set_live_kill_switch", f"rpc inattesa: {name}"

        def _run() -> Any:
            self.kill_calls.append(dict(args))
            if self.kill_raises:
                raise RuntimeError("rpc KO")
            return self.kill_response

        return _Rpc(_run)


# ---------------------------------------------------------------------------
# Fake flumine (markets + blotter)
# ---------------------------------------------------------------------------
class _FakeBlotter:
    def __init__(self, orders: List[Any], exposures: Dict[tuple, Dict[str, float]]) -> None:
        self._orders = orders
        self._exposures = exposures

    def strategy_orders(self, _strategy: Any) -> List[Any]:
        return list(self._orders)

    def get_exposures(self, _strategy: Any, lookup: tuple) -> Dict[str, float]:
        exp = self._exposures.get(lookup)
        if exp is None:
            raise KeyError(lookup)
        return dict(exp)


def _order(lookup: tuple, cleared_profit: Optional[float] = None) -> Any:
    cleared = SimpleNamespace(profit=cleared_profit) if cleared_profit is not None else None
    return SimpleNamespace(lookup=lookup, cleared_order=cleared)


def _market(
    market_id: str,
    *,
    closed: bool = False,
    orders: Optional[List[Any]] = None,
    exposures: Optional[Dict[tuple, Dict[str, float]]] = None,
    best_back: Optional[float] = 2.0,
    best_lay: Optional[float] = 2.02,
    event_id: str = "ev1",
) -> Any:
    orders = orders or []
    runners = []
    for o in orders:
        sel = o.lookup[1]
        ex = SimpleNamespace(
            available_to_back=(
                [SimpleNamespace(price=best_back, size=100.0)] if best_back else []
            ),
            available_to_lay=(
                [SimpleNamespace(price=best_lay, size=100.0)] if best_lay else []
            ),
        )
        runners.append(SimpleNamespace(selection_id=sel, handicap=0.0, ex=ex))
    return SimpleNamespace(
        market_id=market_id,
        event_id=event_id,
        closed=closed,
        blotter=_FakeBlotter(orders, exposures or {}),
        market_book=SimpleNamespace(runners=runners),
        market_catalogue=None,
    )


def _flumine(*markets: Any) -> Any:
    return SimpleNamespace(
        markets=SimpleNamespace(markets={m.market_id: m for m in markets})
    )


_STRATEGY = object()


# ---------------------------------------------------------------------------
# Fixture: isola settings/mode/global del worker + cattura db.* e alert
# ---------------------------------------------------------------------------
@pytest.fixture()
def env(monkeypatch):
    state = {
        "mode": "PAPER",
        "settings": {"kill_switch": False, "daily_loss_limit": 50.0},
        "alerts": [],
        "risk_states": [],
        "settled_writes": [],
    }
    monkeypatch.setattr(dsw.low, "_live_order_mode", lambda: state["mode"])
    monkeypatch.setattr(dsw.low, "_refresh_settings", lambda _sb: None)
    monkeypatch.setattr(dsw.low, "_SETTINGS", state["settings"], raising=False)

    import Betfair.stream.db as dbmod

    monkeypatch.setattr(
        dbmod, "insert_alert",
        lambda level, code, message, event_id=None: state["alerts"].append((level, code, message)),
    )
    monkeypatch.setattr(
        dbmod, "upsert_live_risk_state", lambda row: state["risk_states"].append(dict(row))
    )
    monkeypatch.setattr(
        dbmod, "upsert_live_settled", lambda row: state["settled_writes"].append(dict(row))
    )
    # reset dei global write-on-change/anti-spam del worker
    monkeypatch.setattr(dsw, "_LAST_STATE_SIG", None)
    monkeypatch.setattr(dsw, "_LAST_SETTLED_SIG", {})
    monkeypatch.setattr(dsw, "_WARNED_DAY", {})
    monkeypatch.setattr(dsw, "_ALERT_LAST_TS", {})
    return state


def _critical(env) -> List[str]:
    return [m for (lvl, _c, m) in env["alerts"] if lvl == "CRITICAL"]


# ---------------------------------------------------------------------------
# Falsi scatti: MAI
# ---------------------------------------------------------------------------
def test_off_mode_does_nothing(env):
    env["mode"] = "OFF"
    sb = _FakeSb([{"profit": -999.0}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert sb.kill_calls == []
    assert env["risk_states"] == []


def test_no_fire_when_limit_absent(env):
    env["settings"].pop("daily_loss_limit")
    sb = _FakeSb([{"profit": -999.0}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert sb.kill_calls == []
    assert env["risk_states"][-1]["stop_fired"] is False
    assert env["risk_states"][-1]["detail"]["reason"] == "limit_off"


def test_no_fire_within_limit(env):
    sb = _FakeSb([{"profit": -49.99}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert sb.kill_calls == []
    assert env["risk_states"][-1]["stop_fired"] is False


def test_invalid_limit_warns_once_and_never_fires(env):
    env["settings"]["daily_loss_limit"] = -5
    sb = _FakeSb([{"profit": -999.0}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert sb.kill_calls == []
    warns = [m for (lvl, _c, m) in env["alerts"] if lvl == "WARN" and "INVALIDO" in m]
    assert len(warns) == 1  # anti-spam: una volta per giornata


def test_profit_day_never_fires(env):
    sb = _FakeSb([{"profit": 120.0}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert sb.kill_calls == []


# ---------------------------------------------------------------------------
# Scatti dovuti: SEMPRE (e mai silenziosi)
# ---------------------------------------------------------------------------
def test_fires_on_realized_loss(env):
    sb = _FakeSb([{"profit": -60.0}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert sb.kill_calls == [{"p_on": True}]
    assert any("STOP GIORNALIERO SCATTATO" in m for m in _critical(env))
    assert sb.audit and sb.audit[0]["action"] == "daily_stop"
    assert env["risk_states"][-1]["stop_fired"] is True
    assert env["risk_states"][-1]["detail"]["kill_switch"] is True


def test_fires_exactly_at_limit(env):
    sb = _FakeSb([{"profit": -50.0}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert sb.kill_calls == [{"p_on": True}]


def test_fires_on_open_mtm_loss(env):
    # nessun settled; posizione aperta con MTM −60: W=-70, L=-50, diff=-20 → BACK@2.0
    # locked = L + diff/p = -50 + (-20/2.0) = -60
    lookup = ("1.23", 111, 0.0)
    exp = {
        "matched_profit_if_win": -70.0,
        "matched_profit_if_lose": -50.0,
        "worst_possible_profit_on_win": -70.0,
        "worst_possible_profit_on_lose": -50.0,
    }
    m = _market("1.23", orders=[_order(lookup)], exposures={lookup: exp})
    sb = _FakeSb([])
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert sb.kill_calls == [{"p_on": True}]
    state = env["risk_states"][-1]
    assert state["open_mtm"] == pytest.approx(-60.0)
    assert state["realized"] == pytest.approx(0.0)


def test_missing_prices_use_worst_case_conservative(env):
    # book vuoto → MTM non calcolabile → worst-case (−100) → scatta (limite 50).
    lookup = ("1.23", 111, 0.0)
    exp = {
        "matched_profit_if_win": 10.0,
        "matched_profit_if_lose": -40.0,
        "worst_possible_profit_on_win": 5.0,
        "worst_possible_profit_on_lose": -100.0,
    }
    m = _market(
        "1.23", orders=[_order(lookup)], exposures={lookup: exp},
        best_back=None, best_lay=None,
    )
    sb = _FakeSb([])
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert sb.kill_calls == [{"p_on": True}]
    assert env["risk_states"][-1]["detail"]["degraded"] is True
    assert any("worst-case" in m for m in _critical(env))


def test_rpc_failure_alerts_and_retries_next_cycle(env):
    sb = _FakeSb([{"profit": -60.0}])
    sb.kill_raises = True
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert any("FALLITA" in m for m in _critical(env))
    assert env["risk_states"][-1]["detail"]["kill_switch"] is False
    # il DB kill resta off → al ciclo dopo RITENTA
    sb.kill_raises = False
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert len(sb.kill_calls) == 2


def test_rpc_unconfirmed_is_failure(env):
    sb = _FakeSb([{"profit": -60.0}])
    sb.kill_response = {"kill_switch": False}
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert any("NON confermato" in m for m in _critical(env))
    assert env["risk_states"][-1]["detail"]["kill_switch"] is False


def test_no_duplicate_activation_when_kill_already_on(env):
    env["settings"]["kill_switch"] = True
    sb = _FakeSb([{"profit": -60.0}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert sb.kill_calls == []  # già fermo: nessuna ri-attivazione, nessuno spam
    assert env["risk_states"][-1]["stop_fired"] is True


def test_refires_if_user_rearms_with_loss_beyond_limit(env):
    sb = _FakeSb([{"profit": -60.0}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert len(sb.kill_calls) == 1
    # l'utente spegne il kill (decisione sua) ma il P&L resta oltre soglia
    env["settings"]["kill_switch"] = False
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert len(sb.kill_calls) == 2  # lo stop RISCATTA (limite = enforcement, non consiglio)


# ---------------------------------------------------------------------------
# Dati corrotti: mai silenzioso, mai "0"
# ---------------------------------------------------------------------------
def test_corrupt_settled_alerts_critical_and_skips(env):
    sb = _FakeSb([{"profit": None}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert sb.kill_calls == []
    assert env["risk_states"] == []  # nessuno stato pubblicato su dati inaffidabili
    assert any("ILLEGGIBILI" in m for m in _critical(env))


def test_unreadable_positions_degrade_and_alert_critical(env):
    # get_exposures solleva → posizione illeggibile: degraded + alert CRITICAL
    # (fix review CRITICAL: buco di rischio non quantificabile, mai un WARN sommesso)
    lookup = ("1.23", 111, 0.0)
    m = _market("1.23", orders=[_order(lookup)], exposures={})
    sb = _FakeSb([])
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert env["risk_states"][-1]["detail"]["degraded"] is True
    crit = [msg for (lvl, _c, msg) in env["alerts"] if lvl == "CRITICAL"]
    assert any("NON leggibili" in msg for msg in crit)
    # cooldown anti-flood: un secondo ciclo immediato NON duplica l'alert
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    crit2 = [msg for (lvl, _c, msg) in env["alerts"] if lvl == "CRITICAL" and "NON leggibili" in msg]
    assert len(crit2) == 1


# ---------------------------------------------------------------------------
# Sweep LIVE dei cleared orders → settled (fonte autoritativa Betfair)
# ---------------------------------------------------------------------------
def test_live_sweep_writes_settled_from_cleared(env):
    env["mode"] = "LIVE"
    lookup = ("1.99", 222, 0.0)
    m = _market(
        "1.99", closed=True,
        orders=[_order(lookup, cleared_profit=-12.5), _order(lookup, cleared_profit=4.0)],
    )
    sb = _FakeSb([])
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert len(env["settled_writes"]) == 1
    row = env["settled_writes"][0]
    assert row["mode"] == "live"
    assert row["source"] == "cleared"
    assert row["profit"] == pytest.approx(-8.5)
    assert row["orders"] == 2
    # write-on-change: stesso stato → nessuna seconda scrittura
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert len(env["settled_writes"]) == 1


def test_live_sweep_skips_open_markets_and_uncleared(env):
    env["mode"] = "LIVE"
    lookup = ("1.99", 222, 0.0)
    open_m = _market("1.98", closed=False, orders=[_order(lookup, cleared_profit=9.0)])
    pending = _market("1.99", closed=True, orders=[_order(lookup)])  # nessun cleared
    sb = _FakeSb([])
    dsw._process_once(sb, _flumine(open_m, pending), _STRATEGY)
    assert env["settled_writes"] == []


def test_paper_mode_does_not_sweep_cleared(env):
    env["mode"] = "PAPER"
    lookup = ("1.99", 222, 0.0)
    m = _market("1.99", closed=True, orders=[_order(lookup, cleared_profit=9.0)])
    sb = _FakeSb([])
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert env["settled_writes"] == []


# ---------------------------------------------------------------------------
# Stato pubblicato (top bar): write-on-change, MTM esclude i mercati chiusi
# ---------------------------------------------------------------------------
def test_state_write_on_change(env):
    sb = _FakeSb([{"profit": -10.0}])
    dsw._process_once(sb, _flumine(), _STRATEGY)
    dsw._process_once(sb, _flumine(), _STRATEGY)
    assert len(env["risk_states"]) == 1
    sb.settled.append({"profit": -5.0, "mode": "paper"})
    # NB: il fake filtra per mode solo su eq(): la riga aggiunta senza mode non matcha,
    # quindi cambio realized aggiungendo una riga coerente
    sb2 = _FakeSb([{"profit": -15.0}])
    dsw._process_once(sb2, _flumine(), _STRATEGY)
    assert len(env["risk_states"]) == 2


def test_mtm_excludes_closed_markets_once_settled(env):
    # PAPER: mercato chiuso CON profit simulato → lo sweep backstop scrive il settled
    # nello stesso ciclo → il mercato esce dall'MTM (mai doppio conteggio).
    lookup = ("1.23", 111, 0.0)
    exp = {
        "matched_profit_if_win": -70.0,
        "matched_profit_if_lose": -50.0,
        "worst_possible_profit_on_win": -70.0,
        "worst_possible_profit_on_lose": -50.0,
    }
    orders = [_order(lookup)]
    orders[0].simulated = SimpleNamespace(profit=-20.0)
    m = _market("1.23", closed=True, orders=orders, exposures={lookup: exp})
    sb = _FakeSb([])
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert env["settled_writes"] and env["settled_writes"][0]["source"] == "simulated"
    assert env["settled_writes"][0]["profit"] == pytest.approx(-20.0)
    assert env["risk_states"][-1]["open_mtm"] == pytest.approx(0.0)
    assert sb.kill_calls == []  # −20 entro il limite 50


def test_closed_uncleared_live_market_counts_worst_case(env):
    # fix review CRITICAL (gap cleared LIVE): mercato chiuso i cui cleared non sono
    # ancora arrivati NON deve sparire dal P&L → conteggiato worst-case (conservativo).
    env["mode"] = "LIVE"
    lookup = ("1.23", 111, 0.0)
    exp = {
        "matched_profit_if_win": -80.0,
        "matched_profit_if_lose": -60.0,
        "worst_possible_profit_on_win": -80.0,
        "worst_possible_profit_on_lose": -60.0,
    }
    m = _market("1.23", closed=True, orders=[_order(lookup)], exposures={lookup: exp},
                best_back=None, best_lay=None)
    sb = _FakeSb([])
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert env["settled_writes"] == []                      # nessun cleared → nessun settled
    state = env["risk_states"][-1]
    assert state["open_mtm"] == pytest.approx(-80.0)         # worst-case, mai invisibile
    assert state["detail"]["degraded"] is True
    assert sb.kill_calls == [{"p_on": True}]                 # −80 oltre il limite 50 → scatta


def test_paper_backstop_retries_after_db_failure(env, monkeypatch):
    # fix review CRITICAL (settle one-shot): se l'upsert fallisce, lo sweep RITENTA
    # al ciclo successivo (mai un P&L perso per sempre per un blip DB).
    lookup = ("1.23", 111, 0.0)
    orders = [_order(lookup)]
    orders[0].simulated = SimpleNamespace(profit=-20.0)
    m = _market("1.23", closed=True, orders=orders,
                exposures={lookup: {
                    "matched_profit_if_win": -20.0, "matched_profit_if_lose": -20.0,
                    "worst_possible_profit_on_win": -20.0, "worst_possible_profit_on_lose": -20.0,
                }})
    sb = _FakeSb([])
    import Betfair.stream.db as dbmod
    calls = {"n": 0}

    def _flaky(row):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db blip")
        env["settled_writes"].append(dict(row))

    monkeypatch.setattr(dbmod, "upsert_live_settled", _flaky)
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert env["settled_writes"] == []                       # primo ciclo: fallito
    dsw._process_once(sb, _flumine(m), _STRATEGY)
    assert len(env["settled_writes"]) == 1                   # retry riuscito


def test_entry_never_raises(env, monkeypatch):
    # entry robusta: _process_once che esplode NON deve propagare
    monkeypatch.setattr(dsw, "_process_once", lambda *_a, **_k: 1 / 0)
    monkeypatch.setattr("db_client.get_supabase_client", lambda: _FakeSb([]), raising=False)
    dsw.daily_stop_worker({}, _flumine(), None, _STRATEGY)  # nessuna eccezione
