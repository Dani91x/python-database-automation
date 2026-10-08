"""CANTIERE 5 (08/10/2026): il PARCHEGGIO del place-and-trim nei bot TENNIS dalla
fonte unica, come il calcio (cantiere L del 07/10).

Prima i bot tennis parcheggiavano la banca SEMPRE a LAY 1,01 (lo scalper con
`SubminState` costruito a mano senza `park_price`, pro/FLB/swing e il green-up del
worker con `condotta_ordini.UsciteEsatte`, idem). Per un resto fra 0,50 e 0,79 il
taglio lascia una banca a 1,01 con la liability arrotondata FUORI dalla banda
INVALID_PROFIT_RATIO (0,70 @1,01 = 0,007 -> 0,01, +43 %): Betfair rifiuta il taglio
e il resto resta scoperto. Ora:
  * importo del parcheggio = `trading/submin.place_min_size` (1,00);
  * quota = `trading/submin.quota_parcheggio_lontano` (BACK 1000; LAY 0,50 -> 1,02,
    0,70 -> 1,03, 0,79 -> 1,03, 0,80 -> 1,01, 0,99 -> 1,01);
  * nessuna quota sicura -> nessun ordine, riga nell'attivita', resto dichiarato.
Il banco tennis (`certificazione_bot`) riconosce il parcheggio nella banda (B8) e
VERIFICA la quota col nuovo controllo B11.

Qui i bot VERI girano sul runner paper VERO del banco dell'iscrizione a caldo
(Flumine + client paper, esecuzione simulata resa sincrona): parcheggio, taglio
(`cancelOrders` con `sizeReduction`) e rimpiazzo sono quelli di flumine, nessun
fill scritto a mano.
"""
from __future__ import annotations

from typing import Any, List

import pytest

from Betfair.stream.tennis_live import certificazione_bot as CB
from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_esatte_2026_09_28 import (  # noqa: F401
    _BotFinto,
    _MercatoFinto,
    esecuzione_sincrona,
)
from Betfair.stream.tennis_live.tests.test_scalper_tennis_cp4_parcheggio_2026_10_07 import (
    _cp4_su_ogni_ordine_nuovo,
    _scalper_dopo_chiusura_in_parte,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _control,
    _follow,
    banchi,
    db,
)
from Betfair.stream.tennis_scalper import condotta_ordini as CD
from Betfair.stream.tennis_scalper import tennis_scalper_bot as TSB
from Betfair.stream.trading import submin as SM

#: la tabella del cantiere: resto -> quota attesa del parcheggio LAY (dalla regola
#: della banda INVALID_PROFIT_RATIO; la fonte unica la deve dare identica)
TABELLA_LAY = [(0.50, 1.02), (0.70, 1.03), (0.79, 1.03), (0.80, 1.01), (0.99, 1.01)]
RESTI = [r for r, _q in TABELLA_LAY]
BOT_CONDOTTA = ["tennis_pro", "tennis_flb", "tennis_swing"]


def _giri(b: Any, strat: Any, n: int = 8) -> None:
    for _ in range(n):
        b.book("101")
        strat._esatte.avanza(b.fw.markets.markets["1.101"])


def _osservazione(market: Any, strat: Any) -> CB.Osservazione:
    """Le righe del banco dagli ordini VERI del blotter (`riga_ordine`)."""
    righe = [CB.riga_ordine(o) for o in market.blotter.strategy_orders(strat)]
    return CB.Osservazione(bot="t", modalita="live", giurisdizione="it", ordini=righe)


def _b11(oss: CB.Osservazione) -> tuple:
    soll: dict = {}
    viol = [v for v in CB.verifica(oss, soll) if v.codice.startswith("B11")]
    return soll.get("B11", 0), viol


@pytest.fixture(autouse=True)
def _cache_b11_pulita():
    CB._quota_parcheggio_attesa.cache_clear()
    yield
    CB._quota_parcheggio_attesa.cache_clear()


# ---------------------------------------------------------------------------
# la regola pura: una sola fonte
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("resto,quota", TABELLA_LAY)
def test_stato_parcheggio_lay_quota_della_banda(resto, quota):
    st = CD.stato_parcheggio("LAY", 2.10, resto, note="x")
    assert st is not None
    assert st.prezzo_parcheggio == pytest.approx(quota)
    assert st.prezzo_parcheggio == pytest.approx(SM.quota_parcheggio_lontano("lay", resto))
    assert st.placed_size == pytest.approx(SM.place_min_size("it", "lay"))
    assert st.target_size == pytest.approx(resto)
    assert st.size_reduction == pytest.approx(round(st.placed_size - resto, 2))
    # la banca residua dopo il taglio sta DENTRO la banda del profit-ratio
    assert SM.rendimento_in_banda(resto, st.prezzo_parcheggio)


@pytest.mark.parametrize("resto", RESTI)
def test_stato_parcheggio_back_a_1000(resto):
    st = CD.stato_parcheggio("BACK", 2.10, resto, note="x")
    assert st.prezzo_parcheggio == pytest.approx(1000.0)
    assert st.placed_size == pytest.approx(SM.place_min_size("it", "back"))


@pytest.mark.parametrize("resto", [0.50, 0.70, 0.79])
def test_il_vecchio_parcheggio_a_1_01_era_fuori_banda(resto):
    """Il motivo del cantiere: 0,50-0,79 @1,01 = taglio rifiutato da Betfair."""
    assert not SM.rendimento_in_banda(resto, 1.01)


def test_quote_del_parcheggio_lay_dalla_fonte_unica():
    assert CD.QUOTE_PARCHEGGIO_LAY == (1.01, 1.02, 1.03)
    assert CD.QUOTA_PARCHEGGIO_LAY_ALTA == pytest.approx(1.03)
    assert CD.QUOTA_PARCHEGGIO_BACK == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# pro, FLB, swing (UsciteEsatte) sul runner paper vero
# ---------------------------------------------------------------------------
def _bot(db: Any, banchi: Any, bot: str) -> tuple:
    db.controls = [_control("101", bot, status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    return b, b.session.hosted[("101", bot)], b.fw.markets.markets["1.101"]


def _parcheggio_piazzato(o: CD.OrdineComposto) -> Any:
    """Il gradino 1 VERO: il primo ordine del Trade della sequenza."""
    base = o.sequenza.get("order") or o.sequenza["ops"].last_order
    return base.trade.orders[0]


@pytest.mark.parametrize("bot", BOT_CONDOTTA)
@pytest.mark.parametrize("resto,quota", TABELLA_LAY)
def test_uscita_esatta_lay_parcheggia_alla_quota_della_banda(bot, resto, quota, db, banchi,
                                                            esecuzione_sincrona):
    b, strat, market = _bot(db, banchi, bot)
    o = strat._place(market, 11, "LAY", 2.10, resto, copertura=True)
    assert isinstance(o, CD.OrdineComposto) and o.diretto is None
    st = o.sequenza["state"]
    assert st.prezzo_parcheggio == pytest.approx(quota)
    park = _parcheggio_piazzato(o)
    assert park.side == "LAY"
    assert float(park.order_type.price) == pytest.approx(quota)
    assert float(park.order_type.size) == pytest.approx(SM.place_min_size("it", "lay"))


@pytest.mark.parametrize("bot", BOT_CONDOTTA)
def test_uscita_esatta_back_parcheggia_a_1000(bot, db, banchi, esecuzione_sincrona):
    b, strat, market = _bot(db, banchi, bot)
    o = strat._place(market, 11, "BACK", 2.0, 0.70, copertura=True)
    park = _parcheggio_piazzato(o)
    assert float(park.order_type.price) == pytest.approx(1000.0)
    assert float(park.order_type.size) == pytest.approx(SM.place_min_size("it", "back"))


@pytest.mark.parametrize("bot", BOT_CONDOTTA)
def test_sequenza_completa_e_banco_verde(bot, db, banchi, esecuzione_sincrona):
    """LAY 0,70: parcheggio 1,00 @1,03, taglio a 0,70, rimpiazzo @2,10. Il banco
    riconosce la catena (B8 verde) e verifica la quota (B11 sollecitato, verde)."""
    b, strat, market = _bot(db, banchi, bot)
    o = strat._place(market, 11, "LAY", 2.10, 0.70, copertura=True)
    _giri(b, strat)
    assert str(o.sequenza["state"].step.value) == "done"
    park = _parcheggio_piazzato(o)
    assert float(park.order_type.price) == pytest.approx(1.03)
    sost = park.trade.orders[1]
    assert float(sost.order_type.price) == pytest.approx(2.10)
    assert float(sost.order_type.size) == pytest.approx(0.70)
    oss = _osservazione(market, strat)
    assert CB._b8(oss) is None
    n, viol = _b11(oss)
    assert n == 1 and viol == [], viol
    pk = [r["parcheggio"] for r in oss.ordini if r.get("parcheggio")]
    assert pk == [{"lato": "LAY", "quota": 1.03, "residuo": 0.70, "quota_attesa": 1.03}]


def test_vecchio_parcheggio_a_1_01_e_rosso_per_b11(db, banchi, esecuzione_sincrona,
                                                   monkeypatch):
    """FALSIFICAZIONE del cantiere: la condotta di prima (LAY sempre 1,01, cioe'
    `initial_place_price`) con resto 0,70 la deve vedere B11."""
    monkeypatch.setattr(CD, "quota_parcheggio_lontano",
                        lambda side, t: SM.initial_place_price(side))
    b, strat, market = _bot(db, banchi, "tennis_pro")
    o = strat._place(market, 11, "LAY", 2.10, 0.70, copertura=True)
    _giri(b, strat)
    assert float(_parcheggio_piazzato(o).order_type.price) == pytest.approx(1.01)
    n, viol = _b11(_osservazione(market, strat))
    assert n == 1 and len(viol) == 1
    assert "@1.01" in viol[0].dettaglio and "0.70" in viol[0].dettaglio
    assert "1.03" in viol[0].dettaglio


def test_parcheggio_tagliato_in_attesa_del_rimpiazzo_si_giudica(db, banchi,
                                                               esecuzione_sincrona,
                                                               monkeypatch):
    """Parcheggio ridotto e ancora vivo (rimpiazzo non ancora fatto): il resto e'
    size - size_cancelled. Quota giusta verde; 1,01 rossa."""
    b, strat, market = _bot(db, banchi, "tennis_flb")
    o = strat._place(market, 11, "LAY", 2.10, 0.70, copertura=True)
    park = _parcheggio_piazzato(o)
    for _ in range(6):
        if park.size_cancelled > 0:
            break
        _giri(b, strat, n=1)
    assert park.size_cancelled == pytest.approx(0.30)
    assert CD.ordine_vivo(park) and len(park.trade.orders) == 1
    oss = _osservazione(market, strat)
    assert [r["parcheggio"] for r in oss.ordini if r.get("parcheggio")] == [
        {"lato": "LAY", "quota": 1.03, "residuo": 0.70, "quota_attesa": 1.03}]
    assert _b11(oss) == (1, [])


def test_b11_senza_quota_sicura_il_parcheggio_e_rosso(db, banchi, esecuzione_sincrona,
                                                      monkeypatch):
    """Se la fonte unica non ha una quota sicura per il resto, NESSUN parcheggio
    doveva partire: B11 rosso su quello che c'e'."""
    b, strat, market = _bot(db, banchi, "tennis_swing")
    strat._place(market, 11, "LAY", 2.10, 0.70, copertura=True)
    _giri(b, strat)
    monkeypatch.setattr(SM, "quota_parcheggio_lontano", lambda side, t: None)
    CB._quota_parcheggio_attesa.cache_clear()
    n, viol = _b11(_osservazione(market, strat))
    assert n == 1 and len(viol) == 1 and "nessuna quota" in viol[0].dettaglio


# ---------------------------------------------------------------------------
# caso None: nessun ordine, riga nell'attivita', resto dichiarato
# ---------------------------------------------------------------------------
def test_uscite_esatte_senza_quota_sicura_nessun_ordine(monkeypatch):
    monkeypatch.setattr(CD, "quota_parcheggio_lontano", lambda side, t: None)

    def _mai(*a, **k):
        raise AssertionError("nessun passo della sequenza doveva partire")
    monkeypatch.setattr(SM, "advance_submin", _mai)
    bot = _BotFinto()
    dichiarati: List[tuple] = []

    class _Memoria:
        def dichiara(self, *a: Any) -> None:
            dichiarati.append(a)
    bot.residui_ricordati = _Memoria()
    ue = CD.UsciteEsatte(bot, bot._emit)
    assert ue.piazza(_MercatoFinto(), 11, "LAY", 2.10, 0.70, diretto=lambda s: None) is None
    assert ue.attive == []
    righe = [p for k, p in bot.eventi if k == "uscita_esatta_senza_parcheggio"]
    assert len(righe) == 1 and righe[0]["level"] == "CRITICAL"
    assert righe[0]["scoperto"] == 0.70 and righe[0]["lato"] == "LAY"
    assert len(dichiarati) == 1 and dichiarati[0][2:4] == ("LAY", 0.70)


def test_uscite_esatte_senza_quota_sicura_la_parte_diretta_parte(monkeypatch):
    """Senza quota sicura per il resto, la parte DIRETTA parte comunque e il
    composto porta solo quella (nessuna sequenza). Oggi `spezza_esatta` non da' mai
    parte diretta E resto >= 0,50 insieme: la spartizione si forza per esercitare
    il ramo."""
    monkeypatch.setattr(CD, "quota_parcheggio_lontano", lambda side, t: None)
    bot = _BotFinto()
    ue = CD.UsciteEsatte(bot, bot._emit)
    # nessuna combinazione reale ha parte diretta E resto >= 0,50 (spezza_esatta):
    # il ramo "parte > 0" si esercita forzando la spartizione
    monkeypatch.setattr(CD, "spezza_esatta", lambda size, side: (1.0, 0.7))
    diretto = object()
    o = ue.piazza(_MercatoFinto(), 11, "BACK", 2.0, 1.7, diretto=lambda s: diretto)
    assert o is not None and o.diretto is diretto and o.sequenza is None
    assert [k for k, _p in bot.eventi] == ["uscita_esatta_senza_parcheggio"]


# ---------------------------------------------------------------------------
# scalper tennis (`_place_exact` / `_drive_submins` / flatten)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lato", ["LAY", "BACK"])
@pytest.mark.parametrize("resto,quota", TABELLA_LAY)
def test_scalper_place_exact_parcheggio_dalla_fonte_unica(lato, resto, quota, db, banchi,
                                                          esecuzione_sincrona):
    b, strat, market, slot, _c = _scalper_dopo_chiusura_in_parte(db, banchi)
    slot.t_last_submin = None
    slot.status = TSB.LOCKING
    assert strat._place_exact(market, 11, lato, 2.10, resto, slot) is None
    assert len(slot.submins) == 1
    st = slot.submins[0]["state"]
    attesa = quota if lato == "LAY" else 1000.0
    assert st.prezzo_parcheggio == pytest.approx(attesa)
    assert st.placed_size == pytest.approx(SM.place_min_size("it", lato.lower()))
    assert st.target_size == pytest.approx(resto)
    # il gradino 1 VERO a mercato
    strat._drive_submins(market, slot, 0)
    park = slot.submins[0]["order"] if slot.submins else None
    park = park or slot.submins[0]["ops"].last_order
    assert float(park.order_type.price) == pytest.approx(attesa)
    assert float(park.order_type.size) == pytest.approx(SM.place_min_size("it", lato.lower()))


def test_scalper_senza_quota_sicura_nessun_ordine(db, banchi, esecuzione_sincrona,
                                                  monkeypatch):
    b, strat, market, slot, _c = _scalper_dopo_chiusura_in_parte(db, banchi)
    eventi: List[tuple] = []
    monkeypatch.setattr(strat, "_emit", lambda k, **p: eventi.append((k, p)))
    monkeypatch.setattr(SM, "quota_parcheggio_lontano", lambda side, t: None)
    slot.t_last_submin = None
    slot.status = TSB.LOCKING
    prima = len(list(market.blotter.strategy_orders(strat)))
    assert strat._place_exact(market, 11, "LAY", 2.10, 0.70, slot) is None
    assert slot.submins == []
    assert len(list(market.blotter.strategy_orders(strat))) == prima
    assert slot.resto_np == ("LAY", 0.70, 2.10) and slot.residual_ok is True
    skip = [p for k, p in eventi if k == "min_bet_skip"]
    assert len(skip) == 1 and skip[0]["size"] == 0.70 and "banda" in skip[0]["motivo"]


def test_scalper_flatten_completa_col_parcheggio_a_1_02_e_banco_verde(db, banchi,
                                                                      esecuzione_sincrona):
    """Il caso del CP4 (35790089): flatten LAY 0,60 -> parcheggio 1,00 @1,02. Il
    flatten NON lo scambia per una chiusura stantia (la soglia segue la banda) e
    la sequenza arriva al rimpiazzo; il banco: B8 e B11 verdi, B11 sollecitato."""
    b, strat, market, slot, _c = _scalper_dopo_chiusura_in_parte(db, banchi)
    viol, nuovi = _cp4_su_ogni_ordine_nuovo(b, strat, market, lambda: None)
    assert viol == [], viol
    park = [o for o in nuovi if float(o.order_type.price) < 1.1]
    assert len(park) == 1 and float(park[0].order_type.price) == pytest.approx(1.02)
    assert len(park[0].trade.orders) == 2, "il rimpiazzo e' avvenuto"
    oss = _osservazione(market, strat)
    assert CB._b8(oss) is None
    n, v = _b11(oss)
    assert n == 1 and v == [], v


# ---------------------------------------------------------------------------
# il riconoscimento del banco (B8): la banda, non la sola 1,01
# ---------------------------------------------------------------------------
def _ordine_finto(side: str, prezzo: float, size: float, cancellato: float = 0.0) -> Any:
    """Le stesse chiavi del finto di B8 (`test_cantiere_d2_chiusure_esatte`)."""
    from types import SimpleNamespace

    from flumine.order.order import OrderStatus

    return SimpleNamespace(id=str(id(object())), bet_id=None, status=OrderStatus.EXECUTABLE,
                           side=side, selection_id=11, market_id="1.101",
                           order_type=SimpleNamespace(price=prezzo, size=size),
                           size_matched=0.0, size_remaining=size - cancellato,
                           size_cancelled=cancellato, size_lapsed=0.0, size_voided=0.0,
                           average_price_matched=0.0, customer_order_ref=None,
                           violation_msg=None, trade=None)


def _in_trade(*ordini: Any) -> list:
    from types import SimpleNamespace

    tr = SimpleNamespace(orders=list(ordini))
    for o in ordini:
        o.trade = tr
    return list(ordini)


@pytest.mark.parametrize("quota,riconosciuto", [(1.01, True), (1.02, True), (1.03, True),
                                                (1.04, False), (1.10, False)])
def test_b8_sostituto_di_un_parcheggio_lay_nella_banda(quota, riconosciuto):
    park, sost = _in_trade(_ordine_finto("LAY", quota, 1.0, cancellato=1.0),
                           _ordine_finto("LAY", 2.10, 0.70))
    assert CB.sostituto_di_parcheggio(sost) is riconosciuto
