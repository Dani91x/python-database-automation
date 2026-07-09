"""Fix 2026-07-09 — TennisFLB, exit ``hybrid``: il residuo INEVASO dell'entry va
cancellato al green. Prima restava resting a quota estrema e poteva riempirsi DOPO
il green parziale, riaprendo esposizione oltre la frazione dichiarata (green_frac).
La parte MATCHED residua resta hold fino al settlement (per design)."""
from __future__ import annotations

from betfairlightweight import filters

from Betfair.stream.tennis_scalper.tennis_flb_bot import OPEN, TennisFLBStrategy


class _Ex:
    def __init__(self, back, lay):
        self.available_to_back = [{"price": back[0], "size": back[1]}] if back else []
        self.available_to_lay = [{"price": lay[0], "size": lay[1]}] if lay else []


class _Runner:
    def __init__(self, sel, back, lay, status="ACTIVE", ltp=None):
        self.selection_id = sel
        self.status = status
        self.last_price_traded = ltp
        self.ex = _Ex(back, lay)


class _Order:
    def __init__(self, sel, side, sm, ap):
        self.selection_id = sel
        self.side = side
        self.size_matched = sm
        self.average_price_matched = ap


class _Blotter:
    def __init__(self):
        self.orders = []

    def strategy_orders(self, _s):
        return self.orders


class _Market:
    def __init__(self):
        self.market_id = "1.1"
        self.blotter = _Blotter()
        self.placed = []
        self.cancelled = []

    def place_order(self, o):
        self.placed.append(o)

    def cancel_order(self, o):
        self.cancelled.append(o)


class _MB:
    def __init__(self, runners, tm=100000.0):
        self.runners = runners
        self.total_matched = tm
        self.status = "OPEN"
        self.market_id = "1.1"


def test_hybrid_green_cancels_unmatched_entry_residual():
    s = TennisFLBStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        flb_params={"exit_mode": "hybrid", "green_ticks": 2, "green_frac": 0.5,
                    "lay_max": 1.10, "min_lay_size": 5.0, "dry_run": False},
    )
    m = _Market()
    # 1) INGRESSO: lay del favorito estremo a 1.05
    s.process_market_book(m, _MB([_Runner(111, (1.04, 200), (1.05, 200), ltp=1.05)]))
    assert len(m.placed) == 1, "entry LAY piazzata"
    entry_order = m.placed[0]
    st = s._pos_state[("1.1", 111)]
    assert st["state"] == OPEN and st["order"] is entry_order

    # 2) fill PARZIALE dell'entry (il resto è ancora resting sul book)
    m.blotter.orders.append(_Order(111, "LAY", 2.0, 1.05))

    # 3) la quota RISALE di >= green_ticks: green PARZIALE (hybrid)
    s.process_market_book(m, _MB([_Runner(111, (1.07, 200), (1.08, 200), ltp=1.07)]))
    assert st["greened"] is True
    assert len(m.placed) == 2, "hedge di green piazzato"
    assert (m.placed[1].side or "").upper() == "BACK"
    # FIX: il residuo INEVASO dell'entry è stato cancellato
    assert entry_order in m.cancelled, "residuo entry cancellato al green (hybrid)"
    # la posizione matched residua resta HOLD (stato ancora OPEN, per design)
    assert s._pos_state[("1.1", 111)]["state"] == OPEN
