"""W1-C2 - P&L di mercato "se vince": PARITA' con flumine, green-up e ladder del frontend.

  * per selezione: ``Blotter.get_exposures`` VERO di flumine su ``BetfairOrder``
    VERI con il ``CurrentOrder`` vero di betfairlightweight come risposta;
  * per il mercato: la formula ``pnlSeVince`` di
    ``frontend/src/lib/replayOperazioni.ts`` (righe 186-194) ripresa qui riga per
    riga (``_ts_pnl_se_vince``); il test verifica anche che il sorgente TS
    contenga ancora quelle righe (se cambia, il test diventa rosso);
  * P&L bloccato: ``lockedPnlAt`` di ``frontend/src/lib/ladderMath.ts`` (righe
    10-13) riga per riga e ``trading/greenup.compute_greenup``.
ASCII-only.
"""
from __future__ import annotations

import itertools
import pathlib
import random
from typing import Any, List, Optional, Tuple

import pytest
from flumine import BaseStrategy
from flumine.markets.blotter import Blotter
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.nucleo.ordini import pnl_mercato as P
from Betfair.nucleo.ordini.contratto import OrdineConto
from Betfair.nucleo.ordini.tests.test_c2_aiuti import (AWAY, DRAW, HOME, MKT, correnti,
                                                       ordine_json)

RADICE = pathlib.Path(__file__).resolve().parents[4]


def oc(bet: str, sel: int, lato: str, abbinato: float, pm: Optional[float], *,
       autore: str = "desktop", modo: str = "live", market: str = MKT,
       handicap: float = 0.0, residuo: float = 0.0) -> OrdineConto:
    return OrdineConto(bet_id=bet, market_id=market, selection_id=sel, handicap=handicap,
                       lato=lato, prezzo=pm or 2.0, importo=abbinato + residuo,  # type: ignore[arg-type]
                       abbinato=abbinato, residuo=residuo, prezzo_medio=pm, stato="abbinato",
                       autore=autore, ref=None, modo=modo, aggiornato_ms=1)  # type: ignore[arg-type]


# --------------------------------------------------------------------- la formula del frontend
def _ts_pnl_se_vince(abb: List[Tuple[int, str, float, float]], vincitore: Optional[int]) -> float:
    """replayOperazioni.ts:186-194, riga per riga:
        let v = 0;
        for (const a of abb) {
            const suo = vincitore != null && a.selectionId === vincitore;
            if (a.lato === 'back') v += suo ? a.importo * (a.prezzo - 1) : -a.importo;
            else v += suo ? -a.importo * (a.prezzo - 1) : a.importo;
        }
        return v;"""
    v = 0.0
    for sel, lato, importo, prezzo in abb:
        suo = vincitore is not None and sel == vincitore
        if lato == "back":
            v += importo * (prezzo - 1) if suo else -importo
        else:
            v += -importo * (prezzo - 1) if suo else importo
    return v


def _ts_locked(price: float, win: float, lose: float) -> float:
    """ladderMath.ts:10-13:
        if (!Number.isFinite(price) || price <= 1) return lose;
        return lose + (win - lose) / price;"""
    import math

    if not math.isfinite(price) or price <= 1:
        return lose
    return lose + (win - lose) / price


def test_il_sorgente_ts_contiene_ancora_le_formule_citate():
    rep = (RADICE / "frontend/src/lib/replayOperazioni.ts").read_text(encoding="utf-8")
    assert "if (a.lato === 'back') v += suo ? a.importo * (a.prezzo - 1) : -a.importo;" in rep
    assert "else v += suo ? -a.importo * (a.prezzo - 1) : a.importo;" in rep
    lad = (RADICE / "frontend/src/lib/ladderMath.ts").read_text(encoding="utf-8")
    assert "if (!Number.isFinite(price) || price <= 1) return lose;" in lad
    assert "return lose + (win - lose) / price;" in lad


def _griglia(seed: int, n: int) -> List[OrdineConto]:
    rnd = random.Random(seed)
    prezzi = [1.01, 1.5, 1.83, 2.0, 2.62, 3.45, 5.5, 10.0, 34.0, 1000.0]
    out = []
    for i in range(n):
        out.append(oc(str(i), rnd.choice([HOME, AWAY, DRAW]), rnd.choice(["back", "lay"]),
                      round(rnd.choice([0.5, 1.0, 2.0, 2.37, 3.0, 10.0, 0.01]), 2),
                      rnd.choice(prezzi), autore=rnd.choice(["desktop", "mike", "sito", "omega"])))
    return out


@pytest.mark.parametrize("seed", range(12))
def test_se_vince_identico_alla_formula_del_ladder(seed):
    ordini = _griglia(seed, 1 + seed * 3)
    pos = P.posizione_mercato(MKT, "live", ordini, runner=[HOME, AWAY, DRAW])
    abb = [(o.selection_id, o.lato, o.abbinato, o.prezzo_medio) for o in ordini]
    for sel in (HOME, AWAY, DRAW):
        assert pos.se_vince[sel] == round(_ts_pnl_se_vince(abb, sel), 2)
        assert P.pnl_se_vince(ordini, sel) == _ts_pnl_se_vince(abb, sel)   # identico, non arrotondato
    for autore, sv in pos.se_vince_per_autore.items():
        suoi = [(o.selection_id, o.lato, o.abbinato, o.prezzo_medio) for o in ordini
                if o.autore == autore]
        for sel in (HOME, AWAY, DRAW):
            assert sv[sel] == round(_ts_pnl_se_vince(suoi, sel), 2)
    assert pos.esposizione_massima == round(min([0.0] + list(pos.se_vince.values())), 2)


def _blotter_vero(ordini_json: List[dict]) -> Tuple[Blotter, BaseStrategy]:
    """Ordini flumine VERI nel blotter VERO, con il CurrentOrder vero."""
    s = BaseStrategy(market_filter={}, name="parita_c2")
    bl = Blotter(MKT)
    for co in correnti(*ordini_json):
        t = Trade(market_id=MKT, selection_id=co.selection_id, handicap=co.handicap, strategy=s)
        o = t.create_order(side=co.side, order_type=LimitOrder(price=co.price_size.price,
                                                               size=co.price_size.size))
        o.placing()
        o.executable()
        o.update_current_order(co)
        bl[o.id] = o
    return bl, s


@pytest.mark.parametrize("seed", range(8))
def test_esposizioni_per_selezione_identiche_al_blotter_di_flumine(seed):
    from Betfair.nucleo.ordini.libro_conto import componi_ordine_conto, ordine_da_corrente
    from Betfair.nucleo.ordini.attribuzione import Attribuzione

    rnd = random.Random(100 + seed)
    js = []
    for i in range(3 + seed * 2):
        abb = rnd.choice([0.0, 0.5, 2.0, 3.37, 10.0])
        js.append(ordine_json(str(i), rnd.choice(["BACK", "LAY"]), abb,
                              rnd.choice([1.5, 2.0, 3.25, 7.8]),
                              residuo=rnd.choice([0.0, 1.0]), sel=rnd.choice([HOME, AWAY]),
                              avp=rnd.choice([1.52, 2.02, 3.3]) if abb > 0 else 0.0))
    bl, s = _blotter_vero(js)
    ordini = [componi_ordine_conto("live", ordine_da_corrente(co, ricevuto_ms=1),
                                   Attribuzione("sito", "sito", "riferimenti"))
              for co in correnti(*js)]
    espo = P.esposizioni_per_selezione(ordini)
    for sel in (HOME, AWAY):
        vero = bl.get_exposures(s, (MKT, sel, 0.0))
        e = espo.get((sel, 0.0))
        if e is None:
            assert (vero["matched_profit_if_win"], vero["matched_profit_if_lose"]) == (0.0, 0.0)
            continue
        assert (e.se_vince, e.se_perde) == (vero["matched_profit_if_win"],
                                            vero["matched_profit_if_lose"])


def test_green_up_e_lockedpnl_sulla_stessa_posizione():
    from Betfair.stream.trading.greenup import compute_greenup

    ordini = [oc("1", HOME, "back", 10.0, 3.0), oc("2", HOME, "lay", 4.0, 2.2)]
    e = P.esposizioni_per_selezione(ordini)[(HOME, 0.0)]
    for prezzo in (1.01, 1.5, 2.0, 2.5, 4.4, 1000.0):
        assert P.pnl_bloccato(prezzo, e.se_vince, e.se_perde) == _ts_locked(prezzo, e.se_vince,
                                                                             e.se_perde)
        piano = compute_greenup(matched_if_win=e.se_vince, matched_if_lose=e.se_perde,
                                best_back_price=prezzo, best_lay_price=prezzo,
                                target_price=prezzo)
        if piano.actionable:
            # stessa formula; l'unico scarto e' la size dell'ordine vero arrotondata
            # al centesimo (greenup._hedge_size): al piu' 0,005 x prezzo, piu' i centesimi
            locked = P.pnl_bloccato(piano.price, e.se_vince, e.se_perde)
            tol = 0.005 * piano.price + 0.01 + 1e-9
            assert abs(piano.expected_if_win - locked) <= tol
            assert abs(piano.expected_if_lose - locked) <= tol
    assert P.pnl_bloccato(1.0, 5.0, -2.0) == -2.0
    assert P.pnl_bloccato(float("nan"), 5.0, -2.0) == -2.0


def test_abbinato_e_prezzo_medio_per_lato():
    ordini = [oc("1", HOME, "back", 2.0, 2.0), oc("2", HOME, "back", 6.0, 3.0),
              oc("3", AWAY, "lay", 1.5, 4.0), oc("4", AWAY, "lay", 0.0, None, residuo=2.0)]
    pos = P.posizione_mercato(MKT, "live", ordini)
    assert pos.abbinato_back == {HOME: 8.0, AWAY: 0.0}
    assert pos.abbinato_lay == {HOME: 0.0, AWAY: 1.5}
    assert pos.prezzo_medio_back == {HOME: 2.75, AWAY: None}      # (2*2+6*3)/8
    assert pos.prezzo_medio_lay == {HOME: None, AWAY: 4.0}
    assert all(type(v) is float for v in pos.abbinato_back.values())


def test_esposizione_massima_con_e_senza_elenco_dei_runner():
    ordini = [oc("1", HOME, "back", 10.0, 2.0)]        # vince HOME +10, altrimenti -10
    senza = P.posizione_mercato(MKT, "live", ordini)
    assert senza.se_vince == {HOME: 10.0}
    assert senza.esposizione_massima == -10.0          # "vince un altro": prudente
    con = P.posizione_mercato(MKT, "live", ordini, runner=[HOME, AWAY, DRAW])
    assert con.se_vince == {HOME: 10.0, AWAY: -10.0, DRAW: -10.0}
    assert con.esposizione_massima == -10.0
    vuoto = P.posizione_mercato(MKT, "live", [])
    assert (vuoto.se_vince, vuoto.esposizione_massima) == ({}, 0.0)
    # verde su ogni esito: l'esposizione massima e' zero, mai positiva
    verde = P.posizione_mercato(MKT, "live", [oc("1", HOME, "back", 10.0, 3.0),
                                              oc("2", HOME, "lay", 12.0, 2.0)], runner=[HOME, AWAY])
    assert verde.se_vince == {HOME: 8.0, AWAY: 2.0}
    assert verde.esposizione_massima == 0.0


def test_paper_e_live_mai_sommati_e_mercato_sbagliato():
    with pytest.raises(ValueError, match="mai sommati"):
        P.posizione_mercato(MKT, "live", [oc("1", HOME, "back", 2.0, 2.0),
                                          oc("2", HOME, "back", 2.0, 2.0, modo="paper")])
    with pytest.raises(ValueError, match="mercato"):
        P.posizione_mercato(MKT, "live", [oc("1", HOME, "back", 2.0, 2.0, market="1.9")])


def test_abbinato_senza_prezzo_medio_fuori_e_dichiarato():
    c = P.calcola(MKT, "live", [oc("1", HOME, "back", 2.0, None), oc("2", HOME, "back", 2.0, 3.0),
                                oc("3", HOME, "back", 2.0, 1.0)])
    assert c.scartati == ("1", "3")                    # nessun prezzo medio, o non > 1
    assert c.posizione.se_vince == {HOME: 4.0}


def test_mercato_a_linee_handicap():
    ordini = [oc("1", HOME, "back", 10.0, 1.9, handicap=-0.5),
              oc("2", AWAY, "lay", 5.0, 2.1, handicap=0.5)]
    c = P.calcola(MKT, "live", ordini)
    assert c.a_linee and c.posizione.se_vince == {} and c.posizione.se_vince_per_autore == {}
    e = P.esposizioni_per_selezione(ordini)
    assert set(e) == {(HOME, -0.5), (AWAY, 0.5)}
    assert c.posizione.esposizione_massima == round(-10.0 + -5.5, 2)


def test_commissione_non_applicata():
    pos = P.posizione_mercato(MKT, "live", [oc("1", HOME, "back", 10.0, 2.0)], runner=[HOME, AWAY])
    assert pos.se_vince[HOME] == 10.0                  # lordo: nessun 5%


def test_per_autore_somma_al_totale_al_centesimo():
    for seed in range(20):
        ordini = _griglia(1000 + seed, 15)
        pos = P.posizione_mercato(MKT, "live", ordini, runner=[HOME, AWAY, DRAW])
        for sel in (HOME, AWAY, DRAW):
            somma = sum(v[sel] for v in pos.se_vince_per_autore.values())
            assert abs(somma - pos.se_vince[sel]) <= 0.005 * len(pos.se_vince_per_autore) + 1e-9


def test_blotter_caso_fisso_non_a_vuoto():
    """Un caso fisso con numeri diversi da zero (il test a griglia non passa a vuoto)."""
    from Betfair.nucleo.ordini.attribuzione import Attribuzione
    from Betfair.nucleo.ordini.libro_conto import componi_ordine_conto, ordine_da_corrente

    js = [ordine_json("1", "BACK", 10.0, 3.0), ordine_json("2", "LAY", 4.0, 2.2, residuo=1.0),
          ordine_json("3", "LAY", 2.5, 5.0, sel=AWAY)]
    bl, s = _blotter_vero(js)
    ordini = [componi_ordine_conto("live", ordine_da_corrente(co, ricevuto_ms=1),
                                   Attribuzione("sito", "sito", "riferimenti"))
              for co in correnti(*js)]
    espo = P.esposizioni_per_selezione(ordini)
    vero_h = bl.get_exposures(s, (MKT, HOME, 0.0))
    vero_a = bl.get_exposures(s, (MKT, AWAY, 0.0))
    assert (espo[(HOME, 0.0)].se_vince, espo[(HOME, 0.0)].se_perde) == (15.2, -6.0)
    assert (vero_h["matched_profit_if_win"], vero_h["matched_profit_if_lose"]) == (15.2, -6.0)
    assert (espo[(AWAY, 0.0)].se_vince, espo[(AWAY, 0.0)].se_perde) == (
        vero_a["matched_profit_if_win"], vero_a["matched_profit_if_lose"]) == (-10.0, 2.5)
