"""Test dei fix money-critical dell'audit 2026-07 (sezione Live Trading).

Copre i finding confermati dalla review adversariale multi-agente:
  CRITICAL-1  place/cancel/replace flumine ritornano False su rifiuto dei control →
              il worker DEVE scrivere 'error', mai 'done ok=True' su ordini inesistenti.
  CRITICAL-2  LiveTradingStrategy disattiva i default nascosti di BaseStrategy
              (max_order_exposure=10, max_selection_exposure=100, max_live_trade_count=1).
  HIGH (math) evaluate_rule NON solleva su params malformati: RuleDecision.error
              (disarmo visibile nel worker, mai retry silenzioso infinito).
  HIGH (dutch) gamba senza prezzo risolvibile → NESSUN ordine; place rifiutato a metà →
              rollback best-effort delle gambe già piazzate.
  HIGH-3      follow-through regole 'triggered': richiesta in error → retry bounded;
              esauriti → rule 'error' + alert CRITICAL.
  MEDIUM      dutch_variable con pesi irrealizzabili (stake negativo) → non azionabile;
              xhedge espone ignored_orders; greenup con esposizioni NaN → no-op;
              kill-switch blocca le APERTURE ma lascia passare le CHIUSURE;
              LiveRateControl non rate-limita gli ordini reduces_liability;
              specchio: riconciliazione per bet_id dopo riavvio (no righe duplicate).

Nessuna rete, nessun login, nessun ordine reale: tutto mock in-memory.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.live_order_worker as wk
import Betfair.stream.risk_engine_worker as rw
import Betfair.stream.engine.live_trading_strategy as strat_mod
from Betfair.stream.trading import risk_engine
from Betfair.stream.trading.controls import LiveRateControl
from Betfair.stream.trading.dutching import dutch_variable
from Betfair.stream.trading.greenup import compute_greenup
from Betfair.stream.trading.xhedge import compute_xhedge

from .test_live_order_worker import (  # riuso dell'infra mock esistente
    _STRAT,
    _FakeFlumine,
    _FakeMarket,
    _FakeSupabase,
    _by_id,
    _fake_order,
    _row,
)


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "PAPER")
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(wk, "_batch", lambda: 5)
    monkeypatch.setattr(wk, "_max_stake", lambda: 100.0)
    monkeypatch.setattr(wk, "_SETTINGS", {}, raising=False)


# ===========================================================================
# CRITICAL-1 — esito di place/cancel/replace verificato
# ===========================================================================
class _RejectingMarket(_FakeMarket):
    """Market che rifiuta i place come fa flumine su ControlError (ritorna False)."""

    def __init__(self, market_id: str, reject_from_call: int = 0) -> None:
        super().__init__(market_id)
        self._reject_from = reject_from_call
        self._n_places = 0

    def place_order(self, order: Any, **kwargs: Any) -> bool:
        self.calls.append(("place_order", order, kwargs))
        self._n_places += 1
        if self._n_places > self._reject_from:
            order.violation_msg = "Market is not open"
            return False
        return True


def test_place_rejected_by_control_writes_error():
    """place_order → False (control): la riga DEVE finire 'error', mai 'done ok=True'."""
    sb = _FakeSupabase([_row(1)])
    market = _RejectingMarket("1.1", reject_from_call=0)
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "RIFIUTATO" in (row["error"] or "")
    assert "Market is not open" in (row["error"] or "")


def test_cancel_rejected_by_control_writes_error():
    sb = _FakeSupabase([_row(1, action="cancel", bet_id="B1", price=None, size=None)])
    market = _FakeMarket("1.1")
    order = _fake_order(bet_id="B1", market_id="1.1")
    market.blotter.add(order)
    market.cancel_order = lambda o, sr=None: False  # rifiuto del control
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "RIFIUTATO" in (row["error"] or "")


def test_replace_rejected_by_control_writes_error():
    sb = _FakeSupabase([_row(1, action="replace", bet_id="B1", new_price=2.5,
                             price=None, size=None)])
    market = _FakeMarket("1.1")
    order = _fake_order(bet_id="B1", market_id="1.1", side="BACK")
    market.blotter.add(order)
    market.replace_order = lambda o, p: False
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "RIFIUTATO" in (row["error"] or "")


# ===========================================================================
# HIGH (dutch) — gamba senza prezzo → nessun ordine; rollback su rifiuto a metà
# ===========================================================================
def _dutch_row(rid: int = 1, selections: Optional[List[Dict[str, Any]]] = None,
               **params_kw: Any) -> Dict[str, Any]:
    params = {
        "selections": selections
        if selections is not None
        else [{"selection_id": 1, "price": 2.0}, {"selection_id": 2, "price": 2.0}],
        "side": "back",
        "mode": "equal",
        "total_stake": 10.0,
        "pricing": "as_given",
    }
    params.update(params_kw)
    return _row(rid, action="dutch", selection_id=None, side=None,
                price=None, size=None, params=params)


def test_dutch_leg_without_price_places_nothing():
    """Una gamba senza prezzo risolvibile NON viene scartata in silenzio: zero ordini."""
    sb = _FakeSupabase([_dutch_row(selections=[
        {"selection_id": 1, "price": 2.0}, {"selection_id": 2},  # gamba 2 senza prezzo
    ])])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "prezzo non risolvibile" in (row["error"] or "")
    assert market.calls == []  # NESSUNA gamba piazzata


def test_dutch_place_rejected_midway_rolls_back():
    """Place rifiutato sulla gamba 2: la gamba 1 già piazzata viene cancellata (rollback)."""
    sb = _FakeSupabase([_dutch_row()])
    market = _RejectingMarket("1.1", reject_from_call=1)  # 1° place ok, 2° rifiutato
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "rollback" in (row["error"] or "")
    cancels = [c for c in market.calls if c[0] == "cancel_order"]
    places = [c for c in market.calls if c[0] == "place_order"]
    assert len(places) == 2  # tentati due place
    assert len(cancels) == 1  # rollback della gamba già a mercato
    # l'ordine cancellato è quello del PRIMO place (l'unico riuscito)
    assert cancels[0][1] is places[0][1]


def test_dutch_build_failure_places_nothing():
    """Gamba sotto il minimo .it (€2) su build: NESSUN ordine piazzato (all-or-nothing)."""
    # 10€ su 6 selezioni → gambe ~1.67 < €2 minimo back .it
    sels = [{"selection_id": i, "price": 6.0} for i in range(1, 7)]
    sb = _FakeSupabase([_dutch_row(selections=sels)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert market.calls == []  # pre-build all-or-nothing: zero place


# ===========================================================================
# Kill-switch: blocca le APERTURE, lascia passare le CHIUSURE
# ===========================================================================
def test_kill_switch_blocks_opening_but_allows_cancel(monkeypatch):
    # BUG FIX cert 10/07 (visto dal vivo): l'apertura col freno tirato NON resta più
    # 'pending' (veniva ESEGUITA al riarmo, 36s dopo nel test reale, quando l'utente
    # la credeva morta) → ora è RIFIUTATA con esito 'error' esplicito. Le chiusure
    # passano sempre.
    monkeypatch.setattr(wk, "_kill_switch", lambda: True)
    market = _FakeMarket("1.1")
    order = _fake_order(bet_id="B9", market_id="1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    sb = _FakeSupabase([
        _row(1),  # place (apertura) → RIFIUTATA esplicitamente
        _row(2, action="cancel", bet_id="B9", price=None, size=None),  # chiusura → passa
    ])

    wk._process_once(sb, fl, strategy=_STRAT)

    r1 = _by_id(sb, 1)
    assert r1["status"] == "error"                       # mai più pending-trappola
    assert "kill-switch" in str(r1.get("error") or "")   # motivo ESPLICITO per l'utente
    assert _by_id(sb, 2)["status"] == "done"             # cancel eseguito
    assert [c[0] for c in market.calls] == ["cancel_order"]


# ===========================================================================
# HIGH (math) — evaluate_rule: params malformati → RuleDecision.error, MAI raise
# ===========================================================================
def test_evaluate_rule_fractional_ticks_returns_error_not_raise():
    d = risk_engine.evaluate_rule(
        rule_type="stop_loss", entry_side="back", entry_price=2.0,
        params={"trigger_ticks": 0.5}, current_price=2.5,
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.5, best_lay_price=2.52, trail_extreme=None,
    )
    assert d.fire is False
    assert d.error is not None
    assert "trigger_ticks" in d.error


def test_evaluate_rule_both_ticks_and_pct_returns_error():
    d = risk_engine.evaluate_rule(
        rule_type="stop_loss", entry_side="back", entry_price=2.0,
        params={"trigger_ticks": 5, "trigger_pct": 0.02}, current_price=2.5,
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.5, best_lay_price=2.52, trail_extreme=None,
    )
    assert d.fire is False and d.error is not None


def test_evaluate_rule_negative_stop_amount_returns_error():
    """stop_amount=-5 ('perdita 5' digitata col segno): mai più disarmo silenzioso."""
    d = risk_engine.evaluate_rule(
        rule_type="stop_loss", entry_side="back", entry_price=2.0,
        params={"stop_amount": -5.0}, current_price=2.5,
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.5, best_lay_price=2.52, trail_extreme=None,
    )
    assert d.fire is False and d.error is not None and "stop_amount" in d.error


def test_evaluate_rule_trailing_malformed_returns_error():
    d = risk_engine.evaluate_rule(
        rule_type="trailing_stop", entry_side="lay", entry_price=2.0,
        params={"trail_ticks": 0}, current_price=2.5,
        matched_if_win=-5.0, matched_if_lose=10.0,
        best_back_price=2.5, best_lay_price=2.52, trail_extreme=None,
    )
    assert d.fire is False and d.error is not None


def test_evaluate_rule_valid_params_no_error():
    d = risk_engine.evaluate_rule(
        rule_type="stop_loss", entry_side="back", entry_price=2.0,
        params={"trigger_ticks": 5}, current_price=2.02,
        matched_if_win=10.0, matched_if_lose=-5.0,
        best_back_price=2.02, best_lay_price=2.04, trail_extreme=None,
    )
    assert d.error is None


# ===========================================================================
# MEDIUM (math) — greenup NaN / dutch_variable irrealizzabile / xhedge ignorati
# ===========================================================================
def test_greenup_nan_exposures_not_actionable():
    plan = compute_greenup(
        matched_if_win=float("nan"), matched_if_lose=-5.0,
        best_back_price=3.0, best_lay_price=3.05,
    )
    assert plan.actionable is False
    assert plan.side is None and plan.size is None  # contratto dataclass rispettato


def test_dutch_variable_infeasible_weights_not_actionable():
    """Book >100% + peso forte sul longshot → stake negativo: piano rifiutato, non
    clampato (il clamp spenderebbe PIÙ del total_stake richiesto)."""
    plan = dutch_variable([(1, 1.5, 1.0), (2, 1.5, 1.0), (3, 1.5, 10.0)], 100.0)
    assert plan.actionable is False
    assert "irrealizzabili" in plan.note
    assert plan.total_stake == 0.0


def test_dutch_variable_regular_case_still_works():
    plan = dutch_variable([(1, 3.0, 1.0), (2, 3.0, 2.0)], 30.0)
    assert plan.actionable is True
    assert round(sum(leg.size for leg in plan.legs), 2) == plan.total_stake


def test_xhedge_reports_ignored_orders():
    """Un back matched su 'Any Other Home Win' (non mappabile) DEVE risultare ignorato."""
    orders = [{
        "market_id": "1.1", "selection_id": 99, "side": "back",
        "average_price_matched": 4.0, "size_matched": 10.0,
    }]
    meta = {"1.1": {"market_type": "CORRECT_SCORE",
                    "selections": {99: {"name": "Any Other Home Win", "sort_priority": 17}}}}
    out = compute_xhedge(orders, meta)
    assert out["n_positions"] == 0
    assert out["ignored_orders"] == 1


def test_xhedge_ignored_zero_when_all_mapped():
    orders = [{
        "market_id": "1.1", "selection_id": 1, "side": "back",
        "average_price_matched": 2.0, "size_matched": 10.0,
    }]
    meta = {"1.1": {"market_type": "MATCH_ODDS",
                    "selections": {1: {"name": "Home", "sort_priority": 1}}}}
    out = compute_xhedge(orders, meta)
    assert out["n_positions"] == 1
    assert out["ignored_orders"] == 0


# ===========================================================================
# CRITICAL-2 — default nascosti di BaseStrategy disattivati
# ===========================================================================
def test_live_strategy_disables_hidden_flumine_caps():
    s = strat_mod.LiveTradingStrategy(market_filter={}, mode="paper")
    assert s.max_order_exposure is None       # era 10 (€10 per ordine!)
    assert s.max_selection_exposure is None   # era 100
    assert s.max_live_trade_count >= 10**9    # era 1 (un solo ordine vivo per selezione)
    assert s.max_trade_count >= 10**9


def test_live_strategy_caps_still_overridable():
    s = strat_mod.LiveTradingStrategy(market_filter={}, mode="paper",
                                      max_order_exposure=50.0)
    assert s.max_order_exposure == 50.0


# ===========================================================================
# MEDIUM — LiveRateControl non rate-limita le chiusure (reduces_liability)
# ===========================================================================
def test_rate_control_skips_reduces_liability(monkeypatch):
    import Betfair.stream.trading.controls as ctl
    monkeypatch.setattr(ctl, "_max_orders_per_min", lambda: 1)
    from flumine.order.orderpackage import OrderPackageType

    control = LiveRateControl.__new__(LiveRateControl)
    ctl.reset_rate_window()  # §7.2: finestra condivisa a livello modulo
    control.flumine = None

    def _on_error(order, msg):  # come BaseControl: registra la violazione
        raise RuntimeError(f"violation: {msg}")

    control._on_error = _on_error

    opening = SimpleNamespace(context={}, side="BACK",
                              order_type=SimpleNamespace(size=5.0, price=2.0))
    closing = SimpleNamespace(context={"reduces_liability": True}, side="LAY",
                              order_type=SimpleNamespace(size=0.75, price=2.0))

    control._validate(opening, OrderPackageType.PLACE)  # 1° place: passa e riempie la finestra
    control._validate(closing, OrderPackageType.PLACE)  # chiusura: DEVE passare (skip)
    with pytest.raises(RuntimeError):
        control._validate(opening, OrderPackageType.PLACE)  # 2ª apertura: rifiutata


# ===========================================================================
# HIGH-4 — specchio: riconciliazione per bet_id dopo riavvio
# ===========================================================================
def test_mirror_reconciles_fallback_ref_by_bet_id():
    """Ordine post-riavvio (ref flumine hash-uuid, non awlq): se il bet_id è già nello
    specchio, la riga riusa il client_order_ref originale → nessuna riga duplicata."""
    s = strat_mod.LiveTradingStrategy(market_filter={}, mode="paper")

    class _DB:
        def __init__(self):
            self.rows: List[Dict[str, Any]] = []

        def find_live_order_ref(self, mode: str, bet_id: str) -> Optional[str]:
            assert mode == "paper" and bet_id == "B77"
            return "awlq42"

    db = _DB()
    row = {"client_order_ref": "a1b2c3-uuid", "bet_id": "B77", "request_id": None}
    out = s._reconcile_ref_by_bet(db, row)
    assert out["client_order_ref"] == "awlq42"
    assert out["request_id"] == 42
    # cache: seconda chiamata senza toccare il DB
    db.find_live_order_ref = None  # rompe il metodo: se richiamato → TypeError
    out2 = s._reconcile_ref_by_bet(db, dict(row))
    assert out2["client_order_ref"] == "awlq42"


def test_mirror_keeps_own_ref_untouched():
    s = strat_mod.LiveTradingStrategy(market_filter={}, mode="paper")
    row = {"client_order_ref": "awlq7", "bet_id": "B1", "request_id": 7}
    assert s._reconcile_ref_by_bet(object(), row) is row  # nessun lookup, riga intatta


# ===========================================================================
# HIGH-3 — follow-through delle regole 'triggered'
# ===========================================================================
class _RulesDB:
    """Fake supabase per il risk worker: tabella regole + tabella richieste."""

    def __init__(self, rules: List[Dict[str, Any]], requests: List[Dict[str, Any]]) -> None:
        self.rules = rules
        self.requests = requests
        self.rpc_calls: List[Dict[str, Any]] = []

    def table(self, name: str):
        store = self.rules if name == "betfair_live_risk_rules" else self.requests
        from .test_live_order_worker import _FakeQuery
        return _FakeQuery(store)

    def rpc(self, fn: str, args: Dict[str, Any]):
        self.rpc_calls.append({"fn": fn, "args": args})
        payload = args.get("p") or {}
        new_id = 900 + len(self.rpc_calls)
        self.requests.append({"id": new_id, "status": "pending",
                              "client_ref": payload.get("client_ref")})
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=new_id))


def _triggered_rule(rid: int = 5, req_id: int = 100, **kw: Any) -> Dict[str, Any]:
    base = {
        "id": rid, "status": "triggered", "mode": "paper", "rule_type": "stop_loss",
        "market_id": "1.1", "selection_id": 47999, "handicap": 0,
        "entry_side": "back", "entry_price": 2.0, "params": {},
        "enqueued_request_id": req_id, "enqueued_client_ref": f"risk{rid}s",
        "triggered_at": "2026-07-02T10:00:00+00:00", "result": {}, "error": None,
    }
    base.update(kw)
    return base


@pytest.fixture()
def _alerts(monkeypatch):
    captured: List[tuple] = []
    monkeypatch.setattr(rw, "_alert", lambda lvl, msg: captured.append((lvl, msg)))
    monkeypatch.setattr(rw, "_kill_active", lambda: False)
    return captured


def test_followthrough_request_error_retries_with_new_ref(_alerts):
    rules = [_triggered_rule()]
    requests = [{"id": 100, "status": "error", "error": "market non risolvibile"}]
    sb = _RulesDB(rules, requests)
    fl = _FakeFlumine({})

    rw._check_triggered_rules(sb, fl, "paper")

    rule = rules[0]
    assert rule["status"] == "triggered"  # resta viva: sta ritentando
    assert rule["enqueued_client_ref"] == "risk5s2"  # ref NUOVO (il vecchio è bruciato)
    assert rule["result"]["close_retries"] == 1
    assert sb.rpc_calls and sb.rpc_calls[0]["args"]["p"]["action"] == "greenup"
    assert any(lvl == "WARN" for lvl, _ in _alerts)


def test_followthrough_retries_exhausted_escalates(_alerts):
    rules = [_triggered_rule(result={"close_retries": 2})]
    requests = [{"id": 100, "status": "error", "error": "ancora KO"}]
    sb = _RulesDB(rules, requests)

    rw._check_triggered_rules(sb, _FakeFlumine({}), "paper")

    rule = rules[0]
    assert rule["status"] == "error"
    assert "FALLITA" in (rule["error"] or "")
    assert any(lvl == "CRITICAL" for lvl, _ in _alerts)
    assert sb.rpc_calls == []  # niente nuovi tentativi


def test_followthrough_done_and_filled_marks_rule_done(_alerts):
    rules = [_triggered_rule()]
    requests = [{"id": 100, "status": "done", "error": None}]
    sb = _RulesDB(rules, requests)
    # ordine di chiusura interamente abbinato nel blotter
    market = _FakeMarket("1.1")
    hedge = _fake_order(bet_id="H1", market_id="1.1", size_remaining=0.0,
                        cust_ref="awlq100")
    market.blotter.add(hedge)
    fl = _FakeFlumine({"1.1": market})

    rw._check_triggered_rules(sb, fl, "paper")

    assert rules[0]["status"] == "done"


def test_followthrough_unmatched_hedge_alerts_critical(_alerts):
    rules = [_triggered_rule()]  # triggered_at nel passato → età > soglia
    requests = [{"id": 100, "status": "done", "error": None}]
    sb = _RulesDB(rules, requests)
    market = _FakeMarket("1.1")
    hedge = _fake_order(bet_id="H1", market_id="1.1", size_remaining=3.0,
                        cust_ref="awlq100")
    market.blotter.add(hedge)
    fl = _FakeFlumine({"1.1": market})

    rw._check_triggered_rules(sb, fl, "paper")

    rule = rules[0]
    assert rule["status"] == "triggered"  # non chiusa: c'è resting scoperto
    assert rule["result"].get("fill_alerted") is True
    assert any(lvl == "CRITICAL" and "NON" in msg for lvl, msg in _alerts)


def test_followthrough_pending_request_waits(_alerts):
    rules = [_triggered_rule()]
    requests = [{"id": 100, "status": "pending", "error": None}]
    sb = _RulesDB(rules, requests)

    rw._check_triggered_rules(sb, _FakeFlumine({}), "paper")

    assert rules[0]["status"] == "triggered"
    assert sb.rpc_calls == []
    assert _alerts == []


# ===========================================================================
# Cert PAPER 2026-07-02 — book LIVE con livelli a DICT + no-op greenup dichiarato
# ===========================================================================
def _dict_book_market(market_id="1.1", sel=47999, bb=1.39, bl=1.41):
    """Market con market_book in forma STREAM LIVE: livelli ex come dict
    {'price':…,'size':…} (betfairlightweight), NON oggetti PriceSize."""
    m = _FakeMarket(market_id)
    m.market_book = SimpleNamespace(inplay=True, runners=[SimpleNamespace(
        selection_id=sel, handicap=0.0, last_price_traded=bb,
        ex=SimpleNamespace(
            available_to_back=[{"price": bb, "size": 120.0}],
            available_to_lay=[{"price": bl, "size": 80.0}],
        ),
    )])
    return m


def test_best_prices_reads_dict_shaped_levels():
    """Fix cert: con i dict dello stream live i best DEVONO essere letti (prima: None)."""
    m = _dict_book_market()
    bb, bl = wk._best_prices(m, 47999, 0.0)
    assert bb == 1.39 and bl == 1.41


def test_best_prices_still_reads_object_levels():
    m = _FakeMarket("1.1")
    m.market_book = SimpleNamespace(runners=[SimpleNamespace(
        selection_id=47999, handicap=0.0,
        ex=SimpleNamespace(
            available_to_back=[SimpleNamespace(price=2.5, size=10)],
            available_to_lay=[SimpleNamespace(price=2.52, size=10)],
        ),
    )])
    assert wk._best_prices(m, 47999, 0.0) == (2.5, 2.52)


class _ExposedBlotter:
    """Blotter con esposizione APERTA (W>L) per i path greenup/cashout."""

    def get_exposures(self, strategy, lookup):
        return {"matched_profit_if_win": 5.0, "matched_profit_if_lose": -2.0}

    def selection_exposure(self, strategy, lookup):
        return 2.0


def test_greenup_dict_book_places_hedge():
    """E2E worker: esposizione aperta + book a dict → hedge LAY piazzato (non più no-op)."""
    m = _dict_book_market()
    m.blotter = _ExposedBlotter()
    fl = _FakeFlumine({"1.1": m})
    sb = _FakeSupabase([_row(1, action="greenup", side=None, price=None, size=None,
                             params={"fraction": 1.0})])
    wk._process_once(sb, fl, strategy=_STRAT)
    row = _by_id(sb, 1)
    assert row["status"] == "done"
    places = [c for c in m.calls if c[0] == "place_order"]
    assert len(places) == 1  # hedge davvero piazzato
    assert (row["result"] or {}).get("side") == "lay"


def test_greenup_open_exposure_without_prices_is_error_not_done():
    """Fix cert: esposizione APERTA + prezzi assenti → riga ERROR (mai 'done ok=True'
    che consumerebbe lo stop lasciando la posizione aperta)."""
    m = _FakeMarket("1.1")
    m.market_book = SimpleNamespace(runners=[SimpleNamespace(
        selection_id=47999, handicap=0.0,
        ex=SimpleNamespace(available_to_back=[], available_to_lay=[]),
    )])
    m.blotter = _ExposedBlotter()
    fl = _FakeFlumine({"1.1": m})
    sb = _FakeSupabase([_row(1, action="greenup", side=None, price=None, size=None,
                             params={"fraction": 1.0})])
    wk._process_once(sb, fl, strategy=_STRAT)
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "NON eseguibile" in (row["error"] or "")
    assert m.calls == []


def test_greenup_flat_position_still_noop_done():
    """Posizione GIÀ piatta senza prezzi → vero no-op: done, nessun ordine."""
    class _FlatBlotter:
        def get_exposures(self, strategy, lookup):
            return {"matched_profit_if_win": 0.0, "matched_profit_if_lose": 0.0}

    m = _FakeMarket("1.1")
    m.market_book = SimpleNamespace(runners=[])
    m.blotter = _FlatBlotter()
    fl = _FakeFlumine({"1.1": m})
    sb = _FakeSupabase([_row(1, action="greenup", side=None, price=None, size=None,
                             params={"fraction": 1.0})])
    wk._process_once(sb, fl, strategy=_STRAT)
    row = _by_id(sb, 1)
    assert row["status"] == "done"
    assert m.calls == []


def test_cashout_open_exposure_without_prices_reports_incomplete():
    """Fix cert: cash-out con esposizione aperta ma book vuoto → ERROR 'INCOMPLETO',
    mai 'done, 0 selezioni chiuse' con la posizione ancora a mercato."""
    m = _FakeMarket("1.1")
    m.market_book = SimpleNamespace(runners=[SimpleNamespace(
        selection_id=47999, handicap=0.0,
        ex=SimpleNamespace(available_to_back=[], available_to_lay=[]),
    )])
    m.blotter = _ExposedBlotter()
    fl = _FakeFlumine({"1.1": m})
    sb = _FakeSupabase([_row(1, action="cashout_all", selection_id=None, side=None,
                             price=None, size=None, params={"fraction": 1.0})])
    wk._process_once(sb, fl, strategy=_STRAT)
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "INCOMPLETO" in (row["error"] or "")


# ===========================================================================
# Risk worker — decision.error → disarmo VISIBILE
# ===========================================================================
def test_monitored_rule_invalid_params_disarmed_visibly(_alerts, monkeypatch):
    rule = {
        "id": 9, "status": "armed", "mode": "paper", "rule_type": "stop_loss",
        "market_id": "1.1", "selection_id": 47999, "handicap": 0,
        "entry_side": "back", "entry_price": 2.0,
        "params": {"trigger_ticks": 0.5},  # frazionario → int() → 0 → invalido
        "trail_extreme": None, "result": {"inplay": False}, "error": None,
    }
    rules = [rule]
    sb = _RulesDB(rules, [])
    market = _FakeMarket("1.1")
    market.market_book = SimpleNamespace(inplay=False, runners=[SimpleNamespace(
        selection_id=47999, handicap=0.0, last_price_traded=2.5,
        ex=SimpleNamespace(
            available_to_back=[SimpleNamespace(price=2.5, size=100)],
            available_to_lay=[SimpleNamespace(price=2.52, size=100)],
        ),
    )])
    fl = _FakeFlumine({"1.1": market})

    class _Blot:
        def get_exposures(self, s, lookup):
            return {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0}

    market.blotter = _Blot()

    rw._handle_monitored(sb, fl, rule, "paper", _STRAT)

    assert rules[0]["status"] == "error"
    assert "trigger_ticks" in (rules[0]["error"] or "")
    assert any(lvl == "CRITICAL" and "PROTEZIONE" in msg for lvl, msg in _alerts)
