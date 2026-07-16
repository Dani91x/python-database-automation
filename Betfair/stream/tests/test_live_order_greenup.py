"""Unit test dell'azione ``greenup`` del worker (`live_order_worker._do_greenup`).

Money-critical: NESSUNA rete, NESSUN ordine reale. Market/blotter/market_book sono MOCK
in-memory; ``build_order`` reale (logica pura). Verifica che il green-up:
  * legga le esposizioni MATCHED da ``blotter.get_exposures`` (autoritative) e il best
    price opposto dal ``market_book``;
  * piazzi l'UNICO ordine di hedge corretto (LAY se vinco di più sul VINCE, BACK altrimenti)
    via API nativa ``market.place_order``;
  * sia un NO-OP pulito (riga 'done', nessun place) se la posizione è già piatta;
  * onori la frazione di cash-out parziale.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from flumine import BaseStrategy

import Betfair.stream.live_order_worker as wk

_STRAT = BaseStrategy(market_filter={}, name="live_trading")


# ---------------------------------------------------------------------------
# Fake Supabase (coda in-memory) — stessa catena del worker
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
        for r in rows:
            r.update(self._payload)
        return _FakeResp([dict(r) for r in rows])


class _FakeSupabase:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows

    def table(self, _name: str) -> _FakeQuery:
        return _FakeQuery(self.rows)


# ---------------------------------------------------------------------------
# Fake Market con blotter.get_exposures + market_book (best back/lay)
# ---------------------------------------------------------------------------
class _FakeBlotter:
    def __init__(self, exposures: Dict[str, float]) -> None:
        self._exp = exposures
        self.lookups: List[tuple] = []

    def get_exposures(self, strategy: Any, lookup: tuple) -> Dict[str, float]:
        self.lookups.append(lookup)
        return self._exp


def _ex(atb: List[tuple], atl: List[tuple]) -> SimpleNamespace:
    return SimpleNamespace(
        available_to_back=[SimpleNamespace(price=p, size=s) for p, s in atb],
        available_to_lay=[SimpleNamespace(price=p, size=s) for p, s in atl],
    )


class _FakeMarket:
    def __init__(
        self, market_id: str, exposures: Dict[str, float],
        atb: List[tuple], atl: List[tuple], selection_id: int = 47999, handicap: float = 0.0,
    ) -> None:
        self.market_id = market_id
        self.blotter = _FakeBlotter(exposures)
        self.market_book = SimpleNamespace(
            runners=[SimpleNamespace(selection_id=selection_id, handicap=handicap, ex=_ex(atb, atl))]
        )
        self.calls: List[tuple] = []

    def place_order(self, order: Any, **kwargs: Any) -> bool:
        self.calls.append(("place_order", order, kwargs))
        return True


class _FakeMarketsContainer:
    def __init__(self, markets: Dict[str, _FakeMarket]) -> None:
        self.markets = markets

    def __iter__(self):
        return iter(list(self.markets.values()))


class _FakeFlumine:
    def __init__(self, markets: Dict[str, _FakeMarket]) -> None:
        self.markets = _FakeMarketsContainer(markets)


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "PAPER")
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(wk, "_batch", lambda: 5)
    monkeypatch.setattr(wk, "_max_stake", lambda: 10.0)


def _greenup_row(rid: int, **kw: Any) -> Dict[str, Any]:
    base = {
        "id": rid,
        "action": "greenup",
        "mode": "paper",
        "status": "pending",
        "market_id": "1.1",
        "selection_id": 47999,
        "handicap": 0,
        "side": None,
        "price": None,
        "size": None,
        "params": None,
        "result": None,
        "error": None,
    }
    base.update(kw)
    return base


def _by_id(sb: _FakeSupabase, rid: int) -> Dict[str, Any]:
    return next(r for r in sb.rows if r["id"] == rid)


# ===========================================================================
# Scenari
# ===========================================================================
def test_greenup_back_led_places_lay_at_best_lay():
    """W>L (10 vs −5) → LAY a best available-to-lay (3.0), size (W−L)/p = 5.00."""
    sb = _FakeSupabase([_greenup_row(1)])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    fl = _FakeFlumine({"1.1": market})

    n = wk._process_once(sb, fl, strategy=_STRAT)

    assert n == 1
    assert [c[0] for c in market.calls] == ["place_order"]
    placed = market.calls[0][1]
    assert placed.side == "LAY"
    assert placed.order_type.price == 3.0
    assert placed.order_type.size == pytest.approx(5.0, abs=1e-9)
    assert market.calls[0][2].get("customer_strategy_ref") == wk.CUSTOMER_STRATEGY_REF
    row = _by_id(sb, 1)
    assert row["status"] == "done"
    assert row["result"]["ok"] is True
    assert row["result"]["action"] == "greenup"
    assert row["result"]["side"] == "lay"
    assert row["result"]["size"] == pytest.approx(5.0, abs=1e-9)
    # esposizioni lette dal blotter (autoritative) col lookup corretto
    assert market.blotter.lookups == [("1.1", 47999, 0.0)]


def test_greenup_lay_led_places_back_at_best_back():
    """L>W (6 vs −8) → BACK a best available-to-back (4.0), size (L−W)/p = 3.50."""
    sb = _FakeSupabase([_greenup_row(1)])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": -8.0, "matched_profit_if_lose": 6.0},
        atb=[(4.0, 40)], atl=[(4.1, 30)],
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    placed = market.calls[0][1]
    assert placed.side == "BACK"
    assert placed.order_type.price == 4.0
    assert placed.order_type.size == pytest.approx(3.5, abs=1e-9)
    assert _by_id(sb, 1)["result"]["side"] == "back"


def test_greenup_partial_fraction_halves_size():
    """params.fraction=0.5 → size dimezzata (cash-out parziale)."""
    sb = _FakeSupabase([_greenup_row(1, params={"fraction": 0.5})])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    placed = market.calls[0][1]
    assert placed.order_type.size == pytest.approx(2.5, abs=0.01)  # 5.0/2


def test_greenup_flat_position_is_noop_done():
    """Posizione piatta → riga 'done' SENZA piazzare alcun ordine."""
    sb = _FakeSupabase([_greenup_row(1)])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 3.0, "matched_profit_if_lose": 3.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls == []  # nessun place
    row = _by_id(sb, 1)
    assert row["status"] == "done"
    assert row["result"]["ok"] is True
    assert "piatta" in (row["result"]["detail"] or "")


def test_greenup_without_strategy_errors_not_silent_done():
    """HIGH-2: senza strategy NON possiamo leggere le esposizioni → la riga deve andare in
    'error' (mai un 'done' bugiardo "posizione piatta" con la posizione APERTA)."""
    sb = _FakeSupabase([_greenup_row(1)])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=None)

    assert market.calls == []  # nessun ordine piazzato
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "strategy" in (row["error"] or "").lower()


def test_greenup_no_book_price_with_open_exposure_is_error():
    """Best LAY assente quando serve (W>L, esposizione APERTA) → nessun ordine alla
    cieca E riga 'error' (fix cert PAPER 2026-07-02): un 'done ok=True' qui
    consumerebbe uno stop scattato ("eseguita e verificata") lasciando la posizione
    aperta a sanguinare. L'errore fa scattare il retry del follow-through del risk engine."""
    sb = _FakeSupabase([_greenup_row(1)])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[],  # niente lato lay
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls == []  # mai un ordine alla cieca senza prezzo
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "NON eseguibile" in (row["error"] or "")


# ===========================================================================
# target_price ("greening column") — percorso WORKER end-to-end (review fix)
# ===========================================================================
def test_greenup_target_price_places_at_that_level_ignoring_best():
    """params.target_price=2.5 (W>L) -> LAY esattamente a 2.5, NON al best (3.0)."""
    sb = _FakeSupabase([_greenup_row(1, params={"target_price": 2.5})])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    placed = market.calls[0][1]
    assert placed.side == "LAY"
    assert placed.order_type.price == 2.5           # il livello richiesto, MAI il best
    assert placed.order_type.size == pytest.approx(15.0 / 2.5, abs=1e-9)
    row = _by_id(sb, 1)
    assert row["status"] == "done"
    assert row["result"]["ok"] is True


def test_greenup_target_price_string_jsonb_is_parsed():
    """jsonb numerico-come-stringa: target_price="2.5" -> parse a float, piazza a 2.5."""
    sb = _FakeSupabase([_greenup_row(1, params={"target_price": "2.5"})])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls[0][1].order_type.price == 2.5


def test_greenup_target_price_ignores_place_at_ticks():
    """target_price + place_at_ticks insieme -> vince il target (place_at ignorato)."""
    sb = _FakeSupabase([_greenup_row(1, params={"target_price": 2.5, "place_at_ticks": 3})])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls[0][1].order_type.price == 2.5  # non 2.5+3tick, non best+3tick


def test_greenup_target_price_works_without_best_prices():
    """Book vuoto + target -> si piazza comunque AL target (take-profit resting)."""
    sb = _FakeSupabase([_greenup_row(1, params={"target_price": 2.0})])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[], atl=[],  # nessun best disponibile
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    placed = market.calls[0][1]
    assert placed.side == "LAY"
    assert placed.order_type.price == 2.0
    assert _by_id(sb, 1)["status"] == "done"


@pytest.mark.parametrize("bad", ["abc", "", 0, 1.0, -3, 1001, "NaN"])
def test_greenup_target_price_malformed_is_error_never_best(bad):
    """MONEY-CRITICAL: target malformato -> riga 'error', NESSUN ordine (mai ripiegare
    in silenzio sul best: sarebbe un ordine a un prezzo diverso dal livello cliccato)."""
    sb = _FakeSupabase([_greenup_row(1, params={"target_price": bad})])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    fl = _FakeFlumine({"1.1": market})

    wk._process_once(sb, fl, strategy=_STRAT)

    assert market.calls == []  # nessun place, mai
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "target_price" in (row["error"] or "")


# ---------------------------------------------------------------------------
# FIX audit #25 — params.persistence onorata dall'hedge (default LAPSE invariato)
# ---------------------------------------------------------------------------
def test_greenup_honours_params_persistence():
    """persistence=PERSIST nei params (flatten del risk engine) → l'ordine di hedge
    la porta con sé (prima era HARDCODED LAPSE e la scelta UI veniva ignorata)."""
    sb = _FakeSupabase([_greenup_row(1, params={"persistence": "PERSIST"})])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    wk._process_once(sb, _FakeFlumine({"1.1": market}), strategy=_STRAT)
    placed = market.calls[0][1]
    assert placed.order_type.persistence_type == "PERSIST"
    assert _by_id(sb, 1)["status"] == "done"


def test_greenup_default_persistence_stays_lapse():
    sb = _FakeSupabase([_greenup_row(1)])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    wk._process_once(sb, _FakeFlumine({"1.1": market}), strategy=_STRAT)
    assert market.calls[0][1].order_type.persistence_type == "LAPSE"


def test_greenup_invalid_persistence_is_error_never_silent_default():
    """Valore malformato = errore ESPLICITO della richiesta (mai ripiegare in silenzio
    su un default diverso da quello chiesto)."""
    sb = _FakeSupabase([_greenup_row(1, params={"persistence": "KEEPZ"})])
    market = _FakeMarket(
        "1.1", {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0},
        atb=[(2.98, 60)], atl=[(3.0, 80)],
    )
    wk._process_once(sb, _FakeFlumine({"1.1": market}), strategy=_STRAT)
    assert market.calls == []                       # NESSUN ordine piazzato
    row = _by_id(sb, 1)
    assert row["status"] == "error"
    assert "persistence" in (row["error"] or "")
