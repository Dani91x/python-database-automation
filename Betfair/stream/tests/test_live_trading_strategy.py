"""Unit test di `Betfair/stream/engine/live_trading_strategy.py`.

Money-critical: NESSUNA rete, NESSUN login, NESSUN ordine reale. Market, blotter,
ordini e le scritture DB sono MOCK in-memory. In particolare:
  * le ESPOSIZIONI provengono da un blotter fake che imita
    ``flumine.markets.blotter.Blotter.get_exposures`` → verifichiamo che la strategia
    le RIFLETTE senza ricalcolarle a mano;
  * le scritture (``upsert_live_order`` / ``upsert_live_position``) sono catturate da un
    fake DB iniettato via monkeypatch su ``_db`` (nessun supabase importato).

Scenari:
  - process_market_book è NO-OP (nessun ordine, nessuna scrittura);
  - process_orders specchia ordine + posizione con il mapping corretto dei campi;
  - le esposizioni scritte sono ESATTAMENTE quelle del blotter;
  - write-on-change: ordine invariato → nessuna nuova scrittura; cambiato → riscrive;
  - net_position = back matched − lay matched;
  - best-effort: get_exposures che solleva non fa cadere il runner e l'ordine resta specchiato;
  - lista ordini vuota → no-op.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.engine.live_trading_strategy as strat


# ---------------------------------------------------------------------------
# Fake DB (cattura le scritture)
# ---------------------------------------------------------------------------
class _FakeDB:
    def __init__(self) -> None:
        self.orders: List[Dict[str, Any]] = []
        self.positions: List[Dict[str, Any]] = []
        self.settled: List[Dict[str, Any]] = []

    def upsert_live_order(self, row: Dict[str, Any]) -> None:
        self.orders.append(dict(row))

    def upsert_live_position(self, row: Dict[str, Any]) -> None:
        self.positions.append(dict(row))

    def upsert_live_settled(self, row: Dict[str, Any]) -> None:
        self.settled.append(dict(row))


# ---------------------------------------------------------------------------
# Fake flumine: Market + blotter + ordini
# ---------------------------------------------------------------------------
_DEFAULT_EXPOSURES = {
    "matched_profit_if_win": 50.0,
    "matched_profit_if_lose": -10.0,
    "worst_potential_unmatched_profit_if_win": -20.0,
    "worst_potential_unmatched_profit_if_lose": -5.0,
    "worst_possible_profit_on_win": 30.0,
    "worst_possible_profit_on_lose": -15.0,
}


class _FakeBlotter:
    def __init__(
        self,
        exposures: Optional[Dict[str, float]] = None,
        sel_exposure: float = 15.0,
        sel_orders: Optional[List[Any]] = None,
        raise_on_exposures: bool = False,
    ) -> None:
        self._exposures = dict(exposures if exposures is not None else _DEFAULT_EXPOSURES)
        self._sel_exposure = sel_exposure
        self._sel_orders = sel_orders or []
        self._raise = raise_on_exposures
        self.exposure_calls: List[tuple] = []

    def get_exposures(self, strategy: Any, lookup: tuple) -> Dict[str, float]:
        self.exposure_calls.append(lookup)
        if self._raise:
            raise RuntimeError("blotter boom")
        return dict(self._exposures)

    def selection_exposure(self, strategy: Any, lookup: tuple) -> float:
        return self._sel_exposure

    def strategy_selection_orders(
        self, strategy: Any, selection_id: int, handicap: float = 0, matched_only: Any = None
    ) -> list:
        return list(self._sel_orders)

    def strategy_orders(self, strategy: Any) -> list:
        return list(getattr(self, "_strategy_orders", []))


def _fake_market(market_id: str = "1.1", event_id: str = "31.999", blotter: Any = None) -> Any:
    return SimpleNamespace(
        market_id=market_id,
        event_id=event_id,
        blotter=blotter if blotter is not None else _FakeBlotter(),
    )


def _fake_order(
    *,
    oid: str = "OID-1",
    bet_id: Optional[str] = "B1",
    market_id: str = "1.1",
    selection_id: int = 47999,
    handicap: float = 0.0,
    side: str = "BACK",
    status: str = "EXECUTABLE",
    order_type: str = "LIMIT",
    price: float = 3.0,
    size: float = 5.0,
    size_matched: float = 2.0,
    size_remaining: float = 3.0,
    size_cancelled: float = 0.0,
    size_lapsed: float = 0.0,
    size_voided: float = 0.0,
    average_price_matched: float = 3.0,
    customer_order_ref: str = "awlq42",
    persistence_type: str = "LAPSE",
    placed: str = "2026-06-30T10:00:00+00:00",
) -> Any:
    ot = SimpleNamespace(
        ORDER_TYPE=SimpleNamespace(name=order_type),
        price=price,
        size=size,
        persistence_type=persistence_type,
    )
    return SimpleNamespace(
        id=oid,
        bet_id=bet_id,
        market_id=market_id,
        selection_id=selection_id,
        handicap=handicap,
        side=side,
        status=SimpleNamespace(name=status),
        order_type=ot,
        size_matched=size_matched,
        size_remaining=size_remaining,
        size_cancelled=size_cancelled,
        size_lapsed=size_lapsed,
        size_voided=size_voided,
        average_price_matched=average_price_matched,
        customer_order_ref=customer_order_ref,
        responses=SimpleNamespace(date_time_placed=placed),
        date_time_status_update="2026-06-30T10:05:00+00:00",
    )


@pytest.fixture
def fake_db(monkeypatch) -> _FakeDB:
    db = _FakeDB()
    monkeypatch.setattr(strat, "_db", lambda: db)
    return db


def _make_strategy(mode: str = "paper") -> strat.LiveTradingStrategy:
    return strat.LiveTradingStrategy(market_filter={"marketIds": ["1.1"]}, session=None, mode=mode)


# ===========================================================================
# NO auto-trading
# ===========================================================================
def test_process_market_book_is_noop(monkeypatch):
    # _db NON deve mai essere chiamato dalla logica di mercato.
    def _boom():
        raise AssertionError("process_market_book non deve scrivere nel DB")

    monkeypatch.setattr(strat, "_db", _boom)
    s = _make_strategy()
    s.process_market_book(_fake_market(), SimpleNamespace())  # nessuna eccezione


def test_check_market_book_false():
    s = _make_strategy()
    assert s.check_market_book(_fake_market(), SimpleNamespace()) is False


def test_empty_orders_noop(fake_db):
    s = _make_strategy()
    s.process_orders(_fake_market(), [])
    assert fake_db.orders == []
    assert fake_db.positions == []


# ===========================================================================
# Specchio ordine
# ===========================================================================
def test_process_orders_mirrors_order_fields(fake_db):
    s = _make_strategy(mode="paper")
    market = _fake_market(market_id="1.1", event_id="31.999")
    order = _fake_order(side="BACK", status="EXECUTABLE", customer_order_ref="awlq42")

    s.process_orders(market, [order])

    assert len(fake_db.orders) == 1
    row = fake_db.orders[0]
    assert row["bet_id"] == "B1"
    assert row["client_order_ref"] == "awlq42"
    assert row["request_id"] == 42          # estratto da awlq<id>
    assert row["mode"] == "paper"
    assert row["event_id"] == "31.999"
    assert row["market_id"] == "1.1"
    assert row["selection_id"] == 47999
    assert row["side"] == "back"            # lower-case
    assert row["order_type"] == "LIMIT"
    assert row["price"] == 3.0
    assert row["size"] == 5.0
    assert row["size_matched"] == 2.0
    assert row["size_remaining"] == 3.0
    assert row["average_price_matched"] == 3.0
    assert row["status"] == "EXECUTABLE"
    assert row["persistence"] == "LAPSE"
    assert row["placed_at"] == "2026-06-30T10:00:00+00:00"
    assert row["matched_at"] == "2026-06-30T10:05:00+00:00"  # size_matched>0


def test_mirror_reads_client_ref_from_context_not_flumine_attr(fake_db):
    """Produzione: l'attributo flumine ``order.customer_order_ref`` è name_hash+id, NON il
    nostro ref. Lo specchio deve leggere awlq<id> da ``order.context`` (salvato da
    build_order) → request_id corretto. Qui il customer_order_ref attr è un ref flumine
    fittizio diverso, ma il context ha il vero awlq77."""
    s = _make_strategy(mode="paper")
    order = _fake_order(customer_order_ref="ab12x9,deadbeef-uuid")  # ref flumine (NON awlq)
    order.context = {"customer_order_ref": "awlq77"}

    s.process_orders(_fake_market(), [order])

    row = fake_db.orders[0]
    assert row["client_order_ref"] == "awlq77"
    assert row["request_id"] == 77


def test_pending_order_has_null_betid_and_matched_at(fake_db):
    s = _make_strategy()
    order = _fake_order(bet_id=None, status="PENDING", size_matched=0.0, size_remaining=5.0)
    s.process_orders(_fake_market(), [order])
    row = fake_db.orders[0]
    assert row["bet_id"] is None
    assert row["matched_at"] is None
    assert row["size_matched"] == 0.0


# ===========================================================================
# Specchio posizione: esposizioni SEMPRE da blotter.get_exposures (no ricalcolo)
# ===========================================================================
def test_position_uses_blotter_exposures(fake_db):
    s = _make_strategy(mode="live")
    blotter = _FakeBlotter()
    market = _fake_market(market_id="1.1", event_id="31.999", blotter=blotter)
    order = _fake_order(selection_id=47999, handicap=0.0)

    s.process_orders(market, [order])

    assert len(fake_db.positions) == 1
    pos = fake_db.positions[0]
    assert pos["mode"] == "live"
    assert pos["market_id"] == "1.1"
    assert pos["selection_id"] == 47999
    assert pos["handicap"] == 0.0
    # mappatura ESATTA delle chiavi flumine
    assert pos["matched_if_win"] == 50.0
    assert pos["matched_if_lose"] == -10.0
    assert pos["worst_if_win"] == 30.0
    assert pos["worst_if_lose"] == -15.0
    assert pos["selection_exposure"] == 15.0
    assert pos["unmatched_lay_exposure"] == -20.0   # worst_potential_unmatched_profit_if_win
    assert pos["unmatched_back_exposure"] == -5.0   # worst_potential_unmatched_profit_if_lose
    # lookup passato a get_exposures = (market_id, selection_id, handicap)
    assert blotter.exposure_calls == [("1.1", 47999, 0.0)]


def test_net_position_back_minus_lay(fake_db):
    sel_orders = [
        _fake_order(oid="A", side="BACK", size_matched=5.0),
        _fake_order(oid="B", side="LAY", size_matched=2.0),
    ]
    blotter = _FakeBlotter(sel_orders=sel_orders)
    market = _fake_market(blotter=blotter)
    s = _make_strategy()

    s.process_orders(market, [_fake_order(oid="A", side="BACK", size_matched=5.0)])

    assert fake_db.positions[0]["net_position"] == 3.0  # 5 back − 2 lay


def test_one_position_per_touched_selection(fake_db):
    # due ordini sulla STESSA selezione → una sola riga posizione
    blotter = _FakeBlotter()
    market = _fake_market(blotter=blotter)
    s = _make_strategy()
    o1 = _fake_order(oid="A", bet_id="B1", selection_id=100)
    o2 = _fake_order(oid="B", bet_id="B2", selection_id=100)

    s.process_orders(market, [o1, o2])

    assert len(fake_db.orders) == 2
    assert len(fake_db.positions) == 1
    assert fake_db.positions[0]["selection_id"] == 100


# ===========================================================================
# write-on-change
# ===========================================================================
def test_write_on_change_skips_unchanged(fake_db):
    s = _make_strategy()
    market = _fake_market()
    order = _fake_order(oid="OID-1")

    s.process_orders(market, [order])
    assert len(fake_db.orders) == 1
    assert len(fake_db.positions) == 1

    # stessa identica firma → nessuna nuova scrittura
    s.process_orders(market, [_fake_order(oid="OID-1")])
    assert len(fake_db.orders) == 1
    assert len(fake_db.positions) == 1


def test_write_on_change_rewrites_on_fill(fake_db):
    s = _make_strategy()
    market = _fake_market()
    s.process_orders(market, [_fake_order(oid="OID-1", size_matched=2.0, size_remaining=3.0)])
    assert len(fake_db.orders) == 1

    # size_matched cambia (fill) → riscrive ordine e ricalcola posizione
    s.process_orders(market, [_fake_order(oid="OID-1", size_matched=5.0, size_remaining=0.0,
                                          status="EXECUTION_COMPLETE")])
    assert len(fake_db.orders) == 2
    assert fake_db.orders[-1]["status"] == "EXECUTION_COMPLETE"
    assert fake_db.orders[-1]["size_matched"] == 5.0


# ===========================================================================
# best-effort (mai far cadere il runner)
# ===========================================================================
def test_exposures_failure_does_not_crash_and_order_is_mirrored(fake_db):
    blotter = _FakeBlotter(raise_on_exposures=True)
    market = _fake_market(blotter=blotter)
    s = _make_strategy()

    s.process_orders(market, [_fake_order()])  # non deve sollevare

    # l'ordine è stato comunque specchiato; la posizione no (esposizione KO)
    assert len(fake_db.orders) == 1
    assert fake_db.positions == []


def test_missing_blotter_skips_position(fake_db):
    market = SimpleNamespace(market_id="1.1", event_id="31.999", blotter=None)
    s = _make_strategy()
    s.process_orders(market, [_fake_order()])
    assert len(fake_db.orders) == 1
    assert fake_db.positions == []


# ===========================================================================
# LOW-3: cleanup cache write-on-change per ordini in stato terminale
# ===========================================================================
@pytest.mark.parametrize(
    "terminal_status", ["EXECUTION_COMPLETE", "EXPIRED", "LAPSED", "VIOLATION"]
)
def test_terminal_order_removed_from_signature_cache(fake_db, terminal_status):
    """Un ordine in stato terminale è specchiato UNA volta poi rimosso dalla cache
    delle firme: il dict non cresce illimitatamente accumulando ordini chiusi."""
    s = _make_strategy()
    market = _fake_market()
    order = _fake_order(oid="OID-T", status=terminal_status)

    s.process_orders(market, [order])

    assert len(fake_db.orders) == 1                 # specchiato comunque
    assert "OID-T" not in s._last_order_sig         # ma non trattenuto in cache


def test_non_terminal_order_kept_in_signature_cache(fake_db):
    """Un ordine ancora vivo (EXECUTABLE) resta in cache per il write-on-change."""
    s = _make_strategy()
    order = _fake_order(oid="OID-L", status="EXECUTABLE")
    s.process_orders(_fake_market(), [order])
    assert "OID-L" in s._last_order_sig


def test_cache_shrinks_when_live_order_becomes_terminal(fake_db):
    """EXECUTABLE (in cache) → EXECUTION_COMPLETE: la firma viene rimossa, lasciando
    il dict limitato ai soli ordini ancora vivi."""
    s = _make_strategy()
    market = _fake_market()

    s.process_orders(market, [_fake_order(oid="OID-1", status="EXECUTABLE",
                                          size_matched=2.0, size_remaining=3.0)])
    assert "OID-1" in s._last_order_sig

    # transizione a terminale → riflesso una volta e poi rimosso dalla cache
    s.process_orders(market, [_fake_order(oid="OID-1", status="EXECUTION_COMPLETE",
                                          size_matched=5.0, size_remaining=0.0)])
    assert len(fake_db.orders) == 2                 # la transizione è stata scritta
    assert "OID-1" not in s._last_order_sig         # cache ripulita
    assert s._last_order_sig == {}


# ===========================================================================
# E34/D33 — settled PAPER alla chiusura del mercato (process_closed_market)
# ===========================================================================
def _sim_order(profit: float) -> Any:
    return SimpleNamespace(simulated=SimpleNamespace(profit=profit))


def test_closed_market_paper_writes_settled(fake_db):
    s = _make_strategy(mode="paper")
    blotter = _FakeBlotter()
    blotter._strategy_orders = [_sim_order(-12.5), _sim_order(4.0)]
    market = _fake_market(market_id="1.77", event_id="31.5", blotter=blotter)
    s.process_closed_market(market, SimpleNamespace())
    assert len(fake_db.settled) == 1
    row = fake_db.settled[0]
    assert row["mode"] == "paper"
    assert row["market_id"] == "1.77"
    assert row["event_id"] == "31.5"
    assert row["profit"] == pytest.approx(-8.5)
    assert row["orders"] == 2
    assert row["source"] == "simulated"


def test_closed_market_live_mode_is_noop(fake_db):
    # LIVE: il realizzato arriva dai cleared orders Betfair, MAI dal simulato.
    s = _make_strategy(mode="live")
    blotter = _FakeBlotter()
    blotter._strategy_orders = [_sim_order(99.0)]
    s.process_closed_market(_fake_market(blotter=blotter), SimpleNamespace())
    assert fake_db.settled == []


def test_closed_market_no_orders_no_row(fake_db):
    s = _make_strategy(mode="paper")
    s.process_closed_market(_fake_market(blotter=_FakeBlotter()), SimpleNamespace())
    assert fake_db.settled == []


def test_closed_market_zero_profit_still_written(fake_db):
    # profitto 0 con ordini presenti → riga scritta (0 è un risultato, non "niente")
    s = _make_strategy(mode="paper")
    blotter = _FakeBlotter()
    blotter._strategy_orders = [_sim_order(0.0)]
    s.process_closed_market(_fake_market(blotter=blotter), SimpleNamespace())
    assert len(fake_db.settled) == 1
    assert fake_db.settled[0]["profit"] == pytest.approx(0.0)


def test_closed_market_settled_errors_never_propagate(fake_db, monkeypatch):
    s = _make_strategy(mode="paper")
    blotter = _FakeBlotter()
    blotter._strategy_orders = [_sim_order(1.0)]

    def _boom(row):
        raise RuntimeError("db KO")

    monkeypatch.setattr(fake_db, "upsert_live_settled", _boom)
    # non deve sollevare (best-effort: il runner resta in piedi)
    s.process_closed_market(_fake_market(blotter=blotter), SimpleNamespace())
