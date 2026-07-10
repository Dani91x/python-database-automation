"""Unit test del risk_engine_worker. NESSUNA rete/ordine reale: coda Supabase, framework
flumine, market_book e blotter sono mock in-memory. La matematica usa risk_engine reale.

Scenari:
  - offset → accoda un 'place' opposto al target + regola 'done';
  - stop_loss che scatta → accoda un 'greenup' (flatten) + regola 'triggered';
  - stop_loss che NON scatta → nessun accodamento, regola resta 'armed';
  - trailing che non scatta → aggiorna trail_extreme;
  - kill-switch attivo → nessun accodamento anche se la condizione è vera;
  - posizione piatta al fire → regola 'done' senza ordine.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.risk_engine_worker as rw

_REAL_KILL = rw.low._kill_switch
_REAL_MODE = rw.low._live_order_mode


# ---------------------------------------------------------------------------
# Fake Supabase (regole + cattura enqueue via rpc)
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: List[Dict[str, Any]]) -> None:
        self._store = store
        self._op: Optional[str] = None
        self._payload: Dict[str, Any] = {}
        self._filters: List[tuple] = []
        self._limit: Optional[int] = None
        self._order: Optional[str] = None

    def select(self, *_a: Any) -> "_Query":
        self._op = "select"
        return self

    def update(self, payload: Dict[str, Any]) -> "_Query":
        self._op = "update"
        self._payload = dict(payload)
        return self

    def eq(self, k: str, v: Any) -> "_Query":
        self._filters.append((k, v))
        return self

    def order(self, k: str, **kw: Any) -> "_Query":
        self._order = k
        self._order_desc = bool(kw.get("desc"))
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def _match(self, row: Dict[str, Any]) -> bool:
        return all(row.get(k) == v for k, v in self._filters)

    def execute(self) -> _Resp:
        rows = [r for r in self._store if self._match(r)]
        if self._order:
            rows.sort(key=lambda r: r.get(self._order))
        if self._op == "select":
            if self._limit is not None:
                rows = rows[: self._limit]
            return _Resp([dict(r) for r in rows])
        for r in rows:
            r.update(self._payload)
        return _Resp([dict(r) for r in rows])


class _FakeSb:
    def __init__(self, rules: List[Dict[str, Any]]) -> None:
        self.rules = rules
        self.enqueued: List[Dict[str, Any]] = []
        self._next_req_id = 1000

    def table(self, _name: str) -> _Query:
        return _Query(self.rules)

    def rpc(self, name: str, args: Dict[str, Any]) -> "_RpcCall":
        assert name == "request_betfair_live_order"
        self.enqueued.append(args["p"])
        self._next_req_id += 1
        return _RpcCall(self._next_req_id)


class _RpcCall:
    def __init__(self, req_id: int) -> None:
        self._req_id = req_id

    def execute(self) -> _Resp:
        return _Resp(self._req_id)


# ---------------------------------------------------------------------------
# Fake flumine (market_book runner + blotter esposizioni)
# ---------------------------------------------------------------------------
def _runner(sel: int, ltp: float, best_back: float, best_lay: float) -> Any:
    ex = SimpleNamespace(
        available_to_back=[SimpleNamespace(price=best_back, size=100.0)],
        available_to_lay=[SimpleNamespace(price=best_lay, size=100.0)],
    )
    return SimpleNamespace(selection_id=sel, handicap=0.0, last_price_traded=ltp, ex=ex)


class _Blotter:
    def __init__(self, w: float, l: float) -> None:
        self._w, self._l = w, l

    def get_exposures(self, _strategy: Any, _lookup: Any) -> Dict[str, float]:
        return {"matched_profit_if_win": self._w, "matched_profit_if_lose": self._l}


def _market(market_id: str, sel: int, ltp: float, bb: float, bl: float, w: float, l: float) -> Any:
    mb = SimpleNamespace(runners=[_runner(sel, ltp, bb, bl)])
    return SimpleNamespace(market_id=market_id, market_book=mb, blotter=_Blotter(w, l))


class _Markets:
    def __init__(self, m: Dict[str, Any]) -> None:
        self.markets = m

    def __iter__(self):
        return iter(self.markets.values())


def _flumine(market: Any) -> Any:
    return SimpleNamespace(markets=_Markets({market.market_id: market}))


@pytest.fixture(autouse=True)
def _force_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rw.low, "_live_order_mode", lambda: "PAPER")
    monkeypatch.setattr(rw.low, "_kill_switch", lambda: False)
    monkeypatch.setattr(rw.low, "_db_kill_switch", lambda: False)
    monkeypatch.setattr(rw, "_alert", lambda *a, **k: None)  # niente tentativi DB per gli alert


def _rule(**kw: Any) -> Dict[str, Any]:
    base = {
        "id": 1, "mode": "paper", "status": "armed", "market_id": "1.1",
        "selection_id": 47973, "handicap": 0, "entry_side": "back",
        "entry_price": 3.0, "entry_size": 10.0, "params": {}, "trail_extreme": None,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
def test_offset_enqueues_place_and_marks_done():
    rule = _rule(rule_type="offset", params={"offset_ticks": 10})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.0, 2.98, 3.0, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert len(sb.enqueued) == 1
    p = sb.enqueued[0]
    assert p["action"] == "place" and p["side"] == "lay" and p["price"] == 2.80 and p["size"] == 10.0
    assert p["client_ref"] == "risk1o"  # offset = suffisso 'o' (coesiste con lo stop 's' nei bracket)
    assert rule["status"] == "done" and rule["enqueued_request_id"]


def test_stop_loss_fires_enqueues_greenup():
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10})
    sb = _FakeSb([rule])
    # LTP 3.55 >= trigger 3.50 → scatta; posizione non piatta
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert len(sb.enqueued) == 1
    assert sb.enqueued[0]["action"] == "greenup"
    assert rule["status"] == "triggered"


def test_stop_loss_no_fire_stays_armed():
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.40, 3.35, 3.4, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "armed"


def test_trailing_no_fire_updates_extreme():
    rule = _rule(rule_type="trailing_stop", params={"trail_ticks": 5}, trail_extreme=None)
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 2.80, 2.78, 2.80, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["trail_extreme"] == 2.80 and rule["status"] == "armed"


def test_kill_switch_blocks_fire(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rw.low, "_kill_switch", lambda: True)
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 20.0, -10.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "armed"  # tenuta armata, riprende a freno tolto


def test_flat_position_marks_done_without_order():
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10})
    sb = _FakeSb([rule])
    # condizione di prezzo vera ma posizione piatta (W==L)
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 0.0, 0.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "done"


def test_transient_error_keeps_rule_armed():
    # fix review MEDIUM: un errore transitorio (mercato momentaneamente assente) NON deve
    # disarmare la regola protettiva → resta 'armed' e ritenta al giro dopo.
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10}, market_id="1.999")
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 20.0, -10.0))  # mercato "1.999" assente
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "armed"  # NON 'error'


# ===========================================================================
# Risk engine v2: on-fill / anti-gamba-nuda / bracket OCO / place_at / in-play
# ===========================================================================
def _orderobj(bet_id=None, matched=0.0, status="EXECUTABLE", cust_ref=None) -> Any:
    return SimpleNamespace(
        bet_id=bet_id, size_matched=matched, status=SimpleNamespace(name=status),
        notes=({"customer_order_ref": cust_ref} if cust_ref else {}), context={},
    )


class _BlotterV2:
    def __init__(self, w, l, orders=None):
        self._w, self._l = w, l
        self._orders = list(orders or [])

    def get_exposures(self, _s, _lk):
        return {"matched_profit_if_win": self._w, "matched_profit_if_lose": self._l}

    def get_order_bet_id(self, bet_id):
        for o in self._orders:
            if getattr(o, "bet_id", None) == bet_id:
                return o
        return None

    def __iter__(self):
        return iter(self._orders)


def _market_v2(sel=47973, ltp=3.0, bb=2.98, bl=3.0, w=20.0, l=-10.0, inplay=None, orders=None) -> Any:
    mb = SimpleNamespace(runners=[_runner(sel, ltp, bb, bl)], inplay=inplay)
    return SimpleNamespace(market_id="1.1", market_book=mb, blotter=_BlotterV2(w, l, orders))


def test_offset_on_fill_waits_then_places_matched_size():
    entry = _orderobj(bet_id="E1", matched=0.0, status="EXECUTABLE")
    rule = _rule(rule_type="offset", params={"offset_ticks": 10, "timing": "on_fill"}, entry_bet_id="E1")
    sb = _FakeSb([rule])
    market = _market_v2(orders=[entry])
    fl = _flumine(market)
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == [] and rule["status"] == "armed"   # attende il fill dell'ingresso
    entry.size_matched = 8.0                                  # l'ingresso si abbina
    rw._process_once(sb, fl, strategy=object())
    assert len(sb.enqueued) == 1
    assert sb.enqueued[0]["action"] == "place" and sb.enqueued[0]["size"] == 8.0
    assert rule["status"] == "done"


def test_offset_anti_naked_leg():
    entry = _orderobj(bet_id="E1", matched=0.0, status="LAPSED")  # ingresso lapsato, 0 match
    rule = _rule(rule_type="offset", params={"offset_ticks": 10}, entry_bet_id="E1")
    sb = _FakeSb([rule])
    rw._process_once(sb, _flumine(_market_v2(orders=[entry])), strategy=object())
    assert sb.enqueued == []                # NESSUN offset orfano
    assert rule["status"] == "done" and "gamba-nuda" in rule["result"]["note"]


def test_bracket_places_offset_then_stop_fires_cancels_offset():
    rule = _rule(rule_type="bracket", params={"offset_ticks": 10, "trigger_ticks": 10})
    sb = _FakeSb([rule])
    market = _market_v2(ltp=3.0)
    fl = _flumine(market)
    # poll 1: piazza l'offset, stato offset_placed
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued[0]["client_ref"] == "risk1o"
    assert rule["result"]["state"] == "offset_placed"
    off_req = rule["result"]["offset_request_id"]
    # l'offset ora "risiede" nel blotter (piazzato dalla coda), con bet_id
    market.blotter._orders.append(_orderobj(bet_id="OFF1", status="EXECUTABLE", cust_ref="awlq" + str(off_req)))
    # poll 2: prezzo avverso (LTP 3.55 >= trigger 3.50) → stop → cancel offset + greenup (OCO)
    market.market_book.runners[0].last_price_traded = 3.55
    market.market_book.runners[0].ex.available_to_lay = [SimpleNamespace(price=3.55, size=100.0)]
    rw._process_once(sb, fl, strategy=object())
    actions = [e["action"] for e in sb.enqueued]
    assert "cancel" in actions and "greenup" in actions
    assert rule["status"] == "triggered"


def test_bracket_take_profit_fills_cancels_stop():
    rule = _rule(rule_type="bracket", params={"offset_ticks": 10, "trigger_ticks": 10})
    sb = _FakeSb([rule])
    market = _market_v2(ltp=3.0)
    fl = _flumine(market)
    rw._process_once(sb, fl, strategy=object())          # poll 1: offset piazzato
    off_req = rule["result"]["offset_request_id"]
    # l'offset si ABBINA (take-profit eseguito)
    market.blotter._orders.append(_orderobj(bet_id="OFF1", matched=10.0,
                                            status="EXECUTION_COMPLETE", cust_ref="awlq" + str(off_req)))
    before = len(sb.enqueued)
    rw._process_once(sb, fl, strategy=object())          # poll 2: OCO → done, niente stop
    assert len(sb.enqueued) == before                    # nessun ordine nuovo (stop annullato)
    assert rule["status"] == "done" and "take-profit" in rule["result"]["note"]


def test_stop_passes_place_at_to_greenup():
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10, "place_at_ticks": 3})
    sb = _FakeSb([rule])
    market = _market_v2(ltp=3.55, bb=3.5, bl=3.55)
    rw._process_once(sb, _flumine(market), strategy=object())
    assert sb.enqueued[0]["action"] == "greenup"
    assert sb.enqueued[0]["params"]["place_at_ticks"] == 3


def test_inplay_cancel_policy_disarms_rule():
    # fix review MEDIUM: la transizione pre→in va rilevata su un GENUINO False→True (non al primo
    # avvistamento). Ciclo 1 pre-match = semina inplay=False; ciclo 2 in-play = transizione → cancel.
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10, "on_inplay": "cancel"})
    sb = _FakeSb([rule])
    market = _market_v2(ltp=3.0, inplay=False)   # pre-match
    fl = _flumine(market)
    rw._process_once(sb, fl, strategy=object())
    assert rule["status"] == "armed" and rule["result"]["inplay"] is False   # seminato, no policy
    market.market_book.inplay = True             # calcio d'inizio → transizione vera
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "cancelled"


def test_inplay_no_false_transition_when_armed_inplay():
    # regola armata mentre il mercato è GIÀ in-play: il primo giro NON deve annullare (solo semina).
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10, "on_inplay": "cancel"})
    sb = _FakeSb([rule])
    market = _market_v2(ltp=3.0, inplay=True)    # già in-play all'armamento
    rw._process_once(sb, _flumine(market), strategy=object())
    assert rule["status"] == "armed"             # NON cancellata (nessuna falsa transizione)
    assert rule["result"]["inplay"] is True


def test_inplay_keep_policy_continues():
    rule = _rule(rule_type="stop_loss", params={"trigger_ticks": 10})  # default keep
    sb = _FakeSb([rule])
    market = _market_v2(ltp=3.55, bb=3.5, bl=3.55, inplay=True)  # in-play + stop condition vera
    rw._process_once(sb, _flumine(market), strategy=object())
    assert sb.enqueued[0]["action"] == "greenup"   # keep → continua e scatta
    assert rule["status"] == "triggered"


def test_bracket_stop_waits_if_offset_not_yet_placed():
    # fix review HIGH: se lo stop scatta ma l'offset non è ancora nel blotter (bet_id assente),
    # il worker NON deve flattenare (lascerebbe un take-profit resting nudo piazzato dopo): ASPETTA.
    rule = _rule(rule_type="bracket", params={"offset_ticks": 10, "trigger_ticks": 10})
    sb = _FakeSb([rule])
    market = _market_v2(ltp=3.0)
    fl = _flumine(market)
    rw._process_once(sb, fl, strategy=object())          # poll1: offset accodato, state offset_placed
    n_after_p1 = len(sb.enqueued)
    # offset NON ancora nel blotter (la coda non l'ha piazzato). Il prezzo diventa avverso.
    market.market_book.runners[0].last_price_traded = 3.55
    market.market_book.runners[0].ex.available_to_lay = [SimpleNamespace(price=3.55, size=100.0)]
    rw._process_once(sb, fl, strategy=object())          # poll2: off is None → aspetta
    assert len(sb.enqueued) == n_after_p1                # nessun cancel, nessun greenup
    assert rule["status"] == "armed"                     # resta in attesa (non 'triggered')


# ---------------------------------------------------------------------------
# STOP-ENTRY (C23) — worker
# ---------------------------------------------------------------------------
def test_stop_entry_waits_below_trigger():
    rule = _rule(rule_type="stop_entry", entry_price=None,
                 params={"trigger_price": 3.5, "trigger_direction": "at_or_above"})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.4, 3.35, 3.4, 0.0, 0.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "armed"  # resta in attesa della soglia


def test_stop_entry_fires_places_at_best():
    rule = _rule(rule_type="stop_entry", entry_price=None,
                 params={"trigger_price": 3.5, "trigger_direction": "at_or_above"})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 0.0, 0.0))
    rw._process_once(sb, fl, strategy=object())
    assert len(sb.enqueued) == 1
    p = sb.enqueued[0]
    assert p["action"] == "place" and p["side"] == "back"
    assert p["price"] == 3.5 and p["size"] == 10.0   # best BACK del proprio lato
    assert p["client_ref"] == "risk1e"
    assert rule["status"] == "done"                  # nessun follow-through per gli ingressi


def test_stop_entry_invalid_direction_is_visible_error():
    rule = _rule(rule_type="stop_entry", entry_price=None,
                 params={"trigger_price": 3.5, "trigger_direction": "sopra"})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 0.0, 0.0))
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "error"  # disarmo VISIBILE, mai retry silenzioso


def test_stop_entry_kill_switch_blocks_entry():
    rule = _rule(rule_type="stop_entry", entry_price=None,
                 params={"trigger_price": 3.5, "trigger_direction": "at_or_above"})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.55, 3.5, 3.55, 0.0, 0.0))
    import pytest as _pt
    with _pt.MonkeyPatch.context() as mp:
        mp.setattr(rw, "_kill_active", lambda: True)
        rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []          # il freno blocca le APERTURE
    assert rule["status"] == "armed"  # resta armata (potrà entrare a freno tolto)


# ---------------------------------------------------------------------------
# CHASE (C25) — worker (macchina a stati cancel→place)
# ---------------------------------------------------------------------------
def _live_order(bet_id: str, price: float, rem: float, status_name: str = "EXECUTABLE",
                cancelled: float = 0.0):
    return SimpleNamespace(
        bet_id=bet_id,
        status=SimpleNamespace(name=status_name),
        size_remaining=rem,
        size_cancelled=cancelled,
        order_type=SimpleNamespace(price=price),
    )


def test_chase_tracking_enqueues_cancel_when_best_moves(monkeypatch):
    rule = _rule(rule_type="chase", entry_price=None, entry_bet_id="B1",
                 params={"offset_ticks": 0})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.1, 3.1, 3.15, 0.0, 0.0))
    order = _live_order("B1", 3.0, 10.0)  # resting a 3.0, best back ora 3.1
    monkeypatch.setattr(rw.low, "_find_order_by_bet_id", lambda *a: order)
    rw._process_once(sb, fl, strategy=object())
    assert len(sb.enqueued) == 1
    assert sb.enqueued[0]["action"] == "cancel" and sb.enqueued[0]["bet_id"] == "B1"
    assert rule["status"] == "armed"
    assert rule["result"]["phase"] == "cancelling"
    assert rule["result"]["pending_size"] == 10.0


def test_chase_no_requote_when_already_at_best(monkeypatch):
    rule = _rule(rule_type="chase", entry_price=None, entry_bet_id="B1",
                 params={"offset_ticks": 0})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.0, 3.0, 3.05, 0.0, 0.0))
    order = _live_order("B1", 3.0, 10.0)  # gia' al best
    monkeypatch.setattr(rw.low, "_find_order_by_bet_id", lambda *a: order)
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "armed"


def test_chase_cancelling_places_remaining_after_terminal(monkeypatch):
    rule = _rule(rule_type="chase", entry_price=None, entry_bet_id="B1",
                 params={"offset_ticks": 0},
                 result={"phase": "cancelling", "pending_size": 10.0,
                         "current_bet_id": "B1", "chase_count": 0})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.1, 3.1, 3.15, 0.0, 0.0))
    order = _live_order("B1", 3.0, 0.0, status_name="CANCELLED", cancelled=6.0)
    monkeypatch.setattr(rw.low, "_find_order_by_bet_id", lambda *a: order)
    rw._process_once(sb, fl, strategy=object())
    assert len(sb.enqueued) == 1
    p = sb.enqueued[0]
    assert p["action"] == "place" and p["price"] == 3.1
    assert p["size"] == 6.0  # SOLO il non-abbinato (size_cancelled), mai il totale
    assert rule["result"]["phase"] == "placing"


def test_chase_matched_during_requote_is_done(monkeypatch):
    rule = _rule(rule_type="chase", entry_price=None, entry_bet_id="B1",
                 params={"offset_ticks": 0},
                 result={"phase": "cancelling", "pending_size": 10.0,
                         "current_bet_id": "B1", "chase_count": 0})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.1, 3.1, 3.15, 0.0, 0.0))
    order = _live_order("B1", 3.0, 0.0, status_name="EXECUTION_COMPLETE")
    monkeypatch.setattr(rw.low, "_find_order_by_bet_id", lambda *a: order)
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "done"  # abbinato durante il re-quote: mai ripiazzare


def test_chase_cap_stops_requoting(monkeypatch):
    rule = _rule(rule_type="chase", entry_price=None, entry_bet_id="B1",
                 params={"offset_ticks": 0, "max_chases": 2},
                 result={"phase": "tracking", "chase_count": 2, "current_bet_id": "B1"})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.1, 3.1, 3.15, 0.0, 0.0))
    order = _live_order("B1", 3.0, 10.0)
    monkeypatch.setattr(rw.low, "_find_order_by_bet_id", lambda *a: order)
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "done"  # cap raggiunto: l'ordine resta dov'e'


def test_chase_cancelling_lapsed_uses_size_lapsed_not_stale_pending(monkeypatch):
    """Fix review CRITICAL: terminale LAPSED (persistence LAPSE + in-play durante il
    cancel) -> si ripiazza size_LAPSED, MAI il pending_size stantio pre-cancel (che
    non sconta un fill avvenuto nella race -> esposizione doppiata)."""
    rule = _rule(rule_type="chase", entry_price=None, entry_bet_id="B1",
                 params={"offset_ticks": 0},
                 result={"phase": "cancelling", "pending_size": 10.0,
                         "current_bet_id": "B1", "chase_count": 0})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.1, 3.1, 3.15, 0.0, 0.0))
    # 4 abbinati nella race, 6 lapsati: da ripiazzare SOLO 6
    order = SimpleNamespace(
        bet_id="B1", status=SimpleNamespace(name="LAPSED"),
        size_remaining=0.0, size_cancelled=0.0, size_lapsed=6.0, size_voided=0.0,
        order_type=SimpleNamespace(price=3.0),
    )
    monkeypatch.setattr(rw.low, "_find_order_by_bet_id", lambda *a: order)
    rw._process_once(sb, fl, strategy=object())
    assert len(sb.enqueued) == 1
    assert sb.enqueued[0]["size"] == 6.0  # size_lapsed, non 10.0


def test_chase_cancelling_zero_to_place_is_done(monkeypatch):
    """Tutto abbinato durante il cancel (campi terminali a 0) -> done, MAI fallback
    al pending_size (0.0 legittimo != dato mancante)."""
    rule = _rule(rule_type="chase", entry_price=None, entry_bet_id="B1",
                 params={"offset_ticks": 0},
                 result={"phase": "cancelling", "pending_size": 10.0,
                         "current_bet_id": "B1", "chase_count": 0})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.1, 3.1, 3.15, 0.0, 0.0))
    order = SimpleNamespace(
        bet_id="B1", status=SimpleNamespace(name="CANCELLED"),
        size_remaining=0.0, size_cancelled=0.0, size_lapsed=0.0, size_voided=0.0,
        order_type=SimpleNamespace(price=3.0),
    )
    monkeypatch.setattr(rw.low, "_find_order_by_bet_id", lambda *a: order)
    rw._process_once(sb, fl, strategy=object())
    assert sb.enqueued == []
    assert rule["status"] == "done"


def test_chase_placing_completes_back_to_tracking(monkeypatch):
    """Fase placing: il ripiazzo diventa un ordine vivo -> torna 'tracking' col nuovo
    bet_id e chase_count incrementato."""
    rule = _rule(rule_type="chase", entry_price=None, entry_bet_id="B1",
                 params={"offset_ticks": 0},
                 result={"phase": "placing", "place_request_id": 777,
                         "chase_count": 0, "current_bet_id": "B1"})
    sb = _FakeSb([rule])
    fl = _flumine(_market("1.1", 47973, 3.1, 3.1, 3.15, 0.0, 0.0))
    new_order = SimpleNamespace(bet_id="B2", status=SimpleNamespace(name="EXECUTABLE"),
                                size_remaining=6.0, order_type=SimpleNamespace(price=3.1))
    monkeypatch.setattr(rw, "_offset_order_obj", lambda *a: new_order)
    rw._process_once(sb, fl, strategy=object())
    assert rule["status"] == "armed"
    assert rule["result"]["phase"] == "tracking"
    assert rule["result"]["current_bet_id"] == "B2"
    assert rule["result"]["chase_count"] == 1


# ===========================================================================
# F39 — AUTO-HEDGE (floor-keeper del worst-case scoreline)
# ===========================================================================
from datetime import datetime, timedelta, timezone as _tz


class _FakeSbTables:
    """Fake Supabase con ROUTING per tabella (regole + betfair_live_xhedge)."""

    def __init__(self, rules, xhedge_rows):
        self.tables = {
            "betfair_live_risk_rules": rules,
            "betfair_live_xhedge": xhedge_rows,
        }
        self.enqueued = []
        self._next_req_id = 2000

    def table(self, name):
        return _Query(self.tables[name])

    def rpc(self, name, args):
        assert name == "request_betfair_live_order"
        self.enqueued.append(args["p"])
        self._next_req_id += 1
        return _RpcCall(self._next_req_id)


def _iso_ago(sec: float) -> str:
    return (datetime.now(_tz.utc) - timedelta(seconds=sec)).isoformat()


def _ah_rule(**over):
    rule = {
        "id": 7, "status": "armed", "mode": "paper", "rule_type": "auto_hedge",
        "market_id": "1.99", "selection_id": 0, "handicap": 0, "entry_side": "back",
        "params": {"floor": 10.0, "event_id": "ev1"}, "result": None,
    }
    rule.update(over)
    return rule


def _ah_xrow(worst=-25.0, *, age_sec=2.0, ignored=0, sug=None):
    suggestion = {
        "actionable": True, "scoreline": [1, 1], "side": "back",
        "odds": 8.0, "size": 5.0, "new_worst": -8.0, "new_best": 3.0, "note": "",
        "market_id": "1.99", "selection_id": 55,
    }
    if sug is not None:
        suggestion = sug
    return {
        "event_id": "ev1", "mode": "paper", "updated_at": _iso_ago(age_sec),
        "analysis": {
            "n_positions": 2, "ignored_orders": ignored,
            "summary": {"worst": worst, "best": 3.0, "mean": -1.0,
                        "worst_scoreline": [1, 1], "best_scoreline": [0, 0], "n_scorelines": 81},
            "suggestion": suggestion,
        },
    }


@pytest.fixture()
def _no_kill(monkeypatch):
    monkeypatch.setattr(rw.low, "_kill_switch", lambda: False)
    monkeypatch.setattr(rw.low, "_db_kill_switch", lambda: False)


def test_auto_hedge_fires_and_stays_armed(_no_kill):
    rule = _ah_rule()
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-25.0)])
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert len(sb.enqueued) == 1
    p = sb.enqueued[0]
    # payload ESATTO: ID dal suggerimento, ref deterministico, FoK 10s, back CS
    assert p["client_ref"] == "risk7h1"
    assert p["action"] == "place" and p["side"] == "back"
    assert p["market_id"] == "1.99" and p["selection_id"] == 55
    assert p["price"] == 8.0 and p["size"] == 5.0
    assert p["params"]["fok_ttl_sec"] == 10 and p["params"]["role"] == "auto_hedge"
    # floor-keeper: la regola RESTA armata con lo stato aggiornato
    assert rule["status"] == "armed"
    assert rule["result"]["hedges_done"] == 1
    assert rule["result"]["last_hedge_ts"]


def test_auto_hedge_no_action_when_floor_ok(_no_kill):
    rule = _ah_rule()
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-9.99)])  # floor 10 → −9.99 ok
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert sb.enqueued == [] and rule["status"] == "armed"


def test_auto_hedge_stale_analysis_never_hedges(_no_kill):
    rule = _ah_rule()
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-99.0, age_sec=120.0)])  # stantia
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert sb.enqueued == [] and rule["status"] == "armed"


def test_auto_hedge_incomplete_matrix_suspends_with_warning(_no_kill):
    rule = _ah_rule()
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-99.0, ignored=2)])
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert sb.enqueued == []
    assert rule["result"]["warned_incomplete"] is True  # avvisato, MAI coperto al buio


def test_auto_hedge_cap_reached_goes_done_with_alert(_no_kill):
    rule = _ah_rule(result={"hedges_done": 3})
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-99.0)])
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert sb.enqueued == []
    assert rule["status"] == "done"  # mai inseguire all'infinito: intervento manuale


def test_auto_hedge_cooldown_blocks_second_hedge(_no_kill):
    rule = _ah_rule(result={"hedges_done": 1, "last_hedge_ts": _iso_ago(10.0)})
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-99.0)])
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert sb.enqueued == []  # 10s < cooldown 60s


def test_auto_hedge_kill_switch_blocks(monkeypatch):
    monkeypatch.setattr(rw.low, "_kill_switch", lambda: True)
    rule = _ah_rule()
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-99.0)])
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert sb.enqueued == [] and rule["status"] == "armed"


def test_auto_hedge_submin_flow_below_min_stake(_no_kill):
    sug = {"actionable": True, "scoreline": [1, 1], "side": "back", "odds": 8.0,
           "size": 1.4, "new_worst": -8.0, "new_best": 3.0, "note": "",
           "market_id": "1.99", "selection_id": 55}
    rule = _ah_rule()
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-25.0, sug=sug)])
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    p = sb.enqueued[0]
    assert p["action"] == "place_submin" and p["size"] == 1.4
    assert "fok_ttl_sec" not in p["params"]  # il submin ha la sua macchina a stati


def test_auto_hedge_no_ids_alerts_and_waits(_no_kill):
    sug = {"actionable": True, "scoreline": [1, 1], "side": "back", "odds": 8.0,
           "size": 5.0, "new_worst": -8.0, "new_best": 3.0, "note": "",
           "market_id": None, "selection_id": None}
    rule = _ah_rule()
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-25.0, sug=sug)])
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert sb.enqueued == []
    assert rule["result"]["warned_nosug"] is True  # floor sforato senza copertura: avvisato


def test_auto_hedge_invalid_params_error(_no_kill):
    rule = _ah_rule(params={"floor": 0, "event_id": "ev1"})
    sb = _FakeSbTables([rule], [])
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert rule["status"] == "error" and sb.enqueued == []


def test_auto_hedge_max_stake_clamps_size(_no_kill):
    rule = _ah_rule(params={"floor": 10.0, "event_id": "ev1", "max_stake": 3.0})
    sb = _FakeSbTables([rule], [_ah_xrow(worst=-25.0)])
    rw._handle_auto_hedge(sb, SimpleNamespace(), rule, "paper")
    assert sb.enqueued[0]["size"] == 3.0  # clamp esplicito al cap utente


# ===========================================================================
# BUG FIX #9 cert 10/07 — DISARM: ritiro del TP resting creato dalla regola
# (visto dal vivo: bracket disarmato → lay 2.0@4.0 RESTAVA sul book = ordine nudo)
# ===========================================================================
def _cancelled_rule_with_offset(req_id=84, cleanup=False):
    return {
        "id": 13, "status": "cancelled", "mode": "paper", "rule_type": "bracket",
        "market_id": "1.9", "selection_id": 1, "handicap": 0, "entry_side": "back",
        "params": {}, "result": {"state": "offset_placed", "offset_request_id": req_id,
                                  **({"offset_cleanup": True} if cleanup else {})},
    }


def test_disarm_cancels_resting_offset(monkeypatch):
    rule = _cancelled_rule_with_offset()
    sb = _FakeSbTables([rule], [])
    live = SimpleNamespace(bet_id="B77", size_remaining=2.0, status="EXECUTABLE")
    monkeypatch.setattr(rw, "_offset_order_obj", lambda fl, mid, rid: live)
    n = rw._cleanup_cancelled_offsets(sb, SimpleNamespace(), "paper")
    assert n == 1
    assert len(sb.enqueued) == 1
    p = sb.enqueued[0]
    assert p["action"] == "cancel" and p["bet_id"] == "B77"
    assert p["client_ref"] == "risk13dc"          # deterministico: mai doppio cancel
    assert rule["result"]["offset_cleanup"] is True


def test_disarm_offset_already_matched_no_cancel(monkeypatch):
    rule = _cancelled_rule_with_offset()
    sb = _FakeSbTables([rule], [])
    done = SimpleNamespace(bet_id="B77", size_remaining=0.0, status="EXECUTION_COMPLETE")
    monkeypatch.setattr(rw, "_offset_order_obj", lambda fl, mid, rid: done)
    n = rw._cleanup_cancelled_offsets(sb, SimpleNamespace(), "paper")
    assert n == 1 and sb.enqueued == []           # niente da ritirare
    assert rule["result"]["offset_cleanup"] is True


def test_disarm_cleanup_idempotent(monkeypatch):
    rule = _cancelled_rule_with_offset(cleanup=True)  # già ripulita
    sb = _FakeSbTables([rule], [])
    monkeypatch.setattr(rw, "_offset_order_obj", lambda fl, mid, rid: None)
    n = rw._cleanup_cancelled_offsets(sb, SimpleNamespace(), "paper")
    assert n == 0 and sb.enqueued == []


def test_disarm_offset_unresolvable_alerts(monkeypatch):
    rule = _cancelled_rule_with_offset()
    sb = _FakeSbTables([rule], [])
    alerts = []
    monkeypatch.setattr(rw, "_offset_order_obj", lambda fl, mid, rid: None)
    monkeypatch.setattr(rw, "_alert", lambda lvl, msg: alerts.append((lvl, msg)))
    n = rw._cleanup_cancelled_offsets(sb, SimpleNamespace(), "paper")
    assert n == 1 and sb.enqueued == []
    assert alerts and alerts[0][0] == "CRITICAL"  # mai silenzio su un resting non ritirabile
