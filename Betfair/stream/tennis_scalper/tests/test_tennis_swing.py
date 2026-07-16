"""Test TennisSwingStrategy — fix 2026-07-09.

1. La GESTIONE segue la selezione TRADATA, non il favorito corrente del book
   (bug orfano: flip del favorito a metà trade → posizione abbandonata senza stop).
2. Il time-stop ``tmax`` conta i SECONDI di publish_time, non gli update del book.
3. La chiusura MAKER non riempita ESCALA a taker al touch e il trade viene chiuso
   SOLO a posizione flat (mai hedge orfani).
4. L'ingresso memorizza sel + t0 nel trade.
"""
from __future__ import annotations

from collections import deque

from betfairlightweight import filters

from Betfair.stream.tennis_scalper.tennis_swing_bot import TennisSwingStrategy, _tki


# ---------------- fake flumine (formato dict come lo stream lightweight) ----------
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
    def __init__(self, orders=None):
        self.orders = orders if orders is not None else []

    def strategy_orders(self, _s):
        return self.orders


class _Market:
    def __init__(self, blotter=None):
        self.market_id = "1.1"
        self.blotter = blotter or _Blotter()
        self.placed = []
        self.cancelled = []

    def place_order(self, o):
        self.placed.append(o)

    def cancel_order(self, o):
        self.cancelled.append(o)


class _MB:
    def __init__(self, runners, tm=100000.0, pt=None):
        self.runners = runners
        self.total_matched = tm
        self.status = "OPEN"
        self.market_id = "1.1"
        self.publish_time_epoch = pt


def _make(**p):
    return TennisSwingStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        swing_params={"dry_run": False, **p},
    )


# ---------------------------------------------------------------------------
# 1) FIX ORFANO: gestione sulla selezione TRADATA anche se il favorito flippa
# ---------------------------------------------------------------------------
def test_manages_traded_selection_after_favourite_flip():
    s = _make(stop_ticks=2, maker=False)
    m = _Market(_Blotter([_Order(111, "BACK", 2.0, 1.50)]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(1.50),
                    "anchor": _tki(1.40), "order": None, "held": 0,
                    "wait": 0, "t0": 1_000}
    # 111 è andato CONTRO (quota salita a 2.2x): ora il FAVORITO corrente è 222.
    mb = _MB([_Runner(111, (2.20, 100), (2.24, 100), ltp=2.22),
              _Runner(222, (1.70, 100), (1.72, 100), ltp=1.71)], pt=5_000)
    s.process_market_book(m, mb)
    tr = s._tr.get("1.1")
    assert tr is not None, "il trade NON va scartato con la posizione aperta"
    assert tr.get("closing") is True, "stop scattato sulla selezione tradata"
    assert m.placed, "hedge di chiusura piazzato"
    assert int(m.placed[-1].selection_id) == 111, "hedge sulla selezione TRADATA"


def test_position_never_abandoned_when_favourite_flips():
    """Regressione del bug storico: col favorito flippato la vecchia logica vedeva
    b+l=0 (posizione del NUOVO favorito) e dopo 40 update scartava il trade
    lasciando la posizione su 111 orfana."""
    s = _make(stop_ticks=200, maker=False, tmax=10_000)  # né stop né time-stop
    m = _Market(_Blotter([_Order(111, "BACK", 2.0, 1.50)]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(1.50),
                    "anchor": _tki(1.40), "order": None, "held": 0,
                    "wait": 0, "t0": 1_000}
    mb = _MB([_Runner(111, (1.52, 100), (1.53, 100)),
              _Runner(222, (1.48, 100), (1.49, 100))], pt=2_000)
    for _ in range(50):  # > 40 update: prima del fix il trade veniva scartato
        s.process_market_book(m, mb)
    assert "1.1" in s._tr, "trade ancora gestito (posizione NON orfana)"


# ---------------------------------------------------------------------------
# 2) time-stop in SECONDI (publish_time), non in numero di update
# ---------------------------------------------------------------------------
def test_time_stop_uses_publish_time_seconds_not_update_count():
    s = _make(tmax=90, stop_ticks=50, target_frac=0.5, maker=False)
    m = _Market(_Blotter([_Order(111, "BACK", 2.0, 2.00)]))
    t0 = 1_000_000
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(2.00),
                    "anchor": _tki(1.80), "order": None, "held": 0,
                    "wait": 0, "t0": t0}
    mb_30s = _MB([_Runner(111, (2.00, 100), (2.02, 100))], pt=t0 + 30_000)
    for _ in range(200):  # 200 update in 30s: PRIMA del fix usciva a 90 update
        s.process_market_book(m, mb_30s)
    assert not s._tr["1.1"].get("closing"), "a 30s il time-stop NON deve scattare"
    mb_91s = _MB([_Runner(111, (2.00, 100), (2.02, 100))], pt=t0 + 91_000)
    s.process_market_book(m, mb_91s)
    assert s._tr["1.1"].get("closing") is True, "oltre tmax secondi → uscita"


# ---------------------------------------------------------------------------
# 3) chiusura: escalation a TAKER e pop SOLO a posizione flat
# ---------------------------------------------------------------------------
def test_closing_escalates_to_taker_and_pops_only_when_flat():
    s = _make(close_retry_ticks=2, maker=True)
    orders = [_Order(111, "BACK", 2.0, 2.00)]
    m = _Market(_Blotter(orders))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(2.00),
                    "anchor": _tki(1.80), "order": None, "held": 0, "wait": 0,
                    "t0": 1, "closing": True, "close_order": None, "close_wait": 0}
    mb = _MB([_Runner(111, (2.00, 100), (2.02, 100))], pt=10_000)
    s.process_market_book(m, mb)   # close_wait 1
    s.process_market_book(m, mb)   # close_wait 2
    assert not m.placed, "dentro la finestra maker non si ripiazza"
    s.process_market_book(m, mb)   # close_wait 3 > 2 → escalation TAKER
    assert m.placed, "chiusura taker piazzata"
    assert float(m.placed[-1].order_type.price) == 2.02  # touch lay = attraversa
    assert "1.1" in s._tr, "trade ancora vivo finché non è flat"
    # la gamba di chiusura si riempie: posizione pareggiata → pop
    orders.append(_Order(111, "LAY", 1.98, 2.02))
    s.process_market_book(m, mb)
    assert "1.1" not in s._tr, "flat verificato → trade chiuso"


# ---------------------------------------------------------------------------
# 4) l'ingresso memorizza sel + t0 nel trade
# ---------------------------------------------------------------------------
def test_entry_stores_selection_and_t0():
    s = _make(N=10, conf_ticks=1, zin=1.0, er_max=0.95, maker=False,
              price_min=1.01, price_max=8.0)
    # storia pre-caricata: oscillazione 2.94/2.96 + spike a 3.20, ritorno a 3.05
    s._hist["1.1"] = deque([146, 147] * 11 + [153], maxlen=200)
    s._prev_rsi["1.1"] = 70.0   # RSI in cross discendente attraverso 65
    m = _Market(_Blotter([]))
    pt = 777_000
    mb = _MB([_Runner(111, (3.00, 100), (3.10, 100), ltp=3.05)], pt=pt)
    s.process_market_book(m, mb)
    tr = s._tr.get("1.1")
    assert tr is not None, "ingresso scattato"
    assert tr["sel"] == 111
    assert tr["t0"] == pt
    assert tr["side"] == "BACK"
    assert s.stats["entries"] == 1


# ---------------------------------------------------------------------------
# 5) FIX 16/07 — caso reale: entry LAY con z=-674.500.000 su book piatto
# ---------------------------------------------------------------------------
def test_mad_zero_niente_falsi_segnali():
    """Book piatto → MAD 0: il vecchio fallback 1e-9 trasformava UN tick di
    movimento in z astronomico (firma: 0.6745/1e-9 ≈ 6.7e8) → falso segnale.
    Nessuna dispersione = nessun segnale."""
    s = _make(N=10, conf_ticks=1, zin=1.0, er_max=0.95, maker=False,
              price_min=1.01, price_max=8.0)
    s._hist["1.1"] = deque([147] * 21 + [155, 154], maxlen=200)
    s._prev_rsi["1.1"] = 70.0
    m = _Market(_Blotter([]))
    mb = _MB([_Runner(111, (3.00, 100), (3.10, 100), ltp=3.05)], pt=777_000)
    s.process_market_book(m, mb)
    assert s._tr.get("1.1") is None, "MAD 0: nessun ingresso"
    assert s.stats["entries"] == 0
    assert m.placed == []


# ---------------------------------------------------------------------------
# 6) FIX 16/07 — dry: ciclo paper COMPLETO con esito (prima evaporava a 40s)
# ---------------------------------------------------------------------------
def test_dry_ciclo_completo_paper_con_esito():
    s = _make(dry_run=True, stake=5.0, tmax=90, stop_ticks=50,
              target_frac=0.5, maker=False)
    m = _Market(_Blotter([]))
    t0 = 1_000_000
    s._tr["1.1"] = {"sel": 111, "side": "LAY", "etk": _tki(1.27),
                    "anchor": _tki(1.35), "order": None, "held": 0,
                    "wait": 0, "px": 1.27, "t0": t0}
    # a 30s il trade virtuale e' ancora VIVO (prima: ramo 'non riempita')
    s.process_market_book(
        m, _MB([_Runner(111, (1.26, 100), (1.27, 100))], pt=t0 + 30_000))
    assert "1.1" in s._tr, "posizione virtuale gestita, non evaporata"
    # oltre tmax: uscita a tempo con ESITO virtuale (lay 1.27 → back 1.28)
    s.process_market_book(
        m, _MB([_Runner(111, (1.28, 100), (1.29, 100))], pt=t0 + 91_000))
    assert "1.1" not in s._tr, "trade chiuso con esito"
    assert s.stats["losses"] == 1              # uscita a tempo
    assert s.stats["pnl"] != 0.0               # P&L virtuale contabilizzato
    assert m.placed == [], "dry: MAI ordini piazzati"
