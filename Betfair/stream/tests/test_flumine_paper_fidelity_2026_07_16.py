"""CERTIFICATO DI FEDELTÀ PAPER — flumine 2.13.11 (sorgente installato in .venv).

Certificazione RUNTIME del comportamento REALE del paper live di flumine
(``BetfairClient(paper_trade=True)`` -> SimulatedExecution + SimulatedMiddleware
sul flusso live). Ogni test PINNA il sorgente installato: se un upgrade di
flumine cambia queste regole, questi test DEVONO rompersi.

Tutti i riferimenti file:linea sono relativi a
``.venv/Lib/site-packages/flumine/`` (versione 2.13.11).

=============================== GARANTITO ====================================
G-1  ROUTING: con paper_trade=True l'execution del client è
     ``flumine.simulated_execution`` (clients/baseclient.py:83-84) — place/
     cancel/update/replace NON passano MAI da BetfairExecution, quindi
     NESSUNA chiamata REST di ordini all'exchange. L'order stream reale è
     sostituito da SimulatedOrderStream (streams/streams.py:91-94), che legge
     solo il blotter locale (streams/simulatedorderstream.py:38-43).
     ATTENZIONE (non è un ordine, ma è rete): login / keep_alive /
     update_account_details restano chiamate REALI all'exchange — servono per
     la sessione dello stream mercato (clients/betfairclient.py:24-108).

G-2  MIDDLEWARE: ``clients.simulated`` è True se un client ha paper_trade
     (clients/clients.py:80-86) e il framework aggiunge da solo
     SimulatedMiddleware in add_client (baseflumine.py:91-94); viene invocata
     su OGNI market book del flusso live (baseflumine.py:164-166).

G-3  BET DELAY IN-PLAY: APPLICATO DAVVERO. Il package prende
     ``bet_delay = market.market_book.bet_delay`` (execution/transaction.py:266),
     cioè marketDefinition.betDelay dello stream (betfairlightweight
     MarketBook.bet_delay). In paper live ``execute_place`` fa
     ``time.sleep(order_package.bet_delay + config.place_latency)`` REALE
     (execution/simulatedexecution.py:35-36) e SOLO DOPO legge il market book
     CORRENTE (riga 37) e matcha: durante il delay il prezzo può scappare,
     esattamente come live. Idem replace (righe 109-112).
     Pre-play betDelay=0 -> si dorme solo place_latency.

G-4  LATENZE: place_latency=0.120s, cancel=0.170, update=0.150, replace=0.280
     (config.py:21-24), dormite davvero in paper (simulatedexecution.py:36,
     59, 85, 112).

G-5  MATCHING AL PIAZZAMENTO (simulation/simulatedorder.py:139-239):
     - prezzo disponibile -> fill immediato camminando il ladder visibile,
       LIMITATO dal volume mostrato (_process_price_matched:348-368): i fill
       NON sono regalati oltre la size visibile; il resto resta EXECUTABLE.
     - prezzo NON disponibile -> 0 matched, ordine in coda con
       PIQ = size già esposta al tuo prezzo (righe 232-238).

G-6  CODA/PIQ: i fill successivi arrivano SOLO dal traded volume DELTA
     calcolato da RunnerAnalytics (markets/middleware.py:256-288) e processato
     da _process_traded (simulatedorder.py:457-497): prima si consuma la PIQ,
     poi tocca a te. Niente volume scambiato al tuo prezzo = niente fill.

G-7  SOSPENSIONE: su cambio versione mercato con status SUSPENDED gli ordini
     con persistence LAPSE lapsano (simulatedorder.py:57-62) — il caso gol.
     Runner REMOVED -> ordine voidato (markets/middleware.py:100-107).

G-8  DEFAULT SANI: config.simulation_available_prices=False (config.py:5) ->
     in paper live NON esiste il fill "ottimistico" sui prezzi disponibili;
     config.simulated_strategy_isolation=True (config.py:4) -> anti doppio
     conteggio della liquidità passiva PER STRATEGY (middleware.py:192-206).

============================ NON GARANTITO / GAP =============================
GAP-1  DIMEZZAMENTO DEL TRADED: _calculate_process_traded usa
       ``traded_size / 2`` (simulatedorder.py:479) — si assume che solo il 50%
       del volume scambiato consumi la TUA coda. La coda è quindi una
       APPROSSIMAZIONE (di solito conservativa), non una replica esatta.
GAP-2  PIQ SENZA CANCELLAZIONI: la coda davanti a te scende solo con i trade,
       mai per cancellazioni altrui ("todo estimated piq cancellations",
       simulatedorder.py:47) -> fill più LENTI del reale (pessimistico).
GAP-3  DOPPIO CONTEGGIO AL PIAZZAMENTO: il fill aggressivo al place consuma il
       ladder visibile ma NON lo depaupera per gli altri ordini: due ordini
       piazzati insieme possono mangiare lo STESSO volume. L'isolation di
       middleware.py copre solo i fill passivi post-place.
GAP-4  COMMISSIONE NON APPLICATA: ``commission_base  # not implemented``
       (clients/baseclient.py:45) -> i P&L paper sono LORDI.
GAP-5  SNAPSHOT DEL BET DELAY (OTTIMISTICO): bet_delay è congelato alla
       creazione del package (transaction.py:266); se il mercato passa in-play
       (o cambia regime post-sospensione) tra decisione e submit si dorme il
       valore VECCHIO (tipicamente 0 -> nessun delay) -> fill PIÙ VELOCE del
       reale proprio negli scenari post-gol/transizione, dove il delay conta.
       Pinnato da TestBetDelay::test_GAP5_stale_bet_delay_snapshot_is_slept.
       MITIGATO nel NOSTRO codice: FreshDelaySimulatedExecution
       (Betfair/stream/tennis_live/paper_execution.py) ri-legge il betDelay
       corrente dal market book al momento dell'esecuzione (cablato nel runner
       tennis; wiring scalper da fare a parte).
GAP-6  NIENTE ERRORI DI EXCHANGE (OTTIMISTICO): in paper il place riesce
       SEMPRE se mercato OPEN e runner ACTIVE (niente rifiuti API, niente
       latenza di rete variabile, niente ordini persi) -> il paper è PIÙ
       AFFIDABILE del reale, mai meno.

VERDETTO: il paper live flumine 2.13.11 rispetta betDelay in-play (sleep
reale + match sul book DOPO il delay), rispetta coda e volume (PIQ + traded
delta, fill mai oltre la size visibile) e non tocca l'exchange per gli ordini.
I gap NON sono tutti conservativi: GAP-1/GAP-2/GAP-4 sono neutri/conservativi;
sono invece OTTIMISTICI GAP-3 (più ordini aggressivi nello stesso istante
mangiano lo stesso volume), GAP-5 (betDelay stantio nelle transizioni
pre-off->in-play/post-sospensione: fill più veloce del reale — mitigato da
FreshDelaySimulatedExecution nel nostro codice) e GAP-6 (place sempre
riuscito: nessun rifiuto/perdita d'ordine che dal vivo esiste).
"""
from __future__ import annotations

from unittest import mock

import pytest

import flumine  # NB: l'import applica il patch EX/SP (dict ladder) — flumine/__init__.py:13-14
from betfairlightweight.resources.bettingresources import RunnerBook

from flumine import config
from flumine.baseflumine import BaseFlumine
from flumine.clients import BetfairClient
from flumine.clients.clients import VenueType
from flumine.execution.betfairexecution import BetfairExecution
from flumine.execution.simulatedexecution import SimulatedExecution
from flumine.execution.transaction import Transaction
from flumine.flumine import Flumine
from flumine.markets.middleware import RunnerAnalytics, SimulatedMiddleware
from flumine.order.ordertype import OrderTypes
from flumine.order.orderpackage import OrderPackageType
from flumine.simulation.simulatedorder import SimulatedOrder
from flumine.streams.orderstream import OrderStream
from flumine.streams.simulatedorderstream import SimulatedOrderStream

SELECTION_ID = 123
HANDICAP = 0.0


# --------------------------------------------------------------------------
# helper: oggetti minimi (stesso stile dei test ufficiali flumine su github,
# tests/test_simulated.py — order/package mockati, runner book REALE)
# --------------------------------------------------------------------------

def make_runner(atb=None, atl=None, traded=None, status="ACTIVE") -> RunnerBook:
    """RunnerBook betfairlightweight REALE; dopo l'import di flumine il ladder
    resta lista di dict (patch flumine/__init__.py:13-14 -> patching.EX)."""
    return RunnerBook(
        selectionId=SELECTION_ID,
        status=status,
        handicap=HANDICAP,
        ex={
            "availableToBack": atb or [],
            "availableToLay": atl or [],
            "tradedVolume": traded or [],
        },
    )


def make_market_book(runner, status="OPEN", version=1, publish_time=1_000):
    mb = mock.Mock()
    mb.status = status
    mb.version = version
    mb.publish_time_epoch = publish_time
    mb.bsp_reconciled = False
    mb.inplay = True
    mb.runners = [runner]
    return mb


def make_order(side="BACK", price=2.10, size=10.0, persistence="LAPSE"):
    order = mock.Mock()
    order.id = "order-1"
    order.side = side
    order.selection_id = SELECTION_ID
    order.handicap = HANDICAP
    order.order_type.ORDER_TYPE = OrderTypes.LIMIT
    order.order_type.price = price
    order.order_type.size = size
    order.order_type.persistence_type = persistence
    order.client.simulated_full_match = False
    order.client.paper_trade = True
    return order


def make_order_package(market_version=None, best_price_execution=True):
    package = mock.Mock()
    package.market_version = market_version
    package.client.best_price_execution = best_price_execution
    return package


# ==========================================================================
# (a) WIRING: paper_trade=True -> SimulatedExecution + SimulatedMiddleware
# ==========================================================================


class TestPaperWiring:
    def _paper_framework(self):
        betting_client = mock.Mock(lightweight=False, username="paper-user")
        client = BetfairClient(betting_client, paper_trade=True)
        return Flumine(client=client), client

    def test_paper_client_execution_is_simulated(self):
        """clients/baseclient.py:83-84 — paper_trade -> simulated_execution."""
        framework, client = self._paper_framework()
        assert client.paper_trade is True
        assert isinstance(client.execution, SimulatedExecution)
        assert client.execution is framework.simulated_execution
        assert client.execution is not framework.betfair_execution

    def test_paper_client_makes_clients_simulated_true(self):
        """clients/clients.py:80-86."""
        framework, _ = self._paper_framework()
        assert framework.clients.simulated is True

    def test_framework_adds_simulated_middleware_automatically(self):
        """baseflumine.py:91-94 — SimulatedMiddleware aggiunta dal framework."""
        framework, _ = self._paper_framework()
        middleware = [
            m
            for m in framework._market_middleware
            if isinstance(m, SimulatedMiddleware)
        ]
        assert len(middleware) == 1

    def test_paper_order_stream_is_simulated_not_exchange(self):
        """streams/streams.py:91-94 — ordini letti dal blotter locale,
        NESSUNA sottoscrizione all'order stream reale dell'exchange."""
        framework, _ = self._paper_framework()
        streams = list(framework.streams)
        assert any(isinstance(s, SimulatedOrderStream) for s in streams)
        assert not any(isinstance(s, OrderStream) for s in streams)

    def test_live_client_wiring_is_the_opposite(self):
        """Controprova: senza paper_trade -> BetfairExecution, niente
        middleware simulata, order stream REALE."""
        betting_client = mock.Mock(lightweight=False, username="live-user")
        client = BetfairClient(betting_client)  # paper_trade=False
        framework = Flumine(client=client)
        assert isinstance(client.execution, BetfairExecution)
        assert framework.clients.simulated is False
        assert not any(
            isinstance(m, SimulatedMiddleware) for m in framework._market_middleware
        )
        assert any(isinstance(s, OrderStream) for s in framework.streams)


# ==========================================================================
# (b) MATCHING al piazzamento: prezzo non disponibile -> coda; disponibile ->
#     fill secondo le regole reali, MAI oltre il volume visibile
# ==========================================================================


class TestPlaceMatching:
    def test_back_price_not_available_stays_unmatched_with_piq(self):
        """simulatedorder.py:139-239 — back a prezzo sopra il best NON viene
        matchato: entra in coda con PIQ = size già esposta al suo prezzo
        (lato available_to_lay per un BACK, righe 184 e 232-238)."""
        order = make_order(side="BACK", price=2.10, size=10.0)
        simulated = SimulatedOrder(order)
        runner = make_runner(
            atb=[{"price": 2.00, "size": 100.0}],
            atl=[{"price": 2.04, "size": 20.0}, {"price": 2.10, "size": 55.0}],
        )
        market_book = make_market_book(runner)

        response = simulated.place(make_order_package(), market_book, {}, 1001)

        assert response.status == "SUCCESS"
        assert response.order_status == "EXECUTABLE"  # NON matched
        assert simulated.size_matched == 0
        assert simulated.average_price_matched == 0
        assert simulated._piq == 55.0  # coda davanti = size visibile al prezzo
        assert simulated.size_remaining == 10.0

    def test_back_price_available_fill_capped_by_visible_volume(self):
        """simulatedorder.py:176-183 + _process_price_matched:348-368 — fill
        immediato al meglio disponibile, ma SOLO fino al volume mostrato:
        200 richiesti contro 30@2.02 + 50@2.00 -> 80 matched, 120 in coda."""
        order = make_order(side="BACK", price=2.00, size=200.0)
        simulated = SimulatedOrder(order)
        runner = make_runner(
            atb=[{"price": 2.02, "size": 30.0}, {"price": 2.00, "size": 50.0}],
            atl=[{"price": 2.06, "size": 10.0}],
        )
        market_book = make_market_book(runner)

        response = simulated.place(make_order_package(), market_book, {}, 1002)

        assert response.status == "SUCCESS"
        assert simulated.size_matched == 80.0  # NON regalato oltre il ladder
        # 30@2.02 (price improvement, best_price_execution=True) + 50@2.00
        assert simulated.average_price_matched == pytest.approx(2.01, abs=0.001)
        assert simulated.size_remaining == 120.0
        assert response.order_status == "EXECUTABLE"
        assert simulated.matched == [[1_000, 2.02, 30.0], [1_000, 2.00, 50.0]]

    def test_back_full_fill_when_volume_sufficient(self):
        order = make_order(side="BACK", price=2.00, size=20.0)
        simulated = SimulatedOrder(order)
        runner = make_runner(atb=[{"price": 2.00, "size": 100.0}])
        market_book = make_market_book(runner)

        response = simulated.place(make_order_package(), market_book, {}, 1003)

        assert response.order_status == "EXECUTION_COMPLETE"
        assert simulated.size_matched == 20.0
        assert simulated.average_price_matched == 2.00

    def test_lay_symmetric_behaviour(self):
        """Lay a prezzo sotto il best lay -> coda con PIQ dal lato back."""
        order = make_order(side="LAY", price=1.90, size=10.0)
        simulated = SimulatedOrder(order)
        runner = make_runner(
            atb=[{"price": 1.88, "size": 40.0}, {"price": 1.90, "size": 33.0}],
            atl=[{"price": 1.95, "size": 100.0}],
        )
        market_book = make_market_book(runner)

        response = simulated.place(make_order_package(), market_book, {}, 1004)

        assert response.order_status == "EXECUTABLE"
        assert simulated.size_matched == 0
        assert simulated._piq == 33.0

    def test_place_on_suspended_market_fails(self):
        """simulatedorder.py:69-75 — mercato non OPEN -> FAILURE + void."""
        order = make_order()
        simulated = SimulatedOrder(order)
        runner = make_runner(atb=[{"price": 2.0, "size": 10.0}])
        market_book = make_market_book(runner, status="SUSPENDED")

        response = simulated.place(make_order_package(), market_book, {}, 1005)

        assert response.status == "FAILURE"
        assert response.error_code == "ERROR_IN_ORDER"
        assert simulated.size_voided == 10.0


# ==========================================================================
# (b2) CODA: fill SOLO da traded volume delta, PIQ consumata prima
# ==========================================================================


class TestQueueFidelity:
    def _queued_back(self):
        """Ordine back 2.10 in coda con PIQ 55 (come nel test place)."""
        order = make_order(side="BACK", price=2.10, size=10.0)
        simulated = SimulatedOrder(order)
        runner = make_runner(
            atb=[{"price": 2.00, "size": 100.0}],
            atl=[{"price": 2.10, "size": 55.0}],
        )
        market_book = make_market_book(runner)
        simulated.place(make_order_package(), market_book, {}, 2001)
        assert simulated._piq == 55.0
        return simulated, runner

    def test_no_traded_volume_no_fill(self):
        """Niente scambi al tuo prezzo = NESSUN fill (non regalato)."""
        simulated, runner = self._queued_back()
        market_book = make_market_book(runner)
        simulated(market_book, (runner, {}))
        assert simulated.size_matched == 0
        assert simulated._piq == 55.0

    def test_traded_at_worse_price_does_not_fill_back(self):
        """simulatedorder.py:469 — per un BACK conta solo traded >= prezzo."""
        simulated, runner = self._queued_back()
        market_book = make_market_book(runner)
        simulated(market_book, (runner, {2.08: 500.0}))
        assert simulated.size_matched == 0
        assert simulated._piq == 55.0

    def test_queue_consumed_then_filled_with_halved_traded(self):
        """GAP-1 PINNATO: _calculate_process_traded (simulatedorder.py:478-497)
        DIMEZZA il traded (traded_size/2) prima di consumare PIQ e fillare.

        60 scambiati @2.10 -> 30 'utili': PIQ 55 -> 25, matched 0.
        Altri 60 -> 30 'utili': 25 chiudono la PIQ, 5 matchano a te.
        """
        simulated, runner = self._queued_back()
        market_book = make_market_book(runner)

        simulated(market_book, (runner, {2.10: 60.0}))
        assert simulated.size_matched == 0
        assert simulated._piq == 25.0  # 55 - 60/2

        simulated(market_book, (runner, {2.10: 60.0}))
        assert simulated._piq == 0
        assert simulated.size_matched == 5.0  # 60/2 - 25
        assert simulated.average_price_matched == 2.10
        assert simulated.size_remaining == 5.0

        # ulteriore flusso completa l'ordine (10 scambiati -> 5 utili)
        simulated(market_book, (runner, {2.10: 10.0}))
        assert simulated.size_matched == 10.0
        assert simulated.status == "EXECUTION_COMPLETE"

    def test_suspension_with_version_change_lapses_order(self):
        """G-7 — gol/sospensione: version bump + SUSPENDED -> LAPSE
        (simulatedorder.py:57-62)."""
        simulated, runner = self._queued_back()
        market_book = make_market_book(runner, status="SUSPENDED", version=2)
        simulated(market_book, (runner, {}))
        assert simulated.size_lapsed == 10.0
        assert simulated.size_remaining == 0
        assert simulated.status == "EXECUTION_COMPLETE"

    def test_runner_analytics_computes_traded_delta(self):
        """markets/middleware.py:256-288 — il 'traded' passato al matching è il
        DELTA di traded volume fra due update dello stream (volume REALE)."""
        runner_t0 = make_runner(traded=[{"price": 2.10, "size": 100.0}])
        analytics = RunnerAnalytics(runner_t0)
        assert analytics.traded == {}

        runner_t1 = make_runner(
            traded=[{"price": 2.10, "size": 160.0}, {"price": 2.12, "size": 8.0}]
        )
        analytics(runner_t1)
        assert analytics.traded == {2.10: 60.0, 2.12: 8.0}

        # nessun nuovo scambio -> delta vuoto
        runner_t2 = make_runner(
            traded=[{"price": 2.10, "size": 160.0}, {"price": 2.12, "size": 8.0}]
        )
        analytics(runner_t2)
        assert analytics.traded == {}


# ==========================================================================
# (c) BET DELAY: applicato come sleep REALE prima del matching, valore preso
#     dal market_definition.betDelay del market book
# ==========================================================================


class TestBetDelay:
    def _package(self, bet_delay, order):
        package = mock.MagicMock()
        package.client.paper_trade = True
        package.bet_delay = bet_delay
        package.market_id = "1.234"
        package.package_type = OrderPackageType.PLACE
        package.__iter__.return_value = iter([order])
        package.__len__.return_value = 1
        package.place_instructions = [{}]
        return package

    def test_execute_place_sleeps_bet_delay_plus_place_latency(self):
        """execution/simulatedexecution.py:35-36 — betDelay in-play (5s) +
        place_latency (0.120s) dormiti DAVVERO in paper live."""
        mock_flumine = mock.MagicMock()
        execution = SimulatedExecution(mock_flumine)
        order = mock.MagicMock()
        order.simulated.place.return_value = mock.Mock(
            status="SUCCESS", bet_id=None, error_code=None
        )
        package = self._package(bet_delay=5, order=order)

        with mock.patch(
            "flumine.execution.simulatedexecution.time.sleep"
        ) as mock_sleep:
            execution.execute_place(package, http_session=None)

        mock_sleep.assert_called_once_with(5 + config.place_latency)
        order.executable.assert_called_once()

    def test_pre_play_bet_delay_zero_only_place_latency(self):
        mock_flumine = mock.MagicMock()
        execution = SimulatedExecution(mock_flumine)
        order = mock.MagicMock()
        order.simulated.place.return_value = mock.Mock(
            status="SUCCESS", bet_id=None, error_code=None
        )
        package = self._package(bet_delay=0, order=order)

        with mock.patch(
            "flumine.execution.simulatedexecution.time.sleep"
        ) as mock_sleep:
            execution.execute_place(package, http_session=None)

        mock_sleep.assert_called_once_with(config.place_latency)

    def test_matching_uses_market_book_read_AFTER_the_delay(self):
        """execution/simulatedexecution.py:36-37 — l'ordine degli eventi è
        sleep(betDelay+latency) POI lettura del market book corrente: il
        matching avviene sul book che si è mosso durante il delay (fedeltà
        in-play: il prezzo può scappare)."""
        events = []
        mock_flumine = mock.MagicMock()
        mock_market = mock.MagicMock()

        def _get_market(key):
            events.append("read_book")
            return mock_market

        mock_flumine.markets.markets.__getitem__.side_effect = _get_market
        execution = SimulatedExecution(mock_flumine)
        order = mock.MagicMock()
        order.simulated.place.return_value = mock.Mock(
            status="SUCCESS", bet_id=None, error_code=None
        )
        package = self._package(bet_delay=5, order=order)

        with mock.patch(
            "flumine.execution.simulatedexecution.time.sleep",
            side_effect=lambda _s: events.append("sleep"),
        ):
            execution.execute_place(package, http_session=None)

        assert events == ["sleep", "read_book"]
        # e il matching riceve proprio QUEL book
        order.simulated.place.assert_called_once_with(
            package, mock_market.market_book, {}, 100000000001
        )

    def test_bet_delay_sourced_from_market_book_of_transaction(self):
        """execution/transaction.py:266 — bet_delay del package =
        market.market_book.bet_delay (marketDefinition.betDelay via
        betfairlightweight MarketBook, resources/bettingresources.py:600)."""
        mock_market = mock.Mock()
        mock_market.market_id = "1.234"
        mock_market.market_book.bet_delay = 7
        client = mock.Mock()
        client.VENUE = VenueType.BETFAIR
        client.execution.VENUE = VenueType.SIMULATED  # paper -> simulated exec
        transaction = Transaction(
            mock_market, id_=1, async_place_orders=False, client=client
        )

        packages = transaction._create_order_package(
            [(mock.Mock(), None)], OrderPackageType.PLACE
        )

        assert len(packages) == 1
        assert packages[0].bet_delay == 7
        # orderpackage.py:74-77: delay simulato complessivo = latency + betDelay
        assert packages[0].simulated_delay == pytest.approx(
            config.place_latency + 7
        )

    def test_GAP5_stale_bet_delay_snapshot_is_slept(self):
        """GAP-5 PINNATO (transaction.py:266 + orderpackage.py:56 +
        simulatedexecution.py:35-36): il bet_delay è CONGELATO alla creazione
        del package. Se al momento dell'esecuzione il mercato è ormai in-play
        (betDelay corrente 3s sul market book del framework), flumine vanilla
        dorme comunque lo SNAPSHOT VECCHIO (0) -> fill più veloce del reale
        proprio nelle transizioni pre-off->in-play/post-sospensione
        (OTTIMISTICO). Mitigazione nel NOSTRO codice:
        tennis_live/paper_execution.py::FreshDelaySimulatedExecution
        (testata in tennis_live/tests/test_paper_execution_gap5.py)."""
        mock_flumine = mock.MagicMock()
        # il market book CORRENTE nel framework è già in-play, delay 3s...
        mock_flumine.markets.markets.__getitem__.return_value.market_book.bet_delay = 3
        execution = SimulatedExecution(mock_flumine)
        order = mock.MagicMock()
        order.simulated.place.return_value = mock.Mock(
            status="SUCCESS", bet_id=None, error_code=None
        )
        # ...ma il package fu creato PRE-OFF: snapshot betDelay=0
        package = self._package(bet_delay=0, order=order)

        with mock.patch(
            "flumine.execution.simulatedexecution.time.sleep"
        ) as mock_sleep:
            execution.execute_place(package, http_session=None)

        # dorme lo SNAPSHOT stantio (0), NON il betDelay corrente (3)
        mock_sleep.assert_called_once_with(0 + config.place_latency)

    def test_paper_handler_runs_async_in_thread_pool(self):
        """execution/simulatedexecution.py:27-28 — in paper il place va nel
        thread pool: lo sleep del betDelay NON blocca il loop strategie
        (stesso comportamento asincrono del live)."""
        mock_flumine = mock.MagicMock()
        execution = SimulatedExecution(mock_flumine)
        package = mock.Mock()
        package.package_type = OrderPackageType.PLACE
        package.client.paper_trade = True
        with mock.patch.object(execution, "_thread_pool") as mock_pool:
            execution.handler(package)
        mock_pool.submit.assert_called_once_with(
            execution.execute_place, package, None
        )


# ==========================================================================
# (d) place_latency / default di config PINNATI + modalità ottimistica (gap)
# ==========================================================================


class TestConfigPins:
    def test_flumine_version_pinned(self):
        assert flumine.__version__ == "2.13.11"

    def test_latency_defaults(self):
        """config.py:21-24 — latenze di simulazione."""
        assert config.place_latency == 0.120
        assert config.cancel_latency == 0.170
        assert config.update_latency == 0.150
        assert config.replace_latency == 0.280

    def test_queue_mode_is_default_not_optimistic(self):
        """config.py:4-5 — la coda su volume è il default; il fill ottimistico
        sui prezzi disponibili è OFF; isolation per strategy ON."""
        assert config.simulation_available_prices is False
        assert config.simulated_strategy_isolation is True

    def test_cancel_latency_slept_in_paper(self):
        """execution/simulatedexecution.py:58-59."""
        mock_flumine = mock.MagicMock()
        execution = SimulatedExecution(mock_flumine)
        order = mock.MagicMock()
        order.simulated.cancel.return_value = mock.Mock(
            status="SUCCESS", bet_id=None, error_code=None
        )
        order.size_remaining = 0
        package = mock.MagicMock()
        package.client.paper_trade = True
        package.market_id = "1.234"
        package.package_type = OrderPackageType.CANCEL
        package.__iter__.return_value = iter([order])
        with mock.patch(
            "flumine.execution.simulatedexecution.time.sleep"
        ) as mock_sleep:
            execution.execute_cancel(package, http_session=None)
        mock_sleep.assert_called_once_with(config.cancel_latency)

    def test_optimistic_available_prices_mode_gifts_fills(self):
        """GAP DOCUMENTATO: con config.simulation_available_prices=True il
        matching riempie al TUO prezzo contro la size disponibile e AZZERA la
        PIQ (simulatedorder.py:52-55 + 499-528) — modalità ottimistica che
        IGNORA la coda. Il default False (test sopra) è ciò che rende il
        paper live 'demo = live senza soldi'. NON attivarla mai in paper."""
        order = make_order(side="BACK", price=2.10, size=10.0)
        simulated = SimulatedOrder(order)
        runner = make_runner(
            atb=[{"price": 2.00, "size": 100.0}],
            atl=[{"price": 2.10, "size": 55.0}],
        )
        market_book = make_market_book(runner)
        simulated.place(make_order_package(), market_book, {}, 3001)
        assert simulated._piq == 55.0

        runner_later = make_runner(atb=[{"price": 2.10, "size": 40.0}])
        original = config.simulation_available_prices
        try:
            config.simulation_available_prices = True
            simulated(make_market_book(runner_later), (runner_later, {}))
        finally:
            config.simulation_available_prices = original

        # fill regalato SENZA consumare la coda: ecco perché deve restare OFF
        assert simulated.size_matched == 10.0
        assert simulated._piq == 0

    def test_simulated_order_active_when_paper_trade(self):
        """simulatedorder.py:658-661 — l'oggetto simulated è 'attivo' (bool
        True) quando il client è paper_trade, anche senza config.simulated:
        è il gancio che fa usare il ramo simulato a tutto il framework."""
        assert config.simulated is False  # runtime live/paper, non backtest
        order = make_order()
        order.client.paper_trade = True
        assert bool(SimulatedOrder(order)) is True
        order_live = make_order()
        order_live.client.paper_trade = False
        assert bool(SimulatedOrder(order_live)) is False
