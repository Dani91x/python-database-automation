"""Unit test CLUSTER 1 — costruzione/registrazione di LiveTradingStrategy nel runner.

Money-critical-adjacent: nessuna rete, nessun login, nessun ordine reale. Si usa un
``api_client`` fittizio (SimpleNamespace) per costruire il VERO client flumine PAPER e si
verifica che la strategia specchio venga costruita ESATTAMENTE come fa ``runner.setup_and_run``
(con ``market_filter``) e che sia registrabile in un framework ``Flumine`` senza sollevare.

Copre:
  * HIGH-1: senza ``market_filter`` BaseStrategy di flumine solleva TypeError → il runner non
    parte. Con il filtro esplicito (come ora nel call-site) NON solleva ed è registrabile;
    process_orders resta dispatchabile (lo specchio funziona).
  * LOW-1: in PAPER la latenza simulata (PAPER_SIMULATED_LATENCY_MS) viene applicata a
    ``flumine.config.place_latency`` (ms→s).
  * LOW-2: gli interval dei BackgroundWorker accettano float sub-secondo senza troncamento.
"""
from __future__ import annotations

import types

import pytest
from betfairlightweight.filters import streaming_market_filter

import flumine.config as flumine_config
from flumine import Flumine
from flumine.worker import BackgroundWorker

from Betfair.stream import runner
from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy


def _fake_api_client() -> types.SimpleNamespace:
    # niente attributo .lightweight → BaseClient salta `assert betting_client.lightweight is False`.
    # `username` serve a flumine.clients.add_client (Flumine.__init__) che legge betting_client.username.
    return types.SimpleNamespace(username="test-paper")


# ---------------------------------------------------------------------------
# HIGH-1: costruzione come il runner + registrabilità
# ---------------------------------------------------------------------------
def test_live_strategy_requires_market_filter():
    """Senza market_filter BaseStrategy di flumine solleva TypeError (la causa di HIGH-1)."""
    with pytest.raises(TypeError):
        LiveTradingStrategy(session=None, mode="paper")  # type: ignore[call-arg]


def test_live_strategy_constructed_like_runner_does_not_raise():
    """Costruzione ESATTAMENTE come il call-site del runner: non solleva e tiene il filtro."""
    market_ids = ["1.111", "1.222"]
    strat = LiveTradingStrategy(
        market_filter=streaming_market_filter(market_ids=market_ids),
        session=None,
        mode="paper",
    )
    assert strat.market_filter == streaming_market_filter(market_ids=market_ids)
    # advisory: nessun auto-trading
    assert strat.check_market_book(object(), object()) is False


def test_live_strategy_registrable_in_framework():
    """La strategia è registrabile nel framework (come fa runner.setup_and_run) senza rete.

    Replica il client PAPER del runner via build_order_client(fake_api, 'PAPER') e aggiunge la
    strategia con add_strategy: deve creare gli stream e archiviarla senza sollevare.
    """
    client, orders_enabled = runner.build_order_client(_fake_api_client(), "PAPER")
    assert orders_enabled is True
    framework = Flumine(client=client)
    strat = LiveTradingStrategy(
        market_filter=streaming_market_filter(market_ids=["1.999"]),
        session=None,
        mode="paper",
    )
    # non deve sollevare (HIGH-1: prima sollevava TypeError già in costruzione)
    framework.add_strategy(strat)
    assert strat in list(framework.strategies)
    # process_orders è un hook esistente e invocabile (lo specchio è best-effort: lista vuota = no-op)
    assert strat.process_orders(object(), []) is None


# ---------------------------------------------------------------------------
# LOW-1: latenza simulata PAPER applicata a flumine.config.place_latency
# ---------------------------------------------------------------------------
def test_paper_applies_simulated_latency(monkeypatch):
    prev = flumine_config.place_latency
    try:
        monkeypatch.setattr(runner, "PAPER_SIMULATED_LATENCY_MS", 250)
        runner.build_order_client(_fake_api_client(), "PAPER")
        assert flumine_config.place_latency == pytest.approx(0.250)
    finally:
        flumine_config.place_latency = prev


def test_off_and_live_do_not_touch_simulated_latency(monkeypatch):
    """OFF/LIVE non devono toccare la latenza simulata (è una leva solo-PAPER)."""
    for mode in ("OFF", "LIVE"):
        prev = flumine_config.place_latency
        sentinel = 0.077
        flumine_config.place_latency = sentinel
        try:
            monkeypatch.setattr(runner, "PAPER_SIMULATED_LATENCY_MS", 999)
            runner.build_order_client(_fake_api_client(), mode)
            assert flumine_config.place_latency == sentinel
        finally:
            flumine_config.place_latency = prev


# ---------------------------------------------------------------------------
# LOW-2: gli interval float sub-secondo non vengono troncati
# ---------------------------------------------------------------------------
def test_background_worker_keeps_float_subsecond_interval():
    """Regola LOW-2: il poll della coda ordini 0.5s NON deve diventare 0 o 1 (int troncava)."""
    fake_fn = lambda *a, **k: None  # noqa: E731
    w = BackgroundWorker(None, function=fake_fn, interval=0.5 or 1.0, name="x")
    assert w.interval == 0.5
    assert isinstance(w.interval, float)
