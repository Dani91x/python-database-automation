"""SCALPER CALCIO (maker e sniper): chiusure AL CENTESIMO (07/10/2026).

Ordine dell'utente (07/10): "lo scalper deve chiudere pulito come gli altri bot!
questi residui non hanno senso, controlla il calcolo di uscita, se facciamo back,
possiamo uscire in lay al centesimo!". Regola 10 del brief: chiusure all'importo
ESATTO, mai gonfiate, mai arrotondate.

Casi VERI del replay `base` sulla 35797769 (diagnostica del 07/10, codice prima):
  R1 17:02 sel 22: LAY 25 @1,65 abbinata 2,80 -> scratch BACK 2,80: partivano
     2,50 diretti, 0,30 "residuo" (mai piazzato);
  R2 17:27 sel 47973: BACK 25 @1,85 abbinata, close LAY 25 @1,84 in coda: la
     pre-dimensione chiedeva +0,14 (sotto 0,50, saltata) -> residuo 0,25;
  R3 17:35 sel 22: LAY 25 @1,67 abbinata 9,25 -> BACK 9,00 + 0,25 "residuo";
  R5 17:36 sel 47973: flatten BACK 20,69 -> 20,50 + 0,19 "residuo";
  R6 18:19 sel 47972: LAY 25 @2,22 abbinata 1,98 -> BACK 1,50 + 0,48 "residuo"
     (e' quello che fa scattare il tetto di perdita a -1,61).
  R4 17:36 sel 22: ingresso BACK abbinato SOLO 0,29: la chiusura LAY 0,29 e'
     sotto il floor di legge 0,50 (nessuna tecnica la piazza): resta dichiarato,
     col testo che dice l'ORDINE e non la differenza fra gli esiti.

I finti hanno le chiavi e i tipi degli ordini flumine (`size_matched`,
`size_remaining`, `size_cancelled`, `size_lapsed`, `average_price_matched`,
`status` Enum, `order_type.price/size`).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.scalper.scalper_bot import (
    LOCKING,
    QUOTING2,
    ScalperStrategy,
    spezza_uscita,
)
from Betfair.stream.trading.minimi_it import IT_MIN_BACK, IT_MIN_LAY
from Betfair.stream.trading.submin import quota_parcheggio_lontano, rendimento_in_banda


class _Market:
    market_id = "1.259819674"

    def __init__(self):
        self.orders = []
        self.cancelled = []          # (ordine, size_reduction)
        self.blotter = []

    def place_order(self, order, **_kw):
        self.orders.append(order)
        self.blotter.append(order)
        return True

    def cancel_order(self, order, size_reduction=None):
        self.cancelled.append((order, size_reduction))


class _Ordine:
    """Stesse chiavi e tipi di un ordine flumine."""

    def __init__(self, side, price, size, size_matched=0.0, live=False, sel=22):
        self.side = side
        self.selection_id = sel
        self.market_id = "1.259819674"
        self.size_matched = float(size_matched)
        self.average_price_matched = float(price) if size_matched else 0.0
        self.size_remaining = round(size - size_matched, 2) if live else 0.0
        self.size_cancelled = 0.0 if live else round(size - size_matched, 2)
        self.size_lapsed = 0.0
        self.status = OrderStatus.EXECUTABLE if live else OrderStatus.EXECUTION_COMPLETE
        self.order_type = SimpleNamespace(price=float(price), size=float(size),
                                          persistence_type="LAPSE")
        self.trade = None
        self.id = "f%d" % id(self)


def _scalper(events=None):
    kw = {}
    if events is not None:
        kw["event_sink"] = lambda kind, payload: events.append((kind, payload))
    # parametri di produzione delle uscite (scalper_session.VALIDATED_PARAMS)
    return ScalperStrategy(market_filter={}, scalper_params={
        "dry_run": False, "stake": 25.0, "uscite_automatiche": True,
        "exact_exits": True, "size_step": 0.5, "live_min_bet": 2.0}, **kw)


# ------------------------------------------------- la spartizione dell'uscita
@pytest.mark.parametrize("size, diretta, trim", [
    (2.80, 2.00, 0.80),     # R1
    (9.25, 8.50, 0.75),     # R3
    (20.69, 20.00, 0.69),   # R5
    (1.98, 1.00, 0.98),     # R6
    (24.77, 24.00, 0.77),   # pre-dimensione di una close BACK
])
def test_punta_di_chiusura_esatta_al_centesimo(size, diretta, trim):
    """Una PUNTA di chiusura non multipla di 0,50 esce ESATTA: parte diretta a
    multiplo di 0,50 (>= 1,00) + resto fra 0,50 e 0,99 col place-and-trim.
    Prima il resto (< 0,50) era "residuo non piazzabile"."""
    d, t, r = spezza_uscita("BACK", 2.0, size)
    assert (d, t, r) == (pytest.approx(diretta), pytest.approx(trim), 0.0)
    assert round(d + t, 2) == pytest.approx(size)
    assert d >= IT_MIN_BACK and abs(d * 2 - round(d * 2)) < 1e-9   # diretta legale
    assert 0.50 <= t < 1.00                                         # trim legale


def test_banca_di_chiusura_al_centesimo_invariata():
    assert spezza_uscita("LAY", 1.84, 25.14) == (25.14, 0.0, 0.0)
    assert spezza_uscita("LAY", 1.84, 0.70) == (0.0, 0.70, 0.0)
    # sotto il floor di legge (0,50): nessuna tecnica, resta residuo (R4)
    assert spezza_uscita("LAY", 1.67, 0.29) == (0.0, 0.0, 0.29)


def test_punta_multipla_resta_diretta():
    assert spezza_uscita("BACK", 2.0, 25.0) == (25.0, 0.0, 0.0)
    assert spezza_uscita("BACK", 2.0, 0.80) == (0.0, 0.80, 0.0)


# --------------------------------------------- il parcheggio del place-and-trim
def test_scratch_r6_parte_esatto_e_parcheggio_al_minimo_di_giurisdizione():
    """R6: LAY 25 @2,22 abbinata 1,98, scratch BACK 1,98 @2,22: parte BACK 1,00
    diretta + sequenza place-and-trim di 0,98 col parcheggio al minimo della
    fonte unica (1,00), mai 2,00 scritto a mano."""
    s = _scalper()
    m = _Market()
    slot = s._slot(m.market_id, 47972)
    slot.status = LOCKING
    d = s._place(m, 47972, "BACK", 2.22, 1.98, floor_min=False, slot=slot)
    assert d is not None and d.order_type.size == pytest.approx(1.00)
    assert len(slot.submins) == 1
    st = slot.submins[0]["state"]
    assert st.target_size == pytest.approx(0.98)
    assert st.placed_size == pytest.approx(IT_MIN_BACK)
    assert round(d.order_type.size + st.target_size, 2) == pytest.approx(1.98)


@pytest.mark.parametrize("target", [0.50, 0.55, 0.63, 0.70, 0.79])
def test_parcheggio_lay_dentro_la_banda_del_profit_ratio(target):
    """Banca residua fra 0,50 e 0,79: il parcheggio @1,01 sarebbe rifiutato
    INVALID_PROFIT_RATIO (0,70 @1,01 = liability 0,007 -> 0,01, +43 %). Il
    parcheggio va alla quota di `quota_parcheggio_lontano` (in banda)."""
    s = _scalper()
    m = _Market()
    slot = s._slot(m.market_id, 22)
    slot.status = LOCKING
    s._place(m, 22, "LAY", 1.67, target, floor_min=False, slot=slot)
    assert len(slot.submins) == 1
    st = slot.submins[0]["state"]
    assert st.placed_size == pytest.approx(IT_MIN_LAY)
    assert st.prezzo_parcheggio == pytest.approx(quota_parcheggio_lontano("lay", target))
    assert rendimento_in_banda(target, st.prezzo_parcheggio)


# ------------------------------------------------ la pre-dimensione della close
def test_r2_predimensione_close_lay_sotto_il_minimo_esatta_al_centesimo():
    """R2: BACK 25 @1,85 abbinata, close LAY 25 @1,84 in coda. Serve LAY 25,14
    (25 x 1,85 / 1,84). Il +0,14 da solo non e' piazzabile: si piazza LAY 1,14
    alla stessa quota (banca al centesimo, >= 1,00) e si riduce di 1,00 la
    close in coda (cancel parziale: la coda del resto resta). Totale 25,14."""
    events = []
    s = _scalper(events)
    m = _Market()
    eb = _Ordine("BACK", 1.85, 25.0, size_matched=25.0, sel=47973)
    el = _Ordine("LAY", 1.84, 25.0, live=True, sel=47973)
    slot = s._slot(m.market_id, 47973)
    slot.status, slot.entry_back, slot.entry_lay, slot.t_quote = QUOTING2, eb, el, 1_000
    s._manage_maker(m, slot, now=2_000, best_back=1.84, best_lay=1.85,
                    size_back=500.0, size_lay=500.0)
    assert slot.status == LOCKING and slot.close is el
    assert [(o is el, r) for o, r in m.cancelled] == [(True, pytest.approx(1.00))]
    assert len(m.orders) == 1
    top = m.orders[0]
    assert top.side == "LAY" and top.order_type.price == pytest.approx(1.84)
    assert top.order_type.size == pytest.approx(1.14)
    totale = round(25.0 - 1.00 + top.order_type.size, 2)
    assert totale == pytest.approx(25.14)
    # a close abbinata la posizione e' pari al centesimo sui due esiti
    nw = 25.0 * 0.85 - totale * 0.84
    nl = totale - 25.0
    assert abs(nw - nl) <= 0.01


# ------------------------------------------------ il testo del residuo (R4)
def test_r4_testo_del_residuo_dice_l_ordine_non_la_differenza():
    """R4: BACK abbinata 0,29 @1,67: per chiudere servirebbe LAY 0,29 (sotto
    0,50, nessuna tecnica). Il testo dice l'ORDINE (0,29 @1,67), non solo la
    differenza fra gli esiti (0,48), che il trader leggeva come un importo."""
    events = []
    s = _scalper(events)
    slot = s._slot("1.259819674", 22)
    slot.flatten_orders.append(_Ordine("BACK", 1.67, 25.0, size_matched=0.29))
    s._ricorda_residuo(slot, 0.1943, -0.29, quota=1.67)
    msg = [p for k, p in events if k == "residuo_ricordato"][0]["msg"]
    assert "LAY 0.29 @1.67" in msg
    assert "0.48" in msg


# ------------------------------------------------------------------- sniper
@pytest.mark.parametrize("lato, size, diretta, target", [
    ("BACK", 1.98, 1.00, 0.98),      # stessa spartizione del maker
    ("LAY", 0.70, None, 0.70),       # banca 0,70: tutta place-and-trim, in banda
])
def test_sniper_uscita_esatta_parcheggio_dalla_fonte_unica(lato, size, diretta, target):
    """Lo sniper usa la stessa uscita esatta del maker: parte diretta + resto
    col place-and-trim, parcheggio 1,00 (mai 2,00) e LAY in banda."""
    from Betfair.stream.scalper.sniper_bot import SniperStrategy

    s = SniperStrategy(market_filter={}, sniper_params={
        "stake": 10.0, "exact_exits": True, "size_step": 0.5, "live_min_bet": 2.0})
    m = _Market()
    pos = s._p(m.market_id, 47972)
    o = s._place(m, 47972, lato, 2.22, size, floor=False, pos=pos)
    if diretta is None:
        assert o is None
    else:
        assert o is not None and o.order_type.size == pytest.approx(diretta)
    assert len(pos.submins) == 1
    st = pos.submins[0]["state"]
    assert st.target_size == pytest.approx(target)
    assert st.placed_size == pytest.approx(1.00)
    assert st.prezzo_parcheggio == pytest.approx(
        quota_parcheggio_lontano(lato.lower(), target))
