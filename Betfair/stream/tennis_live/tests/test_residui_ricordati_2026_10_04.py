# -*- coding: utf-8 -*-
"""DECISIONE 1 DELL'UTENTE (04/10): il residuo che Betfair .it non accetta.

Testuale: «1) a» + «IL RESIDUO RESTA RICORDATO E LO CHIUDO IO». Un residuo la cui
chiusura richiede un ordine sotto 0,50 EUR (floor di legge del place-and-trim,
`trading/minimi_it.SUBMIN_IMPORTO_FINALE_MIN`) si DICHIARA una volta (una riga
CRITICAL per episodio, con la proposta), il bot RIPRENDE a operare e il residuo
resta RICORDATO (stats del bot) finche' torna pari o il mercato si regola.

Prima (replay 35794049, CERTIFICAZIONE_TENNIS_PRO_SCALPER): il PRO rimandava ogni
30 s un place-and-trim da 0,02-0,06 rifiutato (~200 sequenze, 181 CRITICAL) e restava
CLOSING per tutta la partita; lo SCALPER restava FLATTENING.

Finti: bot, mercato, Flumine e ordini VERI del banco del runner paper
(`test_tennis_iscrizione_a_caldo`), esecuzione differita come la latenza del replay.
"""
from __future__ import annotations

from typing import Any, List

import pytest
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_esatte_2026_09_28 import (  # noqa: F401
    _BotFinto,
    _MercatoFinto,
    esecuzione_sincrona,
)
from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_via_bot_2026_09_28 import (
    _netto,
    _nessun_vivo,
)
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    _giri,
    _pro_in_closing,
    esecuzione_differita,
)
from Betfair.stream.tennis_live.tests.test_cantiere_t_scalper_sequenze_2026_09_28 import (
    _giri_con_invariante,
    _scalper_in_flatten,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    banchi,
    db,
)
from Betfair.stream.tennis_scalper import condotta_ordini as CD
from Betfair.stream.tennis_scalper import tennis_pro_bot as PRO
from Betfair.stream.tennis_scalper import tennis_scalper_bot as TSB
from Betfair.stream.trading import minimi_it as MIN


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


def _critiche(eventi: List[tuple], kind: str = "residuo_non_piazzabile") -> List[dict]:
    return [p for k, p in eventi if k == kind]


# --------------------------------------------------------------------------- memoria
def test_residuo_dichiarato_una_volta_ricordato_poi_chiuso_o_regolato():
    bot = _BotFinto()
    r = CD.ResiduiRicordati(bot._emit)
    assert r.dichiara("1.101", 11, "BACK", 0.05, 2.0, -0.10, 0.0) is True
    assert r.dichiara("1.101", 11, "BACK", 0.05, 2.02, -0.10, 0.0) is False   # stesso episodio
    crit = _critiche(bot.eventi)
    assert len(crit) == 1 and crit[0]["level"] == "CRITICAL"
    assert crit[0]["proposta"] == {"azione": "chiudi a mano", "lato": "BACK", "importo": 0.05,
                                   "quota": 2.0, "selection_id": 11, "market_id": "1.101"}
    assert r.per_stats()[0]["sbilancio"] == 0.1 and r.sbilancio("1.101", 11) == 0.1
    r.aggiorna("1.101", 11, -0.11, 0.0)          # ancora sbilanciato: resta
    assert r.sbilancio("1.101", 11) == 0.11
    r.aggiorna("1.101", 11, -0.018, 0.0)         # sotto 0,02 ma non pari: resta
    assert r.sbilancio("1.101", 11) == 0.02
    r.aggiorna("1.101", 11, 0.005, 0.0)          # tornato pari (lo ha chiuso qualcuno)
    assert r.per_stats() == [] and [k for k, _ in bot.eventi].count("residuo_chiuso") == 1
    r.dichiara("1.101", 22, "LAY", 0.3, 15.0, 4.2, -0.3)
    r.regola_mercato("1.101")
    assert r.per_stats() == [] and [k for k, _ in bot.eventi].count("residuo_regolato") == 1


# --------------------------------------------------------------------------- UsciteEsatte
def test_nessun_place_and_trim_con_finale_sotto_il_floor(monkeypatch):
    from Betfair.stream.trading import submin as SM

    chiamate = []
    monkeypatch.setattr(SM, "advance_submin", lambda m, st, **k: chiamate.append(1) or st)
    bot = _BotFinto()
    ue = CD.UsciteEsatte(bot, bot._emit)
    m = _MercatoFinto()
    diretti: List[float] = []

    def _diretto(s: float) -> Any:
        diretti.append(s)
        return object()
    floor = float(MIN.SUBMIN_IMPORTO_FINALE_MIN)
    # BACK 1,37 = 1,00 diretti + 0,37 (sotto il floor): solo la parte diretta
    o = ue.piazza(m, 11, "BACK", 2.0, 1.37, diretto=_diretto)
    assert o is not None and o.sequenza is None and diretti == [1.0]
    assert o.order_type.size == 1.0
    # BACK 0,30 tutto sotto il floor: niente ordine, niente sequenza
    assert ue.piazza(m, 11, "BACK", 2.0, round(floor - 0.2, 2), diretto=_diretto) is None
    assert chiamate == [] and ue.attive == []
    # al floor esatto il place-and-trim e' legale e parte
    assert ue.piazza(m, 11, "BACK", 2.0, floor, diretto=_diretto) is not None
    assert chiamate == [1]


def test_done_senza_sostituto_a_mercato_e_una_sequenza_fallita(monkeypatch):
    """`advance_submin` dichiara DONE anche se il replace e' stato rifiutato
    (flumine live: nessun sostituto, resta il parcheggio annullato a 1000):
    `UsciteEsatte` lo conta come FALLITO (anti-cascata che raddoppia)."""
    from dataclasses import replace as _r

    from Betfair.stream.trading import submin as SM

    bot = _BotFinto()

    def _done_col_parcheggio(market, state, **k):
        park = Trade(market_id="1.101", selection_id=11, handicap=0.0,
                     strategy=bot).create_order(
            side="BACK", order_type=LimitOrder(price=1000.0, size=1.0))
        park.execution_complete()             # annullato dal replace fallito
        k["ops"].last_order = park
        return _r(state, step=SM.SubminStep.DONE)
    monkeypatch.setattr(SM, "advance_submin", _done_col_parcheggio)
    ue = CD.UsciteEsatte(bot, bot._emit)
    o = ue.piazza(_MercatoFinto(), 11, "BACK", 2.0, 0.7, diretto=lambda s: None)
    assert o is not None and str(o.sequenza["state"].step.value) == "aborted"
    assert ue.intervallo_s(("1.101", 11)) == 60      # fallita: 30 -> 60
    assert [k for k, _ in bot.eventi].count("uscita_esatta_abort") == 1


# --------------------------------------------------------------------------- PRO
def test_pro_residuo_sotto_il_floor_dichiarato_flat_e_riprende(db, banchi, differita,
                                                              monkeypatch):
    """LAY 1,00 @2,10 scoperta: copertura BACK 1,05 al best-back 2,00 = 1,00
    diretti + 0,05 di residuo. Il PRO copre 1,00, NON manda nessun place-and-trim,
    dichiara il residuo UNA volta e torna FLAT (puo' riaprire)."""
    from Betfair.stream.trading import submin as SM

    sequenze = []
    vero = SM.advance_submin
    monkeypatch.setattr(SM, "advance_submin",
                        lambda *a, **k: sequenze.append(1) or vero(*a, **k))
    b, strat, market = _pro_in_closing(db, banchi, [("LAY", 2.10, 1.0)], retry_subito=False)
    eventi: List[tuple] = []
    strat.event_sink = lambda k, p: eventi.append((k, dict(p)))
    viol = _giri(b, strat, differita, n=40)
    assert viol == [], viol[:3]
    assert strat._trade["1.101"]["state"] == PRO.FLAT, (eventi, _netto(market, strat))
    assert sequenze == []                                  # mai un place-and-trim
    assert _nessun_vivo(market, strat) == []
    crit = _critiche(eventi)
    assert len(crit) == 1 and crit[0]["importo"] == 0.05 and crit[0]["lato"] == "BACK"
    nw, nl = _netto(market, strat)
    assert abs(nw - nl) == pytest.approx(0.05 * 2.0, abs=0.011)
    assert strat.stats["residui_ricordati"][0]["importo"] == 0.05
    # mercato regolato: il residuo esce dalla memoria
    strat.process_closed_market(market, market.market_book)
    assert strat.stats["residui_ricordati"] == []


# --------------------------------------------------------------------------- SCALPER
@pytest.mark.parametrize("size_lay,resto", [(1.0, 0.05), (2.0, 0.10), (3.0, 0.15)])
def test_scalper_resto_sotto_il_floor_dichiarato_e_ciclo_chiuso(size_lay, resto, db, banchi,
                                                               differita):
    """LAY x @2,10 in flatten: BACK x*1,05 al best-back 2,00 = multiplo di 0,50
    diretto + resto sotto 0,50. Nessuna sequenza, una riga CRITICAL, ciclo
    chiuso (lo slot non resta FLATTENING), niente vivo, residuo ricordato."""
    b, strat, market, slot, righe = _scalper_in_flatten(db, banchi, size_lay)
    viol = _giri_con_invariante(b, strat, slot, svuota=differita)
    assert viol == [], viol[:3]
    assert slot.status in (TSB.IDLE, TSB.DONE)
    assert slot.submin_count == 0
    assert _nessun_vivo(market, strat) == []
    crit = _critiche(righe)
    assert len(crit) == 1 and crit[0]["importo"] == resto and crit[0]["lato"] == "BACK", righe
    assert strat.stats["residui_ricordati"][0]["importo"] == resto


def test_scalper_minimi_dalla_fonte_unica_banca_al_centesimo():
    s = TSB.TennisScalperStrategy.__new__(TSB.TennisScalperStrategy)
    assert TSB.TennisScalperStrategy._side_min("BACK") == float(MIN.IT_MIN_BACK)
    assert TSB.TennisScalperStrategy._side_min("LAY") == float(MIN.IT_MIN_LAY)
    assert s._size_direct_ok("LAY", 1.37) is True            # banca al centesimo
    assert s._size_direct_ok("LAY", 0.60) is False           # sotto il minimo diretto
    assert s._size_direct_ok("BACK", 1.50) is True
    assert s._size_direct_ok("BACK", 1.37) is False          # punta: multipli di 0,50
