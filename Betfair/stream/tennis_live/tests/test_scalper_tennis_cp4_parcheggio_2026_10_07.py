"""SCALPER TENNIS, CP4 del banco (07/10/2026): il PARCHEGGIO del place-and-trim
non chiede mai piu' di quanto resta da chiudere.

Reperto del coordinatore (prima registrazione tennis vera, 35790089, scenario
`chiusura-abbinata-in-parte`): close LAY 1,68 @1,44 abbinata 0,67 (resto
annullato), flatten LAY 0,98 @1,49 sotto il minimo -> place-and-trim col
PARCHEGGIO LAY 2,00 @1,01. Se il parcheggio si abbinasse (e' il rischio per cui
esiste la guardia-abort di `trading/submin`) sposterebbe il netto di 2,02 quando
da chiudere ne resta 1,46: posizione ROVESCIATA. CP4 x1 "size calcolata sul
CHIESTO, non sull'abbinato".

Causa: `TennisScalperStrategy._place_exact` costruiva lo `SubminState` a mano
con `placed_size=2.0` (il vecchio minimo della PUNTA, prima dei minimi .it del
01/10). Il parcheggio e' il MINIMO di giurisdizione della fonte unica
(`trading/submin.place_min_size` -> `trading/minimi_it`: 1,00 per i due lati),
come gia' fa l'uscita esatta di pro/FLB/swing (`condotta_ordini.UsciteEsatte`).

Qui il bot VERO riceve book veri dal Flumine del runner paper (stesso banco di
`test_cantiere_t_scalper_sequenze_2026_09_28.py`), con la latenza di 1 e di 4
book; l'ordine abbinato in parte e' un ordine di flumine con `size_matched`,
`size_remaining`, `size_cancelled`, `size_lapsed` veri. La regola si misura
con le funzioni del banco (`backtest/chiusura_parziale`: `direzione`,
`tolleranza`, `vivo`, `residuo`, `lato`), cioe' la stessa formula di CP4.
"""
from __future__ import annotations

from typing import Any, List, Tuple

import pytest
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.stream.backtest import chiusura_parziale as CPZ
from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_esatte_2026_09_28 import (  # noqa: F401
    esecuzione_sincrona,
)
from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_via_bot_2026_09_28 import (
    _netto,
    _nessun_vivo,
)
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _control,
    _follow,
    banchi,
    db,
)
from Betfair.stream.tennis_scalper import tennis_scalper_bot as TSB
from Betfair.stream.trading import minimi_it as MI
from Betfair.stream.trading.submin import place_min_size, quota_parcheggio_lontano

N_BOOK = 40


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Latenza di 1 e di 4 book (bet delay e coda del banco piu' lunghi)."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


def _ordine_abbinato_in_parte(b: Any, strat: Any, lato: str, prezzo: float,
                              chiesto: float, abbinato: float) -> Any:
    """Un ordine VERO di flumine nel blotter VERO: chiesto ``chiesto``,
    abbinato ``abbinato`` al prezzo, il resto ANNULLATO (`size_cancelled`),
    esecuzione completa. E' la close a target colpita dal guasto del banco."""
    market = b.fw.markets.markets["1.101"]
    trade = Trade("1.101", 11, 0, strat)
    o = trade.create_order(lato, LimitOrder(prezzo, chiesto))
    o.update_client(b.client)
    o.simulated.matched = [[0, prezzo, abbinato]]
    o.simulated.size_matched = abbinato
    o.simulated.average_price_matched = prezzo
    o.simulated.size_cancelled = round(chiesto - abbinato, 2)
    o.execution_complete()
    market.blotter[o.id] = o
    # chiavi e valori come nel vero (catalogo par.7.27)
    assert o.size_matched == pytest.approx(abbinato)
    assert o.size_remaining == pytest.approx(0.0)
    assert o.size_cancelled == pytest.approx(round(chiesto - abbinato, 2))
    assert o.size_lapsed == pytest.approx(0.0)
    return o


def _scalper_dopo_chiusura_in_parte(db: Any, banchi: Any) -> Tuple[Any, Any, Any, Any, Any]:
    """Scalper tennis del runner paper (uscite esatte), ingressi spenti coi soli
    numeri della UI. Ingresso BACK 2,00 @2,10 abbinato; close LAY 2,00 @2,10
    abbinata IN PARTE (1,40; 0,60 annullati). Da chiudere: netto 0,60 * 2,10 =
    1,26 -> flatten LAY 0,60 al best-lay 2,10, sotto il minimo (place-and-trim)."""
    ctl = _control("101", "tennis_scalper", status="running")
    ctl["params"] = {"min_size": 1e12, "min_flow": 1e12, "exact_exits": True}
    db.controls = [ctl]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    strat = b.session.hosted[("101", "tennis_scalper")]
    assert strat.exact_exits is True
    market = b.fw.markets.markets["1.101"]
    ingresso = b.posizione("101", "tennis_scalper", lato="BACK", prezzo=2.10, size=2.0)
    close = _ordine_abbinato_in_parte(b, strat, "LAY", 2.10, chiesto=2.0, abbinato=1.4)
    slot = strat._slot("1.101", 11)
    slot.entry = ingresso
    slot.entry_side = "BACK"
    slot.close = close
    strat._begin_flatten(slot)
    return b, strat, market, slot, close


def _ordini_sel(market: Any, strat: Any) -> List[Any]:
    return [o for o in market.blotter.strategy_orders(strat)
            if int(getattr(o, "selection_id", -1)) == 11]


def _cp4_su_ogni_ordine_nuovo(b: Any, strat: Any, market: Any, svuota: Any,
                              n: int = N_BOOK) -> Tuple[List[str], List[Any]]:
    """Book al bot; ogni ordine NUOVO della strategia sulla selezione si giudica
    con la regola di CP4 nell'istante in cui Betfair lo vede (all'esecuzione
    del pacchetto): quanto sposterebbe il netto se si abbinasse tutto, piu' il
    residuo delle chiusure vive dallo stesso lato, contro il netto da chiudere."""
    visti = {id(o) for o in _ordini_sel(market, strat)}
    violazioni: List[str] = []
    nuovi: List[Any] = []

    def _giudica() -> None:
        for o in _ordini_sel(market, strat):
            if id(o) in visti or o.bet_id is None:
                continue
            visti.add(id(o))
            nuovi.append(o)
            altri = [x for x in _ordini_sel(market, strat) if x is not o]
            d = CPZ.direzione(altri)
            tol = CPZ.tolleranza(altri + [o])
            la = CPZ.lato(o)
            vive = [x for x in altri if CPZ.lato(x) == la and CPZ.vivo(x)]
            capacita = float(o.order_type.size) * float(o.order_type.price) + sum(
                CPZ.residuo(x) * float(x.order_type.price) for x in vive)
            if capacita > abs(d) * 1.02 + tol:
                violazioni.append(
                    "%s %.2f @%s chiede di spostare il netto di %.2f quando da "
                    "chiudere ne resta %.2f" % (la, float(o.order_type.size),
                                                o.order_type.price, capacita, abs(d)))

    for _ in range(n):
        b.book("101")
        svuota()
        _giudica()
        m = b.fw.markets.markets["1.101"]
        if strat.check_market_book(m, m.market_book):
            strat.process_market_book(m, m.market_book)
    for _ in range(8):
        svuota()
    _giudica()
    return violazioni, nuovi


def test_parcheggio_non_chiede_piu_di_quanto_resta_da_chiudere(db, banchi, differita):
    """Dopo la close abbinata in parte il flatten (LAY 0,60, sotto il minimo)
    passa dal place-and-trim: il parcheggio e' il MINIMO di giurisdizione
    (1,00 @1,01 = 1,01 di netto al peggio), mai 2,00 (2,02 contro 1,26 da
    chiudere: posizione rovesciata se si abbinasse). La chiusura resta esatta."""
    b, strat, market, slot, close = _scalper_dopo_chiusura_in_parte(db, banchi)
    viol, nuovi = _cp4_su_ogni_ordine_nuovo(b, strat, market, differita)
    assert nuovi, "il flatten deve aver mandato almeno un ordine"
    assert viol == [], viol
    # il parcheggio c'e' (la condizione del test e' davvero esposta) ed e' il
    # minimo .it della fonte unica, per il lato della chiusura
    # 08/10 (cantiere 5): il parcheggio LAY sta alla quota della banda del
    # profit-ratio per il resto 0,60 (`quota_parcheggio_lontano`: 1,02), non piu'
    # a 1,01 fisso (0,60 @1,01 = taglio rifiutato da Betfair, INVALID_PROFIT_RATIO)
    park = [o for o in nuovi if float(o.order_type.price) <= 1.031]
    assert park, [(o.side, o.order_type.size, o.order_type.price) for o in nuovi]
    assert float(park[0].order_type.price) == pytest.approx(
        quota_parcheggio_lontano("lay", 0.6))
    assert float(park[0].order_type.price) == pytest.approx(1.02)
    assert float(park[0].order_type.size) == pytest.approx(place_min_size("it", "lay"))
    assert float(park[0].order_type.size) == pytest.approx(MI.IT_MIN_LAY)
    # chiusura PERFETTA: se vince = se perde al centesimo, niente di vivo
    nw, nl = _netto(market, strat)
    assert abs(nw - nl) <= 0.01, (nw, nl)
    assert _nessun_vivo(market, strat) == []
    # la close colpita resta quella: abbinato 1,40, il resto annullato
    assert close.size_matched == pytest.approx(1.4)
    assert close.size_cancelled == pytest.approx(0.6)


# 08/10 (cantiere 5): LAY 0,60 -> 1,02 (banda del profit-ratio), prima 1,01 fisso
@pytest.mark.parametrize("lato,quota", [("LAY", 1.02), ("BACK", 1000.0)])
def test_parcheggio_della_sequenza_e_il_minimo_di_giurisdizione(lato, quota, db, banchi,
                                                               esecuzione_sincrona):
    """Lo stato della sequenza nasce col parcheggio della fonte unica
    (`place_min_size`, cioe' `minimi_it`), per i due lati; prima 2,00 scritto a
    mano. Importo finale invariato; quota del parcheggio dalla fonte unica
    (`quota_parcheggio_lontano`, 08/10 cantiere 5)."""
    b, strat, market, slot, _c = _scalper_dopo_chiusura_in_parte(db, banchi)
    slot.t_last_submin = None
    slot.status = TSB.LOCKING          # una chiusura decisa fuori dall'inseguimento
    o = strat._place_exact(market, 11, lato, 2.10, 0.6, slot)
    assert o is None                    # nessuna parte diretta: tutto in sequenza
    assert len(slot.submins) == 1
    st = slot.submins[0]["state"]
    assert st.placed_size == pytest.approx(place_min_size("it", lato.lower()))
    assert st.placed_size == pytest.approx(MI.IT_MIN_BACK if lato == "BACK" else MI.IT_MIN_LAY)
    assert st.target_size == pytest.approx(0.6)
    assert st.size_reduction == pytest.approx(round(st.placed_size - 0.6, 2))
    assert st.prezzo_parcheggio == pytest.approx(quota)
    assert st.prezzo_parcheggio == pytest.approx(quota_parcheggio_lontano(lato.lower(), 0.6))
