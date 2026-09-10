"""CASH OUT PROFESSIONALE (10/09) — stake assoluto, pareggio su ogni esito, sotto-minimo.

Nessuna rete, nessun login, nessun ordine reale: Market/blotter/coda sono mock, la
matematica (trading/greenup, trading/hedging) e la macchina submin sono REALI.

Copre:
  A) ``compute_greenup(amount=...)`` — stake ASSOLUTO in EUR (decimale libero), cappato al
     green totale, con esposizioni attese ESATTE anche per la copertura parziale;
  B) ``hedging.plan_equalize`` — cash-out PAREGGIATO: P&L finale UGUALE su OGNI esito
     (2 e 3 runner, gambe miste back/lay, runner senza posizione, overround, prezzo mancante);
  C) worker — ``params.equal`` su cashout_all/cashout_event, ``params.amount`` su greenup;
  D) sotto-minimo place-and-trim SINCRONO (``_place_sub_minimum``) + ripiego delle chiusure.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from flumine import BaseStrategy

import Betfair.stream.live_order_worker as wk
import Betfair.stream.trading.controls as ctl
from Betfair.stream.trading.greenup import compute_greenup
from Betfair.stream.trading.hedging import (
    PositionInput,
    market_payoffs,
    plan_equalize,
)

_STRAT = BaseStrategy(market_filter={}, name="live_trading")


# ===========================================================================
# A — compute_greenup(amount=...)
# ===========================================================================
def test_amount_lay_partial_is_exact():
    # BACK 10 @ 3.00: W=+20, L=-10 -> diff=+30 -> LAY. Green totale = 30/3.05 = 9.84.
    plan = compute_greenup(
        matched_if_win=20.0, matched_if_lose=-10.0,
        best_back_price=3.00, best_lay_price=3.05, amount=4.0,
    )
    assert plan.side == "lay" and plan.size == pytest.approx(4.0)
    # esposizioni ESATTE per la copertura parziale (non una scala della frazione)
    assert plan.expected_if_win == pytest.approx(round(20.0 - 4.0 * 2.05, 2))
    assert plan.expected_if_lose == pytest.approx(-6.0)
    assert "amount" in plan.note


def test_amount_back_branch_and_decimals():
    # LAY aperto: W=-8, L=+4 -> diff<0 -> BACK. amount decimale qualunque.
    plan = compute_greenup(
        matched_if_win=-8.0, matched_if_lose=4.0,
        best_back_price=2.50, best_lay_price=2.60, amount=1.37,
    )
    assert plan.side == "back" and plan.size == pytest.approx(1.37)
    assert plan.expected_if_win == pytest.approx(round(-8.0 + 1.37 * 1.5, 2))
    assert plan.expected_if_lose == pytest.approx(round(4.0 - 1.37, 2))


def test_amount_is_capped_at_full_green_never_reverses():
    plan = compute_greenup(
        matched_if_win=20.0, matched_if_lose=-10.0,
        best_back_price=3.00, best_lay_price=3.05, amount=1000.0,
    )
    full = round(30.0 / 3.05, 2)
    assert plan.size == pytest.approx(full)
    assert "CAPPATO" in plan.note
    # cappato = green TOTALE: i due esiti coincidono (mai una posizione invertita)
    assert plan.expected_if_win == pytest.approx(plan.expected_if_lose, abs=0.02)


def test_amount_wins_over_fraction():
    plan = compute_greenup(
        matched_if_win=20.0, matched_if_lose=-10.0,
        best_back_price=3.00, best_lay_price=3.05, fraction=0.1, amount=5.0,
    )
    assert plan.size == pytest.approx(5.0)   # la frazione e' ignorata


def test_amount_non_valido_non_produce_ordini():
    for bad in (0.0, -3.0, float("nan")):
        plan = compute_greenup(
            matched_if_win=20.0, matched_if_lose=-10.0,
            best_back_price=3.00, best_lay_price=3.05, amount=bad,
        )
        assert plan.actionable is False
        assert "amount" in plan.note


def test_amount_su_posizione_piatta_resta_noop():
    plan = compute_greenup(
        matched_if_win=1.0, matched_if_lose=1.0,
        best_back_price=3.00, best_lay_price=3.05, amount=5.0,
    )
    assert plan.actionable is False


# ===========================================================================
# B — plan_equalize (cash-out PAREGGIATO)
# ===========================================================================
def _payoff_check(positions, plan, tol=0.011):
    """Verifica NUMERICA indipendente: simula ogni esito sommando posizione + gambe."""
    finals = []
    for k, pos_k in enumerate(positions):
        total = float(pos_k.matched_if_win) + sum(
            float(p.matched_if_lose) for j, p in enumerate(positions) if j != k
        )
        for leg in plan.legs:
            if not leg.plan.actionable:
                continue
            size, price = float(leg.plan.size), float(leg.plan.price)
            wins = leg.selection_id == pos_k.selection_id
            if leg.plan.side == "back":
                total += size * (price - 1.0) if wins else -size
            else:
                total += -size * (price - 1.0) if wins else size
        finals.append(round(total, 6))
    assert max(finals) - min(finals) <= tol, finals
    return finals


def test_equalize_two_runners_equal_payoff():
    pos = [
        PositionInput("1.1", 10, 0.0, 20.0, -10.0, 3.00, 3.05),
        PositionInput("1.1", 20, 0.0, 0.0, 0.0, 1.50, 1.52),
    ]
    plan = plan_equalize(pos)
    assert plan.actionable
    finals = _payoff_check(pos, plan)
    # tutte le gambe usano il prezzo del lato giusto
    for leg in plan.legs:
        if leg.plan.actionable:
            src = pos[0] if leg.selection_id == 10 else pos[1]
            want = src.best_back_price if leg.plan.side == "back" else src.best_lay_price
            assert leg.plan.price == pytest.approx(want)
    assert finals[0] == pytest.approx(plan.legs[0].plan.expected_if_win, abs=0.011)


def test_equalize_three_runners_mixed_sides():
    # posizione su due runner con segni opposti -> serve BACK su uno e LAY sull'altro
    pos = [
        PositionInput("1.1", 10, 0.0, 30.0, -12.0, 4.00, 4.10),
        PositionInput("1.1", 20, 0.0, -18.0, 6.00, 3.00, 3.05),
        PositionInput("1.1", 30, 0.0, 0.0, 0.0, 5.00, 5.10),
    ]
    plan = plan_equalize(pos)
    assert plan.actionable
    sides = {leg.selection_id: leg.plan.side for leg in plan.legs if leg.plan.actionable}
    assert set(sides.values()) == {"back", "lay"}   # gambe MISTE
    _payoff_check(pos, plan)


def test_equalize_runner_senza_posizione_riceve_gamba():
    pos = [
        PositionInput("1.1", 10, 0.0, 25.0, -10.0, 3.20, 3.25),
        PositionInput("1.1", 20, 0.0, 0.0, 0.0, 2.00, 2.02),
        PositionInput("1.1", 30, 0.0, 0.0, 0.0, 6.00, 6.20),
    ]
    plan = plan_equalize(pos)
    acted = {leg.selection_id for leg in plan.legs if leg.plan.actionable}
    assert 20 in acted and 30 in acted     # anche i runner "vuoti" partecipano al pareggio
    _payoff_check(pos, plan)


def test_equalize_con_overround_realistico():
    # book con overround (somma 1/p > 1) su 3 esiti, posizione su uno solo
    pos = [
        PositionInput("1.1", 10, 0.0, 40.0, -20.0, 2.40, 2.44),
        PositionInput("1.1", 20, 0.0, 0.0, 0.0, 3.20, 3.30),
        PositionInput("1.1", 30, 0.0, 0.0, 0.0, 3.30, 3.40),
    ]
    over = sum(1.0 / p.best_back_price for p in pos)
    assert over > 1.0
    plan = plan_equalize(pos)
    finals = _payoff_check(pos, plan)
    # il pareggio esiste ed e' compreso tra il peggior e il miglior esito iniziale
    p0 = market_payoffs(pos)
    assert min(p0) <= finals[0] <= max(p0)


def test_equalize_prezzo_mancante_rifiuta_tutto():
    pos = [
        PositionInput("1.1", 10, 0.0, 20.0, -10.0, None, None),
        PositionInput("1.1", 20, 0.0, 0.0, 0.0, 2.00, 2.02),
    ]
    plan = plan_equalize(pos)
    assert plan.actionable is False
    assert all(not leg.plan.actionable for leg in plan.legs)
    assert "prezzo mancante" in plan.note


def test_equalize_fraction_scala_le_size():
    pos = [
        PositionInput("1.1", 10, 0.0, 20.0, -10.0, 3.00, 3.05),
        PositionInput("1.1", 20, 0.0, 0.0, 0.0, 1.50, 1.52),
    ]
    full = plan_equalize(pos)
    half = plan_equalize(pos, fraction=0.5)
    for a, b in zip(full.legs, half.legs):
        if a.plan.actionable:
            assert b.plan.size == pytest.approx(round(a.plan.size / 2, 2), abs=0.011)
            assert b.plan.side == a.plan.side


def test_equalize_amount_e_budget_totale_cappato():
    pos = [
        PositionInput("1.1", 10, 0.0, 20.0, -10.0, 3.00, 3.05),
        PositionInput("1.1", 20, 0.0, 0.0, 0.0, 1.50, 1.52),
    ]
    full = plan_equalize(pos)
    total = sum(leg.plan.size for leg in full.legs if leg.plan.actionable)
    small = plan_equalize(pos, amount=total / 4.0)
    spent = sum(leg.plan.size for leg in small.legs if leg.plan.actionable)
    assert spent == pytest.approx(total / 4.0, abs=0.03)
    capped = plan_equalize(pos, amount=total * 10)
    spent_cap = sum(leg.plan.size for leg in capped.legs if leg.plan.actionable)
    assert spent_cap == pytest.approx(total, abs=0.02)
    assert "CAPPATO" in capped.note


def test_equalize_mercati_diversi_e_un_errore_di_contratto():
    pos = [
        PositionInput("1.1", 10, 0.0, 20.0, -10.0, 3.00, 3.05),
        PositionInput("1.2", 20, 0.0, 0.0, 0.0, 1.50, 1.52),
    ]
    with pytest.raises(ValueError, match="UN SOLO mercato"):
        plan_equalize(pos)


def test_market_payoffs_somma_gli_altri_perdenti():
    pos = [
        PositionInput("1.1", 10, 0.0, 20.0, -10.0, 3.0, 3.05),
        PositionInput("1.1", 20, 0.0, -5.0, 2.0, 2.0, 2.02),
    ]
    p = market_payoffs(pos)
    assert p[0] == pytest.approx(20.0 + 2.0)
    assert p[1] == pytest.approx(-5.0 - 10.0)


def test_equalize_mercato_gia_pareggiato_non_ordina():
    # payoff identici su ogni esito -> nessuna gamba necessaria
    pos = [
        PositionInput("1.1", 10, 0.0, 5.0, 5.0, 3.0, 3.05),
        PositionInput("1.1", 20, 0.0, 5.0, 5.0, 2.0, 2.02),
    ]
    plan = plan_equalize(pos)
    assert plan.actionable is False


# ===========================================================================
# C — worker: params.equal / params.amount
# ===========================================================================
class _Query:
    def __init__(self, store: List[Dict[str, Any]]) -> None:
        self._store = store
        self._payload: Dict[str, Any] = {}
        self._filters: List[tuple] = []
        self._op = None

    def update(self, payload):
        self._op = "update"
        self._payload = dict(payload)
        return self

    def select(self, *_a):
        self._op = "select"
        return self

    def eq(self, k, v):
        self._filters.append((k, v))
        return self

    def execute(self):
        rows = [r for r in self._store if all(r.get(k) == v for k, v in self._filters)]
        if self._op == "update":
            for r in rows:
                r.update(self._payload)
        return SimpleNamespace(data=[dict(r) for r in rows])


class _Sb:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _n):
        return _Query(self.rows)


def _runner(sel, bb, bl):
    ex = SimpleNamespace(
        available_to_back=[SimpleNamespace(price=bb, size=500.0)],
        available_to_lay=[SimpleNamespace(price=bl, size=500.0)],
    )
    return SimpleNamespace(selection_id=sel, handicap=0.0, last_price_traded=bb, ex=ex)


class _Market:
    def __init__(self, market_id, runners=None, exposures=None, place_ok=True):
        self.market_id = market_id
        self.event_id = None
        self.placed: List[Any] = []
        self.cancelled: List[Any] = []
        self.market_book = SimpleNamespace(runners=runners or [])
        self._exp = exposures or {}
        self.blotter = self
        self._place_ok = place_ok

    def place_order(self, order, customer_strategy_ref=None):
        self.placed.append(order)
        return self._place_ok

    def cancel_order(self, order, size_reduction=None):
        self.cancelled.append((order, size_reduction))
        return True

    def get_exposures(self, _strat, lookup):
        return self._exp.get(lookup[1], {"matched_profit_if_win": 0.0, "matched_profit_if_lose": 0.0})

    def selection_exposure(self, _strat, _lookup):
        return 0.0

    def strategy_orders(self, _strat):
        return []


class _Markets:
    def __init__(self, m):
        self.markets = m

    def __iter__(self):
        return iter(self.markets.values())


def _fl(market):
    return SimpleNamespace(markets=_Markets({market.market_id: market}))


@pytest.fixture(autouse=True)
def _clean_state():
    wk._SETTINGS.clear()
    ctl.reset_rate_window()
    yield
    wk._SETTINGS.clear()
    ctl.reset_rate_window()


def _market_2runner():
    return _Market(
        "1.1",
        runners=[_runner(10, 3.00, 3.05), _runner(20, 1.50, 1.52)],
        exposures={10: {"matched_profit_if_win": 20.0, "matched_profit_if_lose": -10.0}},
    )


def test_cashout_all_equal_piazza_una_gamba_per_runner():
    market = _market_2runner()
    row = {"id": 101, "market_id": "1.1", "handicap": 0, "action": "cashout_all",
           "params": {"equal": True}}
    sb = _Sb([row])
    wk._do_cashout_all(sb, _fl(market), row, "paper", _STRAT)
    assert row["status"] == "done"
    legs = row["result"]["legs"]
    assert {leg["selection_id"] for leg in legs} == {10, 20}
    assert "PAREGGIATO" in row["result"]["detail"]
    # ref per gamba: awlq<rid>x<idx>
    assert legs[0]["ref"].startswith("awlq101x")


def test_cashout_all_default_resta_flatten_indipendente():
    market = _market_2runner()
    row = {"id": 102, "market_id": "1.1", "handicap": 0, "action": "cashout_all", "params": {}}
    wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", _STRAT)
    legs = row["result"]["legs"]
    # senza params.equal si chiude SOLO la selezione con esposizione aperta
    assert [leg["selection_id"] for leg in legs] == [10]


def test_cashout_all_equal_senza_prezzo_fallisce_forte():
    market = _Market(
        "1.1",
        runners=[
            SimpleNamespace(selection_id=10, handicap=0.0, last_price_traded=None,
                            ex=SimpleNamespace(available_to_back=[], available_to_lay=[])),
            _runner(20, 1.50, 1.52),
        ],
        exposures={10: {"matched_profit_if_win": 20.0, "matched_profit_if_lose": -10.0}},
    )
    row = {"id": 103, "market_id": "1.1", "handicap": 0, "action": "cashout_all",
           "params": {"equal": True}}
    with pytest.raises(ValueError, match="INCOMPLETO"):
        wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert market.placed == []          # mai un pareggio a meta'


def test_cashout_event_equal_propaga_il_flag():
    m1 = _market_2runner()
    m1.event_id = "ev1"
    row = {"id": 104, "market_id": "1.1", "handicap": 0, "action": "cashout_event",
           "params": {"equal": True}}
    fl = SimpleNamespace(markets=_Markets({"1.1": m1}))
    wk._do_cashout_event(_Sb([row]), fl, row, "paper", _STRAT)
    assert row["status"] == "done"
    assert len(row["result"]["legs"]) == 2
    assert "PAREGGIATO" in row["result"]["detail"]


def test_greenup_amount_limita_lo_stake():
    market = _market_2runner()
    row = {"id": 105, "market_id": "1.1", "selection_id": 10, "handicap": 0,
           "action": "greenup", "params": {"amount": 4.0}}
    wk._do_greenup(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert row["status"] == "done"
    assert row["result"]["size"] == pytest.approx(4.0)
    assert row["result"]["side"] == "lay"


def test_greenup_amount_malformato_e_errore_esplicito():
    market = _market_2runner()
    row = {"id": 106, "market_id": "1.1", "selection_id": 10, "handicap": 0,
           "action": "greenup", "params": {"amount": 0}}
    with pytest.raises(ValueError, match="amount"):
        wk._do_greenup(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert market.placed == []


# ===========================================================================
# D — sotto-minimo (place-and-trim) SINCRONO
# ===========================================================================
class _SubOrder(SimpleNamespace):
    pass


def _sub_order():
    return _SubOrder(
        id="OID-1", bet_id=None, status="EXECUTABLE", size_matched=0.0,
        size_remaining=0.0, side="back",
        order_type=SimpleNamespace(price=None, size=None),
    )


class _SubOps:
    """SubminOps mock che MUTA l'ordine come farebbe l'exchange (place/cancel/replace)."""

    def __init__(self, order, trim=True):
        self.order = order
        self.calls: List[tuple] = []
        self.last_order: Any = None
        self._trim = trim

    def place(self, market, *, side, price, size, customer_order_ref):  # noqa: ARG002
        self.calls.append(("place", price, size))
        self.order.order_type.price = price
        self.order.order_type.size = size
        self.order.size_remaining = size
        self.order.bet_id = "BET-1"
        self.last_order = self.order
        return self.order

    def cancel(self, market, order, size_reduction):  # noqa: ARG002
        self.calls.append(("cancel", size_reduction))
        if not self._trim:
            return
        if size_reduction is None:
            order.size_remaining = 0.0
        else:
            order.size_remaining = round(order.size_remaining - float(size_reduction), 2)

    def replace(self, market, order, new_price):  # noqa: ARG002
        self.calls.append(("replace", new_price))
        order.order_type.price = new_price

    def names(self):
        return [c[0] for c in self.calls]


def test_place_sub_minimum_sequenza_completa():
    market = _Market("1.1")
    order = _sub_order()
    ops = _SubOps(order)
    state, got = wk._place_sub_minimum(
        None, market, market_id="1.1", strategy=_STRAT, selection_id=10, handicap=0.0,
        side="back", price=3.00, size=1.20, cust_ref="awlq1x0", what="test",
        ops=ops, find_order=lambda _oid, _bid: order, sleep=lambda *_a: None,
        timeout_sec=5.0,
    )
    assert ops.names() == ["place", "cancel", "replace"]
    assert ops.calls[0][1] == 1000.0 and ops.calls[0][2] == pytest.approx(2.00)  # park BACK
    assert ops.calls[1][1] == pytest.approx(0.80)                                # 2.00 - 1.20
    assert ops.calls[2][1] == pytest.approx(3.00)                                # quota target
    assert state.step.value == "done"
    assert state.target_size == pytest.approx(1.20)
    assert got is order


def test_place_sub_minimum_lato_lay_parcheggia_a_1_01():
    market = _Market("1.1")
    order = _sub_order()
    order.side = "lay"
    ops = _SubOps(order)
    wk._place_sub_minimum(
        None, market, market_id="1.1", strategy=_STRAT, selection_id=10, handicap=0.0,
        side="lay", price=2.50, size=0.30, cust_ref="awlq2x0", what="test",
        ops=ops, find_order=lambda _oid, _bid: order, sleep=lambda *_a: None,
        timeout_sec=5.0,
    )
    assert ops.calls[0][1] == pytest.approx(1.01)
    assert ops.calls[0][2] == pytest.approx(0.50)      # minimo LAY .it
    assert ops.calls[1][1] == pytest.approx(0.20)


def test_place_sub_minimum_abort_ritira_il_residuo_e_alza():
    market = _Market("1.1")
    order = _sub_order()
    ops = _SubOps(order)

    def _matched(_oid, _bid):
        order.size_matched = 2.0       # abbinato alla quota NON abbinabile = anomalia
        return order

    with pytest.raises(ValueError, match="sotto-minimo NON piazzato"):
        wk._place_sub_minimum(
            None, market, market_id="1.1", strategy=_STRAT, selection_id=10, handicap=0.0,
            side="back", price=3.00, size=1.20, cust_ref="awlq3x0", what="test",
            ops=ops, find_order=_matched, sleep=lambda *_a: None, timeout_sec=5.0,
        )
    assert "replace" not in ops.names()          # MAI un replace dopo l'abort
    assert market.cancelled                      # residuo ritirato


def test_place_sub_minimum_timeout_ritira_e_alza():
    market = _Market("1.1")
    order = _sub_order()
    ops = _SubOps(order)
    with pytest.raises(ValueError, match="timeout"):
        wk._place_sub_minimum(
            None, market, market_id="1.1", strategy=_STRAT, selection_id=10, handicap=0.0,
            side="back", price=3.00, size=1.20, cust_ref="awlq4x0", what="test",
            ops=ops, find_order=lambda _o, _b: order, sleep=lambda *_a: None,
            timeout_sec=0.0,
        )
    assert ops.names() == ["place"]
    assert market.cancelled


def test_closing_leg_ripiega_sul_submin_solo_in_live(monkeypatch):
    calls: List[Dict[str, Any]] = []

    def _fake_submin(*_a, **kw):
        calls.append(kw)
        return SimpleNamespace(step=SimpleNamespace(value="done")), None

    monkeypatch.setattr(wk, "_place_sub_minimum", _fake_submin)
    market = _Market("1.1", place_ok=False)          # i control rifiutano il place diretto
    order = SimpleNamespace(violation_msg="size sotto il minimo")
    wk._place_closing_leg(
        None, market, order=order, strategy=_STRAT, market_id="1.1", selection_id=10,
        handicap=0.0, side="lay", price=2.5, size=0.30, cust_ref="awlq5x0",
        what="greenup", mode="live", params={},
    )
    assert len(calls) == 1 and calls[0]["size"] == pytest.approx(0.30)


def test_closing_leg_in_paper_non_usa_il_trucco(monkeypatch):
    monkeypatch.setattr(wk, "_place_sub_minimum",
                        lambda *_a, **_k: pytest.fail("mai in PAPER"))
    market = _Market("1.1", place_ok=False)
    order = SimpleNamespace(violation_msg="rifiutato")
    with pytest.raises(ValueError):
        wk._place_closing_leg(
            None, market, order=order, strategy=_STRAT, market_id="1.1", selection_id=10,
            handicap=0.0, side="lay", price=2.5, size=0.30, cust_ref="awlq6x0",
            what="greenup", mode="paper", params={},
        )


def test_closing_leg_opt_out_esplicito(monkeypatch):
    monkeypatch.setattr(wk, "_place_sub_minimum",
                        lambda *_a, **_k: pytest.fail("allow_sub_minimum=False"))
    market = _Market("1.1", place_ok=False)
    order = SimpleNamespace(violation_msg="rifiutato")
    with pytest.raises(ValueError):
        wk._place_closing_leg(
            None, market, order=order, strategy=_STRAT, market_id="1.1", selection_id=10,
            handicap=0.0, side="lay", price=2.5, size=0.30, cust_ref="awlq7x0",
            what="greenup", mode="live", params={"allow_sub_minimum": False},
        )


def test_closing_leg_sopra_il_minimo_propaga_il_rifiuto(monkeypatch):
    monkeypatch.setattr(wk, "_place_sub_minimum",
                        lambda *_a, **_k: pytest.fail("size sopra il minimo"))
    market = _Market("1.1", place_ok=False)
    order = SimpleNamespace(violation_msg="rate limit")
    with pytest.raises(ValueError):
        wk._place_closing_leg(
            None, market, order=order, strategy=_STRAT, market_id="1.1", selection_id=10,
            handicap=0.0, side="back", price=2.5, size=5.0, cust_ref="awlq8x0",
            what="greenup", mode="live", params={},
        )


def test_do_place_sotto_minimo_richiede_opt_in(monkeypatch):
    """APERTURA: senza params.allow_sub_minimum il place sotto-minimo resta RIFIUTATO."""
    monkeypatch.setattr(wk, "_place_sub_minimum",
                        lambda *_a, **_k: pytest.fail("opt-in mancante"))
    market = _Market("1.1", runners=[_runner(10, 3.0, 3.05)])
    row = {"id": 201, "market_id": "1.1", "selection_id": 10, "handicap": 0,
           "side": "back", "order_type": "LIMIT", "price": 3.0, "size": 1.0,
           "action": "place", "params": {}}
    with pytest.raises(ValueError):
        wk._do_place(_Sb([row]), _fl(market), row, "live", _STRAT)


def test_do_place_ignora_allow_sub_minimum_e_applica_il_minimo_normale(monkeypatch):
    """ALIGN-7: il place SEMPLICE non conosce piu' ``params.allow_sub_minimum`` (la RPC
    lo RIFIUTA: le aperture sotto-minimo passano SOLO dall'azione ``place_submin``).
    Il worker e' coerente: flag ignorato (log) + comportamento min-stake NORMALE."""
    monkeypatch.setattr(wk, "_place_sub_minimum",
                        lambda *_a, **_k: pytest.fail("mai il place-and-trim dal place semplice"))
    market = _Market("1.1", runners=[_runner(10, 3.0, 3.05)])
    row = {"id": 202, "market_id": "1.1", "selection_id": 10, "handicap": 0,
           "side": "back", "order_type": "LIMIT", "price": 3.0, "size": 1.0,
           "action": "place", "params": {"allow_sub_minimum": True}}
    sb = _Sb([row])
    with pytest.raises(ValueError):     # build_order rifiuta il sotto-minimo .it
        wk._do_place(sb, _fl(market), row, "live", _STRAT)
    assert market.placed == []
    assert not hasattr(wk, "_do_place_sub_minimum")   # ramo rimosso: niente vie laterali


def test_do_place_in_paper_ignora_il_trucco(monkeypatch):
    """In PAPER come in LIVE: ``allow_sub_minimum`` sul place semplice e' IGNORATO e il
    minimo di giurisdizione si applica normalmente (build_order rifiuta)."""
    monkeypatch.setattr(wk, "_place_sub_minimum",
                        lambda *_a, **_k: pytest.fail("mai in PAPER"))
    market = _Market("1.1", runners=[_runner(10, 3.0, 3.05)])
    row = {"id": 203, "market_id": "1.1", "selection_id": 10, "handicap": 0,
           "side": "back", "order_type": "LIMIT", "price": 3.0, "size": 1.0,
           "action": "place", "params": {"allow_sub_minimum": True}}
    with pytest.raises(ValueError):     # build_order rifiuta il sotto-minimo .it
        wk._do_place(_Sb([row]), _fl(market), row, "paper", _STRAT)


# ===========================================================================
# E — review 10/09 (sera): gambe di APERTURA nel pareggio, amount su cashout_all/event,
#     follow-through pareggiato, non-convergenza, amount infinito, rate guard submin.
# ===========================================================================
import Betfair.stream.trading.hedging as hedging
from Betfair.stream.tests import test_cashout_complete_ft as ftt


def _market_small():
    """Posizione piccola: la gamba di pareggio sul runner PIATTO (BACK 0.66@1.50) e'
    SOTTO il minimo di apertura .it (2.00) mentre la chiusura (LAY 0.66) e' legale."""
    return _Market(
        "1.1",
        runners=[_runner(10, 3.00, 3.05), _runner(20, 1.50, 1.52)],
        exposures={10: {"matched_profit_if_win": 2.0, "matched_profit_if_lose": -1.0}},
    )


def _row_eq(rid, **extra):
    return {"id": rid, "market_id": "1.1", "handicap": 0, "action": "cashout_all",
            "params": {"equal": True, **extra}}


@pytest.fixture()
def alerts_sink(monkeypatch):
    sink: List[str] = []
    import Betfair.stream.db as dbmod

    monkeypatch.setattr(
        dbmod, "insert_alert",
        lambda level, code, msg, event_id=None: sink.append(f"{level}:{code}:{msg}"),
    )
    return sink


# --- CRITICAL-1: la gamba su un runner senza esposizione e' un'APERTURA -----------------
def test_equalize_gamba_su_runner_piatto_e_apertura_non_chiusura():
    market = _market_2runner()
    row = _row_eq(301)
    wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", _STRAT)
    legs = {leg["selection_id"]: leg for leg in row["result"]["legs"]}
    # chiusura (sel 10, esposizione aperta): size libera al centesimo (reduces_liability)
    assert legs[10]["size"] == pytest.approx(6.60) and not legs[10].get("opening")
    # APERTURA (sel 20, runner piatto): min-stake NORMALE .it -> BACK legalizzato allo
    # step 0.50 (6.58 -> 6.50): la prova che NON e' passata da reduces_liability=True
    assert legs[20]["opening"] is True
    assert legs[20]["size"] == pytest.approx(6.50)
    assert row["result"]["equal"] is True and row["result"]["partial"] is False


def test_equalize_apertura_sotto_minimo_saltata_mai_submin_piano_parziale(monkeypatch):
    monkeypatch.setattr(wk, "_place_sub_minimum",
                        lambda *_a, **_k: pytest.fail("MAI place-and-trim su un'apertura"))
    market = _market_small()
    row = _row_eq(302)
    wk._do_cashout_all(_Sb([row]), _fl(market), row, "live", _STRAT)
    assert row["status"] == "done"
    assert [leg["selection_id"] for leg in row["result"]["legs"]] == [10]   # solo la chiusura
    skipped = row["result"]["skipped"]
    assert len(skipped) == 1 and skipped[0]["selection_id"] == 20
    assert skipped[0]["size"] == pytest.approx(0.66) and "minimo" in skipped[0]["note"]
    assert row["result"]["partial"] is True and row["result"]["equal"] is False
    assert "PARZIALE" in row["result"]["detail"]
    assert len(market.placed) == 1


def test_equalize_apertura_passa_dal_rate_guard():
    wk._SETTINGS["max_orders_per_min"] = 1
    ctl.record_place()                       # finestra gia' piena
    market = _market_2runner()
    row = _row_eq(303)
    with pytest.raises(ValueError, match="rate-limit"):
        wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", _STRAT)
    # la CHIUSURA (riduce liability) e' passata, l'APERTURA e' stata fermata dalla guardia
    assert len(market.placed) == 1


def test_equalize_apertura_passa_dall_exposure_guard():
    wk._SETTINGS["max_exposure_per_selection"] = 1.0
    market = _market_2runner()
    row = _row_eq(304)
    with pytest.raises(ValueError, match="esposizione"):
        wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", _STRAT)
    assert len(market.placed) == 1


# --- HIGH-2: params.amount su cashout_all / cashout_event -------------------------------
def test_cashout_all_amount_non_equal_limita_lo_stake():
    market = _market_2runner()
    row = {"id": 311, "market_id": "1.1", "handicap": 0, "action": "cashout_all",
           "params": {"amount": 3.0}}
    wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", _STRAT)
    legs = row["result"]["legs"]
    assert len(legs) == 1 and legs[0]["size"] == pytest.approx(3.0)


def test_cashout_all_amount_non_equal_budget_ripartito_proporzionalmente():
    # due selezioni aperte: green totale 9.84 (sel 10) e 20/1.52=13.16 (sel 20)
    market = _Market(
        "1.1",
        runners=[_runner(10, 3.00, 3.05), _runner(20, 1.50, 1.52)],
        exposures={10: {"matched_profit_if_win": 20.0, "matched_profit_if_lose": -10.0},
                   20: {"matched_profit_if_win": 15.0, "matched_profit_if_lose": -5.0}},
    )
    row = {"id": 312, "market_id": "1.1", "handicap": 0, "action": "cashout_all",
           "params": {"amount": 4.6}}
    wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", _STRAT)
    legs = {leg["selection_id"]: leg["size"] for leg in row["result"]["legs"]}
    full10, full20 = round(30 / 3.05, 2), round(20 / 1.52, 2)
    scale = 4.6 / (full10 + full20)
    assert legs[10] == pytest.approx(round(full10 * scale, 2), abs=0.011)
    assert legs[20] == pytest.approx(round(full20 * scale, 2), abs=0.011)
    assert sum(legs.values()) == pytest.approx(4.6, abs=0.02)


def test_cashout_all_amount_equal_e_il_budget_di_plan_equalize():
    market = _market_2runner()
    row = _row_eq(313, amount=6.59)           # meta' del totale 6.60 + 6.58
    wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", _STRAT)
    legs = {leg["selection_id"]: leg["size"] for leg in row["result"]["legs"]}
    assert legs[10] == pytest.approx(3.30, abs=0.011)
    assert legs[20] <= 3.29 + 1e-9            # apertura: legalizzata allo step .it


def test_cashout_all_amount_malformato_e_errore_esplicito():
    for bad in (-1.0, 0, "abc", float("inf")):
        market = _market_2runner()
        row = {"id": 314, "market_id": "1.1", "handicap": 0, "action": "cashout_all",
               "params": {"amount": bad}}
        with pytest.raises(ValueError, match="amount"):
            wk._do_cashout_all(_Sb([row]), _fl(market), row, "paper", _STRAT)
        assert market.placed == []


def test_cashout_event_amount_propagato():
    m1 = _market_2runner()
    m1.event_id = "ev1"
    row = {"id": 315, "market_id": "1.1", "handicap": 0, "action": "cashout_event",
           "params": {"amount": 3.0}}
    fl = SimpleNamespace(markets=_Markets({"1.1": m1}))
    wk._do_cashout_event(_Sb([row]), fl, row, "paper", _STRAT)
    assert row["result"]["legs"][0]["size"] == pytest.approx(3.0)
    m2 = _market_2runner()
    m2.event_id = "ev1"
    row2 = {"id": 316, "market_id": "1.1", "handicap": 0, "action": "cashout_event",
            "params": {"amount": "nan"}}
    with pytest.raises(ValueError, match="amount"):
        wk._do_cashout_event(_Sb([row2]), SimpleNamespace(markets=_Markets({"1.1": m2})),
                             row2, "paper", _STRAT)
    assert m2.placed == []


# --- HIGH-3: follow-through di un cash-out PAREGGIATO = nuovo cashout di MERCATO ---------
def test_ft_rehedge_equal_riaccoda_cashout_di_mercato_una_volta_per_mercato(alerts_sink):
    orders = [ftt._order("H1", 10, "EXECUTABLE", 3.0, ref="awlq42x0"),
              ftt._order("H2", 20, "EXECUTABLE", 2.0, ref="awlq42x1")]
    m = ftt._Market(orders=orders)
    row = ftt._done_row(
        rid=42, action="cashout_all",
        params={"equal": True, "fraction": 0.5, "amount": 6.59},
        result={"legs": [
            {"market_id": "1.1", "selection_id": 10, "handicap": 0.0, "ref": "awlq42x0", "bet_id": "H1"},
            {"market_id": "1.1", "selection_id": 20, "handicap": 0.0, "ref": "awlq42x1", "bet_id": "H2"},
        ]},
    )
    sb = ftt._FtSb([row])
    wk._check_manual_followthrough(sb, ftt._flumine(m), "paper")
    # UN SOLO re-cashout per il MERCATO (non un greenup per selezione)
    assert len(sb.enqueued) == 1
    p = sb.enqueued[0]
    assert p["action"] == "cashout_all"
    assert p["market_id"] == "1.1" and p.get("selection_id") is None
    assert p["params"] == {"equal": True, "fraction": 0.5, "amount": 6.59,
                           "ft_parent": 42, "ft_retry": 1}
    assert p["client_ref"] == "ft42m1.1r1"
    legs_state = sb.updates[-1]["result"]["ft"]["legs"]
    assert legs_state["1.1:10"]["handed_off"] is True
    assert legs_state["1.1:20"]["handed_off"] is True
    assert legs_state["1.1:20"]["retry_req"] == legs_state["1.1:10"]["retry_req"]


def test_ft_rehedge_equal_cashout_event_conserva_l_azione(alerts_sink):
    m = ftt._Market(orders=[ftt._order("H1", 10, "EXECUTABLE", 3.0, ref="awlq43x0")])
    row = ftt._done_row(
        rid=43, action="cashout_event", params={"equal": True},
        result={"legs": [{"market_id": "1.1", "selection_id": 10, "handicap": 0.0,
                          "ref": "awlq43x0", "bet_id": "H1"}]},
    )
    sb = ftt._FtSb([row])
    wk._check_manual_followthrough(sb, ftt._flumine(m), "paper")
    assert len(sb.enqueued) == 1
    p = sb.enqueued[0]
    assert p["action"] == "cashout_event" and p["market_id"] == "1.1"
    assert p["params"]["equal"] is True and p["params"]["fraction"] == 1.0
    assert "amount" not in p["params"]


def test_ft_rehedge_cashout_non_equal_resta_greenup_per_selezione(alerts_sink):
    m = ftt._Market(orders=[ftt._order("H1", 10, "EXECUTABLE", 3.0, ref="awlq44x0")])
    row = ftt._done_row(
        rid=44, action="cashout_all", params={},
        result={"legs": [{"market_id": "1.1", "selection_id": 10, "handicap": 0.0,
                          "ref": "awlq44x0", "bet_id": "H1"}]},
    )
    sb = ftt._FtSb([row])
    wk._check_manual_followthrough(sb, ftt._flumine(m), "paper")
    assert len(sb.enqueued) == 1 and sb.enqueued[0]["action"] == "greenup"
    assert sb.enqueued[0]["selection_id"] == 10


# --- MEDIUM-4: lati non convergenti = rifiuto esplicito, MAI un prezzo del lato sbagliato --
def test_eq_solve_non_convergente_rifiuta_tutto(monkeypatch):
    monkeypatch.setattr(hedging, "_EQ_MAX_ITER", 1)     # forza la NON convergenza
    pos = [
        PositionInput("1.1", 10, 0.0, 20.0, -10.0, 3.00, 3.05),
        PositionInput("1.1", 20, 0.0, 0.0, 0.0, 1.50, 1.52),
    ]
    plan = plan_equalize(pos)
    assert plan.actionable is False
    assert all(not leg.plan.actionable for leg in plan.legs)
    assert "equalize_non_convergente" in plan.note
    assert all("equalize_non_convergente" in leg.plan.note for leg in plan.legs)


def test_eq_solve_convergente_usa_il_prezzo_del_lato_giusto():
    pos = [
        PositionInput("1.1", 10, 0.0, 20.0, -10.0, 3.00, 3.05),
        PositionInput("1.1", 20, 0.0, 0.0, 0.0, 1.50, 1.52),
    ]
    xs, prices, _e = hedging._eq_solve(hedging.market_payoffs(pos), pos)
    for x, p, src in zip(xs, prices, pos):
        assert p == (src.best_back_price if x >= 0 else src.best_lay_price)


# --- MEDIUM-5: amount infinito sul greenup ----------------------------------------------
def test_greenup_amount_infinito_e_errore_esplicito():
    for bad in (float("inf"), "inf", "-inf"):
        market = _market_2runner()
        row = {"id": 321, "market_id": "1.1", "selection_id": 10, "handicap": 0,
               "action": "greenup", "params": {"amount": bad}}
        with pytest.raises(ValueError, match="amount"):
            wk._do_greenup(_Sb([row]), _fl(market), row, "paper", _STRAT)
        assert market.placed == []


# --- MEDIUM-6: il ripiego submin della chiusura rispetta il rate guard -------------------
def test_closing_leg_submin_rispetta_il_rate_guard(monkeypatch):
    monkeypatch.setattr(wk, "_place_sub_minimum",
                        lambda *_a, **_k: pytest.fail("rate guard non rispettato"))
    wk._SETTINGS["max_orders_per_min"] = 1
    ctl.record_place()
    market = _Market("1.1", place_ok=False)
    order = SimpleNamespace(violation_msg="size sotto il minimo")
    with pytest.raises(ValueError, match="rate-limit"):
        wk._place_closing_leg(
            None, market, order=order, strategy=_STRAT, market_id="1.1", selection_id=10,
            handicap=0.0, side="lay", price=2.5, size=0.30, cust_ref="awlq9x0",
            what="greenup", mode="live", params={},
        )
