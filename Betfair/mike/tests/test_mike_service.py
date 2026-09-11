"""Test del ciclo del BOT Mike (service.run_once) con fake db/market.

Nessuna rete, nessun Supabase. File ASCII-only (console Windows cp1252).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


class FakeDB:
    """Specchio in memoria di mike_* (stesse regole del DB reale)."""

    def __init__(self, status="running", mode="paper", params=None):
        self.control = {"id": 1, "status": status, "mode": mode, "params": params or {}}
        self.events: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.activity: list[tuple] = []
        self.requests: list[dict] = []
        self.scan_rows: list[dict] = []
        self.scanner = {"updated_at": NOW.isoformat(), "payload": {}}
        self._id = 0

    # control / log
    def read_control(self):
        return self.control

    def set_control(self, **fields):
        self.control.update(fields)

    def log(self, kind, payload=None, event_id=None):
        self.activity.append((kind, payload or {}, event_id))

    def kinds(self):
        return [k for k, _, _ in self.activity]

    # events
    def list_events(self, states=None, since_iso=None):
        return [dict(e) for e in self.events.values() if not states or e.get("state") in states]

    def get_event(self, event_id):
        return self.events.get(event_id)

    def upsert_event(self, row):
        self.events[str(row["event_id"])] = dict(row)

    # trades
    def insert_trade(self, trade):
        for t in self.trades:
            if t["event_id"] == trade["event_id"] and t.get("signal_key") == trade.get("signal_key") \
                    and t.get("status") != "error":
                raise Exception("unique signal_key")
        self._id += 1
        t = dict(trade); t["id"] = self._id; t.setdefault("placed_at", NOW.isoformat())
        self.trades.append(t)
        return self._id

    def update_trade(self, trade_id, **fields):
        for t in self.trades:
            if t["id"] == trade_id:
                t.update(fields)

    def get_trade(self, trade_id):
        return next((t for t in self.trades if t["id"] == trade_id), None)

    def trades_for_event(self, event_id):
        return [t for t in self.trades if t["event_id"] == event_id]

    def all_trades(self):
        return list(self.trades)

    def aggregates(self, now=None):
        from Betfair.safe_strategy import bot_db as B
        from Betfair.safe_strategy import risk as R
        return B.aggregate_rows(self.trades, R.operating_day_start(now))

    # requests
    def pending_requests(self, limit=50):
        return [r for r in self.requests if r["status"] == "pending"]

    def set_request_status(self, req_id, status, result=None):
        for r in self.requests:
            if r["id"] == req_id:
                r["status"] = status
                r["result"] = result

    # feed
    def fetch_scan_rows(self):
        return list(self.scan_rows)

    def scanner_status(self):
        return self.scanner

    # dossier
    def fixture_id_for_event(self, event_id):
        return None

    def fixture_lambdas(self, fid):
        return None

    def fixture_analysis(self, fid):
        return None

    def ht_ft_rows(self, league_id):
        return []


class FakeMarket:
    def __init__(self):
        self.books: dict[str, dict] = {}
        self.calls: list[str] = []

    def read_book(self, market_id, names):
        self.calls.append(market_id)
        return self.books.get(market_id)

    def place_order_live(self, **kw):
        raise AssertionError("mai REST in paper")


def run(db, market, now, rows):
    return S.run_once(db=db, market=market, now=now, rows=rows, atlas=None)


def state(db):
    return db.events["E1"]["state"]


def legs(db):
    return db.events["E1"]["positions"]


# ---------------------------------------------------------------------------
def test_prematch_cycle_entry_and_green_taker():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    res = run(db, mk, NOW, [row(payload())])
    assert res["new"] == 1 and "armed" in db.kinds()
    # entry piazzata e fillata nello stesso ciclo (paper, pre-match: nessun betDelay)
    assert state(db) == "PRE_ENTRY_PENDING"
    assert legs(db)[0]["role"] == "under_entry" and legs(db)[0]["status"] == "open"
    assert legs(db)[0]["matched"] == 10.0 and legs(db)[0]["avg_price"] == 1.50
    assert db.trades[0]["status"] == "open" and db.trades[0]["strategy"] == "under_entry"
    # ciclo 2: PRE_OPEN (taker: nessuna resting)
    run(db, mk, NOW + timedelta(seconds=2), [row(payload())])
    assert state(db) == "PRE_OPEN" and len(legs(db)) == 1
    assert db.events["E1"]["entry_price_initial"] == 1.50
    # prezzo scende: lay a 1.48 disponibile -> green taker piazzata e fillata
    p = payload(u35=(1.47, 1.48, 30.0, 25.0))
    run(db, mk, NOW + timedelta(seconds=4), [row(p)])
    assert state(db) == "PRE_GREEN_PENDING"
    g = [l for l in legs(db) if l["role"] == "under_green"][0]
    assert g["status"] == "open" and g["side"] == "lay" and g["avg_price"] == 1.48
    # ciclo dopo: ciclo chiuso, WATCH con cycle_no 1 e gambe archiviate
    run(db, mk, NOW + timedelta(seconds=6), [row(p)])
    assert state(db) == "WATCH" and db.events["E1"]["cycle_no"] == 1
    assert all(l["archived"] for l in legs(db))
    assert "pre_cycle" in db.kinds()


def test_no_fill_when_price_gone_before_execution():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    # il book ha size 5 < stake 10: l'engine non entra (liquidita)
    run(db, mk, NOW, [row(payload(u35=(1.50, 1.52, 5.0, 25.0)))])
    assert state(db) == "WATCH" and db.trades == []


def test_bot_stopped_makes_no_new_entries_but_keeps_protections():
    db = FakeDB(status="stopped", params={"stake": 10})
    mk = FakeMarket()
    res = run(db, mk, NOW, [row(payload())])
    assert res["new"] == 0 and db.events == {}


def test_inplay_cover_is_deferred_by_bet_delay_in_paper():
    db = FakeDB(params={"stake": 10, "cover_policy": "immediate"})
    mk = FakeMarket()
    # posizione Under gia' aperta e partita in corso con betDelay 5
    db.events["E1"] = {
        "event_id": "E1", "event_name": "Roma v Lazio", "state": "LIVE_UNCOVERED", "cycle_no": 1,
        "entry_price_initial": 1.5, "markets": {"OU35": {"market_id": "1.35"}, "OU45": {"market_id": "1.45"}},
        "positions": [{"role": "under_last", "market": "OU35", "selection": "UNDER", "side": "back",
                       "price": 1.5, "size": 10.0, "matched": 10.0, "avg_price": 1.5, "ref": "under_last-1-1",
                       "status": "open", "placed_at": 0.0, "persistence": "PERSIST", "cycle_no": 1,
                       "final": False, "archived": False}],
        "dossier": {}, "live": {}, "ctx": {}, "mode": "paper", "ko_at": (NOW - timedelta(minutes=5)).isoformat(),
    }
    p = payload(inplay=True, minute=5, sh=0, sa=0, bet_delay=5, ko=NOW - timedelta(minutes=5))
    run(db, mk, NOW, [row(p)])
    assert state(db) == "LIVE_COVER_PENDING"
    cover = [l for l in legs(db) if l["role"] == "over_cover"][0]
    assert cover["status"] == "pending"                       # differita
    assert "place_deferred" in db.kinds() and db.trades == []
    # 3 secondi dopo: ancora in attesa
    run(db, mk, NOW + timedelta(seconds=3), [row(p)])
    assert [l for l in legs(db) if l["role"] == "over_cover"][0]["status"] == "pending"
    # dopo il betDelay: fill al prezzo ancora disponibile
    run(db, mk, NOW + timedelta(seconds=6), [row(p)])
    cover = [l for l in legs(db) if l["role"] == "over_cover"][0]
    assert cover["status"] == "open" and cover["matched"] == cover["size"]
    assert db.trades[-1]["strategy"] == "over_cover" and db.trades[-1]["status"] == "open"
    run(db, mk, NOW + timedelta(seconds=8), [row(p)])
    assert state(db) == "LIVE_COVERED"


def test_deferred_cover_cancelled_if_price_worsens():
    db = FakeDB(params={"stake": 10, "cover_policy": "immediate"})
    mk = FakeMarket()
    db.events["E1"] = {
        "event_id": "E1", "event_name": "Roma v Lazio", "state": "LIVE_UNCOVERED", "cycle_no": 1,
        "entry_price_initial": 1.5, "markets": {"OU35": {"market_id": "1.35"}, "OU45": {"market_id": "1.45"}},
        "positions": [{"role": "under_last", "market": "OU35", "selection": "UNDER", "side": "back",
                       "price": 1.5, "size": 10.0, "matched": 10.0, "avg_price": 1.5, "ref": "under_last-1-1",
                       "status": "open", "placed_at": 0.0, "persistence": "PERSIST", "cycle_no": 1,
                       "final": False, "archived": False}],
        "dossier": {}, "live": {}, "ctx": {}, "mode": "paper", "ko_at": (NOW - timedelta(minutes=5)).isoformat(),
    }
    p = payload(inplay=True, minute=5, sh=0, sa=0, bet_delay=5, ko=NOW - timedelta(minutes=5))
    run(db, mk, NOW, [row(p)])
    # durante il ritardo il prezzo dell'Over 4.5 scende sotto quello richiesto
    p2 = payload(inplay=True, minute=5, sh=0, sa=0, bet_delay=5, ko=NOW - timedelta(minutes=5),
                 o45=(5.0, 5.2, 12.0, 9.0))
    run(db, mk, NOW + timedelta(seconds=6), [row(p2)])
    cover = [l for l in legs(db) if l["role"] == "over_cover"][0]
    assert cover["status"] == "cancelled" and "no_fill" in db.kinds()
    # il ciclo dopo torna scoperto e ripiazza al nuovo prezzo
    run(db, mk, NOW + timedelta(seconds=8), [row(p2)])
    assert state(db) in ("LIVE_UNCOVERED", "LIVE_COVER_PENDING")


def test_settlement_when_row_disappears():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = {
        "event_id": "E1", "event_name": "Roma v Lazio", "state": "LIVE_COVERED", "cycle_no": 1,
        "entry_price_initial": 1.5, "markets": {"OU35": {"market_id": "1.35"}, "OU45": {"market_id": "1.45"}},
        "positions": [
            {"role": "under_last", "market": "OU35", "selection": "UNDER", "side": "back", "price": 1.5,
             "size": 10.0, "matched": 10.0, "avg_price": 1.5, "ref": "under_last-1-1", "status": "open",
             "placed_at": 0.0, "persistence": "PERSIST", "cycle_no": 1, "final": False, "archived": False},
            {"role": "over_cover", "market": "OU45", "selection": "OVER", "side": "back", "price": 6.0,
             "size": 2.53, "matched": 2.53, "avg_price": 6.0, "ref": "over_cover-1-2", "status": "open",
             "placed_at": 0.0, "persistence": "LAPSE", "cycle_no": 1, "final": False, "archived": False},
        ],
        "dossier": {}, "live": {}, "mode": "paper", "ko_at": (NOW - timedelta(hours=2)).isoformat(),
        "ctx": {"seen_inplay": True,
                "selections": {"OU35|UNDER": 1222344, "OU35|OVER": 1222345, "OU45|UNDER": 1222347, "OU45|OVER": 1222346}},
    }
    db.trades = [
        {"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open", "pnl": 0},
        {"id": 2, "event_id": "E1", "signal_key": "over_cover-1-2", "status": "open", "pnl": 0},
    ]
    # partita finita 2-0: Under 3.5 WINNER, Under 4.5 WINNER
    mk.books["1.35"] = {"market_id": "1.35", "status": "CLOSED", "inplay": True,
                        "runners": [{"selection_id": 1222344, "status": "WINNER"}, {"selection_id": 1222345, "status": "LOSER"}]}
    mk.books["1.45"] = {"market_id": "1.45", "status": "CLOSED", "inplay": True,
                        "runners": [{"selection_id": 1222347, "status": "WINNER"}, {"selection_id": 1222346, "status": "LOSER"}]}
    res = run(db, mk, NOW, [])                      # riga sparita dal feed
    assert res["settled"] == 1 and state(db) == "SETTLED"
    exp = round(10 * 0.5 * 0.95 - 2.53, 2)
    assert abs(db.events["E1"]["settled_pnl"] - exp) < 0.02
    assert db.trades[0]["status"] == "won" and db.trades[1]["status"] == "lost"
    assert abs(db.trades[0]["pnl"] - 5.0) < 0.01 and db.trades[1]["pnl"] == -2.53
    assert sorted(mk.calls) == ["1.35", "1.45"]
    # terminale: nessun'altra chiamata
    run(db, mk, NOW + timedelta(seconds=2), [])
    assert len(mk.calls) == 2


def test_final_total_from_books_mapping():
    from Betfair.mike import feed as F
    info = F.EventInfo("E1", "x", None, None, None, 1.0, None, {"OU35": "1.35", "OU45": "1.45"},
                       {("OU35", "UNDER"): 1, ("OU35", "OVER"): 2, ("OU45", "UNDER"): 3, ("OU45", "OVER"): 4})
    def bk(mid, winner):
        return {"market_id": mid, "status": "CLOSED", "runners": [{"selection_id": winner, "status": "WINNER"}]}
    assert S.final_total_from_books(bk("1.35", 1), bk("1.45", 3), info) == 3
    assert S.final_total_from_books(bk("1.35", 2), bk("1.45", 3), info) == 4
    assert S.final_total_from_books(bk("1.35", 2), bk("1.45", 4), info) == 5
    assert S.final_total_from_books({"status": "OPEN", "runners": []}, None, info) is None


def test_skip_and_resume_requests():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload(u35=(1.50, 1.52, 5.0, 25.0)))])     # armata ma senza ingresso
    assert state(db) == "WATCH"
    db.requests.append({"id": 1, "kind": "skip_event", "payload": {"event_id": "E1"}, "status": "pending"})
    run(db, mk, NOW + timedelta(seconds=2), [row(payload())])
    assert db.requests[0]["status"] == "done" and state(db) == "SKIPPED"
    # skippata: anche con liquidita' non entra
    run(db, mk, NOW + timedelta(seconds=4), [row(payload())])
    assert state(db) == "SKIPPED" and db.trades == []
    db.requests.append({"id": 2, "kind": "resume_event", "payload": {"event_id": "E1"}, "status": "pending"})
    run(db, mk, NOW + timedelta(seconds=6), [row(payload())])
    assert db.requests[1]["status"] == "done" and state(db) == "PRE_ENTRY_PENDING"


def test_max_open_matches_cap():
    db = FakeDB(params={"stake": 10, "max_open_matches": 1})
    mk = FakeMarket()
    p2 = payload()
    r2 = row(p2); r2["event_id"] = "E2"
    res = run(db, mk, NOW, [row(payload()), r2])
    assert res["new"] == 1 and len(db.events) == 1


def test_dry_mode_logs_would_place_without_trades():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    S.run_once(db=db, market=mk, now=NOW, rows=[row(payload())], atlas=None, dry=True)
    assert "would_place" in db.kinds() and db.trades == []
    assert state(db) == "PRE_ENTRY_PENDING"
    S.run_once(db=db, market=mk, now=NOW + timedelta(seconds=2), rows=[row(payload())], atlas=None, dry=True)
    assert state(db) == "WATCH"          # gamba cancellata -> si riparte
