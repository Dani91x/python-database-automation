"""Test ADVERSARIALI di A3 (cash-out COMPLETO) e A4 (follow-through manuale).

NESSUNA rete: flumine/blotter/supabase/db sono fake. Garanzie money-critical:
  A3 — il cash-out annulla PRIMA tutti gli unmatched (mai un resting che si
       abbina dopo l'hedge), un cancel fallito = cash-out INCOMPLETO (errore
       esplicito); il greenup di selezione cancella SOLO con l'opt-in
       params.cancel_unmatched (mai per greening column / risk engine).
  A4 — hedge non abbinato oltre soglia → cancel + re-hedge BOUNDED con ref
       deterministico; mai due hedge vivi; retry esauriti → CRITICAL una volta;
       righe del risk engine escluse.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.live_order_worker as wk


# ---------------------------------------------------------------------------
# Fake flumine: ordini + blotter + market
# ---------------------------------------------------------------------------
def _order(
    bet_id: str = "B1",
    selection_id: int = 111,
    status: str = "EXECUTABLE",
    remaining: float = 5.0,
    ref: Optional[str] = None,
) -> Any:
    return SimpleNamespace(
        bet_id=bet_id,
        selection_id=selection_id,
        handicap=0.0,
        status=SimpleNamespace(name=status),
        size_remaining=remaining,
        market_id="1.1",
        notes=None,
        context={"customer_order_ref": ref} if ref else {},
    )


class _Blotter:
    def __init__(self, orders: List[Any]) -> None:
        self._orders = orders

    def strategy_orders(self, _strategy: Any) -> List[Any]:
        return list(self._orders)

    def get_order_bet_id(self, bet_id: str) -> Optional[Any]:
        for o in self._orders:
            if getattr(o, "bet_id", None) == bet_id:
                return o
        return None

    def __iter__(self):
        return iter(self._orders)


class _Market:
    def __init__(self, market_id: str = "1.1", orders: Optional[List[Any]] = None) -> None:
        self.market_id = market_id
        self.event_id = "ev1"
        self.blotter = _Blotter(orders or [])
        self.market_book = SimpleNamespace(runners=[])
        self.cancel_calls: List[Any] = []
        self.cancel_result = True

    def cancel_order(self, order: Any, size_reduction: Any = None) -> bool:
        self.cancel_calls.append(order)
        return self.cancel_result


def _flumine(*markets: _Market) -> Any:
    ns = SimpleNamespace(markets=SimpleNamespace(markets={m.market_id: m for m in markets}))
    ns.markets.__iter__ = None  # non usato direttamente
    # _find_order_by_bet_id itera flumine.markets in fallback: rendiamolo iterabile
    class _Mkts:
        def __init__(self, d):
            self.markets = d

        def __iter__(self):
            return iter(self.markets.values())

    return SimpleNamespace(markets=_Mkts({m.market_id: m for m in markets}))


_STRATEGY = object()


# ===========================================================================
# A3 — _cancel_unmatched / _flatten_market cancel-first
# ===========================================================================
def test_cancel_unmatched_cancels_only_executable_with_remaining():
    orders = [
        _order("B1", 111, "EXECUTABLE", 5.0),
        _order("B2", 111, "EXECUTION_COMPLETE", 0.0),
        _order("B3", 222, "EXECUTABLE", 0.0),     # rem 0: nulla da cancellare
        _order("B4", 222, "PENDING", 5.0),         # non ancora cancellabile
    ]
    m = _Market(orders=orders)
    n, failed = wk._cancel_unmatched(m, _STRATEGY)
    assert n == 1
    assert failed == []
    assert [o.bet_id for o in m.cancel_calls] == ["B1"]


def test_cancel_unmatched_selection_filter():
    orders = [_order("B1", 111), _order("B2", 222)]
    m = _Market(orders=orders)
    n, _ = wk._cancel_unmatched(m, _STRATEGY, selection_id=222)
    assert n == 1
    assert m.cancel_calls[0].bet_id == "B2"


def test_cancel_unmatched_collects_failures_and_continues():
    m = _Market(orders=[_order("B1", 111), _order("B2", 222)])
    m.cancel_result = False  # control flumine rifiuta il cancel
    n, failed = wk._cancel_unmatched(m, _STRATEGY)
    assert n == 0
    assert len(failed) == 2  # entrambi tentati, entrambi tracciati
    assert "cancel unmatched fallito" in failed[0]["error"]


def test_flatten_market_cancels_before_hedging_and_reports_count():
    m = _Market(orders=[_order("B1", 111, "EXECUTABLE", 5.0)])
    closed, idx, failed, cancelled = wk._flatten_market(_flumine(m), m, _STRATEGY, 1.0, 42, 0)
    assert cancelled == 1
    assert failed == []
    assert closed == []  # nessun runner nel book → nessun hedge
    assert m.cancel_calls  # il cancel è avvenuto


def test_cashout_all_raises_incompleto_on_cancel_failure(monkeypatch):
    m = _Market(orders=[_order("B1", 111)])
    m.cancel_result = False
    flu = _flumine(m)

    class _Sb:
        def table(self, name):
            raise AssertionError("non deve scrivere: deve sollevare prima")

        def rpc(self, *_a, **_k):
            raise AssertionError("no rpc")

    req = {"id": 42, "action": "cashout_all", "market_id": "1.1", "params": None}
    with pytest.raises(ValueError, match="INCOMPLETO"):
        wk._do_cashout_all(_Sb(), flu, req, "paper", _STRATEGY)


def test_greenup_cancel_unmatched_only_with_opt_in(monkeypatch):
    calls: List[Any] = []
    monkeypatch.setattr(wk, "_cancel_unmatched", lambda m, s, selection_id=None: (calls.append(selection_id) or (1, [])))
    m = _Market()
    monkeypatch.setattr(wk, "_resolve_market", lambda _f, _mid: m)
    monkeypatch.setattr(wk, "_read_matched_exposures", lambda *_a: (0.0, 0.0))  # piatta → no-op
    monkeypatch.setattr(wk, "_best_prices", lambda *_a: (2.0, 2.02))
    written: List[Dict[str, Any]] = []
    monkeypatch.setattr(wk, "_write_done", lambda _sb, _rid, result: written.append(result))

    base = {"id": 42, "action": "greenup", "market_id": "1.1", "selection_id": 111, "handicap": 0}
    # SENZA opt-in → nessun cancel
    wk._do_greenup(object(), _flumine(m), {**base, "params": {"fraction": 1.0}}, "paper", _STRATEGY)
    assert calls == []
    # CON opt-in → cancel della SOLA selezione
    wk._do_greenup(object(), _flumine(m), {**base, "params": {"fraction": 1.0, "cancel_unmatched": True}}, "paper", _STRATEGY)
    assert calls == [111]
    assert "unmatched annullati: 1" in (written[-1].get("detail") or "")


# ===========================================================================
# A4 — follow-through dei cash-out manuali
# ===========================================================================
class _FtSb:
    """Fake supabase per lo sweep follow-through: righe coda + cattura rpc/update."""

    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows
        self.updates: List[Dict[str, Any]] = []
        self.enqueued: List[Dict[str, Any]] = []
        self.rpc_raises = False

    def table(self, name: str):
        assert name == wk._TABLE
        sb = self

        class _Q:
            def __init__(self):
                self._update = None
                self._id = None

            def select(self, *_a):
                return self

            def eq(self, k, v):
                if self._update is not None and k == "id":
                    self._id = v
                return self

            def in_(self, *_a):
                return self

            def gte(self, *_a):
                return self

            def order(self, *_a):
                return self

            def limit(self, *_a):
                return self

            def update(self, payload):
                self._update = payload
                return self

            def execute(self):
                if self._update is not None:
                    sb.updates.append({"id": self._id, **self._update})
                    # persisti nel fake (per il ciclo successivo)
                    for r in sb.rows:
                        if r.get("id") == self._id:
                            r["result"] = self._update.get("result", r.get("result"))
                    return SimpleNamespace(data=[])
                return SimpleNamespace(data=[dict(r) for r in sb.rows])

        return _Q()

    def rpc(self, name: str, args: Dict[str, Any]):
        assert name == "request_betfair_live_order"
        sb = self

        class _R:
            def execute(self):
                if sb.rpc_raises:
                    raise RuntimeError("rpc KO")
                sb.enqueued.append(args["p"])
                return SimpleNamespace(data=1000 + len(sb.enqueued))

        return _R()


def _done_row(
    rid: int = 42,
    action: str = "greenup",
    age_sec: float = 30.0,
    result: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_sec)).isoformat()
    return {
        "id": rid, "action": action, "mode": "paper", "market_id": "1.1",
        "selection_id": 111, "handicap": 0,
        "params": params, "processed_at": ts,
        "result": result if result is not None else {
            "bet_id": "H1", "customer_order_ref": "awlq42", "size": 3.0,
        },
    }


@pytest.fixture()
def alerts(monkeypatch):
    sink: List[str] = []
    import Betfair.stream.db as dbmod

    monkeypatch.setattr(
        dbmod, "insert_alert",
        lambda level, code, msg, event_id=None: sink.append(f"{level}:{code}:{msg}"),
    )
    return sink


def test_ft_hedge_filled_marks_done(alerts):
    m = _Market(orders=[_order("H1", 111, "EXECUTION_COMPLETE", 0.0)])
    sb = _FtSb([_done_row()])
    wk._check_manual_followthrough(sb, _flumine(m), "paper")
    assert sb.enqueued == []
    assert sb.updates and sb.updates[-1]["result"]["ft"]["done"] is True


def test_ft_unfilled_hedge_cancel_then_rehedge(alerts):
    m = _Market(orders=[_order("H1", 111, "EXECUTABLE", 3.0)])
    sb = _FtSb([_done_row(params={"fraction": 0.5})])
    wk._check_manual_followthrough(sb, _flumine(m), "paper")
    # 1) cancel dell'hedge stantio
    assert [o.bet_id for o in m.cancel_calls] == ["H1"]
    # 2) re-hedge accodato con ref DETERMINISTICO e frazione ORIGINALE
    assert len(sb.enqueued) == 1
    p = sb.enqueued[0]
    assert p["client_ref"] == "ft42s111r1"
    assert p["action"] == "greenup"
    assert p["params"]["fraction"] == 0.5
    assert p["params"]["ft_retry"] == 1
    st = sb.updates[-1]["result"]["ft"]["legs"]["1.1:111"]
    assert st["handed_off"] is True


def test_ft_too_young_row_untouched(alerts):
    m = _Market(orders=[_order("H1", 111, "EXECUTABLE", 3.0)])
    sb = _FtSb([_done_row(age_sec=3.0)])
    wk._check_manual_followthrough(sb, _flumine(m), "paper")
    assert sb.enqueued == [] and m.cancel_calls == [] and sb.updates == []


def test_ft_risk_engine_rows_excluded(alerts):
    m = _Market(orders=[_order("H1", 111, "EXECUTABLE", 3.0)])
    sb = _FtSb([_done_row(params={"risk_rule_id": 7})])
    wk._check_manual_followthrough(sb, _flumine(m), "paper")
    assert sb.enqueued == [] and m.cancel_calls == []


def test_ft_cancel_failure_blocks_rehedge(alerts):
    # MAI due hedge vivi: se il cancel fallisce, NESSUN re-hedge in questo giro.
    m = _Market(orders=[_order("H1", 111, "EXECUTABLE", 3.0)])
    m.cancel_result = False
    sb = _FtSb([_done_row()])
    wk._check_manual_followthrough(sb, _flumine(m), "paper")
    assert sb.enqueued == []


def test_ft_retries_exhausted_critical_alert_once(alerts):
    # riga di RETRY (ft_retry=2 = ultimo consentito) col suo hedge ancora unmatched
    m = _Market(orders=[_order("H9", 111, "EXECUTABLE", 3.0)])
    row = _done_row(rid=77, result={"bet_id": "H9", "customer_order_ref": "awlq77", "size": 3.0},
                    params={"fraction": 1.0, "ft_retry": 2, "ft_parent": 42})
    sb = _FtSb([row])
    wk._check_manual_followthrough(sb, _flumine(m), "paper")
    crit = [a for a in alerts if a.startswith("CRITICAL:CASHOUT_FT")]
    assert len(crit) == 1 and "CHIUDERE A MANO" in crit[0]
    assert sb.enqueued == []  # niente altro re-hedge
    # secondo giro: alerted persistito → nessun duplicato
    wk._check_manual_followthrough(sb, _flumine(m), "paper")
    assert len([a for a in alerts if a.startswith("CRITICAL:CASHOUT_FT")]) == 1


def test_ft_order_lost_rehedges_directly(alerts):
    # hedge introvabile nel blotter (crash/restart): re-hedge diretto (ricalcola dal reale)
    m = _Market(orders=[])
    sb = _FtSb([_done_row()])
    wk._check_manual_followthrough(sb, _flumine(m), "paper")
    assert len(sb.enqueued) == 1


def test_ft_cashout_row_rehedges_only_unfilled_leg(alerts):
    filled = _order("L1", 111, "EXECUTION_COMPLETE", 0.0, ref="awlq42x0")
    unfilled = _order("L2", 222, "EXECUTABLE", 4.0, ref="awlq42x1")
    m = _Market(orders=[filled, unfilled])
    row = _done_row(action="cashout_all", result={
        "legs": [
            {"market_id": "1.1", "selection_id": 111, "handicap": 0.0, "ref": "awlq42x0", "bet_id": "L1"},
            {"market_id": "1.1", "selection_id": 222, "handicap": 0.0, "ref": "awlq42x1", "bet_id": "L2"},
        ],
    })
    sb = _FtSb([row])
    wk._check_manual_followthrough(sb, _flumine(m), "paper")
    assert len(sb.enqueued) == 1
    assert sb.enqueued[0]["selection_id"] == 222
    legs = sb.updates[-1]["result"]["ft"]["legs"]
    assert legs["1.1:111"]["ok"] is True
    assert legs["1.1:222"]["handed_off"] is True


def test_ft_noop_greenup_row_closed_without_action(alerts):
    # greenup no-op (posizione già piatta: size None) → follow-through chiuso subito
    row = _done_row(result={"bet_id": None, "customer_order_ref": "awlq42", "size": None})
    sb = _FtSb([row])
    wk._check_manual_followthrough(sb, _flumine(_Market()), "paper")
    assert sb.enqueued == []
    assert sb.updates and sb.updates[-1]["result"]["ft"]["done"] is True
    # secondo giro: ft.done persistito → riga saltata, nessun nuovo update
    n_updates = len(sb.updates)
    wk._check_manual_followthrough(sb, _flumine(_Market()), "paper")
    assert len(sb.updates) == n_updates


def test_greenup_rejects_cancel_unmatched_with_target_price(monkeypatch):
    # fix review HIGH: la coda accetta richieste da qualunque origine → la
    # combinazione contraddittoria va rifiutata ANCHE dal worker, non solo dal client.
    m = _Market()
    monkeypatch.setattr(wk, "_resolve_market", lambda _f, _mid: m)
    req = {
        "id": 42, "action": "greenup", "market_id": "1.1", "selection_id": 111,
        "handicap": 0,
        "params": {"fraction": 1.0, "cancel_unmatched": True, "target_price": 2.5},
    }
    with pytest.raises(ValueError, match="cancel_unmatched"):
        wk._do_greenup(object(), _flumine(m), req, "paper", _STRATEGY)
