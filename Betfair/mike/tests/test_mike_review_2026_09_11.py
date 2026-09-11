"""Review indipendente dell'11/09/2026 (letta sul DB reale) sui fix Mike.

Un test per ogni finding: C-1..C-5, H-1..H-8, M-1..M-9, L-1..L-3 + il predicato
``is_placed`` dello storico condiviso. ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from Betfair.mike import config as C
from Betfair.mike import db as MDB
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_audit_2026_09_11 import (asdict, fill, live_event, over_leg,
                                                           under_leg)
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import FakeDB, FakeMarket, legs, run, state
from Betfair.safe_strategy import db as SDB
from Betfair.safe_strategy import scanner as SC

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    S._LAST_HEARTBEAT.clear()
    S._CONFIG_WARNED.clear()
    S._DAILY_STOP_LOGGED.clear()
    MDB._TOTALS.clear()
    MDB._AGG_RPC.clear()
    monkeypatch.setenv("SAFE_PRE_KO_OU_HOURS", "3")
    yield


def _boom(*_a, **_k):
    raise RuntimeError("Supabase giu'")


# ===========================================================================
# C-1 — lettura righe FALLITA != nessuna riga (mai righe doppie)
# ===========================================================================
def test_c1_lettura_righe_fallita_non_reinserisce_nulla():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg()), asdict(over_leg())])
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open",
                  "pnl": 0, "liability": 10.0, "meta": {}},
                 {"id": 2, "event_id": "E1", "signal_key": "over_cover-1-2", "status": "open",
                  "pnl": 0, "liability": 2.53, "meta": {}}]
    db.trades_for_event = _boom
    db.open_trades = _boom
    p = payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(hours=1))
    run(db, mk, NOW, [row(p)])
    assert len(db.trades) == 2                      # NESSUNA riga reinserita
    assert "reconcile_pending" in db.kinds()
    pay = [pl for k, pl, _ in db.activity if k == "reconcile_pending"][0]
    assert pay["reason"] == "righe_illeggibili" and pay["critical"] is True


def test_c1_event_rows_ritorna_none_su_errore_e_non_mette_in_cache():
    db = FakeDB()
    db.trades_for_event = _boom
    cache: dict = {}
    assert S._event_rows(db, "E1", cache) is None
    assert cache == {}                              # mai un [] velenoso in cache


def test_c1_settlement_deduplica_le_righe_doppie():
    """Se per qualunque motivo esistono DUE righe per la stessa gamba, il P&L si
    scrive UNA volta: prima realized/stop/storico raddoppiavano."""
    db = FakeDB(params={"stake": 10})
    ctx = E.MatchCtx(state="SETTLING", legs=[under_leg(size=10.0, price=1.5)], cycle_no=1)
    db.trades = [
        {"id": 5, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open", "pnl": 0,
         "meta": {}},
        {"id": 6, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open", "pnl": 0,
         "meta": {}},
    ]
    res = E.settle_legs(ctx.legs, 2, 0.05)
    S._settle_trades(db, "E1", ctx, {"per_leg": res.per_leg, "per_market": res.per_market,
                                     "net": res.net, "per_leg_gross": res.per_leg_gross,
                                     "commission_by_market": res.commission_by_market},
                     C.merge_params({"stake": 10}))
    kept = next(t for t in db.trades if t["id"] == 5)
    dup = next(t for t in db.trades if t["id"] == 6)
    assert kept["status"] == "won" and kept["pnl"] == pytest.approx(4.75, abs=0.01)
    assert dup["status"] == "error" and dup["pnl"] == 0.0
    assert dup["meta"]["duplicate_of"] == 5
    assert sum(float(t["pnl"]) for t in db.trades) == pytest.approx(res.net, abs=0.02)
    assert any(pl.get("reason") == "duplicate_signal_key" for k, pl, _ in db.activity
               if k == "error")


# ===========================================================================
# C-2 — cash out manuale pre-KO con lay APPOGGIATA (default)
# ===========================================================================
def test_c2_cashout_pre_ko_con_resting_chiude_in_due_cicli():
    db = FakeDB(params={"stake": 10, "pre_exit_mode": "resting"})
    mk = FakeMarket()
    resting = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                    price=1.48, size=10.14, ref="under_green-1-2", status="pending",
                    placed_at=NOW.timestamp() - 60)
    entry = under_leg(role="under_entry")
    entry.placed_at = NOW.timestamp() - 120
    db.events["E1"] = live_event([asdict(entry), asdict(resting)], state_="PRE_OPEN",
                                 ctx={}, ko=NOW + timedelta(hours=2))
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_entry-1-1", "status": "open",
                  "pnl": 0, "meta": {}},
                 {"id": 2, "event_id": "E1", "signal_key": "under_green-1-2", "status": "pending",
                  "pnl": 0, "meta": {}}]
    db.requests = [{"id": 1, "kind": "cashout", "payload": {"event_id": "E1"}, "status": "pending"}]
    run(db, mk, NOW, [row(payload())])
    assert db.requests[0]["status"] == "done"
    # ciclo 2: nessuna lay RIAPPOGGIATA e posizione PIATTA (prima era un loop:
    # la cancellava e la riappoggiava senza mai chiudere)
    t = NOW + timedelta(seconds=2)
    run(db, mk, t, [row(payload(), updated=t)])
    ctx = S._ctx_from_row(db.events["E1"])
    assert E.live_open_selections(ctx.legs, None) == []
    greens = [l for l in legs(db) if l["role"] == "under_green" and l["status"] == "pending"]
    assert greens == []
    closes = [l for l in legs(db) if l["role"] == "manual_close"]
    assert closes and closes[0]["matched"] > 0
    # terzo ciclo: ciclo archiviato, nessun capitale a rischio, nessun rientro
    t2 = NOW + timedelta(seconds=4)
    run(db, mk, t2, [row(payload(), updated=t2)])
    ctx2 = S._ctx_from_row(db.events["E1"])
    assert E.event_liability(ctx2.legs, 0.05) == 0.0
    assert ctx2.no_reentry is True and ctx2.flatten_pending is False
    assert state(db) == "WATCH"


def test_c2_engine_non_riappoggia_la_green_durante_il_flatten():
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[under_leg(role="under_entry")], cycle_no=1,
                     flatten_pending=True)
    snap = E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() + 7200, inplay=False,
                      books={(E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.48, back_size=50.0,
                                                                  best_lay=1.50, lay_size=50.0)})
    d = E.decide(ctx, snap, C.merge_params({"stake": 10, "pre_exit_mode": "resting"}))
    roles = [a.role for a in d.actions if a.kind == "place"]
    assert roles == ["manual_close"] and d.state == "PRE_GREEN_PENDING"


# ===========================================================================
# C-3 — no_reentry LETTO davvero
# ===========================================================================
def test_c3_no_reentry_blocca_l_ingresso_nell_engine():
    ctx = E.MatchCtx(state="WATCH", cycle_no=1, no_reentry=True)
    snap = E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() + 7200, inplay=False,
                      books={(E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.50, back_size=99.0,
                                                                  best_lay=1.52, lay_size=99.0)})
    d = E.decide(ctx, snap, C.merge_params({"stake": 10}))
    assert d.state == "WATCH" and d.actions == [] and "Riprendi" in d.reason
    # senza il flag si entra
    ctx2 = E.MatchCtx(state="WATCH", cycle_no=1)
    assert E.decide(ctx2, snap, C.merge_params({"stake": 10})).state == "PRE_ENTRY_PENDING"


def test_c3_no_reentry_blocca_anche_il_re_ingresso_live():
    snap = E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() - 600, inplay=True, minute=20,
                      goals=1, feed_fresh=True,
                      books={(E.MARKET_OU45, E.SEL_UNDER): E.Book(best_back=1.60, back_size=99.0,
                                                                  best_lay=1.62, lay_size=99.0,
                                                                  inplay=True)})
    ctx = E.MatchCtx(state="FLAT", cycle_no=1, reentry_allowed=True, entry_price_initial=1.5,
                     no_reentry=True)
    d = E.decide(ctx, snap, C.merge_params({"stake": 10}))
    assert d.state == "FLAT" and not d.actions


def test_c3_dopo_il_cashout_pre_ko_il_bot_non_rientra_dopo_il_cooldown():
    db = FakeDB(params={"stake": 10, "pre_exit_mode": "taker", "pre_reentry_cooldown_s": 0})
    mk = FakeMarket()
    entry = under_leg(role="under_entry")
    entry.placed_at = NOW.timestamp() - 120
    db.events["E1"] = live_event([asdict(entry)], state_="PRE_OPEN", ctx={},
                                 ko=NOW + timedelta(hours=2))
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_entry-1-1", "status": "open",
                  "pnl": 0, "meta": {}}]
    db.requests = [{"id": 1, "kind": "cashout", "payload": {"event_id": "E1"}, "status": "pending"}]
    run(db, mk, NOW, [row(payload())])
    for i in range(1, 4):                     # cooldown a 0: prima rientrava subito
        t = NOW + timedelta(seconds=2 * i)
        run(db, mk, t, [row(payload(), updated=t)])
    entries = [l for l in legs(db) if l["role"] == "under_entry"]
    assert len(entries) == 1
    assert S._ctx_from_row(db.events["E1"]).no_reentry is True
    # "Riprendi" riabilita davvero
    db.requests.append({"id": 2, "kind": "resume_event", "payload": {"event_id": "E1"},
                        "status": "pending"})
    t = NOW + timedelta(seconds=20)
    run(db, mk, t, [row(payload(), updated=t)])
    assert S._ctx_from_row(db.events["E1"]).no_reentry is False
    t = NOW + timedelta(seconds=22)
    run(db, mk, t, [row(payload(), updated=t)])
    assert len([l for l in legs(db) if l["role"] == "under_entry"]) == 2


# ===========================================================================
# C-4 — void PER MERCATO
# ===========================================================================
def test_c4_void_di_un_solo_mercato_non_azzera_la_partita():
    legs_ = [under_leg(size=10.0, price=1.5), over_leg(size=2.53, price=6.0)]
    # 4 gol: Under 3.5 PERSO (-10), Over 4.5 annullato (0) → -10, non 0
    res = E.settle_legs_by_market(legs_, {E.MARKET_OU35: E.SEL_OVER, E.MARKET_OU45: None}, 0.05)
    assert res.net == pytest.approx(-10.0, abs=0.01)
    by_ref = {r: (st, p) for r, st, p in res.per_leg}
    assert by_ref["under_last-1-1"] == ("lost", -10.0)
    assert by_ref["over_cover-1-2"] == ("void", 0.0)
    # entrambi annullati: zero davvero
    res0 = E.settle_legs_by_market(legs_, {E.MARKET_OU35: None, E.MARKET_OU45: None}, 0.05)
    assert res0.net == 0.0 and all(st == "void" for _r, st, _p in res0.per_leg)


def test_c4_settle_plan_aspetta_se_un_mercato_non_e_ne_regolato_ne_void():
    from Betfair.mike import feed as F

    info = F.event_info("E1", payload())
    closed35 = {"status": "CLOSED", "runners": [{"selection_id": 1222344, "status": "WINNER"},
                                                {"selection_id": 1222345, "status": "LOSER"}]}
    void45 = {"status": "CLOSED", "runners": [{"selection_id": 1222346, "status": "REMOVED"},
                                              {"selection_id": 1222347, "status": "REMOVED"}]}
    winners, tele = S.settle_plan(closed35, void45, info)
    assert winners == {E.MARKET_OU35: E.SEL_UNDER, E.MARKET_OU45: None}
    assert tele["voided"] == [E.MARKET_OU45]
    # 4.5 illeggibile (non void): si ASPETTA, non si azzera nulla
    assert S.settle_plan(closed35, None, info)[0] is None
    assert S.settle_plan(closed35, {"status": "OPEN", "runners": []}, info)[0] is None


def test_c4_ciclo_regola_per_mercato_e_non_perde_la_perdita_reale():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    under = under_leg(size=10.0, price=1.5)
    under.placed_at = NOW.timestamp() - 7200
    over = over_leg(size=2.53, price=6.0)
    over.placed_at = NOW.timestamp() - 3600
    db.events["E1"] = live_event([asdict(under), asdict(over)], state_="LIVE_COVERED",
                                 ctx={"seen_inplay": True, "last_goals": 4,
                                      "selections": {"OU35|UNDER": 1222344, "OU35|OVER": 1222345,
                                                     "OU45|UNDER": 1222347, "OU45|OVER": 1222346}},
                                 ko=NOW - timedelta(hours=2))
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open",
                  "pnl": 0, "meta": {}},
                 {"id": 2, "event_id": "E1", "signal_key": "over_cover-1-2", "status": "open",
                  "pnl": 0, "meta": {}}]
    mk.books["1.35"] = {"market_id": "1.35", "status": "CLOSED",
                        "runners": [{"selection_id": 1222344, "status": "LOSER"},
                                    {"selection_id": 1222345, "status": "WINNER"}]}
    mk.books["1.45"] = {"market_id": "1.45", "status": "CLOSED",
                        "runners": [{"selection_id": 1222346, "status": "REMOVED"},
                                    {"selection_id": 1222347, "status": "REMOVED"}]}
    res = run(db, mk, NOW, [])
    assert res["settled"] == 1 and state(db) == "SETTLED"
    assert db.events["E1"]["settled_pnl"] == pytest.approx(-10.0, abs=0.01)
    by_id = {t["id"]: t for t in db.trades}
    assert by_id[1]["status"] == "lost" and by_id[1]["pnl"] == pytest.approx(-10.0, abs=0.01)
    assert by_id[2]["status"] == "void" and by_id[2]["pnl"] == 0.0


# ===========================================================================
# C-5 — nessun retry cieco dell'insert
# ===========================================================================
def test_c5_insert_ritenta_solo_su_colonna_mancante():
    assert S._is_missing_column_error(
        RuntimeError("Could not find the 'closes_trade_id' column of 'mike_trades' "
                     "in the schema cache (PGRST204)"), "closes_trade_id") is True
    assert S._is_missing_column_error(
        RuntimeError('column "closes_trade_id" of relation "mike_trades" does not exist (42703)'),
        "closes_trade_id") is True
    # timeout / errore di rete: NON e' uno schema mancante
    assert S._is_missing_column_error(RuntimeError("read timeout"), "closes_trade_id") is False
    assert S._is_missing_column_error(
        RuntimeError("insert on table violates foreign key constraint "
                     "mike_trades_closes_trade_id_fkey"), "closes_trade_id") is False


def test_c5_timeout_sull_insert_non_crea_la_riga_doppia():
    db = FakeDB()
    calls = []

    def flaky(row_):
        calls.append(row_)
        raise RuntimeError("read timeout dopo l'insert")
    db.insert_trade = flaky
    with pytest.raises(RuntimeError):
        S._insert_trade_row(db, {"event_id": "E1", "closes_trade_id": 3, "meta": {}}, "E1")
    assert len(calls) == 1                     # un solo tentativo


def test_c5_colonna_assente_ripiega_una_volta_sola():
    db = FakeDB()
    calls = []

    def missing(row_):
        calls.append(dict(row_))
        if "closes_trade_id" in row_:
            raise RuntimeError("PGRST204: Could not find the 'closes_trade_id' column "
                               "in the schema cache")
        return 42
    db.insert_trade = missing
    tid = S._insert_trade_row(db, {"event_id": "E1", "closes_trade_id": 3, "meta": {}}, "E1")
    assert tid == 42 and len(calls) == 2
    assert calls[1]["meta"]["closes_trade_id_pending"] == 3
    assert "schema_warn" in db.kinds()


# ===========================================================================
# H-1 / H-2
# ===========================================================================
def test_h1_stop_giornaliero_spegne_anche_l_ultimo_ingresso():
    db = FakeDB(params={"stake": 10, "daily_loss_stop": 1})
    mk = FakeMarket()
    db.trades = [{"id": 1, "event_id": "OLD", "signal_key": "x", "status": "lost", "pnl": -5.0,
                  "placed_at": NOW.isoformat(), "settled_at": NOW.isoformat(), "meta": {}}]
    res = run(db, mk, NOW, [row(payload())])
    assert res["stats"]["daily_stop"] is True
    # a stop attivo l'ultimo ingresso PERSIST non parte
    eff = dict(C.merge_params({"stake": 10}), pre_enabled=False, reentry_enabled=False,
               last_entry_persist=False)
    ctx = E.MatchCtx(state="PRE_GREEN_PENDING", cycle_no=1)
    d = E._after_final_green(ctx, E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() + 300,
                                             books={}), eff,
                             E.Book(best_back=1.5, back_size=99.0, best_lay=1.52, lay_size=99.0),
                             10.0)
    assert d.state == "IDLE_LIVE" and not d.actions


def test_h2_righe_illeggibili_non_cancellano_una_gamba_pending():
    db = FakeDB(params={"stake": 10, "pre_exit_mode": "taker"})
    mk = FakeMarket()
    stale = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                  price=1.5, size=10.0, ref="under_entry-1-1", status="pending",
                  placed_at=NOW.timestamp() - 600)
    db.events["E1"] = live_event([asdict(stale)], state_="PRE_ENTRY_PENDING", ctx={},
                                 ko=NOW + timedelta(hours=2))
    db.trades_for_event = _boom
    run(db, mk, NOW, [row(payload())])
    got = legs(db)[0]
    assert got["status"] == E.STATUS_RECONCILE       # mai 'cancelled' nel dubbio


# ===========================================================================
# H-3 — aggregati incrementali anche senza la RPC
# ===========================================================================
def test_h3_fallback_aggregati_non_scansiona_tutto_a_ogni_ciclo(monkeypatch):
    calls = {"all": 0, "live": 0}

    def fake_all(*_a, **_k):
        calls["all"] += 1
        return []

    def fake_live(since=None):
        calls["live"] += 1
        return []
    monkeypatch.setattr(MDB, "all_trades", fake_all)
    monkeypatch.setattr(MDB, "live_trades", fake_live)
    monkeypatch.setattr(MDB, "_sb", _boom)
    for i in range(5):
        MDB.aggregates(NOW + timedelta(seconds=i))
    assert calls["live"] == 5
    assert calls["all"] == 1                   # cumulativi in cache (TTL 5 min)
    assert MDB._AGG_RPC.get("missing") is True


def test_h3_live_trades_e_usata_dal_fallback(monkeypatch):
    rows = [{"id": 1, "event_id": "A", "status": "won", "pnl": 1.0,
             "placed_at": NOW.isoformat(), "settled_at": NOW.isoformat()}]
    monkeypatch.setattr(MDB, "_sb", _boom)
    monkeypatch.setattr(MDB, "live_trades", lambda since=None: list(rows))
    monkeypatch.setattr(MDB, "all_trades", lambda *a, **k: list(rows))
    agg = MDB.aggregates(NOW)
    assert agg["realized_today"] == 1.0 and agg["realized_total"] == 1.0
    assert agg["totals_from"] == "full_scan_cache"


# ===========================================================================
# H-4 / H-5 / H-6 / H-7 — scanner
# ===========================================================================
def test_h4_solo_le_partite_con_esposizione_sono_esenti():
    assert SDB._mike_has_exposure({"state": "WATCH", "positions": []}) is False
    assert SDB._mike_has_exposure({"state": "IDLE_LIVE", "positions": []}) is False
    assert SDB._mike_has_exposure({"state": "SETTLED", "positions": [{"matched": 10}]}) is False
    assert SDB._mike_has_exposure({"state": "PRE_OPEN", "positions": []}) is True
    assert SDB._mike_has_exposure(
        {"state": "WATCH", "positions": [{"status": "open", "matched": 10.0}]}) is True
    assert SDB._mike_has_exposure(
        {"state": "WATCH", "positions": [{"status": "pending", "matched": 0.0}]}) is True
    assert SDB._mike_has_exposure(
        {"state": "WATCH", "positions": [{"status": "pending_reconcile", "matched": 0.0}]}) is True
    # ciclo pre-match ARCHIVIATO: capitale non piu' a rischio
    assert SDB._mike_has_exposure(
        {"state": "WATCH",
         "positions": [{"status": "open", "matched": 10.0, "archived": True}]}) is False


def test_h4_esenzione_cappata():
    # 20 partite "seguite" (bug o giornata anomala) con la priorita' piu' BASSA
    cands = [f"E{i}" for i in range(30)] + [f"M{i}" for i in range(20)]
    out = SC.select_opp_candidates(cands, followed=[f"M{i}" for i in range(20)])
    assert out[:SC.MIKE_MAX_FOLLOWED] == [f"M{i}" for i in range(SC.MIKE_MAX_FOLLOWED)]
    assert len([e for e in out if e.startswith("M")]) == SC.MIKE_MAX_FOLLOWED
    assert len(out) == SC.MIKE_MAX_FOLLOWED + SC.OPP_MAX_EVENTS
    # le seguite oltre il tetto non spariscono: competono col tetto normale
    out2 = SC.select_opp_candidates([f"M{i}" for i in range(20)],
                                    followed=[f"M{i}" for i in range(20)])
    assert len(out2) == 20


def test_h5_le_linee_di_mike_hanno_priorita_sopra_le_altre_opportunita():
    core_inplay = SC.rank_key(True, "2026-09-12T12:00:00Z")
    core_pre = SC.rank_key(False, "2026-09-12T12:00:00Z")
    mike_line = SC.opp_rank_key(3, "2026-09-12T12:00:00Z", mike=True)
    other = SC.opp_rank_key(80, "2026-09-12T12:00:00Z")
    assert core_inplay[0] < core_pre[0] < mike_line[0] < other[0]
    # ordinabili insieme senza confrontare una data con un minuto
    assert sorted([other, mike_line, core_pre, core_inplay],
                  key=lambda k: k[0])[0] == core_inplay


def test_h6_una_linea_decisa_non_e_piu_un_mercato_per_le_opportunita():
    from Betfair.safe_strategy.opportunity import OpportunityModel

    assert SC.ou_block_decided({"market_type": "OVER_UNDER_35", "line": 3.5}, 2, 2) is True
    assert SC.ou_block_decided({"market_type": "OVER_UNDER_45", "line": 4.5}, 2, 2) is False
    assert SC.ou_block_decided({"market_type": "BOTH_TEAMS_TO_SCORE", "line": None}, 2, 2) is False
    p = {"minute": 70, "score_home": 3, "score_away": 1, "inplay": True,
         "ou": [
             {"market_type": "OVER_UNDER_35", "line": 3.5, "market_id": "1.35", "status": "OPEN",
              "decided": True, "for_mike": True,
              "selections": [{"name": "Under 3.5 Goals", "back": 1.01, "lay": 1.02},
                             {"name": "Over 3.5 Goals", "back": 200.0, "lay": 500.0}]},
             {"market_type": "OVER_UNDER_45", "line": 4.5, "market_id": "1.45", "status": "OPEN",
              "selections": [{"name": "Under 4.5 Goals", "back": 1.3, "lay": 1.32},
                             {"name": "Over 4.5 Goals", "back": 4.0, "lay": 4.2}]},
         ]}
    m = OpportunityModel.__new__(OpportunityModel)
    specs = m._market_specs(p, 70)
    lines = [s["line"] for s in specs if s["market_type"] == "OVER_UNDER"]
    assert 3.5 not in lines and 4.5 in lines
    # anche senza il marcatore: la linea superata non e' un mercato
    p2 = {**p, "ou": [{**p["ou"][0]}, p["ou"][1]]}
    p2["ou"][0].pop("decided")
    specs2 = m._market_specs(p2, 70)
    assert 3.5 not in [s["line"] for s in specs2 if s["market_type"] == "OVER_UNDER"]


def test_h7_la_partita_mike_e_candidata_anche_al_primo_minuto():
    assert SC.is_opp_candidate(True, 0) is False        # regola generale invariata
    assert SC.is_opp_candidate(True, None) is False
    assert SC.is_opp_candidate(True, 1) is True


# ===========================================================================
# H-8 — throttle della riconciliazione e riduzione del rischio
# ===========================================================================
def test_h8_con_esito_ignoto_il_ciclo_continua_e_riduce_il_rischio():
    """Le APERTURE sono bloccate, le chiusure NO: prima il ciclo usciva prima di
    copertura, cash-out, uscite e cap di perdita."""
    unknown = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                    price=1.5, size=10.0, ref="under_entry-0-9", status=E.STATUS_RECONCILE)
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[under_leg(), over_leg(), unknown], cycle_no=1)
    books = {(E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.09, back_size=99.0, best_lay=1.10,
                                                  lay_size=99.0, inplay=True),
             (E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=28.0, back_size=99.0, best_lay=30.0,
                                                 lay_size=99.0, inplay=True)}
    snap = E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() - 1800, inplay=True, minute=30,
                      goals=0, feed_fresh=True, books=books)
    d = E.decide(ctx, snap, C.merge_params({"stake": 10}))
    assert d.state == "LIVE_CLOSING"                  # il cash-out a profitto agisce
    assert all(a.role != "over_cover" for a in d.actions)
    # una decisione di sola APERTURA viene svuotata
    ctx2 = E.MatchCtx(state="LIVE_UNCOVERED", legs=[under_leg(), unknown], cycle_no=1)
    snap2 = E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() - 600, inplay=True, minute=10,
                       goals=1, feed_fresh=True, last_goal_ts=None,
                       books={(E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=6.0, back_size=99.0,
                                                                  best_lay=6.2, lay_size=99.0,
                                                                  inplay=True)})
    d2 = E.decide(ctx2, snap2, C.merge_params({"stake": 10, "cover_policy": "immediate"}))
    assert [a for a in d2.actions if a.kind == "place"] == []
    assert "nessuna apertura" in d2.reason


def test_h8_riconciliazione_throttlata():
    db = FakeDB(mode="live", params={"stake": 10, "settle_confirm_s": 60})
    calls = []

    class Market(FakeMarket):
        def list_current_orders(self):
            calls.append(1)
            return []

        def list_cleared_orders(self):
            return []

    mk = Market()
    unknown = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                    price=1.5, size=10.0, ref="under_entry-1-1", status=E.STATUS_RECONCILE,
                    placed_at=NOW.timestamp() - 30)
    db.events["E1"] = live_event([asdict(unknown)], state_="PRE_ENTRY_PENDING", ctx={},
                                 mode="live", ko=NOW + timedelta(hours=2))
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_entry-1-1", "status": "pending",
                  "market_id": "1.35", "selection_id": 1222344, "side": "back", "price": 1.5,
                  "size": 10.0, "placed_at": NOW.isoformat(),
                  "meta": {"reason": "place_exception_reconciling"}}]
    for i in range(5):
        t = NOW + timedelta(seconds=2 * i)
        run(db, mk, t, [row(payload(), updated=t)])
    assert len(calls) == 1                     # prima: una coppia di REST per ciclo
    later = NOW + timedelta(seconds=120)
    run(db, mk, later, [row(payload(), updated=later)])
    assert len(calls) == 2


# ===========================================================================
# M-1..M-9 / L-1..L-3
# ===========================================================================
def test_m1_il_bloccato_di_ieri_non_entra_nello_stop_di_oggi():
    db = FakeDB(params={"stake": 10, "daily_loss_stop": 5})
    mk = FakeMarket()
    back = under_leg(size=100.0, price=1.50, role="under_entry")
    lay = fill(E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                     price=1.70, size=88.24, ref="under_close-1-2"))
    yesterday = NOW.timestamp() - 30 * 3600
    back.placed_at = yesterday
    lay.placed_at = yesterday + 60
    db.events["E1"] = live_event([asdict(back), asdict(lay)], state_="FLAT")
    res = run(db, mk, NOW, [row(payload(inplay=True, minute=50, sh=1, sa=1,
                                        ko=NOW - timedelta(hours=1)))])
    assert res["stats"]["locked_open"] == 0.0 and res["stats"]["daily_stop"] is False
    # la stessa partita piazzata OGGI conta
    back.placed_at = NOW.timestamp() - 600
    lay.placed_at = NOW.timestamp() - 300
    db.events["E1"] = live_event([asdict(back), asdict(lay)], state_="FLAT")
    S._DAILY_STOP_LOGGED.clear()
    t = NOW + timedelta(seconds=2)
    res2 = run(db, mk, t, [row(payload(inplay=True, minute=50, sh=1, sa=1,
                                       ko=NOW - timedelta(hours=1)), updated=t)])
    assert res2["stats"]["locked_open"] < -5 and res2["stats"]["daily_stop"] is True


def test_m2_riga_orfana_open_in_paper_viene_chiusa():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())])
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open",
                  "pnl": 0, "meta": {}},
                 {"id": 9, "event_id": "E1", "signal_key": "fantasma", "status": "open",
                  "pnl": 0, "liability": 50.0, "meta": {}}]
    run(db, mk, NOW, [row(payload(inplay=True, minute=30, sh=0, sa=0,
                                  ko=NOW - timedelta(hours=1)))])
    ghost = next(t for t in db.trades if t["id"] == 9)
    assert ghost["status"] == "error" and ghost["meta"]["reason"] == "orphan_paper"


def test_m3_gamba_malformata_grida():
    db = FakeDB()
    buona = {"role": "under_entry", "market": "OU35", "selection": "UNDER", "side": "back",
             "price": 1.5, "size": 10.0}
    out = S._legs_from_json([buona, "spazzatura", {"role": "senza_campi"}], db, "E1")
    assert len(out) == 1                        # solo la gamba valida sopravvive
    errs = [pl for k, pl, _ in db.activity if k == "error"]
    assert errs and errs[0]["reason"] == "leg_malformata" and errs[0]["critical"] is True


def test_m6_il_battito_non_si_scrive_a_ogni_ciclo():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    writes = []
    orig = db.set_control

    def spy(**f):
        if "heartbeat_at" in f:
            writes.append(f["heartbeat_at"])
        orig(**f)
    db.set_control = spy
    db.events["E1"] = live_event([asdict(under_leg()), asdict(over_leg())])
    # 10 cicli a 1 s con prezzi (e quindi P&L) diversi a ogni giro
    for i in range(10):
        t = NOW + timedelta(seconds=i)
        p = payload(inplay=True, minute=30 + i, sh=0, sa=0, ko=NOW - timedelta(hours=1),
                    u35=(1.30 + i / 100.0, 1.32 + i / 100.0, 99.0, 99.0))
        run(db, mk, t, [row(p, updated=t)])
    assert len(writes) <= 3                     # prima: 10 scritture su 10 cicli


def test_m7_un_log_critico_non_resta_muto_cinque_minuti():
    db = FakeDB()
    extra: dict = {}
    params = C.merge_params({"skip_log_interval_s": 300})
    assert S._log_throttled(db, extra, params, 1000.0, "feed_line_missing",
                            {"reason": "x", "critical": True}, "E1") is True
    assert S._log_throttled(db, extra, params, 1030.0, "feed_line_missing",
                            {"reason": "x", "critical": True}, "E1") is False
    assert S._log_throttled(db, extra, params, 1050.0, "feed_line_missing",
                            {"reason": "x", "critical": True}, "E1") is True
    # un log NON critico resta sull'intervallo lungo
    assert S._log_throttled(db, extra, params, 2000.0, "skip", {"reason": "y"}, "E1") is True
    assert S._log_throttled(db, extra, params, 2100.0, "skip", {"reason": "y"}, "E1") is False


def test_m9_closes_trade_id_pending_viene_ribaltato_in_colonna():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())])
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open",
                  "pnl": 0, "meta": {}},
                 {"id": 2, "event_id": "E1", "signal_key": "under_close-1-9", "status": "open",
                  "pnl": 0, "meta": {"closes_trade_id_pending": 1}}]
    run(db, mk, NOW, [row(payload(inplay=True, minute=30, sh=0, sa=0,
                                  ko=NOW - timedelta(hours=1)))])
    fixed = next(t for t in db.trades if t["id"] == 2)
    assert fixed["closes_trade_id"] == 1
    assert "closes_trade_id_pending" not in fixed["meta"]


def test_l1_open_trades_e_paginata():
    calls = []

    class FakeSB:
        def table(self, _n):
            return self

        def select(self, *_a, **_k):
            return self

        def in_(self, *_a):
            return self

        def order(self, *_a, **_k):
            return self

        def range(self, a, b):
            calls.append((a, b))
            return self

        def execute(self):
            rows = [{"id": i} for i in range(MDB.PAGE_SIZE)] if len(calls) == 1 else []

            class R:
                data = rows
            return R()

    orig = MDB._sb
    try:
        MDB._sb = lambda: FakeSB()
        rows = MDB.open_trades()
    finally:
        MDB._sb = orig
    assert calls == [(0, MDB.PAGE_SIZE - 1), (MDB.PAGE_SIZE, 2 * MDB.PAGE_SIZE - 1)]
    assert len(rows) == MDB.PAGE_SIZE


def test_l2_il_throttle_del_regolamento_persiste_lo_stato():
    db = FakeDB(params={"stake": 10, "settle_confirm_s": 120})
    mk = FakeMarket()
    leg = under_leg()
    leg.placed_at = NOW.timestamp() - 7200
    db.events["E1"] = live_event([asdict(leg)], state_="LIVE_COVERED",
                                 ctx={"seen_inplay": True, "last_goals": 2,
                                      "selections": {"OU35|UNDER": 1222344}},
                                 ko=NOW - timedelta(hours=2))
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open",
                  "pnl": 0, "meta": {}}]
    run(db, mk, NOW, [])                         # primo giro: fissa settle_next_ts
    nxt = db.events["E1"]["ctx"]["settle_next_ts"]
    # secondo giro DENTRO il throttle: lo stato persiste comunque
    db.events["E1"]["ctx"]["ht_score"] = [1, 1]
    run(db, mk, NOW + timedelta(seconds=5), [])
    assert db.events["E1"]["ctx"]["settle_next_ts"] == nxt
    assert db.events["E1"]["ctx"]["ht_score"] == [1, 1]


def test_l3_la_chiusura_manuale_usa_i_parametri_effettivi():
    """In LIVE la lay appoggiata e' spenta: la chiusura manuale deve essere taker."""
    seen = {}
    db = FakeDB(mode="live", params={"stake": 10, "pre_exit_mode": "resting"})
    mk = FakeMarket()
    entry = under_leg(role="under_entry")
    entry.placed_at = NOW.timestamp() - 120
    db.events["E1"] = live_event([asdict(entry)], state_="PRE_OPEN", ctx={}, mode="live",
                                 ko=NOW + timedelta(hours=2))
    db.requests = [{"id": 1, "kind": "cashout", "payload": {"event_id": "E1"}, "status": "pending"}]
    orig = S._request_flatten

    def spy(db_, market, ev, row_, params, now, dry, **kw):
        seen["pre_exit_mode"] = params.get("pre_exit_mode")
        return orig(db_, market, ev, row_, params, now, dry, **kw)
    S._request_flatten = spy
    try:
        run(db, mk, NOW, [row(payload())])
    finally:
        S._request_flatten = orig
    assert seen["pre_exit_mode"] == "taker"


def test_is_placed_dello_storico_conta_le_righe_in_riconciliazione():
    """Review Safe: una riga 'pending' in riconciliazione e' PIAZZATA anche per
    lo storico, come la contano i KPI (prima trades_placed < day_trades)."""
    sql = (MIGRATIONS / "mike_history_v2.sql").read_text(encoding="utf-8")
    assert "OR t.meta->>'reason' = 'place_exception_reconciling') AS is_placed" in sql
    sql2 = (MIGRATIONS / "mike_bot_v2.sql").read_text(encoding="utf-8")
    assert "place_exception_reconciling" in sql2
    assert "'liability_source'" in sql2 and "LIMIT 500" in sql2


def test_c2_il_flatten_non_archivia_una_posizione_ancora_aperta():
    """Senza prezzi la chiusura manuale ASPETTA: chiudere il ciclo qui
    archivierebbe una posizione viva (capitale a rischio invisibile)."""
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[under_leg(role="under_entry")], cycle_no=1,
                     flatten_pending=True)
    snap = E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() + 7200, inplay=False, books={})
    d = E.decide(ctx, snap, C.merge_params({"stake": 10}))
    assert d.state == "PRE_OPEN" and not d.actions and "prezzi non disponibili" in d.reason
    E.apply_decision(ctx, d, snap.now)
    assert ctx.flatten_pending is True and not ctx.legs[0].archived
    assert E.event_liability(ctx.legs, 0.05) == 10.0
