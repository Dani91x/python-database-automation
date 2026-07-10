"""Missione "2 tick per evento" + fix audit 10/07/2026 — scalper calcio.

Coperture (logica pura, no rete):
  1. one_green_per_phase: un ciclo verde (locked >= 0.05) PRE-MATCH blocca i
     nuovi ingressi pre-match ma NON quelli in-play; un verde in-play blocca
     tutto. Il blocco cancella anche le quote resting inevase (ramo A2).
  2. FIX contabilita' micro-residui: il residuo accettato dal flatten entra
     in pnl_locked e nel P&L di fase (prima spariva dalla contabilita').
  3. FIX watcher HT (scalper_session.ht_should_start): staleness 300s e
     vincolo minute <= 48 (non scatta durante il recupero del 1° tempo).
  4. FIX gate di evento per-book: event_loss_cap si arma anche con lo slot
     in cooldown (prima viveva solo in _try_enter, dopo cooldown/banda).
  5. FIX QUOTING2 parziale senza TTL: oltre entry_ttl_ms il residuo resting
     viene cancellato e la parte matchata chiusa via LOCKING standard.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.scalper.scalper_bot import ScalperStrategy, _Slot


# ------------------------------------------------------------------- fixtures
class _FakeMarket:
    market_id = "1.234"

    def __init__(self):
        self.orders = []
        self.cancelled = []

    def place_order(self, order):
        self.orders.append(order)

    def cancel_order(self, order):
        self.cancelled.append(order)


class _FakeOrder:
    """Ordine minimale (duck-typing dei campi letti dal bot)."""

    def __init__(self, side, price=2.2, size=25.0, size_matched=0.0,
                 avg=0.0, live=False, selection_id=42):
        self.side = side
        self.selection_id = selection_id
        self.size_matched = size_matched
        self.average_price_matched = avg
        self.size_remaining = max(0.0, size - size_matched) if live else 0.0
        self.status = (OrderStatus.EXECUTABLE if live
                       else OrderStatus.EXECUTION_COMPLETE)
        self.order_type = SimpleNamespace(price=price, size=size)
        self.trade = None


class _ExBook:
    def __init__(self, bb=2.20, bl=2.22, sb=500.0, sl=500.0):
        self.available_to_back = [{"price": bb, "size": sb}]
        self.available_to_lay = [{"price": bl, "size": sl}]
        self.traded_volume = []


class _RunnerBook:
    def __init__(self, sid=42):
        self.selection_id = sid
        self.status = "ACTIVE"
        self.total_matched = 10_000.0
        self.ex = _ExBook()


class _MarketBook:
    def __init__(self, now, inplay=False):
        self.publish_time_epoch = now
        self.market_id = "1.234"
        self.inplay = inplay
        self.status = "OPEN"
        self.market_definition = None
        self.runners = [_RunnerBook()]


def _make_strategy(events=None, **params):
    kw = {}
    if events is not None:
        kw["event_sink"] = lambda kind, payload: events.append((kind, payload))
    return ScalperStrategy(market_filter={}, scalper_params=params, **kw)


def _mission_strategy(events=None, **over):
    """Strategia reversion che PUO' entrare via process_market_book:
    gate KO/finestre disattivati, segnale pre-seminabile via slot.history."""
    params = dict(
        mode="reversion", one_green_per_phase=True,
        allow_inplay=True, inplay_from_s=0.0, inplay_to_s=0.0,
        flatten_before_s=0.0, entry_stop_before_s=0.0,
        min_size=10.0, signal_ticks=1, max_signal_ticks=4,
        signal_window_ms=10_000, wom_block=0.9,
    )
    params.update(over)
    return _make_strategy(events=events, **params)


def _seed_signal(strategy, now_ref=95_000, ref=2.18):
    """Pre-semina la history dello slot: segnale BACK su book 2.20/2.22."""
    slot = strategy._slot("1.234", 42)
    slot.history.append((now_ref, ref))
    return slot


# --------------------------------------------- 1. missione one_green_per_phase
def test_on_cycle_closed_contabilita_e_evento_mission():
    events = []
    s = _mission_strategy(events=events)
    slot = _Slot()          # inplay_cycle=False -> fase prematch
    s._on_cycle_closed(slot, 0.06, kind="scalp", now=1_000)
    assert s.stats["greens_prematch"] == 1
    assert s.stats["pnl_prematch"] == pytest.approx(0.06)
    assert ("mission", {"phase": "prematch", "locked": 0.06,
                        "msg": "tick di fase completato"}) in events
    # secondo verde della stessa fase: contato ma NIENTE secondo evento
    s._on_cycle_closed(slot, 0.07, kind="scalp", now=2_000)
    assert s.stats["greens_prematch"] == 2
    assert sum(1 for k, _ in events if k == "mission") == 1
    # cycle_log popolato con la forma {"phase","locked","kind","ts"}
    assert s.cycle_log[-1] == {"phase": "prematch", "locked": 0.07,
                               "kind": "scalp", "ts": 2_000}


def test_micro_locked_sotto_soglia_non_e_un_green():
    s = _mission_strategy()
    slot = _Slot()
    s._on_cycle_closed(slot, 0.01, kind="roundtrip", now=1_000)
    assert s.stats["greens_prematch"] == 0
    assert s.stats["pnl_prematch"] == pytest.approx(0.01)


def test_green_prematch_blocca_prematch_ma_non_inplay():
    s = _mission_strategy()
    market = _FakeMarket()
    # ciclo verde PRE-MATCH gia' chiuso
    s._on_cycle_closed(_Slot(), 0.06, kind="scalp", now=90_000)
    _seed_signal(s)
    # book pre-match: fase completata -> NESSUN nuovo ingresso
    s.process_market_book(market, _MarketBook(100_000, inplay=False))
    assert market.orders == []
    # book IN-PLAY: il tick in-play manca ancora -> ingresso PERMESSO
    s.process_market_book(market, _MarketBook(101_000, inplay=True))
    assert len(market.orders) == 1
    assert s._slot("1.234", 42).inplay_cycle is True


def test_green_inplay_blocca_tutto():
    s = _mission_strategy()
    market = _FakeMarket()
    s._on_cycle_closed(_Slot(), 0.06, kind="scalp", now=90_000)      # prematch
    in_slot = _Slot()
    in_slot.inplay_cycle = True
    s._on_cycle_closed(in_slot, 0.07, kind="scalp", now=91_000)      # inplay
    _seed_signal(s)
    s.process_market_book(market, _MarketBook(100_000, inplay=False))
    s.process_market_book(market, _MarketBook(101_000, inplay=True))
    assert market.orders == []


def test_senza_missione_il_green_non_blocca():
    """Sanita': con one_green_per_phase=False il verde non chiude la fase."""
    s = _mission_strategy(one_green_per_phase=False)
    market = _FakeMarket()
    s._on_cycle_closed(_Slot(), 0.06, kind="scalp", now=90_000)
    _seed_signal(s)
    s.process_market_book(market, _MarketBook(100_000, inplay=False))
    assert len(market.orders) == 1


def test_fase_completata_cancella_le_quote_resting():
    """Ramo A2: con no_entry armato dalla missione le quote INEVASE ancora
    vive vengono cancellate (anche in-play, dove prima no_entry non viveva)."""
    s = _mission_strategy()
    in_slot = _Slot()
    in_slot.inplay_cycle = True
    s._on_cycle_closed(in_slot, 0.07, kind="scalp", now=90_000)      # inplay OK
    market = _FakeMarket()
    slot = s._slot("1.234", 42)
    slot.status = "QUOTING2"
    slot.entry_back = _FakeOrder("BACK", price=2.20, live=True)
    slot.entry_lay = _FakeOrder("LAY", price=2.22, live=True)
    s.process_market_book(market, _MarketBook(100_000, inplay=True))
    assert slot.status == "CANCELLING"
    assert len(market.cancelled) == 2


# --------------------------------------- 2. residuo flatten in contabilita'
def test_residuo_flatten_contabilizzato_in_pnl_e_fase():
    events = []
    s = _make_strategy(events=events, live_min_bet=2.0, size_step=0.5)
    slot = _Slot()
    # residuo direzionale minuscolo: back 0.10 @ 2.0 -> nw=+0.10 / nl=-0.10
    slot.entry = _FakeOrder("BACK", price=2.0, size=0.10,
                            size_matched=0.10, avg=2.0)
    s._begin_flatten(slot)
    market = _FakeMarket()
    s._drive_flatten(market, slot, 2.20, 2.22, 100_000)
    assert slot.status == "DONE"
    assert slot.residual_ok is True
    # worst-case in contabilita': pnl_locked E P&L di fase
    assert s.stats["pnl_locked"] == pytest.approx(-0.10)
    assert s.stats["pnl_prematch"] == pytest.approx(-0.10)
    assert any(k == "flatten_residual" for k, _ in events)
    # seconda passata (monitor DONE / rientro in FLATTENING): MAI doppio conteggio
    slot.status = "FLATTENING"
    s._drive_flatten(market, slot, 2.20, 2.22, 101_000)
    assert s.stats["pnl_locked"] == pytest.approx(-0.10)
    assert s.stats["pnl_prematch"] == pytest.approx(-0.10)


# ------------------------------------------------------- 3. watcher HT (300s)
@pytest.mark.parametrize("minute,stale,expected", [
    (45, 200, False),   # recupero del 1° tempo: NON e' l'intervallo
    (45, 320, True),    # minuto congelato oltre 5' -> intervallo
    (46, 320, True),
    (48, 320, True),
    (52, 320, False),   # feed oltre 48: non e' l'intervallo
    (None, 320, False),
    (44, 320, False),
])
def test_ht_should_start_soglie(minute, stale, expected):
    from Betfair.stream.scalper.scalper_session import ht_should_start

    assert ht_should_start(minute, stale) is expected


# ---------------------------------------- 4. gate di evento valutato per-book
def test_event_loss_cap_armato_anche_con_slot_in_cooldown():
    """Prima del fix il gate viveva solo in _try_enter: con lo slot in
    cooldown il loss cap NON si armava mai e i cicli continuavano."""
    events = []
    s = _mission_strategy(events=events, one_green_per_phase=False,
                          event_loss_cap=1.0)
    s.stats["pnl_locked"] = -1.5
    slot = _seed_signal(s)
    slot.cooldown_until = 10**12     # cooldown: _try_enter non passerebbe mai
    market = _FakeMarket()
    s.process_market_book(market, _MarketBook(100_000, inplay=False))
    assert s.force_flat is True      # force-flat armato dal guard per-book
    assert market.orders == []
    assert any(k == "loss_cap" for k, _ in events)


def test_target_ratchet_blocca_gli_ingressi_per_book():
    s = _mission_strategy(one_green_per_phase=False,
                          event_profit_target=1.0, event_target_giveback=0.30)
    s.stats["pnl_locked"] = 0.50
    s.stats["pnl_peak"] = 1.20       # target raggiunto, giveback superato
    _seed_signal(s)
    market = _FakeMarket()
    s.process_market_book(market, _MarketBook(100_000, inplay=False))
    assert market.orders == []
    assert s.force_flat is False     # cricchetto: blocco ingressi, NON flatten


# ------------------------------------------- 5. QUOTING2 parziale oltre TTL
def test_quoting2_parziale_oltre_ttl_apre_il_lock():
    s = _make_strategy(entry_ttl_ms=1_000)
    market = _FakeMarket()
    slot = _Slot()
    slot.status = "QUOTING2"
    slot.t_quote = 0
    eb = _FakeOrder("BACK", price=2.22, size=25.0, size_matched=10.0,
                    avg=2.22, live=True)
    el = _FakeOrder("LAY", price=2.20, size=25.0, live=True)
    slot.entry_back, slot.entry_lay = eb, el
    # oltre il TTL: residui cancellati, chiusura della parte matchata
    s._manage_maker(market, slot, 5_000, 2.18, 2.24, 500.0, 500.0)
    assert slot.status == "LOCKING"
    assert slot.entry is eb and slot.entry_side == "BACK"
    assert slot.close is not None
    assert eb in market.cancelled and el in market.cancelled


def test_quoting2_parziale_entro_ttl_resta_in_attesa():
    s = _make_strategy(entry_ttl_ms=600_000)
    market = _FakeMarket()
    slot = _Slot()
    slot.status = "QUOTING2"
    slot.t_quote = 0
    slot.entry_back = _FakeOrder("BACK", price=2.22, size=25.0,
                                 size_matched=10.0, avg=2.22, live=True)
    slot.entry_lay = _FakeOrder("LAY", price=2.20, size=25.0, live=True)
    s._manage_maker(market, slot, 5_000, 2.18, 2.24, 500.0, 500.0)
    assert slot.status == "QUOTING2"     # comportamento invariato entro TTL
    assert slot.close is None
    assert market.orders == []
