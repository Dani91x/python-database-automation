"""Test del ciclo del BOT Safe Strategy (bot_service) con fake db/market/engine.

Nessuna rete, nessun Supabase. File ASCII-only (console Windows cp1252).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as M
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X

NOW = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeDB:
    """Specchio in memoria di safe_strategy_* (stesse regole del DB reale)."""

    def __init__(self, status="running", mode="paper", params=None):
        self.control = {"id": 1, "status": status, "mode": mode,
                        "params": params or {}}
        self.trades: list[dict] = []
        self.activity: list[tuple] = []
        self.requests: list[dict] = []
        self.opportunities: list[dict] = []
        self.scan_rows: list[dict] = []
        self.queue: list[dict] = []
        self.follow = "NONE"          # gate flumine chiuso -> percorso legacy
        self.heartbeat = {"ts": NOW.isoformat(), "mode": "PAPER"}
        self._id = 0

    # --- control/log ---
    def read_control(self):
        return self.control

    def set_control(self, **fields):
        self.control.update(fields)

    def log(self, kind, payload=None):
        self.activity.append((kind, payload or {}))

    def kinds(self):
        return [k for k, _ in self.activity]

    # --- trades ---
    def insert_trade(self, trade):
        # unique PARZIALE (event_id, signal_key) WHERE origin='auto' AND status<>'error'
        if str(trade.get("origin") or "auto") == "auto" and trade.get("signal_key"):
            key = (str(trade["event_id"]), str(trade["signal_key"]))
            for t in self.trades:
                if t.get("status") == "error" or str(t.get("origin") or "auto") != "auto":
                    continue
                if (str(t.get("event_id")), str(t.get("signal_key"))) == key:
                    raise Exception("unique signal_key")
        self._id += 1
        row = dict(trade)
        row["id"] = self._id
        row.setdefault("placed_at", NOW.isoformat())
        self.trades.append(row)
        return self._id

    def update_trade(self, trade_id, **fields):
        for t in self.trades:
            if t["id"] == trade_id:
                t.update(fields)

    def delete_trade(self, trade_id):
        self.trades = [t for t in self.trades
                       if not (t["id"] == trade_id and t.get("status") == "pending")]

    def get_trade(self, trade_id):
        return next((t for t in self.trades if t["id"] == int(trade_id)), None)

    def list_trades(self, status=None):
        return [t for t in self.trades if status is None or t.get("status") == status]

    def open_trades(self):
        return [t for t in self.trades if t.get("status") in ("open", "hedged")]

    def closing_trades_for(self, ids):
        ids = {int(i) for i in ids}
        return [t for t in self.trades if t.get("closes_trade_id") in ids]

    def traded_signal_keys(self):
        return {(str(t.get("event_id")), str(t.get("signal_key")))
                for t in self.trades
                if t.get("signal_key") and t.get("status") != "error"
                and str(t.get("origin") or "auto") == "auto"}

    def aggregates(self):
        from Betfair.safe_strategy import bot_db

        return bot_db.aggregate_rows(self.trades)

    # --- richieste ---
    def pending_requests(self, limit=50):
        return [r for r in self.requests if r.get("status") == "pending"]

    def set_request_status(self, req_id, status, result=None):
        for r in self.requests:
            if r["id"] == req_id:
                r["status"] = status
                if result is not None:
                    r["result"] = result

    def fail_stale_processing(self, max_age_min=10):
        return None

    # --- feed / opportunita' ---
    def fetch_scan_rows(self):
        return self.scan_rows

    def upsert_opportunities(self, rows):
        self.opportunities.append(rows)

    # --- coda flumine (contratto del gate) ---
    def live_follow_status(self, event_id):
        return self.follow

    def runner_heartbeat(self):
        return self.heartbeat

    def enqueue_live_order(self, payload):
        self.queue.append(payload)
        return len(self.queue)

    def get_live_order_request(self, rid):
        return {"id": rid, "status": "pending"}

    def get_live_order_request_by_ref(self, ref):
        return None

    def get_live_order_mirror(self, ref, mode="paper"):
        return None

    def revoke_live_order_request(self, rid):
        return True


class FakeMarket:
    def __init__(self):
        self.placed: list[dict] = []
        self.snapshot = None
        self.book = None

    def place_order_live(self, **kw):
        self.placed.append(kw)
        return M.PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="b-1",
                             size_matched=kw["size"], avg_price_matched=kw["price"])

    def read_market(self, cs):
        return self.snapshot

    def read_book(self, market_id, runner_names):
        return self.book


class FakeEngine:
    """Stessa forma di SafeEngine: params + evaluate(rows) -> [Signal]."""

    def __init__(self, signals=None, raises=False):
        self.signals = list(signals or [])
        self.raises = raises
        self.seen_rows = None
        self.params = {}

    def update_params(self, params):
        self.params = dict(params)

    def evaluate(self, rows):
        if self.raises:
            raise RuntimeError("motore rotto")
        self.seen_rows = list(rows)
        return list(self.signals)


def _signal(key="k1", event_id="1.1", variant="base", side="back", price=3.0,
            size=10.0, size_available=100.0, market_type="MATCH_ODDS",
            selection_id=7, sport="calcio"):
    return SimpleNamespace(
        key=key, event_id=event_id, sport=sport, variant=variant,
        event_name="Home v Away", market_type=market_type, market_id="m1",
        selection_id=selection_id, selection_name="Home", side=side, price=price,
        size_available=size_available, size=size, headline="test", minute=55,
        score="1-0", first_seen_ts=1.0, checks=(),
    )


def _run(db, market=None, engine=None, **kw):
    # il gate spread all'ingresso legge back/lay REALI dal feed: senza riga
    # dell'evento nessun segnale passerebbe -> feed di default (sel 7, 3.0/3.1)
    if engine is not None and not db.scan_rows:
        db.scan_rows = [_feed_row()]
    return S.run_once(db=db, market=market or FakeMarket(), engine=engine,
                      now=NOW, **kw)


# ---------------------------------------------------------------------------
# Parametri
# ---------------------------------------------------------------------------
def test_resolve_params_default_e_clamp():
    p = S.resolve_params(None)
    assert p["poll_interval_s"] == 2
    assert p["auto_trade_opportunities"] is False
    assert p["variants"] == ["base", "esatto", "punta", "tennis"]
    clamped = S.resolve_params({"poll_interval_s": 0, "commission_pct": 99,
                                "max_liability_per_trade": -5})
    assert clamped["poll_interval_s"] == 1.0
    assert clamped["commission_pct"] == 20.0
    assert clamped["max_liability_per_trade"] == 0.0


def test_resolve_params_non_schiaccia_le_sezioni_del_motore():
    from Betfair.safe_strategy import engine as eng

    p = S.resolve_params({"base": {"minuteMin": 51}}, engine_mod=eng)
    assert p["base"]["minuteMin"] == 51
    # le altre chiavi della sezione restano quelle di default (deep-merge)
    assert len(p["base"]) == len(eng.DEFAULT_PARAMS["base"])


# ---------------------------------------------------------------------------
# (d) segnali -> piazzamento
# ---------------------------------------------------------------------------
def test_running_piazza_il_segnale_con_reserve_first():
    db = FakeDB()
    eng = FakeEngine([_signal()])
    res = _run(db, engine=eng)
    assert res["placed"] == 1 and res["signals"] == 1
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["origin"] == "auto" and t["signal_key"] == "k1"
    assert t["strategy"] == "base" and t["mode"] == "paper"
    assert t["liability"] == 10.0, "BACK: il rischio e' lo stake"
    assert "place" in db.kinds()


def test_lo_stesso_segnale_non_viene_mai_ripiazzato():
    db = FakeDB()
    eng = FakeEngine([_signal()])
    _run(db, engine=eng)
    res = _run(db, engine=eng)
    assert res["placed"] == 0
    assert len([t for t in db.trades if not t.get("closes_trade_id")]) == 1


def test_bot_fermo_non_piazza_nulla():
    db = FakeDB(status="stopped")
    eng = FakeEngine([_signal()])
    res = _run(db, engine=eng)
    assert res["placed"] == 0 and db.trades == []


def test_stopping_passa_a_stopped():
    db = FakeDB(status="stopping")
    res = _run(db, engine=FakeEngine([_signal()]))
    assert db.control["status"] == "stopped"
    assert res["placed"] == 0
    assert "stop" in db.kinds()


def test_paper_fill_cappato_alla_liquidita_disponibile():
    db = FakeDB()
    eng = FakeEngine([_signal(size=10.0, size_available=4.0)])
    # con factor 0 il gate di liquidita' non blocca: il fill viene CAPPATO
    db.control["params"] = {"min_size_available_factor": 0}
    res = _run(db, engine=eng)
    assert res["placed"] == 1
    assert db.trades[0]["size"] == 4.0


def test_segnale_scartato_se_la_liquidita_e_sotto_il_fattore_minimo():
    db = FakeDB()
    eng = FakeEngine([_signal(size=10.0, size_available=4.0)])
    res = _run(db, engine=eng)
    assert res["placed"] == 0
    reasons = [p.get("reason") for k, p in db.activity if k == "skip"]
    assert "liquidita_insufficiente" in reasons


def test_variante_non_abilitata_viene_saltata():
    db = FakeDB(params={"variants": ["esatto"]})
    res = _run(db, engine=FakeEngine([_signal(variant="base")]))
    assert res["placed"] == 0 and db.trades == []


def test_cap_di_liability_per_trade():
    db = FakeDB(params={"max_liability_per_trade": 5})
    res = _run(db, engine=FakeEngine([_signal(side="lay", price=6.0, size=10.0)]))
    assert res["placed"] == 0
    reasons = [p.get("reason") for k, p in db.activity if k == "skip"]
    assert "max_liability_per_trade" in reasons


def test_max_open_trades_ferma_il_ciclo():
    db = FakeDB(params={"max_open_trades": 1})
    eng = FakeEngine([_signal(key="k1"), _signal(key="k2")])
    res = _run(db, engine=eng)
    assert res["placed"] == 1
    reasons = [p.get("reason") for k, p in db.activity if k == "skip"]
    assert "max_open_trades" in reasons


def test_motore_rotto_non_uccide_il_ciclo():
    db = FakeDB()
    res = _run(db, engine=FakeEngine(raises=True))
    assert res["placed"] == 0
    assert "error" in db.kinds()


def test_senza_motore_il_ciclo_gira_lo_stesso():
    db = FakeDB()
    res = _run(db, engine=None)
    assert res["placed"] == 0
    assert db.control["heartbeat_at"] == NOW.isoformat()


def test_il_motore_riceve_le_righe_del_feed():
    db = FakeDB()
    db.scan_rows = [{"event_id": "1.1", "sport": "calcio", "payload": {},
                     "updated_at": NOW.isoformat()}]
    eng = FakeEngine()
    _run(db, engine=eng)
    assert eng.seen_rows == db.scan_rows


def test_mode_live_del_control_arriva_al_trade():
    db = FakeDB(mode="live")
    mk = FakeMarket()
    res = _run(db, market=mk, engine=FakeEngine([_signal()]))
    assert res["placed"] == 1
    assert db.trades[0]["mode"] == "live"
    assert mk.placed[0]["side"] == "back", "LIVE: passa dal REST quando il gate e' chiuso"


# ---------------------------------------------------------------------------
# (c) richieste della UI
# ---------------------------------------------------------------------------
def _place_payload(**kw):
    base = {"event_id": "1.1", "market_id": "m1", "market_type": "MATCH_ODDS",
            "selection_id": 7, "side": "back", "price": 3.0, "size": 5.0}
    base.update(kw)
    return base


def _feed_row(event_id="1.1", back=3.0, lay=3.1, sid=7):
    return {"event_id": event_id, "sport": "calcio", "updated_at": NOW.isoformat(),
            "payload": {"event_name": "Home v Away", "inplay": True, "minute": 55,
                        "score_home": 1, "score_away": 0,
                        "odds": {"home": {"selection_id": sid, "back": back,
                                          "lay": lay, "back_size": 500.0,
                                          "lay_size": 500.0}}}}


def test_richiesta_place_manuale_eseguita_anche_a_bot_fermo():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    db.requests.append({"id": 1, "kind": "place", "status": "pending",
                        "payload": _place_payload()})
    res = _run(db)
    assert res["requests"] == 1
    assert db.requests[0]["status"] == "done"
    t = db.trades[0]
    assert t["origin"] == "manual" and t["strategy"] == "manual"
    assert t["status"] == "open" and t["mode"] == "paper"


def test_richiesta_place_senza_mode_esplicito_resta_paper():
    db = FakeDB(status="running", mode="live")
    db.scan_rows = [_feed_row()]
    db.requests.append({"id": 1, "kind": "place", "status": "pending",
                        "payload": _place_payload()})
    _run(db)
    assert db.trades[0]["mode"] == "paper", "il LIVE deve essere sempre esplicito"


def test_richiesta_place_invalida_va_in_errore():
    db = FakeDB()
    db.requests.append({"id": 1, "kind": "place", "status": "pending",
                        "payload": _place_payload(side="sopra")})
    _run(db)
    assert db.requests[0]["status"] == "error"
    assert db.requests[0]["result"]["error"].startswith("side_non_valido")


def test_kind_sconosciuto_va_in_errore():
    db = FakeDB()
    db.requests.append({"id": 1, "kind": "place", "status": "pending", "payload": {}})
    _run(db)
    assert db.requests[0]["status"] == "error"


def test_richiesta_cashout_chiude_la_gamba():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(back=2.5, lay=2.6)]
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1",
                           "market_type": "MATCH_ODDS", "selection_id": 7,
                           "side": "back", "size": 10.0, "price": 3.0,
                           "status": "open", "mode": "paper", "commission": 0.05,
                           "origin": "manual"})
    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": tid}})
    _run(db)
    assert db.requests[0]["status"] == "done", db.requests[0].get("result")
    closing = db.get_trade(db.requests[0]["result"]["closing_trade_id"])
    assert closing["side"] == "lay" and closing["closes_trade_id"] == tid
    assert db.get_trade(tid)["status"] == "hedged"


def test_richiesta_cashout_su_trade_inesistente():
    db = FakeDB()
    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": 999}})
    _run(db)
    assert db.requests[0]["result"]["error"] == "trade_inesistente"


def test_richiesta_cancel_libera_solo_una_riserva_senza_ordine():
    db = FakeDB()
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back",
                           "meta": {}})
    db.requests.append({"id": 1, "kind": "cancel", "status": "pending",
                        "payload": {"trade_id": tid}})
    _run(db)
    assert db.requests[0]["status"] == "done"
    assert db.get_trade(tid) is None


def test_richiesta_cancel_non_tocca_un_ordine_gia_a_mercato():
    db = FakeDB()
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back",
                           "meta": {"flumine_client_ref": "safe-t1"}})
    db.requests.append({"id": 1, "kind": "cancel", "status": "pending",
                        "payload": {"trade_id": tid}})
    _run(db)
    assert db.requests[0]["result"]["error"] == "ordine_gia_a_mercato"
    assert db.get_trade(tid) is not None


# ---------------------------------------------------------------------------
# (b) settlement
# ---------------------------------------------------------------------------
def _closed(winner_id, sid=7):
    return M.MarketSnapshot(
        status="CLOSED", inplay=False, closed=True, winner_selection_id=winner_id,
        voided=(winner_id is None),
        runners=[E.ScoreRunner(sid, "Home", lay_price=None)],
    )


def test_settlement_trade_semplice():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(7)
    db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                     "side": "back", "size": 10.0, "price": 3.0, "status": "open",
                     "commission": 0.05, "mode": "paper"})
    res = _run(db, market=mk)
    assert res["settled"] == 1
    assert db.trades[0]["status"] == "won"
    assert db.trades[0]["pnl"] == pytest.approx(19.0, abs=0.01)


def test_settlement_della_coppia_hedged_netta_la_commissione():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(999)  # la nostra selezione PERDE
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0,
                           "status": "hedged", "commission": 0.05, "mode": "paper",
                           "meta": {"locked_pnl": 9.0}})
    cid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "back", "size": 1.0, "price": 6.0,
                           "status": "open", "commission": 0.05, "mode": "paper",
                           "closes_trade_id": tid})
    res = _run(db, market=mk)
    assert res["settled"] == 1
    assert round(db.get_trade(tid)["pnl"] + db.get_trade(cid)["pnl"], 2) == 8.55
    assert db.get_trade(cid)["settled_at"] == NOW.isoformat()


def test_settlement_aspetta_una_chiusura_ancora_pending():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(999)
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0,
                           "status": "hedged", "commission": 0.05, "mode": "paper"})
    # fill flumine ancora in arrivo (marker): NON e' un pending da riconciliare
    db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                     "side": "back", "size": 1.0, "price": 6.0, "status": "pending",
                     "closes_trade_id": tid, "mode": "paper",
                     "meta": {"flumine_client_ref": "safe-t2", "flumine_request_id": 1}})
    res = _run(db, market=mk)
    assert res["settled"] == 0
    assert db.get_trade(tid)["status"] == "hedged"
    assert "settle_wait" in db.kinds()


def test_mercato_non_chiuso_non_regola_nulla():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = M.MarketSnapshot(status="OPEN", inplay=True, runners=[],
                                   closed=False, winner_selection_id=None,
                                   voided=False)
    db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                     "side": "back", "size": 10.0, "price": 3.0, "status": "open",
                     "commission": 0.05, "mode": "paper"})
    assert _run(db, market=mk)["settled"] == 0


# ---------------------------------------------------------------------------
# (e) opportunita'
# ---------------------------------------------------------------------------
class FakeModel:
    def __init__(self, opps=None):
        self.opps = list(opps or [])
        self.calls = 0

    def evaluate(self, payload, *, sport, lambdas, league_id, now_ts, **kw):
        self.calls += 1
        self.last = {"lambdas": lambdas, "league_id": league_id, **kw}
        return list(self.opps)


FAKE_OPP_MOD = SimpleNamespace(
    resolve_lambdas=lambda payload, *, fixture: (1.3, 1.1, 135, "prematch"))


def _opp(**kw):
    base = {"market_type": "OVER_UNDER_25", "market_name": "Over/Under 2.5",
            "line": 2.5, "market_id": "m2", "selection_id": 47972,
            "selection_name": "Over 2.5", "side": "back", "price": 2.2,
            "size_available": 300.0, "p_model": 0.55, "p_implied": 0.45,
            "edge": 0.10, "ev": 0.2, "confidence": 0.8, "rationale": "test"}
    base.update(kw)
    return base


def test_opportunita_scritte_solo_quando_cambiano():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    model = FakeModel([_opp()])
    state = {"last_ts": 0.0, "hashes": {}}
    r1 = _run(db, engine=None, opp_model=model, opp_mod=FAKE_OPP_MOD,
              opps_state=state)
    assert r1["opportunities"]["written"] == 1
    assert db.opportunities[0][0]["event_id"] == "1.1"
    state["last_ts"] = 0.0  # forza un secondo giro (throttle a parte)
    r2 = _run(db, engine=None, opp_model=model, opp_mod=FAKE_OPP_MOD,
              opps_state=state)
    assert r2["opportunities"]["written"] == 0, "write-on-change: payload identico"
    assert len(db.opportunities) == 1


def test_opportunita_throttlate():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    model = FakeModel([_opp()])
    state = {"last_ts": NOW.timestamp() - 1.0, "hashes": {}}
    res = _run(db, engine=None, opp_model=model, opp_mod=FAKE_OPP_MOD,
               opps_state=state)
    assert res["opportunities"] == {"events": 0, "written": 0, "traded": 0}
    assert model.calls == 0


def test_opportunita_non_tradate_per_default():
    db = FakeDB(status="running")
    db.scan_rows = [_feed_row()]
    res = _run(db, engine=None, opp_model=FakeModel([_opp()]), opp_mod=FAKE_OPP_MOD,
               opps_state={"last_ts": 0.0, "hashes": {}})
    assert res["opportunities"]["traded"] == 0
    assert db.trades == []


def test_opportunita_tradate_se_abilitate_e_oltre_le_soglie():
    db = FakeDB(status="running", params={"auto_trade_opportunities": True,
                                          "opps_stake": 4})
    db.scan_rows = [_feed_row()]
    res = _run(db, engine=None, opp_model=FakeModel([_opp()]), opp_mod=FAKE_OPP_MOD,
               opps_state={"last_ts": 0.0, "hashes": {}})
    assert res["opportunities"]["traded"] == 1
    t = db.trades[0]
    assert t["strategy"] == "model" and t["size"] == 4
    assert t["signal_key"] == "model:OVER_UNDER_25:47972:back"


def test_opportunita_sotto_soglia_non_tradate():
    db = FakeDB(status="running", params={"auto_trade_opportunities": True,
                                          "opps_stake": 4,
                                          "opps_min_confidence": 0.9})
    db.scan_rows = [_feed_row()]
    res = _run(db, engine=None, opp_model=FakeModel([_opp(confidence=0.5)]),
               opp_mod=FAKE_OPP_MOD, opps_state={"last_ts": 0.0, "hashes": {}})
    assert res["opportunities"]["traded"] == 0


def test_opportunita_a_bot_fermo_non_vengono_mai_tradate():
    db = FakeDB(status="stopped", params={"auto_trade_opportunities": True,
                                          "opps_stake": 4})
    db.scan_rows = [_feed_row()]
    res = _run(db, engine=None, opp_model=FakeModel([_opp()]), opp_mod=FAKE_OPP_MOD,
               opps_state={"last_ts": 0.0, "hashes": {}})
    assert res["opportunities"]["traded"] == 0


# ---------------------------------------------------------------------------
# prezzi dal feed + stats
# ---------------------------------------------------------------------------
def test_prezzi_match_odds_dal_feed():
    p = S.prices_from_row(_feed_row(), market_type="MATCH_ODDS", selection_id=7)
    assert p["back"] == 3.0 and p["lay"] == 3.1 and p["back_size"] == 500.0
    assert S.prices_from_row(_feed_row(), market_type="MATCH_ODDS",
                             selection_id=999) is None


def test_prezzi_correct_score_dal_feed():
    row = {"event_id": "1.1", "sport": "calcio", "payload": {
        "cs": {"market_id": "m9", "selections": [
            {"selection_id": 12, "name": "2 - 1", "back": 70.0, "lay": 75.0,
             "back_size": 10.0, "lay_size": 12.0}]}}}
    p = S.prices_from_row(row, market_type="CORRECT_SCORE", selection_id=12)
    assert p["lay"] == 75.0 and p["lay_size"] == 12.0


def test_prezzi_fallback_rest_quando_il_feed_non_ha_l_evento():
    mk = FakeMarket()
    mk.book = {"market_id": "m1", "status": "OPEN", "runners": [
        {"selection_id": 7, "back_price": 2.0, "back_size": 9.0,
         "lay_price": 2.1, "lay_size": 8.0, "lay_ladder": [[2.1, 8.0]]}]}
    p = S.prices_for(market=mk, rows_by_event={}, event_id="1.9", market_id="m1",
                     market_type="MATCH_ODDS", selection_id=7)
    assert p["back"] == 2.0 and p["lay_size"] == 8.0


def test_stats_e_heartbeat_sempre_aggiornati():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(), _feed_row("1.2")]
    db.insert_trade({"event_id": "1.1", "status": "open", "liability": 25.0,
                     "pnl": 0.0, "side": "back", "market_id": "m1",
                     "selection_id": 7, "size": 5.0, "price": 6.0,
                     "commission": 0.05, "mode": "paper"})
    res = _run(db)
    stats = res["stats"]
    assert stats["events_total"] == 2
    assert stats["trades_open"] == 1
    assert stats["open_liability"] == 25.0
    assert db.control["stats"] == stats
    assert db.control["heartbeat_at"] == NOW.isoformat()


def test_senza_control_il_ciclo_esce_pulito():
    class NoControl(FakeDB):
        def read_control(self):
            return None

    assert _run(NoControl()) == {"skipped": "no_control"}


def test_liability_lay_e_back():
    assert X.liability_of("lay", 10.0, 6.0) == 50.0
    assert X.liability_of("back", 10.0, 6.0) == 10.0


# ---------------------------------------------------------------------------
# CRITICAL-1: esito ignoto del place LIVE -> pending, MAI ripiazzato
# ---------------------------------------------------------------------------
class BoomMarket(FakeMarket):
    def place_order_live(self, **kw):
        self.placed.append(kw)
        raise RuntimeError("timeout betfair dopo l'accettazione")


class ReconMarket(FakeMarket):
    """FakeMarket + API ordini per la riconciliazione LIVE."""

    def __init__(self, current=None, cleared=None, by_bet=None):
        super().__init__()
        self.current = list(current or [])
        self.cleared = list(cleared or [])
        self.by_bet = dict(by_bet or {})

    def list_current_orders(self):
        return list(self.current)

    def list_cleared_orders(self):
        return list(self.cleared)

    def order_state_by_bet_id(self, bet_id):
        return self.by_bet.get(str(bet_id), {"found": False})


def _order(ref, sid=7, matched=10.0, remaining=0.0, price=3.0, bet_id="b-7"):
    return {"bet_id": bet_id, "market_id": "m1", "selection_id": sid, "side": "back",
            "size_matched": matched, "size_remaining": remaining,
            "avg_price_matched": price, "customer_order_ref": ref}


def test_live_eccezione_del_place_resta_pending_e_non_viene_ripiazzato():
    db = FakeDB(mode="live")
    mk = BoomMarket()
    eng = FakeEngine([_signal()])
    r1 = _run(db, market=mk, engine=eng)
    assert r1["placed"] == 1 and len(mk.placed) == 1
    t = db.trades[0]
    assert t["status"] == "pending"
    assert t["meta"]["reason"] == "place_exception_reconciling"
    assert "place_pending" in db.kinds() and "place_exception" in db.kinds()
    # cicli successivi: lo stesso segnale NON si ripiazza (resta in traded_signal_keys)
    _run(db, market=mk, engine=eng)
    _run(db, market=mk, engine=eng)
    assert len(db.trades) == 1 and len(mk.placed) == 1
    # e la riserva conta come esposizione (l'ordine puo' esistere)
    assert db.aggregates()["open_count"] == 1


# ---------------------------------------------------------------------------
# HIGH-3: reconcile_pending (port di Omega su bot_db)
# ---------------------------------------------------------------------------
def _pending_live(db, **kw):
    row = {"event_id": "1.1", "market_id": "m1", "selection_id": 7, "side": "back",
           "size": 10.0, "price": 3.0, "status": "pending", "mode": "live",
           "commission": 0.05, "origin": "auto", "signal_key": "k1",
           "meta": {"phase": "reserved", "reason": "place_exception_reconciling"}}
    row.update(kw)
    return db.insert_trade(row)


def test_reconcile_live_conferma_dal_fill_reale_su_betfair():
    db = FakeDB(status="stopped")
    tid = _pending_live(db)
    mk = ReconMarket(current=[_order(f"safe-t{tid}", matched=8.0, price=3.1)])
    res = _run(db, market=mk)
    assert res["reconciled"] == 1
    t = db.get_trade(tid)
    assert t["status"] == "open" and t["bet_id"] == "b-7"
    assert t["size"] == 8.0 and t["price"] == 3.1
    assert t["liability"] == 8.0 and t["meta"]["reconciled"] == "live"
    assert "reason" not in t["meta"]
    assert "reconciled_open" in db.kinds()


def test_reconcile_live_non_confonde_l_ordine_di_un_altro_trade():
    db = FakeDB(status="stopped")
    tid = _pending_live(db)
    mk = ReconMarket(current=[_order("safe-t999")])  # ref di un altro trade
    res = _run(db, market=mk)
    assert res["reconciled"] == 0
    assert db.get_trade(tid)["status"] == "pending", "fresco e non trovato: keep"


def test_reconcile_live_libera_la_riserva_mai_piazzata_dopo_il_grace():
    from datetime import timedelta

    db = FakeDB(status="stopped")
    tid = _pending_live(db, placed_at=(NOW - timedelta(minutes=10)).isoformat())
    mk = ReconMarket()
    res = _run(db, market=mk)
    assert res["reconciled"] == 1
    assert db.get_trade(tid) is None and "reconciled_free" in db.kinds()


def test_reconcile_live_con_bet_id_usa_lo_stato_per_betid():
    db = FakeDB(status="stopped")
    tid = _pending_live(db, bet_id="b-55")
    mk = ReconMarket(by_bet={"b-55": {"found": True, "size_matched": 10.0,
                                      "size_remaining": 0.0, "avg_price_matched": 3.05}})
    _run(db, market=mk)
    t = db.get_trade(tid)
    assert t["status"] == "open" and t["price"] == 3.05 and t["bet_id"] == "b-55"


def test_reconcile_senza_api_ordini_non_decide_mai():
    db = FakeDB(status="stopped")
    tid = _pending_live(db)
    res = _run(db, market=FakeMarket())  # nessuna list_current_orders
    assert res["reconciled"] == 0
    assert db.get_trade(tid)["status"] == "pending"
    assert "reconcile_error" in db.kinds()


def test_reconcile_non_tocca_i_pending_della_coda_flumine():
    db = FakeDB(status="stopped")
    tid = _pending_live(db, meta={"flumine_client_ref": "safe-t1", "flumine_request_id": 1})
    mk = ReconMarket(current=[_order(f"safe-t{tid}")])
    _run(db, market=mk)
    assert db.get_trade(tid)["status"] == "pending", "proprieta' del poll flumine"


def test_reconcile_paper_conferma_con_i_dati_della_riserva():
    db = FakeDB(status="stopped")
    tid = _pending_live(db, mode="paper")
    res = _run(db)
    assert res["reconciled"] == 1
    t = db.get_trade(tid)
    assert t["status"] == "open" and t["size"] == 10.0 and t["meta"]["reconciled"] == "paper"


def test_reconcile_della_chiusura_riallinea_l_apertura():
    """La chiusura riconciliata come fillata porta l'apertura a 'hedged'."""
    db = FakeDB(status="stopped")
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0, "status": "open",
                           "mode": "live", "commission": 0.05,
                           "meta": {"hedge_pending_ids": [2], "closing_trade_id": 2}})
    cid = _pending_live(db, side="back", size=12.0, price=5.0, closes_trade_id=tid,
                        origin="manual", signal_key=None)
    mk = ReconMarket(current=[_order(f"safe-t{cid}", matched=12.0, price=5.0)])
    _run(db, market=mk)
    assert db.get_trade(cid)["status"] == "open"
    apri = db.get_trade(tid)
    assert apri["status"] == "hedged" and apri["meta"]["hedge_pending_ids"] == []


# ---------------------------------------------------------------------------
# CRITICAL-2 via richieste UI + HIGH-6 sync del fill flumine
# ---------------------------------------------------------------------------
def _open_lay(db, **kw):
    row = {"event_id": "1.1", "market_id": "m1", "market_type": "MATCH_ODDS",
           "selection_id": 7, "side": "lay", "size": 10.0, "price": 6.0,
           "status": "open", "mode": "paper", "commission": 0.05, "origin": "manual"}
    row.update(kw)
    return db.insert_trade(row)


def test_richiesta_cashout_rifiutata_mentre_una_chiusura_e_in_sospeso():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(back=5.0, lay=5.2)]
    tid = _open_lay(db)
    db.insert_trade({"event_id": "1.1", "side": "back", "size": 12.0, "price": 5.0,
                     "status": "pending", "closes_trade_id": tid, "mode": "paper",
                     "meta": {"flumine_client_ref": "safe-t2", "flumine_request_id": 1}})
    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": tid}})
    _run(db)
    assert db.requests[0]["status"] == "error"
    assert db.requests[0]["result"]["error"] == "chiusura_in_corso"
    assert len([t for t in db.trades if t.get("closes_trade_id") == tid]) == 1


def test_sync_porta_a_hedged_quando_il_poll_conferma_la_chiusura():
    db = FakeDB(status="stopped")
    tid = _open_lay(db, meta={"hedge_pending_ids": [2], "closing_trade_id": 2})
    cid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "back", "size": 12.0, "price": 5.0,
                           "status": "pending", "closes_trade_id": tid, "mode": "paper",
                           "meta": {"flumine_client_ref": "safe-t2", "flumine_request_id": 1}})
    mk = FakeMarket()
    mk.snapshot = M.MarketSnapshot(status="OPEN", inplay=True, runners=[], closed=False,
                                   winner_selection_id=None, voided=False)
    _run(db, market=mk)
    assert db.get_trade(tid)["status"] == "open"
    db.update_trade(cid, status="open", price=5.0, size=12.0)  # il poll conferma
    _run(db, market=mk)
    apri = db.get_trade(tid)
    assert apri["status"] == "hedged"
    assert apri["meta"]["hedged_size"] == pytest.approx(10.0, abs=0.01)
    assert apri["meta"]["closing_ids"] == [cid]


def test_richiesta_cashout_parziale_lascia_l_apertura_open():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(back=5.0, lay=5.2)]
    tid = _open_lay(db)
    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": tid, "fraction": 0.5}})
    _run(db)
    assert db.requests[0]["status"] == "done", db.requests[0].get("result")
    apri = db.get_trade(tid)
    assert apri["status"] == "open"
    assert apri["meta"]["residual_size"] == pytest.approx(5.0, abs=0.01)


# ---------------------------------------------------------------------------
# HIGH-4 / HIGH-5: settlement in coppia, orfani, ripresa
# ---------------------------------------------------------------------------
def test_settlement_apertura_open_con_chiusura_confermata_in_coppia():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(999)
    tid = _open_lay(db)  # ancora 'open' (hedge parziale)
    cid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "back", "size": 4.0, "price": 5.0, "status": "open",
                           "commission": 0.05, "mode": "paper", "closes_trade_id": tid})
    res = _run(db, market=mk)
    assert res["settled"] == 1
    a, c = db.get_trade(tid), db.get_trade(cid)
    assert a["status"] == "won" and c["status"] == "lost"
    assert round(a["pnl"] + c["pnl"], 2) == pytest.approx(5.70, abs=0.01)


def test_settlement_gamba_orfana_con_apertura_gia_regolata():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = None
    tid = _open_lay(db, status="won", pnl=9.5, settled_at=NOW.isoformat())
    cid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "back", "size": 12.0, "price": 5.0, "status": "open",
                           "commission": 0.05, "mode": "paper", "closes_trade_id": tid})
    res = _run(db, market=mk)
    assert res["settled"] == 1
    c = db.get_trade(cid)
    # netting col padre già regolato (review HIGH-3): netto di mercato 10 − 12 = −2 → nessuna
    # commissione; la chiusura prende −2 − 9,5 = −11,5 (padre + chiusura = −2 esatto)
    assert c["status"] == "lost" and c["pnl"] == pytest.approx(-11.5, abs=0.01)
    assert "settle_orphan_closing" in db.kinds()


def test_settlement_ripresa_con_chiusura_gia_regolata():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(999)
    tid = _open_lay(db, status="hedged")
    cid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "back", "size": 1.0, "price": 6.0, "status": "lost",
                           "pnl": -1.0, "settled_at": "old", "commission": 0.05,
                           "mode": "paper", "closes_trade_id": tid})
    res = _run(db, market=mk)
    assert res["settled"] == 1
    assert db.get_trade(tid)["pnl"] == pytest.approx(9.55, abs=0.01)
    assert db.get_trade(cid)["settled_at"] == "old"
    ordine = [p["trade_id"] for k, p in db.activity if k == "settle"]
    assert ordine == [tid], "la chiusura gia' regolata non viene riscritta"


def test_settlement_chiusure_scritte_prima_dell_apertura():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(999)
    tid = _open_lay(db, status="hedged")
    cid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "back", "size": 12.0, "price": 5.0, "status": "open",
                           "commission": 0.05, "mode": "paper", "closes_trade_id": tid})
    _run(db, market=mk)
    ordine = [p["trade_id"] for k, p in db.activity if k == "settle"]
    assert ordine == [cid, tid]


# ---------------------------------------------------------------------------
# HIGH-8: mai piazzare senza market_id / selection_id
# ---------------------------------------------------------------------------
def test_segnale_senza_selection_id_non_viene_piazzato():
    db = FakeDB()
    res = _run(db, engine=FakeEngine([_signal(selection_id=None)]))
    assert res["placed"] == 0 and db.trades == []
    reasons = [p.get("reason") for k, p in db.activity if k == "skip"]
    assert "market_o_selezione_mancante" in reasons


def test_segnale_senza_market_id_non_viene_piazzato():
    s = _signal()
    s.market_id = None
    db = FakeDB()
    res = _run(db, engine=FakeEngine([s]))
    assert res["placed"] == 0 and db.trades == []


def test_opportunita_senza_market_id_non_viene_tradata():
    db = FakeDB(status="running", params={"auto_trade_opportunities": True,
                                          "opps_stake": 4})
    db.scan_rows = [_feed_row()]
    res = _run(db, engine=None, opp_model=FakeModel([_opp(market_id=None)]),
               opp_mod=FAKE_OPP_MOD, opps_state={"last_ts": 0.0, "hashes": {}})
    assert res["opportunities"]["traded"] == 0 and db.trades == []


# ---------------------------------------------------------------------------
# MEDIUM: prezzi dai blocchi ou/btts/ht_result + idempotency_key
# ---------------------------------------------------------------------------
def _feed_row_goal_markets():
    return {"event_id": "1.1", "sport": "calcio", "updated_at": NOW.isoformat(),
            "payload": {
                "event_name": "Home v Away", "inplay": True, "minute": 30,
                "ou": [{"market_id": "ou15", "line": 1.5, "selections": [
                            {"selection_id": 1221385, "name": "Over 1.5 Goals",
                             "back": 1.5, "lay": 1.52, "back_size": 50.0, "lay_size": 60.0}]},
                       {"market_id": "ou25", "line": 2.5, "selections": [
                            {"selection_id": 47972, "name": "Over 2.5 Goals",
                             "back": 2.2, "lay": 2.24, "back_size": 300.0, "lay_size": 200.0},
                            {"selection_id": 47973, "name": "Under 2.5 Goals",
                             "back": 1.8, "lay": 1.82, "back_size": 100.0, "lay_size": 90.0}]}],
                "btts": {"market_id": "btts1", "selections": [
                    {"selection_id": 30246, "name": "Yes", "back": 1.9, "lay": 1.95,
                     "back_size": 10.0, "lay_size": 11.0}]},
                "ht_result": {"market_id": "ht1", "selections": [
                    {"selection_id": 7, "name": "Home", "back": 2.5, "lay": 2.6,
                     "back_size": 5.0, "lay_size": 6.0}]},
            }}


def test_prezzi_over_under_btts_ht_result_dal_feed():
    row = _feed_row_goal_markets()
    p = S.prices_from_row(row, market_type="OVER_UNDER", selection_id=47972)
    assert p["back"] == 2.2 and p["lay_size"] == 200.0
    p = S.prices_from_row(row, market_type="OVER_UNDER_25", selection_id=47973,
                          market_id="ou25")
    assert p["lay"] == 1.82
    p = S.prices_from_row(row, market_type="BOTH_TEAMS_TO_SCORE", selection_id=30246)
    assert p["back"] == 1.9 and p["back_size"] == 10.0
    p = S.prices_from_row(row, market_type="HALF_TIME", selection_id=7)
    assert p["lay"] == 2.6
    # market_id noto: si legge dal blocco giusto anche con market_type generico
    p = S.prices_from_row(row, market_type="", selection_id=7, market_id="ht1")
    assert p["back"] == 2.5
    assert S.prices_from_row(row, market_type="OVER_UNDER", selection_id=47972,
                             market_id="ou15") is None


def test_cashout_di_un_trade_di_modello_legge_i_prezzi_dal_feed():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row_goal_markets()]
    tid = db.insert_trade({"event_id": "1.1", "market_id": "ou25",
                           "market_type": "OVER_UNDER", "selection_id": 47972,
                           "side": "back", "size": 10.0, "price": 2.0,
                           "status": "open", "mode": "paper", "commission": 0.05,
                           "origin": "auto", "strategy": "model"})
    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": tid}})
    mk = FakeMarket()  # book None: senza feed il cash-out fallirebbe
    _run(db, market=mk)
    assert db.requests[0]["status"] == "done", db.requests[0].get("result")
    closing = db.get_trade(db.requests[0]["result"]["closing_trade_id"])
    assert closing["side"] == "lay" and closing["price"] == 2.24


def test_place_manuale_con_idempotency_key_non_si_ripete():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    for i in (1, 2):
        db.requests.append({"id": i, "kind": "place", "status": "pending",
                            "payload": _place_payload(idempotency_key="ui-abc")})
    _run(db)
    assert len(db.trades) == 1
    assert db.trades[0]["meta"]["idempotency_key"] == "ui-abc"
    assert db.requests[1]["status"] == "done"
    assert db.requests[1]["result"]["deduplicated"] is True
    assert db.requests[1]["result"]["trade_id"] == db.trades[0]["id"]


def test_aggregate_esclude_le_gambe_di_chiusura_dall_esposizione():
    """Le righe di CHIUSURA (closes_trade_id) non contano in trades_open /
    open_liability (stessa regola di get_safe_state e omega_engine.aggregate_trades):
    il rischio vivo e' gia' contato dall'originale 'hedged'. Il loro pnl entra
    nel realizzato solo quando regolate."""
    from Betfair.safe_strategy import bot_db

    rows = [
        {"id": 1, "status": "hedged", "liability": 10.0},
        {"id": 2, "status": "open", "liability": 5.0, "closes_trade_id": 1},
        {"id": 3, "status": "pending", "liability": 3.0, "closes_trade_id": 1,
         "meta": {"flumine_client_ref": "x"}},
        {"id": 4, "status": "won", "pnl": 2.0, "closes_trade_id": 1,
         "settled_at": NOW.isoformat()},
        {"id": 5, "status": "open", "liability": 4.0},
    ]
    agg = bot_db.aggregate_rows(rows)
    assert agg["open_count"] == 2
    assert agg["open_liability"] == 14.0
    assert agg["realized_total"] == 2.0


def test_aggregate_conta_il_pending_in_riconciliazione():
    from Betfair.safe_strategy import bot_db

    agg = bot_db.aggregate_rows([{"status": "pending", "liability": 8.0,
                                  "meta": {"reason": "place_exception_reconciling"}},
                                 {"status": "pending", "liability": 8.0, "meta": {}}])
    assert agg["open_count"] == 1 and agg["open_liability"] == 8.0


# ---------------------------------------------------------------------------
# (e-bis) catena dei lambda pre-match (Omega -> fixture per nomi -> pre-KO -> default)
# ---------------------------------------------------------------------------
from datetime import timedelta  # noqa: E402

from Betfair.safe_strategy import opportunity as O  # noqa: E402


class LambdaDB(FakeDB):
    """FakeDB con la catena dati di Omega: omega_events + fixture_predictions."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.events: dict[str, dict] = {}
        self.fixtures: list[dict] = []
        self.analyses: dict[int, dict] = {}
        self.window_calls = 0

    def get_event(self, event_id):
        return self.events.get(str(event_id))

    def fixtures_for_window(self, start_iso, end_iso):
        self.window_calls += 1
        return list(self.fixtures)

    def fixture_analysis(self, fixture_id):
        return self.analyses.get(int(fixture_id))


def _inplay_row(event_id="1.1", home="SK Slavia Praha U19", away="AC Sparta Praha U19",
                pre_ko=None, open_date=None):
    row = _feed_row(event_id=event_id)
    row["payload"].update({
        "event_name": f"{home} v {away}", "home": home, "away": away,
        "open_date": (open_date or (NOW - timedelta(hours=1))).isoformat(),
        "pre_ko": pre_ko,
    })
    return row


class OmegaStub:
    """Finto omega_service: conta le chiamate a _prematch_lambdas."""

    def __init__(self, result=None, raises=False):
        self.result, self.raises, self.calls = result, raises, 0

    def _prematch_lambdas(self, db, event_id, payload):
        self.calls += 1
        if self.raises:
            raise RuntimeError("omega rotto")
        return self.result


def _run_opps(db, model, state, monkeypatch, omega):
    monkeypatch.setattr(S, "_omega_service", lambda: omega)
    state["last_ts"] = 0.0
    return _run(db, engine=None, opp_model=model, opp_mod=O, opps_state=state)


def _written(db):
    return db.opportunities[-1][0]["payload"]


def test_lambda_catena_omega_ha_la_precedenza(monkeypatch):
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row(pre_ko={"home": 2.0, "draw": 3.4, "away": 4.0})]
    db.fixtures = [{"fixture_id": 501, "home_team_name": "Slavia Praha U19",
                    "away_team_name": "Sparta Praha U19",
                    "fixture_date": (NOW - timedelta(hours=1)).isoformat(), "league_id": 667}]
    model = FakeModel([_opp()])
    state = {"last_ts": 0.0, "hashes": {}}
    _run_opps(db, model, state, monkeypatch, OmegaStub((1.7, 0.9, 135, "fixture")))
    assert model.last["lambdas"] == (1.7, 0.9) and model.last["league_id"] == 135
    assert model.last["lambda_source"] == "fixture"
    body = _written(db)
    assert body["source"] == "fixture" and body["lambdas"] == [1.7, 0.9]
    assert body["league_id"] == 135
    assert db.window_calls == 0, "Omega ha risposto: nessuna lettura fixture"


def test_lambda_fixture_abbinata_per_nomi_fuzzy(monkeypatch):
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row()]  # niente pre_ko: partita gia' in-play all'avvio
    db.fixtures = [
        {"fixture_id": 400, "home_team_name": "Bohemians 1905", "away_team_name": "Slovan Liberec",
         "fixture_date": (NOW - timedelta(hours=1)).isoformat(), "league_id": 345},
        {"fixture_id": 501, "home_team_name": "Slavia Praha U19", "away_team_name": "Sparta Praha U19",
         "fixture_date": (NOW - timedelta(hours=1)).isoformat(), "league_id": 667},
    ]
    db.analyses[501] = {"inputs": {"lambda_home": 1.6, "lambda_away": 1.2, "league_id": 667,
                                   "ht_ratio_home": 0.4, "ht_ratio_away": 0.45}}
    model = FakeModel([_opp()])
    state = {"last_ts": 0.0, "hashes": {}}
    _run_opps(db, model, state, monkeypatch, OmegaStub(None))
    assert model.last["lambdas"] == (1.6, 1.2) and model.last["league_id"] == 667
    assert model.last["lambda_source"] == "fixture_match"
    assert model.last["ht_ratio"] == (0.4, 0.45)
    body = _written(db)
    assert body["source"] == "fixture_match" and body["league_id"] == 667


def test_lambda_fixture_fuori_finestra_oraria_non_viene_abbinata(monkeypatch):
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row(pre_ko={"home": 2.0, "draw": 3.4, "away": 4.0})]
    db.fixtures = [{"fixture_id": 501, "home_team_name": "Slavia Praha U19",
                    "away_team_name": "Sparta Praha U19",
                    "fixture_date": (NOW + timedelta(hours=9)).isoformat(), "league_id": 667}]
    db.analyses[501] = {"inputs": {"lambda_home": 1.6, "lambda_away": 1.2}}
    model = FakeModel([_opp()])
    _run_opps(db, model, {"last_ts": 0.0, "hashes": {}}, monkeypatch, OmegaStub(None))
    assert model.last["lambda_source"] == "pre_ko"
    assert _written(db)["source"] == "pre_ko"


def test_lambda_default_quando_tutta_la_catena_fallisce(monkeypatch):
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row()]
    model = FakeModel([_opp()])
    _run_opps(db, model, {"last_ts": 0.0, "hashes": {}}, monkeypatch, OmegaStub(raises=True))
    assert model.last["lambdas"] == S.DEFAULT_LAMBDAS
    assert model.last["lambda_source"] == "default"
    body = _written(db)
    assert body["source"] == "default" and body["lambdas"] == list(S.DEFAULT_LAMBDAS)
    assert body["league_id"] is None


def test_lambda_cache_per_evento_e_retry_dei_default(monkeypatch):
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row()]
    omega = OmegaStub((1.7, 0.9, 135, "fixture"))
    state = {"last_ts": 0.0, "hashes": {}}
    model = FakeModel([_opp()])
    _run_opps(db, model, state, monkeypatch, omega)
    _run_opps(db, model, state, monkeypatch, omega)
    assert omega.calls == 1, "lambda risolti una volta per partita"

    # i 'default' invece si riprovano dopo l'intervallo di retry
    db2 = LambdaDB(status="stopped")
    db2.scan_rows = [_inplay_row()]
    omega2 = OmegaStub(None)
    state2 = {"last_ts": 0.0, "hashes": {}}
    _run_opps(db2, model, state2, monkeypatch, omega2)
    _run_opps(db2, model, state2, monkeypatch, omega2)
    assert omega2.calls == 1 and state2["lambdas"]["1.1"]["source"] == "default"
    state2["lambdas"]["1.1"]["ts"] -= S.DEFAULT_LAMBDA_RETRY_S + 1
    omega2.result = (1.5, 1.0, 99, "pre_ko_odds")
    _run_opps(db2, model, state2, monkeypatch, omega2)
    assert omega2.calls == 2 and model.last["lambda_source"] == "pre_ko_odds"


def test_lambda_cache_dimentica_gli_eventi_usciti_dal_feed(monkeypatch):
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row(event_id="1.1"), _inplay_row(event_id="1.2")]
    state = {"last_ts": 0.0, "hashes": {}}
    model = FakeModel([_opp()])
    _run_opps(db, model, state, monkeypatch, OmegaStub((1.7, 0.9, 135, "fixture")))
    assert set(state["lambdas"]) == {"1.1", "1.2"}
    db.scan_rows = [_inplay_row(event_id="1.2")]
    _run_opps(db, model, state, monkeypatch, OmegaStub((1.7, 0.9, 135, "fixture")))
    assert set(state["lambdas"]) == {"1.2"}


def test_matcher_difflib_di_riserva():
    fixtures = [
        {"fixture_id": 400, "home_team_name": "Bohemians 1905", "away_team_name": "Slovan Liberec"},
        {"fixture_id": 501, "home_team_name": "Slavia Praha U19", "away_team_name": "Sparta Praha U19"},
    ]
    fx = S._fuzzy_fixture("SK Slavia Praha U19", "AC Sparta Praha U19", fixtures)
    assert fx and fx["fixture_id"] == 501
    # invertito casa/trasferta: accettato lo stesso (stesso incontro)
    fx = S._fuzzy_fixture("Sparta Praha U19", "Slavia Praha U19", fixtures)
    assert fx and fx["fixture_id"] == 501
    assert S._fuzzy_fixture("Viktoria Plzen", "Banik Ostrava", fixtures) is None


# ---------------------------------------------------------------------------
# (c-bis) USCITE automatiche (exits.py + process_exits)
# ---------------------------------------------------------------------------
from Betfair.safe_strategy import exits as XE  # noqa: E402


def _exit_feed_row(minute=60, sh=1, sa=0, red_home=0, red_away=0, mo_status="OPEN",
                   updated_at=None, event_id="1.1"):
    """Feed calcio per le uscite: casa = sel 7 (favorita), ospite = sel 8."""
    return {"event_id": event_id, "sport": "calcio",
            "updated_at": (updated_at or NOW).isoformat(),
            "payload": {"event_name": "Home v Away", "inplay": True, "minute": minute,
                        "score_home": sh, "score_away": sa,
                        "red_home": red_home, "red_away": red_away,
                        "mo_market_id": "m1", "mo_status": mo_status,
                        "odds": {"home": {"selection_id": 7, "back": 1.5, "lay": 1.52,
                                          "back_size": 500.0, "lay_size": 500.0},
                                 "draw": {"selection_id": 9, "back": 4.0, "lay": 4.2,
                                          "back_size": 500.0, "lay_size": 500.0},
                                 "away": {"selection_id": 8, "back": 9.0, "lay": 9.5,
                                          "back_size": 500.0, "lay_size": 500.0}},
                        "cs": {"market_id": "cs1", "status": "OPEN",
                               "any_other_home": {"selection_id": 501, "back": 20.0,
                                                  "lay": 22.0, "back_size": 50.0,
                                                  "lay_size": 50.0},
                               "selections": [
                                   {"selection_id": 501, "name": "Any Other Home Win",
                                    "back": 20.0, "lay": 22.0, "back_size": 50.0,
                                    "lay_size": 50.0}]}}}


def _tennis_feed_row(sets=(1, 0), games=(4, 2), updated_at=None, event_id="2.1"):
    return {"event_id": event_id, "sport": "tennis",
            "updated_at": (updated_at or NOW).isoformat(),
            "payload": {"event_name": "P1 v P2", "inplay": True, "mo_market_id": "mt",
                        "mo_status": "OPEN",
                        "sets": {"p1": sets[0], "p2": sets[1]},
                        "games": {"p1": games[0], "p2": games[1]},
                        "odds": {"p1": {"selection_id": 11, "back": 1.3, "lay": 1.32,
                                        "back_size": 500.0, "lay_size": 500.0},
                                 "p2": {"selection_id": 12, "back": 4.0, "lay": 4.4,
                                        "back_size": 500.0, "lay_size": 500.0}}}}


def _auto_trade(db, strategy="base", **kw):
    # lay 10@8.5 sull'ospite (sel 8): col feed back 9.0 la chiusura integrale
    # blocca +0.56 EUR -> le uscite in profitto (tempo/profit) escono davvero
    row = {"event_id": "1.1", "market_id": "m1", "market_type": "MATCH_ODDS",
           "selection_id": 8, "side": "lay", "size": 10.0, "price": 8.5,
           "status": "open", "mode": "paper", "commission": 0.05, "origin": "auto",
           "strategy": strategy, "score_at_entry": "1-0", "minute_at_entry": 56,
           "signal_key": f"1.1:{strategy}:1-0", "sport": "calcio", "meta": {}}
    row.update(kw)
    return db.insert_trade(row)


def _closings(db, tid):
    return [t for t in db.trades if t.get("closes_trade_id") == tid]


def _cycle(db, feed_row, at=NOW, market=None):
    db.scan_rows = [feed_row]
    return S.run_once(db=db, market=market or FakeMarket(), engine=None, now=at)


def test_resolve_params_fonde_la_sezione_exits():
    p = S.resolve_params({"exits": {"base_exit_minute": 82}})
    assert p["exits"]["base_exit_minute"] == 82
    assert p["exits"]["esatto_exit_minute"] == 72 and p["exits"]["enabled"] is True
    assert S.resolve_params(None)["exits"] == XE.DEFAULT_EXIT_PARAMS


def test_exit_base_profit_chiude_dopo_l_assestamento_e_mai_due_volte():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "base")
    r = _cycle(db, _exit_feed_row(60, 1, 0))
    assert r["exits"] == 0
    assert db.get_trade(tid)["meta"]["exit_track"]["side"] == "home"
    # gol della favorita: decisione 'profit' ma si aspetta l'assestamento (30 s)
    t_goal = NOW + timedelta(seconds=2)
    r = _cycle(db, _exit_feed_row(66, 2, 0, updated_at=t_goal), at=t_goal)
    assert r["exits"] == 0 and _closings(db, tid) == []
    t_ok = t_goal + timedelta(seconds=31)
    r = _cycle(db, _exit_feed_row(66, 2, 0, updated_at=t_ok), at=t_ok)
    assert r["exits"] == 1
    closing = _closings(db, tid)
    assert len(closing) == 1 and closing[0]["side"] == "back"
    assert closing[0]["origin"] == "auto" and closing[0]["strategy"] == "base"
    assert db.get_trade(tid)["status"] == "hedged", "green-up integrale (fraction 1.0)"
    req = db.get_trade(tid)["meta"]["exit_requested"]
    assert req["sent"] is True and req["kind"] == "profit"
    assert req["closing_trade_id"] == closing[0]["id"]
    ex = [p for k, p in db.activity if k == "exit"]
    assert len(ex) == 1
    assert ex[0]["trade_id"] == tid and ex[0]["kind"] == "profit"
    assert ex[0]["reason"] == "favorita_segna_ancora"
    assert ex[0]["minute"] == 66 and ex[0]["score"] == "2-0"
    # cicli successivi: MAI una seconda uscita
    t2 = t_ok + timedelta(seconds=2)
    db.update_trade(tid, status="open")  # anche se la riga tornasse 'open'
    r = _cycle(db, _exit_feed_row(70, 3, 0, updated_at=t2), at=t2)
    assert r["exits"] == 0 and len(_closings(db, tid)) == 1


def test_exit_base_time_al_minuto_80_anche_a_bot_fermo():
    db = FakeDB(status="stopped")
    tid = _auto_trade(db, "base")
    _cycle(db, _exit_feed_row(79, 1, 0))
    assert _closings(db, tid) == []
    r = _cycle(db, _exit_feed_row(80, 1, 0))
    assert r["exits"] == 1
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["kind"] == "time" and ex["minute"] == 80


def test_exit_loss_esatto_aspetta_il_ritardo_di_assestamento_parametrico():
    db = FakeDB(status="running", params={"exits": {"loss_settle_delay_s": 20}})
    tid = _auto_trade(db, "esatto", market_id="cs1", market_type="CORRECT_SCORE",
                      selection_id=501, price=22.0, size=2.0)
    _cycle(db, _exit_feed_row(50, 1, 0))
    t_goal = NOW + timedelta(seconds=2)
    r = _cycle(db, _exit_feed_row(58, 2, 0, updated_at=t_goal), at=t_goal)
    assert r["exits"] == 0
    t_early = t_goal + timedelta(seconds=15)
    r = _cycle(db, _exit_feed_row(58, 2, 0, updated_at=t_early), at=t_early)
    assert r["exits"] == 0, "prima dei 20 s non si invia"
    t_ok = t_goal + timedelta(seconds=21)
    r = _cycle(db, _exit_feed_row(58, 2, 0, updated_at=t_ok), at=t_ok)
    assert r["exits"] == 1
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["kind"] == "loss" and ex["reason"] == "lato_bancato_segna"
    assert _closings(db, tid)[0]["side"] == "back"


def test_exit_punta_loss_quando_la_favorita_subisce():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "punta", selection_id=7, side="back", price=1.5,
                      score_at_entry="2-0")
    _cycle(db, _exit_feed_row(68, 2, 0))
    t_goal = NOW + timedelta(seconds=2)
    _cycle(db, _exit_feed_row(75, 2, 1, updated_at=t_goal), at=t_goal)
    t_ok = t_goal + timedelta(seconds=31)
    r = _cycle(db, _exit_feed_row(75, 2, 1, updated_at=t_ok), at=t_ok)
    assert r["exits"] == 1
    assert _closings(db, tid)[0]["side"] == "lay"
    assert [p for k, p in db.activity if k == "exit"][0]["kind"] == "loss"


def test_exit_rosso_alla_favorita():
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _cycle(db, _exit_feed_row(60, 1, 0))
    t_red = NOW + timedelta(seconds=2)
    _cycle(db, _exit_feed_row(63, 1, 0, red_home=1, updated_at=t_red), at=t_red)
    t_ok = t_red + timedelta(seconds=31)
    r = _cycle(db, _exit_feed_row(63, 1, 0, red_home=1, updated_at=t_ok), at=t_ok)
    assert r["exits"] == 1
    assert [p for k, p in db.activity if k == "exit"][0]["kind"] == "red_card"


def test_exit_tennis_obbligatoria_chiude_il_back_del_leader():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "tennis", event_id="2.1", market_id="mt", selection_id=11,
                      side="back", price=1.3, sport="tennis",
                      score_at_entry="set 1-0 \u00b7 game 4-2", minute_at_entry=None,
                      signal_key="2.1:tennis:set 1-0")
    _cycle(db, _tennis_feed_row((1, 0), (4, 2)))
    r = _cycle(db, _tennis_feed_row((1, 0), (4, 3)))
    assert r["exits"] == 0
    r = _cycle(db, _tennis_feed_row((1, 0), (4, 4)))
    assert r["exits"] == 1
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["kind"] == "mandatory" and ex["score"] == "set 1-0 \u00b7 game 4-4"
    assert ex["minute"] is None
    assert _closings(db, tid)[0]["side"] == "lay" and _closings(db, tid)[0]["price"] == 1.32


def test_exit_tennis_profit_al_game_vinto():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "tennis", event_id="2.1", market_id="mt", selection_id=11,
                      side="back", price=1.3, sport="tennis",
                      score_at_entry="set 1-0 \u00b7 game 4-2", minute_at_entry=None,
                      signal_key="2.1:tennis:set 1-0")
    _cycle(db, _tennis_feed_row((1, 0), (4, 2)))
    won = _tennis_feed_row((1, 0), (5, 2))
    won["payload"]["odds"]["p1"].update({"back": 1.22, "lay": 1.25})  # quota scesa
    r = _cycle(db, won)
    assert r["exits"] == 1 and len(_closings(db, tid)) == 1
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["kind"] == "profit" and ex["locked_pnl"] > 0
    assert ex["model_why"].startswith("profitto bloccato")


def test_exit_disabilitata_dai_parametri():
    db = FakeDB(status="running", params={"exits": {"enabled": False}})
    tid = _auto_trade(db, "base")
    _cycle(db, _exit_feed_row(60, 1, 0))
    r = _cycle(db, _exit_feed_row(85, 1, 0))
    assert r["exits"] == 0 and _closings(db, tid) == []
    assert "exit" not in db.kinds()


def test_exit_non_tocca_trade_manuali_o_hedged_e_traccia_il_modello():
    db = FakeDB(status="running")
    t_manual = _auto_trade(db, "manual", origin="manual", signal_key=None)
    t_model = _auto_trade(db, "model", signal_key="model:x")
    t_hedged = _auto_trade(db, "base", status="hedged", signal_key="1.1:base:h")
    _cycle(db, _exit_feed_row(60, 1, 0))
    r = _cycle(db, _exit_feed_row(85, 1, 1))
    assert r["exits"] == 0
    for tid in (t_manual, t_hedged):
        assert _closings(db, tid) == []
        assert "exit_track" not in (db.get_trade(tid)["meta"] or {})
    # il trade di MODELLO viene tracciato (regole a modello) ma, senza regola
    # attiva (lay dell'ospite: P(ospite vince) all'85' resta sotto soglia), si tiene
    assert _closings(db, t_model) == []
    assert "exit_track" in db.get_trade(t_model)["meta"]


def test_exit_con_feed_non_fresco_aspetta_poi_chiude():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "base")
    _cycle(db, _exit_feed_row(60, 1, 0))
    stale = NOW - timedelta(seconds=60)
    r = _cycle(db, _exit_feed_row(81, 1, 0, updated_at=stale))
    assert r["exits"] == 0 and _closings(db, tid) == []
    waits = [p for k, p in db.activity if k == "exit_wait"]
    assert len(waits) == 1 and waits[0]["wait"] == "feed_non_fresco"
    r = _cycle(db, _exit_feed_row(81, 1, 0, updated_at=stale))
    assert len([p for k, p in db.activity if k == "exit_wait"]) == 1, "log solo al cambio"
    assert db.get_trade(tid)["meta"].get("exit_requested") is None, "nessun tentativo consumato"
    # feed di nuovo fresco -> chiusura
    r = _cycle(db, _exit_feed_row(81, 1, 0))
    assert r["exits"] == 1 and len(_closings(db, tid)) == 1


def test_exit_con_scanner_vivo_accetta_la_riga_ferma():
    class ScannerDB(FakeDB):
        def scanner_status(self):
            return {"payload": {}, "updated_at": NOW.isoformat()}

    db = ScannerDB(status="running")
    tid = _auto_trade(db, "base")
    _cycle(db, _exit_feed_row(60, 1, 0))
    r = _cycle(db, _exit_feed_row(81, 1, 0, updated_at=NOW - timedelta(seconds=60)))
    assert r["exits"] == 1 and len(_closings(db, tid)) == 1


def test_exit_con_mercato_sospeso_aspetta():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "base")
    _cycle(db, _exit_feed_row(60, 1, 0))
    r = _cycle(db, _exit_feed_row(81, 1, 0, mo_status="SUSPENDED"))
    assert r["exits"] == 0 and _closings(db, tid) == []
    assert [p for k, p in db.activity if k == "exit_wait"][0]["wait"] == "mercato_sospeso"
    r = _cycle(db, _exit_feed_row(81, 1, 0))
    assert r["exits"] == 1


def test_exit_ritenta_fino_al_cap_poi_logga_errore():
    class NoClosingDB(FakeDB):
        """La riserva della gamba di chiusura fallisce sempre (DB KO)."""

        def __init__(self, **kw):
            super().__init__(**kw)
            self.closing_attempts = 0

        def insert_trade(self, trade):
            if trade.get("closes_trade_id"):
                self.closing_attempts += 1
                raise RuntimeError("db ko")
            return super().insert_trade(trade)

    db = NoClosingDB(status="running")
    tid = _auto_trade(db, "base")
    _cycle(db, _exit_feed_row(60, 1, 0))
    for i in range(1, 4):
        r = _cycle(db, _exit_feed_row(81, 1, 0))
        assert r["exits"] == 0
        assert db.get_trade(tid)["meta"]["exit_requested"]["attempts"] == i
    assert db.closing_attempts == 3
    req = db.get_trade(tid)["meta"]["exit_requested"]
    assert req["failed"] is True and req["sent"] is False
    assert req["last_error"] == "riserva_chiusura_fallita"
    errs = [p for k, p in db.activity if k == "error" and p.get("reason") == "exit_failed"]
    assert len(errs) == 1 and errs[0]["trade_id"] == tid and errs[0]["attempts"] == 3
    assert len([k for k in db.kinds() if k == "exit_retry"]) == 2
    # oltre il cap: nessun altro tentativo
    _cycle(db, _exit_feed_row(82, 1, 0))
    assert db.closing_attempts == 3


def test_exit_cashout_manuale_in_volo_non_conta_come_tentativo():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "base")
    _cycle(db, _exit_feed_row(60, 1, 0))
    db.insert_trade({"event_id": "1.1", "side": "back", "size": 12.0, "price": 9.0,
                     "status": "pending", "closes_trade_id": tid, "mode": "paper",
                     "meta": {"flumine_client_ref": "safe-t2", "flumine_request_id": 1}})
    r = _cycle(db, _exit_feed_row(81, 1, 0))
    assert r["exits"] == 0
    req = db.get_trade(tid)["meta"]["exit_requested"]
    assert req["attempts"] == 0 and req["sent"] is False and req["failed"] is False
    assert len(_closings(db, tid)) == 1, "nessuna seconda gamba di chiusura"


# ---------------------------------------------------------------------------
# RESIDUO dopo una chiusura cappata dalla liquidita' (difetto live trade 12)
# ---------------------------------------------------------------------------
def _cs_row(minute=72, back_size=1.0, updated_at=None, back=65.0, lay=70.0):
    """Feed CS: 'Altro risultato Casa' (sel 501) back 65 (tick valido: la chiusura
    del lay 2@60 blocca +0.15) con liquidita' limitata -> fill cappato, residuo."""
    row = _exit_feed_row(minute, 1, 0, updated_at=updated_at)
    for blk in (row["payload"]["cs"]["any_other_home"],
                row["payload"]["cs"]["selections"][0]):
        blk.update({"back": back, "lay": lay, "back_size": back_size})
    return row


def _esatto_2_at_60(db):
    return _auto_trade(db, "esatto", market_id="cs1", market_type="CORRECT_SCORE",
                       selection_id=501, price=60.0, size=2.0, minute_at_entry=50)


def test_exit_residuo_dopo_fill_cappato_viene_richiuso_dopo_il_cooldown():
    db = FakeDB(status="running")
    tid = _esatto_2_at_60(db)
    _cycle(db, _cs_row(60))
    r = _cycle(db, _cs_row(72, back_size=1.0))
    assert r["exits"] == 1
    t = db.get_trade(tid)
    assert t["status"] == "open", "fill parziale: resta aperta col residuo"
    assert t["meta"]["hedged_size"] == pytest.approx(1.08, abs=0.01)
    assert t["meta"]["residual_size"] == pytest.approx(0.92, abs=0.01)
    ex = [p for k, p in db.activity if k == "exit"]
    assert ex[0]["attempt"] == 1 and ex[0]["residual_after"] == pytest.approx(0.92, abs=0.01)
    # entro il cooldown (20 s) NON si ritenta, anche con liquidita' tornata
    for s in (2, 19):
        at = NOW + timedelta(seconds=s)
        r = _cycle(db, _cs_row(73, back_size=50.0, updated_at=at), at=at)
        assert r["exits"] == 0 and len(_closings(db, tid)) == 1
    at = NOW + timedelta(seconds=21)
    r = _cycle(db, _cs_row(73, back_size=50.0, updated_at=at), at=at)
    assert r["exits"] == 1
    legs = _closings(db, tid)
    assert len(legs) == 2 and legs[1]["side"] == "back"
    assert legs[1]["size"] == pytest.approx(0.85, abs=0.02), "residuo 0.92 * 60 / 65"
    t = db.get_trade(tid)
    assert t["status"] == "hedged" and t["meta"]["residual_size"] < 0.01
    req = t["meta"]["exit_requested"]
    assert req["sent"] is True and req["residual_attempts"] == 1
    ex = [p for k, p in db.activity if k == "exit"]
    assert len(ex) == 2 and ex[1]["attempt"] == 2
    assert ex[1]["residual_before"] == pytest.approx(0.92, abs=0.01)
    assert ex[1]["residual_after"] < 0.01 and ex[1]["kind"] == "time"
    # posizione chiusa: mai un altro tentativo
    at = NOW + timedelta(seconds=60)
    r = _cycle(db, _cs_row(74, back_size=50.0, updated_at=at), at=at)
    assert r["exits"] == 0 and len(_closings(db, tid)) == 2


def test_exit_residuo_non_si_ritenta_con_gamba_di_chiusura_pending():
    db = FakeDB(status="running")
    tid = _esatto_2_at_60(db)
    _cycle(db, _cs_row(60))
    _cycle(db, _cs_row(72, back_size=1.0))
    assert db.get_trade(tid)["status"] == "open"
    # una chiusura (manuale) e' in volo sulla coda flumine
    db.insert_trade({"event_id": "1.1", "market_id": "cs1", "selection_id": 501,
                     "side": "back", "size": 1.0, "price": 20.0, "status": "pending",
                     "closes_trade_id": tid, "mode": "paper",
                     "meta": {"flumine_client_ref": "safe-t9", "flumine_request_id": 9}})
    at = NOW + timedelta(seconds=30)
    r = _cycle(db, _cs_row(73, back_size=50.0, updated_at=at), at=at)
    assert r["exits"] == 0
    assert len([t for t in _closings(db, tid) if t["status"] != "pending"]) == 1
    assert db.get_trade(tid)["meta"]["exit_requested"].get("residual_attempts", 0) == 0


def test_exit_residuo_si_ferma_al_cap_e_logga_una_volta():
    db = FakeDB(status="running", params={"exits": {"residual_max_attempts": 2,
                                                    "residual_retry_s": 10}})
    tid = _esatto_2_at_60(db)
    _cycle(db, _cs_row(60))
    _cycle(db, _cs_row(72, back_size=0.3))     # 1a chiusura: 0.3@65 -> residuo 1.68
    for i, s in enumerate((11, 22), start=1):
        at = NOW + timedelta(seconds=s)
        r = _cycle(db, _cs_row(73, back_size=0.3, updated_at=at), at=at)
        assert r["exits"] == 1
        assert db.get_trade(tid)["meta"]["exit_requested"]["residual_attempts"] == i
    assert len(_closings(db, tid)) == 3
    assert db.get_trade(tid)["status"] == "open" and \
        db.get_trade(tid)["meta"]["residual_size"] > 0.01
    for s in (33, 44):
        at = NOW + timedelta(seconds=s)
        r = _cycle(db, _cs_row(74, back_size=50.0, updated_at=at), at=at)
        assert r["exits"] == 0
    assert len(_closings(db, tid)) == 3, "oltre il cap nessun tentativo"
    errs = [p for k, p in db.activity if k == "error"
            and p.get("reason") == "exit_residual_exhausted"]
    assert len(errs) == 1 and errs[0]["trade_id"] == tid and errs[0]["attempts"] == 2
    assert db.get_trade(tid)["meta"]["exit_requested"]["residual_exhausted"] is True


def test_exit_parametri_residuo_con_clamp():
    p = S.resolve_params({"exits": {"residual_retry_s": 0, "residual_max_attempts": -3}})
    assert p["exits"]["residual_retry_s"] == 2.0 and p["exits"]["residual_max_attempts"] == 0
    assert S.resolve_params(None)["exits"]["residual_retry_s"] == 20
    assert S.resolve_params(None)["exits"]["residual_max_attempts"] == 15


# ---------------------------------------------------------------------------
# dedupe dei log 'skip' del piazzamento (spam liquidita_insufficiente)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_skip_log_state():
    S._SKIP_LOG_STATE.clear()
    yield
    S._SKIP_LOG_STATE.clear()


def _skips(db, reason=None):
    return [p for k, p in db.activity if k == "skip"
            and (reason is None or p.get("reason") == reason)]


def test_skip_loggato_una_volta_per_segnale_e_motivo():
    db = FakeDB()
    db.scan_rows = [_feed_row()]
    eng = FakeEngine([_signal(size=10.0, size_available=4.0)])
    for i in range(8):
        S.run_once(db=db, market=FakeMarket(), engine=eng, now=NOW + timedelta(seconds=2 * i))
    assert len(_skips(db, "liquidita_insufficiente")) == 1
    assert S.resolve_params(None)["skip_log_interval_s"] == 300


def test_skip_riloggato_al_cambio_di_motivo_e_dopo_l_intervallo():
    db = FakeDB()
    eng = FakeEngine([_signal(size=10.0, size_available=4.0)])
    _run(db, engine=eng)
    # cambio di motivo: liquidita' ok ma liability oltre il cap -> nuovo log
    db.control["params"] = {"max_liability_per_trade": 5}
    eng.signals = [_signal(side="lay", price=6.0, size=10.0)]
    _run(db, engine=eng)
    assert len(_skips(db)) == 2 and _skips(db)[1]["reason"] == "max_liability_per_trade"
    # stesso motivo: silenzio finche' non passa l'intervallo
    _run(db, engine=eng)
    assert len(_skips(db)) == 2
    S.run_once(db=db, market=FakeMarket(), engine=eng, now=NOW + timedelta(seconds=299))
    assert len(_skips(db)) == 2
    S.run_once(db=db, market=FakeMarket(), engine=eng, now=NOW + timedelta(seconds=301))
    assert len(_skips(db)) == 3
    # intervallo personalizzato
    db.control["params"] = {"max_liability_per_trade": 5, "skip_log_interval_s": 30}
    S.run_once(db=db, market=FakeMarket(), engine=eng, now=NOW + timedelta(seconds=320))
    assert len(_skips(db)) == 3
    S.run_once(db=db, market=FakeMarket(), engine=eng, now=NOW + timedelta(seconds=332))
    assert len(_skips(db)) == 4


def test_skip_state_dimentica_le_chiavi_non_viste_da_10_minuti():
    db = FakeDB()
    db.scan_rows = [_feed_row(), _feed_row("1.2")]
    eng = FakeEngine([_signal(key="k1", size=10.0, size_available=4.0),
                      _signal(key="k2", size=10.0, size_available=4.0)])
    _run(db, engine=eng)
    assert set(S._SKIP_LOG_STATE) == {("1.1", "k1"), ("1.1", "k2")}
    eng.signals = [_signal(key="k2", size=10.0, size_available=4.0)]
    S.run_once(db=db, market=FakeMarket(), engine=eng, now=NOW + timedelta(seconds=601))
    assert set(S._SKIP_LOG_STATE) == {("1.1", "k2")}
    # segnale per un altro evento: chiave indipendente, log proprio
    eng.signals = [_signal(key="k1", event_id="1.2", size=10.0, size_available=4.0)]
    S.run_once(db=db, market=FakeMarket(), engine=eng, now=NOW + timedelta(seconds=602))
    # k1@1.1, k2@1.1, k2@1.1 riloggato a +601 s (intervallo passato), k1@1.2
    assert [(p["event_id"], p["signal_key"]) for p in _skips(db, "liquidita_insufficiente")] == \
        [("1.1", "k1"), ("1.1", "k2"), ("1.1", "k2"), ("1.2", "k1")]


# ---------------------------------------------------------------------------
# USCITE IN PROFITTO A MODELLO (decide_time_exit): mai chiudere in perdita
# quando il margine e' ampio; le uscite in PERDITA restano incondizionate
# ---------------------------------------------------------------------------
def _holds(db):
    return [p for k, p in db.activity if k == "exit_hold"]


def _cs_away_row(minute=72, sh=0, sa=1, back=20.0, lay=60.0, back_size=50.0, updated_at=None):
    """Feed CS del caso trade 12: 0-1, 'Altro risultato Ospite' (sel 502) back 20 / lay 60."""
    row = _exit_feed_row(minute, sh, sa, updated_at=updated_at)
    blk = {"selection_id": 502, "name": "Any Other Away Win", "back": back, "lay": lay,
           "back_size": back_size, "lay_size": back_size}
    row["payload"]["cs"]["any_other_away"] = dict(blk)
    row["payload"]["cs"]["selections"].append(dict(blk))
    return row


def _esatto_away_2_at_60(db):
    return _auto_trade(db, "esatto", market_id="cs1", market_type="CORRECT_SCORE",
                       selection_id=502, price=60.0, size=2.0, minute_at_entry=50,
                       score_at_entry="0-1", signal_key="1.1:esatto:away:0-1")


def test_caso_trade_12_uscita_a_tempo_in_perdita_con_margine_ampio_tiene():
    """esatto lay 2@60 'Altro risultato Ospite', 0-1 al 72', back 20: chiusura
    integrale = -4.0 EUR; il modello da' P(perdita) ~0.1% -> HOLD fino al
    settlement, log 'exit_hold' una volta, meta.exit_hold per la UI."""
    db = FakeDB(status="running")
    tid = _esatto_away_2_at_60(db)
    _cycle(db, _cs_away_row(60))
    for s in (2, 4, 6):
        at = NOW + timedelta(seconds=s)
        r = _cycle(db, _cs_away_row(72, updated_at=at), at=at)
        assert r["exits"] == 0 and _closings(db, tid) == []
    holds = _holds(db)
    assert len(holds) == 1, "log una sola volta per motivo"
    h = holds[0]
    assert h["trade_id"] == tid and h["kind"] == "time"
    assert h["locked"] == pytest.approx(-4.0, abs=0.01)
    assert h["source"] == "model" and h["p_lose"] is not None and h["p_lose"] <= 0.02
    assert h["msg"].startswith("margine ampio: P(perdita)=")
    assert h["msg"].endswith("tengo fino al settlement")
    assert h["hold_profit"] == 2.0 and h["loss_if_lose"] == 118.0
    meta = db.get_trade(tid)["meta"]
    assert meta.get("exit_requested") is None, "nessun invio"
    eh = meta["exit_hold"]
    assert eh["reason"] == h["msg"] and eh["p_lose"] == h["p_lose"]
    assert eh["source"] == "model" and eh["locked"] == pytest.approx(-4.0, abs=0.01)
    assert eh["ev_hold"] is not None and "ts" in eh
    assert "exit_kind" not in meta, "exit_kind solo a uscita INVIATA"
    # il prezzo migliora (back 65): profitto bloccato -> esce, exit_hold rimosso
    at = NOW + timedelta(seconds=8)
    r = _cycle(db, _cs_away_row(72, back=65.0, lay=70.0, updated_at=at), at=at)
    assert r["exits"] == 1 and db.get_trade(tid)["status"] == "hedged"
    meta = db.get_trade(tid)["meta"]
    assert "exit_hold" not in meta and meta["exit_kind"] == "time"
    assert meta["exit_reason"] == "Uscita a tempo al 72': green-up"
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["model_why"].startswith("profitto bloccato") and ex["exit_kind"] == "time"
    assert len(_holds(db)) == 1


def test_uscita_a_tempo_esce_se_il_rischio_supera_il_cap(monkeypatch):
    monkeypatch.setattr(S, "_p_selection_wins", lambda **kw: (0.15, "test"))
    db = FakeDB(status="running")
    tid = _esatto_away_2_at_60(db)
    _cycle(db, _cs_away_row(60))
    r = _cycle(db, _cs_away_row(72))
    assert r["exits"] == 1 and _holds(db) == []
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["p_lose"] == 0.15 and ex["p_source"] == "test"
    assert ex["model_why"].startswith("rischio alto: P(perdita)=15.0%")
    assert ex["locked_pnl"] == pytest.approx(-4.0, abs=0.01)
    assert db.get_trade(tid)["meta"]["exit_kind"] == "time"


def test_uscita_a_tempo_in_profitto_esce_sempre():
    db = FakeDB(status="running")
    tid = _esatto_away_2_at_60(db)
    _cycle(db, _cs_away_row(60, back=65.0, lay=70.0))
    r = _cycle(db, _cs_away_row(72, back=65.0, lay=70.0))
    assert r["exits"] == 1 and _holds(db) == []
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["locked_pnl"] == pytest.approx(0.15, abs=0.01)
    assert ex["model_why"].startswith("profitto bloccato +0.15")
    assert db.get_trade(tid)["status"] == "hedged"


def test_riserva_di_mercato_quando_il_modello_manca(monkeypatch):
    monkeypatch.setattr(S, "_import_opportunity_module", lambda: None)
    monkeypatch.setitem(S._EXIT_MODEL, "model", None)
    db = FakeDB(status="running")
    _esatto_away_2_at_60(db)
    _cycle(db, _cs_away_row(60))
    # implicita: P(vince)=1/20=5% -> EV(tengo)=0.95*2-0.05*118=-4.0 ~ bloccato -4.0 -> esce
    r = _cycle(db, _cs_away_row(72))
    assert r["exits"] == 1
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["p_source"] == "market" and ex["p_lose"] == pytest.approx(0.05)
    assert ex["ev_hold"] == pytest.approx(-4.0, abs=0.01)
    assert ex["model_why"].startswith("tenere non rende")


def test_hold_non_blocca_la_successiva_uscita_in_perdita():
    """Trade 12 in HOLD sull'uscita a tempo: quando il lato bancato segna la
    LOSS exit parte incondizionata (anche se blocca una perdita maggiore)."""
    db = FakeDB(status="running")
    tid = _esatto_away_2_at_60(db)
    _cycle(db, _cs_away_row(60))
    _cycle(db, _cs_away_row(72))
    assert len(_holds(db)) == 1 and _closings(db, tid) == []
    t_goal = NOW + timedelta(seconds=2)
    _cycle(db, _cs_away_row(74, sa=2, back=5.0, lay=6.0, updated_at=t_goal), at=t_goal)
    assert _closings(db, tid) == [], "assestamento post-gol"
    t_ok = t_goal + timedelta(seconds=31)
    r = _cycle(db, _cs_away_row(75, sa=2, back=5.0, lay=6.0, updated_at=t_ok), at=t_ok)
    assert r["exits"] == 1
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["kind"] == "loss" and ex["locked_pnl"] < -4.0
    assert ex["p_lose"] is None, "uscita in perdita: nessun gate a modello"
    meta = db.get_trade(tid)["meta"]
    assert meta["exit_kind"] == "loss" and "exit_hold" not in meta
    assert meta["exit_reason"] == "Il lato bancato ha segnato: chiusura in perdita"
    leg = _closings(db, tid)[0]
    assert leg["meta"]["exit_kind"] == "loss" and leg["meta"]["exit_reason"] == meta["exit_reason"]
    assert leg["meta"]["cashout"] is True, "il meta della chiusura resta intatto"


def test_take_profit_tennis_a_modello_tiene_in_perdita_con_margine_ampio():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "tennis", event_id="2.1", market_id="mt", selection_id=11,
                      side="back", price=1.3, size=10.0, sport="tennis",
                      score_at_entry="set 1-0 \u00b7 game 4-2", minute_at_entry=None,
                      signal_key="2.1:tennis:set 1-0")
    _cycle(db, _tennis_feed_row((1, 0), (4, 2)))
    # game vinto ma quota salita (lay 1.32 > 1.3): chiusura -0.15 -> modello
    r = _cycle(db, _tennis_feed_row((1, 0), (5, 2)))
    assert r["exits"] == 0 and _closings(db, tid) == []
    h = _holds(db)[0]
    assert h["kind"] == "profit" and h["source"] == "model"
    assert h["p_lose"] < 0.05 and h["msg"].endswith("tengo")
    assert h["ev_hold"] > h["locked"], "tenere rende di piu' della chiusura in perdita"
    assert db.get_trade(tid)["meta"]["exit_hold"]["source"] == "model"
    # quota scesa: profitto bloccato -> esce
    won = _tennis_feed_row((1, 0), (5, 2))
    won["payload"]["odds"]["p1"].update({"back": 1.22, "lay": 1.25})
    r = _cycle(db, won)
    assert r["exits"] == 1 and "exit_hold" not in db.get_trade(tid)["meta"]


def test_uscita_obbligatoria_tennis_e_forced_per_la_ui():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "tennis", event_id="2.1", market_id="mt", selection_id=11,
                      side="back", price=1.3, sport="tennis",
                      score_at_entry="set 1-0 \u00b7 game 4-2", minute_at_entry=None,
                      signal_key="2.1:tennis:set 1-0")
    for g in ((4, 2), (4, 3), (4, 4)):
        _cycle(db, _tennis_feed_row((1, 0), g))
    meta = db.get_trade(tid)["meta"]
    assert meta["exit_kind"] == "forced"
    assert meta["exit_reason"].startswith("Due game persi di fila")
    assert _closings(db, tid)[0]["meta"]["exit_kind"] == "forced"


def test_residuo_di_uscita_a_tempo_usa_la_stessa_decisione():
    db = FakeDB(status="running")
    tid = _esatto_2_at_60(db)
    _cycle(db, _cs_row(60))
    _cycle(db, _cs_row(72, back_size=1.0))            # fill cappato -> residuo 0.92
    assert db.get_trade(tid)["status"] == "open"
    # il prezzo peggiora (back 20): richiudere il residuo bloccherebbe una perdita
    # e il modello dice margine ampio -> HOLD del residuo
    at = NOW + timedelta(seconds=25)
    r = _cycle(db, _cs_row(73, back=20.0, lay=60.0, back_size=50.0, updated_at=at), at=at)
    assert r["exits"] == 0 and len(_closings(db, tid)) == 1
    assert len(_holds(db)) == 1 and _holds(db)[0]["locked"] < 0
    assert db.get_trade(tid)["meta"]["exit_requested"].get("residual_attempts", 0) == 0
    at = NOW + timedelta(seconds=27)
    r = _cycle(db, _cs_row(73, back_size=50.0, updated_at=at), at=at)
    assert r["exits"] == 1 and db.get_trade(tid)["status"] == "hedged"


def test_parametri_decisione_a_modello_e_chiavi_della_scheda():
    p = S.resolve_params(None)["exits"]
    assert p["hold_max_risk"] == 0.02 and p["risk_cap"] == 0.10 and p["ev_margin"] == 0.10
    sheet = {"enabled": True, "base_exit_minute": 81, "esatto_exit_minute": 73,
             "punta_exit_minute": 84, "loss_settle_delay_s": 25, "red_card_fav_exit": False,
             "tennis_take_profit_next_game": False, "tennis_exit_on_lost_game": True,
             "exit_max_retries": 5, "hold_max_risk": 0.05, "risk_cap": 0.2,
             "ev_margin": 0.5, "residual_retry_s": 30, "residual_max_attempts": 4,
             "model_exit_p_lose": 0.2, "model_take_profit_frac": 0.7,
             "model_free_cashout_p_lose": 0.01}
    m = S.resolve_params({"exits": sheet})["exits"]
    for k, v in sheet.items():
        assert m[k] == v, k
    assert set(m) == set(sheet), "nessuna chiave in piu' o in meno rispetto alla scheda"
    assert S.resolve_params({"exits": {"risk_cap": 5}})["exits"]["risk_cap"] == 1.0


# ---------------------------------------------------------------------------
# REGOLA B: gate SPREAD all'ingresso (lay/back dal feed, max 1.6)
# ---------------------------------------------------------------------------
def _cs_signal(**kw):
    base = dict(key="1.1:esatto:home:1-0", variant="esatto", side="lay", price=60.0,
                size=2.0, market_type="CORRECT_SCORE", selection_id=501)
    base.update(kw)
    s = _signal(**base)
    s.market_id = "cs1"
    return s


def test_spread_anomalo_scarta_l_ingresso_del_trade_12():
    db = FakeDB(status="running")
    db.scan_rows = [_cs_row(50, back=20.0, lay=60.0, back_size=50.0)]
    res = _run(db, engine=FakeEngine([_cs_signal()]))
    assert res["placed"] == 0 and db.trades == []
    sk = _skips(db, "spread_anomalo")
    assert len(sk) == 1 and sk[0]["signal_key"] == "1.1:esatto:home:1-0"
    assert sk[0]["back"] == 20.0 and sk[0]["lay"] == 60.0
    assert sk[0]["spread_ratio"] == pytest.approx(3.0) and sk[0]["max_spread_ratio"] == 1.6
    # log deduplicato nei cicli successivi
    _run(db, engine=FakeEngine([_cs_signal()]))
    assert len(_skips(db, "spread_anomalo")) == 1


def test_spread_nel_limite_entra_e_oltre_il_limite_parametrico_no():
    db = FakeDB(status="running")
    db.scan_rows = [_cs_row(50, back=60.0, lay=65.0, back_size=50.0)]
    res = _run(db, engine=FakeEngine([_cs_signal()]))
    assert res["placed"] == 1 and db.trades[0]["strategy"] == "esatto"
    # 1.083 di spread ma soglia utente 1.05 -> scartato
    db = FakeDB(status="running", params={"max_spread_ratio": 1.05})
    db.scan_rows = [_cs_row(50, back=60.0, lay=65.0, back_size=50.0)]
    res = _run(db, engine=FakeEngine([_cs_signal()]))
    assert res["placed"] == 0 and _skips(db, "spread_anomalo")
    assert S.resolve_params({"max_spread_ratio": 0.2})["max_spread_ratio"] == 1.0


def test_spread_gate_senza_back_nel_feed_scarta():
    db = FakeDB(status="running")
    row = _feed_row()
    row["payload"]["odds"]["home"]["back"] = None
    db.scan_rows = [row]
    res = _run(db, engine=FakeEngine([_signal()]))
    assert res["placed"] == 0
    assert _skips(db, "spread_anomalo")[0]["spread_ratio"] is None
    # evento assente dal feed: nessun prezzo reale -> scartato (fail-closed)
    S._SKIP_LOG_STATE.clear()   # stessa chiave/motivo del caso sopra: dedupe
    db = FakeDB(status="running")
    db.scan_rows = [_feed_row("9.9")]
    res = _run(db, engine=FakeEngine([_signal()]))
    assert res["placed"] == 0 and _skips(db, "spread_anomalo")
    # Match Odds con spread normale (3.0/3.1): entra
    db = FakeDB(status="running")
    assert _run(db, engine=FakeEngine([_signal()]))["placed"] == 1


# ---------------------------------------------------------------------------
# RISCHIO (risk.py) cablato prima di ogni riserva
# ---------------------------------------------------------------------------
from Betfair.safe_strategy import risk as RK  # noqa: E402


def _blocks(db, reason=None):
    return [p for k, p in db.activity if k == "risk_block" and (reason is None or p["reason"] == reason)]


def _lost_today(db, pnl=-60.0):
    return db.insert_trade({"event_id": "0.1", "status": "lost", "pnl": pnl, "liability": 10.0,
                            "side": "back", "market_id": "m0", "selection_id": 1, "size": 10.0,
                            "price": 2.0, "mode": "paper", "settled_at": NOW.isoformat(),
                            "strategy": "base", "origin": "auto", "signal_key": "0.1:old"})


def test_parametri_di_rischio_e_flag_auto_trade_per_default():
    p = S.resolve_params(None)
    assert p["risk"] == RK.merge_risk_params(None)
    assert p["risk"]["daily_liability_cap"] == 500 and p["risk"]["daily_loss_stop"] == -50
    assert p["auto_trade_anomalies"] is False and p["auto_trade_combos"] is False
    assert p["auto_trade_tennis"] is False and p["auto_trade_opportunities"] is False
    q = S.resolve_params({"risk": {"per_event_liability_cap": 20}, "auto_trade_combos": 1})
    assert q["risk"]["per_event_liability_cap"] == 20 and q["risk"]["model_stake"] == 5
    assert q["auto_trade_combos"] is True


def test_loss_stop_giornaliero_blocca_i_segnali_con_log_deduplicato():
    S._SKIP_LOG_STATE.clear()
    db = FakeDB(status="running")
    _lost_today(db, -60.0)
    res = _run(db, engine=FakeEngine([_signal()]))
    assert res["placed"] == 0
    assert [t for t in db.trades if t.get("signal_key") == "k1"] == []
    b = _blocks(db, "daily_loss_stop")
    assert len(b) == 1 and b[0]["signal_key"] == "k1" and b[0]["realized_today"] == -60.0
    assert res["stats"]["risk"]["loss_stop_active"] is True
    _run(db, engine=FakeEngine([_signal()]))
    assert len(_blocks(db, "daily_loss_stop")) == 1, "dedupe del log per segnale e motivo"
    # sotto la soglia si piazza
    db2 = FakeDB(status="running")
    _lost_today(db2, -20.0)
    assert _run(db2, engine=FakeEngine([_signal()]))["placed"] == 1
    assert db2.control["stats"]["risk"]["loss_stop_active"] is False


def test_cap_per_evento_correlato_sui_segnali():
    S._SKIP_LOG_STATE.clear()
    # aperto 60 di liability sul CS dell'evento: il lay CS 2@60 (118) -> 178 > 170
    db = FakeDB(status="running", params={"risk": {"per_event_liability_cap": 170}})
    _auto_trade(db, "esatto", market_type="CORRECT_SCORE", liability=60.0, signal_key="1.1:esatto:x")
    db.scan_rows = [_cs_row(50, back=60.0, lay=65.0, back_size=50.0)]
    res = _run(db, engine=FakeEngine([_cs_signal()]))
    assert res["placed"] == 0 and _blocks(db, "per_event_liability_cap")
    # stesso aperto ma su un altro mercato (Match Odds): pesa 0.7 -> 42 + 118 = 160 <= 170
    db = FakeDB(status="running", params={"risk": {"per_event_liability_cap": 170}})
    _auto_trade(db, "base", market_type="MATCH_ODDS", liability=60.0, signal_key="1.1:base:x")
    db.scan_rows = [_cs_row(50, back=60.0, lay=65.0, back_size=50.0)]
    assert _run(db, engine=FakeEngine([_cs_signal()]))["placed"] == 1


def test_posizioni_per_evento_e_cap_giornaliero_contano_anche_nel_ciclo():
    S._SKIP_LOG_STATE.clear()
    db = FakeDB(status="running", params={"risk": {"per_event_max_trades": 2}})
    sig = [_signal(key=f"k{i}", size=5.0) for i in range(4)]
    res = _run(db, engine=FakeEngine(sig))
    assert res["placed"] == 2, "la terza posizione sullo stesso evento e' bloccata nello stesso ciclo"
    assert _blocks(db, "per_event_max_trades")
    # cap giornaliero: 3 segnali da 200 con cap 500 -> il terzo e' bloccato
    S._SKIP_LOG_STATE.clear()
    db = FakeDB(status="running", params={"max_liability_per_trade": 300,
                                          "risk": {"per_event_liability_cap": 0}})
    sig = [_signal(key=f"k{i}", event_id=f"1.{i}", size=200.0, size_available=500.0) for i in range(3)]
    db.scan_rows = [_feed_row(f"1.{i}") for i in range(3)]
    res = _run(db, engine=FakeEngine(sig))
    assert res["placed"] == 2 and _blocks(db, "daily_liability_cap")
    assert res["stats"]["risk"]["daily_liability"] == 400.0 and res["stats"]["risk"]["daily_cap"] == 500.0


def test_manuale_controllo_morbido_solo_cap():
    # loss stop attivo: il manuale passa lo stesso
    db = FakeDB(status="stopped")
    _lost_today(db, -60.0)
    db.scan_rows = [_feed_row()]
    db.requests.append({"id": 1, "kind": "place", "status": "pending", "payload": _place_payload()})
    _run(db)
    assert db.requests[0]["status"] == "done"
    # cap giornaliero superato: il manuale e' bloccato con motivo
    db = FakeDB(status="stopped", params={"risk": {"daily_liability_cap": 100}})
    _auto_trade(db, "base", liability=98.0)
    db.scan_rows = [_feed_row()]
    db.requests.append({"id": 1, "kind": "place", "status": "pending", "payload": _place_payload()})
    _run(db)
    assert db.requests[0]["status"] == "error"
    assert db.requests[0]["result"] == {"error": "risk_block", "reason": "daily_liability_cap",
                                        "liability": 5.0}
    assert _blocks(db, "daily_liability_cap")[0]["soft"] is True


def test_aggregati_giornalieri_per_il_rischio():
    from Betfair.safe_strategy import bot_db

    day = RK.operating_day_start(NOW)
    rows = [
        {"id": 1, "status": "open", "liability": 10.0, "placed_at": NOW.isoformat(), "strategy": "model"},
        {"id": 2, "status": "lost", "liability": 7.0, "pnl": -7.0, "placed_at": NOW.isoformat(),
         "settled_at": NOW.isoformat(), "strategy": "base"},
        {"id": 3, "status": "void", "liability": 5.0, "placed_at": NOW.isoformat()},
        {"id": 4, "status": "pending", "liability": 4.0, "placed_at": NOW.isoformat(), "meta": {}},
        {"id": 5, "status": "hedged", "liability": 3.0, "placed_at": "2026-09-01T10:00:00+00:00"},
        {"id": 6, "status": "open", "liability": 2.0, "placed_at": NOW.isoformat(), "closes_trade_id": 1},
    ]
    agg = bot_db.aggregate_rows(rows, day_start=day)
    assert agg["day_liability"] == 17.0 and agg["day_liability_model"] == 10.0
    assert agg["day_trades"] == 2 and agg["realized_today"] == -7.0
    assert bot_db.aggregate_rows(rows)["day_liability"] == 20.0, "senza giornata: tutto"


# ---------------------------------------------------------------------------
# USCITE dei trade di MODELLO
# ---------------------------------------------------------------------------
def _model_trade(db, **kw):
    row = dict(strategy="model", signal_key="model:MATCH_ODDS:8:lay", selection_name="Away",
               meta={"kind": "model", "p_lose_entry": 0.05})
    row.update(kw)
    return _auto_trade(db, **row)


def test_uscita_modello_gol_avverso_dopo_l_assestamento(monkeypatch):
    monkeypatch.setattr(S, "_p_selection_wins", lambda **kw: (0.2, "test"))
    db = FakeDB(status="running")
    tid = _model_trade(db)   # lay ospite 10@8.5 sull'1-0
    r = _cycle(db, _exit_feed_row(60, 1, 0))
    assert r["exits"] == 0 and db.get_trade(tid)["status"] == "open"
    t_goal = NOW + timedelta(seconds=2)
    r = _cycle(db, _exit_feed_row(66, 1, 1, updated_at=t_goal), at=t_goal)
    assert r["exits"] == 0, "ritardo di assestamento"
    assert db.get_trade(tid)["meta"]["exit_track"]["wait_reason"] == "assestamento_post_evento"
    t_ok = t_goal + timedelta(seconds=31)
    r = _cycle(db, _exit_feed_row(66, 1, 1, updated_at=t_ok), at=t_ok)
    assert r["exits"] == 1 and db.get_trade(tid)["status"] == "hedged"
    meta = db.get_trade(tid)["meta"]
    assert meta["exit_kind"] == "loss" and meta["exit_reason"].startswith("Gol avverso")
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["strategy"] == "model" and ex["p_lose"] == 0.2 and ex["model_why"] == "loss:gol_avverso"
    # mai due volte
    r = _cycle(db, _exit_feed_row(70, 1, 1, updated_at=t_ok), at=t_ok + timedelta(seconds=5))
    assert r["exits"] == 0 and len(_closings(db, tid)) == 1


def test_uscita_modello_gol_non_avverso_o_sotto_soglia_tiene(monkeypatch):
    monkeypatch.setattr(S, "_p_selection_wins", lambda **kw: (0.08, "test"))
    db = FakeDB(status="running")
    tid = _model_trade(db)
    _cycle(db, _exit_feed_row(60, 1, 0))
    t = NOW + timedelta(seconds=40)
    r = _cycle(db, _exit_feed_row(66, 1, 1, updated_at=t), at=t)
    assert r["exits"] == 0 and _closings(db, tid) == []
    # p_lose alta ma SCESA rispetto all'ingresso: il gol ha aiutato
    monkeypatch.setattr(S, "_p_selection_wins", lambda **kw: (0.3, "test"))
    db = FakeDB(status="running")
    tid = _model_trade(db, meta={"kind": "model", "p_lose_entry": 0.45})
    _cycle(db, _exit_feed_row(60, 1, 0))
    r = _cycle(db, _exit_feed_row(66, 1, 1, updated_at=t), at=t)
    assert r["exits"] == 0 and _closings(db, tid) == []


def test_uscita_modello_take_profit(monkeypatch):
    monkeypatch.setattr(S, "_p_selection_wins", lambda **kw: (0.9, "test"))
    db = FakeDB(status="running")
    # back casa 10@3.0 (profitto massimo 20): la casa scende a 1.10 -> chiusura blocca ~17 >= 16
    tid = _model_trade(db, side="back", selection_id=7, price=3.0, selection_name="Home",
                       signal_key="model:MATCH_ODDS:7:back", meta={"kind": "model", "p_lose_entry": 0.6})
    row = _exit_feed_row(75, 2, 0)
    row["payload"]["odds"]["home"].update({"back": 1.09, "lay": 1.1})
    r = _cycle(db, row)
    assert r["exits"] == 1 and db.get_trade(tid)["status"] == "hedged"
    meta = db.get_trade(tid)["meta"]
    assert meta["exit_kind"] == "profit" and meta["exit_reason"] == "Take profit del modello: profitto bloccato"
    ex = [p for k, p in db.activity if k == "exit"][0]
    assert ex["locked_pnl"] >= 16.0
    # a 1.3 blocca solo ~13 (< 16): si tiene
    db = FakeDB(status="running")
    tid = _model_trade(db, side="back", selection_id=7, price=3.0, selection_name="Home",
                       signal_key="model:MATCH_ODDS:7:back")
    row = _exit_feed_row(75, 2, 0)
    row["payload"]["odds"]["home"].update({"back": 1.29, "lay": 1.3})
    assert _cycle(db, row)["exits"] == 0 and _closings(db, tid) == []


def test_uscita_modello_cashout_quasi_gratis(monkeypatch):
    monkeypatch.setattr(S, "_p_selection_wins", lambda **kw: (0.001, "test"))
    db = FakeDB(status="running")
    # lay ospite 10@8.5: ospite a 30 -> chiusura in profitto con P(perdita) 0.1%
    tid = _model_trade(db)
    row = _exit_feed_row(80, 3, 0)
    row["payload"]["odds"]["away"].update({"back": 30.0, "lay": 34.0})
    r = _cycle(db, row)
    assert r["exits"] == 1
    assert db.get_trade(tid)["meta"]["exit_reason"].startswith("Posizione ormai vinta")


def test_uscita_modello_linea_decisa_contro():
    db = FakeDB(status="running")
    row = _feed_row_goal_markets()
    row["payload"].update({"score_home": 1, "score_away": 0, "minute": 30,
                           "red_home": 0, "red_away": 0, "mo_status": "OPEN"})
    tid = _auto_trade(db, "model", market_id="ou25", market_type="OVER_UNDER_25", selection_id=47973,
                      selection_name="Under 2.5 Goals", side="back", price=1.8, size=10.0,
                      score_at_entry="1-0", signal_key="model:OVER_UNDER_25:47973:back",
                      meta={"kind": "model", "line": 2.5, "p_lose_entry": 0.45})
    assert _cycle(db, row)["exits"] == 0
    row2 = _feed_row_goal_markets()
    row2["payload"].update({"score_home": 2, "score_away": 1, "minute": 70,
                            "red_home": 0, "red_away": 0, "mo_status": "OPEN"})
    t = NOW + timedelta(seconds=2)
    row2["updated_at"] = t.isoformat()
    assert _cycle(db, row2, at=t)["exits"] == 0, "assestamento post-gol"
    t2 = t + timedelta(seconds=31)
    row2["updated_at"] = t2.isoformat()
    assert _cycle(db, row2, at=t2)["exits"] == 1
    meta = db.get_trade(tid)["meta"]
    assert meta["exit_kind"] == "loss" and meta["exit_reason"].startswith("La linea tradata")
    assert _closings(db, tid)[0]["side"] == "lay" and _closings(db, tid)[0]["price"] == 1.82


def test_uscita_modello_tennis_due_game_persi_di_fila():
    db = FakeDB(status="running")
    tid = _auto_trade(db, "model", sport="tennis", event_id="2.1", market_id="mt",
                      market_type="MATCH_ODDS", selection_id=11, selection_name="P1", side="back",
                      price=1.3, size=10.0, score_at_entry="set 1-0 . game 4-2",
                      signal_key="tennis:MATCH_ODDS:11:back", meta={"kind": "tennis"})
    assert _cycle(db, _tennis_feed_row((1, 0), (4, 2)))["exits"] == 0
    assert db.get_trade(tid)["meta"]["exit_track"]["side"] == "p1"
    t1 = NOW + timedelta(seconds=2)
    assert _cycle(db, _tennis_feed_row((1, 0), (4, 3), updated_at=t1), at=t1)["exits"] == 0
    t2 = t1 + timedelta(seconds=2)
    r = _cycle(db, _tennis_feed_row((1, 0), (4, 4), updated_at=t2), at=t2)
    assert r["exits"] == 1 and db.get_trade(tid)["status"] == "hedged"
    meta = db.get_trade(tid)["meta"]
    assert meta["exit_kind"] == "loss" and "due game" in meta["exit_reason"]


# ---------------------------------------------------------------------------
# ANOMALIE (cecchino), COMBO (tutte o nessuna), TENNIS: moduli opzionali
# ---------------------------------------------------------------------------
class FakeBookModel(FakeModel):
    def book(self, payload, *, lambdas, league_id, ht_ratio=None):
        return {"over_2_5": 0.55, "btts_yes": 0.5}


def _anomaly(**kw):
    a = _opp(kind="anomaly", rule="ou_ladder", price=2.4, size_available=100.0)
    a.update(kw)
    return a


class FakeAnomaly:
    def __init__(self, found=None):
        self.found = list(found or [])
        self.calls = 0

    def detect(self, payload, book, *, params=None):
        self.calls += 1
        assert "over_2_5" in book
        return list(self.found)


def _feed_odds_row(ts=1, event_id="1.1"):
    row = _feed_row_goal_markets()
    row["event_id"] = event_id
    row["payload"].update({"score_home": 1, "score_away": 0, "odds_ts_ms": ts})
    return row


def test_anomalie_valutate_a_ogni_ciclo_solo_se_le_quote_cambiano_e_fuse_nelle_opportunita():
    db = FakeDB(status="running")
    db.scan_rows = [_feed_odds_row(ts=1)]
    an = FakeAnomaly([_anomaly()])
    st = {"last_ts": 0.0, "hashes": {}}
    r = _run(db, engine=None, opp_model=FakeBookModel([_opp()]), opp_mod=FAKE_OPP_MOD,
             opps_state=st, extra_mods={"anomaly": an})
    assert r["anomalies"] == {"events": 1, "found": 1, "traded": 0} and an.calls == 1
    body = db.opportunities[-1][0]["payload"]
    kinds = [o["kind"] for o in body["opportunities"]]
    assert sorted(kinds) == ["anomaly", "model"] and body["kinds"] == {"model": 1, "anomaly": 1, "combo": 0}
    assert r["stats"]["opps"] == {"model": 1, "anomaly": 1, "combo": 0, "tennis": 0}
    # stesso odds_ts_ms: nessuna rivalutazione; cambia -> rivalutata
    r = _run(db, engine=None, opp_model=FakeBookModel([_opp()]), opp_mod=FAKE_OPP_MOD,
             opps_state=st, extra_mods={"anomaly": an})
    assert r["anomalies"]["events"] == 0 and an.calls == 1
    db.scan_rows = [_feed_odds_row(ts=2)]
    r = _run(db, engine=None, opp_model=FakeBookModel([_opp()]), opp_mod=FAKE_OPP_MOD,
             opps_state=st, extra_mods={"anomaly": an})
    assert r["anomalies"]["events"] == 1 and an.calls == 2
    assert db.trades == [], "auto_trade_anomalies spento per default"


def test_anomalie_piazzate_subito_come_cecchino_con_dedupe_120s():
    db = FakeDB(status="running", params={"auto_trade_anomalies": True})
    db.scan_rows = [_feed_odds_row(ts=1)]
    an = FakeAnomaly([_anomaly()])
    st = {"last_ts": NOW.timestamp(), "hashes": {}}   # opportunita' throttlate: il cecchino no
    r = _run(db, engine=None, opp_model=FakeBookModel(), opp_mod=FAKE_OPP_MOD,
             opps_state=st, extra_mods={"anomaly": an})
    assert r["anomalies"]["traded"] == 1 and len(db.trades) == 1
    t = db.trades[0]
    assert t["strategy"] == "model" and t["size"] == 5 and t["status"] == "open"
    assert t["meta"]["kind"] == "anomaly" and t["meta"]["sniper"] is True
    assert t["signal_key"].startswith("anomaly:OVER_UNDER_25:47972:back:")
    assert t["meta"]["p_lose_entry"] == 0.45
    # quote cambiate entro 120 s: stessa (evento, mercato, selezione, lato) -> dedupe
    db.scan_rows = [_feed_odds_row(ts=2)]
    at = NOW + timedelta(seconds=60)
    r = S.run_once(db=db, market=FakeMarket(), engine=None, opp_model=FakeBookModel(),
                   opp_mod=FAKE_OPP_MOD, opps_state=st, extra_mods={"anomaly": an}, now=at)
    assert r["anomalies"]["traded"] == 0 and len(db.trades) == 1
    # dopo 120 s: si puo' rientrare (anche con lo stato in memoria perso)
    db.scan_rows = [_feed_odds_row(ts=3)]
    at = NOW + timedelta(seconds=121)
    st2 = {"last_ts": at.timestamp(), "hashes": {}}
    r = S.run_once(db=db, market=FakeMarket(), engine=None, opp_model=FakeBookModel(),
                   opp_mod=FAKE_OPP_MOD, opps_state=st2, extra_mods={"anomaly": an}, now=at)
    assert r["anomalies"]["traded"] == 1 and len(db.trades) == 2
    # a bot fermo mai
    db = FakeDB(status="stopped", params={"auto_trade_anomalies": True})
    db.scan_rows = [_feed_odds_row(ts=1)]
    r = _run(db, engine=None, opp_model=FakeBookModel(), opp_mod=FAKE_OPP_MOD,
             opps_state={"last_ts": 0.0, "hashes": {}}, extra_mods={"anomaly": FakeAnomaly([_anomaly()])})
    assert r["anomalies"]["found"] == 1 and db.trades == []


def test_anomalie_rispettano_il_rischio_e_lo_stake_di_modello():
    S._SKIP_LOG_STATE.clear()
    db = FakeDB(status="running", params={"auto_trade_anomalies": True,
                                          "risk": {"model_stake": 8, "model_daily_liability_cap": 10}})
    db.scan_rows = [_feed_odds_row(ts=1)]
    st = {"last_ts": NOW.timestamp(), "hashes": {}}
    r = _run(db, engine=None, opp_model=FakeBookModel(), opp_mod=FAKE_OPP_MOD, opps_state=st,
             extra_mods={"anomaly": FakeAnomaly([_anomaly(), _anomaly(selection_id=47973,
                                                                       selection_name="Under 2.5 Goals")])})
    assert r["anomalies"]["traded"] == 1 and db.trades[0]["size"] == 8
    assert _blocks(db, "model_daily_liability_cap")


def _combo(legs=None, **kw):
    legs = legs or [
        {"market_type": "OVER_UNDER_25", "market_id": "ou25", "selection_id": 47972,
         "selection_name": "Over 2.5 Goals", "side": "back", "price": 2.2,
         "size_available": 300.0, "stake_ratio": 0.5},
        {"market_type": "BOTH_TEAMS_TO_SCORE", "market_id": "btts1", "selection_id": 30246,
         "selection_name": "Yes", "side": "back", "price": 1.9, "size_available": 10.0,
         "stake_ratio": 0.5},
    ]
    c = _opp(kind="combo", id="c1", legs=legs, rationale="dutching")
    c.update(kw)
    return c


class FakeCombos:
    def __init__(self, combos=None):
        self.combos = list(combos or [])

    def find_combos(self, payload, book, *, params=None):
        return list(self.combos)


def test_combo_tutte_le_gambe_o_nessuna():
    db = FakeDB(status="running", params={"auto_trade_combos": True})
    db.scan_rows = [_feed_odds_row(ts=1)]
    st = {"last_ts": 0.0, "hashes": {}}
    r = _run(db, engine=None, opp_model=FakeBookModel(), opp_mod=FAKE_OPP_MOD, opps_state=st,
             extra_mods={"combos": FakeCombos([_combo()])})
    assert r["opportunities"]["traded"] == 1 and len(db.trades) == 2
    assert {t["meta"]["combo_id"] for t in db.trades} == {"c1"}
    assert [t["signal_key"] for t in db.trades] == ["combo:c1:0", "combo:c1:1"]
    assert all(t["strategy"] == "model" and t["meta"]["kind"] == "combo" and t["size"] == 5.0
               and t["status"] == "open" for t in db.trades)
    assert db.opportunities[-1][0]["payload"]["kinds"]["combo"] == 1
    # una gamba non abbinabile in paper (liquidita' 1 < stake): nessuna gamba piazzata
    S._SKIP_LOG_STATE.clear()
    db = FakeDB(status="running", params={"auto_trade_combos": True})
    db.scan_rows = [_feed_odds_row(ts=1)]
    legs = _combo()["legs"]
    legs[1]["size_available"] = 1.0
    r = _run(db, engine=None, opp_model=FakeBookModel(), opp_mod=FAKE_OPP_MOD,
             opps_state={"last_ts": 0.0, "hashes": {}},
             extra_mods={"combos": FakeCombos([_combo(legs=legs)])})
    assert r["opportunities"]["traded"] == 0 and db.trades == []
    assert _skips(db, "combo_gamba_non_abbinabile")
    # proporzioni di dutching rispettate: 0.7/0.3 su 2 gambe da 5 medi -> 7 e 3
    db = FakeDB(status="running", params={"auto_trade_combos": True})
    db.scan_rows = [_feed_odds_row(ts=1)]
    legs = _combo()["legs"]
    legs[0]["stake_ratio"], legs[1]["stake_ratio"] = 0.7, 0.3
    _run(db, engine=None, opp_model=FakeBookModel(), opp_mod=FAKE_OPP_MOD,
         opps_state={"last_ts": 0.0, "hashes": {}}, extra_mods={"combos": FakeCombos([_combo(legs=legs)])})
    assert [t["size"] for t in db.trades] == [7.0, 3.0]


def test_combo_riserva_incompleta_libera_le_riserve():
    class HalfDB(FakeDB):
        def insert_trade(self, trade):
            if str(trade.get("signal_key") or "").endswith(":1"):
                raise Exception("unique")
            return super().insert_trade(trade)

    S._SKIP_LOG_STATE.clear()
    db = HalfDB(status="running", params={"auto_trade_combos": True})
    db.scan_rows = [_feed_odds_row(ts=1)]
    r = _run(db, engine=None, opp_model=FakeBookModel(), opp_mod=FAKE_OPP_MOD,
             opps_state={"last_ts": 0.0, "hashes": {}}, extra_mods={"combos": FakeCombos([_combo()])})
    assert r["opportunities"]["traded"] == 0
    assert db.trades == [], "la riserva della prima gamba e' stata liberata"
    assert _skips(db, "combo_riserva_incompleta")


class FakeTennisModel:
    def __init__(self, params):
        self.params = params

    def evaluate(self, payload, now_ts):
        return [_opp(kind="tennis", market_type="MATCH_ODDS", market_id="mt", selection_id=11,
                     selection_name="P1", price=1.3, size_available=500.0, p_model=0.85)]


def test_opportunita_tennis_pubblicate_e_tradate_solo_se_abilitate():
    db = FakeDB(status="running")
    db.scan_rows = [_tennis_feed_row()]
    tennis = SimpleNamespace(TennisOpportunityModel=FakeTennisModel)
    st = {"last_ts": 0.0, "hashes": {}}
    r = _run(db, engine=None, opp_model=None, opp_mod=None, opps_state=st,
             extra_mods={"tennis": tennis})
    assert r["opportunities"] == {"events": 1, "written": 1, "traded": 0}
    w = db.opportunities[-1][0]
    assert w["sport"] == "tennis" and w["payload"]["opportunities"][0]["kind"] == "tennis"
    assert r["stats"]["opps"]["tennis"] == 1 and db.trades == []
    db = FakeDB(status="running", params={"auto_trade_tennis": True})
    db.scan_rows = [_tennis_feed_row()]
    r = _run(db, engine=None, opp_model=None, opp_mod=None, opps_state={"last_ts": 0.0, "hashes": {}},
             extra_mods={"tennis": tennis})
    assert r["opportunities"]["traded"] == 1
    t = db.trades[0]
    assert t["sport"] == "tennis" and t["strategy"] == "model" and t["meta"]["kind"] == "tennis"
    assert t["signal_key"] == "tennis:MATCH_ODDS:11:back" and t["size"] == 5
    assert t["score_at_entry"] == "set 1-0 \u00b7 game 4-2" and t["meta"]["p_lose_entry"] == 0.15


def test_moduli_opzionali_assenti_non_rompono_il_ciclo():
    db = FakeDB(status="running", params={"auto_trade_anomalies": True, "auto_trade_combos": True,
                                          "auto_trade_tennis": True})
    db.scan_rows = [_feed_odds_row(ts=1), _tennis_feed_row()]
    r = _run(db, engine=None, opp_model=FakeBookModel([_opp()]), opp_mod=FAKE_OPP_MOD,
             opps_state={"last_ts": 0.0, "hashes": {}},
             extra_mods={"anomaly": None, "combos": None, "tennis": None})
    assert r["anomalies"] == {"events": 0, "found": 0, "traded": 0}
    assert r["opportunities"]["events"] == 1 and "risk" in r["stats"] and "opps" in r["stats"]
    assert S._import_optional("modulo_che_non_esiste") is None
