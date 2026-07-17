"""CANTIERE D (17/07) — fix GAP-5 (betDelay stantio) + restart bloccato VISIBILE.

1) FreshDelaySimulatedExecution: il paper dorme il betDelay VIGENTE al momento
   dell'esecuzione (ri-letto dal market book streamato), non lo snapshot della
   decisione (transaction.py:266). Lo scenario stantio di flumine vanilla è
   pinnato in Betfair/stream/tests/test_flumine_paper_fidelity_2026_07_16.py
   (TestBetDelay::test_GAP5_stale_bet_delay_snapshot_is_slept).
2) install_fresh_delay_execution: wiring pulito (sostituisce
   framework.simulated_execution -> shutdown corretto in __exit__) sui client
   paper di un framework flumine REALE.
3) Restart bloccato visibile: un bot A non-flat rinvia il restart; i bot IN
   CODA (armati/richiesti, anche su ALTRI eventi) mostrano il motivo sul
   control-row (campo ``error`` esistente, nessuna migrazione) e il motivo
   viene ripulito quando il restart parte.
"""
from __future__ import annotations

import queue
import types
from unittest import mock

import pytest

from flumine import config as flumine_config
from flumine.clients import BetfairClient
from flumine.execution.simulatedexecution import SimulatedExecution
from flumine.flumine import Flumine
from flumine.order.orderpackage import OrderPackageType

from Betfair.stream.tennis_live import tennis_runner
from Betfair.stream.tennis_live.paper_execution import (
    FreshDelaySimulatedExecution,
    install_fresh_delay_execution,
)

MARKET_ID = "1.234"


# ---------------------------------------------------------------------------
# helper: package/order/flumine mockati (stesso stile del certificato fedeltà)
# ---------------------------------------------------------------------------
def _order(place_status="SUCCESS"):
    order = mock.MagicMock()
    order.simulated.place.return_value = mock.Mock(
        status=place_status, bet_id=None, error_code=None
    )
    order.simulated.cancel.return_value = mock.Mock(
        status="SUCCESS", bet_id=None, error_code=None, size_cancelled=2.0
    )
    return order


def _package(bet_delay, order, package_type=OrderPackageType.PLACE):
    package = mock.MagicMock()
    package.client.paper_trade = True
    package.bet_delay = bet_delay
    package.market_id = MARKET_ID
    package.package_type = package_type
    package.__iter__.return_value = iter([order])
    package.__len__.return_value = 1
    package.place_instructions = [{}]
    package.replace_instructions = [{"newPrice": 2.0}]
    return package


def _flumine_with_book(bet_delay):
    """flumine mock con markets.markets DICT reale (come in flumine) e un
    market book corrente col betDelay indicato."""
    market = mock.MagicMock()
    market.market_book.bet_delay = bet_delay
    fl = mock.MagicMock()
    fl.markets.markets = {MARKET_ID: market}
    return fl, market


# ---------------------------------------------------------------------------
# (1) betDelay FRESCO dormito al posto dello snapshot stantio
# ---------------------------------------------------------------------------
class TestFreshDelayExecution:
    def test_place_sleeps_current_bet_delay_not_stale_snapshot(self):
        """Package creato PRE-OFF (snapshot 0) ma mercato ormai in-play
        (betDelay corrente 3): si dorme 3 + place_latency, come farebbe
        l'exchange all'arrivo dell'ordine."""
        fl, _market = _flumine_with_book(bet_delay=3)
        execution = FreshDelaySimulatedExecution(fl)
        package = _package(bet_delay=0, order=_order())

        with mock.patch(
            "flumine.execution.simulatedexecution.time.sleep"
        ) as mock_sleep:
            execution.execute_place(package, http_session=None)

        mock_sleep.assert_called_once_with(3 + flumine_config.place_latency)
        assert package.bet_delay == 3  # snapshot allineato al regime corrente

    def test_place_regime_change_after_suspension_delay_can_also_drop(self):
        """Vale anche al contrario (delay snapshottato ALTO, regime corrente
        più basso): si segue SEMPRE il mercato, mai lo snapshot."""
        fl, _market = _flumine_with_book(bet_delay=1)
        execution = FreshDelaySimulatedExecution(fl)
        package = _package(bet_delay=5, order=_order())

        with mock.patch(
            "flumine.execution.simulatedexecution.time.sleep"
        ) as mock_sleep:
            execution.execute_place(package, http_session=None)

        mock_sleep.assert_called_once_with(1 + flumine_config.place_latency)

    def test_replace_also_refreshed(self):
        fl, _market = _flumine_with_book(bet_delay=3)
        execution = FreshDelaySimulatedExecution(fl)
        package = _package(
            bet_delay=0, order=_order(), package_type=OrderPackageType.REPLACE
        )

        with mock.patch(
            "flumine.execution.simulatedexecution.time.sleep"
        ) as mock_sleep:
            execution.execute_replace(package, http_session=None)

        mock_sleep.assert_called_once_with(3 + flumine_config.replace_latency)

    def test_simulated_delay_kept_coherent(self):
        """orderpackage.simulated_delay (usato per logging/terzi) viene
        ricalcolato dopo il refresh."""
        fl, _market = _flumine_with_book(bet_delay=3)
        execution = FreshDelaySimulatedExecution(fl)
        package = _package(bet_delay=0, order=_order())

        with mock.patch("flumine.execution.simulatedexecution.time.sleep"):
            execution.execute_place(package, http_session=None)

        package.calc_simulated_delay.assert_called()
        assert package.simulated_delay is package.calc_simulated_delay.return_value

    @pytest.mark.parametrize(
        "setup",
        ["market_missing", "book_missing", "delay_none", "delay_not_numeric"],
    )
    def test_fail_safe_keeps_snapshot(self, setup):
        """Refresh BEST-EFFORT: se mercato/book/delay non sono leggibili si
        tiene lo snapshot originale (comportamento flumine invariato)."""
        fl, market = _flumine_with_book(bet_delay=3)
        if setup == "market_missing":
            fl.markets.markets = {}
        elif setup == "book_missing":
            market.market_book = None
        elif setup == "delay_none":
            market.market_book.bet_delay = None
        elif setup == "delay_not_numeric":
            market.market_book.bet_delay = "boom"
        execution = FreshDelaySimulatedExecution(fl)
        package = _package(bet_delay=0, order=_order())
        if setup == "market_missing":
            # super().execute_place fa markets[market_id]: rimettiamo il market
            # DOPO il refresh per isolare il fail-safe del solo refresh
            fl.markets.markets = mock.MagicMock()
            fl.markets.markets.get.return_value = None

        with mock.patch(
            "flumine.execution.simulatedexecution.time.sleep"
        ) as mock_sleep:
            execution.execute_place(package, http_session=None)

        mock_sleep.assert_called_once_with(0 + flumine_config.place_latency)
        assert package.bet_delay == 0


# ---------------------------------------------------------------------------
# (2) wiring: install su un framework flumine REALE + runner tennis
# ---------------------------------------------------------------------------
class TestInstallWiring:
    def _paper_framework(self):
        betting_client = mock.Mock(lightweight=False, username="paper-user")
        client = BetfairClient(betting_client, paper_trade=True)
        return Flumine(client=client), client

    def test_install_replaces_framework_execution_and_repoints_client(self):
        framework, client = self._paper_framework()
        assert isinstance(client.execution, SimulatedExecution)
        assert not isinstance(client.execution, FreshDelaySimulatedExecution)

        fresh = install_fresh_delay_execution(framework)

        # framework.simulated_execution sostituita -> __exit__ (baseflumine.py:525)
        # spegne il thread-pool GIUSTO a ogni restart del runner
        assert framework.simulated_execution is fresh
        assert isinstance(fresh, FreshDelaySimulatedExecution)
        # il client paper ora esegue con la variante a betDelay fresco
        assert client.execution is fresh

    def test_install_is_idempotent(self):
        framework, client = self._paper_framework()
        first = install_fresh_delay_execution(framework)
        second = install_fresh_delay_execution(framework)
        assert first is second
        assert client.execution is first

    def test_install_does_not_touch_live_execution(self):
        betting_client = mock.Mock(lightweight=False, username="live-user")
        client = BetfairClient(betting_client)  # paper_trade=False
        framework = Flumine(client=client)
        live_exec = client.execution
        install_fresh_delay_execution(framework)
        assert client.execution is live_exec  # LIVE resta su BetfairExecution

    def test_runner_wires_install_for_non_live_modes(self):
        """Test COMPORTAMENTALE del wiring (review 17/07: via il check sul
        sorgente): ``_wire_paper_execution`` installa davvero la subclass su
        un framework reale per PAPER/OFF e non tocca nulla in LIVE."""
        for mode in ("PAPER", "OFF"):
            betting_client = mock.Mock(lightweight=False, username=f"u-{mode}")
            client = BetfairClient(betting_client, paper_trade=True)
            framework = Flumine(client=client)
            assert tennis_runner._wire_paper_execution(framework, mode) is True
            assert isinstance(framework.simulated_execution,
                              FreshDelaySimulatedExecution)
            assert client.execution is framework.simulated_execution

        betting_client = mock.Mock(lightweight=False, username="live-user")
        client = BetfairClient(betting_client)  # paper_trade=False
        framework = Flumine(client=client)
        live_exec = client.execution
        sim_exec = framework.simulated_execution
        assert tennis_runner._wire_paper_execution(framework, "LIVE") is False
        assert client.execution is live_exec           # LIVE intoccato
        assert framework.simulated_execution is sim_exec


# ---------------------------------------------------------------------------
# (3) restart bloccato VISIBILE sui control-row dei bot in attesa
# ---------------------------------------------------------------------------
class _FakeStrategy:
    def __init__(self):
        self.dry_run = False
        self.force_flat = False
        self.stats = {}


def _fake_flumine():
    return types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])


def _session_with_blocker():
    session = tennis_runner.TennisLiveSession(trading=object())
    session.market_meta = {"evA": {"market_id": "1.1"}}
    session.hosted = {("evA", "tennis_scalper"): _FakeStrategy()}
    return session


@pytest.fixture()
def _db(monkeypatch):
    """tennis_db finto: registra le scritture del motivo d'attesa."""
    calls = {"wait": [], "activity": []}
    controls = [
        # bot BLOCCANTE, ospitato su evA (non va MAI annotato: è lui il problema)
        {"event_id": "evA", "bot_key": "tennis_scalper", "status": "running"},
        # bot B in CODA su un ALTRO evento: armato, mai ospitato -> da annotare
        {"event_id": "evB", "bot_key": "tennis_pro", "status": "requested"},
        # bot_key ignoto: mai annotato
        {"event_id": "evB", "bot_key": "sconosciuto", "status": "requested"},
    ]
    monkeypatch.setattr(
        tennis_runner.tennis_db, "list_tennis_bot_controls",
        lambda event_id=None, statuses=None, **k: list(controls),
    )
    monkeypatch.setattr(
        tennis_runner.tennis_db, "set_tennis_bot_wait_reason",
        lambda ev, bk, reason: calls["wait"].append((ev, bk, reason)),
    )
    monkeypatch.setattr(
        tennis_runner.tennis_db, "write_tennis_bot_activity",
        lambda ev, bk, kind, payload: calls["activity"].append((ev, bk, kind)),
    )
    return calls


def test_deferred_restart_marks_waiting_bots_with_reason(monkeypatch, _db):
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)
    session = _session_with_blocker()
    fl = _fake_flumine()

    assert tennis_runner._request_restart(fl, session, "nuovo follow") is False

    # il bot in coda su evB è annotato col motivo ESPLICITO...
    assert len(_db["wait"]) == 1
    ev, bk, reason = _db["wait"][0]
    assert (ev, bk) == ("evB", "tennis_pro")
    assert "in attesa" in reason
    assert "tennis_scalper@evA" in reason      # CHI blocca (evento X non-flat)
    assert "non-flat" in reason
    assert "nuovo follow" in reason            # perché serviva il restart
    # ...e il bloccante ospitato NON viene toccato
    assert all(k[0] != "evA" for k in _db["wait"])


def test_waiting_mark_written_once_per_episode(monkeypatch, _db):
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)
    session = _session_with_blocker()
    fl = _fake_flumine()

    tennis_runner._request_restart(fl, session, "test")
    tennis_runner._request_restart(fl, session, "test")  # secondo giro: no spam

    assert len(_db["wait"]) == 1


def test_waiting_mark_cleared_when_restart_proceeds(monkeypatch, _db):
    flat = {"value": False}
    monkeypatch.setattr(
        tennis_runner, "_strategy_is_flat", lambda *a, **k: flat["value"]
    )
    session = _session_with_blocker()
    fl = _fake_flumine()

    assert tennis_runner._request_restart(fl, session, "test") is False
    assert session._restart_wait_marked == {("evB", "tennis_pro")}

    # il bloccante torna flat -> il restart parte e il motivo viene RIPULITO
    flat["value"] = True
    assert tennis_runner._request_restart(fl, session, "test") is True
    assert ("evB", "tennis_pro", None) in _db["wait"]
    assert session._restart_wait_marked == set()
    assert session.restart_requested.is_set()


def test_waiting_mark_cleared_on_forced_paper_restart(monkeypatch, _db):
    """Anche il restart FORZATO (grazia scaduta, PAPER) ripulisce il motivo."""
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)
    session = _session_with_blocker()
    session.order_mode = "PAPER"
    fl = _fake_flumine()

    assert tennis_runner._request_restart(fl, session, "test") is False
    session.restart_deferred_since -= tennis_runner._RESTART_GRACE_S + 1
    assert tennis_runner._request_restart(fl, session, "test") is True
    assert ("evB", "tennis_pro", None) in _db["wait"]
    assert session._restart_wait_marked == set()


def test_waiting_mark_is_best_effort_never_breaks_worker(monkeypatch):
    """DB KO: il rinvio del restart resta corretto, nessuna eccezione."""
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls", _boom)
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda *a, **k: None)
    session = _session_with_blocker()
    fl = _fake_flumine()

    assert tennis_runner._request_restart(fl, session, "test") is False
    assert session._restart_wait_marked == set()
