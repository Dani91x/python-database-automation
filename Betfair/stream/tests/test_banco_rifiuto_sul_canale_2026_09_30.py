"""BANCO 30/09 - LA LEVA DEL RIFIUTO PROVOCATO VALE ANCHE SUL TRASPORTO CANALE.

Reperto (``AUDIT_2026-09-29/replay/mike_coperture_P5_4C.txt``): negli scenari
``copertura-rifiutata`` / ``-legacy`` di Mike la leva del banco
(``MercatoFlumine``: ``guasti["place_rifiuto"]``, ``rifiuta_lato``,
``rifiuta_market_id``, ``rifiuta_sotto_minimo``) funzionava sulla CODA (la
copertura rifiutata, P&L -10,00) ma non sul CANALE (copertura abbinata,
-14,17 / -14,00; motore ``rifiutati: 0``; parita' NON RAGGIUNTA). Causa: la
leva stava solo dentro ``MercatoFlumine.place_order_live``; sul canale l'ordine
va client vero -> ``WsBanco`` -> ``MotoreOrdini`` -> ``live_order_worker._dispatch``
-> ``Market.place_order`` di flumine, e da ``place_order_live`` non passa mai.

Qui si prova, con oggetti VERI di flumine (``FlumineSimulation`` del banco,
``SimulatedExecution``, ``Trade``/``LimitOrder``/``BetfairOrderPackage``, la
strategia ``BaseStrategy``) e con la leva VERA (``MercatoFlumine``), che:
  1. un ordine nato dal motore (ref ``awlq``) che la leva colpisce torna
     FAILURE da flumine: nessun abbinato, nessun residuo, EXECUTION_COMPLETE,
     rifiuto contato in ``rifiutati``; lo specchio di produzione
     (``LiveTradingStrategy._order_row`` + ``motore_ordini.fase_da_riga``) lo
     vede terminale senza abbinato;
  2. la leva conta come sulla coda (contatore che si consuma, lato, mercato);
  3. gli ordini della REST del banco (ripiego D5, gia' passati dalla leva) e
     quelli che la leva non colpisce NON sono toccati;
  4. a fine replay l'esecuzione torna quella della classe;
  5. SOTTO IL MINIMO (``copertura-rifiutata-legacy``): sul canale il motore fa
     il place-and-trim vero e l'ordine che corrisponde a quello della coda e'
     il NUOVO ordine del replace finale; la leva lo colpisce li' (e solo per
     un replace di una sequenza place-and-trim in corso nel motore).
Unico finto: il ``market_book`` del replace, di cui ``simulated.cancel`` legge
solo ``status`` (stesso nome e stesso valore del vero). ASCII-only.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from flumine import BaseStrategy
from flumine.markets.market import Market
from flumine.order.orderpackage import BetfairOrderPackage, OrderPackageType
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.stream import motore_ordini as MO
from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest import trasporto as TRA
from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy

OU45, OU35 = "1.259475534", "1.259475537"


@pytest.fixture(autouse=True)
def _dentro_la_simulazione(monkeypatch):
    """Come ``FlumineSimulation.__enter__`` (``baseflumine.py:493``): dentro il
    replay ``config.simulated`` e' vero e gli ordini leggono ``simulated``."""
    from flumine import config

    monkeypatch.setattr(config, "simulated", True)


class _Strategia(BaseStrategy):
    """La classe VERA: ``Order.execution_complete`` passa dalla strategia."""

    def check_market_book(self, market, market_book):  # pragma: no cover
        return False

    def process_market_book(self, market, market_book):  # pragma: no cover
        return None


class _StrategiaBanco:
    """Il minimo che ``MercatoFlumine`` legge dalla strategia del banco."""

    mercati: dict = {}


def _banco():
    from flumine import FlumineSimulation

    cliente = B.cliente_simulato()
    quadro = FlumineSimulation(client=cliente)
    assert cliente.execution is quadro.simulated_execution
    mercato = B.MercatoFlumine(_StrategiaBanco())
    strategia = SimpleNamespace(mercato=mercato)
    motore = SimpleNamespace(quadro=quadro)
    return quadro, cliente, mercato, strategia, motore


def _ordine(cliente: Any, market_id: str, side: str, size: float, ref_motore: Any):
    trade = Trade(market_id=market_id, selection_id=1222347, handicap=0.0,
                  strategy=_Strategia(market_filter={}))
    o = trade.create_order(side=side, order_type=LimitOrder(
        price=1.35, size=size, persistence_type="LAPSE", time_in_force="FILL_OR_KILL"))
    o.update_client(cliente)
    if ref_motore is not None:
        # come ``live_order_build``: il ref interno nelle note dell'ordine
        o.notes["customer_order_ref"] = ref_motore
    else:
        o.notes["bot_ref"] = "mike-t9"      # ordine della REST del banco
    return o


def _pacchetto(cliente: Any, market_id: str, ordini: List[Any]) -> BetfairOrderPackage:
    return BetfairOrderPackage(client=cliente, market_id=market_id, orders=ordini,
                               package_type=OrderPackageType.PLACE, bet_delay=0)


def _leva_copertura(mercato: Any) -> None:
    """La leva di ``copertura-rifiutata`` (``replay_registrazioni``): ogni BANCA
    sul mercato 4,5, rifiuto che non finisce, codice vero."""
    mercato.guasti["place_rifiuto"] = -1
    mercato.rifiuta_lato = "lay"
    mercato.rifiuta_market_id = OU45
    mercato.rifiuto_codice = "CANCELLED_NOT_PLACED"
    mercato.rifiuto_codice_interno = "INVALID_ODDS"


def test_ordine_del_motore_colpito_dalla_leva_torna_failure_da_flumine():
    quadro, cliente, mercato, strategia, motore = _banco()
    quadro.markets._markets[OU45] = Market(quadro, OU45, None)
    _leva_copertura(mercato)
    st: dict = {}
    TRA._monta_rifiuti_canale(st, motore, strategia)
    o = _ordine(cliente, OU45, "LAY", 12.63, "awlq5")
    quadro.simulated_execution.handler(_pacchetto(cliente, OU45, [o]))
    assert o.simulated.size_matched == 0.0
    assert o.size_remaining == 0.0, "un ordine rifiutato non resta vivo"
    assert o.status.name == "EXECUTION_COMPLETE"
    assert mercato.rifiutati == [{"ref": "awlq5",
                                  "err": "CANCELLED_NOT_PLACED (rifiuto provocato)"}]
    # lo specchio di PRODUZIONE lo vede terminale senza abbinato
    riga = LiveTradingStrategy._order_row(SimpleNamespace(mode="paper"), o,
                                          event_id="35760084", market_id=OU45)
    assert riga["client_order_ref"] == "awlq5"
    assert riga["size_matched"] == 0.0 and riga["status"] == "EXECUTION_COMPLETE"
    assert MO.fase_da_riga(riga) == "annullato"
    TRA._smonta(st)
    assert "execute_place" not in vars(quadro.simulated_execution)


def test_la_leva_sul_canale_conta_come_sulla_coda_e_colpisce_solo_chi_deve():
    quadro, cliente, mercato, strategia, motore = _banco()
    passati: List[Any] = []
    # l'esecuzione "vera" qui e' una spia: registra i pacchetti che le arrivano
    # (il matching di flumine non serve per sapere CHI la leva ha colpito)
    quadro.simulated_execution.execute_place = \
        lambda pkg, http_session=None: passati.extend(list(pkg))
    mercato.guasti["place_rifiuto"] = 1              # UN rifiuto, poi si consuma
    mercato.rifiuta_lato = "lay"
    mercato.rifiuta_market_id = OU45
    st: dict = {}
    TRA._monta_rifiuti_canale(st, motore, strategia)
    back45 = _ordine(cliente, OU45, "BACK", 5.0, "awlq1")     # lato sbagliato
    lay35 = _ordine(cliente, OU35, "LAY", 5.0, "awlq2")       # mercato sbagliato
    rest45 = _ordine(cliente, OU45, "LAY", 5.0, None)         # REST: leva gia' passata
    lay45 = _ordine(cliente, OU45, "LAY", 5.0, "awlq3")       # colpito
    lay45b = _ordine(cliente, OU45, "LAY", 5.0, "awlq4")      # contatore consumato
    originali = {id(x): x.simulated.place for x in (back45, lay35, rest45, lay45, lay45b)}
    for mid, o in ((OU45, back45), (OU35, lay35), (OU45, rest45), (OU45, lay45),
                   (OU45, lay45b)):
        quadro.simulated_execution.execute_place(_pacchetto(cliente, mid, [o]), None)
    assert [x for x in passati] == [back45, lay35, rest45, lay45, lay45b]
    toccati = [o for o in passati if o.simulated.place != originali[id(o)]]
    assert toccati == [lay45]
    assert [r["ref"] for r in mercato.rifiutati] == ["awlq3"]
    assert mercato.guasti["place_rifiuto"] == 0
    TRA._smonta(st)


def test_la_coda_resta_identica_con_la_leva_estratta():
    """``place_order_live`` usa la STESSA ``rifiuto_provocato``: stesso esito di
    prima (ok False, nessun ordine, codice e report interno di Betfair)."""
    mercato = B.MercatoFlumine(_StrategiaBanco())
    _leva_copertura(mercato)
    res = mercato.place_order_live(market_id=OU45, selection_id=1222347, price=1.35,
                                   size=12.63, event_id="35760084", side="lay",
                                   customer_ref="mike-t5")
    assert res.ok is False and res.bet_id is None and res.error_code == "CANCELLED_NOT_PLACED"
    assert res.raw["instructionReports"][0]["placeInstructionReport"]["errorCode"] == \
        "INVALID_ODDS"
    assert mercato.rifiutati == [{"ref": "mike-t5",
                                  "err": "CANCELLED_NOT_PLACED (rifiuto provocato)"}]
    assert mercato.guasti["place_rifiuto"] == -1     # -1 non si consuma
    # un BACK sullo stesso mercato passa la leva (e va a flumine: mercato assente)
    res2 = mercato.place_order_live(market_id=OU45, selection_id=1222347, price=1.35,
                                    size=12.63, event_id="35760084", side="back",
                                    customer_ref="mike-t6")
    assert res2.raw == {"motivo": "mercato non in replay"}


def test_il_montaggio_del_canale_arma_la_leva_e_lo_smontaggio_la_toglie():
    """La strada VERA del banco: ``trasporto.contesto("mike", "canale")`` +
    ``su_esegui`` (primo passo di ``MotoreReplay.esegui``) montano porta del
    banco, client VERO di Mike e leva; all'uscita dal contesto tutto torna."""
    quadro, cliente, mercato, _s, _m = _banco()
    motore = SimpleNamespace(quadro=quadro, _ora_mercato=None)
    strategia = SimpleNamespace(mercato=mercato, mode="paper",
                                process_market_book=lambda market, market_book: None)
    with TRA.contesto("mike", "canale") as st:
        TRA.su_esegui(motore, strategia)
        assert st["client"] is not None
        assert "execute_place" in vars(quadro.simulated_execution), \
            "sul canale la leva del rifiuto non e' armata"
        _leva_copertura(mercato)
        quadro.markets._markets[OU45] = Market(quadro, OU45, None)
        o = _ordine(cliente, OU45, "LAY", 12.63, "awlq8")
        quadro.simulated_execution.handler(_pacchetto(cliente, OU45, [o]))
        assert o.size_matched == 0.0 and o.size_remaining == 0.0
        assert [r["ref"] for r in mercato.rifiutati] == ["awlq8"]
    assert "execute_place" not in vars(quadro.simulated_execution)
    assert "execute_replace" not in vars(quadro.simulated_execution)


# ---------------------------------------------------------------------------
# 5. sotto il minimo: il replace finale del place-and-trim
# ---------------------------------------------------------------------------
def _leva_sotto_minimo(mercato: Any) -> None:
    """La leva di ``copertura-rifiutata-legacy`` (``replay_registrazioni``)."""
    mercato.guasti["place_rifiuto"] = -1
    mercato.rifiuta_lato = "back"
    mercato.rifiuta_sotto_minimo = 2.00
    mercato.rifiuto_codice = "CANCELLED_NOT_PLACED"
    mercato.rifiuto_codice_interno = "BET_TAKEN_OR_LAPSED"


def _parcheggio_tagliato(cliente: Any, ref: str):
    """Il gradino 2 del place-and-trim: parcheggio da 2,00 a quota non
    abbinabile, tagliato a 1,26 (resta la size voluta), poi il replace alla
    quota vera (``market.replace_order`` -> ``order.replace``)."""
    o = _ordine(cliente, OU45, "BACK", 2.00, ref)
    o.bet_id = "900001"          # il parcheggio e' stato piazzato (``_order_logger``)
    o.executable()
    o.simulated.size_cancelled = 0.74
    assert o.size_remaining == 1.26
    o.replace(4.1)
    return o


def _pacchetto_replace(cliente: Any, ordini: List[Any]) -> BetfairOrderPackage:
    return BetfairOrderPackage(client=cliente, market_id=OU45, orders=ordini,
                               package_type=OrderPackageType.REPLACE, bet_delay=0)


def test_sotto_minimo_il_replace_del_place_and_trim_torna_failure(monkeypatch):
    quadro, cliente, mercato, strategia, motore = _banco()
    quadro.markets._markets[OU45] = Market(quadro, OU45, SimpleNamespace(status="OPEN"))
    _leva_sotto_minimo(mercato)
    st: dict = {"porta_banco": SimpleNamespace(metti_giu=lambda: None, motore=SimpleNamespace(
        _submin={"awlq9": {"step": "trimmed"}}))}
    TRA._monta_rifiuti_canale(st, motore, strategia)
    o = _parcheggio_tagliato(cliente, "awlq9")
    # spia sulla CLASSE (il metodo vero resta quello che esegue): chi nasce dal replace
    nati: List[Any] = []
    vero_crea = Trade.create_order_replacement

    def _spia(self, *a, **k):
        nati.append(vero_crea(self, *a, **k))
        return nati[-1]

    monkeypatch.setattr(Trade, "create_order_replacement", _spia)
    quadro.simulated_execution.handler(_pacchetto_replace(cliente, [o]))
    # l'annullo e' riuscito (1,26 tolti), il NUOVO ordine e' stato rifiutato
    assert o.size_remaining == 0.0 and o.simulated.size_cancelled == 2.00
    assert len(nati) == 1
    nuovo = nati[0]
    assert nuovo.order_type.size == 1.26 and nuovo.order_type.price == 4.1
    assert nuovo.size_matched == 0.0 and nuovo.size_remaining == 0.0
    assert nuovo not in list(quadro.markets._markets[OU45].blotter), "nessun ordine nuovo"
    assert [r["ref"] for r in mercato.rifiutati] == ["awlq9"]
    # il trucco sul Trade vale UN replace: poi torna il metodo della classe
    assert "create_order_replacement" not in vars(o.trade)
    TRA._smonta(st)
    assert "execute_replace" not in vars(quadro.simulated_execution)


def test_sotto_minimo_un_replace_fuori_dal_place_and_trim_non_si_tocca():
    quadro, cliente, mercato, strategia, motore = _banco()
    arrivati: List[Any] = []
    quadro.simulated_execution.execute_replace = \
        lambda pkg, http_session=None: arrivati.append(
            [("patch" if "create_order_replacement" in vars(x.trade) else "vero") for x in pkg])
    _leva_sotto_minimo(mercato)
    st: dict = {"porta_banco": SimpleNamespace(metti_giu=lambda: None, motore=SimpleNamespace(
        _submin={"awlq9": {"step": "trimmed"}}))}
    TRA._monta_rifiuti_canale(st, motore, strategia)
    fuori = _parcheggio_tagliato(cliente, "awlq7")     # nessuna sequenza in corso
    rest = _parcheggio_tagliato(cliente, None)        # ordine della REST del banco
    dentro = _parcheggio_tagliato(cliente, "awlq9")   # sequenza in corso: colpito
    for o in (fuori, rest, dentro):
        quadro.simulated_execution.execute_replace(_pacchetto_replace(cliente, [o]), None)
    assert arrivati == [["vero"], ["vero"], ["patch"]]
    assert [r["ref"] for r in mercato.rifiutati] == ["awlq9"]
    TRA._smonta(st)
