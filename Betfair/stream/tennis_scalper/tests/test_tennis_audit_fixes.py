"""Fix AUDIT 2026-07-16 — bot tennis (scalper/pro/swing/flb), money-critical.

Coprono i finding verificati in lettura del 16/07:
  #5  _has_live/_cancel_if_live includono CANCELLING/UPDATING/REPLACING (un cancel
      inviato ma NON confermato non e' un ordine morto: fill tardivo = gamba nuda);
  #6  contabilita' INCREMENTALE del ciclo (slot.booked): un ciclo che riapre il
      flatten (fill orfano post-DONE) non ri-somma il P&L gia' contabilizzato,
      ne' riconta slot.cycles;
  #12 chiusura scalp: locked = min(nw, nl) (floor garantito), mai il solo nl;
  #7  tennis_pro: stato CLOSING sorvegliato dopo il green/stop finale — FLAT solo
      a blotter pari, re-hedge se la chiusura non riempie;
  #10 tennis_swing: escalation della chiusura in SECONDI di publish_time;
  #11 tennis_flb: green_est esatto con frac<1 (prima sovrastimava ~2x);
  #13 tennis_pro: cognome CONDIVISO dai due runner = ambiguo, NON indicizzato.
"""
from __future__ import annotations

import types

import pytest
from betfairlightweight import filters
from flumine.order.order import OrderStatus

from Betfair.stream.tennis_scalper.tennis_flb_bot import TennisFLBStrategy
from Betfair.stream.tennis_scalper.tennis_pro_bot import (
    CLOSING,
    FLAT,
    OPEN,
    TennisProStrategy,
)
from Betfair.stream.tennis_scalper.tennis_scalper_bot import (
    DONE,
    FLATTENING,
    LOCKING,
    TennisScalperStrategy,
    _Slot,
    compute_green,
)
from Betfair.stream.tennis_scalper.tennis_swing_bot import TennisSwingStrategy


# ---------------------------------------------------------------------------
# fake flumine (stesso stile di test_tennis_mission)
# ---------------------------------------------------------------------------
class _Market:
    market_id = "1.1"

    def __init__(self, blotter=None):
        self.placed = []
        self.cancelled = []
        self.blotter = blotter

    def place_order(self, o):
        self.placed.append(o)

    def cancel_order(self, o):
        self.cancelled.append(o)


def _order(side="BACK", price=1.90, sel=1, matched=0.0, avg=0.0,
           remaining=2.0, status=OrderStatus.EXECUTABLE):
    return types.SimpleNamespace(
        status=status, size_remaining=remaining, size_matched=matched,
        average_price_matched=avg, side=side, selection_id=sel,
        order_type=types.SimpleNamespace(price=price, size=2.0),
    )


def _make_scalper(**params):
    return TennisScalperStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        scalper_params={"stake": 2.0, **params},
    )


# ---------------------------------------------------------------------------
# #5 — CANCELLING/UPDATING/REPLACING sono ordini ancora VIVI
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", [
    OrderStatus.PENDING, OrderStatus.EXECUTABLE, OrderStatus.CANCELLING,
    OrderStatus.UPDATING, OrderStatus.REPLACING,
])
def test_has_live_includes_transitional_statuses(status):
    o = _order(status=status, remaining=2.0)
    assert TennisScalperStrategy._has_live(o) is True


def test_has_live_false_on_terminal_or_no_residual():
    assert TennisScalperStrategy._has_live(None) is False
    assert TennisScalperStrategy._has_live(
        _order(status=OrderStatus.EXECUTION_COMPLETE, remaining=0.0)) is False
    assert TennisScalperStrategy._has_live(
        _order(status=OrderStatus.CANCELLING, remaining=0.0)) is False


def test_cancel_if_live_retries_on_cancelling():
    """Un ordine in CANCELLING con residuo va RI-cancellato (retry idempotente),
    non considerato morto: prima il fix lo slot veniva resettato e un fill
    tardivo diventava una posizione nuda non gestita."""
    m = _Market()
    o = _order(status=OrderStatus.CANCELLING, remaining=2.0)
    TennisScalperStrategy._cancel_if_live(m, o)
    assert o in m.cancelled


# ---------------------------------------------------------------------------
# #12 — chiusura scalp: locked = min(nw, nl), mai il solo nl
# ---------------------------------------------------------------------------
def test_scalp_close_books_min_of_outcomes():
    s = _make_scalper()
    slot = s._slot("1.1", 1)
    slot.status = LOCKING
    # entry BACK 2 @ 2.00 tutta matchata; close LAY 2.11 @ 1.90 tutta matchata
    slot.entry = _order("BACK", 2.00, matched=2.0, avg=2.00, remaining=0.0,
                        status=OrderStatus.EXECUTION_COMPLETE)
    slot.entry_side = "BACK"
    slot.close = _order("LAY", 1.90, matched=2.11, avg=1.90, remaining=0.0,
                        status=OrderStatus.EXECUTION_COMPLETE)
    nw, nl = s._net_position(slot)
    assert abs(nw - nl) <= 0.02          # roundtrip equalizzato (entro tolleranza)
    s._manage(_Market(), None, None, slot, now=0, best_back=None, best_lay=None,
              size_back=None, size_lay=None)
    assert slot.status == DONE
    # floor garantito = min dei due esiti (qui nw < nl), MAI il solo nl
    assert s.stats["pnl_locked"] == pytest.approx(min(nw, nl))
    assert min(nw, nl) < nl              # il vecchio bug avrebbe scritto nl


# ---------------------------------------------------------------------------
# #6 — booking incrementale: close + riapertura flatten = P&L contato UNA volta
# ---------------------------------------------------------------------------
def test_reopened_flatten_books_only_the_delta():
    s = _make_scalper()
    slot = s._slot("1.1", 1)
    m = _Market()
    # 1) prima chiusura: flatten pulito con locked 0.10
    s._net_position = lambda sl: (0.10, 0.10)  # type: ignore[assignment]
    slot.status = LOCKING
    s._begin_flatten(slot)
    s._drive_flatten(m, slot, best_back=None, best_lay=None, now=0)
    assert slot.status == DONE
    assert s.stats["pnl_locked"] == pytest.approx(0.10)
    assert slot.cycles == 1
    # 2) fill ORFANO: il ciclo riapre e ri-chiude a -0.05 → si accredita SOLO la
    #    correzione (-0.15), il totale contabilizzato = locked finale UNA volta
    s._net_position = lambda sl: (-0.05, -0.05)  # type: ignore[assignment]
    s._begin_flatten(slot)
    s._drive_flatten(m, slot, best_back=None, best_lay=None, now=0)
    assert slot.status == DONE
    assert s.stats["pnl_locked"] == pytest.approx(-0.05)   # NON 0.10 + (-0.05)
    assert slot.cycles == 1                                # niente doppio ciclo
    # la contabilita' di FASE segue lo stesso delta (missione onesta)
    assert s.stats["pnl_prematch"] == pytest.approx(-0.05)


def test_reset_clears_cycle_accounting():
    s = _make_scalper()
    slot = s._slot("1.1", 1)
    slot.booked = 0.4
    slot.cycle_counted = True
    s._reset(slot)
    assert slot.booked == 0.0
    assert slot.cycle_counted is False


# ---------------------------------------------------------------------------
# #7 — tennis_pro: CLOSING sorvegliato (mai FLAT col solo hedge piazzato)
# ---------------------------------------------------------------------------
class _ProOrder:
    def __init__(self, sel, side, sm, ap):
        self.selection_id = sel
        self.side = side
        self.size_matched = sm
        self.average_price_matched = ap


class _ProBlotter:
    def __init__(self, orders=None):
        self.orders = orders or []

    def strategy_orders(self, _s):
        return self.orders


class _ProMarket(_Market):
    def __init__(self, blotter=None):
        super().__init__(blotter=blotter or _ProBlotter())


class _ProMB:
    def __init__(self, runners, pt=None):
        self.runners = runners
        self.total_matched = 200000.0
        self.status = "OPEN"
        self.market_id = "1.1"
        self.inplay = True
        self.publish_time_epoch = pt


class _ProEx:
    def __init__(self, back, lay):
        self.available_to_back = [{"price": back[0], "size": back[1]}] if back else []
        self.available_to_lay = [{"price": lay[0], "size": lay[1]}] if lay else []


class _ProRunner:
    def __init__(self, sel, back, lay):
        self.selection_id = sel
        self.status = "ACTIVE"
        self.last_price_traded = None
        self.ex = _ProEx(back, lay)


def _make_pro(**p):
    return TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        pro_params={"dry_run": False, **p},
        name_to_sel={},
    )


def _pro_open_trade(entry=1.80):
    from flumine.utils import price_ticks_away
    return {
        "state": OPEN, "sel": 111, "side": "BACK", "entry": entry,
        "target": price_ticks_away(entry, -4), "stop": price_ticks_away(entry, 3),
        "kind": "break_point", "staged_done": False, "staged_order": None,
        "order": None, "wait": 0, "entry_games": None,
    }


def test_pro_final_close_enters_closing_not_flat():
    s = _make_pro()
    m = _ProMarket(_ProBlotter([_ProOrder(111, "BACK", 2.0, 1.80)]))
    s._trade["1.1"] = _pro_open_trade()
    # target raggiunto: green totale → hedge piazzato, posizione NON ancora pari
    mb = _ProMB([_ProRunner(111, (1.74, 100), (1.75, 100))], pt=1_000_000)
    s.process_market_book(m, mb)
    tr = s._trade["1.1"]
    assert tr["state"] == CLOSING          # mai FLAT col solo hedge piazzato
    assert tr["close_order"] is not None
    assert s.stats["greens"] == 1


def test_pro_closing_goes_flat_when_blotter_is_even():
    s = _make_pro()
    # blotter PARI: BACK 2 @ 1.80 + LAY 2.06 @ 1.75 → |nw−nl| < 0.02
    blot = _ProBlotter([_ProOrder(111, "BACK", 2.0, 1.80),
                        _ProOrder(111, "LAY", 2.06, 1.75)])
    m = _ProMarket(blot)
    hedge = object()
    s._trade["1.1"] = {"state": CLOSING, "sel": 111, "side": "BACK",
                       "kind": "break_point", "order": None, "staged_order": None,
                       "close_order": hedge, "t_close": 1_000_000, "close_wait": 0}
    mb = _ProMB([_ProRunner(111, (1.74, 100), (1.75, 100))], pt=1_001_000)
    s.process_market_book(m, mb)
    assert s._trade["1.1"] == {"state": FLAT}
    assert hedge in m.cancelled            # residuo hedge ritirato (no rovescio)


def test_pro_closing_rehedges_after_timeout():
    s = _make_pro(close_retry_s=20.0)
    # posizione ancora SBILANCIATA (solo l'entry matchata: hedge mai riempito)
    m = _ProMarket(_ProBlotter([_ProOrder(111, "BACK", 2.0, 1.80)]))
    stale = object()
    s._trade["1.1"] = {"state": CLOSING, "sel": 111, "side": "BACK",
                       "kind": "break_point", "order": None, "staged_order": None,
                       "close_order": stale, "t_close": 1_000_000, "close_wait": 0}
    # +5s: NESSUNA escalation (si lascia lavorare la chiusura in coda)
    s.process_market_book(m, _ProMB([_ProRunner(111, (1.74, 100), (1.75, 100))],
                                    pt=1_005_000))
    assert s._trade["1.1"]["close_order"] is stale
    assert m.placed == []
    # +21s: hedge stantio cancellato e RI-hedge al touch (posizione mai abbandonata)
    s.process_market_book(m, _ProMB([_ProRunner(111, (1.74, 100), (1.75, 100))],
                                    pt=1_021_000))
    assert stale in m.cancelled
    assert len(m.placed) == 1
    assert s._trade["1.1"]["state"] == CLOSING


# ---------------------------------------------------------------------------
# #13 — tennis_pro: cognome condiviso = ambiguo, NON indicizzato
# ---------------------------------------------------------------------------
def test_pro_ambiguous_surname_not_indexed():
    s = TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        pro_params={},
        name_to_sel={"Karolina Pliskova": 1, "Kristyna Pliskova": 2},
    )
    assert "pliskova" not in s.name_to_sel      # ambiguo: mai indicizzato
    assert s._lookup_sel("Karolina Pliskova") == 1
    assert s._lookup_sel("Pliskova") is None    # cognome solo → nessun azzardo


def test_pro_unique_surname_still_indexed():
    s = TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        pro_params={},
        name_to_sel={"Ar Fery": 1, "Al Zverev": 2},
    )
    assert s._lookup_sel("Arthur Fery") == 1    # match per cognome (univoco)
    assert s._lookup_sel("Alexander Zverev") == 2


# ---------------------------------------------------------------------------
# #10 — tennis_swing: escalation della chiusura in SECONDI di publish_time
# ---------------------------------------------------------------------------
class _SwingBlotter(_ProBlotter):
    pass


def _make_swing(**p):
    return TennisSwingStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        swing_params={"dry_run": False, **p},
    )


def _swing_mb(pt):
    return _ProMB([_ProRunner(7, (1.90, 100), (1.92, 100))], pt=pt)


def test_swing_close_escalates_on_seconds_not_updates():
    s = _make_swing(close_retry_s=20.0, close_retry_ticks=3)
    m = _ProMarket(_SwingBlotter([_ProOrder(7, "BACK", 2.0, 1.90)]))
    stale = object()
    s._tr["1.1"] = {"sel": 7, "side": "BACK", "closing": True,
                    "close_order": stale, "close_wait": 0, "t_close": 1_000_000,
                    "order": None, "etk": 0, "anchor": 0}
    # 5 update fitti in 4s (in live sono molti al secondo): NIENTE escalation
    # anche oltre close_retry_ticks (il fallback conta solo senza publish_time)
    for i in range(5):
        s.process_market_book(m, _swing_mb(1_000_000 + (i + 1) * 800))
    assert s._tr["1.1"]["close_order"] is stale
    assert m.placed == []
    # +21s di publish_time → escalation TAKER al touch
    s.process_market_book(m, _swing_mb(1_021_000))
    assert stale in m.cancelled
    assert len(m.placed) == 1


def test_swing_close_escalation_falls_back_to_updates_without_pt():
    s = _make_swing(close_retry_s=20.0, close_retry_ticks=3)
    m = _ProMarket(_SwingBlotter([_ProOrder(7, "BACK", 2.0, 1.90)]))
    stale = object()
    s._tr["1.1"] = {"sel": 7, "side": "BACK", "closing": True,
                    "close_order": stale, "close_wait": 0,
                    "order": None, "etk": 0, "anchor": 0}
    for _ in range(4):                      # publish_time assente → conta update
        s.process_market_book(m, _swing_mb(None))
    assert stale in m.cancelled             # oltre close_retry_ticks=3
    assert len(m.placed) == 1


# ---------------------------------------------------------------------------
# #11 — tennis_flb: green_est esatto con frac < 1
# ---------------------------------------------------------------------------
def _make_flb(**p):
    return TennisFLBStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        flb_params={"dry_run": False, **p},
    )


def test_flb_green_est_exact_with_partial_fraction():
    # posizione: LAY 2 @ 1.05 → nw = -0.10, nl = +2.00 ; green a 1.20
    blot = _ProBlotter([_ProOrder(5, "LAY", 2.0, 1.05)])
    m = _ProMarket(blot)
    s = _make_flb()
    nw, nl = -0.10, 2.00
    gside, gsize, locked_full = compute_green(nw, nl, 1.20)
    assert gside == "BACK"
    # frac=1: stima invariata (= locked del green totale)
    est_full, _ = s._green(m, 5, 1.20, 1.0)
    assert est_full == pytest.approx(locked_full, abs=1e-9)
    # frac=0.5: floor REALE dopo l'hedge parziale = min(nw', nl'), non locked_full
    est_half, _ = s._green(m, 5, 1.20, 0.5)
    size = gsize * 0.5
    nw2, nl2 = nw + size * 0.20, nl - size
    assert est_half == pytest.approx(min(nw2, nl2), abs=1e-9)
    assert est_half < locked_full            # il vecchio bug sovrastimava ~2x
