"""Unit test del worker della coda ordini live (`Betfair/stream/live_order_worker.py`).

Money-critical: NESSUNA rete, NESSUN login, NESSUN ordine reale. Il framework flumine,
il Market, il blotter e la coda Supabase sono MOCK leggeri in-memory; le validazioni
e la costruzione ordine usano `live_order_build` reale (logica pura, niente I/O).

Scenari coperti:
  - place paper: claim atomico → market.place_order NATIVO → riga 'done' + esito;
  - filtro mode: una riga 'live' NON è processata da un runner PAPER (resta 'pending');
  - claim: una riga già 'processing' (non-submin) non viene ri-presa;
  - market non sottoscritto / validazione fallita / ordine non trovato → riga 'error', no crash;
  - cancel / replace su ordine trovato per bet_id nel blotter (API native);
  - kill-switch attivo → nessun ordine processato;
  - best-effort: un'eccezione su una riga non fa cadere il worker;
  - place_submin: step1 place + riga 'processing' con SubminState persistito; avanzamento
    (PLACED→TRIMMED) e guardia rischio (match alla quota non abbinabile → ABORTED/'error').
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from flumine import BaseStrategy

import Betfair.stream.live_order_worker as wk

# Riferimenti alle implementazioni REALI catturati all'import (prima che la fixture autouse
# li sovrascriva): servono ai test che verificano la rilettura LIVE dell'env (fix kill/cap).
_REAL_KILL_SWITCH = wk._kill_switch
_REAL_MAX_STAKE = wk._max_stake
_REAL_LIVE_ORDER_MODE = wk._live_order_mode

# Strategy registrata "tipo": l'istanza sotto cui gli ordini del worker sono creati
# (in produzione è la LiveTradingStrategy registrata nel framework e passata via func_kwargs).
_STRAT = BaseStrategy(market_filter={}, name="live_trading")


# ---------------------------------------------------------------------------
# Fake Supabase (coda in-memory) — supporta la catena usata dal worker
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, store: List[Dict[str, Any]]) -> None:
        self._store = store
        self._op: Optional[str] = None
        self._payload: Dict[str, Any] = {}
        self._filters: List[tuple] = []
        self._neq_filters: List[tuple] = []
        self._order: Optional[str] = None
        self._limit: Optional[int] = None

    def select(self, *_a: Any) -> "_FakeQuery":
        self._op = "select"
        return self

    def update(self, payload: Dict[str, Any]) -> "_FakeQuery":
        self._op = "update"
        self._payload = dict(payload)
        return self

    def eq(self, k: str, v: Any) -> "_FakeQuery":
        self._filters.append((k, v))
        return self

    def neq(self, k: str, v: Any) -> "_FakeQuery":
        self._neq_filters.append((k, v))
        return self

    def order(self, k: str) -> "_FakeQuery":
        self._order = k
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def _match(self, row: Dict[str, Any]) -> bool:
        return all(row.get(k) == v for k, v in self._filters) and all(
            row.get(k) != v for k, v in self._neq_filters
        )

    def execute(self) -> _FakeResp:
        rows = [r for r in self._store if self._match(r)]
        if self._order:
            rows.sort(key=lambda r: r.get(self._order))
        if self._op == "select":
            if self._limit is not None:
                rows = rows[: self._limit]
            return _FakeResp([dict(r) for r in rows])
        # update: muta in place
        for r in rows:
            r.update(self._payload)
        return _FakeResp([dict(r) for r in rows])


class _FakeSupabase:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows

    def table(self, _name: str) -> _FakeQuery:
        return _FakeQuery(self.rows)


# ---------------------------------------------------------------------------
# Fake framework flumine (Market + blotter)
# ---------------------------------------------------------------------------
class _FakeBlotter:
    def __init__(self) -> None:
        self._by_bet: Dict[str, Any] = {}
        self._by_id: Dict[str, Any] = {}

    def add(self, order: Any) -> None:
        bid = getattr(order, "bet_id", None)
        if bid:
            self._by_bet[bid] = order
        oid = getattr(order, "id", None)
        if oid:
            self._by_id[oid] = order

    def get_order_bet_id(self, bet_id: str) -> Optional[Any]:
        return self._by_bet.get(bet_id)

    def __getitem__(self, oid: str) -> Any:
        return self._by_id[oid]  # KeyError se assente (come flumine)

    def __iter__(self):
        return iter(list(self._by_id.values()))  # come flumine Blotter.__iter__


class _FakeMarket:
    def __init__(self, market_id: str) -> None:
        self.market_id = market_id
        self.blotter = _FakeBlotter()
        self.calls: List[tuple] = []

    def place_order(self, order: Any, **kwargs: Any) -> bool:
        self.calls.append(("place_order", order, kwargs))
        return True

    def cancel_order(self, order: Any, size_reduction: Optional[float] = None) -> bool:
        self.calls.append(("cancel_order", order, size_reduction))
        return True

    def replace_order(self, order: Any, new_price: float) -> bool:
        self.calls.append(("replace_order", order, new_price))
        return True


class _FakeMarketsContainer:
    def __init__(self, markets: Dict[str, _FakeMarket]) -> None:
        self.markets = markets

    def __iter__(self):
        return iter(list(self.markets.values()))


class _FakeFlumine:
    def __init__(self, markets: Dict[str, _FakeMarket]) -> None:
        self.markets = _FakeMarketsContainer(markets)


def _fake_order(
    *,
    bet_id: Optional[str] = "B1",
    market_id: str = "1.1",
    side: str = "LAY",
    status: str = "EXECUTABLE",
    price: Optional[float] = 1.01,
    size: Optional[float] = 0.50,
    size_matched: float = 0.0,
    size_remaining: Optional[float] = None,
    oid: Optional[str] = "OID-1",
    cust_ref: Optional[str] = None,
):
    refs = {"customer_order_ref": cust_ref} if cust_ref else {}
    return SimpleNamespace(
        id=oid,
        bet_id=bet_id,
        market_id=market_id,
        side=side,
        status=status,
        size_matched=size_matched,
        size_remaining=size_remaining if size_remaining is not None else size,
        average_price_matched=0.0,
        size_cancelled=0.0,
        size_lapsed=0.0,
        size_voided=0.0,
        order_type=SimpleNamespace(price=price, size=size),
        notes=dict(refs),
        context=dict(refs),
    )


# ---------------------------------------------------------------------------
# Config patch (mode/jurisdiction/cap/kill) deterministica
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "PAPER")
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(wk, "_batch", lambda: 5)
    monkeypatch.setattr(wk, "_max_stake", lambda: 10.0)


def _row(rid: int, **kw: Any) -> Dict[str, Any]:
    base = {
        "id": rid,
        "action": "place",
        "mode": "paper",
        "status": "pending",
        "market_id": "1.1",
        "selection_id": 47999,
        "handicap": 0,
        "side": "back",
        "order_type": "LIMIT",
        "price": 3.0,
        "size": 5.0,
        "liability": None,
        "persistence": "LAPSE",
        "time_in_force": None,
        "min_fill_size": None,
        "bet_id": None,
        "new_price": None,
        "size_reduction": None,
        "params": None,
        "result": None,
        "error": None,
    }
    base.update(kw)
    return base


def _by_id(sb: _FakeSupabase, rid: int) -> Dict[str, Any]:
    return next(r for r in sb.rows if r["id"] == rid)


# ===========================================================================
# place
# ===========================================================================
def test_place_paper_happy():
    sb = _FakeSupabase([_row(1)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    assert [c[0] for c in market.calls] == ["place_order"]
    # customer_strategy_ref nativo passato a place_order
    assert market.calls[0][2].get("customer_strategy_ref") == wk.CUSTOMER_STRATEGY_REF
    row = _by_id(sb, 1)
    assert row["status"] == "done"
    res = row["result"]
    assert res["ok"] is True
    assert res["action"] == "place"
    assert res["mode"] == "paper"
    assert res["side"] == "back"
    assert res["price"] == 3.0
    assert res["size"] == 5.0
    assert res["customer_order_ref"] == "awlq1"


def test_place_creates_order_under_registered_strategy():
    """FIX keystone: l'ordine piazzato è un Trade legato alla strategy REGISTRATA passata
    al worker → flumine instrada process_orders (specchio) alla nostra strategia."""
    sb = _FakeSupabase([_row(1)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    placed_order = market.calls[0][1]
    assert placed_order.trade.strategy is _STRAT
    # ref nostro awlq<id> nel context (lo specchio lo rilegge da qui)
    assert placed_order.context["customer_order_ref"] == "awlq1"


def test_cross_mode_row_marked_error_not_left_pending():
    """fix(b): un runner PAPER NON piazza una richiesta 'live', ma la marca 'error'
    (messaggio chiaro) invece di lasciarla 'pending' all'infinito."""
    sb = _FakeSupabase([_row(1, mode="live")])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    assert market.calls == []  # nessun ordine piazzato dal runner della mode opposta
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "non servibile" in (row["error"] or "")
    assert "live" in (row["error"] or "")


def test_same_mode_row_not_touched_by_cross_mode_pass():
    """La riga della STESSA mode del runner non è toccata dal passo cross-mode."""
    sb = _FakeSupabase([_row(1, mode="paper")])  # runner PAPER (fixture) → servibile
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    row = _by_id(sb, 1)
    assert row["status"] == "done"  # processata normalmente, NON marcata error
    assert "non servibile" not in (row["error"] or "")


def test_processing_row_not_reclaimed():
    """Una riga già 'processing' (non-submin) non viene ri-processata."""
    sb = _FakeSupabase([_row(1, status="processing")])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 0
    assert market.calls == []


def test_market_not_subscribed_writes_error():
    sb = _FakeSupabase([_row(1)])
    fl = _FakeFlumine({})  # nessun mercato

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "non sottoscritto" in row["error"]


def test_build_validation_error_below_min_stake():
    """BACK €1,00 < minimo €2,00 (.it) → riga error, nessun ordine piazzato."""
    sb = _FakeSupabase([_row(1, size=1.0)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    assert market.calls == []
    assert _by_id(sb, 1)["status"] == "error"


def test_unknown_action_errors():
    sb = _FakeSupabase([_row(1, action="frobnicate")])
    # action non in CHECK ma simuliamo robustezza del dispatch
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)
    assert _by_id(sb, 1)["status"] == "error"


# ===========================================================================
# cancel / replace
# ===========================================================================
def test_cancel_happy():
    order = _fake_order(bet_id="B1", market_id="1.1")
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    sb = _FakeSupabase([_row(1, action="cancel", bet_id="B1", side=None, price=None, size=None)])

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    assert market.calls[0][0] == "cancel_order"
    assert market.calls[0][1] is order
    assert _by_id(sb, 1)["status"] == "done"


def test_cancel_partial_passes_size_reduction():
    order = _fake_order(bet_id="B2", market_id="1.1")
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    sb = _FakeSupabase([_row(1, action="cancel", bet_id="B2", size_reduction=0.20,
                             side=None, price=None, size=None)])

    wk._process_once(sb, fl, strategy=_STRAT)
    assert market.calls[0] == ("cancel_order", order, 0.20)


def test_cancel_order_not_found_errors():
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})
    sb = _FakeSupabase([_row(1, action="cancel", bet_id="NOPE", side=None, price=None, size=None)])

    wk._process_once(sb, fl, strategy=_STRAT)
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "non trovato" in row["error"]
    assert market.calls == []


def test_replace_happy_rounds_to_tick():
    order = _fake_order(bet_id="B3", market_id="1.1")
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    sb = _FakeSupabase([_row(1, action="replace", bet_id="B3", new_price=3.0,
                             side=None, price=None, size=None)])

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls[0][0] == "replace_order"
    assert market.calls[0][2] == 3.0
    assert _by_id(sb, 1)["status"] == "done"


def test_find_order_by_bet_id_scans_all_markets():
    order = _fake_order(bet_id="ZZ", market_id="1.2")
    m1 = _FakeMarket("1.1")
    m2 = _FakeMarket("1.2")
    m2.blotter.add(order)
    fl = _FakeFlumine({"1.1": m1, "1.2": m2})
    # market_id assente nella riga → scan di tutti i mercati
    found = wk._find_order_by_bet_id(fl, None, "ZZ")
    assert found is order


# ===========================================================================
# kill-switch + robustezza (best-effort)
# ===========================================================================
def test_kill_switch_blocks_everything(monkeypatch):
    monkeypatch.setattr(wk, "_kill_switch", lambda: True)
    sb = _FakeSupabase([_row(1)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    n = wk._process_once(sb, fl, strategy=_STRAT)

    # BUG FIX cert 10/07: l'apertura col freno NON resta pending (veniva eseguita
    # al riarmo) -> claim + esito 'error' esplicito, contata come handled.
    assert n == 1
    assert market.calls == []
    r1 = _by_id(sb, 1)
    assert r1["status"] == "error"
    assert "kill-switch" in str(r1.get("error") or "")


def test_kill_switch_flip_midbatch_blocks_remaining_orders(monkeypatch):
    """fix(a): il kill-switch è RI-LETTO per-ordine. Se viene attivato a metà batch,
    gli ordini GIÀ processati restano done, ma i rimanenti NON sono processati e
    restano 'pending' (mai claimati → mai bloccati in 'processing')."""
    # _kill_switch: OFF al gate di inizio ciclo + al 1° ordine, ON dal 2° in poi.
    state = {"n": 0}

    def _ks() -> bool:
        state["n"] += 1
        return state["n"] >= 3  # call1=gate, call2=row1 → False; call3=row2 → True

    monkeypatch.setattr(wk, "_kill_switch", _ks)
    sb = _FakeSupabase([_row(1), _row(2)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    n = wk._process_once(sb, fl, strategy=_STRAT)

    # solo il 1° ordine è stato piazzato; il 2° è RIFIUTATO esplicitamente a metà
    # batch (BUG FIX cert 10/07: mai più pending-trappola eseguita al riarmo)
    assert n == 2
    assert [c[0] for c in market.calls] == ["place_order"]
    assert _by_id(sb, 1)["status"] == "done"
    r2 = _by_id(sb, 2)
    assert r2["status"] == "error"
    assert "kill-switch" in str(r2.get("error") or "")


def test_off_mode_is_inert(monkeypatch):
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "OFF")
    sb = _FakeSupabase([_row(1)])
    fl = _FakeFlumine({"1.1": _FakeMarket("1.1")})
    assert wk._process_once(sb, fl, strategy=_STRAT) == 0
    assert _by_id(sb, 1)["status"] == "pending"


def test_place_order_raising_does_not_crash_worker():
    """market.place_order che solleva → riga error, nessuna eccezione propagata.

    CONTRATTO (fix 17/07): un'eccezione DENTRO place_order è AMBIGUA (l'ordine
    può essere già in dispatch) → il messaggio DEVE portare il prefisso
    ``post_place:`` così omega non libera mai la riserva su questo esito."""
    class _BoomMarket(_FakeMarket):
        def place_order(self, order: Any, **kwargs: Any) -> bool:
            raise RuntimeError("betfair boom")

    sb = _FakeSupabase([_row(1)])
    fl = _FakeFlumine({"1.1": _BoomMarket("1.1")})

    n = wk._process_once(sb, fl, strategy=_STRAT)  # non deve sollevare

    assert n == 1
    assert _by_id(sb, 1)["status"] == "error"
    assert "boom" in _by_id(sb, 1)["error"]
    assert _by_id(sb, 1)["error"].startswith("post_place:")


def test_place_rifiutato_dai_control_resta_pre_place():
    """Ritorno False dai trading control = ordine MAI inviato: l'errore NON
    deve portare il prefisso post_place: (omega può liberare la riserva)."""
    class _RejectMarket(_FakeMarket):
        def place_order(self, order: Any, **kwargs: Any) -> bool:
            return False

    sb = _FakeSupabase([_row(1)])
    fl = _FakeFlumine({"1.1": _RejectMarket("1.1")})

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    assert _by_id(sb, 1)["status"] == "error"
    assert not _by_id(sb, 1)["error"].startswith("post_place:")
    assert "RIFIUTATO" in _by_id(sb, 1)["error"]


def test_live_order_worker_none_flumine_is_noop():
    # firma BackgroundWorker; flumine None → ritorna senza errori
    wk.live_order_worker({}, None, session=None)


# ===========================================================================
# fix(a): l'awlq<id> è un ref INTERNO, NON viaggia verso Betfair
# ===========================================================================
def test_awlq_ref_not_sent_to_betfair_only_internal_context():
    """Il ref awlq<id> è correlazione interna richiesta↔ordine: NON è passato come
    customerRef a market.place_order (a Betfair va solo customer_strategy_ref). Vive
    esclusivamente in order.context/notes per lo specchio DB."""
    sb = _FakeSupabase([_row(1)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    place_kwargs = market.calls[0][2]
    # a Betfair NON inviamo alcun customerRef "awlq": solo customer_strategy_ref nativo
    assert place_kwargs == {"customer_strategy_ref": wk.CUSTOMER_STRATEGY_REF}
    assert not any("awlq" in str(v) for v in place_kwargs.values())
    # il ref interno vive solo in context/notes dell'ordine
    placed = market.calls[0][1]
    assert placed.context["customer_order_ref"] == "awlq1"
    assert placed.notes["customer_order_ref"] == "awlq1"


# ===========================================================================
# fix(c): kill-switch e cap RI-LETTI LIVE dall'env (no riavvio)
# ===========================================================================
def test_kill_switch_reread_from_env_live(monkeypatch):
    """Il kill-switch è riletto dall'env ad ogni ciclo: flipparlo a runtime blocca i
    place al giro successivo senza reimport/riavvio del runner."""
    monkeypatch.setattr(wk, "_kill_switch", _REAL_KILL_SWITCH)  # usa l'impl REALE (non la fixture)
    monkeypatch.delenv("LIVE_KILL_SWITCH", raising=False)

    # ciclo 1: kill-switch OFF → l'ordine è processato
    sb1 = _FakeSupabase([_row(1)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})
    assert wk._process_once(sb1, fl, strategy=_STRAT) == 1
    assert _by_id(sb1, 1)["status"] == "done"

    # flip a runtime → ciclo 2 bloccato, riga intatta (pending)
    monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
    sb2 = _FakeSupabase([_row(2)])
    market2 = _FakeMarket("1.1")
    fl2 = _FakeFlumine({"1.1": market2})
    assert wk._process_once(sb2, fl2, strategy=_STRAT) == 1
    assert market2.calls == []
    r2 = _by_id(sb2, 2)
    assert r2["status"] == "error"  # BUG FIX cert 10/07: rifiuto esplicito
    assert "kill-switch" in str(r2.get("error") or "")


def test_max_stake_reread_from_env_live(monkeypatch):
    """Il cap di stake è riletto dall'env ad ogni chiamata: stringerlo a runtime fa fallire
    (riga error) l'ordine che lo supera, senza riavvio."""
    monkeypatch.setattr(wk, "_max_stake", _REAL_MAX_STAKE)  # usa l'impl REALE (non la fixture)

    # cap largo: BACK €5 passa
    monkeypatch.setenv("LIVE_MAX_STAKE_PER_ORDER", "10")
    sb1 = _FakeSupabase([_row(1, size=5.0)])
    fl = _FakeFlumine({"1.1": _FakeMarket("1.1")})
    wk._process_once(sb1, fl, strategy=_STRAT)
    assert _by_id(sb1, 1)["status"] == "done"

    # cap stretto a runtime: BACK €5 ora oltre il tetto €3 → error
    monkeypatch.setenv("LIVE_MAX_STAKE_PER_ORDER", "3")
    sb2 = _FakeSupabase([_row(2, size=5.0)])
    wk._process_once(sb2, fl, strategy=_STRAT)
    row = _by_id(sb2, 2)
    assert row["status"] == "error"
    assert "cap" in (row["error"] or "")


def test_live_order_mode_reread_from_env_live(monkeypatch):
    """SEC-MED-1: la mode è RI-LETTA dall'env ad ogni ciclo. Un DOWNGRADE di sicurezza
    (LIVE/PAPER → OFF) a runtime rende il worker inerte al giro successivo, SENZA riavvio
    (prima era congelata via _cfg_attr all'import)."""
    monkeypatch.setattr(wk, "_live_order_mode", _REAL_LIVE_ORDER_MODE)  # impl REALE, non la fixture

    # ciclo 1: PAPER → l'ordine è processato
    monkeypatch.setenv("LIVE_ORDER_MODE", "paper")
    sb1 = _FakeSupabase([_row(1)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})
    assert wk._process_once(sb1, fl, strategy=_STRAT) == 1
    assert _by_id(sb1, 1)["status"] == "done"

    # downgrade a runtime → OFF: worker INERTE (diverso dal kill: qui non si
    # processa nulla e la riga resta pending — nessun claim, nessun esito)
    monkeypatch.setenv("LIVE_ORDER_MODE", "OFF")
    sb2 = _FakeSupabase([_row(2)])
    market2 = _FakeMarket("1.1")
    fl2 = _FakeFlumine({"1.1": market2})
    assert wk._process_once(sb2, fl2, strategy=_STRAT) == 0
    assert market2.calls == []
    assert _by_id(sb2, 2)["status"] == "pending"


def test_live_order_mode_falls_back_to_env_when_no_config_helper(monkeypatch):
    """SEC-MED-1 fallback: senza il helper config_stream.live_order_mode, la mode è letta
    direttamente da os.getenv (con default OFF)."""
    import Betfair.stream.config_stream as cs
    monkeypatch.setattr(wk, "_live_order_mode", _REAL_LIVE_ORDER_MODE)
    monkeypatch.delattr(cs, "live_order_mode", raising=False)
    monkeypatch.setenv("LIVE_ORDER_MODE", "live")
    assert wk._live_order_mode() == "LIVE"
    monkeypatch.delenv("LIVE_ORDER_MODE", raising=False)
    assert wk._live_order_mode() == "OFF"


def test_config_helper_live_order_mode_rereads_env(monkeypatch):
    """SEC-MED-1: config_stream.live_order_mode() rilegge l'env ad ogni chiamata (UPPER)."""
    from Betfair.stream import config_stream as cs

    monkeypatch.setenv("LIVE_ORDER_MODE", "paper")
    assert cs.live_order_mode() == "PAPER"
    monkeypatch.setenv("LIVE_ORDER_MODE", "live")
    assert cs.live_order_mode() == "LIVE"
    monkeypatch.delenv("LIVE_ORDER_MODE", raising=False)
    assert cs.live_order_mode() == "OFF"


# ===========================================================================
# SEC-MED-2: kill-switch ferma anche l'avanzamento submin in corso
# ===========================================================================
def _submin_state(bid: str) -> Dict[str, Any]:
    return {
        "step": "placed", "bet_id": bid, "target_size": 0.30,
        "target_price": 5.0, "placed_size": 0.50, "side": "lay", "note": "",
    }


def test_kill_switch_blocks_inflight_submin_advance(monkeypatch):
    """SEC-MED-2: kill-switch ATTIVO → _advance_inflight_submins non avanza alcuna riga
    (nessun cancel/replace) e lo stato submin resta invariato ('processing')."""
    monkeypatch.setattr(wk, "_kill_switch", lambda: True)
    order = _fake_order(bet_id="B1", market_id="1.1", side="LAY", status="EXECUTABLE",
                        price=1.01, size=0.50, size_remaining=0.50, oid="OID-1")
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    sb = _FakeSupabase([_row(1, action="place_submin", status="processing", side="lay",
                             price=5.0, size=0.30,
                             result={"submin_step": "placed",
                                     "submin_state": _submin_state("B1"), "submin_order_id": "OID-1"})])

    n = wk._advance_inflight_submins(sb, fl, "paper", _STRAT)

    assert n == 0
    assert market.calls == []  # nessun cancel/replace partito
    assert _by_id(sb, 1)["status"] == "processing"
    assert _by_id(sb, 1)["result"]["submin_step"] == "placed"  # invariato


def test_kill_switch_flip_stops_remaining_inflight_submins(monkeypatch):
    """SEC-MED-2: il kill-switch è RI-LETTO per-riga nel loop submin. Attivarlo a metà
    avanzamento fa proseguire la riga già in corso ma BLOCCA SUBITO le rimanenti."""
    state = {"n": 0}

    def _ks() -> bool:
        state["n"] += 1
        return state["n"] >= 2  # row1 → False (avanza); row2 → True (break)

    monkeypatch.setattr(wk, "_kill_switch", _ks)
    o1 = _fake_order(bet_id="B1", market_id="1.1", side="LAY", status="EXECUTABLE",
                     price=1.01, size=0.50, size_remaining=0.50, oid="OID-1")
    o2 = _fake_order(bet_id="B2", market_id="1.1", side="LAY", status="EXECUTABLE",
                     price=1.01, size=0.50, size_remaining=0.50, oid="OID-2")
    market = _FakeMarket("1.1")
    market.blotter.add(o1)
    market.blotter.add(o2)
    fl = _FakeFlumine({"1.1": market})
    sb = _FakeSupabase([
        _row(1, action="place_submin", status="processing", side="lay", price=5.0, size=0.30,
             result={"submin_step": "placed",
                     "submin_state": _submin_state("B1"), "submin_order_id": "OID-1"}),
        _row(2, action="place_submin", status="processing", side="lay", price=5.0, size=0.30,
             result={"submin_step": "placed",
                     "submin_state": _submin_state("B2"), "submin_order_id": "OID-2"}),
    ])

    n = wk._advance_inflight_submins(sb, fl, "paper", _STRAT)

    assert n == 1  # solo row1 avanzata
    assert [c[0] for c in market.calls] == ["cancel_order"]  # un solo cancel (row1)
    # fix 11/07: il cancel NON promuove piu' a TRIMMED (serve l'osservazione);
    # la row1 resta 'placed' ma con la richiesta di trim registrata
    r1 = _by_id(sb, 1)["result"]
    assert r1["submin_step"] == "placed"
    assert r1["submin_state"]["trim_requested_ms"] > 0
    r2 = _by_id(sb, 2)["result"]
    assert r2["submin_step"] == "placed"  # bloccata, invariata
    assert not r2["submin_state"].get("trim_requested_ms")


# ===========================================================================
# CODE-MED-1: replace LAY oltre il cap → error (liability = size*(price-1))
# ===========================================================================
def test_replace_lay_over_cap_errors():
    """CODE-MED-1: un replace al rialzo che porta la liability LAY oltre il cap effettivo
    è RIFIUTATO (riga error) PRIMA di market.replace_order. cap fixture = €10."""
    # LAY size €5 @ replace 4.0 → liability 5*(4-1)=€15 > cap €10
    order = _fake_order(bet_id="B9", market_id="1.1", side="LAY", price=2.0, size=5.0)
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    sb = _FakeSupabase([_row(1, action="replace", bet_id="B9", new_price=4.0,
                             side=None, price=None, size=None)])

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls == []  # nessun replace reale: cap scattato prima
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "cap" in (row["error"] or "")


def test_replace_lay_under_cap_ok():
    """CODE-MED-1 no falsi positivi: liability sotto il cap → replace eseguito."""
    order = _fake_order(bet_id="B10", market_id="1.1", side="LAY", price=1.5, size=1.0)
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    sb = _FakeSupabase([_row(1, action="replace", bet_id="B10", new_price=3.0,
                             side=None, price=None, size=None)])

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls[0][0] == "replace_order"  # liability 1*(3-1)=€2 < €10 → ok
    assert _by_id(sb, 1)["status"] == "done"


def test_replace_lay_respects_per_request_cap(monkeypatch):
    """CODE-MED-1: il cap effettivo include params.max_stake per-richiesta (più stretto)."""
    order = _fake_order(bet_id="B11", market_id="1.1", side="LAY", price=1.5, size=1.0)
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    # liability 1*(3-1)=€2 supera il cap per-richiesta €1 (più stretto del cap globale €10)
    sb = _FakeSupabase([_row(1, action="replace", bet_id="B11", new_price=3.0,
                             side=None, price=None, size=None, params={"max_stake": 1.0})])

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls == []
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "cap" in (row["error"] or "")


def test_config_helpers_reread_env(monkeypatch):
    """I helper config_stream.live_kill_switch / live_max_stake_per_order rileggono l'env
    ad ogni chiamata (non sono congelati all'import)."""
    from Betfair.stream import config_stream as cs

    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    assert cs.live_kill_switch() is False
    monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
    assert cs.live_kill_switch() is True

    # Cap OPT-IN (scelta utente 2026-07-01: no-cap di default). Un numero > 0 = cap attivo;
    # vuoto / 0 / non numerico / assente = None (nessun cap).
    monkeypatch.setenv("LIVE_MAX_STAKE_PER_ORDER", "7.5")
    assert cs.live_max_stake_per_order() == 7.5
    monkeypatch.setenv("LIVE_MAX_STAKE_PER_ORDER", "not-a-number")
    assert cs.live_max_stake_per_order() is None
    monkeypatch.setenv("LIVE_MAX_STAKE_PER_ORDER", "0")
    assert cs.live_max_stake_per_order() is None
    monkeypatch.setenv("LIVE_MAX_STAKE_PER_ORDER", "")
    assert cs.live_max_stake_per_order() is None
    monkeypatch.delenv("LIVE_MAX_STAKE_PER_ORDER", raising=False)
    assert cs.live_max_stake_per_order() is None


# ===========================================================================
# place_submin (place-and-trim)
# ===========================================================================
def test_submin_start_places_step1_and_stays_processing():
    sb = _FakeSupabase([_row(1, action="place_submin", side="lay", price=5.0, size=0.30)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    # step1: place size minima @ quota non abbinabile (lay 1.01), size 0.50
    assert [c[0] for c in market.calls] == ["place_order"]
    placed = market.calls[0][1]
    assert placed.order_type.price == 1.01
    assert placed.order_type.size == 0.50
    row = _by_id(sb, 1)
    assert row["status"] == "processing"   # sequenza in corso
    res = row["result"]
    assert res["submin_step"] == "placed"
    assert res["submin_state"]["target_size"] == 0.30
    assert res["submin_order_id"]  # id flumine persistito per i poll successivi


def test_submin_inflight_advance_to_trimmed():
    order = _fake_order(bet_id="B1", market_id="1.1", side="LAY",
                        status="EXECUTABLE", price=1.01, size=0.50, size_remaining=0.50)
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    state = {
        "step": "placed", "bet_id": "B1", "target_size": 0.30,
        "target_price": 5.0, "placed_size": 0.50, "side": "lay", "note": "",
    }
    sb = _FakeSupabase([_row(1, action="place_submin", status="processing", side="lay",
                             price=5.0, size=0.30,
                             result={"submin_state": state, "submin_order_id": "OID-1"})])

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    # PLACED: cancel parziale RICHIESTO (size_reduction 0.20); la promozione a
    # TRIMMED richiede l'OSSERVAZIONE del trim (fix 11/07, bug live 21:43)
    assert market.calls[0] == ("cancel_order", order, 0.20)
    row = _by_id(sb, 1)
    assert row["status"] == "processing"
    assert row["result"]["submin_step"] == "placed"
    assert row["result"]["submin_state"]["trim_requested_ms"] > 0

    # il trim viene OSSERVATO (size_remaining ~ target) → TRIMMED, no re-cancel
    order.size_remaining = 0.30
    n = wk._process_once(sb, fl, strategy=_STRAT)
    assert n == 1
    assert len([c for c in market.calls if c[0] == "cancel_order"]) == 1
    assert _by_id(sb, 1)["result"]["submin_step"] == "trimmed"


def test_submin_inflight_unexpected_match_aborts_to_error():
    """Match alla quota NON abbinabile (PLACED) → ABORTED → riga 'error', nessun cancel."""
    order = _fake_order(bet_id="B1", market_id="1.1", side="LAY",
                        status="EXECUTABLE", price=1.01, size=0.50,
                        size_matched=0.50, size_remaining=0.0)
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    state = {
        "step": "placed", "bet_id": "B1", "target_size": 0.30,
        "target_price": 5.0, "placed_size": 0.50, "side": "lay", "note": "",
    }
    sb = _FakeSupabase([_row(1, action="place_submin", status="processing", side="lay",
                             price=5.0, size=0.30,
                             result={"submin_state": state, "submin_order_id": "OID-1"})])

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls == []  # NESSUN cancel dopo il match
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "ABORT" in (row["error"] or "")
    assert row["result"]["submin_step"] == "aborted"


# ===========================================================================
# fix(a) MEDIUM — finestra di crash tra place REALE e persistenza dello step
# ===========================================================================
def test_submin_persists_init_state_before_real_place():
    """Lo SubminState ATTESO (step=INIT) è persistito su DB PRIMA del market.place_order
    REALE: un crash tra place e persistenza lascia comunque traccia (no ordine orfano)."""
    sb = _FakeSupabase([_row(1, action="place_submin", side="lay", price=5.0, size=0.30)])
    seen: Dict[str, Any] = {}

    class _PeekMarket(_FakeMarket):
        def place_order(self, order: Any, **kwargs: Any) -> bool:
            # fotografa lo stato persistito su DB AL MOMENTO del place reale
            res = _by_id(sb, 1).get("result") or {}
            seen["state_before_place"] = res.get("submin_state")
            return super().place_order(order, **kwargs)

    market = _PeekMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    # al momento del place reale lo stato INIT era GIÀ persistito (riconciliabile dopo crash)
    assert seen["state_before_place"] is not None
    assert seen["state_before_place"]["step"] == "init"


def test_submin_resume_after_real_restart_not_reconcilable_errors_no_double_place():
    """RIAVVIO REALE del processo TRA place e persistenza dello step.

    Sicurezza prima di tutto: lo stato su DB è ancora INIT (pre-persistito), SENZA
    submin_order_id né bet_id. Dopo un riavvio reale l'ordine è ricostruito dall'order
    stream di flumine SENZA le annotazioni locali notes/context (vedi
    order/process.create_order_from_current), quindi il NOSTRO ref interno awlq<id> NON
    sopravvive: l'ordine non è riconciliabile per ref. Il place POTREBBE già essere
    avvenuto su Betfair → la scelta onesta è NON ri-piazzare MAI: la riga va in 'error'
    con invito a riconciliare a mano. (Il test precedente asseriva una FALSA garanzia
    perché fingeva un ordine col ref ancora attaccato dopo il restart.)"""
    # Ordine fisicamente presente sul mercato ma SENZA il nostro ref (annotazioni perse
    # nel rebuild post-restart): non identificabile come nostro.
    orphan = _fake_order(
        bet_id="B-REAL", market_id="1.1", side="LAY", status="EXECUTABLE",
        price=1.01, size=0.50, size_remaining=0.50, oid="REBUILT-XYZ", cust_ref=None,
    )
    market = _FakeMarket("1.1")
    market.blotter.add(orphan)
    fl = _FakeFlumine({"1.1": market})
    # stato post-restart: INIT pre-persistito, SENZA submin_order_id né bet_id
    state = {
        "step": "init", "bet_id": None, "target_size": 0.30, "target_price": 5.0,
        "placed_size": 0.50, "side": "lay", "note": "submin init",
    }
    sb = _FakeSupabase([_row(1, action="place_submin", status="processing", side="lay",
                             price=5.0, size=0.30,
                             result={"submin_state": state, "submin_order_id": None})])

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    assert market.calls == []  # NESSUN secondo place: mai ri-piazzare in ripresa
    row = _by_id(sb, 1)
    assert row["status"] == "error"                       # fermati, non proseguire alla cieca
    assert row["result"]["submin_step"] == "aborted"
    assert "riconciliare manualmente" in (row["error"] or "")
    assert "NON ripiazzato" in (row["error"] or "")


def test_submin_resume_inprocess_reconciles_when_order_has_bet_id():
    """Crash IN-PROCESS (stessa esecuzione) tra place e persist: lo stato è ancora INIT
    ma l'ordine reale è ancora in memoria col ref interno awlq<id> E con bet_id assegnato
    → riconciliato con CERTEZZA a PLACED, senza ri-piazzare."""
    order = _fake_order(
        bet_id="B-REAL", market_id="1.1", side="LAY", status="EXECUTABLE",
        price=1.01, size=0.50, size_remaining=0.50, oid="OID-REAL", cust_ref="awlq1",
    )
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    state = {
        "step": "init", "bet_id": None, "target_size": 0.30, "target_price": 5.0,
        "placed_size": 0.50, "side": "lay", "note": "submin init",
    }
    sb = _FakeSupabase([_row(1, action="place_submin", status="processing", side="lay",
                             price=5.0, size=0.30,
                             result={"submin_state": state, "submin_order_id": None})])

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    assert market.calls == []  # NESSUN re-place: l'ordine reale è stato riconciliato per ref
    row = _by_id(sb, 1)
    assert row["status"] == "processing"
    assert row["result"]["submin_step"] == "placed"          # riconciliato a PLACED
    assert row["result"]["submin_state"]["bet_id"] == "B-REAL"
    assert row["result"]["submin_order_id"] == "OID-REAL"


def test_submin_resume_init_waits_when_order_found_without_bet_id():
    """Ripresa IN-PROCESS con ordine ritrovato per ref ma bet_id non ancora assegnato
    (placement async): si ATTENDE (resta INIT/processing), NON si piazza un secondo
    ordine e NON si abortisce — il bet_id arriverà al poll successivo."""
    order = _fake_order(
        bet_id=None, market_id="1.1", side="LAY", status="PENDING",
        price=1.01, size=0.50, size_remaining=0.50, oid="OID-REAL", cust_ref="awlq1",
    )
    market = _FakeMarket("1.1")
    market.blotter.add(order)
    fl = _FakeFlumine({"1.1": market})
    state = {
        "step": "init", "bet_id": None, "target_size": 0.30, "target_price": 5.0,
        "placed_size": 0.50, "side": "lay", "note": "submin init",
    }
    sb = _FakeSupabase([_row(1, action="place_submin", status="processing", side="lay",
                             price=5.0, size=0.30,
                             result={"submin_state": state, "submin_order_id": None})])

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    assert market.calls == []  # né place né cancel: si attende il bet_id
    row = _by_id(sb, 1)
    assert row["status"] == "processing"
    assert row["result"]["submin_step"] == "init"            # invariato, attesa


def test_find_order_by_cust_ref_scans_all_markets():
    """Lookup per ref interno deterministico: scandisce tutti i mercati del framework."""
    order = _fake_order(bet_id="ZZ", market_id="1.2", oid="OID-Z", cust_ref="awlq42")
    m1 = _FakeMarket("1.1")
    m2 = _FakeMarket("1.2")
    m2.blotter.add(order)
    fl = _FakeFlumine({"1.1": m1, "1.2": m2})

    assert wk._find_order_by_cust_ref(fl, None, "awlq42") is order
    assert wk._find_order_by_cust_ref(fl, None, "awlq-nope") is None


# ===========================================================================
# fix(b) LOW — il ramo submin NON bypassa il cap e passa il customer_strategy_ref
# ===========================================================================
def test_submin_start_passes_customer_strategy_ref_to_place():
    """Lo step1 submin passa il customer_strategy_ref NATIVO a market.place_order (come il
    place normale), non solo l'ordine."""
    sb = _FakeSupabase([_row(1, action="place_submin", side="lay", price=5.0, size=0.30)])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls[0][0] == "place_order"
    assert market.calls[0][2].get("customer_strategy_ref") == wk.CUSTOMER_STRATEGY_REF


def test_submin_place_enforces_effective_cap():
    """Il ramo submin propaga il cap effettivo a build_order (NON più max_stake=None): un cap
    per-richiesta sotto la size minima di piazzamento fa fallire la validazione (riga error),
    nessun ordine reale piazzato."""
    # BACK submin: placed = €2,00 (min .it). Cap per-richiesta €1,00 → il place del minimo
    # supera il cap → build_order solleva PRIMA di market.place_order.
    sb = _FakeSupabase([_row(1, action="place_submin", side="back", price=3.0, size=1.50,
                             params={"max_stake": 1.0})])
    market = _FakeMarket("1.1")
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls == []  # cap scattato in validazione: nessun place reale
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "cap" in (row["error"] or "")
