# -*- coding: utf-8 -*-
"""REPLAY VELOCE (02/10, PROCESSO_STANDARD_BOT par. 6.9): le memorie nuove del
banco hanno ognuna un test di EQUIVALENZA con la via lenta e un test che diventa
ROSSO se la memoria restituisce un dato stantio.

  * ``MercatoFlumine.registra_libro_chiuso`` riusa il libro finale quando flumine
    riconsegna lo STESSO book CLOSED (``RIUSA_LIBRO_CHIUSO``). Un book NUOVO dello
    stesso mercato (la cache e' cambiata: per esempio lo stato dei runner arriva
    con l'ultima consegna) deve essere ricostruito.

Finti: il libro e' la classe VERA ``betfairlightweight...MarketBook`` costruita
dal JSON di ``listMarketBook`` (chiavi camelCase di Betfair). ASCII-only.
"""
from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from Betfair.stream.backtest import banco_comune as B


def _grezzo(vincitore: int = 1222345, livelli: bool = False) -> Dict[str, Any]:
    """Il JSON di ``listMarketBook`` di un Over/Under 3,5 chiuso."""
    def runner(sid: int, st: str):
        atb = [(1.5, 10.0)] if livelli else []
        atl = [(1.52, 7.0), (1.53, 4.0)] if livelli else []
        return {"selectionId": sid, "handicap": 0.0, "status": st, "adjustmentFactor": None,
                "ex": {"availableToBack": [{"price": p, "size": s} for p, s in atb],
                       "availableToLay": [{"price": p, "size": s} for p, s in atl],
                       "tradedVolume": []}}
    runners = [runner(1222344, "WINNER" if vincitore == 1222344 else "LOSER"),
               runner(1222345, "WINNER" if vincitore == 1222345 else "LOSER")]
    return {"marketId": "1.259475537", "isMarketDataDelayed": False, "status": "CLOSED",
            "betDelay": 5, "bspReconciled": False, "complete": True, "inplay": True,
            "numberOfWinners": 1, "numberOfRunners": 2, "numberOfActiveRunners": 0,
            "totalMatched": 1000.0, "totalAvailable": 0.0, "crossMatching": True,
            "runnersVoidable": False, "version": 1, "runners": runners}


def _libro(grezzo: Dict[str, Any]) -> Any:
    from betfairlightweight.resources.bettingresources import MarketBook

    return MarketBook(**copy.deepcopy(grezzo))


def _lento(book: Any) -> Dict[str, Any]:
    """La via di prima: ricostruito da capo, senza memoria."""
    m = B.MercatoFlumine(strategia=None)
    vecchio = B.RIUSA_LIBRO_CHIUSO
    B.RIUSA_LIBRO_CHIUSO = False
    try:
        return m.registra_libro_chiuso(book)
    finally:
        B.RIUSA_LIBRO_CHIUSO = vecchio


@pytest.mark.parametrize("livelli", [False, True])
def test_stesso_book_riconsegnato_libro_identico_alla_via_lenta(livelli):
    book = _libro(_grezzo(livelli=livelli))
    m = B.MercatoFlumine(strategia=None)
    primo = m.registra_libro_chiuso(book)
    for _ in range(5):                       # flumine lo riconsegna a ogni riga
        assert m.registra_libro_chiuso(book) == _lento(book)
    assert m.libri_chiusi[book.market_id] == _lento(book)
    assert m.libri_chiusi[book.market_id] is primo      # riusato, non rifatto
    assert m.read_book(book.market_id, {}) == _lento_letto(book)


def _lento_letto(book: Any) -> Dict[str, Any]:
    m = B.MercatoFlumine(strategia=None)
    vecchio = B.RIUSA_LIBRO_CHIUSO
    B.RIUSA_LIBRO_CHIUSO = False
    try:
        m.registra_libro_chiuso(book)
        return m.read_book(book.market_id, {})
    finally:
        B.RIUSA_LIBRO_CHIUSO = vecchio


def test_book_nuovo_dello_stesso_mercato_si_ricostruisce():
    """FALSIFICAZIONE: una memoria per market_id (e non per oggetto) darebbe il
    vincitore VECCHIO. Qui il secondo book porta l'esito rovesciato."""
    m = B.MercatoFlumine(strategia=None)
    a = _libro(_grezzo(vincitore=1222345))
    b = _libro(_grezzo(vincitore=1222344))
    m.registra_libro_chiuso(a)
    m.registra_libro_chiuso(a)
    m.registra_libro_chiuso(b)
    stati = {r["selection_id"]: r["status"] for r in m.libri_chiusi[b.market_id]["runners"]}
    assert stati == {1222344: "WINNER", 1222345: "LOSER"}
    assert m.libri_chiusi[b.market_id] == _lento(b)


def test_stesso_book_convertito_in_eur_dopo_si_ricostruisce():
    """FALSIFICAZIONE: lo STESSO oggetto le cui scale sono state sostituite dalla
    conversione in EUR (`valuta.converti_libro`) non deve dare il libro in GBP."""
    from Betfair.stream import valuta as V

    book = _libro(_grezzo(livelli=True))
    m = B.MercatoFlumine(strategia=None)
    gbp = m.registra_libro_chiuso(book)
    # la conversione VERA di produzione, col cambio FISSO del banco
    V.converti_libro(book, V.CambioGbpEur(fisso=1.25))
    assert getattr(book, "size_gbp_convertite", False) is True
    eur = m.registra_libro_chiuso(book)
    assert eur == _lento(book)
    assert eur != gbp


def test_libro_sostituito_da_altri_non_si_riusa():
    """FALSIFICAZIONE: se qualcuno sostituisce il libro in ``libri_chiusi``, la
    riconsegna dello stesso book lo rifa' invece di restituire il proprio."""
    book = _libro(_grezzo())
    m = B.MercatoFlumine(strategia=None)
    m.registra_libro_chiuso(book)
    m.libri_chiusi[book.market_id] = {"market_id": book.market_id, "runners": []}
    assert m.registra_libro_chiuso(book) == _lento(book)
    assert m.libri_chiusi[book.market_id] == _lento(book)


# ===========================================================================
# 2. LE REGOLE DI LAPSE non si ricalcolano sullo STESSO book riconsegnato
# ===========================================================================
class _MdFinta:
    def __init__(self, in_play: bool) -> None:
        self.in_play = in_play


class _BookFinto:
    """I campi che `_a_flumine` e le due regole di lapse leggono da un
    `MarketBook` vero: market_id, publish_time, status,
    market_definition.in_play, inplay."""

    def __init__(self, in_play: bool, stato: str = "OPEN", secondi: int = 0) -> None:
        from datetime import datetime, timedelta, timezone

        self.market_id = "1.1"
        self.publish_time = (datetime(2026, 10, 2, tzinfo=timezone.utc)
                             + timedelta(seconds=secondi))
        self.status = stato
        self.market_definition = _MdFinta(in_play)
        self.inplay = in_play


class _Blotter(list):
    active = False

    @property
    def live_orders(self):
        return list(self)


class _Mercato:
    closed = False

    def __init__(self, ordini):
        self.market_id = "1.1"
        self.blotter = _Blotter(ordini)
        self.libri = []

    def __call__(self, market_book):
        self.libri.append(market_book)


class _Mercati:
    def __init__(self, mercato):
        self.markets = {"1.1": mercato}


class _Quadro:
    def __init__(self, mercato):
        self.handler_queue = []
        self.markets = _Mercati(mercato)
        self._market_middleware = []
        self.ore = []

    def simulated_datetime(self, adesso):
        self.ore.append(adesso)


def _ordine_lapse(size: float = 2.0):
    from flumine import BaseStrategy
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    class _Strategia(BaseStrategy):
        def check_market_book(self, market, market_book):  # pragma: no cover
            return False

        def process_market_book(self, market, market_book):  # pragma: no cover
            return None

    trade = Trade(market_id="1.1", selection_id=1, handicap=0.0,
                  strategy=_Strategia(market_filter={}))
    return trade.create_order(side="BACK", order_type=LimitOrder(
        price=1000.0, size=size, persistence_type="LAPSE"))


def _sequenza(riusa: bool, libri):
    """Fa passare `libri` da `_a_flumine` con la memoria accesa o spenta; torna
    (contatori e residui dopo ogni book, stato delle due regole, book applicati)."""
    import flumine.config as fconf

    vecchio, prima = B.RIUSA_LAPSE, fconf.simulated
    B.RIUSA_LAPSE, fconf.simulated = riusa, True
    try:
        ordini = [_ordine_lapse(), _ordine_lapse(3.0)]
        mercato = _Mercato(ordini)
        motore = B.MotoreReplay(_Quadro(mercato))
        dopo_ogni_book = []
        for libro in libri:
            motore._a_flumine(libro)
            dopo_ogni_book.append((motore.lapse_al_fischio, motore.lapse_alla_sospensione,
                                   [round(o.size_remaining, 2) for o in ordini]))
        return (dopo_ogni_book, dict(motore._in_gioco), dict(motore._stato_mercato),
                len(mercato.libri))
    finally:
        B.RIUSA_LAPSE, fconf.simulated = vecchio, prima


def test_lapse_stesso_book_riconsegnato_uguale_alla_via_lenta():
    pre = _BookFinto(False)
    fischio = _BookFinto(True, secondi=1)
    sospeso = _BookFinto(True, "SUSPENDED", secondi=2)
    riaperto = _BookFinto(True, secondi=3)
    libri = [pre, pre, pre, fischio, fischio, sospeso, sospeso, riaperto, riaperto, pre]
    veloce, lento = _sequenza(True, libri), _sequenza(False, libri)
    assert veloce == lento
    # il test non e' muto: il fischio ha davvero ucciso i due appoggiati
    assert lento[0][3][0] == 2 and lento[0][3][2] == [0.0, 0.0]
    assert lento[3] == len(libri)            # ogni book e' arrivato al mercato


def test_lapse_book_nuovo_dopo_riconsegne_scatta_ancora():
    """FALSIFICAZIONE: una memoria per market_id (e non per oggetto) salterebbe
    il fischio, che arriva con un book NUOVO dopo tante riconsegne del vecchio."""
    pre = _BookFinto(False)
    fischio = _BookFinto(True, secondi=1)
    veloce = _sequenza(True, [pre, pre, pre, fischio])
    assert veloce[0][-1][0] == 2, "il fischio non ha ucciso gli appoggiati"
    assert veloce[0][-1][2] == [0.0, 0.0]


def test_lapse_sospensione_con_book_nuovo_dopo_riconsegne():
    """FALSIFICAZIONE: la sospensione in gioco arriva con un book NUOVO; un
    ordine nato dopo il fischio deve morire anche se il book precedente era
    stato riconsegnato molte volte."""
    import flumine.config as fconf

    prima = fconf.simulated
    fconf.simulated = True
    try:
        in_gioco = _BookFinto(True)
        sospeso = _BookFinto(True, "SUSPENDED", secondi=2)
        mercato = _Mercato([])
        motore = B.MotoreReplay(_Quadro(mercato))
        motore._a_flumine(in_gioco)
        motore._a_flumine(in_gioco)
        nuovo = _ordine_lapse()
        mercato.blotter.append(nuovo)        # l'uscita appoggiata dopo il fischio
        motore._a_flumine(in_gioco)
        motore._a_flumine(sospeso)
        assert motore.lapse_alla_sospensione == 1
        assert nuovo.size_remaining == 0.0
    finally:
        fconf.simulated = prima


# ===========================================================================
# 3. LA CHIUSURA DEL MERCATO senza i resoconti simulati che nessuno ascolta
# ===========================================================================
_MID = "1.259475537"


def _definizione(stato: str, in_play: bool = True) -> Any:
    """La `MarketDefinition` VERA dello stream (betfairlightweight)."""
    from betfairlightweight.resources.streamingresources import MarketDefinition

    return MarketDefinition(
        betDelay=5, bettingType="ODDS", bspMarket=False, bspReconciled=False,
        complete=True, crossMatching=True, discountAllowed=True, eventId="35760084",
        eventTypeId="1", inPlay=in_play, marketBaseRate=5.0,
        marketTime="2026-06-30T16:00:00.000Z", numberOfActiveRunners=2,
        numberOfWinners=1, persistenceEnabled=True, regulators="MR_INT",
        runnersVoidable=False, status=stato, timezone="GMT", turnInPlayEnabled=True,
        version=1, marketType="OVER_UNDER_35",
        runners=[{"id": 1222344, "sortPriority": 1, "status": "ACTIVE", "hc": 0.0},
                 {"id": 1222345, "sortPriority": 2, "status": "ACTIVE", "hc": 0.0}])


def _book_stream(stato: str, vincitore: int = 1222345) -> Any:
    """Un `MarketBook` VERO con la definizione dello stream, aperto o chiuso."""
    from betfairlightweight.resources.bettingresources import MarketBook

    def runner(sid: int) -> Dict[str, Any]:
        st = "ACTIVE" if stato == "OPEN" else ("WINNER" if sid == vincitore else "LOSER")
        return {"selectionId": sid, "handicap": 0.0, "status": st, "adjustmentFactor": None,
                "ex": {"availableToBack": [], "availableToLay": [], "tradedVolume": []}}
    return MarketBook(
        market_definition=_definizione(stato), marketId=_MID, isMarketDataDelayed=False,
        status=stato, betDelay=5, bspReconciled=False, complete=True, inplay=True,
        numberOfWinners=1, numberOfRunners=2, numberOfActiveRunners=2,
        totalMatched=1000.0, totalAvailable=0.0, crossMatching=True,
        runnersVoidable=False, version=1, runners=[runner(1222344), runner(1222345)])


def _scena_chiusura(muti: bool, controllo: bool = False, info: bool = False):
    """Un quadro flumine VERO con un mercato, una strategia che registra le
    chiusure e due ordini abbinati (uno per selezione); il book CLOSED arriva tre
    volte (come la riemissione di flumine). Torna tutto cio' che si puo' osservare."""
    import logging as _logging

    import flumine.config as fconf
    from flumine import BaseStrategy, FlumineSimulation
    from flumine.controls.loggingcontrols import LoggingControl
    from flumine.events import events as fevents
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    visti: list = []

    class _Strategia(BaseStrategy):
        def check_market_book(self, market, market_book):  # pragma: no cover
            return False

        def process_market_book(self, market, market_book):  # pragma: no cover
            return None

        def process_closed_market(self, market, market_book):
            visti.append((market.market_id, market_book.status,
                          [r.status for r in market_book.runners]))

    def _eventi_ascoltati(controllo_vero: Any) -> list:
        """Svuota la coda VERA del logging control (flumine la consuma in un
        thread: qui la si legge in ordine) e racconta ogni evento."""
        out = []
        while not controllo_vero.logging_queue.empty():
            ev = controllo_vero.logging_queue.get_nowait()
            nome = type(ev).__name__
            if nome == "ClearedOrdersEvent":
                out.append(("orders", ev.event.market_id, len(ev.event.orders)))
            elif nome == "ClearedOrdersMetaEvent":
                out.append(("meta", len(ev.event)))
            elif nome == "ClearedMarketsEvent":
                out.append(("markets", [o.market_id for o in ev.event.orders],
                            [o.profit for o in ev.event.orders]))
            else:
                out.append((nome,))
        return out

    log = _logging.getLogger("flumine.baseflumine")
    livello, vecchio = log.level, B.CHIUSURA_SENZA_RESOCONTI_MUTI
    prima = fconf.simulated
    try:
        fconf.simulated = True
        log.setLevel(_logging.INFO if info else _logging.WARNING)
        B.CHIUSURA_SENZA_RESOCONTI_MUTI = muti
        q = FlumineSimulation(client=B.cliente_simulato())
        ascolto = LoggingControl()
        if controllo:
            q._logging_controls.append(ascolto)
        strategia = _Strategia(market_filter={})
        q.add_strategy(strategia)
        mercato = q._add_market(_MID, _book_stream("OPEN"))
        ordini = []
        for sid, lato, prezzo in ((1222344, "LAY", 1.6), (1222345, "BACK", 2.5)):
            trade = Trade(market_id=_MID, selection_id=sid, handicap=0.0,
                          strategy=strategia)
            o = trade.create_order(side=lato, order_type=LimitOrder(price=prezzo, size=4.0))
            o.update_client(q.clients.get_default())
            o.simulated.size_matched = 4.0
            o.simulated.average_price_matched = prezzo
            o.simulated.matched = [[0, prezzo, 4.0]]
            mercato.blotter[o.id] = o
            ordini.append(o)
        chiuso = _book_stream("CLOSED")
        with B.simulazione_flumine():
            for _ in range(3):
                q._process_close_market(event=fevents.CloseMarketEvent(chiuso))
        return {
            "strategia": visti,
            "chiuso": mercato.closed,
            "book": mercato.market_book is chiuso,
            "mercati": sorted(q.markets.markets),
            "ordini": [(o.runner_status, o.market_type, o.number_of_dead_heat_winners,
                        o.profit, o.status) for o in ordini],
            "eventi_ascolto": _eventi_ascoltati(ascolto),
        }
    finally:
        fconf.simulated = prima
        log.setLevel(livello)
        B.CHIUSURA_SENZA_RESOCONTI_MUTI = vecchio


def test_chiusura_muta_uguale_alla_vera():
    veloce, vera = _scena_chiusura(True), _scena_chiusura(False)
    assert veloce == vera
    # il test non e' muto: tre chiusure viste, esito e P&L degli ordini scritti
    assert len(vera["strategia"]) == 3
    assert vera["strategia"][0][2] == ["LOSER", "WINNER"]
    assert vera["ordini"][0][0] == "LOSER" and vera["ordini"][1][0] == "WINNER"
    assert vera["ordini"][0][3] == 4.0 and vera["ordini"][1][3] == 6.0


def test_chiusura_con_un_ascoltatore_e_la_vera():
    """FALSIFICAZIONE: con un logging control montato i resoconti di
    regolamento DEVONO arrivare (la via muta li perderebbe)."""
    veloce, vera = _scena_chiusura(True, controllo=True), _scena_chiusura(False, controllo=True)
    assert veloce == vera
    tipi = [e[0] for e in vera["eventi_ascolto"]]
    assert tipi.count("meta") == 3 and tipi.count("markets") == 3
    assert ("markets", [_MID], [10.0]) in vera["eventi_ascolto"]


def test_chiusura_con_log_info_acceso_e_la_vera(monkeypatch):
    """FALSIFICAZIONE: con il log INFO di flumine acceso si usa la funzione
    VERA (i suoi `logger.info` di regolamento sono osservabili)."""
    from flumine import baseflumine

    righe = []
    monkeypatch.setattr(baseflumine.logger, "info",
                        lambda msg, *a, **k: righe.append(msg % a if a else msg))
    _scena_chiusura(True, info=True)
    assert righe.count("Market level cleared") == 3
    assert righe.count("Market cleared") == 3


def test_chiusura_impronta_di_flumine_e_ripristino():
    """La copia vale per QUESTO flumine: impronta uguale (se flumine cambia, il
    banco usa la vera e questo test lo dice) e all'uscita torna la funzione vera."""
    from flumine.baseflumine import BaseFlumine

    assert B._impronta_chiusura_flumine() == B._IMPRONTA_CHIUSURA_FLUMINE
    vera = BaseFlumine.__dict__["_process_close_market"]
    with B.simulazione_flumine():
        assert BaseFlumine.__dict__["_process_close_market"] is not vera
    assert BaseFlumine.__dict__["_process_close_market"] is vera
