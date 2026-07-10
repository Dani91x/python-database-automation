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
    """Riga di controllo SPARITA (né armata né 'stopping'): il bot va disabilitato subito
    e — con blotter FLAT verificato — lo stato scritto è 'stopped' (mai bugiardo)."""
    statuses = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: statuses.append((a, k)))
    # nessun bot desiderato (né in 'stopping') ⇒ il bot ospitato va disarmato
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        lambda *a, **k: [])

    strat = _FakeStrategy()
    session = tennis_runner.TennisLiveSession(trading=object())
    session.market_meta = {"ev1": {"market_id": "1.1"}}
    session.hosted = {("ev1", "tennis_scalper"): strat}

    # markets=[] ⇒ nessun ordine/esposizione ⇒ _strategy_is_flat=True ⇒ 'stopped' veritiero
    fake_flumine = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])
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


# ---------------------------------------------------------------------------
# DISARM col contratto 'stopping' (fix review CRITICAL): chiusura FLAT reale
# ---------------------------------------------------------------------------
class _FakeFlatBot(_FakeStrategy):
    """Bot con supporto force_flat (come lo scalper)."""

    def __init__(self):
        super().__init__()
        self.force_flat = False


def _controls_with_stopping(bot_key="tennis_scalper"):
    def _list(event_id, statuses=None, **k):  # noqa: ARG001
        if statuses and "stopping" in statuses:
            return [{"bot_key": bot_key, "status": "stopping"}]
        return []  # nessun bot armato
    return _list


def test_disarm_stopping_sets_force_flat_and_keeps_bot_alive(monkeypatch):
    """Fase 1 del disarm: status 'stopping' ⇒ force_flat=True, bot NON disabilitato,
    NESSUN restart e NESSUNO 'stopped' finché la posizione non è flat."""
    statuses = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: statuses.append((a, k)))
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_with_stopping())
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    strat = _FakeFlatBot()
    session = tennis_runner.TennisLiveSession(trading=object())
    session.market_meta = {"ev1": {"market_id": "1.1"}}
    session.hosted = {("ev1", "tennis_scalper"): strat}
    fake_flumine = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.bot_control_worker({}, fake_flumine, session)

    assert strat.force_flat is True                       # chiusura richiesta al bot
    assert not getattr(strat, "_tennis_disabled", False)  # bot ANCORA attivo (deve chiudere)
    assert not session.restart_requested.is_set()         # stream vivo per farlo lavorare
    assert ("ev1", "tennis_scalper") in session.stopping_deadline
    written = [a[2] for (a, k) in statuses]
    assert "stopped" not in written and "error" not in written


def test_disarm_stopping_marks_stopped_when_flat(monkeypatch):
    """Fase 2: quando il blotter conferma FLAT, il bot viene disabilitato e lo stato
    passa a 'stopped' (veritiero) con restart per rimuoverlo dallo stream."""
    statuses = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: statuses.append((a, k)))
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_with_stopping())
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: True)

    strat = _FakeFlatBot()
    session = tennis_runner.TennisLiveSession(trading=object())
    session.market_meta = {"ev1": {"market_id": "1.1"}}
    session.hosted = {("ev1", "tennis_scalper"): strat}
    # force_flat già chiesto in un giro precedente, finestra ancora aperta
    strat.force_flat = True
    session.stopping_deadline[("ev1", "tennis_scalper")] = 1e18
    fake_flumine = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.bot_control_worker({}, fake_flumine, session)

    assert strat._tennis_disabled is True
    assert session.restart_requested.is_set()
    written = [a[2] for (a, k) in statuses]
    assert written == ["stopped"]
    assert ("ev1", "tennis_scalper") not in session.stopping_deadline


def test_disarm_stopping_timeout_not_flat_is_error(monkeypatch):
    """Fase 2 (finestra scaduta, NON flat): stato 'error' con avviso di verifica manuale —
    MAI uno 'stopped' bugiardo con la posizione aperta."""
    statuses = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: statuses.append((a, k)))
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_with_stopping())
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    strat = _FakeFlatBot()
    session = tennis_runner.TennisLiveSession(trading=object())
    session.market_meta = {"ev1": {"market_id": "1.1"}}
    session.hosted = {("ev1", "tennis_scalper"): strat}
    strat.force_flat = True
    session.stopping_deadline[("ev1", "tennis_scalper")] = 0.0  # finestra già scaduta
    fake_flumine = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.bot_control_worker({}, fake_flumine, session)

    assert strat._tennis_disabled is True
    assert session.restart_requested.is_set()
    assert len(statuses) == 1
    (a, k) = statuses[0]
    assert a[2] == "error"
    assert "NON flat" in (k.get("error") or "")


def test_disarm_stopping_bot_without_force_flat_is_honest(monkeypatch):
    """Bot SENZA chiusura autonoma (pro/flb/swing): disabilitato subito, stato finale
    in base al flat REALE ('error' se la posizione resta aperta)."""
    statuses = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: statuses.append((a, k)))
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_with_stopping(bot_key="tennis_pro"))
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    strat = _FakeStrategy()  # nessun attributo force_flat
    session = tennis_runner.TennisLiveSession(trading=object())
    session.market_meta = {"ev1": {"market_id": "1.1"}}
    session.hosted = {("ev1", "tennis_pro"): strat}
    fake_flumine = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.bot_control_worker({}, fake_flumine, session)

    assert strat._tennis_disabled is True
    (a, k) = statuses[0]
    assert a[2] == "error"  # non flat ⇒ mai 'stopped' bugiardo


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


# ---------------------------------------------------------------------------
# AUTO-SPEGNIMENTO tennis (fix 2026-07-08): mai con bot attivi o disarm in corso
# ---------------------------------------------------------------------------
def test_tennis_lifecycle_shuts_down_when_idle(monkeypatch):
    monkeypatch.setattr(tennis_runner.tennis_db, "list_pending_tennis_follows", lambda: [])
    session = tennis_runner.TennisLiveSession(trading=object())
    fl = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.lifecycle_worker({}, fl, session)

    assert session.shutdown_requested.is_set()
    assert fl._running is False


def test_tennis_lifecycle_never_stops_with_active_bot(monkeypatch):
    monkeypatch.setattr(tennis_runner.tennis_db, "list_pending_tennis_follows", lambda: [])
    session = tennis_runner.TennisLiveSession(trading=object())
    session.hosted = {("ev1", "tennis_scalper"): _FakeStrategy()}  # bot ATTIVO
    fl = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.lifecycle_worker({}, fl, session)

    assert not session.shutdown_requested.is_set()  # il denaro prima del comfort
    assert fl._running is True


def test_tennis_lifecycle_never_stops_during_disarm(monkeypatch):
    monkeypatch.setattr(tennis_runner.tennis_db, "list_pending_tennis_follows", lambda: [])
    session = tennis_runner.TennisLiveSession(trading=object())
    session.stopping_deadline[("ev1", "tennis_scalper")] = 1e18  # disarm in corso
    fl = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.lifecycle_worker({}, fl, session)

    assert not session.shutdown_requested.is_set()


def test_tennis_lifecycle_max_hours_never_stops_with_active_bot(monkeypatch):
    """Fix review CRITICAL: nemmeno la VITA MASSIMA spegne il runner con un bot attivo."""
    monkeypatch.setattr(tennis_runner.tennis_db, "list_pending_tennis_follows", lambda: [])
    session = tennis_runner.TennisLiveSession(trading=object())
    session.hosted = {("ev1", "tennis_scalper"): _FakeStrategy()}  # bot ATTIVO
    session.started_monotonic -= (tennis_runner._TENNIS_MAX_HOURS * 3600.0 + 60.0)
    fl = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])

    tennis_runner.lifecycle_worker({}, fl, session)

    assert not session.shutdown_requested.is_set()  # il denaro prima del comfort
    assert fl._running is True


def test_tennis_lifecycle_deferred_with_live_orders(monkeypatch):
    """Ordini vivi nel blotter -> niente spegnimento anche senza bot ospitati."""
    monkeypatch.setattr(tennis_runner.tennis_db, "list_pending_tennis_follows", lambda: [])
    session = tennis_runner.TennisLiveSession(trading=object())
    blotter = types.SimpleNamespace(live_orders=[object()])
    market = types.SimpleNamespace(market_id="1.9", blotter=blotter)
    fl = types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[market])

    tennis_runner.lifecycle_worker({}, fl, session)

    assert not session.shutdown_requested.is_set()


# ===========================================================================
# BUG FIX cert 10/07 — _Capture senza i default nascosti di BaseStrategy
# (visto dal vivo: 2° ordine sulla stessa selezione RIFIUTATO da STRATEGY_EXPOSURE
#  live_trade_count(1); e max_order_exposure=10 → ordini manuali >€10 rifiutati)
# ===========================================================================
def test_capture_strategy_disables_hidden_flumine_caps():
    from Betfair.stream.tennis_live.tennis_runner import _make_capture

    s = _make_capture("1.234", "ev1")
    assert s.max_order_exposure is None        # era 10 (€10 per ordine!)
    assert s.max_selection_exposure is None    # era 100
    assert s.max_live_trade_count >= 10**9     # era 1 (un ordine vivo per selezione)
    assert s.max_trade_count >= 10**9
