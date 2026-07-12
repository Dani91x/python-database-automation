"""Test del ciclo di Omega con fake market/db (end-to-end senza rete).

Verifica gli invarianti chiave: un solo lay per match (I1), finestra d'ingresso,
selezione+sizing, settlement e P&L (§2/§4/§6).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as M
from Betfair.omega import omega_service as S

NOW = datetime(2026, 7, 12, 15, 42, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
def _event(eid="1.100", minutes_ago=42):
    return M.EventInfo(eid, "Home vs Away", NOW - timedelta(minutes=minutes_ago))


def _cs(eid="1.100", minutes_ago=42):
    return M.CorrectScoreMarket(
        market_id=f"m-{eid}", event_id=eid, event_name="Home vs Away",
        market_start_time=NOW - timedelta(minutes=minutes_ago),
        runner_names={1: "0 - 0", 2: "1 - 0", 3: "2 - 1", 4: "3 - 2"},
    )


def _open_snapshot():
    return M.MarketSnapshot(
        status="OPEN", inplay=True, closed=False, winner_selection_id=None, voided=False,
        runners=[
            E.ScoreRunner(1, "0 - 0", lay_price=6.0, lay_size=100, lay_ladder=((6.0, 100.0),)),
            E.ScoreRunner(3, "2 - 1", lay_price=75.0, lay_size=50, lay_ladder=((75.0, 50.0),)),
            E.ScoreRunner(4, "3 - 2", lay_price=110.0, lay_size=40, lay_ladder=((110.0, 40.0),)),
        ],
    )


def _closed_snapshot(winner_id):
    return M.MarketSnapshot(
        status="CLOSED", inplay=False, closed=True,
        winner_selection_id=winner_id, voided=(winner_id is None),
        runners=[E.ScoreRunner(winner_id or 1, "x", lay_price=None)],
    )


class FakeMarket:
    def __init__(self, events, cs, snapshot):
        self._events = events
        self._cs = cs
        self._snapshot = snapshot
        self.placed = []

    def list_today_football_events(self):
        return self._events

    def get_correct_score_market(self, ev):
        # mercato DISTINTO per evento (come nella realtà)
        return M.CorrectScoreMarket(
            market_id=f"m-{ev.event_id}", event_id=ev.event_id, event_name="Home vs Away",
            market_start_time=ev.open_date,
            runner_names={1: "0 - 0", 2: "1 - 0", 3: "2 - 1", 4: "3 - 2"},
        )

    def read_market(self, cs):
        return self._snapshot

    def place_lay_live(self, **kw):
        self.placed.append(kw)
        return M.PlaceResult(ok=True, order_status="EXECUTION_COMPLETE",
                             bet_id="b1", size_matched=kw["size"],
                             avg_price_matched=kw["price"])

    # --- manuale ---
    def list_event_markets(self, event_id, max_results=30):
        return [{"market_id": f"m-{event_id}", "market_name": "Correct Score",
                 "market_type": "CORRECT_SCORE", "total_matched": 1000,
                 "runner_names": {3: "2 - 1", 4: "3 - 2"}}]

    def read_book(self, market_id, runner_names):
        return {"market_id": market_id, "status": "OPEN", "inplay": True, "event_name": "Home vs Away",
                "runners": [
                    {"selection_id": 3, "name": "2 - 1", "status": "ACTIVE",
                     "lay_price": 75.0, "lay_size": 50, "back_price": 74.0, "back_size": 40,
                     "lay_ladder": [[75.0, 50.0]]},
                    {"selection_id": 4, "name": "3 - 2", "status": "ACTIVE",
                     "lay_price": 110.0, "lay_size": 40, "back_price": 108.0, "back_size": 30,
                     "lay_ladder": [[110.0, 40.0]]},
                ]}

    def place_order_live(self, **kw):
        self.placed.append(kw)
        return M.PlaceResult(ok=True, order_status="EXECUTION_COMPLETE",
                             bet_id="bm1", size_matched=kw["size"], avg_price_matched=kw["price"])

    # --- riconciliazione ---
    def list_current_orders(self, strategy_ref="omega"):
        if getattr(self, "orders_raise", False):
            raise RuntimeError("betfair down")
        return getattr(self, "current_orders", [])

    def list_cleared_orders(self, strategy_ref="omega", market_ids=None, lookback_hours=72):
        if getattr(self, "orders_raise", False):
            raise RuntimeError("betfair down")
        return getattr(self, "cleared_orders", [])


class FakeDB:
    def __init__(self, control):
        self.control = control
        self.trades = []
        self.activity = []
        self._id = 0

    def read_control(self):
        return self.control

    def set_control(self, **fields):
        self.control.update(fields)

    def log(self, kind, payload=None):
        self.activity.append((kind, payload or {}))

    def insert_trade(self, trade):
        origin = trade.get("origin", "auto")
        # partial unique su (event_id) WHERE origin='auto' → I1 automatico
        if origin == "auto" and any(
            t["event_id"] == trade["event_id"] and t.get("origin", "auto") == "auto"
            for t in self.trades
        ):
            raise Exception("unique auto event_id")
        # unique per-gamba (event_id,market_id,selection_id,side) → doppione esatto
        leg = (trade["event_id"], trade.get("market_id"), trade.get("selection_id"), trade.get("side"))
        if any(
            (t["event_id"], t.get("market_id"), t.get("selection_id"), t.get("side")) == leg
            for t in self.trades
        ):
            raise Exception("unique leg")
        self._id += 1
        row = dict(trade)
        row["id"] = self._id
        self.trades.append(row)
        return self._id

    def update_trade(self, trade_id, **fields):
        for t in self.trades:
            if t["id"] == trade_id:
                t.update(fields)

    def delete_trade(self, trade_id):
        # guard status='pending' come il DB reale
        self.trades = [t for t in self.trades
                       if not (t["id"] == trade_id and t.get("status") == "pending")]

    def list_trades(self, status=None):
        return [t for t in self.trades if status is None or t["status"] == status]

    def open_trades(self):
        return self.list_trades("open")

    # --- coda manuale (per i test del ciclo) ---
    def __init_manual(self):
        pass

    def pending_manual_requests(self):
        return getattr(self, "manual_reqs", [])

    def set_manual_status(self, req_id, status, result=None):
        for r in getattr(self, "manual_reqs", []):
            if r["id"] == req_id:
                r["status"] = status
                if result is not None:
                    r["result"] = result

    def upsert_events(self, events):
        self.events_cache = events

    def update_event_markets(self, event_id, markets):
        pass

    def upsert_market_snapshot(self, snapshot):
        self.snapshot = snapshot

    def get_event(self, event_id):
        return None

    def traded_event_ids(self):
        return {t["event_id"] for t in self.trades}

    def aggregates(self):
        return E.aggregate_trades(self.trades)  # stessa logica pura del backend reale


def _control(status="running", mode="paper", goal=250, params=None):
    return {"id": 1, "status": status, "mode": mode, "daily_goal": goal, "params": params or {}}


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
def test_piazza_un_lay_su_match_in_finestra():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1
    assert len(db.trades) == 1
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["runner_name"] == "3 - 2"        # quota più alta nel range [20,120]
    assert t["price"] == 110.0
    assert t["size"] > 0 and t["liability"] > 0
    assert t["minute_at_entry"] == 42


def test_idempotenza_un_solo_trade_per_match():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    S.run_once(market=market, db=db, now=NOW)  # secondo ciclo
    assert len(db.trades) == 1  # I1 rispettato


def test_fuori_finestra_non_piazza():
    db = FakeDB(_control())
    market = FakeMarket([_event(minutes_ago=10)], _cs(minutes_ago=10), _open_snapshot())  # minuto 10 < 30
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 0
    assert len(db.trades) == 0


def test_non_inplay_non_piazza():
    db = FakeDB(_control())
    snap = M.MarketSnapshot(status="OPEN", inplay=False, closed=False,
                            winner_selection_id=None, voided=False, runners=_open_snapshot().runners)
    market = FakeMarket([_event()], _cs(), snap)
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 0


def test_nessun_runner_nel_range_salta():
    db = FakeDB(_control(params={"price_min": 200, "price_max": 300}))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 0
    assert any(k == "skip" for k, _ in db.activity)


def test_settlement_won_quando_risultato_non_esce():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    # ora il mercato chiude con vincitore = "0 - 0" (id 1), NON il nostro "3 - 2" (id 4)
    market._snapshot = _closed_snapshot(winner_id=1)
    res = S.run_once(market=market, db=db, now=NOW + timedelta(hours=2))
    assert res["settled"] == 1
    t = db.trades[0]
    assert t["status"] == "won"
    assert t["pnl"] > 0


def test_settlement_lost_quando_risultato_esce():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    liability = t["liability"]
    # il mercato chiude con vincitore = il NOSTRO "3 - 2" (id 4)
    market._snapshot = _closed_snapshot(winner_id=4)
    S.run_once(market=market, db=db, now=NOW + timedelta(hours=2))
    assert db.trades[0]["status"] == "lost"
    assert db.trades[0]["pnl"] == pytest.approx(-liability, abs=0.01)


def test_settlement_void():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    market._snapshot = _closed_snapshot(winner_id=None)  # abbandonata
    S.run_once(market=market, db=db, now=NOW + timedelta(hours=2))
    assert db.trades[0]["status"] == "void"
    assert db.trades[0]["pnl"] == 0


def test_stop_transizione():
    db = FakeDB(_control(status="stopping"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res.get("stopped")
    assert db.control["status"] == "stopped"


def test_settlement_continua_anche_a_bot_fermo():
    # piazza (running), poi FERMA il bot: i trade aperti devono comunque regolarsi
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.trades[0]["status"] == "open"
    db.control["status"] = "stopped"          # bot fermato
    market._snapshot = _closed_snapshot(winner_id=1)  # match finito, non il nostro
    res = S.run_once(market=market, db=db, now=NOW + timedelta(hours=2))
    assert res.get("settled") == 1
    assert db.trades[0]["status"] == "won"     # regolato nonostante il bot fermo


def test_idle_non_fa_nulla():
    db = FakeDB(_control(status="idle"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res.get("idle")
    assert len(db.trades) == 0


def test_modalita_live_chiama_place_lay_live():
    db = FakeDB(_control(mode="live"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1
    assert len(market.placed) == 1
    assert db.trades[0]["mode"] == "live"
    assert db.trades[0]["bet_id"] == "b1"


def test_stats_aggiornate_nel_control():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    stats = db.control.get("stats")
    assert stats is not None
    assert stats["events_total"] == 1
    assert stats["matches_traded"] == 1
    assert stats["target_match"] > 0
    assert "goal_pct" in stats


def test_daily_loss_cap_ferma_nuovi_ingressi():
    # perdita realizzata −20 con cap 10 → niente nuovi lay (§9 fix HIGH)
    db = FakeDB(_control(params={"daily_loss_cap": 10}))
    db.trades.append({
        "id": 99, "event_id": "past", "status": "lost", "pnl": -20, "liability": 500,
        "selection_id": 1, "price": 50, "size": 10, "commission": 0.05,
    })
    db._id = 99
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 0
    assert any(k == "loss_stop" for k, _ in db.activity)


def test_commissione_fissata_al_piazzamento():
    # piazza con comm 5%, poi l'utente cambia a 10%: il settlement usa il 5% del trade
    db = FakeDB(_control(params={"commission_pct": 5}))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["commission"] == 0.05
    size = t["size"]
    db.control["params"] = {"commission_pct": 10}  # cambio a caldo
    market._snapshot = _closed_snapshot(winner_id=1)  # non il nostro → won
    S.run_once(market=market, db=db, now=NOW + timedelta(hours=2))
    assert db.trades[0]["status"] == "won"
    # pnl con 5% (fissato), NON 10%
    assert db.trades[0]["pnl"] == pytest.approx(size * 0.95, abs=0.02)


def test_reserve_poi_conferma_open():
    # la riga passa da 'pending' (riservata) a 'open' (confermata) — reserve-first
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.trades[0]["status"] == "open"
    assert db.trades[0]["commission"] == 0.05


def test_estimate_minute_usa_live_now_se_fresco():
    # score_lookup ritorna un LiveScore fresco → estimate_minute usa quel minuto+punteggio
    snap = S.LiveScore(minute=70, score_home=1, score_away=1,
                       updated_at=(NOW - timedelta(seconds=10)).isoformat(), inplay=True)
    minute, score = S.estimate_minute(
        market_start=NOW - timedelta(minutes=42), now=NOW, event_id="1.100",
        source="score", score_lookup=lambda e: snap,
    )
    assert minute == 70           # dal feed live_now, NON dal clock (che darebbe 42)
    assert score == "1-1"


def test_estimate_minute_ignora_live_now_stantio():
    # dato vecchio (> SCORE_MAX_AGE_S) → cade sul clock
    snap = S.LiveScore(minute=70, score_home=1, score_away=1,
                       updated_at=(NOW - timedelta(seconds=600)).isoformat(), inplay=True)
    minute, score = S.estimate_minute(
        market_start=NOW - timedelta(minutes=42), now=NOW, event_id="1.100",
        source="score", score_lookup=lambda e: snap,
    )
    assert minute == 42           # clock (live_now scartato perché stantio)
    assert score is None


def test_estimate_minute_assente_usa_clock():
    minute, score = S.estimate_minute(
        market_start=NOW - timedelta(minutes=42), now=NOW, event_id="1.100",
        source="score", score_lookup=lambda e: None,
    )
    assert minute == 42
    assert score is None


def test_build_score_lookup_legge_live_now():
    # il lookup costruito legge da db.read_live_now (fake)
    class DBLive:
        def read_live_now(self, ev):
            return {"minute": 55, "score_home": 2, "score_away": 0,
                    "updated_at": NOW.isoformat(), "inplay": True}
    lookup = S._build_score_lookup(db=DBLive())
    snap = lookup("1.100")
    assert snap.minute == 55 and snap.score_home == 2 and snap.score_away == 0


def test_manuale_piazza_lay_da_richiesta():
    # richiesta manuale 'place' → reserve-first → trade open, origin=manual
    db = FakeDB(_control(status="idle"))  # anche a bot fermo il manuale funziona
    db.manual_reqs = [{
        "id": 1, "kind": "place", "status": "pending",
        "payload": {"event_id": "1.100", "market_id": "m-1.100", "selection_id": 4,
                    "runner_name": "3 - 2", "side": "lay", "mode": "paper", "target": 8},
    }]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["manual"] == 1
    assert db.manual_reqs[0]["status"] == "done"
    assert len(db.trades) == 1
    t = db.trades[0]
    assert t["origin"] == "manual"
    assert t["status"] == "open"
    assert t["side"] == "lay"
    assert t["selection_id"] == 4
    # size da target 8 con comm 5% ≈ 8.42
    assert t["size"] == pytest.approx(8.42, abs=0.05)


def test_manuale_live_chiama_place_order():
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = [{
        "id": 1, "kind": "place", "status": "pending",
        "payload": {"event_id": "1.100", "market_id": "m-1.100", "selection_id": 3,
                    "runner_name": "2 - 1", "side": "lay", "mode": "live", "size": 2},
    }]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(market.placed) == 1
    assert db.trades[0]["mode"] == "live"
    assert db.trades[0]["bet_id"] == "bm1"


def test_settlement_back_manuale():
    # back manuale: se il runner VINCE incassi, se perde −stake
    status_win, pnl_win = E.settle_pnl(our_selection_id=4, winner_selection_id=4,
                                       size=2, price=110, commission=0.05, side="back")
    assert status_win == "won"
    assert pnl_win == pytest.approx(2 * 109 * 0.95, abs=0.01)
    status_lose, pnl_lose = E.settle_pnl(our_selection_id=4, winner_selection_id=1,
                                         size=2, price=110, commission=0.05, side="back")
    assert status_lose == "lost"
    assert pnl_lose == -2


def _manual_req(payload):
    return [{"id": 1, "kind": "place", "status": "pending", "payload": payload}]


def test_manuale_lay_sizing_esatto_a_target():
    # LAY target €8, comm 5% → size = 8/0.95 = 8.42 (al centesimo)
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "paper",
                                  "price": 110, "target": 8})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["size"] == round(8 / 0.95, 2)                 # 8.42 esatto
    assert t["side"] == "lay" and t["price"] == 110
    # incasso netto se non esce ≈ target 8 (al centesimo)
    assert E.net_profit_if_win(t["size"], 0.05) == pytest.approx(8.0, abs=0.01)
    assert t["liability"] == E.liability_from_lay(t["size"], 110)


def test_manuale_back_sizing_esatto_a_target():
    # BACK target €20 a quota 21, comm 5% → size = 20/((21-1)*0.95) = 20/19 = 1.05
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 3, "side": "back", "mode": "paper",
                                  "price": 21, "target": 20})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    expected = round(20 / ((21 - 1) * 0.95), 2)            # 1.05
    assert t["size"] == expected
    assert t["side"] == "back"
    assert t["liability"] == round(t["size"], 2)           # BACK: rischio = stake
    # profit se il BACK vince ≈ target (entro l'arrotondamento al centesimo)
    _, pnl = E.settle_pnl(our_selection_id=3, winner_selection_id=3, size=t["size"],
                          price=21, commission=0.05, side="back")
    assert pnl == pytest.approx(20.0, abs=0.20)


def test_manuale_stake_rispettato_al_centesimo():
    for side, sid in (("lay", 4), ("back", 3)):
        db = FakeDB(_control(status="idle"))
        db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                      "selection_id": sid, "side": side, "mode": "paper",
                                      "price": 110 if side == "lay" else 21, "size": 2.37})
        market = FakeMarket([_event()], _cs(), _open_snapshot())
        S.run_once(market=market, db=db, now=NOW)
        assert db.trades[0]["size"] == 2.37               # STAKE esplicito ESATTO


def test_manuale_stake_sotto_minimo_rifiutato():
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "paper",
                                  "price": 110, "size": 0.30})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.trades) == 0                             # niente riserva sotto il minimo
    assert db.manual_reqs[0]["status"] == "error"


def test_manuale_ordine_su_market_e_selection_esatti_live():
    # LIVE: l'ordine deve andare ESATTAMENTE sul market_id/selection scelti
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "live",
                                  "price": 110, "size": 2})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(market.placed) == 1
    p = market.placed[0]
    assert p["market_id"] == "m-1.100"
    assert p["selection_id"] == 4
    assert p["side"] == "lay"
    assert p["size"] == 2 and p["price"] == 110
    assert db.trades[0]["market_id"] == "m-1.100" and db.trades[0]["selection_id"] == 4


def test_manuale_mode_non_valido_rifiutato_niente_live():
    # un mode sconosciuto NON deve MAI finire nel ramo LIVE (fail-safe)
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "REAL",
                                  "price": 110, "size": 2})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(market.placed) == 0                         # nessun ordine reale
    assert len(db.trades) == 0
    assert db.manual_reqs[0]["status"] == "error"


def test_manuale_commissione_clampata():
    # commission_pct=999 dal payload NON deve gonfiare la size (clamp a 20%)
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "paper",
                                  "price": 110, "target": 8, "commission_pct": 999})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    # con comm clampata a 20% → size = 8/0.8 = 10.0 (NON milioni)
    assert t["size"] == round(8 / 0.8, 2)


def _pending_row(mode="live", **over):
    row = {"id": 1, "event_id": "1.100", "market_id": "m1", "selection_id": 4,
           "side": "lay", "mode": mode, "price": 110, "size": 5, "liability": 545,
           "status": "pending", "placed_at": NOW.isoformat()}
    row.update(over)
    return row


def test_reconcile_paper_pending_confermato():
    db = FakeDB(_control())
    db.trades = [_pending_row(mode="paper")]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 1
    assert db.trades[0]["status"] == "open"      # paper: confermato senza Betfair


def test_reconcile_live_pending_trovato_su_betfair():
    db = FakeDB(_control())
    db.trades = [_pending_row(mode="live")]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.current_orders = [{"customer_order_ref": "omega-1.100", "market_id": "m1",
                              "selection_id": 4, "side": "lay", "size_matched": 5.0,
                              "avg_price_matched": 110.0, "bet_id": "bX"}]
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 1
    assert db.trades[0]["status"] == "open"       # ordine reale ritrovato → tracciato
    assert db.trades[0]["bet_id"] == "bX"


def test_reconcile_live_pending_non_trovato_liberato():
    db = FakeDB(_control())
    # oltre il grace period (5 min) ma entro le 24h → non piazzato → liberato
    db.trades = [_pending_row(mode="live", placed_at=(NOW - timedelta(minutes=5)).isoformat())]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.current_orders = []
    market.cleared_orders = []
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 1
    assert len(db.trades) == 0                     # mai piazzato → liberato


def test_reconcile_live_pending_troppo_fresco_keep():
    # appena piazzato (< grace) e non ancora visibile via API → NON liberare (attendi)
    db = FakeDB(_control())
    db.trades = [_pending_row(mode="live", placed_at=NOW.isoformat())]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.current_orders = []
    market.cleared_orders = []
    S.reconcile_pending(market=market, db=db, now=NOW)
    assert db.trades[0]["status"] == "pending"     # grace: mai free su ordine freschissimo


def test_reconcile_fetch_error_non_libera_ne_decide():
    # se Betfair è irraggiungibile, NESSUNA decisione sui live pending (no free/error)
    db = FakeDB(_control())
    db.trades = [_pending_row(mode="live")]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.orders_raise = True
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 0
    assert db.trades[0]["status"] == "pending"     # intatto, ritentato dopo


def test_reconcile_live_pending_vecchio_non_trovato_error():
    db = FakeDB(_control())
    old = (NOW - timedelta(hours=48)).isoformat()
    db.trades = [_pending_row(mode="live", placed_at=old)]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.current_orders = []
    market.cleared_orders = []
    S.reconcile_pending(market=market, db=db, now=NOW)
    assert db.trades[0]["status"] == "error"       # vecchio+non trovato → error (mai free)


def test_reconcile_live_pending_parziale_keep():
    # ordine reale ancora parzialmente in esecuzione (remaining>0) → resta pending
    db = FakeDB(_control())
    db.trades = [_pending_row(mode="live")]
    db._id = 1
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.current_orders = [{"customer_order_ref": "omega-1.100", "market_id": "m1",
                              "selection_id": 4, "side": "lay", "size_matched": 2.0,
                              "size_remaining": 3.0, "avg_price_matched": 110.0, "bet_id": "bP"}]
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 0
    assert db.trades[0]["status"] == "pending"     # non congelare un fill parziale


def test_reconcile_non_confonde_ordine_di_altro_trade():
    # un ordine con customerOrderRef DIVERSO non deve confermare questo pending
    other = [{"customer_order_ref": "omega-9.999", "market_id": "m1", "selection_id": 4,
              "side": "lay", "size_matched": 5.0, "size_remaining": 0.0, "bet_id": "bZ"}]
    d = E.reconcile_decision(_pending_row(mode="live"), other, [], NOW.isoformat())
    assert d["action"] != "confirm"                # mai 'confirm' con l'ordine sbagliato


def test_due_eventi_stesso_ciclo_piazzano_entrambi():
    # regressione del bug 'contatore cumulativo': 2 eventi in finestra → 2 trade distinti
    events = [_event("1.100", 42), _event("1.200", 42)]
    db = FakeDB(_control())
    market = FakeMarket(events, _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 2
    assert len(db.trades) == 2
    assert {t["market_id"] for t in db.trades} == {"m-1.100", "m-1.200"}
    assert all(t["status"] == "open" for t in db.trades)


def test_auto_poi_manuale_stesso_evento_altro_mercato_consentito():
    # I1 auto NON deve bloccare un manuale legittimo sullo stesso evento (altro mercato)
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)          # auto piazza su 1.100 / m-1.100 / sel 4
    assert len(db.trades) == 1 and db.trades[0]["origin"] == "auto"
    db.control["status"] = "idle"                       # spengo l'auto
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-altro",
                                  "selection_id": 3, "side": "lay", "mode": "paper", "size": 2})
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.trades) == 2                          # manuale CONSENTITO
    assert db.trades[1]["origin"] == "manual"
    assert db.manual_reqs[0]["status"] == "done"


def test_manuale_cap_sotto_minimo_rifiutato():
    # cap liability/match troppo basso → size sotto il minimo → rifiutato (niente riga)
    db = FakeDB(_control(status="idle", params={"max_liability_per_match": 1}))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "paper",
                                  "price": 110, "target": 8})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.trades) == 0
    assert db.manual_reqs[0]["status"] == "error"


def test_target_dinamico_scala_con_piu_eventi():
    # 50 eventi, solo 1 in finestra → target del piazzato ~ 250/50 = 5
    events = [_event("1.100", 42)] + [_event(f"1.{200+i}", -30) for i in range(49)]
    db = FakeDB(_control())
    market = FakeMarket(events, _cs("1.100"), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.trades) == 1
    assert db.trades[0]["target"] == pytest.approx(5.0, abs=0.2)
