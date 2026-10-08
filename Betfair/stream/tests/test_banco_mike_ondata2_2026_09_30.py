# -*- coding: utf-8 -*-
"""BANCO COMUNE, ONDATA 2 DI MIKE (30/09): i pezzi del banco toccati.

  * ``MercatoFlumine.read_book`` di un mercato CHIUSO risponde col libro FINALE
    della registrazione (runner WINNER/LOSER) nella STESSA forma di
    ``omega_market.read_book`` (la REST ``listMarketBook`` di produzione): il
    confronto e' fatto passando lo stesso JSON grezzo di Betfair a tutti e due.
    Un mercato mai chiuso risponde None come prima.
  * ``chiusura_parziale``: la SPINTA dichiarata (``libro_con_spinta``) e la
    regola «CP1/CP3/CP4 si contano solo dove il guasto ha avuto effetto»
    (``Sorveglianza(solo_con_effetto=True)``), con ordini VERI di flumine.
  * ``certifica``: il trasporto obbligato di uno scenario, il segno NE (non
    esercitato) al posto di OK.

Finti: il libro e' la classe VERA ``betfairlightweight...MarketBook`` costruita
dal JSON di ``listMarketBook`` (chiavi camelCase di Betfair); gli ordini sono
``flumine.order.trade.Trade``/``LimitOrder`` veri. ASCII-only.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest import certifica as CF
from Betfair.stream.backtest import chiusura_parziale as CP


def _grezzo(stato: str = "CLOSED", vincitore: int = 1222345) -> Dict[str, Any]:
    """Il JSON di ``listMarketBook`` di un Over/Under 3,5 regolato (Over vince)."""
    def runner(sid: int, st: str, atb=(), atl=()):
        return {"selectionId": sid, "handicap": 0.0, "status": st, "adjustmentFactor": None,
                "ex": {"availableToBack": [{"price": p, "size": s} for p, s in atb],
                       "availableToLay": [{"price": p, "size": s} for p, s in atl],
                       "tradedVolume": []}}
    if stato == "CLOSED":
        runners = [runner(1222344, "LOSER" if vincitore != 1222344 else "WINNER"),
                   runner(1222345, "WINNER" if vincitore == 1222345 else "LOSER")]
    else:
        runners = [runner(1222344, "ACTIVE", [(1.5, 10.0)], [(1.52, 7.0), (1.53, 4.0)]),
                   runner(1222345, "ACTIVE", [(2.9, 3.0)], [(3.0, 5.0)])]
    return {"marketId": "1.259475537", "isMarketDataDelayed": False, "status": stato,
            "betDelay": 5, "bspReconciled": False, "complete": True, "inplay": True,
            "numberOfWinners": 1, "numberOfRunners": 2, "numberOfActiveRunners": 0,
            "totalMatched": 1000.0, "totalAvailable": 0.0, "crossMatching": True,
            "runnersVoidable": False, "version": 1, "runners": runners}


def _libro_vero(grezzo: Dict[str, Any]) -> Any:
    from betfairlightweight.resources.bettingresources import MarketBook

    return MarketBook(**grezzo)


def _omega(grezzo: Dict[str, Any], nomi: Dict[int, str], monkeypatch) -> Dict[str, Any]:
    from Betfair.omega import omega_market as OM

    monkeypatch.setattr(OM, "call", lambda fn: [grezzo])
    return OM.read_book(grezzo["marketId"], nomi)


@pytest.mark.parametrize("vincitore", [1222344, 1222345])
def test_read_book_mercato_chiuso_stessa_forma_della_produzione(vincitore, monkeypatch):
    grezzo = _grezzo("CLOSED", vincitore)
    nomi = {1222344: "Under 3.5 Goals", 1222345: "Over 3.5 Goals"}
    m = B.MercatoFlumine(strategia=None)
    assert m.read_book(grezzo["marketId"], nomi) is None      # prima della chiusura
    assert m.registra_libro_chiuso(_libro_vero(grezzo)) is not None
    banco = m.read_book(grezzo["marketId"], nomi)
    vero = _omega(grezzo, nomi, monkeypatch)
    assert banco == vero
    assert {r["selection_id"]: r["status"] for r in banco["runners"]}[vincitore] == "WINNER"


def test_read_book_mercato_aperto_non_si_registra(monkeypatch):
    grezzo = _grezzo("OPEN")
    m = B.MercatoFlumine(strategia=None)
    assert m.registra_libro_chiuso(_libro_vero(grezzo)) is None
    assert m.read_book(grezzo["marketId"], {}) is None
    assert m.letture == 1


def test_read_book_i_campi_del_ladder_come_la_produzione(monkeypatch):
    """Anche con livelli nel libro (chiusura con un ladder residuo) la lettura
    dei migliori prezzi e' quella di produzione."""
    grezzo = _grezzo("OPEN")
    grezzo["status"] = "CLOSED"
    m = B.MercatoFlumine(strategia=None)
    m.registra_libro_chiuso(_libro_vero(grezzo))
    assert m.read_book(grezzo["marketId"], {}) == _omega(grezzo, {}, monkeypatch)


# ---------------------------------------------------------------------------
# chiusura_parziale: la spinta e il conteggio solo con effetto
# ---------------------------------------------------------------------------
def _ordine(lato: str, prezzo: float, size: float) -> Any:
    from flumine import BaseStrategy
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    # dentro la simulazione (come nel replay): l'ordine legge abbinato e
    # residuo dal suo ``SimulatedOrder``
    with B.simulazione_flumine():
        trade = Trade(market_id="1.1", selection_id=7, handicap=0.0,
                      strategy=BaseStrategy(market_filter={}))
        return trade.create_order(side=lato, order_type=LimitOrder(price=prezzo, size=size))


class _Ex:
    def __init__(self, atb, atl) -> None:
        self.available_to_back = [{"price": p, "size": s} for p, s in atb]
        self.available_to_lay = [{"price": p, "size": s} for p, s in atl]


class _Runner:
    def __init__(self, sid, atb, atl) -> None:
        self.selection_id = sid
        self.handicap = 0.0
        self.ex = _Ex(atb, atl)


class _Libro:
    def __init__(self, runners) -> None:
        self.runners = runners
        self.publish_time = None


def test_libro_con_spinta_mette_il_livello_al_prezzo_della_chiusura():
    libro = _Libro([_Runner(7, [(1.50, 50.0)], [(1.52, 30.0), (1.53, 10.0)]),
                    _Runner(8, [(3.0, 5.0)], [(3.1, 5.0)])])
    vista = CP.libro_con_spinta(libro, 7, 0.0, "LAY", 1.48, 4.05)
    r7 = next(r for r in vista.runners if r.selection_id == 7)
    assert r7.ex.available_to_lay[0] == {"price": 1.48, "size": 4.05}
    assert r7.ex.available_to_lay[1:] == [{"price": 1.52, "size": 30.0},
                                          {"price": 1.53, "size": 10.0}]
    assert r7.ex.available_to_back == [{"price": 1.50, "size": 50.0}]   # intatto
    r8 = next(r for r in vista.runners if r.selection_id == 8)
    assert r8 is libro.runners[1]                                    # altri runner intatti
    # il libro VERO non e' toccato
    assert libro.runners[0].ex.available_to_lay[0] == {"price": 1.52, "size": 30.0}
    assert CP._liquidita_al_prezzo(libro, 7, "LAY", 1.48) == 0.0
    assert CP._liquidita_al_prezzo(libro, 7, "LAY", 1.52) == 30.0


def test_con_effetto_appoggiata_solo_se_abbinata():
    g = CP.GuastoChiusuraParziale(spinta_prezzo=True)
    o = _ordine("LAY", 1.48, 10.0)
    rec = {"ordine": o, "chiave": ("1.1", 7), "fok": False, "effetto_fok": False}
    g.colpiti.append(rec)
    assert not g.con_effetto(rec) and not g.chiave_con_effetto(("1.1", 7))
    o.simulated._update_matched([0, 1.48, 4.0])
    assert g.con_effetto(rec) and g.chiave_con_effetto(("1.1", 7))
    fok = {"ordine": _ordine("LAY", 1.48, 10.0), "chiave": ("1.1", 8), "fok": True,
           "effetto_fok": False}
    assert not g.con_effetto(fok)
    fok["effetto_fok"] = True
    assert g.con_effetto(fok)


def test_sorveglianza_solo_con_effetto_non_conta_la_chiusura_mai_abbinata():
    """Il referto del 29/09: tre banche al fischio SCADUTE (abbinato 0) e CP1
    x12052. Con la regola nuova: zero casi finche' il guasto non ha effetto; di
    serie (altri bot) il conteggio resta quello di prima."""
    g = CP.GuastoChiusuraParziale(spinta_prezzo=True)
    o = _ordine("LAY", 1.48, 10.0)
    g.colpiti.append({"ordine": o, "chiave": ("1.1", 7), "fok": False, "effetto_fok": False,
                      "lato": "LAY", "chiesto": 10.0, "tetto": 4.0})
    g.per_chiave[("1.1", 7)] = {"colpito": o, "dopo": 1, "fok": False, "nuovo_ciclo": False,
                                "segno": 1.0, "emesse": set()}
    g.mercato_chiuso = lambda _mid: False            # type: ignore[assignment]
    g.tutti_gli_ordini = lambda: [o]                 # type: ignore[assignment]
    g.ordini_del_bot = lambda *_a, **_k: [o]         # type: ignore[assignment]
    g.sollecitati = {"CP4": 1}
    g._soll_chiave = {("1.1", 7): 1}
    credute = [{"id": "x", "chiave": ("1.1", 7), "chiusa": False, "coperto": None,
                "apertura": None, "ingressi": [], "chiusure": [], "per_selezione": True,
                "tolleranza": 0.0}]
    sol: Dict[str, int] = {}
    CP.Sorveglianza(g, solo_con_effetto=True).verifica(credute, sol)
    assert not any(sol.get(k) for k in ("CP1", "CP3", "CP4")), sol
    # di serie: si conta come prima (CP1, CP3, CP4)
    g.sollecitati = {"CP4": 1}
    g._soll_chiave = {("1.1", 7): 1}
    sol2: Dict[str, int] = {}
    CP.Sorveglianza(g).verifica(credute, sol2)
    assert sol2.get("CP1") and sol2.get("CP3") and sol2.get("CP4"), sol2
    # con effetto (abbinata in parte): si conta
    o.simulated._update_matched([0, 1.48, 4.0])
    g.sollecitati = {"CP4": 1}
    g._soll_chiave = {("1.1", 7): 1}
    sol3: Dict[str, int] = {}
    CP.Sorveglianza(g, solo_con_effetto=True).verifica(credute, sol3)
    assert sol3.get("CP1") and sol3.get("CP3") and sol3.get("CP4"), sol3


# ---------------------------------------------------------------------------
# certifica: trasporto obbligato e segno NE
# ---------------------------------------------------------------------------
def test_trasporto_obbligato_solo_col_canale_richiesto():
    ob = {"chiuso-fuori-app": "coda"}
    assert CF.trasporto_dello_scenario(ob, "chiuso-fuori-app", "canale", "canale") == "coda"
    assert CF.trasporto_dello_scenario(ob, "base", "canale", "canale") == "canale"
    # con ``entrambi`` la coda c'e' gia': il canale resta per la parita'
    assert CF.trasporto_dello_scenario(ob, "chiuso-fuori-app", "canale", "entrambi") == "canale"
    assert CF.trasporto_dello_scenario(ob, "chiuso-fuori-app", None, None) is None


def test_registro_mike_dichiara_il_trasporto_obbligato():
    from Betfair.stream.backtest import registro_bot as REG

    # 08/10 (W3a): tre scenari nuovi, due sul conto live (coda) e uno in paper (canale)
    assert REG.bot("mike").trasporto_obbligato() == {
        "chiuso-fuori-app": "coda", "ridotto-fuori-app": "coda",
        "annullato-dal-sito": "coda", "manuale-app-paper": "canale"}
    assert REG.bot("omega").trasporto_obbligato() == {}


def test_segno_ne_per_uno_scenario_non_esercitato():
    from Betfair.mike import certificazione as CERT

    r = CERT.Referto(event_id="x")
    r.decisioni = 5
    assert CF.segno_referto(r) == "OK "
    r.non_esercitato.append("R3 mai sollecitato")
    assert CF.segno_referto(r) == "NE "
    r.violazioni.append(CERT.Violazione("R3", "regola", "dettaglio"))
    assert CF.segno_referto(r) == "KO "


def test_causa_non_esercitato_degli_scenari_di_mike():
    from Betfair.mike import certificazione as CERT
    from Betfair.mike.tools import replay_registrazioni as RR

    r = CERT.Referto(event_id="x")
    r.contatori.update({"chiusura_utente": 1})
    assert "R3" in RR.causa_non_esercitato(RR.SCENARIO_CHIUSO_FUORI_APP, r)
    r.sollecitati["R3"] = 10
    assert RR.causa_non_esercitato(RR.SCENARIO_CHIUSO_FUORI_APP, r) is None
    r2 = CERT.Referto(event_id="x")
    assert "0 rifiuti" in RR.causa_non_esercitato(RR.SCENARIO_COVER_RIFIUTATA, r2)
    r2.contatori["rifiuti"] = 3
    r2.sollecitati["S1"] = 1
    assert RR.causa_non_esercitato(RR.SCENARIO_COVER_RIFIUTATA, r2) is None
    r3 = CERT.Referto(event_id="x")
    assert RR.causa_non_esercitato(CP.SCENARIO, r3)
    r3.contatori["chiusure_con_effetto"] = 1
    assert RR.causa_non_esercitato(CP.SCENARIO, r3) is None
    assert RR.causa_non_esercitato("base", CERT.Referto(event_id="x")) is None
