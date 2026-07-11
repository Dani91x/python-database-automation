"""Stake pre-dimensionati per il green simmetrico (direttiva operatore 10/07).

Live Spagna 10/07: entry e close a stake IDENTICO (25/25) → roundtrip mai
equalizzato (+0.49/0.00), gamba di greening sotto-minimo skippata, missione
cieca al verde. Direttiva (§12.1 bibbia): il verde si spalma NEGLI STAKE —
quando l'entry si abbina, la close in coda va portata alla size
verde-simmetrica ``exit = entry x P_entry / P_exit`` SENZA perdere la coda:
riduzione via cancel PARZIALE, aumento via micro ordine aggiuntivo alla
stessa quota.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.scalper.scalper_bot import ScalperStrategy, _Slot, QUOTING2, LOCKING


class _FakeMarket:
    market_id = "1.234"

    def __init__(self):
        self.orders = []
        self.cancelled = []          # (order, size_reduction)

    def place_order(self, order):
        self.orders.append(order)

    def cancel_order(self, order, size_reduction=None):
        self.cancelled.append((order, size_reduction))


class _FakeOrder:
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


def _strategy(events=None):
    kw = {}
    if events is not None:
        kw["event_sink"] = lambda kind, payload: events.append((kind, payload))
    return ScalperStrategy(market_filter={},
                           scalper_params={"dry_run": False, "stake": 25.0},
                           **kw)


def _quoting2_slot(strategy, eb, el):
    slot = strategy._slot("1.234", 42)
    slot.status = QUOTING2
    slot.entry_back = eb
    slot.entry_lay = el
    slot.t_quote = 1_000
    return slot


# --------------------------------------------------- BACK filled → top-up LAY
def test_back_filled_close_lay_topup_alla_stessa_quota():
    """Entry BACK 25@2.22 abbinata, close LAY 25@2.20 in coda: serve LAY
    totale 25×2.22/2.20 = 25.23 → top-up di 0.23 alla STESSA quota (la
    parte in coda resta intatta)."""
    events = []
    s = _strategy(events)
    eb = _FakeOrder("BACK", price=2.22, size=25.0, size_matched=25.0,
                    avg=2.22, live=False)
    el = _FakeOrder("LAY", price=2.20, size=25.0, live=True)
    m = _FakeMarket()
    slot = _quoting2_slot(s, eb, el)

    s._manage_maker(m, slot, now=2_000, best_back=2.20, best_lay=2.22,
                    size_back=500.0, size_lay=500.0)

    assert slot.status == LOCKING
    assert slot.close is el                     # la close in coda NON si tocca
    assert not m.cancelled                      # nessuna cancel: coda intatta
    assert len(m.orders) == 1                   # il solo top-up
    top = m.orders[0]
    assert top.side == "LAY"
    assert top.order_type.price == pytest.approx(2.20)
    assert top.order_type.size == pytest.approx(0.23)
    kinds = [k for k, _ in events]
    assert "close_presize" in kinds


def test_back_filled_topup_entra_nella_contabilita_dello_slot():
    """Il top-up e' tracciato: quando close e top-up si riempiono, lo slot
    e' PIATTO e VERDE sui due esiti (la missione vede il verde)."""
    s = _strategy()
    eb = _FakeOrder("BACK", price=2.22, size=25.0, size_matched=25.0,
                    avg=2.22, live=False)
    el = _FakeOrder("LAY", price=2.20, size=25.0, live=True)
    m = _FakeMarket()
    slot = _quoting2_slot(s, eb, el)
    s._manage_maker(m, slot, now=2_000, best_back=2.20, best_lay=2.22,
                    size_back=500.0, size_lay=500.0)
    top = m.orders[0]
    assert top in slot.flatten_orders           # anti-orfani + contabilita'

    # fill di close e top-up → posizione piatta e verde. Il top-up e' un
    # BetfairOrder reale (size_matched = property read-only): per simulare il
    # fill lo si sostituisce nella contabilita' con una replica abbinata.
    idx = slot.flatten_orders.index(top)
    slot.flatten_orders[idx] = _FakeOrder("LAY", price=2.20, size=0.23,
                                          size_matched=0.23, avg=2.20,
                                          live=False)
    el.size_matched, el.average_price_matched = 25.0, 2.20
    el.status, el.size_remaining = OrderStatus.EXECUTION_COMPLETE, 0.0
    nw, nl = s._net_position(slot)
    assert abs(nw - nl) <= 0.02                 # simmetrico al centesimo
    assert min(nw, nl) > 0.20                   # ~+0.22 su entrambi gli esiti


# ------------------------------------------- LAY filled → riduzione close BACK
def test_lay_filled_close_back_ridotta_con_cancel_parziale():
    """Entry LAY 25@2.20 abbinata, close BACK 25@2.22 in coda: serve BACK
    totale 25×2.20/2.22 = 24.77 → cancel PARZIALE di 0.23 (l'exchange
    conserva la coda del residuo)."""
    events = []
    s = _strategy(events)
    el = _FakeOrder("LAY", price=2.20, size=25.0, size_matched=25.0,
                    avg=2.20, live=False)
    eb = _FakeOrder("BACK", price=2.22, size=25.0, live=True)
    m = _FakeMarket()
    slot = _quoting2_slot(s, eb, el)

    s._manage_maker(m, slot, now=2_000, best_back=2.20, best_lay=2.22,
                    size_back=500.0, size_lay=500.0)

    assert slot.status == LOCKING
    assert slot.close is eb
    assert not m.orders                          # nessun ordine nuovo
    assert len(m.cancelled) == 1
    order, reduction = m.cancelled[0]
    assert order is eb
    assert reduction == pytest.approx(0.23)
    kinds = [k for k, _ in events]
    assert "close_presize" in kinds


# ------------------------------------------ F1.4: il flatten TERMINA sempre
def test_flatten_forzato_accetta_residuo_non_piazzabile():
    """Bug live 10/07 20:58: residui sotto-minimo non piazzabili → skip-loop
    oltre la deadline KO-3', flattens=0, ciclo mai contabilizzato. Direttiva:
    dopo molti tentativi senza nulla di piazzabile il residuo si ACCETTA e
    si CONTABILIZZA (il flatten termina SEMPRE, con ledger chiuso)."""
    from Betfair.stream.scalper.scalper_bot import FLATTENING, DONE

    events = []
    s = ScalperStrategy(
        market_filter={},
        scalper_params={"dry_run": False, "live_min_bet": 1.0,
                        "size_step": 0.5, "exact_exits": False},
        event_sink=lambda kind, payload: events.append((kind, payload)),
    )
    slot = s._slot("1.234", 42)
    slot.status = FLATTENING
    # LAY 0.20@4.0 matchata orfana: green BACK ~0.22 (< 0.25 → skip .it),
    # min(nw,nl) = -0.60 (oltre la soglia micro -0.25) → prima del fix: loop.
    orphan = _FakeOrder("LAY", price=4.0, size=0.20, size_matched=0.20,
                        avg=4.0, live=False)
    slot.flatten_orders.append(orphan)
    slot.flat_tries = 13
    m = _FakeMarket()

    s._drive_flatten(m, slot, best_back=4.0, best_lay=4.1, now=10_000)

    assert slot.status == DONE                     # TERMINATO, sempre
    assert slot.residual_ok is True
    assert slot.residual_accepted == pytest.approx(0.80)   # |nw-nl|
    assert s.stats["pnl_locked"] == pytest.approx(-0.60)   # worst-case contato
    kinds = [k for k, _ in events]
    assert "flatten_residual_forced" in kinds
    assert "min_bet_skip" in kinds                 # la causa: non piazzabile


# ------------------------- F1.5: telemetria onesta (scalp = tick VERO)
def test_scratch_par_non_conta_come_scalp():
    """Live 10/07: 7 cicli a 0.00 etichettati 'scalp'. Ora: locked sotto la
    soglia green → esito 'scratch_par', contatore scalps FERMO."""
    from Betfair.stream.scalper.scalper_bot import LOCKING, DONE

    events = []
    s = _strategy(events)
    slot = s._slot("1.234", 42)
    # entry BACK 25@2.20 matchata; close scratch A PARI 25@2.20 matchata
    slot.entry = _FakeOrder("BACK", price=2.20, size=25.0, size_matched=25.0,
                            avg=2.20, live=False)
    slot.entry_side = "BACK"
    slot.close = _FakeOrder("LAY", price=2.20, size=25.0, size_matched=25.0,
                            avg=2.20, live=False)
    slot.close_scratched = True
    slot.status = LOCKING
    m = _FakeMarket()
    mb = SimpleNamespace(publish_time_epoch=10_000, market_definition=None)

    s._manage(m, mb, None, slot, now=10_000, best_back=2.18, best_lay=2.22,
              size_back=500.0, size_lay=500.0)

    assert slot.status == DONE
    assert s.stats["scalps"] == 0                 # NON e' un tick vero
    assert s.stats["scratch_pars"] == 1
    esiti = [p.get("esito") for k, p in events if k == "cycle"]
    assert esiti == ["scratch_par"]


def test_tick_vero_resta_scalp():
    """Il ciclo col tick catturato (locked >= 0.05) resta 'scalp'."""
    from Betfair.stream.scalper.scalper_bot import LOCKING, DONE

    events = []
    s = _strategy(events)
    slot = s._slot("1.234", 42)
    # entry BACK 25@2.22, close LAY pre-dimensionata 25.23@2.20 → +0.22/+0.23
    slot.entry = _FakeOrder("BACK", price=2.22, size=25.0, size_matched=25.0,
                            avg=2.22, live=False)
    slot.entry_side = "BACK"
    slot.close = _FakeOrder("LAY", price=2.20, size=25.23, size_matched=25.23,
                            avg=2.20, live=False)
    slot.status = LOCKING
    m = _FakeMarket()
    mb = SimpleNamespace(publish_time_epoch=10_000, market_definition=None)

    s._manage(m, mb, None, slot, now=10_000, best_back=2.18, best_lay=2.22,
              size_back=500.0, size_lay=500.0)

    assert slot.status == DONE
    assert s.stats["scalps"] == 1
    assert s.stats["scratch_pars"] == 0
    esiti = [p.get("esito") for k, p in events if k == "cycle"]
    assert esiti == ["scalp"]


def test_presize_nessuna_azione_se_gia_simmetrica():
    """Prezzi uguali (scratch a pari implicito): ideal == size → zero mosse."""
    s = _strategy()
    eb = _FakeOrder("BACK", price=2.20, size=25.0, size_matched=25.0,
                    avg=2.20, live=False)
    el = _FakeOrder("LAY", price=2.20, size=25.0, live=True)
    m = _FakeMarket()
    slot = _quoting2_slot(s, eb, el)
    # book che NON incrocia la close (best_lay sopra il suo prezzo)
    s._manage_maker(m, slot, now=2_000, best_back=2.18, best_lay=2.22,
                    size_back=500.0, size_lay=500.0)
    assert slot.status == LOCKING
    assert not m.orders and not m.cancelled
