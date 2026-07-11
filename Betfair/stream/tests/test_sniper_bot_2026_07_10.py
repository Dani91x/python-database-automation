"""SNIPER in-play (sniper_bot.SniperStrategy) — porting produzione di S16.

Coperture (logica pura, no rete):
  1. GATE: senza cadenza di tick-down non spara; con cadenza+coda+spread ok
     spara (taker al best back). La coda piena o lo spread largo bloccano.
  2. DRY-RUN (demo): nessun ordine, emette ``sniper_dry_fire`` con anti-spam.
  3. TIMEOUT: posizione oltre max_pos_s -> flatten immediato.
  4. VERDE: close matchata -> pnl_locked, missione compiuta (event done),
     nessun nuovo ingresso.
  5. LOSS CAP evento: raggiunto il cap niente nuovi ingressi.
  6. force_flat / is_flat per lo stop sicuro della sessione.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.scalper.sniper_bot import SniperStrategy

KO = dt.datetime(2026, 7, 10, 15, 0, 0)
KO_MS = KO.replace(tzinfo=dt.timezone.utc).timestamp() * 1000.0


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
    def __init__(self, side, price=3.4, size=10.0, size_matched=0.0,
                 avg=0.0, live=False, selection_id=1221385):
        self.side = side
        self.selection_id = selection_id
        self.size_matched = size_matched
        self.average_price_matched = avg
        self.size_remaining = max(0.0, size - size_matched) if live else 0.0
        self.status = (OrderStatus.EXECUTABLE if live
                       else OrderStatus.EXECUTION_COMPLETE)
        self.order_type = SimpleNamespace(price=price, size=size)


def _book(pt_s, bb=3.50, bl=3.55, sb=400.0, sl=400.0, inplay=True):
    """Market book OU15 con Under (sort_priority 1) quotato bb/bl."""
    ex = SimpleNamespace(
        available_to_back=[{"price": bb, "size": sb}],
        available_to_lay=[{"price": bl, "size": sl}],
    )
    runner = SimpleNamespace(selection_id=1221385, status="ACTIVE", ex=ex)
    md = SimpleNamespace(
        market_type="OVER_UNDER_15",
        market_time=KO,
        runners=[SimpleNamespace(selection_id=1221385, sort_priority=1),
                 SimpleNamespace(selection_id=1221386, sort_priority=2)],
    )
    return SimpleNamespace(
        market_id="1.234", status="OPEN", inplay=inplay,
        publish_time_epoch=KO_MS + pt_s * 1000.0,
        market_definition=md, runners=[runner],
    )


def _strategy(**over):
    params = {"stake": 10.0, "min_size": 50.0}
    params.update(over)
    events = []
    s = SniperStrategy(market_filter={}, sniper_params=params,
                       event_sink=lambda k, p: events.append((k, p)))
    s._test_events = events
    return s


def _walk_to_armed(s, mkt, t0=600.0, thin=100.0):
    """Sequenza book: 2 tick-down recenti + coda consumata -> gate verde."""
    s.process_market_book(mkt, _book(t0, bb=3.50, bl=3.55, sb=400))
    s.process_market_book(mkt, _book(t0 + 30, bb=3.45, bl=3.50, sb=380))
    s.process_market_book(mkt, _book(t0 + 60, bb=3.40, bl=3.45, sb=420))
    s.process_market_book(mkt, _book(t0 + 90, bb=3.40, bl=3.45, sb=thin))


# ------------------------------------------------------------------- 1. gate
def test_niente_cadenza_niente_fuoco():
    s = _strategy()
    mkt = _FakeMarket()
    # book fermo: nessun tick-down -> mai ingresso anche con coda sottile
    for i in range(6):
        s.process_market_book(mkt, _book(600 + i * 20, bb=3.40, bl=3.45, sb=60))
    assert mkt.orders == []
    assert s.stats["entries"] == 0


def test_gate_completo_spara_taker_al_best_back():
    s = _strategy()
    mkt = _FakeMarket()
    _walk_to_armed(s, mkt)
    assert len(mkt.orders) == 1
    o = mkt.orders[0]
    assert o.side == "BACK"
    assert o.order_type.price == pytest.approx(3.40)
    assert s.stats["entries"] == 1


def test_coda_piena_blocca():
    s = _strategy()
    mkt = _FakeMarket()
    _walk_to_armed(s, mkt, thin=400.0)   # coda NON consumata (>35% del max)
    assert mkt.orders == []


def test_spread_largo_blocca():
    s = _strategy()
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(600, bb=3.50, bl=3.60, sb=400))
    s.process_market_book(mkt, _book(630, bb=3.45, bl=3.55, sb=380))
    s.process_market_book(mkt, _book(660, bb=3.40, bl=3.50, sb=420))
    s.process_market_book(mkt, _book(690, bb=3.40, bl=3.50, sb=100))  # 2 tick
    assert mkt.orders == []


def test_pre_match_non_spara():
    s = _strategy()
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(-1200, bb=3.50, bl=3.55, sb=400,
                                     inplay=False))
    s.process_market_book(mkt, _book(-1100, bb=3.45, bl=3.50, sb=380,
                                     inplay=False))
    s.process_market_book(mkt, _book(-1000, bb=3.40, bl=3.45, sb=60,
                                     inplay=False))
    assert mkt.orders == []


# ---------------------------------------------------------------- 2. dry-run
def test_dry_run_emette_trigger_senza_ordini():
    s = _strategy(dry_run=True)
    mkt = _FakeMarket()
    _walk_to_armed(s, mkt)
    assert mkt.orders == []                      # NESSUN ordine in demo
    fires = [p for k, p in s._test_events if k == "sniper_dry_fire"]
    assert len(fires) == 1
    assert fires[0]["price"] == pytest.approx(3.40)
    assert s.stats["dry_fires"] == 1
    # anti-spam: entro 120s lo stesso trigger non viene ripetuto
    s.process_market_book(mkt, _book(700, bb=3.40, bl=3.45, sb=90))
    assert s.stats["dry_fires"] == 1


# ---------------------------------------------------------------- 3. timeout
def test_timeout_flatten():
    s = _strategy(max_pos_s=300.0)
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    pos.entries = [_FakeOrder("BACK", price=3.40, size_matched=10.0, avg=3.40)]
    pos.entry_fill_pt = KO_MS + 600_000.0
    # a +301s dal fill il timeout scatta e la posizione va in flatten
    s.process_market_book(mkt, _book(600 + 301, bb=3.40, bl=3.45, sb=200))
    assert pos.flattening is True
    assert s.stats["timeouts"] == 1


# ------------------------------------------------------------------ 4. verde
def test_verde_chiude_l_evento():
    s = _strategy()
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    pos.entries = [_FakeOrder("BACK", price=3.40, size_matched=10.0, avg=3.40)]
    pos.entry_fill_pt = KO_MS + 600_000.0
    # book al target: piazza la close a entry-1 tick
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert pos.close is not None
    assert pos.close.order_type.price == pytest.approx(3.35)
    locked = pos.close_locked
    assert locked > 0
    # la close si riempie -> verde, missione compiuta (fill simulato
    # sostituendo l'ordine flumine con un fake matchato, come nella suite)
    pos.close = _FakeOrder("LAY", price=3.35,
                           size=pos.close.order_type.size,
                           size_matched=pos.close.order_type.size, avg=3.35)
    s.process_market_book(mkt, _book(660, bb=3.35, bl=3.40, sb=200))
    assert s.stats["greens"] == 1
    assert s.stats["pnl_locked"] == pytest.approx(locked)
    assert s._event_done is True
    # dopo la missione NIENTE nuovi ingressi anche col gate verde
    n0 = len(mkt.orders)
    _walk_to_armed(s, mkt, t0=1200.0)
    assert len(mkt.orders) == n0


# --------------------------------------------------------------- 5. loss cap
def test_loss_cap_blocca_ingressi():
    s = _strategy(event_loss_cap=1.0)
    s.stats["pnl_locked"] = -1.2
    mkt = _FakeMarket()
    _walk_to_armed(s, mkt)
    assert mkt.orders == []
    assert s._event_done is True


# ------------------------------------------------- 6b. linea dinamica (live)
def test_set_line_dinamica_e_posizioni_gestite():
    s = _strategy()
    mkt = _FakeMarket()
    # posizione APERTA su OU15, poi il gol sposta la linea a OU65
    pos = s._p("1.234", 1221385)
    pos.entries = [_FakeOrder("BACK", price=3.40, size_matched=10.0, avg=3.40)]
    s.set_line("OVER_UNDER_65")
    assert s.lines == {"OVER_UNDER_65"}
    assert "sniper_line" in [k for k, _ in s._test_events]
    # il book OU15 (posizione aperta) resta GESTITO...
    assert s.check_market_book(mkt, _book(700)) is True
    # ...ma senza posizione un OU15 non passa piu'
    s2 = _strategy()
    s2.set_line("OVER_UNDER_65")
    assert s2.check_market_book(mkt, _book(700)) is False
    # e la microstruttura e' stata azzerata dal cambio linea
    assert not s._dn_ts and not s._level_max_sb


def test_set_line_none_spegne_il_fuoco():
    s = _strategy()
    s.set_line("NONE")   # oltre la 8.5 non esistono linee: niente fuoco
    mkt = _FakeMarket()
    _walk_to_armed(s, mkt)
    assert mkt.orders == []


# --------------------------------------- 7. esecuzione live .it (money-critical)
def test_formula_green_spalmato_esatto():
    """compute_green spalma il profitto IDENTICO sui due esiti:
    BACK 5@1.28 chiuso @1.27 -> +0.0394 su entrambi."""
    from Betfair.stream.scalper.scalper_bot import compute_green
    nw, nl = 5 * 0.28, -5.0
    side, size, locked = compute_green(nw, nl, 1.27)
    assert side == "LAY"
    assert size == pytest.approx(6.40 / 1.27)
    win_after = nw - size * 0.27
    lose_after = nl + size
    assert win_after == pytest.approx(lose_after)      # SPALMATO ESATTO
    assert locked == pytest.approx(win_after)
    assert locked == pytest.approx(0.0394, abs=1e-3)


def test_size_direct_ok_regole_it():
    s = _strategy()
    assert s._size_direct_ok("LAY", 5.0) is True
    assert s._size_direct_ok("LAY", 5.04) is False     # non multiplo di 0.50
    assert s._size_direct_ok("LAY", 0.5) is True       # min LAY 0.50
    assert s._size_direct_ok("BACK", 1.5) is False     # min BACK 2.00
    assert s._size_direct_ok("BACK", 2.0) is True


def test_place_exact_spezza_parte_diretta_piu_submin():
    """LAY 7.63 con exact_exits: 7.50 diretti + sequenza submin per 0.13."""
    s = _strategy(exact_exits=True, size_step=0.5, live_min_bet=2.0)
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    o = s._place(mkt, 1221385, "LAY", 1.27, 7.63, floor=False, pos=pos)
    assert o is not None and o.order_type.size == pytest.approx(7.5)
    assert len(pos.submins) == 1                       # resto 0.13 via submin
    st = pos.submins[0]["state"]
    assert st.target_size == pytest.approx(0.13)
    assert st.target_price == pytest.approx(1.27)


def test_place_exact_micro_resto_accettato():
    """LAY 5.04: 5.00 diretti, resto 0.04 < 0.05 accettato (min_bet_skip),
    NESSUNA sequenza (semantica di produzione dello scalper)."""
    s = _strategy(exact_exits=True, size_step=0.5, live_min_bet=2.0)
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    o = s._place(mkt, 1221385, "LAY", 1.27, 5.04, floor=False, pos=pos)
    assert o is not None and o.order_type.size == pytest.approx(5.0)
    assert pos.submins == []
    assert any(k == "min_bet_skip" for k, _ in s._test_events)


def test_place_senza_exact_arrotonda_e_bumpa():
    s = _strategy(size_step=0.5, live_min_bet=2.0)      # exact_exits OFF
    mkt = _FakeMarket()
    # 5.04 -> arrotondata al multiplo 5.0
    o = s._place(mkt, 1221385, "LAY", 1.27, 5.04, floor=False)
    assert o.order_type.size == pytest.approx(5.0)
    # BACK 1.6 sotto il minimo 2.0 -> bump a 2.0 (micro over-hedge)
    o2 = s._place(mkt, 1221385, "BACK", 3.4, 1.6, floor=False)
    assert o2.order_type.size == pytest.approx(2.0)
    # residuo minuscolo 0.2 -> NON piazzato (micro-rischio accettato)
    o3 = s._place(mkt, 1221385, "LAY", 1.27, 0.2, floor=False)
    assert o3 is None


def test_flatten_accetta_micro_residuo():
    """Residuo non piazzabile (<=0.30) senza ordini vivi -> il flatten chiude
    contabilizzando il worst-case (niente inseguimento infinito)."""
    s = _strategy(size_step=0.5, live_min_bet=2.0)
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    pos.flattening = True
    pos.flatten_orders = [
        _FakeOrder("BACK", price=3.40, size_matched=10.0, avg=3.40),
        _FakeOrder("LAY", price=3.35, size_matched=10.0, avg=3.35),
    ]
    # nw = 10*2.40 - 10*2.35 = +0.50 ; nl = 0 -> sbilancio 0.50 > 0.30:
    # NON accettato: il flatten insegue (piazza la chiusura)
    s._drive_flatten(mkt, pos, 3.40, 3.45, KO_MS)
    assert pos.flattening is True
    # sbilancio piccolo: 10 vs 10.08 -> |nw-nl| <= 0.30 -> accettato
    pos2 = s._p("1.234", 1221386)
    pos2.flattening = True
    pos2.flatten_orders = [
        _FakeOrder("BACK", price=3.40, size_matched=10.0, avg=3.40,
                   selection_id=1221386),
        _FakeOrder("LAY", price=3.35, size_matched=10.08, avg=3.35,
                   selection_id=1221386),
    ]
    n0 = s.stats["flattens"]
    s._drive_flatten(mkt, pos2, 3.40, 3.45, KO_MS)
    assert pos2.flattening is False
    assert s.stats["flattens"] == n0 + 1
    assert any(k == "sniper_flat_residual" for k, _ in s._test_events)


# -------------------------------------------------------- 6. force_flat/flat
def test_force_flat_e_is_flat():
    s = _strategy()
    mkt = _FakeMarket()
    assert s.is_flat() is True
    pos = s._p("1.234", 1221385)
    pos.entries = [_FakeOrder("BACK", price=3.40, size_matched=10.0,
                              avg=3.40, live=True)]
    assert s.is_flat() is False
    s.force_flat = True
    s.process_market_book(mkt, _book(700, bb=3.40, bl=3.45, sb=200))
    assert pos.flattening is True
    # il flatten ha piazzato la chiusura (LAY) per pareggiare la gamba
    lays = [o for o in mkt.orders if o.side == "LAY"]
    assert lays, "attesa chiusura LAY dal flatten"


def test_ledger_divergence_riapre_flatten_con_critical():
    """Regressione 10/07 21:43: posizione considerata CHIUSA (niente entries,
    niente flattening, niente submins) ma gli ordini reali mostrano una
    esposizione direzionale (park abbinati) -> la rete ledger<->ordini emette
    CRITICAL e riapre il flatten certificato. Prima del fix il bot restava
    "flat +0.03" mentre il conto era short ~10 EUR (chiuso a mano)."""
    s = _strategy(dry_run=False)
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    # short invisibile: LAY 8@2.4 matchato orfano; il ledger lo crede chiuso
    pos.flatten_orders.append(_FakeOrder("LAY", price=2.4, size=8.0,
                                         size_matched=8.0, avg=2.4))

    s.process_market_book(mkt, _book(1200, bb=3.40, bl=3.45, sb=200))

    kinds = [k for k, _ in s._test_events]
    assert "ledger_divergence" in kinds
    assert pos.flattening is True                # auto-heal partito
    assert s.stats["ledger_divergences"] == 1
    # l'equalizzazione e' stata piazzata (BACK per chiudere lo short)
    backs = [o for o in mkt.orders if o.side == "BACK"]
    assert backs, "attesa equalizzazione BACK dal flatten"


def test_ledger_flat_non_scatta():
    """Un ciclo chiuso SANO (green equalizzato) non deve far scattare la rete."""
    s = _strategy(dry_run=False)
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    # entry BACK 5@3.45 + green LAY 5.07@3.40: equalizzato (|nw-nl|<=0.02)
    pos.flatten_orders.append(_FakeOrder("BACK", price=3.45, size=5.0,
                                         size_matched=5.0, avg=3.45))
    pos.flatten_orders.append(_FakeOrder("LAY", price=3.40, size=5.07,
                                         size_matched=5.07, avg=3.40))

    s.process_market_book(mkt, _book(1200, bb=3.40, bl=3.45, sb=200))

    kinds = [k for k, _ in s._test_events]
    assert "ledger_divergence" not in kinds
    assert pos.flattening is False
