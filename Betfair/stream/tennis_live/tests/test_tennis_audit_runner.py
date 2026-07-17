"""Fix AUDIT 2026-07-16 — runner/worker live tennis (money-critical).

Coprono i finding verificati in lettura del 16/07:
  #1  restart del framework SOLO a bot FLAT: con una posizione aperta il restart
      (arm/disarm o nuovo follow) viene RINVIATO (blotter nuovo e vuoto =
      posizione orfana in LIVE, stato simulato azzerato in PAPER);
  #2  greenup IMPLEMENTATO nel worker tennis (hedge dalle esposizioni fresche del
      blotter, matematica condivisa trading.greenup);
  #3  PAPER simula il bet delay in-play (~3s) di default, override via env;
  #8  righe tennis_live_positions ORFANE azzerate una volta dopo il restart;
      ordini tracciati di un framework smontato chiusi/scartati (mai EXECUTABLE
      fantasma);
  #14 la mode dello specchio e' quella CATTURATA al build, mai una ri-lettura env.
"""
from __future__ import annotations

import queue
import types

import pytest

from Betfair.stream.tennis_live import tennis_live_order_worker as tow
from Betfair.stream.tennis_live import tennis_runner


# ---------------------------------------------------------------------------
# fakes condivisi
# ---------------------------------------------------------------------------
class _FakeStrategy:
    def __init__(self):
        self.dry_run = False
        self.max_order_exposure = 100.0
        self.max_selection_exposure = 100.0
        self.max_market_exposure = None
        self.stats = {}

    def check_market_book(self, market, market_book):  # noqa: ARG002
        return True


class _FakeFlatBot(_FakeStrategy):
    def __init__(self):
        super().__init__()
        self.force_flat = False


def _fake_flumine():
    return types.SimpleNamespace(_running=True, handler_queue=queue.Queue(), markets=[])


def _session_with_bot(strat, bot_key="tennis_scalper"):
    session = tennis_runner.TennisLiveSession(trading=object())
    session.market_meta = {"ev1": {"market_id": "1.1"}}
    session.hosted = {("ev1", bot_key): strat}
    return session


def _controls_two_bots(hosted_key="tennis_scalper", new_key="tennis_pro"):
    """Il bot ospitato resta ARMATO; un secondo bot richiesto (non ospitato)
    innesca need_restart senza far scattare il ramo disarm sul primo."""
    def _list(event_id, statuses=None, **k):  # noqa: ARG001
        if statuses and "stopping" in statuses:
            return []
        return [{"bot_key": hosted_key, "status": "running"},
                {"bot_key": new_key, "status": "requested"}]
    return _list


# ---------------------------------------------------------------------------
# #1 — restart RINVIATO con bot non flat (bot_control_worker)
# ---------------------------------------------------------------------------
def test_bot_control_restart_deferred_when_not_flat(monkeypatch):
    activity = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_two_bots())
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda ev, bk, kind, payload: activity.append((ev, bk, kind)))
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    strat = _FakeFlatBot()
    session = _session_with_bot(strat)
    fl = _fake_flumine()

    tennis_runner.bot_control_worker({}, fl, session)

    # posizione NON flat: restart RINVIATO (mai blotter nuovo con posizione viva)
    assert not session.restart_requested.is_set()
    assert fl._running is True
    assert fl.handler_queue.empty()
    # il bot che sa appiattirsi riceve il force_flat + attivita' tracciata
    assert strat.force_flat is True
    assert ("ev1", "tennis_scalper", "restart_deferred") in activity


def test_bot_control_restart_deferred_logged_once_per_episode(monkeypatch):
    activity = []
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_two_bots())
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda ev, bk, kind, payload: activity.append(kind))
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    session = _session_with_bot(_FakeFlatBot())
    fl = _fake_flumine()
    tennis_runner.bot_control_worker({}, fl, session)
    tennis_runner.bot_control_worker({}, fl, session)   # secondo giro: no spam

    assert activity.count("restart_deferred") == 1


def test_restart_paper_forced_after_grace_with_stubborn_bot(monkeypatch):
    """Fix controcheck 16/07: un bot SENZA force_flat (pro/flb/swing) non può
    rinviare il restart all'infinito — in PAPER, scaduta la grazia, si forza."""
    activity = []
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda ev, bk, kind, payload: activity.append(kind))
    # fix cantiere D: il rinvio annota i bot in coda -> DB mockato (mai rete nei test)
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        lambda *a, **k: [])
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_wait_reason",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    session = _session_with_bot(_FakeStrategy(), bot_key="tennis_pro")  # niente force_flat
    session.order_mode = "PAPER"
    fl = _fake_flumine()

    # primo giro: rinviato, episodio aperto
    assert tennis_runner._request_restart(fl, session, "test") is False
    assert not session.restart_requested.is_set()
    assert session.restart_deferred_since is not None
    # grazia scaduta → il restart parte comunque (posizione SIMULATA) + attività
    session.restart_deferred_since -= tennis_runner._RESTART_GRACE_S + 1
    assert tennis_runner._request_restart(fl, session, "test") is True
    assert session.restart_requested.is_set()
    assert fl._running is False
    assert "restart_forced" in activity
    # episodio chiuso
    assert session.restart_deferred_since is None


def test_restart_live_never_forced_but_escalates_visibly(monkeypatch):
    """Fix controcheck 16/07: in LIVE il restart non si forza MAI (posizione
    reale orfana) — ma oltre la grazia il blocco diventa VISIBILE (CRITICAL),
    una sola volta per finestra (niente spam)."""
    activity = []
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda ev, bk, kind, payload: activity.append((kind, payload)))
    # fix cantiere D: il rinvio annota i bot in coda -> DB mockato (mai rete nei test)
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        lambda *a, **k: [])
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_wait_reason",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    session = _session_with_bot(_FakeStrategy(), bot_key="tennis_pro")
    session.order_mode = "LIVE"
    fl = _fake_flumine()

    assert tennis_runner._request_restart(fl, session, "test") is False
    session.restart_deferred_since -= tennis_runner._RESTART_GRACE_S + 1
    # LIVE oltre grazia: NIENTE restart, escalation CRITICAL tracciata
    assert tennis_runner._request_restart(fl, session, "test") is False
    assert not session.restart_requested.is_set()
    assert fl._running is True
    kinds = [k for k, _ in activity]
    assert "restart_blocked" in kinds
    assert "restart_forced" not in kinds
    blocked = [p for k, p in activity if k == "restart_blocked"]
    assert blocked[0]["level"] == "CRITICAL"
    # stessa finestra: nessun nuovo log (anti-spam)
    n = kinds.count("restart_blocked")
    assert tennis_runner._request_restart(fl, session, "test") is False
    assert [k for k, _ in activity].count("restart_blocked") == n


def test_bot_control_restart_proceeds_when_flat(monkeypatch):
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_status",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        _controls_two_bots())
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: True)

    session = _session_with_bot(_FakeFlatBot())
    fl = _fake_flumine()
    tennis_runner.bot_control_worker({}, fl, session)

    assert session.restart_requested.is_set()
    assert fl._running is False
    ev = fl.handler_queue.get_nowait()
    assert ev.EVENT_TYPE.name == "TERMINATOR"


def test_follow_worker_defers_restart_when_not_flat(monkeypatch):
    monkeypatch.setattr(tennis_runner.tennis_db, "list_pending_tennis_follows",
                        lambda: [{"event_id": "ev2"}])
    monkeypatch.setattr(tennis_runner.tennis_db, "write_tennis_bot_activity",
                        lambda *a, **k: None)
    # fix cantiere D: il rinvio annota i bot in coda -> DB mockato (mai rete nei test)
    monkeypatch.setattr(tennis_runner.tennis_db, "list_tennis_bot_controls",
                        lambda *a, **k: [])
    monkeypatch.setattr(tennis_runner.tennis_db, "set_tennis_bot_wait_reason",
                        lambda *a, **k: None)
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)

    session = _session_with_bot(_FakeFlatBot())
    fl = _fake_flumine()
    tennis_runner.follow_worker({}, fl, session)

    assert not session.restart_requested.is_set()   # nuovo follow NON orfana la posizione
    assert fl._running is True


def test_follow_worker_restarts_when_flat(monkeypatch):
    monkeypatch.setattr(tennis_runner.tennis_db, "list_pending_tennis_follows",
                        lambda: [{"event_id": "ev2"}])
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: True)

    session = _session_with_bot(_FakeFlatBot())
    fl = _fake_flumine()
    tennis_runner.follow_worker({}, fl, session)

    assert session.restart_requested.is_set()
    assert fl._running is False


def test_disabled_bot_never_blocks_restart(monkeypatch):
    """Un bot gia' disabilitato (disarm concluso con 'error' onesto) non blocca il
    restart: la grace del disarm e' gia' scaduta e lo stato DB avvisa l'utente."""
    monkeypatch.setattr(tennis_runner, "_strategy_is_flat", lambda *a, **k: False)
    strat = _FakeFlatBot()
    strat._tennis_disabled = True
    session = _session_with_bot(strat)
    fl = _fake_flumine()

    assert tennis_runner._request_restart(fl, session, "test") is True
    assert session.restart_requested.is_set()


# ---------------------------------------------------------------------------
# #3 — PAPER: place_latency = SOLO rete/processing (fix cantiere D 17/07).
# Il betDelay in-play arriva dal marketDefinition streamato ed è dormito da
# flumine (sleep(bet_delay + place_latency)) con valore FRESCO garantito da
# FreshDelaySimulatedExecution: il vecchio default 3000ms era doppio conteggio.
# ---------------------------------------------------------------------------
@pytest.fixture()
def _restore_place_latency():
    from flumine import config as flumine_config
    orig = flumine_config.place_latency
    yield
    flumine_config.place_latency = orig


def test_paper_latency_defaults_to_600ms_network_only(monkeypatch, _restore_place_latency):
    from flumine import config as flumine_config
    monkeypatch.delenv("TENNIS_PAPER_LATENCY_MS", raising=False)
    client, enabled = tennis_runner.build_order_client(object(), "PAPER")
    assert client.paper_trade is True and enabled is True
    # SOLO latenza rete/processing: il betDelay in-play lo aggiunge flumine dal
    # marketDefinition streamato (mai doppio conteggio nel place_latency).
    assert tennis_runner.TENNIS_PAPER_LATENCY_MS_DEFAULT == 600
    assert flumine_config.place_latency == pytest.approx(0.6)


def test_paper_latency_env_zero_disables_delay(monkeypatch, _restore_place_latency):
    from flumine import config as flumine_config
    monkeypatch.setenv("TENNIS_PAPER_LATENCY_MS", "0")
    tennis_runner.build_order_client(object(), "PAPER")
    assert flumine_config.place_latency == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# #2 — GREENUP implementato nel worker tennis
# ---------------------------------------------------------------------------
class _GreenBlotter:
    def __init__(self, w, l):
        self._w, self._l = w, l

    def get_exposures(self, strategy, lookup):  # noqa: ARG002
        return {"matched_profit_if_win": self._w, "matched_profit_if_lose": self._l}

    def strategy_orders(self, strategy):  # noqa: ARG002
        return []


def _green_market(w, l, best_back=None, best_lay=None):
    ex = types.SimpleNamespace(
        available_to_back=[{"price": best_back, "size": 100}] if best_back else [],
        available_to_lay=[{"price": best_lay, "size": 100}] if best_lay else [],
    )
    runner = types.SimpleNamespace(selection_id=5, handicap=0.0, ex=ex)
    market = types.SimpleNamespace(
        market_id="1.1",
        blotter=_GreenBlotter(w, l),
        market_book=types.SimpleNamespace(runners=[runner]),
        placed=[],
    )
    market.place_order = lambda order, customer_strategy_ref=None: (
        market.placed.append(order) or True
    )
    return market


def _green_session(market):
    return types.SimpleNamespace(
        market_meta={"ev1": {"market_id": "1.1"}},
        capture={"ev1": object()},
        tracked_orders={},
        order_mode="PAPER",
        framework_gen=0,
    )


def _green_flumine(market):
    return types.SimpleNamespace(markets=types.SimpleNamespace(markets={"1.1": market}))


def _greenup_cmd(**extra):
    base = {"action": "greenup", "mode": "paper", "market_id": "1.1",
            "selection_id": 5, "handicap": 0.0, "params": {}}
    base.update(extra)
    return base


def test_greenup_places_lay_hedge_for_back_position():
    # BACK 2 @ 2.00 aperto: W=+2.00, L=-2.00 → hedge = LAY (W-L)/p al best lay 1.90
    market = _green_market(2.0, -2.0, best_back=1.88, best_lay=1.90)
    session = _green_session(market)
    res = tow._dispatch(_green_flumine(market), session, _greenup_cmd(), "awtq9")
    assert res["ok"] is True and res["action"] == "greenup"
    assert len(market.placed) == 1
    order = market.placed[0]
    assert order.side == "LAY"
    assert order.order_type.price == pytest.approx(1.90)
    assert order.order_type.size == pytest.approx(round(4.0 / 1.90, 2))  # 2.11
    # tracciato per il reconcile dei fill asincroni (specchio ordini)
    assert "awtq9" in session.tracked_orders


def test_greenup_fraction_halves_hedge_size():
    market = _green_market(2.0, -2.0, best_back=1.88, best_lay=1.90)
    session = _green_session(market)
    res = tow._dispatch(_green_flumine(market), session,
                        _greenup_cmd(params={"fraction": 0.5}), "awtq10")
    assert res["ok"] is True
    assert market.placed[0].order_type.size == pytest.approx(round(0.5 * 4.0 / 1.90, 2))


def test_greenup_flat_position_is_noop_ok():
    market = _green_market(0.0, 0.0, best_back=1.88, best_lay=1.90)
    session = _green_session(market)
    res = tow._dispatch(_green_flumine(market), session, _greenup_cmd(), "awtq11")
    assert res["ok"] is True
    assert market.placed == []          # posizione gia' piatta: MAI un place a vuoto


def test_greenup_open_position_without_price_fails_loudly():
    # esposizione APERTA ma book vuoto: un ok=True direbbe "chiuso" col rischio vivo
    market = _green_market(2.0, -2.0)
    session = _green_session(market)
    with pytest.raises(ValueError, match="NON eseguibile"):
        tow._dispatch(_green_flumine(market), session, _greenup_cmd(), "awtq12")
    assert market.placed == []


def test_greenup_without_capture_strategy_fails_loudly():
    # senza strategy le esposizioni sarebbero (0,0): "piatta" FALSO → fail loud
    market = _green_market(2.0, -2.0, best_back=1.88, best_lay=1.90)
    session = types.SimpleNamespace(market_meta={}, capture={}, tracked_orders={})
    with pytest.raises(ValueError, match="capture-strategy"):
        tow._dispatch(_green_flumine(market), session, _greenup_cmd(), "awtq13")


def test_greenup_rejects_cancel_unmatched_with_target_price():
    market = _green_market(2.0, -2.0, best_back=1.88, best_lay=1.90)
    session = _green_session(market)
    with pytest.raises(ValueError, match="non è compatibile"):
        tow._dispatch(_green_flumine(market), session,
                      _greenup_cmd(params={"cancel_unmatched": True,
                                           "target_price": 2.0}), "awtq14")


# ---------------------------------------------------------------------------
# #8 — positions_worker: righe orfane AZZERATE una volta dopo il restart
# ---------------------------------------------------------------------------
class _PosBlotter:
    def __init__(self):
        self.orders = []

    def strategy_orders(self, strategy):  # noqa: ARG002
        return self.orders

    def get_exposures(self, strategy, lookup):  # noqa: ARG002
        return {"matched_profit_if_win": 1.5, "matched_profit_if_lose": -2.0}

    def selection_exposure(self, strategy, lookup):  # noqa: ARG002
        return 2.0

    def strategy_selection_orders(self, strategy, sel, hcap, matched_only=True):  # noqa: ARG002
        return []


def _pos_setup():
    blotter = _PosBlotter()
    market = types.SimpleNamespace(market_id="1.1", blotter=blotter)
    fl = types.SimpleNamespace(markets=types.SimpleNamespace(markets={"1.1": market}))
    session = types.SimpleNamespace(
        market_meta={"ev1": {"market_id": "1.1"}},
        capture={"ev1": object()},
        hosted={},
        order_mode="PAPER",
    )
    return blotter, fl, session


def test_positions_worker_zeroes_stale_rows(monkeypatch):
    rows = []
    monkeypatch.setattr(tow.tennis_db, "upsert_tennis_position",
                        lambda row: rows.append(dict(row)))
    blotter, fl, session = _pos_setup()
    blotter.orders = [types.SimpleNamespace(selection_id=5, handicap=0.0)]

    tow.positions_worker({}, fl, session)
    assert len(rows) == 1 and rows[0]["selection_id"] == 5
    assert rows[0]["matched_if_win"] == pytest.approx(1.5)

    # restart del framework: blotter NUOVO e VUOTO. ANTI-FALSO-FLAT (review 16/07):
    # il PRIMO giro di assenza NON azzera (potrebbe essere una lettura transitoria
    # fallita); il SECONDO giro consecutivo sì, UNA volta.
    blotter.orders = []
    tow.positions_worker({}, fl, session)
    assert len(rows) == 1                       # primo miss: nessun azzeramento
    tow.positions_worker({}, fl, session)
    assert len(rows) == 2                       # secondo miss consecutivo: azzerata
    zero = rows[1]
    assert zero["market_id"] == "1.1" and zero["selection_id"] == 5
    assert zero["mode"] == "paper" and zero["event_id"] == "ev1"
    for f in ("matched_if_win", "matched_if_lose", "selection_exposure",
              "net_position", "worst_if_win", "worst_if_lose"):
        assert zero[f] == 0.0

    # giro successivo: la chiave e' uscita dal registro → NESSUN re-azzeramento
    tow.positions_worker({}, fl, session)
    assert len(rows) == 2


def test_positions_worker_transient_miss_does_not_zero(monkeypatch):
    """ANTI-FALSO-FLAT (review 16/07): una lettura del blotter fallita per UN solo
    ciclo (market sparito transitoriamente) non deve azzerare la posizione — al
    ritorno del blotter la riga viene ri-scritta con l'esposizione VERA."""
    rows = []
    monkeypatch.setattr(tow.tennis_db, "upsert_tennis_position",
                        lambda row: rows.append(dict(row)))
    blotter, fl, session = _pos_setup()
    blotter.orders = [types.SimpleNamespace(selection_id=5, handicap=0.0)]

    tow.positions_worker({}, fl, session)
    assert len(rows) == 1

    # transitorio: il market sparisce per UN ciclo (lettura best-effort fallita)
    saved = fl.markets.markets.pop("1.1")
    tow.positions_worker({}, fl, session)
    assert len(rows) == 1                       # NESSUN azzeramento al primo miss

    # il market torna: la riga viene ri-scritta con l'esposizione reale (mai flat bugiardo)
    fl.markets.markets["1.1"] = saved
    tow.positions_worker({}, fl, session)
    assert len(rows) == 2
    assert rows[1]["matched_if_win"] == pytest.approx(1.5)


def test_positions_worker_uses_build_mode_not_env(monkeypatch):
    """#14: la mode dello specchio e' quella catturata al BUILD (session.order_mode),
    mai una ri-lettura dell'env a meta' processo (righe 'live' per ordini paper)."""
    rows = []
    monkeypatch.setattr(tow.tennis_db, "upsert_tennis_position",
                        lambda row: rows.append(dict(row)))
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")   # env DIVERGENTE
    blotter, fl, session = _pos_setup()                    # order_mode="PAPER"
    blotter.orders = [types.SimpleNamespace(selection_id=5, handicap=0.0)]

    tow.positions_worker({}, fl, session)
    assert rows and rows[0]["mode"] == "paper"             # mode di build, non env


# ---------------------------------------------------------------------------
# #8 — ordini tracciati di un framework SMONTATO: chiusi/scartati, mai fantasmi
# ---------------------------------------------------------------------------
def _tracked_order(status="EXECUTABLE"):
    return types.SimpleNamespace(
        status=types.SimpleNamespace(name=status), bet_id="b1", trade=None,
        size_matched=0.0, average_price_matched=None, size_remaining=2.0,
        size_cancelled=0.0, size_lapsed=0.0, size_voided=0.0,
        market_id="1.1", selection_id=5, side="BACK",
        order_type=types.SimpleNamespace(price=1.9, size=2.0),
    )


def test_reconcile_voids_stale_paper_order_once(monkeypatch):
    mirrored = []
    monkeypatch.setattr(tow.tennis_db, "upsert_tennis_order",
                        lambda row: mirrored.append(dict(row)))
    session = types.SimpleNamespace(
        framework_gen=1, order_sig_cache={}, hosted={}, market_meta={},
        tracked_orders={"awtq1": {"order": _tracked_order(), "trade": None,
                                  "mode": "paper", "event_id": "ev1",
                                  "source": "manual", "gen": 0}},
    )
    tow._reconcile_tracked(session, flumine=None)
    # specchio chiuso con stato TERMINALE (mai EXECUTABLE fantasma) + tracking rimosso
    assert len(mirrored) == 1
    assert mirrored[0]["status"] == "VOIDED"
    assert session.tracked_orders == {}


def test_reconcile_live_stale_order_dropped_without_falsifying(monkeypatch):
    """In LIVE l'ordine reale puo' vivere sull'Exchange: MAI marcarlo morto nello
    specchio — si smette solo di seguirlo (warning esplicito nei log)."""
    mirrored = []
    monkeypatch.setattr(tow.tennis_db, "upsert_tennis_order",
                        lambda row: mirrored.append(dict(row)))
    session = types.SimpleNamespace(
        framework_gen=2, order_sig_cache={}, hosted={}, market_meta={},
        tracked_orders={"awtq2": {"order": _tracked_order(), "trade": None,
                                  "mode": "live", "event_id": "ev1",
                                  "source": "manual", "gen": 1}},
    )
    tow._reconcile_tracked(session, flumine=None)
    assert mirrored == []                       # niente stato falsificato
    assert session.tracked_orders == {}         # ma il fantasma non resta tracciato


# ---------------------------------------------------------------------------
# Fix 17/07 — pulizia bot ORFANI all'avvio (mai 'running' fantasma per giorni)
# ---------------------------------------------------------------------------
def test_cleanup_orfani_marca_solo_heartbeat_stantii(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from Betfair.stream.tennis_live import tennis_runner as tr

    now = datetime.now(timezone.utc)
    rows = [
        # hb 20 ore fa: ORFANO (il caso "partita di ieri ancora running")
        {"event_id": "E_OLD", "bot_key": "tennis_swing", "status": "running",
         "heartbeat_at": (now - timedelta(hours=20)).isoformat(),
         "requested_at": (now - timedelta(hours=21)).isoformat()},
        # hb 3 secondi fa: VIVO, mai toccato
        {"event_id": "E_LIVE", "bot_key": "tennis_pro", "status": "running",
         "heartbeat_at": (now - timedelta(seconds=3)).isoformat(),
         "requested_at": (now - timedelta(minutes=5)).isoformat()},
        # appena richiesto (nessun heartbeat, requested_at fresco): mai toccato
        {"event_id": "E_NEW", "bot_key": "tennis_flb", "status": "requested",
         "heartbeat_at": None,
         "requested_at": (now - timedelta(seconds=10)).isoformat()},
    ]
    monkeypatch.setattr(tr.tennis_db, "list_tennis_bot_controls",
                        lambda statuses: rows)
    marked = []
    monkeypatch.setattr(
        tr.tennis_db, "set_tennis_bot_status",
        lambda ev, bk, st, stopped=False, error=None, **k:
        marked.append((ev, bk, st, error)))

    n = tr._cleanup_orphan_bot_controls()

    assert n == 1
    assert len(marked) == 1
    ev, bk, st, err = marked[0]
    assert (ev, bk, st) == ("E_OLD", "tennis_swing", "error")
    assert "orfana" in err
