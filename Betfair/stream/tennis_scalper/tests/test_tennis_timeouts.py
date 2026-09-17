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
    CLOSING,
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
        # IL FINTO PARLA COME IL VERO (catalogo §7 difetto 27):
        # `Market.place_order` ritorna un BOOL (`market.py:84-98`).
        return True

    def cancel_order(self, o):
        self.cancelled.append(o)
        return True


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
    # ⚠️ NON si dichiara FLAT dopo un cancel non verificato (correzione 17/09):
    # l'ingresso puo' riempirsi DOPO e restare orfano (misurato: 3,52 EUR su
    # 35790089). Si passa in CLOSING, e FLAT arriva solo a blotter pari.
    assert s._trade["1.1"]["state"] == CLOSING
    # il blotter dice che non c'e' niente abbinato: il giro dopo e' FLAT
    s._surveil_closing(m, s._trade["1.1"], _px())
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
    # come sopra: prima CLOSING, poi FLAT a blotter verificato pari
    assert s._trade["1.1"]["state"] == CLOSING
    s._surveil_closing(m, s._trade["1.1"], _px())
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
    # ⚠️ IL CANCEL E' ASINCRONO (correzione 17/09): l'ordine passa per
    # `Cancelling` prima di morire e in quella finestra puo' ancora riempirsi.
    # Prima si dichiarava DONE subito e restava un ordine VIVO sotto una
    # posizione «chiusa» (misurato: K6 su 35790089). Ora si aspetta la conferma.
    assert s._pos_state[key]["state"] == "PENDING"
    # qui l'ordine e' None (nessun ordine vivo): il giro dopo e' DONE
    s._manage(m, 1, key, st, 1.04, 1.05, 1_000_000 + 42_000)
    assert s._pos_state[key]["state"] == "DONE"


# ---------------------------------------------------------------- tennis_swing
def test_swing_entry_wait_counts_seconds_not_updates():
    # modo REALE (16/07): il ramo "entry non riempita" esiste solo con ordini
    # veri — in dry la posizione e' fillata VIRTUALMENTE subito (paper con
    # esito), quindi la regressione secondi-vs-update si testa su dry_run=False
    s = TennisSwingStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        swing_params={"dry_run": False})
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
    assert not tr.get("closing"), "dentro i 40s l'ingresso e' ancora in attesa"
    s.process_market_book(m, _MB(1_000 + 41_000))  # +41s → entry cancellata
    # ⚠️ IL TRADE NON SI DIMENTICA AL TIMEOUT (correzione 17/09). Prima qui si
    # faceva `pop` subito dopo un `cancel` mai verificato: se l'ordine si
    # riempiva DOPO, la posizione restava orfana (misurato: 7,57 EUR abbandonati
    # su 35790089). Ora si passa in CLOSING e si dimentica solo a selezione
    # verificata PARI dal blotter.
    assert "1.1" in s._tr, "il trade resta sorvegliato dopo il timeout"
    assert s._tr["1.1"].get("closing") is True
    # il blotter dice che non c'e' NIENTE abbinato: al giro dopo si dimentica
    s.process_market_book(m, _MB(1_000 + 42_000))
    assert "1.1" not in s._tr, "selezione verificata pari -> trade chiuso"
