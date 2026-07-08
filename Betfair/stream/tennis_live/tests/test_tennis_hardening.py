"""Test di hardening del runner live TENNIS (money-critical + architetturali).

Coprono i fix verificati contro flumine 2.13.11:
  #1 STREAM UNICO   — bot e capture condividono la stessa MarketStream (grouping flumine);
  #2 ARM/DISARM     — il disarm DISABILITA subito il bot e accoda un TERMINATOR (stop reale);
  #3 KILL-SWITCH    — OFF/PAPER forzano paper_trade + dry_run (soldi veri solo in LIVE);
  #4 CROSS-MODE     — una riga di coda di mode opposta è rifiutata SENZA esecuzione;
  #9 GREENUP        — l'azione greenup FALLISCE forte (no più no-op ok=True).

Nessuna rete: flumine Streams è reale ma leggera (nessuna subscription avviata); DB e
framework sono mockati.
"""
from __future__ import annotations

import queue
import types

import pytest
from betfairlightweight.filters import streaming_market_data_filter

from Betfair.stream.tennis_live import tennis_runner
from Betfair.stream.tennis_live import tennis_live_order_worker as tow


# ---------------------------------------------------------------------------
# #3 KILL-SWITCH DI MODALITA': OFF/PAPER ⇒ paper_trade forzato (mai soldi veri)
# ---------------------------------------------------------------------------
def test_build_order_client_off_forces_paper_trade():
    client, enabled = tennis_runner.build_order_client(object(), "OFF")
    assert client.paper_trade is True
    assert enabled is False  # worker ordini NON registrato in OFF


def test_build_order_client_paper_forces_paper_trade():
    client, enabled = tennis_runner.build_order_client(object(), "PAPER")
    assert client.paper_trade is True
    assert enabled is True


def test_build_order_client_live_is_real():
    client, enabled = tennis_runner.build_order_client(object(), "LIVE")
    assert client.paper_trade is False  # UNICA modalità con soldi veri
    assert enabled is True


def test_instantiate_bot_forces_dry_run_outside_live():
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    bot = tennis_runner._instantiate_bot(
        "tennis_scalper", {"stake": 2.0, "dry_run": False, "params": {}},
        "1.100", {}, lambda *a, **k: None, df, "PAPER",
    )
    assert bot.dry_run is True                # forzato: fuori da LIVE non piazza
    assert bot.market_data_filter is df       # #1: stesso data_filter della capture


def test_instantiate_bot_live_respects_control():
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    bot = tennis_runner._instantiate_bot(
        "tennis_scalper", {"stake": 2.0, "dry_run": False, "params": {}},
        "1.100", {}, lambda *a, **k: None, df, "LIVE",
    )
    assert bot.dry_run is False


# ---------------------------------------------------------------------------
# #1 STREAM UNICO: capture + bot con stesso filtro+data_filter ⇒ UNA MarketStream
# ---------------------------------------------------------------------------
def _fake_flumine_for_streams():
    # Streams usa solo flumine.SIMULATED (in __call__) e lo passa a MarketStream.
    return types.SimpleNamespace(SIMULATED=False)


def _data_filter():
    return streaming_market_data_filter(
        fields=list(tennis_runner.STREAM_FIELDS), ladder_levels=tennis_runner.LADDER_DEPTH
    )


def test_bot_shares_capture_marketstream():
    from flumine.streams.streams import Streams

    df = _data_filter()
    cap = tennis_runner._make_capture("1.111", "ev1")
    cap.market_data_filter = df  # come fa il runner prima di add_strategy
    bot = tennis_runner._instantiate_bot(
        "tennis_scalper", {"stake": 2.0, "dry_run": True, "params": {}},
        "1.111", {}, lambda *a, **k: None, df, "PAPER",
    )
    streams = Streams(_fake_flumine_for_streams())
    streams(cap)
    streams(bot)
    # grouping flumine (add_stream): market_filter + market_data_filter + streaming_timeout
    # + conflate_ms coincidono ⇒ il bot RIUSA la stream della capture (una subscription).
    assert len(streams) == 1
    assert set(bot.stream_ids) == set(cap.stream_ids)


def test_bot_diff_data_filter_opens_second_stream():
    """Controllo NEGATIVO = il bug #1: senza market_data_filter condiviso flumine apre una
    SECONDA subscription (esattamente ciò che il fix evita threadando data_filter)."""
    from flumine.streams.streams import Streams

    df_capture = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    df_bot = streaming_market_data_filter(fields=["EX_ALL_OFFERS"], ladder_levels=3)
    cap = tennis_runner._make_capture("1.112", "ev2")
    cap.market_data_filter = df_capture
    bot = tennis_runner._instantiate_bot(
        "tennis_scalper", {"stake": 2.0, "dry_run": True, "params": {}},
        "1.112", {}, lambda *a, **k: None, df_bot, "PAPER",
    )
    streams = Streams(_fake_flumine_for_streams())
    streams(cap)
    streams(bot)
    assert len(streams) == 2  # data_filter diverso ⇒ due stream (subscription duplicata)


# ---------------------------------------------------------------------------
# #2 ARM/DISARM: il disarm DISABILITA il bot e accoda un TERMINATOR (stop reale)
# ---------------------------------------------------------------------------
class _FakeStrategy:
    def __init__(self):
        self.dry_run = False
        self.max_order_exposure = 100.0
        self.max_selection_exposure = 100.0
        self.max_market_exposure = None
        self.stats = {}

    def check_market_book(self, market, market_book):  # noqa: ARG002
        return True  # "vorrebbe" tradare finché non lo disabilitiamo


def test_disarm_disables_bot_and_stops_framework(monkeypatch):
    statuses = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: statuses.append((a, k)))
    # nessun bot desiderato ⇒ il bot ospitato va disarmato
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        lambda *a, **k: [])

    strat = _FakeStrategy()
    session = tennis_runner.TennisLiveSession(trading=object())
    session.market_meta = {"ev1": {"market_id": "1.1"}}
    session.hosted = {("ev1", "tennis_scalper"): strat}

    fake_flumine = types.SimpleNamespace(_running=True, handler_queue=queue.Queue())
    tennis_runner.bot_control_worker({}, fake_flumine, session)

    # bot DISABILITATO subito (non può più piazzare nella finestra pre-restart)
    assert strat._tennis_disabled is True
    assert strat.dry_run is True
    assert strat.check_market_book(None, None) is False
    assert strat.max_order_exposure == 0.0
    # restart richiesto + stop REALE del framework (TERMINATOR accodato, non solo _running)
    assert session.restart_requested.is_set()
    assert fake_flumine._running is False
    ev = fake_flumine.handler_queue.get_nowait()
    assert ev.EVENT_TYPE.name == "TERMINATOR"
    # status DB scritto 'stopped' e NON sovrascritto da 'running' (heartbeat saltato)
    written = [a[2] for (a, k) in statuses]
    assert "stopped" in written
    assert "running" not in written


def test_stop_framework_enqueues_terminator():
    fake_flumine = types.SimpleNamespace(_running=True, handler_queue=queue.Queue())
    tennis_runner._stop_framework(fake_flumine)
    assert fake_flumine._running is False
    ev = fake_flumine.handler_queue.get_nowait()
    assert ev.EVENT_TYPE.name == "TERMINATOR"


# ---------------------------------------------------------------------------
# #4 CROSS-MODE: riga di mode opposta rifiutata SENZA esecuzione
# ---------------------------------------------------------------------------
def test_cross_mode_row_rejected_without_dispatch(monkeypatch):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")
    claimed, errored = [], []
    monkeypatch.setattr(tow.tennis_db, "list_pending_tennis_orders", lambda limit=5: [
        {"id": 7, "payload": {"action": "place", "mode": "live", "market_id": "1.1",
                              "selection_id": 5, "side": "back", "price": 2.0, "size": 2}},
    ])
    monkeypatch.setattr(tow.tennis_db, "claim_tennis_order",
                        lambda rid: (claimed.append(rid) or True))
    monkeypatch.setattr(tow.tennis_db, "write_tennis_order_error",
                        lambda rid, res: errored.append((rid, res)))

    def _no_dispatch(*a, **k):
        raise AssertionError("dispatch NON deve essere chiamato per una riga cross-mode")
    monkeypatch.setattr(tow, "_dispatch", _no_dispatch)

    tow.tennis_live_order_worker({}, flumine=None, session=None)

    assert claimed == [7]                      # claim atomico (transizione unica)
    assert len(errored) == 1
    assert errored[0][0] == 7
    assert errored[0][1]["ok"] is False
    assert "non servibile" in (errored[0][1]["error"] or "")


def test_same_mode_row_is_dispatched(monkeypatch):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "PAPER")
    done, dispatched = [], []
    monkeypatch.setattr(tow.tennis_db, "list_pending_tennis_orders", lambda limit=5: [
        {"id": 8, "payload": {"action": "place", "mode": "paper", "market_id": "1.1",
                              "selection_id": 5, "side": "back", "price": 2.0, "size": 2}},
    ])
    monkeypatch.setattr(tow.tennis_db, "claim_tennis_order", lambda rid: True)
    monkeypatch.setattr(tow.tennis_db, "write_tennis_order_done",
                        lambda rid, res: done.append((rid, res)))
    monkeypatch.setattr(tow, "_dispatch",
                        lambda f, s, cmd, ref: (dispatched.append(cmd) or
                                                {"ok": True, "action": cmd["action"]}))
    monkeypatch.setattr(tow, "_mirror_order", lambda *a, **k: None)

    tow.tennis_live_order_worker({}, flumine=None, session=None)

    assert len(dispatched) == 1                 # stessa mode ⇒ eseguita
    assert dispatched[0]["mode"] == "paper"
    assert done and done[0][0] == 8


# ---------------------------------------------------------------------------
# #9 GREENUP: FAIL LOUDLY (niente più no-op ok=True)
# ---------------------------------------------------------------------------
def test_greenup_fails_loudly():
    with pytest.raises(ValueError):
        tow._dispatch(flumine=None, session=None,
                      cmd={"action": "greenup", "mode": "paper"}, cust_ref="awtq1")
