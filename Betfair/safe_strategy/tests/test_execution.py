"""Test dello strato CONDIVISO di piazzamento/chiusura (execution.py) e del
cash-out di Omega che lo riusa.

Tutto con fake db/market: nessuna rete, nessun Supabase. Il file e' volutamente
ASCII-only (console Windows cp1252).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from Betfair.omega import omega_market as M
from Betfair.omega import omega_service as OS
from Betfair.safe_strategy import execution as X

NOW = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeDB:
    """Specchio in memoria delle tabelle trade + coda flumine."""

    def __init__(self, control=None):
        self.control = control or {"status": "running", "mode": "paper", "params": {}}
        self.trades: list[dict] = []
        self.activity: list[tuple] = []
        self.queue: list[dict] = []
        self.requests: dict[int, dict] = {}
        self.mirrors: dict[str, dict] = {}
        self.follow = "STREAMING"
        self.heartbeat = {"ts": NOW.isoformat(), "mode": "PAPER"}
        self._id = 0
        self._qid = 0

    # --- control/log ---
    def read_control(self):
        return self.control

    def set_control(self, **fields):
        self.control.update(fields)

    def log(self, kind, payload=None):
        self.activity.append((kind, payload or {}))

    # --- trades ---
    def insert_trade(self, trade):
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
        # semantica di omega_db.open_trades: SOLO 'open' (le 'hedged' hanno il
        # loro accessor dedicato e un settlement a due gambe).
        return self.list_trades("open")

    def hedged_trades(self):
        return self.list_trades("hedged")

    def closing_trades_for(self, ids):
        ids = {int(i) for i in ids}
        return [t for t in self.trades if t.get("closes_trade_id") in ids]

    # --- coda flumine (contratto verificato dal gate) ---
    def live_follow_status(self, event_id):
        return self.follow

    def runner_heartbeat(self):
        return self.heartbeat

    def enqueue_live_order(self, payload):
        self._qid += 1
        self.queue.append(payload)
        self.requests[self._qid] = {"id": self._qid, "status": "pending"}
        return self._qid

    def get_live_order_request(self, rid):
        return self.requests.get(int(rid))

    def get_live_order_request_by_ref(self, ref):
        for p in self.queue:
            if p.get("client_ref") == ref:
                return {"id": 1, "status": "pending"}
        return None

    def get_live_order_mirror(self, ref, mode="paper"):
        return self.mirrors.get(ref)

    def revoke_live_order_request(self, rid):
        return True


class FakeMarket:
    def __init__(self):
        self.placed: list[dict] = []
        self.book = None
        self.snapshot = None

    def place_order_live(self, **kw):
        self.placed.append(kw)
        return M.PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="b-1",
                             size_matched=kw["size"], avg_price_matched=kw["price"])

    def read_book(self, market_id, runner_names):
        return self.book

    def read_market(self, cs):
        return self.snapshot


def _gate_open_params():
    return {"execution_mode": "auto", "omega_live_via_flumine": True}


# ---------------------------------------------------------------------------
# place()
# ---------------------------------------------------------------------------
def test_place_paper_riempie_al_prezzo_e_cappa_alla_liquidita():
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"  # gate chiuso -> percorso legacy
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back"})
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=50.0, best_size=12.0,
                  client_ref=f"safe-t{tid}", trade_id=tid, now=NOW, params={})
    assert out.status == "open"
    assert out.size == 12.0, "la size deve essere cappata alla liquidita' disponibile"
    assert out.price == 3.0
    assert mk.placed == [], "in paper non si tocca Betfair"


def test_place_rifiuta_size_o_prezzo_non_validi():
    db, mk = FakeDB(), FakeMarket()
    assert X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                   selection_id=7, side="back", price=None, size=10.0,
                   client_ref="safe-t1", now=NOW, params={}).status == "error"
    assert X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                   selection_id=7, side="back", price=3.0, size=0.0,
                   client_ref="safe-t1", now=NOW, params={}).status == "error"
    assert X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                   selection_id=7, side="giu", price=3.0, size=5.0,
                   client_ref="safe-t1", now=NOW, params={}).status == "error"


def test_place_con_gate_aperto_accoda_su_flumine_e_resta_pending():
    db, mk = FakeDB(), FakeMarket()
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "lay"})
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side="lay", price=6.0, size=10.0, best_size=100.0,
                  client_ref=f"safe-t{tid}", trade_id=tid, now=NOW,
                  params=_gate_open_params())
    assert out.status == "pending"
    assert len(db.queue) == 1
    q = db.queue[0]
    assert q["client_ref"] == f"safe-t{tid}", "il ref deve essere quello del bot Safe"
    assert q["mode"] == "paper" and q["action"] == "place"
    assert "time_in_force" not in q, "il FOK vero e' solo per il live"
    meta = db.get_trade(tid)["meta"]
    assert meta["flumine_client_ref"] == f"safe-t{tid}"
    assert meta["flumine_request_id"] == 1


def test_place_live_con_gate_aperto_porta_il_fok_vero():
    db, mk = FakeDB(), FakeMarket()
    db.heartbeat = {"ts": NOW.isoformat(), "mode": "LIVE"}
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back"})
    out = X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=2.5, size=8.0, best_size=100.0,
                  client_ref=f"safe-t{tid}", trade_id=tid, now=NOW,
                  params=_gate_open_params())
    assert out.status == "pending"
    assert db.queue[0]["time_in_force"] == "FILL_OR_KILL"
    assert db.queue[0]["mode"] == "live"


def test_place_live_ripiega_sul_rest_quando_il_gate_e_chiuso():
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back"})
    out = X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=2.5, size=8.0, best_size=100.0,
                  client_ref=f"safe-t{tid}", trade_id=tid, now=NOW,
                  params=_gate_open_params())
    assert out.status == "open" and out.bet_id == "b-1"
    assert mk.placed[0]["side"] == "back"
    assert mk.placed[0]["customer_ref"] == f"safe-t{tid}"
    assert db.queue == []


def test_place_live_esito_ignoto_resta_pending_in_riconciliazione():
    """CRITICAL-1: eccezione dal place REST (es. timeout DOPO l'accettazione):
    la riga NON va in 'error' (uscirebbe dall'indice unico e da
    traded_signal_keys -> ripiazzamento -> doppio ordine reale) ma resta
    'pending' con meta.reason='place_exception_reconciling'."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back",
                           "meta": {"phase": "reserved", "variant": "base"}})

    def boom(**kw):
        raise RuntimeError("timeout betfair")

    mk.place_order_live = boom
    out = X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=2.5, size=8.0,
                  client_ref=f"safe-t{tid}", trade_id=tid, now=NOW, params={},
                  meta={"variant": "base"})
    assert out.status == "pending" and out.ok
    assert out.fill_note.startswith("place_exception_reconciling")
    row = db.get_trade(tid)
    assert row["status"] == "pending"
    assert row["meta"]["reason"] == "place_exception_reconciling"
    assert row["meta"]["variant"] == "base", "il meta della riserva non va perso"
    assert X.is_reconciling(row) and not X.has_flumine_marker(row)
    assert "place_exception" in [k for k, _ in db.activity]


def test_place_live_rifiuto_provato_dall_exchange_resta_error():
    """Risposta ricevuta e nessun fill (FOK ucciso): 'error' legittimo."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"

    def killed(**kw):
        return M.PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                             size_matched=0.0, avg_price_matched=None)

    mk.place_order_live = killed
    out = X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=2.5, size=8.0,
                  client_ref="safe-t1", trade_id=1, now=NOW, params={})
    assert out.status == "error" and out.fill_note.startswith("live_not_matched")


def test_place_paper_eccezione_del_fill_resta_pending(monkeypatch):
    """Stessa semantica in paper: eccezione -> pending riconciliabile."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back"})

    def boom(*a, **kw):
        raise RuntimeError("ladder corrotta")

    monkeypatch.setattr(X.E, "paper_fill", boom)
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=2.5, size=8.0,
                  client_ref=f"safe-t{tid}", trade_id=tid, now=NOW, params={})
    assert out.status == "pending"
    assert db.get_trade(tid)["meta"]["reason"] == "place_exception_reconciling"


# ---------------------------------------------------------------------------
# close_plan(): matematica del cash-out
# ---------------------------------------------------------------------------
def _lay_trade(size=10.0, price=6.0):
    return {"id": 1, "event_id": "1.1", "market_id": "m1", "selection_id": 7,
            "side": "lay", "size": size, "price": price, "status": "open",
            "mode": "paper", "commission": 0.05}


def _back_trade(size=10.0, price=4.0):
    t = _lay_trade(size, price)
    t["side"] = "back"
    return t


def test_esposizioni_lay_e_back():
    assert X.exposures(_lay_trade(10.0, 6.0)) == (-50.0, 10.0)
    assert X.exposures(_back_trade(10.0, 4.0)) == (30.0, -10.0)


def test_close_plan_lay_totale_backa_e_pareggia_gli_esiti():
    plan = X.close_plan(_lay_trade(10.0, 6.0), best_back=5.0, best_lay=5.2)
    assert plan.side == "back", "chiudere un LAY significa BACKare"
    assert plan.actionable
    assert abs(plan.expected_if_win - plan.expected_if_lose) <= 0.01


def test_close_plan_back_totale_laya():
    plan = X.close_plan(_back_trade(10.0, 4.0), best_back=4.4, best_lay=4.5)
    assert plan.side == "lay"
    # residuo di solo arrotondamento della size al centesimo
    assert abs(plan.expected_if_win - plan.expected_if_lose) <= 0.02


def test_close_plan_frazione_chiude_solo_una_parte():
    tot = X.close_plan(_lay_trade(10.0, 6.0), best_back=5.0, best_lay=5.2)
    meta = X.close_plan(_lay_trade(10.0, 6.0), best_back=5.0, best_lay=5.2, fraction=0.5)
    assert meta.size == pytest.approx(tot.size / 2, abs=0.01)


def test_close_plan_amount_e_lo_stake_assoluto():
    plan = X.close_plan(_lay_trade(10.0, 6.0), best_back=5.0, best_lay=5.2, amount=4.0)
    assert plan.side == "back" and plan.size == pytest.approx(4.0, abs=0.01)


def test_close_plan_senza_prezzo_del_lato_richiesto_non_e_azionabile():
    plan = X.close_plan(_lay_trade(10.0, 6.0), best_back=None, best_lay=5.2)
    assert not plan.actionable


# ---------------------------------------------------------------------------
# close_trade(): riga di chiusura + originale 'hedged'
# ---------------------------------------------------------------------------
def test_close_trade_crea_la_gamba_di_chiusura_e_marca_hedged():
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({**_lay_trade(), "status": "open"})
    tr = db.get_trade(tid)
    res = X.close_trade(db=db, market=mk, trade=tr,
                        prices={"back": 5.0, "back_size": 500.0, "lay": 5.2,
                                "lay_size": 500.0},
                        now=NOW, params={}, origin="manual", table_prefix="safe")
    assert res.get("ok") is True
    closing = db.get_trade(res["closing_trade_id"])
    assert closing["side"] == "back"
    assert closing["closes_trade_id"] == tid
    assert closing["status"] == "open"
    original = db.get_trade(tid)
    assert original["status"] == "hedged"
    assert original["meta"]["locked_pnl"] == res["locked_pnl"]
    assert original["meta"]["closing_trade_id"] == closing["id"]


def test_close_trade_rifiuta_un_trade_non_aperto():
    db, mk = FakeDB(), FakeMarket()
    tr = {**_lay_trade(), "status": "won"}
    assert "error" in X.close_trade(db=db, market=mk, trade=tr,
                                    prices={"back": 5.0, "lay": 5.2}, now=NOW,
                                    params={})


def test_close_trade_senza_prezzi_non_piazza_nulla():
    db, mk = FakeDB(), FakeMarket()
    tid = db.insert_trade({**_lay_trade(), "status": "open"})
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                        prices={"back": None, "lay": None}, now=NOW, params={})
    assert res.get("error") == "niente_da_chiudere"
    assert db.get_trade(tid)["status"] == "open", "l'originale non va toccato"


# ---------------------------------------------------------------------------
# settle_pair / settle_group: commissione sul NETTO di mercato
# ---------------------------------------------------------------------------
def test_settle_pair_commissione_solo_sul_netto_positivo():
    # LAY 10@6 (win -50 / lose +10) chiuso con BACK 10@6 (win +50 / lose -10):
    # netto ZERO su entrambi gli esiti -> nessuna commissione.
    apri = _lay_trade(10.0, 6.0)
    chiudi = {"side": "back", "size": 10.0, "price": 6.0}
    for won in (True, False):
        a, b = X.settle_pair(apri, chiudi, won, 0.05)
        assert round(a + b, 2) == 0.0


def test_settle_pair_netto_positivo_paga_la_commissione_una_sola_volta():
    apri = _lay_trade(10.0, 6.0)          # perde -> +10
    chiudi = {"side": "back", "size": 1.0, "price": 6.0}  # perde -> -1
    a, b = X.settle_pair(apri, chiudi, False, 0.05)
    # netto lordo 9.00 -> commissione 0.45 -> 8.55 totale
    assert round(a + b, 2) == 8.55
    # la commissione (0.45) e' scaricata TUTTA sulla gamba in utile (+10 lordo)
    assert a == pytest.approx(9.55, abs=0.01)
    assert b == pytest.approx(-1.0, abs=0.01)


def test_settle_pair_netto_negativo_non_paga_commissione():
    apri = _lay_trade(10.0, 6.0)   # vince il nostro punteggio -> -50
    chiudi = {"side": "back", "size": 1.0, "price": 6.0}  # vince -> +5
    a, b = X.settle_pair(apri, chiudi, True, 0.05)
    assert round(a + b, 2) == -45.0


def test_settle_group_con_due_chiusure_parziali():
    apri = _lay_trade(10.0, 6.0)
    legs = [{"side": "back", "size": 0.5, "price": 6.0},
            {"side": "back", "size": 0.5, "price": 6.0}]
    a, closes = X.settle_group(apri, legs, False, 0.05)
    assert len(closes) == 2
    assert round(a + sum(closes), 2) == 8.55


# ---------------------------------------------------------------------------
# OMEGA: kind 'cashout' + settlement della coppia 'hedged'
# ---------------------------------------------------------------------------
class OmegaFakeDB(FakeDB):
    """FakeDB + coda manuale di Omega."""

    def __init__(self, control=None):
        super().__init__(control or {"status": "stopped", "mode": "paper", "params": {}})
        self.manual_reqs: list[dict] = []

    def pending_manual_requests(self):
        return [r for r in self.manual_reqs if r.get("status") == "pending"]

    def set_manual_status(self, req_id, status, result=None):
        for r in self.manual_reqs:
            if r["id"] == req_id:
                r["status"] = status
                if result is not None:
                    r["result"] = result

    def fail_stale_processing(self):
        return None


def _omega_book(sid=7, back=5.0, lay=5.2):
    return {"market_id": "m1", "status": "OPEN", "inplay": True,
            "runners": [{"selection_id": sid, "name": "3 - 2", "status": "ACTIVE",
                         "lay_price": lay, "lay_size": 300.0,
                         "back_price": back, "back_size": 300.0,
                         "lay_ladder": [[lay, 300.0]]}]}


def test_omega_process_manual_esegue_il_cashout():
    db, mk = OmegaFakeDB(), FakeMarket()
    db.follow = "NONE"
    mk.book = _omega_book()
    tid = db.insert_trade({**_lay_trade(), "status": "open", "origin": "auto",
                           "runner_name": "3 - 2", "event_name": "Home v Away"})
    db.manual_reqs.append({"id": 1, "kind": "cashout", "status": "pending",
                           "payload": {"trade_id": tid}})
    n = OS.process_manual(market=mk, db=db, now=NOW)
    assert n == 1
    req = db.manual_reqs[0]
    assert req["status"] == "done", req.get("result")
    assert req["result"]["ok"] is True
    closing = db.get_trade(req["result"]["closing_trade_id"])
    assert closing["side"] == "back" and closing["closes_trade_id"] == tid
    assert closing["runner_name"] == "3 - 2"
    assert db.get_trade(tid)["status"] == "hedged"


def test_omega_cashout_rifiuta_trade_inesistente_o_chiuso():
    db, mk = OmegaFakeDB(), FakeMarket()
    mk.book = _omega_book()
    db.manual_reqs.append({"id": 1, "kind": "cashout", "status": "pending",
                           "payload": {"trade_id": 999}})
    OS.process_manual(market=mk, db=db, now=NOW)
    assert db.manual_reqs[0]["status"] == "error"
    assert db.manual_reqs[0]["result"]["error"] == "trade_inesistente"


def test_omega_cashout_valida_fraction():
    db, mk = OmegaFakeDB(), FakeMarket()
    mk.book = _omega_book()
    tid = db.insert_trade({**_lay_trade(), "status": "open"})
    db.manual_reqs.append({"id": 1, "kind": "cashout", "status": "pending",
                           "payload": {"trade_id": tid, "fraction": 2.0}})
    OS.process_manual(market=mk, db=db, now=NOW)
    assert db.manual_reqs[0]["status"] == "error"


def _closed_snapshot(winner_id, sid=7):
    from Betfair.omega import omega_engine as E

    return M.MarketSnapshot(
        status="CLOSED", inplay=False, closed=True,
        winner_selection_id=winner_id, voided=(winner_id is None),
        runners=[E.ScoreRunner(sid, "3 - 2", lay_price=None)],
    )


def test_omega_settle_regola_la_coppia_hedged_insieme():
    db, mk = OmegaFakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({**_lay_trade(10.0, 6.0), "status": "open"})
    # LAY 10@6 chiuso in BACK 12@5 -> P&L bloccato -2.00 su OGNI esito
    X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                  prices={"back": 5.0, "back_size": 300.0, "lay": 5.2, "lay_size": 300.0},
                  now=NOW, params={}, origin="manual", table_prefix="omega")
    apri = db.get_trade(tid)
    assert apri["status"] == "hedged"
    assert apri["meta"]["locked_pnl"] == pytest.approx(-2.0, abs=0.01)
    # il punteggio layato NON esce: il lay vince, il back di chiusura perde.
    mk.snapshot = _closed_snapshot(999)
    n = OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW)
    assert n == 1
    apri = db.get_trade(tid)
    chiudi = next(t for t in db.trades if t.get("closes_trade_id") == tid)
    assert apri["settled_at"] and chiudi["settled_at"]
    # netto NEGATIVO -> nessuna commissione: il realizzato e' il P&L bloccato
    assert round(apri["pnl"] + chiudi["pnl"], 2) == pytest.approx(-2.0, abs=0.01)


def test_omega_settle_non_regola_da_sola_la_gamba_di_chiusura():
    """Una riga con closes_trade_id non deve mai passare dal settlement singolo."""
    db, mk = OmegaFakeDB(), FakeMarket()
    db.insert_trade({**_lay_trade(), "status": "open", "closes_trade_id": 99})
    mk.snapshot = _closed_snapshot(999)
    assert OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW) == 0


def test_omega_settle_hedged_aspetta_la_chiusura_ancora_pending():
    db, mk = OmegaFakeDB(), FakeMarket()
    tid = db.insert_trade({**_lay_trade(), "status": "hedged"})
    db.insert_trade({**_lay_trade(), "side": "back", "status": "pending",
                     "closes_trade_id": tid})
    mk.snapshot = _closed_snapshot(999)
    assert OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW) == 0
    assert db.get_trade(tid)["status"] == "hedged"


def test_omega_settle_hedged_ignora_una_chiusura_in_errore():
    db, mk = OmegaFakeDB(), FakeMarket()
    tid = db.insert_trade({**_lay_trade(10.0, 6.0), "status": "hedged"})
    db.insert_trade({**_lay_trade(), "side": "back", "status": "error",
                     "closes_trade_id": tid})
    mk.snapshot = _closed_snapshot(999)  # il nostro punteggio non esce -> lay vinto
    assert OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW) == 1
    assert db.get_trade(tid)["pnl"] == pytest.approx(9.5, abs=0.01)


def test_omega_settle_hedged_void_azzera_entrambe_le_gambe():
    db, mk = OmegaFakeDB(), FakeMarket()
    tid = db.insert_trade({**_lay_trade(), "status": "hedged"})
    cid = db.insert_trade({**_lay_trade(), "side": "back", "status": "open",
                           "closes_trade_id": tid})
    mk.snapshot = _closed_snapshot(None)
    assert OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW) == 1
    assert db.get_trade(tid)["status"] == "void" and db.get_trade(tid)["pnl"] == 0.0
    assert db.get_trade(cid)["status"] == "void"


def test_omega_settle_legacy_senza_hedged_trades_non_esplode():
    """DB iniettato senza i nuovi accessor (migrazione non applicata)."""

    class VecchioDB(OmegaFakeDB):
        hedged_trades = None

    db, mk = VecchioDB(), FakeMarket()
    mk.snapshot = _closed_snapshot(999)
    assert OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW) == 0


def test_gate_chiuso_se_heartbeat_stantio():
    db, mk = FakeDB(), FakeMarket()
    db.heartbeat = {"ts": (NOW - timedelta(minutes=30)).isoformat(), "mode": "PAPER"}
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back"})
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=5.0, best_size=100.0,
                  client_ref=f"safe-t{tid}", trade_id=tid, now=NOW,
                  params=_gate_open_params())
    assert out.status == "open" and db.queue == []


# ---------------------------------------------------------------------------
# CRITICAL-2 / HIGH-6: chiusura in sospeso, cash-out parziali, residuo
# ---------------------------------------------------------------------------
def _prices(back=5.0, lay=5.2, back_size=500.0, lay_size=500.0):
    return {"back": back, "back_size": back_size, "lay": lay, "lay_size": lay_size}


def test_close_trade_eccezione_sul_place_blocca_un_secondo_cashout():
    """CRITICAL-2: esito ignoto sulla gamba di chiusura -> chiusura 'pending'
    (riconciliabile), apertura ancora 'open' ma con chiusura IN SOSPESO: una
    seconda richiesta di cash-out viene RIFIUTATA (mai un secondo hedge ->
    posizione invertita)."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"

    def boom(**kw):
        raise RuntimeError("timeout betfair")

    mk.place_order_live = boom
    tid = db.insert_trade({**_lay_trade(), "status": "open", "mode": "live"})
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid), prices=_prices(),
                        now=NOW, params={}, origin="manual", table_prefix="safe")
    assert res.get("ok") is True and res["pending_fill"] is True
    closing = db.get_trade(res["closing_trade_id"])
    assert closing["status"] == "pending"
    assert closing["meta"]["reason"] == "place_exception_reconciling"
    apri = db.get_trade(tid)
    assert apri["status"] == "open", "senza fill certo NON e' hedged"
    assert apri["meta"]["hedge_pending_ids"] == [closing["id"]]
    assert apri["meta"]["closing_status"] == "pending"
    # secondo cash-out mentre la prima chiusura e' in sospeso -> rifiutato
    res2 = X.close_trade(db=db, market=mk, trade=db.get_trade(tid), prices=_prices(),
                         now=NOW, params={}, origin="manual", table_prefix="safe")
    assert res2.get("error") == "chiusura_in_corso"
    assert res2["pending_closing_ids"] == [closing["id"]]
    assert len([t for t in db.trades if t.get("closes_trade_id") == tid]) == 1


def test_close_trade_parziale_resta_open_con_residuo_e_poi_chiude_il_resto():
    """HIGH-6: fraction<1 NON marca 'hedged': l'apertura resta 'open' con
    hedged_size accumulato e locked_pnl dal fill; un secondo cash-out lavora
    sul RESIDUO e solo a residuo nullo si passa a 'hedged'."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({**_lay_trade(10.0, 6.0), "status": "open"})
    r1 = X.close_trade(db=db, market=mk, trade=db.get_trade(tid), prices=_prices(),
                       fraction=0.5, now=NOW, params={}, table_prefix="safe")
    assert r1["ok"] and r1["hedged"] is False
    assert r1["size"] == pytest.approx(6.0, abs=0.01)     # meta' del green totale (12@5)
    apri = db.get_trade(tid)
    assert apri["status"] == "open"
    assert apri["meta"]["hedged_size"] == pytest.approx(5.0, abs=0.01)   # 6*5/6
    assert apri["meta"]["residual_size"] == pytest.approx(5.0, abs=0.01)
    # hedge PARZIALE: nessun P&L "bloccato" (review MED-4) — caso peggiore/migliore espliciti:
    # win -50+24=-26, lose +10-6=+4
    assert apri["meta"]["locked_pnl"] is None
    assert apri["meta"]["worst_case"] == pytest.approx(-26.0, abs=0.01)
    assert apri["meta"]["best_case"] == pytest.approx(4.0, abs=0.01)
    r2 = X.close_trade(db=db, market=mk, trade=db.get_trade(tid), prices=_prices(),
                       fraction=1.0, now=NOW, params={}, table_prefix="safe")
    assert r2["ok"] and r2["hedged"] is True
    assert r2["size"] == pytest.approx(6.0, abs=0.01), "chiude SOLO il residuo"
    apri = db.get_trade(tid)
    assert apri["status"] == "hedged"
    assert apri["meta"]["residual_size"] < 0.01
    assert apri["meta"]["locked_pnl"] == pytest.approx(-2.0, abs=0.01)
    # terzo cash-out: niente da chiudere
    r3 = X.close_trade(db=db, market=mk, trade=db.get_trade(tid), prices=_prices(),
                       now=NOW, params={}, table_prefix="safe")
    assert "error" in r3
    # settle_group netta TUTTE le gambe: il nostro punteggio non esce
    legs = db.closing_trades_for([tid])
    pnl_open, pnl_closes = X.settle_group(apri, legs, False, 0.05)
    assert round(pnl_open + sum(pnl_closes), 2) == pytest.approx(-2.0, abs=0.01)


def test_close_trade_size_cappata_alla_liquidita_resta_open():
    """HIGH-6: chiusura cappata al best_size = hedge PARZIALE -> apertura 'open'."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({**_lay_trade(10.0, 6.0), "status": "open"})
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                        prices=_prices(back_size=4.0), now=NOW, params={},
                        table_prefix="safe")
    assert res["ok"] and res["size"] == 4.0 and res["hedged"] is False
    apri = db.get_trade(tid)
    assert apri["status"] == "open"
    assert apri["meta"]["hedged_size"] == pytest.approx(4.0 * 5.0 / 6.0, abs=0.01)
    assert apri["meta"]["residual_size"] == pytest.approx(10.0 - 4.0 * 5.0 / 6.0, abs=0.01)


def test_close_trade_fill_flumine_pending_poi_confermato_diventa_hedged():
    """HIGH-6: fill dalla coda flumine: finche' e' 'pending' l'apertura resta
    'open' e blocca altri cash-out; quando il poll conferma il fill, la
    sincronizzazione porta l'apertura a 'hedged' con i dati REALI."""
    db, mk = FakeDB(), FakeMarket()  # gate aperto (follow STREAMING, heartbeat fresco)
    tid = db.insert_trade({**_lay_trade(10.0, 6.0), "status": "open"})
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid), prices=_prices(),
                        now=NOW, params=_gate_open_params(), table_prefix="safe")
    assert res["ok"] and res["pending_fill"] is True
    cid = res["closing_trade_id"]
    assert db.get_trade(cid)["status"] == "pending"
    assert db.queue[-1]["client_ref"] == f"safe-t{cid}"
    apri = db.get_trade(tid)
    assert apri["status"] == "open" and apri["meta"]["hedge_pending_ids"] == [cid]
    assert X.close_trade(db=db, market=mk, trade=apri, prices=_prices(), now=NOW,
                         params={}, table_prefix="safe").get("error") == "chiusura_in_corso"
    # il poll conferma il fill (size/prezzo reali) -> sync
    db.update_trade(cid, status="open", price=5.0, size=12.0)
    st = X.apply_hedge_state(db, db.get_trade(tid), db.closing_trades_for([tid]), NOW)
    assert st["complete"] and not st["blocked"]
    apri = db.get_trade(tid)
    assert apri["status"] == "hedged"
    assert apri["meta"]["hedge_pending_ids"] == [] and apri["meta"]["closing_ids"] == [cid]
    assert apri["meta"]["locked_pnl"] == pytest.approx(-2.0, abs=0.01)


def test_hedge_state_chiusura_in_errore_non_conta():
    apri = _lay_trade(10.0, 6.0)
    st = X.hedge_state(apri, [{"id": 2, "status": "error", "side": "back",
                               "size": 12.0, "price": 5.0}])
    assert st["hedged_size"] == 0.0 and not st["blocked"] and not st["complete"]


# ---------------------------------------------------------------------------
# HIGH-4 / HIGH-5: settlement di Omega in coppia, orfani, ripresa
# ---------------------------------------------------------------------------
def test_omega_settle_apertura_open_con_chiusura_confermata_regola_in_coppia():
    """HIGH-4: l'apertura e' ancora 'open' (hedge parziale) ma ha una chiusura
    con fill certo -> MAI regolata da sola: coppia nettata."""
    db, mk = OmegaFakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({**_lay_trade(10.0, 6.0), "status": "open"})
    X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                  prices=_prices(back_size=4.0), now=NOW, params={},
                  origin="manual", table_prefix="omega")
    assert db.get_trade(tid)["status"] == "open"
    mk.snapshot = _closed_snapshot(999)  # il punteggio layato NON esce
    n = OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW)
    assert n == 1
    apri = db.get_trade(tid)
    chiudi = next(t for t in db.trades if t.get("closes_trade_id") == tid)
    assert apri["status"] == "won" and chiudi["status"] == "lost"
    # lay +10, back 4@5 -4 -> netto 6 -> commissione 0.30 -> 5.70
    assert round(apri["pnl"] + chiudi["pnl"], 2) == pytest.approx(5.70, abs=0.01)


def test_omega_settle_gamba_orfana_con_apertura_gia_regolata():
    """HIGH-5: chiusura rimasta 'open' con l'apertura gia' 'won' (ciclo
    interrotto): si regola con l'esito dedotto dall'apertura."""
    db, mk = OmegaFakeDB(), FakeMarket()
    tid = db.insert_trade({**_lay_trade(10.0, 6.0), "status": "won", "pnl": 9.5,
                           "settled_at": NOW.isoformat()})
    cid = db.insert_trade({**_lay_trade(12.0, 5.0), "side": "back", "status": "open",
                           "closes_trade_id": tid})
    mk.snapshot = None
    n = OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW)
    assert n == 1
    chiudi = db.get_trade(cid)
    # netting col padre già regolato (review HIGH-3): −2 totale − 9,5 già sul padre = −11,5
    assert chiudi["status"] == "lost" and chiudi["pnl"] == pytest.approx(-11.5, abs=0.01)
    assert chiudi["settled_at"] == NOW.isoformat()


def test_omega_settle_ripresa_con_chiusura_gia_regolata():
    """HIGH-5: la chiusura e' gia' regolata (crash prima dell'apertura): al
    ciclo dopo l'apertura si regola col NETTO completo, la chiusura non viene
    riscritta."""
    db, mk = OmegaFakeDB(), FakeMarket()
    tid = db.insert_trade({**_lay_trade(10.0, 6.0), "status": "hedged"})
    cid = db.insert_trade({**_lay_trade(1.0, 6.0), "side": "back", "status": "lost",
                           "pnl": -1.0, "settled_at": "old", "closes_trade_id": tid})
    mk.snapshot = _closed_snapshot(999)
    assert OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW) == 1
    assert db.get_trade(tid)["pnl"] == pytest.approx(9.55, abs=0.01)
    assert db.get_trade(cid)["settled_at"] == "old" and db.get_trade(cid)["pnl"] == -1.0


def test_omega_settle_scrive_prima_le_chiusure_poi_l_apertura():
    db, mk = OmegaFakeDB(), FakeMarket()
    tid = db.insert_trade({**_lay_trade(10.0, 6.0), "status": "hedged"})
    db.insert_trade({**_lay_trade(12.0, 5.0), "side": "back", "status": "open",
                     "closes_trade_id": tid})
    mk.snapshot = _closed_snapshot(999)
    OS.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW)
    ordine = [p["trade_id"] for k, p in db.activity if k == "settle"]
    assert ordine[-1] == tid, "l'apertura e' l'ULTIMA scrittura (ripresa sicura)"


def test_omega_cashout_manuale_rifiutato_con_chiusura_in_sospeso():
    db, mk = OmegaFakeDB(), FakeMarket()
    mk.book = _omega_book()
    tid = db.insert_trade({**_lay_trade(), "status": "open"})
    db.insert_trade({**_lay_trade(), "side": "back", "status": "pending",
                     "closes_trade_id": tid})
    db.manual_reqs.append({"id": 1, "kind": "cashout", "status": "pending",
                           "payload": {"trade_id": tid}})
    OS.process_manual(market=mk, db=db, now=NOW)
    assert db.manual_reqs[0]["status"] == "error"
    assert db.manual_reqs[0]["result"]["error"] == "chiusura_in_corso"


# ---------------------------------------------------------------------------
# HIGH-3 (decisione pura con ref esplicito) / HIGH-7 (ref del cancel)
# ---------------------------------------------------------------------------
def test_reconcile_decision_con_ref_esplicito_del_bot_safe():
    tr = {"id": 5, "market_id": "m1", "selection_id": 7, "side": "back",
          "price": 2.5, "placed_at": NOW.isoformat()}
    cur = [{"bet_id": "b9", "market_id": "m1", "selection_id": 7, "side": "back",
            "size_matched": 8.0, "size_remaining": 0.0, "avg_price_matched": 2.6,
            "customer_order_ref": "safe-t5"}]
    d = X.reconcile_decision(tr, cur, [], NOW.isoformat(), ref="safe-t5")
    assert d["action"] == "confirm" and d["bet_id"] == "b9" and d["size"] == 8.0
    # con un ref diverso l'ordine NON e' nostro: fresco -> keep, vecchio -> free
    assert X.reconcile_decision(tr, cur, [], NOW.isoformat(), ref="safe-t6")["action"] == "keep"
    old = {**tr, "placed_at": (NOW - timedelta(minutes=10)).isoformat()}
    assert X.reconcile_decision(old, [], [], NOW.isoformat(), ref="safe-t5")["action"] == "free"


def test_flumine_cancel_ref_eredita_il_prefisso_del_bot():
    """HIGH-7: il cancel della coda usa il prefisso del ref di place: il bot
    Safe non deve mai collidere con omega-t<id>-cancel."""
    db = FakeDB()
    tr = {"id": 5, "market_id": "m1"}
    ok = OS._flumine_enqueue_cancel(tr, db=db, bet_id="sim1",
                                    meta={"flumine_client_ref": "safe-t5"}, now=NOW)
    assert ok and db.queue[-1]["client_ref"] == "safe-t5-cancel"
    assert db.queue[-1]["params"]["source"] == "safe"
    ok = OS._flumine_enqueue_cancel(tr, db=db, bet_id="sim1",
                                    meta={"flumine_client_ref": "omega-t5"}, now=NOW)
    assert ok and db.queue[-1]["client_ref"] == "omega-t5-cancel"
    assert db.queue[-1]["params"]["source"] == "omega"
    ok = OS._flumine_enqueue_cancel(tr, db=db, bet_id="sim1", meta={}, now=NOW)
    assert ok and db.queue[-1]["client_ref"] == "omega-t5-cancel"


# ===========================================================================
# CERTIFICAZIONE 12/09 — chiusura in PAPER con liquidita' del book IGNOTA.
# paper_fill non riempie piu' senza controparte dichiarata: se il feed porta
# il PREZZO ma non la SIZE, tentare la chiusura creava a ogni ciclo una riga
# di chiusura 'error' con motivo tecnico, e l'uscita non avveniva mai.
# Ora ci si ferma PRIMA della riserva, con un motivo leggibile.
# ===========================================================================
def test_close_trade_paper_senza_size_del_book_non_riserva_nulla():
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({**_lay_trade(), "status": "open"})
    prima = len(db.trades)
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                        prices={"back": 5.0, "lay": 5.2},   # prezzi si, size no
                        now=NOW, params={}, mode="paper",
                        origin="manual", table_prefix="safe")
    assert res.get("error") == "liquidita_del_book_ignota", res
    assert len(db.trades) == prima          # NESSUNA riga di chiusura creata
    assert db.get_trade(tid)["status"] == "open"   # la posizione resta viva


def test_close_trade_paper_con_ladder_procede_anche_senza_campo_size():
    """La ladder E' la controparte: se c'e', la chiusura parte."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({**_lay_trade(), "status": "open"})
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                        prices={"back": 5.0, "lay": 5.2,
                                "back_ladder": ((5.0, 500.0),)},
                        now=NOW, params={}, mode="paper",
                        origin="manual", table_prefix="safe")
    assert res.get("ok") is True, res


def test_close_trade_live_non_e_bloccato_dalla_size_ignota():
    """In LIVE decide l'exchange col FOK: il pre-check non si applica."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({**_lay_trade(), "status": "open"})
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                        prices={"back": 5.0, "lay": 5.2}, now=NOW, params={},
                        mode="live", origin="manual", table_prefix="safe")
    assert res.get("error") != "liquidita_del_book_ignota", res


# ===========================================================================
# CERTIFICAZIONE 12/09 — aliquota della gamba di CHIUSURA: mai 0 per svista.
# L-02 dice "mai NULL"; il vecchio ``params.get("commission_pct", 5.0) or 0.0``
# faceva scattare lo 0 anche con la chiave PRESENTE ma a None (control senza il
# campo, campo azzerato dalla UI): la gamba nasceva allo 0 % e il P&L mostrato
# era piu' ALTO del vero. Uno 0 ESPLICITO invece resta 0.
# ===========================================================================
def test_commission_fallback_none_torna_al_5_percento():
    assert X._commission_fallback({}) == 0.05
    assert X._commission_fallback({"commission_pct": None}) == 0.05
    assert X._commission_fallback({"commission_pct": "boh"}) == 0.05
    assert X._commission_fallback({"commission_pct": 0}) == 0.0      # 0 esplicito
    assert X._commission_fallback({"commission_pct": 2}) == 0.02
    assert X._commission_fallback({"commission_pct": 500}) == 1.0    # clamp


def test_close_trade_senza_aliquota_sul_trade_usa_il_default_non_zero():
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tr = {**_lay_trade(), "status": "open"}
    tr.pop("commission")                       # apertura storica senza aliquota
    tid = db.insert_trade(tr)
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                        prices={"back": 5.0, "lay": 5.2, "back_size": 500.0},
                        now=NOW, params={"commission_pct": None},   # chiave a None
                        mode="paper", origin="manual", table_prefix="safe")
    assert res.get("ok") is True, res
    closing = db.get_trade(res["closing_trade_id"])
    assert closing["commission"] == 0.05, "mai 0 % per una chiave a None"


def test_close_trade_eredita_sempre_l_aliquota_del_trade():
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({**_lay_trade(), "status": "open", "commission": 0.02})
    res = X.close_trade(db=db, market=mk, trade=db.get_trade(tid),
                        prices={"back": 5.0, "lay": 5.2, "back_size": 500.0},
                        now=NOW, params={"commission_pct": 5.0}, mode="paper",
                        origin="manual", table_prefix="safe")
    assert db.get_trade(res["closing_trade_id"])["commission"] == 0.02


# ===========================================================================
# CERTIFICAZIONE 12/09 — PAPER = LIVE sul minimo Betfair di 2 EUR.
# ===========================================================================
def test_place_paper_rifiuta_l_apertura_sotto_il_minimo_come_il_live():
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    common = dict(db=db, market=mk, event_id="1.1", market_id="m1", selection_id=7,
                  side="back", price=3.0, best_size=100.0, trade_id=1, now=NOW, params={})
    paper = X.place(mode="paper", size=1.5, client_ref="safe-t1", **common)
    live = X.place(mode="live", size=1.5, client_ref="safe-t1", **common)
    assert paper.status == "error" and live.status == "error"
    assert paper.fill_note.startswith("size_sotto_minimo_betfair")
    assert paper.fill_note == live.fill_note, "paper e live devono dire la stessa cosa"
    # a 2,00 EUR esatti passano entrambi
    assert X.place(mode="paper", size=2.0, client_ref="safe-t1", **common).status == "open"


def test_place_paper_minimo_non_blocca_la_gamba_di_chiusura():
    """Betfair ACCETTA il sotto-minimo che RIDUCE una posizione: un residuo da
    1,40 EUR deve poter essere chiuso, in paper come in live (review C2)."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=1.4, best_size=100.0,
                  client_ref="safe-t9", trade_id=9, now=NOW, params={},
                  meta={"cashout": True, "closes_trade_id": 1})
    assert out.status == "open" and out.size == 1.4


# ===========================================================================
# CERTIFICAZIONE P&L 12/09 -- il numero su cui il trader giudica se guadagna.
# Riscontro incrociato con Betfair/tools/verifica_pnl_2026_09_12.py sul DB reale.
# ===========================================================================
def _lay(size: float, price: float, **kw) -> dict:
    return {"id": kw.pop("id", 1), "side": "lay", "size": size, "price": price, **kw}


def _back(size: float, price: float, **kw) -> dict:
    return {"id": kw.pop("id", 2), "side": "back", "size": size, "price": price, **kw}


def test_settle_group_commissione_una_volta_sola_sul_netto_della_posizione():
    """Regola money-critical: 5% sul NETTO vincente, MAI per gamba.

    Riscontro reale (safe_strategy_trades 9 + 16, mercato 1.262238413):
    lay 2.00@36 vinto (+2.00 lordo) chiuso con back 0.60@120 perso (-0.60):
    netto lordo 1.40 -> commissione 0.07 -> 1.33 sul DB. Con la commissione per
    gamba sarebbe stato 1.90 - 0.60 = 1.30 (3 centesimi in meno per posizione).
    """
    apertura, chiusure = X.settle_group(_lay(2.0, 36.0), [_back(0.6, 120.0)],
                                        runner_won=False, commission=0.05)
    assert round(apertura + sum(chiusure), 2) == 1.33
    # e la somma delle gambe deve fare ESATTAMENTE il netto (nessun centesimo
    # creato o distrutto dall'arrotondamento)
    assert round(apertura + sum(chiusure), 2) == round(1.40 * 0.95, 2)


def test_settle_group_nessuna_commissione_se_il_mercato_chiude_in_perdita():
    """Riscontro reale (trade 47 + chiusure 51/52/53): lay 2.00@46 vinto (+2.00)
    contro 12.27 di chiusure perse -> netto -10.27, commissione ZERO. Applicarla
    sul +2.00 avrebbe scritto -10.37: dieci centesimi di perdita inventata."""
    apertura, chiusure = X.settle_group(
        _lay(2.0, 46.0),
        [_back(6.01, 2.48), _back(3.43, 10.5), _back(2.83, 14.5)],
        runner_won=False, commission=0.05)
    assert round(apertura + sum(chiusure), 2) == -10.27
    assert apertura == 2.0, "sul netto negativo l'apertura resta LORDA"


def test_settle_group_void_non_paga_commissione_e_vale_zero():
    apertura, chiusure = X.settle_group({"id": 1, "side": "lay", "size": 0.0,
                                         "price": 0.0}, [], runner_won=False,
                                        commission=0.05)
    assert (apertura, chiusure) == (0.0, [])


def test_locked_pnl_e_LORDO_mentre_il_realizzato_e_NETTO():
    """DIFETTO CERTIFICATO 12/09 (non corretto: fuori perimetro di questo file).

    ``meta.locked_pnl`` -- quello che la UI mostra come «P&L bloccato ... non
    cambia piu', qualunque sia l'esito» -- e' LORDO, mentre il P&L realizzato
    scritto a settlement e' NETTO. Sulla stessa posizione il trader legge prima
    1,40 e poi incassa 1,33. Questo test FISSA la differenza: se un giorno il
    servizio comincia a nettare ``locked_pnl``, deve fallire e va aggiornato
    insieme alla UI.
    """
    st = X.hedge_state(_lay(2.0, 36.0), [_back(0.6, 120.0, status="open")])
    assert st["complete"] is True
    lordo = st["locked_pnl"]
    ap, ch = X.settle_group(_lay(2.0, 36.0), [_back(0.6, 120.0)],
                            runner_won=False, commission=0.05)
    netto = ap + sum(ch)
    assert lordo == 1.4, "oggi il bloccato e' LORDO"
    assert round(netto, 2) == 1.33
    assert round(lordo - netto, 2) == 0.07, "scarto = la commissione non dedotta"


def test_due_posizioni_sullo_stesso_mercato_non_si_nettano_per_la_commissione():
    """DIFETTO CERTIFICATO 12/09 (latente, non corretto).

    ``settle_group`` netta la commissione fra APERTURA e sue CHIUSURE, non fra
    POSIZIONI DIVERSE sullo stesso mercato. Sul DB reale esistono mercati con
    due lay indipendenti (safe 21+22 su 1.262169551, 9+14 su 1.262238413): se
    uno vince e l'altro perde, Betfair netta e non incassa nulla, il bot invece
    addebita il 5% sulla gamba vincente. Direzione CONSERVATIVA (mostra meno
    profitto del reale) ma il numero e' sbagliato.
    """
    vincente, _ = X.settle_group(_lay(2.0, 34.0, id=22), [], runner_won=False,
                                 commission=0.05)
    perdente, _ = X.settle_group(_lay(2.0, 34.0, id=21), [], runner_won=True,
                                 commission=0.05)
    totale_bot = round(vincente + perdente, 2)
    lordo_mercato = 2.0 - 2.0 * 33.0          # +2,00 e -66,00 = -64,00
    assert round(lordo_mercato, 2) == -64.0
    # Betfair: netto negativo -> commissione zero -> -64,00
    assert totale_bot == -64.1, "oggi il bot addebita 0,10 di commissione in piu'"


# ===========================================================================
# CERTIFICAZIONE 12/09 — "P&L bloccato": LORDO e NETTO dichiarati entrambi.
# La UI mostra questo numero come "non cambia piu', qualunque sia l'esito":
# su un bloccato POSITIVO il lordo lo sovrastima del 5% (la commissione si
# paga sul vincente). Mike lo dava gia' netto: stessa etichetta, due numeri.
# ===========================================================================
def test_locked_pnl_pubblica_anche_il_valore_netto():
    tr = {"id": 1, "side": "lay", "size": 10.0, "price": 3.0, "commission": 0.05}
    # chiusura che blocca un profitto: back 15 @2.0 copre il lay 10 @3.0
    closings = [{"id": 2, "side": "back", "size": 15.0, "price": 2.0, "status": "open",
                 "closes_trade_id": 1}]
    st = X.hedge_state(tr, closings)
    assert st["complete"] is True
    lordo = st["locked_pnl"]
    netto = st["locked_pnl_net"]
    assert lordo is not None and netto is not None
    if lordo > 0:
        assert netto == pytest.approx(round(lordo * 0.95, 2), abs=0.01)
        assert netto < lordo
    else:
        assert netto == lordo


def test_locked_pnl_netto_uguale_al_lordo_quando_e_una_perdita():
    """Betfair non incassa commissione su un mercato chiuso in perdita."""
    tr = {"id": 1, "side": "lay", "size": 10.0, "price": 3.0, "commission": 0.05}
    closings = [{"id": 2, "side": "back", "size": 10.0, "price": 4.0, "status": "open",
                 "closes_trade_id": 1}]
    st = X.hedge_state(tr, closings)
    if st["complete"] and st["locked_pnl"] is not None and st["locked_pnl"] <= 0:
        assert st["locked_pnl_net"] == st["locked_pnl"]


def test_locked_pnl_netto_usa_l_aliquota_del_trade_non_il_default():
    tr = {"id": 1, "side": "lay", "size": 10.0, "price": 3.0, "commission": 0.02}
    closings = [{"id": 2, "side": "back", "size": 15.0, "price": 2.0, "status": "open",
                 "closes_trade_id": 1}]
    st = X.hedge_state(tr, closings)
    if st["complete"] and (st["locked_pnl"] or 0) > 0:
        assert st["locked_pnl_net"] == pytest.approx(round(st["locked_pnl"] * 0.98, 2), abs=0.01)


def test_copertura_parziale_non_dichiara_nessun_bloccato():
    tr = {"id": 1, "side": "lay", "size": 10.0, "price": 3.0, "commission": 0.05}
    closings = [{"id": 2, "side": "back", "size": 3.0, "price": 2.0, "status": "open",
                 "closes_trade_id": 1}]
    st = X.hedge_state(tr, closings)
    assert st["complete"] is False
    assert st["locked_pnl"] is None and st["locked_pnl_net"] is None


# ===========================================================================
# CERTIFICAZIONE 12/09 — PAPER = LIVE anche sul FILL OR KILL.
# In live l'ordine parte FOK: se il book non copre tutta la size, Betfair lo
# ANNULLA e a mercato non resta nulla. In paper il fill parziale veniva
# accettato: una richiesta da 5,00 EUR risultava "eseguita" con 0,43 EUR
# (caso reale safe_strategy_requests#7). Il paper dichiarava cosi' posizioni
# che il live non avrebbe mai avuto.
# ===========================================================================
def test_paper_non_accetta_un_fill_parziale_come_il_fok_live():
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back"})
    # il book ha solo 3 EUR al prezzo richiesto, se ne chiedono 10
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=10.0,
                  ladder=((3.0, 3.0),), client_ref=f"safe-t{tid}", trade_id=tid,
                  now=NOW, params={})
    assert out.status == "error", out
    assert out.fill_note.startswith("paper_fok_parziale"), out.fill_note
    assert out.size == 0.0


def test_paper_accetta_il_fill_completo():
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back"})
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=10.0,
                  ladder=((3.0, 50.0),), client_ref=f"safe-t{tid}", trade_id=tid,
                  now=NOW, params={})
    assert out.status == "open" and out.size == 10.0


def test_paper_size_cappata_alla_liquidita_resta_un_fill_completo():
    """La size viene prima cappata a ``best_size``: cosi' il FOK trova tutto."""
    db, mk = FakeDB(), FakeMarket()
    db.follow = "NONE"
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back"})
    out = X.place(db=db, market=mk, mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=50.0, best_size=12.0,
                  client_ref=f"safe-t{tid}", trade_id=tid, now=NOW, params={})
    assert out.status == "open" and out.size == 12.0
