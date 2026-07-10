"""Fix 2026-07-10 — timeout entry in SECONDI di publish_time (bug live≠backtest).

Prima i timeout contavano gli UPDATE del book: in live arrivano molti update al
secondo → l'entry veniva cancellata in pochi secondi invece dei 25/40s attesi.
Ora contano i secondi (delta dal piazzamento); il conteggio update resta SOLO
come fallback quando il publish_time manca.
"""
from __future__ import annotations

import types

from betfairlightweight import filters

from Betfair.stream.tennis_scalper.tennis_flb_bot import (
    OPEN as FLB_OPEN,
    TennisFLBStrategy,
)
from Betfair.stream.tennis_scalper.tennis_pro_bot import (
    FLAT,
    OPEN,
    TennisProStrategy,
)
from Betfair.stream.tennis_scalper.tennis_swing_bot import TennisSwingStrategy, _tki


class _Blotter:
    def strategy_orders(self, _s):
        return []


class _Market:
    market_id = "1.1"
    blotter = _Blotter()

    def __init__(self):
        self.cancelled = []

    def place_order(self, o):
        pass

    def cancel_order(self, o):
        self.cancelled.append(o)


def _px(bb=1.90, bl=1.92):
    return {1: {"bb": bb, "bl": bl, "sb": 100.0, "sl": 100.0, "ltp": bb}}


# ------------------------------------------------------------------ tennis_pro
def _make_pro(**p):
    return TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        pro_params={"dry_run": True, **p}, name_to_sel={},
    )


def test_pro_entry_timeout_counts_seconds_not_updates():
    s = _make_pro(entry_timeout_ticks=25)  # retrocompat: 25 → 25 s
    m = _Market()
    trade = {"state": OPEN, "sel": 1, "side": "BACK", "entry": 1.90,
             "target": 1.85, "stop": 2.0, "kind": "x", "staged_done": False,
             "staged_order": None, "order": None, "wait": 0,
             "t_open": 1_000_000, "entry_games": None}
    s._trade["1.1"] = trade
    s._now_pt = 1_000_000 + 5_000        # +5s: tanti update ma pochi secondi
    for _ in range(100):
        s._manage(m, trade, _px())
    assert trade["state"] == OPEN         # 100 update NON bastano piu'
    s._now_pt = 1_000_000 + 26_000        # +26s > 25s → timeout
    s._manage(m, trade, _px())
    assert s._trade["1.1"]["state"] == FLAT


def test_pro_entry_timeout_fallback_on_missing_publish_time():
    s = _make_pro()
    m = _Market()
    trade = {"state": OPEN, "sel": 1, "side": "BACK", "entry": 1.90,
             "target": 1.85, "stop": 2.0, "kind": "x", "staged_done": False,
             "staged_order": None, "order": None, "wait": 0,
             "t_open": None, "entry_games": None}
    s._trade["1.1"] = trade
    s._now_pt = None
    for _ in range(26):                   # fallback: conta gli update
        s._manage(m, trade, _px())
    assert s._trade["1.1"]["state"] == FLAT


# ------------------------------------------------------------------ tennis_flb
def _make_flb(**p):
    return TennisFLBStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        flb_params={"dry_run": True, **p})


def test_flb_entry_timeout_counts_seconds_not_updates():
    s = _make_flb(entry_timeout=40)
    m = _Market()
    key = ("1.1", 1)
    st = {"state": FLB_OPEN, "entry": 1.05, "order": None, "wait": 0,
          "greened": False, "t0": 1_000_000}
    s._pos_state[key] = st
    for _ in range(100):                  # +5s: NON scade nonostante gli update
        s._manage(m, 1, key, st, 1.04, 1.05, 1_000_000 + 5_000)
    assert s._pos_state[key]["state"] == FLB_OPEN
    s._manage(m, 1, key, st, 1.04, 1.05, 1_000_000 + 41_000)  # +41s → timeout
    assert s._pos_state[key]["state"] == "DONE"


# ---------------------------------------------------------------- tennis_swing
def test_swing_entry_wait_counts_seconds_not_updates():
    s = TennisSwingStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        swing_params={"dry_run": True})
    m = _Market()

    class _MB:
        market_id = "1.1"
        status = "OPEN"

        def __init__(self, pt):
            self.publish_time_epoch = pt
            self.runners = [types.SimpleNamespace(
                selection_id=1, status="ACTIVE", last_price_traded=1.90,
                ex=types.SimpleNamespace(
                    available_to_back=[{"price": 1.90, "size": 100}],
                    available_to_lay=[{"price": 1.92, "size": 100}],
                ))]

    tr = {"sel": 1, "side": "BACK", "etk": _tki(1.90), "anchor": _tki(1.88),
          "order": None, "held": 0, "wait": 0, "t0": 1_000}
    s._tr["1.1"] = tr
    for _ in range(100):                  # +5s di publish_time: NON scade
        s.process_market_book(m, _MB(1_000 + 5_000))
    assert "1.1" in s._tr
    s.process_market_book(m, _MB(1_000 + 41_000))  # +41s → entry cancellata
    assert "1.1" not in s._tr
