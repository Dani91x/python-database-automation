"""SCALPER CALCIO (maker e sniper): il residuo sotto 0,50 si chiude con DUE ordini
legali e il tetto di perdita conta solo le perdite vere (07/10/2026).

Decisioni dell'utente del 07/10 (testuali "1) b 2) b"):
  1) C3, ingresso abbinato sotto 0,50 (R4 del replay 35797769: BACK abbinata 0,29
     @1,67, per chiudere servirebbe LAY 0,29, sotto il floor di legge 0,50):
     si chiude con DUE ordini legali. Prima un ordine di SCAVALCO dal lato
     opposto (punta 1,00, il minimo della fonte unica, alla miglior quota),
     poi la banca al centesimo calcolata dal flatten coi prezzi ABBINATI veri
     (R4: punta 1,00 @1,66 + banca 1,28 @1,67 -> piatto al centesimo);
  2) il tetto di perdita (`event_loss_cap`) NON conta i residui non chiudibili:
     solo le perdite vere dei cicli chiusi.

Finti con le chiavi e i tipi degli ordini flumine (`size_matched`,
`size_remaining`, `size_cancelled`, `size_lapsed`, `average_price_matched`,
`status` Enum, `order_type.price/size`).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.scalper.scalper_bot import (
    DONE,
    FLATTENING,
    ScalperStrategy,
    compute_green,
    ordine_di_scavalco,
    spezza_uscita,
)


class _Market:
    market_id = "1.259819674"

    def __init__(self):
        self.orders = []
        self.cancelled = []
        self.blotter = []

    def place_order(self, order, **_kw):
        self.orders.append(order)
        self.blotter.append(order)
        return True

    def cancel_order(self, order, size_reduction=None):
        self.cancelled.append((order, size_reduction))


class _Ordine:
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


def _netto(ordini):
    sb = sum(o.size_matched for o in ordini if o.side == "BACK")
    sl = sum(o.size_matched for o in ordini if o.side == "LAY")
    nw = sum(o.size_matched * (o.average_price_matched - 1) for o in ordini if o.side == "BACK") \
        - sum(o.size_matched * (o.average_price_matched - 1) for o in ordini if o.side == "LAY")
    return nw, sl - sb


def _scalper(events=None, **over):
    p = {"dry_run": False, "stake": 25.0, "uscite_automatiche": True,
         "exact_exits": True, "size_step": 0.5, "live_min_bet": 2.0}
    p.update(over)
    kw = {}
    if events is not None:
        kw["event_sink"] = lambda kind, payload: events.append((kind, payload))
    return ScalperStrategy(market_filter={}, scalper_params=p, **kw)


# ------------------------------------------------------- la regola, pura
def test_r4_scavalco_punta_1_poi_banca_al_centesimo_piatto():
    """R4: BACK abbinata 0,29 @1,67 (se vince +0,19, se perde -0,29). Lo scavalco
    e' una PUNTA 1,00 alla miglior quota di punta (1,66); abbinata, il flatten
    chiude con una BANCA diretta al centesimo (1,28 @1,67): piatto."""
    entrata = _Ordine("BACK", 1.67, 25.0, size_matched=0.29)
    nw, nl = _netto([entrata])
    sc = ordine_di_scavalco(nw, nl, best_back=1.66, best_lay=1.67)
    assert sc == ("BACK", pytest.approx(1.66), pytest.approx(1.00))
    scavalco = _Ordine("BACK", 1.66, 1.00, size_matched=1.00)
    nw2, nl2 = _netto([entrata, scavalco])
    lato, size, _ = compute_green(nw2, nl2, 1.67)
    banca = round(size, 2)
    assert lato == "LAY" and banca == pytest.approx(1.28)
    assert spezza_uscita("LAY", 1.67, banca) == (banca, 0.0, 0.0)     # diretta
    chiusura = _Ordine("LAY", 1.67, banca, size_matched=banca)
    nw3, nl3 = _netto([entrata, scavalco, chiusura])
    assert abs(nw3 - nl3) <= 0.02                                       # piatto


def test_scavalco_della_posizione_corta_porta_la_punta_a_un_importo_chiudibile():
    """Posizione corta che chiederebbe una PUNTA sotto 0,50: lo scavalco e' una
    BANCA al centesimo (>= 1,00) dimensionata perche' la punta di chiusura venga
    ~2,00 (chiudibile al centesimo: diretta multipla + resto 0,50-0,99)."""
    entrata = _Ordine("LAY", 1.67, 25.0, size_matched=0.29)
    nw, nl = _netto([entrata])
    lato, piccola, _ = compute_green(nw, nl, 1.66)
    assert lato == "BACK" and piccola < 0.50
    sc = ordine_di_scavalco(nw, nl, best_back=1.66, best_lay=1.67)
    assert sc[0] == "LAY" and sc[1] == pytest.approx(1.67) and sc[2] >= 1.00
    scavalco = _Ordine("LAY", 1.67, sc[2], size_matched=sc[2])
    nw2, nl2 = _netto([entrata, scavalco])
    lato2, size2, _ = compute_green(nw2, nl2, 1.66)
    d, t, r = spezza_uscita("BACK", 1.66, round(size2, 2))
    assert lato2 == "BACK" and r == 0.0 and round(d + t, 2) == round(size2, 2)


def test_scavalco_none_senza_prezzi():
    assert ordine_di_scavalco(0.19, -0.29, best_back=None, best_lay=1.67) is None
    assert ordine_di_scavalco(-0.19, 0.29, best_back=1.66, best_lay=None) is None


# ------------------------------------------------------- maker, nel flatten vero
def test_r4_maker_flatten_manda_lo_scavalco_non_dichiara_il_residuo():
    events = []
    s = _scalper(events)
    m = _Market()
    slot = s._slot(m.market_id, 22)
    slot.status = FLATTENING
    slot.flatten_orders.append(_Ordine("BACK", 1.67, 25.0, size_matched=0.29))
    s._drive_flatten(m, slot, best_back=1.66, best_lay=1.67, now=10_000)
    kinds = [k for k, _ in events]
    assert "residuo_ricordato" not in kinds
    assert slot.status == FLATTENING and not slot.residual_ok
    assert len(m.orders) == 1
    o = m.orders[0]
    assert (o.side, o.order_type.price, o.order_type.size) == ("BACK", 1.66, 1.00)
    assert "scavalco" in kinds


def test_maker_scavalco_ha_un_tetto_poi_dichiara():
    """Nessun loop: oltre il tetto di scavalchi del ciclo il residuo si dichiara
    come prima (CP4)."""
    events = []
    s = _scalper(events)
    m = _Market()
    slot = s._slot(m.market_id, 22)
    slot.status = FLATTENING
    slot.flatten_orders.append(_Ordine("BACK", 1.67, 25.0, size_matched=0.29))
    slot.scavalchi = s._SCAVALCHI_MAX_PER_CICLO
    slot.flat_tries = 13
    s._drive_flatten(m, slot, best_back=1.66, best_lay=1.67, now=10_000)
    assert m.orders == []
    assert slot.status == DONE and slot.residual_ok


# ------------------------------------------------------- sniper
def test_sniper_r4_flatten_manda_lo_scavalco():
    from Betfair.stream.scalper.sniper_bot import SniperStrategy

    ev = []
    s = SniperStrategy(market_filter={}, sniper_params={
        "stake": 10.0, "exact_exits": True, "size_step": 0.5, "live_min_bet": 2.0},
        event_sink=lambda k, p: ev.append((k, p)))
    m = _Market()
    pos = s._p(m.market_id, 47972)
    pos.flattening = True
    pos.flatten_orders.append(_Ordine("BACK", 2.22, 10.0, size_matched=0.21, sel=47972))
    s._drive_flatten(m, pos, 2.20, 2.22, 10.0)
    kinds = [k for k, _ in ev]
    assert "residuo_ricordato" not in kinds and "sniper_flat_residual" not in kinds
    assert pos.flattening
    assert [(o.side, o.order_type.price, o.order_type.size) for o in m.orders] == [
        ("BACK", 2.2, 1.0)]


# ------------------------------------------------------- tetto di perdita
def test_tetto_non_conta_i_residui_non_chiudibili():
    """Decisione 2: un residuo accettato non entra nel tetto di perdita."""
    events = []
    s = _scalper(events, exact_exits=False, size_step=0.5, live_min_bet=1.0,
                 event_loss_cap=0.5)
    m = _Market()
    slot = s._slot(m.market_id, 42)
    slot.status = FLATTENING
    slot.flatten_orders.append(_Ordine("LAY", 4.0, 0.20, size_matched=0.20, sel=42))
    slot.flat_tries = 13
    s._drive_flatten(m, slot, best_back=4.0, best_lay=4.1, now=10_000)
    assert slot.residual_ok and s.stats["pnl_locked"] == pytest.approx(-0.60)
    assert s.stats["pnl_residui"] == pytest.approx(-0.60)
    assert s._check_event_guards() is False and not s.force_flat
    # una perdita VERA oltre il tetto lo fa scattare
    s.stats["pnl_locked"] -= 0.60
    assert s._check_event_guards() is True and s.force_flat
    cap = [p for k, p in events if k == "loss_cap"][0]
    assert cap["locked"] == pytest.approx(-0.60)
    assert "residui" in cap["msg"]


def test_sniper_tetto_non_conta_i_residui():
    from Betfair.stream.scalper.sniper_bot import SniperStrategy

    s = SniperStrategy(market_filter={}, sniper_params={"stake": 10.0,
                                                       "event_loss_cap": 1.0})
    s.stats["pnl_locked"] = -1.20
    s.stats["pnl_residui"] = -1.20
    assert s._loss_capped() is False
    s.stats["pnl_locked"] = -2.30
    assert s._loss_capped() is True


# ------------------------------------- dopo lo scavalco: size al prezzo migliore
def test_dopo_lo_scavalco_la_chiusura_si_dimensiona_al_best_non_al_limite_inseguito():
    """Reperto del coordinatore (07/10, test S3 a prezzi assenti, latenza 1): con
    il flatten che insegue (8 tick oltre il best) la chiusura dopo lo scavalco era
    dimensionata al LIMITE (LAY @2,38) e si abbinava al best (2,22): restava un
    nuovo resto sotto 0,50, altri scavalchi, poi residuo 0,07 dichiarato. Dopo uno
    scavalco la size si calcola al best (prezzo d'abbinamento atteso), il limite
    resta inseguito."""
    s = _scalper()
    m = _Market()
    slot = s._slot(m.market_id, 22)
    slot.status = FLATTENING
    slot.flatten_orders.append(_Ordine("LAY", 2.22, 25.0, size_matched=25.0))
    slot.flatten_orders.append(_Ordine("BACK", 2.20, 26.5, size_matched=26.5))
    slot.scavalchi = 1
    slot.flat_tries = 9
    nw, nl = s._net_position(slot)
    assert nw > nl
    s._drive_flatten(m, slot, best_back=2.20, best_lay=2.22, now=10_000)
    assert len(m.orders) == 1
    o = m.orders[0]
    assert o.side == "LAY" and o.order_type.price > 2.22            # limite inseguito
    assert o.order_type.size == pytest.approx(round((nw - nl) / 2.22, 2))


def test_sniper_dopo_lo_scavalco_size_al_best():
    from Betfair.stream.scalper.sniper_bot import SniperStrategy

    s = SniperStrategy(market_filter={}, sniper_params={
        "stake": 10.0, "exact_exits": True, "size_step": 0.5, "live_min_bet": 2.0})
    m = _Market()
    pos = s._p(m.market_id, 47972)
    pos.flattening = True
    pos.flatten_orders.append(_Ordine("LAY", 2.22, 25.0, size_matched=25.0, sel=47972))
    pos.flatten_orders.append(_Ordine("BACK", 2.20, 26.5, size_matched=26.5, sel=47972))
    pos.scavalchi = 1
    pos.flat_tries = 8
    nw, nl = _netto(pos.flatten_orders)
    s._drive_flatten(m, pos, 2.20, 2.22, 10.0)
    assert len(m.orders) == 1
    o = m.orders[0]
    assert o.side == "LAY" and o.order_type.price > 2.22
    assert o.order_type.size == pytest.approx(round((nw - nl) / 2.22, 2))


# ------------------------- 07/10 sera: OGNI flatten inseguito si dimensiona al best
def test_r5_il_resto_non_veniva_dal_limite_ma_dalla_spartizione():
    """R5 (35797769, 17:36:32, sel 47973), numeri della diagnostica: LAY 25 @1,85
    abbinata, close BACK 4,54 @1,85 abbinata, stop a 1 tick -> primo flatten
    (flat_tries 0, cross 0) BACK @1,83 = best di punta, abbinato a 1,83. Limite e
    best COINCIDONO: la chiusura giusta e' 20,68 in entrambi i modi. Il resto 0,18
    veniva dalla spartizione (20,50 + 0,18 "residuo", corretta il 07/10: 20,00 +
    0,68 col place-and-trim), NON dal dimensionamento al limite."""
    s = _scalper()
    m = _Market()
    slot = s._slot(m.market_id, 47973)
    slot.status = FLATTENING
    slot.flatten_orders.append(_Ordine("LAY", 1.85, 25.0, size_matched=25.0, sel=47973))
    slot.flatten_orders.append(_Ordine("BACK", 1.85, 25.0, size_matched=4.54, sel=47973))
    nw, nl = s._net_position(slot)
    assert round((nl - nw) / 1.83, 2) == pytest.approx(20.68)
    s._drive_flatten(m, slot, best_back=1.83, best_lay=1.84, now=10_000)
    o = m.orders[0]
    # parte diretta subito; il resto 0,68 col place-and-trim al giro dopo (nel
    # flatten la sequenza aspetta che la parte diretta sia partita: anti-cascata)
    assert (o.side, o.order_type.price, o.order_type.size) == ("BACK", 1.83, 20.0)
    assert spezza_uscita("BACK", 1.83, 20.68) == (20.0, pytest.approx(0.68), 0.0)


@pytest.mark.parametrize("flat_tries", [3, 9])
def test_flatten_inseguito_si_dimensiona_al_best_anche_senza_scavalco(flat_tries):
    """Ordine del coordinatore (07/10 sera): in OGNI flatten che insegue la size si
    calcola al best del lato di chiusura (dove Betfair abbina), il limite resta
    inseguito. LAY 25 @2,22 abbinata: chiusura BACK al best 2,20 = 25,23, il
    limite scende di N tick."""
    s = _scalper()
    m = _Market()
    slot = s._slot(m.market_id, 22)
    slot.status = FLATTENING
    slot.flatten_orders.append(_Ordine("LAY", 2.22, 25.0, size_matched=25.0))
    slot.flat_tries = flat_tries
    s._drive_flatten(m, slot, best_back=2.20, best_lay=2.22, now=10_000)
    o = m.orders[0]
    assert o.side == "BACK" and o.order_type.price < 2.20          # limite inseguito
    giusta = round(25.0 * 2.22 / 2.20, 2)                            # 25,23 al best
    assert o.order_type.size == pytest.approx(spezza_uscita("BACK", 2.20, giusta)[0])


def test_abbinato_a_prezzo_peggiore_lascia_un_resto_che_il_giro_dopo_chiude():
    """Book al best senza liquidita' per tutta la size: la chiusura (25,23 al best
    2,20) si abbina in parte a prezzi peggiori (media 2,16). Il resto si chiude
    al giro successivo come oggi: un ordine nuovo dallo stesso lato, piatto al
    centesimo quando si abbina."""
    s = _scalper()
    m = _Market()
    slot = s._slot(m.market_id, 22)
    slot.status = FLATTENING
    lay = _Ordine("LAY", 2.22, 25.0, size_matched=25.0)
    back = _Ordine("BACK", 2.04, 25.23, size_matched=25.23)
    back.average_price_matched = 2.05
    slot.flatten_orders += [lay, back]
    slot.flat_tries = 2
    nw, nl = s._net_position(slot)
    assert abs(nw - nl) > 0.5
    s._drive_flatten(m, slot, best_back=2.16, best_lay=2.18, now=20_000)
    assert m.orders, "il resto deve essere chiuso al giro dopo"
    o = m.orders[0]
    tot = round((nl - nw) / 2.16, 2)                 # il resto, al best di adesso
    d, t, r = spezza_uscita("BACK", 2.16, tot)
    assert o.side == "BACK" and o.order_type.size == pytest.approx(d) and r == 0.0
    chiusura = _Ordine("BACK", 2.16, tot, size_matched=tot)
    w, l = _netto([lay, back, chiusura])
    assert abs(w - l) <= 0.02


def test_sniper_flatten_inseguito_si_dimensiona_al_best_anche_senza_scavalco():
    from Betfair.stream.scalper.sniper_bot import SniperStrategy

    s = SniperStrategy(market_filter={}, sniper_params={
        "stake": 10.0, "exact_exits": True, "size_step": 0.5, "live_min_bet": 2.0})
    m = _Market()
    pos = s._p(m.market_id, 47972)
    pos.flattening = True
    pos.flatten_orders.append(_Ordine("BACK", 2.22, 10.0, size_matched=10.0, sel=47972))
    pos.flat_tries = 8
    s._drive_flatten(m, pos, 2.20, 2.22, 10.0)
    o = m.orders[0]
    assert o.side == "LAY" and o.order_type.price > 2.22            # limite inseguito
    assert o.order_type.size == pytest.approx(10.0)                 # 10 x 2,22 / 2,22
