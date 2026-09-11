"""Test dell'audit 11/09/2026 sul bot MIKE (sezione 1 dell'audit + storico condiviso).

Un test (o piu') per OGNI item backend: C1, C2, C3, H1..H5, M1..M10/R2, L1..L5,
piu' i "test mancanti" elencati dall'audit: cash out/flatten manuale, esito
ignoto + TTL, crash dopo l'ordine, in-play senza linea 3.5 dopo 4 gol, mercato
void, fail_stale_processing, selezione decisa nel cash-out, netto vs somma righe.

Nessuna rete, nessun Supabase. File ASCII-only (console Windows cp1252).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from Betfair.mike import config as C
from Betfair.mike import db as MDB
from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import blk, payload, row
from Betfair.mike.tests.test_mike_service import FakeDB, FakeMarket, legs, run, state
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import scanner as SC

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


def _reset_globals() -> None:
    S._LAST_HEARTBEAT.clear()
    S._CONFIG_WARNED.clear()
    S._DAILY_STOP_LOGGED.clear()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    _reset_globals()
    # il ramo pre-KO dello scanner acceso a 3h: nessun config_warn di rumore
    monkeypatch.setenv("SAFE_PRE_KO_OU_HOURS", "3")
    yield
    _reset_globals()


def fill(leg: E.Leg, size=None, price=None) -> E.Leg:
    leg.matched = float(size if size is not None else leg.size)
    leg.avg_price = float(price if price is not None else leg.price)
    leg.status = "open"
    return leg


def under_leg(size=10.0, price=1.50, role="under_last") -> E.Leg:
    return fill(E.Leg(role=role, market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                      price=price, size=size, ref=f"{role}-1-1", cycle_no=1))


def over_leg(size=2.53, price=6.0) -> E.Leg:
    return fill(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER, side="back",
                      price=price, size=size, ref="over_cover-1-2", cycle_no=1))


def live_event(positions, state_="LIVE_COVERED", ctx=None, mode="paper", ko=None):
    return {
        "event_id": "E1", "event_name": "Roma v Lazio", "state": state_, "cycle_no": 1,
        "entry_price_initial": 1.5,
        "markets": {"OU35": {"market_id": "1.35"}, "OU45": {"market_id": "1.45"}},
        "positions": positions, "dossier": {}, "live": {}, "mode": mode,
        "ko_at": (ko or (NOW - timedelta(hours=1))).isoformat(),
        "ctx": ctx if ctx is not None else {"seen_inplay": True},
    }


def asdict(leg: E.Leg) -> dict:
    import dataclasses

    return dataclasses.asdict(leg)


# ===========================================================================
# C1 — le linee di Mike devono restare nel feed finche' la partita e' seguita
# ===========================================================================
def test_c1_scanner_esenta_le_partite_seguite_da_mike_dal_tetto():
    """Il tetto dei mercati opportunita' (20 eventi, minuti piu' avanzati) non
    puo' tagliare una partita con POSIZIONE aperta: senza le sue linee non c'e'
    copertura Over 4.5, ne' cash out, ne' uscita."""
    cands = [f"E{i}" for i in range(30)]          # gia' in ordine di priorita'
    # senza esenzione: passano solo i primi 20 e la partita Mike (E27) esce
    assert SC.select_opp_candidates(cands, followed=()) == cands[:20]
    out = SC.select_opp_candidates(cands, followed=("E27",))
    assert "E27" in out and len(out) == 21 and out[0] == "E27"
    # il tetto vale per le NON seguite: una seguita non viene mai duplicata
    out2 = SC.select_opp_candidates(cands, followed=("E0",))
    assert out2.count("E0") == 1 and len(out2) == 21
    # tetto personalizzabile e mai negativo
    assert SC.select_opp_candidates(cands, followed=(), max_events=0) == []


def test_c1_linee_mancanti_sono_gridate_nel_log_e_nella_card():
    """Se la linea non c'e', Mike NON inventa prezzi: logga `feed_line_missing`
    (critico) e lo espone su live.lines_missing."""
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())], state_="LIVE_UNCOVERED")
    p = payload(inplay=True, minute=20, sh=0, sa=0, ko=NOW - timedelta(minutes=20))
    p["ou"] = p["ou"][:1]                       # la linea 4.5 SPARISCE dal feed
    run(db, mk, NOW, [row(p)])
    assert "feed_line_missing" in db.kinds()
    payload_log = [pl for k, pl, _ in db.activity if k == "feed_line_missing"][0]
    assert payload_log["critical"] is True and payload_log["markets"] == ["OU45"]
    assert db.events["E1"]["live"]["lines_missing"] == ["OU45"]
    # il log non si ripete a ogni ciclo (skip_log_interval_s)
    t = NOW + timedelta(seconds=3)
    run(db, mk, t, [row(p, updated=t)])
    assert db.kinds().count("feed_line_missing") == 1


# ===========================================================================
# C2 — dopo il 4o gol la partita NON si congela
# ===========================================================================
def test_c2_selezione_decisa_vale_0_1_senza_prezzo():
    legs_ = [under_leg(), over_leg()]
    # 4 gol: Under 3.5 ha PERSO per certo, Over 4.5 e' ancora in gioco
    assert E.selection_decided(E.MARKET_OU35, E.SEL_UNDER, 4) is False
    assert E.selection_decided(E.MARKET_OU35, E.SEL_OVER, 4) is True
    assert E.selection_decided(E.MARKET_OU45, E.SEL_OVER, 4) is None
    assert E.selection_decided(E.MARKET_OU35, E.SEL_UNDER, 3) is None
    assert E.selection_decided(E.MARKET_OU35, E.SEL_UNDER, None) is None
    # la 3.5 e' stata potata dal feed: c'e' solo il book dell'Over 4.5
    books = {(E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=3.0, back_size=50.0, best_lay=3.1,
                                                 lay_size=50.0, inplay=True)}
    cv = E.cashout_value(legs_, books, 0.05, goals=4)
    assert cv.complete is True                                   # prima era False → card congelata
    assert (E.MARKET_OU35, E.SEL_UNDER) in cv.decided
    assert cv.per_selection[(E.MARKET_OU35, E.SEL_UNDER)] == -10.0   # perdita CERTA
    # solo la gamba VIVA viene chiusa
    assert (E.MARKET_OU45, E.SEL_OVER) in cv.plans
    assert (E.MARKET_OU35, E.SEL_UNDER) not in cv.plans


def test_c2_engine_decide_con_le_sole_selezioni_vive():
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[under_leg(), over_leg()], cycle_no=1)
    snap = E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() - 3600, inplay=True, minute=70,
                      goals=4, feed_fresh=True,
                      books={(E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=1.6, back_size=200.0,
                                                                 best_lay=1.62, lay_size=200.0,
                                                                 inplay=True)})
    # PRIMA: cashout incompleto → "prezzi incompleti", card ferma, niente uscita
    d = E.decide(ctx, snap, C.merge_params({"stake": 10, "ht_loss_pct": 40, "h2_loss_pct": 40}))
    assert d.telemetry["cashout"]["complete"] is True
    assert d.telemetry["cashout"]["decided"] == ["OU35|UNDER"]
    assert d.reason != "prezzi incompleti"
    # l'uscita in perdita puo' agire: si chiude la SOLA gamba ancora viva
    assert d.state == "LIVE_CLOSING"
    assert [a.market for a in d.actions if a.kind == "place"] == [E.MARKET_OU45]
    # con una perdita tollerata piu' stretta si tiene, ma la card resta VIVA
    d2 = E.decide(ctx, snap, C.merge_params({"stake": 10, "ht_loss_pct": 5, "h2_loss_pct": 5}))
    assert d2.state == "LIVE_COVERED" and d2.telemetry["cashout"]["complete"] is True


def test_c2_chiusura_in_attesa_su_selezione_decisa_viene_annullata():
    pend = E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                 price=1.3, size=11.5, ref="under_close-1-3", status="pending")
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=[under_leg(), pend], cycle_no=1)
    snap = E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() - 3600, inplay=True, minute=70,
                      goals=4, books={})
    d = E.decide(ctx, snap, C.merge_params({"stake": 10}))
    assert [a.kind for a in d.actions] == ["cancel"] and "decisa" in d.reason


# ===========================================================================
# C3 — esito REST ignoto: pending_reconcile, MAI cancelled/error per TTL
# ===========================================================================
def _force_unknown_outcome(monkeypatch):
    def fake_place(**kw):
        db = kw["db"]
        tid = kw.get("trade_id")
        if tid is not None:
            db.update_trade(int(tid), meta={"phase": "reserved",
                                            "reason": "place_exception_reconciling",
                                            "err": "timeout"})
        return X.PlaceOutcome("pending", kw["price"], kw["size"], None,
                              "place_exception_reconciling:timeout")
    monkeypatch.setattr(S.X, "place", fake_place)


def test_c3_esito_ignoto_non_diventa_cancelled_e_blocca_il_rientro(monkeypatch):
    """LIVE: Betfair non raggiungibile → la gamba resta ``pending_reconcile``
    anche dopo il TTL, la riga resta 'pending' e il bot NON rientra."""
    _force_unknown_outcome(monkeypatch)
    db = FakeDB(mode="live", params={"stake": 10, "pre_exit_mode": "taker"})

    class DeadMarket(FakeMarket):
        def list_current_orders(self):
            raise RuntimeError("Betfair giu'")

        def list_cleared_orders(self):
            raise RuntimeError("Betfair giu'")

    mk = DeadMarket()
    run(db, mk, NOW, [row(payload())])              # armata + ingresso
    leg = legs(db)[0]
    assert leg["status"] == E.STATUS_RECONCILE
    assert "reconcile_pending" in db.kinds()
    # la riga resta 'pending' (mai 'error'): un ordine reale potrebbe esistere
    assert [t["status"] for t in db.trades] == ["pending"]
    # TTL scaduto: NON viene cancellata e non si apre nulla di nuovo
    later = NOW + timedelta(seconds=S._PENDING_STALE_S + 30)
    run(db, mk, later, [row(payload(), updated=later)])
    leg = legs(db)[0]
    assert leg["status"] == E.STATUS_RECONCILE
    assert [t["status"] for t in db.trades] == ["pending"]
    assert len(legs(db)) == 1                      # nessun rientro sullo stesso evento
    assert db.events["E1"]["state"] != "ERROR"     # mai ERROR per un TTL
    assert db.events["E1"]["live"]["reconcile_pending"] is True
    assert db.events["E1"]["live"]["liability"] == 10.0   # conta nel rischio


def test_c3_gamba_riconciliata_come_abbinata_viene_confermata():
    """LIVE: l'ordine ESISTE davvero su Betfair → la gamba diventa una posizione
    vera (mai persa), con prezzo e size REALI."""
    db = FakeDB(mode="live", params={"stake": 10})
    unknown = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                    price=1.50, size=10.0, ref="under_entry-0-1", status=E.STATUS_RECONCILE)
    ctx = E.MatchCtx(state="PRE_ENTRY_PENDING", legs=[unknown])
    db.trades = [{"id": 3, "event_id": "E1", "signal_key": "under_entry-0-1", "status": "pending",
                  "market_id": "1.35", "selection_id": 1222344, "side": "back", "price": 1.5,
                  "size": 10.0, "placed_at": NOW.isoformat(),
                  "meta": {"reason": "place_exception_reconciling"}}]

    class LiveMarket(FakeMarket):
        def list_current_orders(self):
            return [{"customer_order_ref": "mike-t3", "market_id": "1.35", "selection_id": 1222344,
                     "side": "back", "size_matched": 10.0, "size_remaining": 0.0,
                     "avg_price_matched": 1.49, "bet_id": "B1"}]

        def list_cleared_orders(self):
            return []

    n = S._reconcile_unknown(db, LiveMarket(), "E1", ctx, "live", NOW)
    assert n == 1 and unknown.status == "open"
    assert unknown.matched == 10.0 and unknown.avg_price == 1.49
    assert db.trades[0]["status"] == "open" and db.trades[0]["bet_id"] == "B1"
    fix = [pl for k, pl, _ in db.activity if k == "reconcile_fix"]
    assert fix and fix[0]["action"] == "confermata"


def test_c3_liability_conta_anche_l_ordine_a_esito_ignoto():
    unknown = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                    price=1.5, size=10.0, ref="under_entry-0-1", status=E.STATUS_RECONCILE)
    assert unknown.needs_reconcile is True and unknown.is_live is False
    # peggior caso: come se fosse abbinato per intero
    assert E.event_liability([unknown], 0.05) == 10.0
    assert E.locked_pnl([unknown], 0.05) is None
    ctx = E.MatchCtx(state="WATCH", legs=[unknown])
    assert E.has_unknown_orders(ctx) is True


def test_c3_in_paper_la_riconciliazione_chiude_il_dubbio(monkeypatch):
    """PAPER: l'eccezione viene dal fill SIMULATO, nessun ordine e' mai partito
    verso Betfair → il dubbio si chiude subito, senza posizioni fantasma."""
    _force_unknown_outcome(monkeypatch)
    db = FakeDB(params={"stake": 10, "pre_exit_mode": "taker"})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    assert legs(db)[0]["status"] == E.STATUS_RECONCILE
    later = NOW + timedelta(seconds=2)
    run(db, mk, later, [row(payload(), updated=later)])
    assert any(k == "reconcile_fix" for k in db.kinds())
    assert db.trades[0]["status"] == "error"
    assert legs(db)[0]["status"] == "cancelled"


# ===========================================================================
# H1 — cash out manuale: prima i cancel, ctx intatto, nessun rientro pre-KO
# ===========================================================================
def test_h1_cashout_manuale_cancella_prima_e_non_azzera_il_contesto():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    resting = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                    price=1.48, size=10.14, ref="under_green-1-2", status="pending")
    ctx0 = {"seen_inplay": True, "ht_score": [1, 1], "last_goals": 2,
            "selections": {"OU35|UNDER": 1222344}}
    db.events["E1"] = live_event([asdict(under_leg()), asdict(resting)], ctx=ctx0)
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open", "pnl": 0},
                 {"id": 2, "event_id": "E1", "signal_key": "under_green-1-2", "status": "pending",
                  "pnl": 0, "meta": {}}]
    db.requests = [{"id": 7, "kind": "cashout", "payload": {"event_id": "E1"}, "status": "pending"}]
    p = payload(inplay=True, minute=50, sh=1, sa=1, ko=NOW - timedelta(hours=1))
    run(db, mk, NOW, [row(p)])
    req = db.requests[0]
    assert req["status"] == "done" and req["result"]["phase"] == "armed"
    assert "annullati 1 ordini" in req["result"]["message"]
    # la resting NON e' piu' viva (prima restava sul book: posizione lay scoperta)
    assert [l["status"] for l in legs(db) if l["ref"] == "under_green-1-2"] == ["cancelled"]
    # il contesto NON e' stato azzerato: le uscite HT->FT restano vive
    kept = db.events["E1"]["ctx"]
    assert kept["ht_score"] == [1, 1] and kept["last_goals"] == 2
    assert kept["selections"]["OU35|UNDER"] == 1222344


def test_h1_cashout_manuale_pre_ko_blocca_il_rientro_fino_a_riprendi():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg(role="under_entry"))], state_="PRE_OPEN",
                                 ctx={}, ko=NOW + timedelta(hours=2))
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_entry-1-1", "status": "open", "pnl": 0}]
    db.requests = [{"id": 1, "kind": "cashout", "payload": {"event_id": "E1"}, "status": "pending"}]
    run(db, mk, NOW, [row(payload())])
    assert db.requests[0]["status"] == "done"
    assert db.events["E1"]["ctx"]["no_reentry"] is True
    # "Riprendi" riabilita il rientro
    db.requests.append({"id": 2, "kind": "resume_event", "payload": {"event_id": "E1"},
                        "status": "pending"})
    run(db, mk, NOW + timedelta(seconds=2), [row(payload(), updated=NOW + timedelta(seconds=2))])
    assert db.requests[-1]["status"] == "done"
    assert not db.events["E1"]["ctx"].get("no_reentry")


def test_h1_cashout_manuale_con_feed_stantio_viene_rifiutato():
    db = FakeDB(params={"stake": 10})
    db.scanner = {"updated_at": (NOW - timedelta(minutes=5)).isoformat(), "payload": {}}
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())])
    db.requests = [{"id": 1, "kind": "cashout", "payload": {"event_id": "E1"}, "status": "pending"}]
    old = NOW - timedelta(minutes=10)
    run(db, mk, NOW, [row(payload(inplay=True, minute=50, sh=1, sa=1), updated=old)])
    assert db.requests[0]["status"] == "rejected"
    assert db.requests[0]["result"]["code"] == "feed_stantio"


# ===========================================================================
# H2 — riconciliazione mike_trades <-> positions a ogni ciclo
# ===========================================================================
def test_h2_gamba_senza_riga_viene_ricostruita():
    """Crash DOPO l'ordine: la posizione esiste ma la riga mirror no."""
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg()), asdict(over_leg())])
    db.trades = []
    run(db, mk, NOW, [row(payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(hours=1)))])
    refs = sorted(t["signal_key"] for t in db.trades)
    assert refs == ["over_cover-1-2", "under_last-1-1"]
    assert all(t["status"] == "open" for t in db.trades)
    assert all(t["meta"]["reconciled"] for t in db.trades)
    assert "reconcile_fix" in db.kinds()


def test_h2_riga_senza_gamba_diventa_orfana():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())])
    db.trades = [
        {"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open", "pnl": 0},
        {"id": 9, "event_id": "E1", "signal_key": "fantasma-1-9", "status": "pending", "pnl": 0,
         "meta": {}},
    ]
    run(db, mk, NOW, [row(payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(hours=1)))])
    ghost = next(t for t in db.trades if t["id"] == 9)
    assert ghost["meta"]["orphan"] is True and ghost["status"] == "error"   # paper: zombie
    fix = [pl for k, pl, _ in db.activity if k == "reconcile_fix"]
    assert any(p["action"] == "riga_orfana" for p in fix)


def test_h2_in_live_una_riga_orfana_non_viene_mai_chiusa_in_silenzio():
    db = FakeDB(mode="live", params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())], mode="live")
    db.trades = [
        {"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open", "pnl": 0},
        {"id": 9, "event_id": "E1", "signal_key": "fantasma-1-9", "status": "open", "pnl": 0,
         "meta": {}},
    ]
    run(db, mk, NOW, [row(payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(hours=1)))])
    ghost = next(t for t in db.trades if t["id"] == 9)
    assert ghost["status"] == "open" and ghost["meta"]["orphan"] is True


# ===========================================================================
# H3 — gambe resting mai simulate in live
# ===========================================================================
def test_h3_in_live_nessuna_lay_appoggiata_simulata(monkeypatch):
    monkeypatch.setenv("MIKE_USE_FLUMINE_QUEUE", "1")
    p = C._coerce("pre_exit_mode", "resting")
    assert p == "resting"
    eff = S._params_for(C.merge_params({"pre_exit_mode": "resting"}), True, "live")
    assert eff["pre_exit_mode"] == "taker"          # anche con la coda flumine
    eff_paper = S._params_for(C.merge_params({"pre_exit_mode": "resting"}), True, "paper")
    assert eff_paper["pre_exit_mode"] == "resting"


def test_h3_gamba_resting_gia_esistente_non_si_riempie_in_live():
    db = FakeDB(mode="live", params={"stake": 10, "pre_exit_mode": "resting"})
    mk = FakeMarket()
    resting = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                    price=1.48, size=10.14, ref="under_green-1-2", status="pending")
    db.events["E1"] = live_event([asdict(under_leg()), asdict(resting)], state_="PRE_OPEN",
                                 mode="live", ko=NOW + timedelta(hours=2))
    # mercato che scambia SOTTO il prezzo della lay: in paper si riempirebbe
    p = payload(u35=(1.40, 1.42, 30.0, 25.0))
    run(db, mk, NOW, [row(p)])
    got = [l for l in legs(db) if l["ref"] == "under_green-1-2"][0]
    assert got["matched"] == 0.0                   # nessun fill fantasma sui soldi veri


# ===========================================================================
# H4 — P&L netto per riga, closes_trade_id, exit_kind, cicli non gambe
# ===========================================================================
def test_h4_somma_delle_righe_uguale_al_netto_della_partita():
    legs_ = [under_leg(size=20.0, price=1.50), over_leg(size=4.0, price=8.0)]
    for total, expected in ((2, 20 * 0.5 * 0.95 - 4), (4, -24.0), (5, 4 * 7 * 0.95 - 20)):
        r = E.settle_legs(legs_, total, 0.05)
        assert r.net == pytest.approx(expected, abs=0.01)
        assert sum(p for _ref, _st, p in r.per_leg) == pytest.approx(r.net, abs=0.02)
    r2 = E.settle_legs(legs_, 2, 0.05)
    # la gamba vincente porta la commissione del suo mercato, la perdente no
    assert r2.per_leg[0][2] == pytest.approx(10.0 * 0.95, abs=0.01)
    assert r2.per_leg[1][2] == pytest.approx(-4.0, abs=0.01)
    assert r2.per_leg_gross[0][2] == pytest.approx(10.0, abs=0.01)
    assert r2.commission_by_market[E.MARKET_OU35] == pytest.approx(0.5, abs=0.01)


def test_h4_commissione_ripartita_fra_piu_gambe_in_utile():
    legs_ = [under_leg(size=10.0, price=1.50, role="under_entry"),
             under_leg(size=10.0, price=1.60, role="under_last")]
    legs_[1].ref = "under_last-2-2"
    r = E.settle_legs(legs_, 1, 0.05)
    assert sum(p for _r, _s, p in r.per_leg) == pytest.approx(r.net, abs=0.02)
    assert all(p > 0 for _r, _s, p in r.per_leg)


def test_h4_ogni_chiusura_sa_quale_apertura_chiude():
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[under_leg(), over_leg()], cycle_no=1)
    books = {(E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.2, back_size=99.0, best_lay=1.22,
                                                  lay_size=99.0, inplay=True),
             (E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=20.0, back_size=99.0, best_lay=22.0,
                                                 lay_size=99.0, inplay=True)}
    cancels, closes = E.force_flat_plan(ctx, books, C.merge_params({"stake": 10}), goals=1)
    assert cancels == [] and len(closes) == 2
    new = E.apply_decision(ctx, E.Decision("LIVE_CLOSING", closes, "manuale",
                                           updates={"close_reason": "manual"}), NOW.timestamp())
    assert {l.role: l.closes_ref for l in new} == {"under_close": "under_last-1-1",
                                                   "over_close": "over_cover-1-2"}


def test_h4_exit_kind_coprono_il_contratto_dichiarato():
    assert E.exit_kind_for("under_green", None) == "greenup"
    assert E.exit_kind_for("reentry_green", "profit") == "greenup"
    assert E.exit_kind_for("under_close", "profit") == "profit"
    assert E.exit_kind_for("over_close", "loss_ht") == "loss"
    assert E.exit_kind_for("under_close", "loss_2t") == "loss"
    assert E.exit_kind_for("under_close", "loss_cap") == "forced"
    assert E.exit_kind_for("reentry_green", "reentry_time") == "time"
    assert E.exit_kind_for("manual_close", "profit") == "manual"
    assert E.exit_kind_for("under_close", "manual") == "manual"
    assert E.exit_kind_for("under_close", None) == "other"
    assert set(E.EXIT_KINDS) == {"greenup", "profit", "loss", "time", "forced", "manual", "other"}


def test_h4_la_riga_di_chiusura_porta_exit_kind_e_closes_trade_id():
    db = FakeDB(params={"stake": 10, "pre_exit_mode": "taker", "cashout_profit_pct": 0.5})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg()), asdict(over_leg())])
    db.trades = [{"id": 11, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open", "pnl": 0},
                 {"id": 12, "event_id": "E1", "signal_key": "over_cover-1-2", "status": "open", "pnl": 0}]
    p = payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(hours=1),
                u35=(1.20, 1.21, 99.0, 99.0), o45=(20.0, 21.0, 99.0, 99.0))
    run(db, mk, NOW, [row(p)])
    closers = [t for t in db.trades if t.get("role") in ("under_close", "over_close")]
    assert closers, "nessuna chiusura piazzata"
    under_close = next(t for t in closers if t["role"] == "under_close")
    assert under_close["closes_trade_id"] == 11
    assert under_close["meta"]["exit_kind"] == "profit"
    assert under_close["meta"]["exit_reason"] == "profit"


# ===========================================================================
# H5 — IO Supabase: log e battito solo quando serve
# ===========================================================================
def test_h5_il_log_state_si_scrive_solo_se_lo_stato_cambia():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg()), asdict(over_leg())])
    p = payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(hours=1))
    for i in range(5):
        t = NOW + timedelta(seconds=i)
        run(db, mk, t, [row(p, updated=t)])
    assert db.kinds().count("state") == 0          # stato immutato per 5 cicli


def test_h5_heartbeat_non_piu_di_una_volta_ogni_10_secondi():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    writes = []
    orig = db.set_control

    def spy(**fields):
        if "heartbeat_at" in fields:
            writes.append(fields["heartbeat_at"])
        orig(**fields)
    db.set_control = spy
    p = payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(hours=1))
    db.events["E1"] = live_event([asdict(under_leg()), asdict(over_leg())])
    for i in range(6):
        t = NOW + timedelta(seconds=i)
        run(db, mk, t, [row(p, updated=t)])
    assert len(writes) <= 2                        # prima era uno per ciclo
    later = NOW + timedelta(seconds=30)
    run(db, mk, later, [row(p, updated=later)])
    assert len(writes) <= 3


def test_h5_lettura_incrementale_dei_trade():
    """``live_trades`` prende SOLO le righe non terminali + le regolate dopo
    ``since``: niente piu' scansione integrale a ogni ciclo."""
    calls = []

    class FakeSB:
        def table(self, name):
            calls.append(name)
            return self

        def select(self, *_a, **_k):
            return self

        def in_(self, field, values):
            calls.append(("in", field, tuple(values)))
            return self

        def range(self, a, b):
            calls.append(("range", a, b))
            return self

        def gte(self, field, value):
            calls.append(("gte", field, value))
            return self

        def order(self, *_a, **_k):
            return self

        def execute(self):
            class R:
                data = []
            return R()

    MDB._sb_orig = MDB._sb
    try:
        MDB._sb = lambda: FakeSB()
        MDB.live_trades("2026-09-12T00:00:00+00:00")
    finally:
        MDB._sb = MDB._sb_orig
    assert ("in", "status", ("open", "hedged", "pending")) in calls   # non terminali (paginate)
    assert ("gte", "settled_at", "2026-09-12T00:00:00+00:00") in calls
    assert ("range", 0, MDB.PAGE_SIZE - 1) in calls


# ===========================================================================
# M1 — ogni richiesta viene chiusa con esito leggibile
# ===========================================================================
def test_m1_richieste_chiuse_con_status_e_messaggio_italiano():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())])
    db.requests = [
        {"id": 1, "kind": "cashout", "payload": {"event_id": "SCONOSCIUTO"}, "status": "pending"},
        {"id": 2, "kind": "skip_event", "payload": {"event_id": "E1"}, "status": "pending"},
        {"id": 3, "kind": "bogus", "payload": {"event_id": "E1"}, "status": "pending"},
    ]
    run(db, mk, NOW, [row(payload(inplay=True, minute=50, sh=1, sa=1))])
    by_id = {r["id"]: r for r in db.requests}
    assert by_id[1]["status"] == "rejected" and by_id[1]["result"]["code"] == "evento_non_seguito"
    assert by_id[2]["status"] == "rejected" and by_id[2]["result"]["code"] == "posizione_aperta"
    # kind ignoto = contratto rotto fra UI e DB, non un rifiuto atteso
    assert by_id[3]["status"] == "error" and by_id[3]["result"]["code"] == "kind_non_valido"
    assert set(S._REJECT_CODES) and "kind_non_valido" not in S._REJECT_CODES
    for r in db.requests:
        assert r["result"]["message"] and isinstance(r["result"]["message"], str)


def test_m1_status_rejected_ripiega_su_error_senza_migrazione():
    """A ``mike_bot_v2.sql`` non applicata il CHECK rifiuta 'rejected': l'esito
    resta identico, cambia solo lo status."""
    seen = []

    class FakeSB:
        def table(self, _n):
            return self

        def update(self, fields):
            seen.append(dict(fields))
            return self

        def eq(self, *_a):
            return self

        def execute(self):
            if seen[-1]["status"] == "rejected":
                raise RuntimeError('violates check constraint "mike_requests_status_check"')
            class R:
                data = []
            return R()

    MDB._sb_orig = MDB._sb
    try:
        MDB._sb = lambda: FakeSB()
        MDB.set_request_status(1, "rejected", {"code": "feed_assente", "message": "no"})
    finally:
        MDB._sb = MDB._sb_orig
    assert [s["status"] for s in seen] == ["rejected", "error"]
    assert seen[-1]["result"]["code"] == "feed_assente"


# ===========================================================================
# M2 — fail_stale_processing a ogni ciclo
# ===========================================================================
def test_m2_fail_stale_processing_chiamato_a_ogni_ciclo():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    seen = []
    db.fail_stale_processing = lambda max_age_min=10: seen.append(max_age_min)
    run(db, mk, NOW, [row(payload())])
    run(db, mk, NOW + timedelta(seconds=2), [row(payload(), updated=NOW + timedelta(seconds=2))])
    assert seen == [S._STALE_REQUEST_MIN, S._STALE_REQUEST_MIN]


def test_m2_una_richiesta_bloccata_viene_chiusa_in_errore():
    calls = []

    class FakeSB:
        def table(self, _n):
            return self

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a):
            return self

        def update(self, fields):
            calls.append(dict(fields))
            return self

        def execute(self):
            if calls:
                class R:
                    data = []
                return R()

            class R2:
                data = [{"id": 5, "updated_at": "2020-01-01T00:00:00+00:00"}]
            return R2()

    MDB._sb_orig = MDB._sb
    try:
        MDB._sb = lambda: FakeSB()
        n = MDB.fail_stale_processing(10)
    finally:
        MDB._sb = MDB._sb_orig
    assert n == 1 and calls[0]["status"] == "error"
    assert calls[0]["result"]["code"] == "processing_stale"


# ===========================================================================
# M3 — i 7 parametri senza effetto: rimossi o cablati
# ===========================================================================
def test_m3_parametri_rimossi_e_cablati():
    d = C.merge_params(None)
    for key in ("max_matches", "catalogue_refresh_s", "stream_extra_lines", "min_total_matched"):
        assert key in C.REMOVED_PARAMS and key not in d
    # cablati davvero
    for key in ("settle_confirm_s", "skip_log_interval_s", "cover_max_overshoot_pct"):
        assert key in d


def test_m3_settle_confirm_s_governa_il_poll_di_regolamento():
    db = FakeDB(params={"stake": 10, "settle_confirm_s": 120})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg())], state_="LIVE_COVERED",
                                 ctx={"seen_inplay": True, "last_goals": 2,
                                      "selections": {"OU35|UNDER": 1222344, "OU45|OVER": 1222346}},
                                 ko=NOW - timedelta(hours=2))
    run(db, mk, NOW, [])                       # riga sparita: parte il settlement
    nxt = db.events["E1"]["ctx"]["settle_next_ts"]
    assert nxt == pytest.approx(NOW.timestamp() + 120, abs=1)


def test_m3_skip_log_interval_s_deduplica_i_log():
    db = FakeDB(params={"stake": 10})
    extra: dict = {}
    params = C.merge_params({"skip_log_interval_s": 300})
    assert S._log_throttled(db, extra, params, 1000.0, "skip", {"reason": "x"}, "E1") is True
    assert S._log_throttled(db, extra, params, 1100.0, "skip", {"reason": "x"}, "E1") is False
    assert S._log_throttled(db, extra, params, 1400.0, "skip", {"reason": "x"}, "E1") is True
    assert db.kinds().count("skip") == 2


def test_m3_cover_max_overshoot_pct_evita_coperture_gonfiate():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[under_leg(size=10.0, price=1.5)], cycle_no=1)
    snap = E.Snapshot(now=NOW.timestamp(), ko_at=NOW.timestamp() - 600, inplay=True, minute=10,
                      goals=1, feed_fresh=True, last_goal_ts=None,
                      books={(E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=30.0, back_size=99.0,
                                                                 best_lay=32.0, lay_size=99.0,
                                                                 inplay=True)})
    # exact_sizes OFF: X = 1.2*10/((30-1)*0.95) = 0.44 -> legalizzata a 2.00 (+355%)
    p = C.merge_params({"stake": 10, "exact_sizes": False, "cover_policy": "immediate",
                        "cover_max_overshoot_pct": 30})
    d = E.decide(ctx, snap, p)
    assert d.state == "LIVE_UNCOVERED" and "overshoot" in d.reason
    # tetto disattivato: la copertura passa (comportamento precedente)
    p2 = dict(p, cover_max_overshoot_pct=0.0)
    d2 = E.decide(ctx, snap, p2)
    assert d2.state == "LIVE_COVER_PENDING"


# ===========================================================================
# M4 — capitale a rischio = liability NETTA
# ===========================================================================
def test_m4_liability_netta_non_e_la_somma_delle_gambe():
    back = under_leg(size=10.0, price=1.50)
    # back 10 @ 1.50 coperto da una lay 10.14 @ 1.48: rischio residuo ~0
    lay = fill(E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                     price=1.48, size=10.14, ref="under_close-1-3"))
    assert E.event_liability([back], 0.0) == 10.0
    assert E.event_liability([back, lay], 0.0) <= 0.05      # non 10 + 4.8
    # un ciclo ARCHIVIATO non e' piu' capitale a rischio
    back.archived = True
    lay.archived = True
    assert E.event_liability([back, lay], 0.0) == 0.0


def test_m4_stats_open_liability_dalle_posizioni_nette():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg(size=10.0, price=1.5)),
                                  asdict(over_leg(size=2.53, price=6.0))])
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open",
                  "pnl": 0, "liability": 10.0},
                 {"id": 2, "event_id": "E1", "signal_key": "over_cover-1-2", "status": "open",
                  "pnl": 0, "liability": 2.53}]
    res = run(db, mk, NOW, [row(payload(inplay=True, minute=30, sh=0, sa=0,
                                        ko=NOW - timedelta(hours=1)))])
    st = res["stats"]
    # la somma delle righe (12.53) sovrastima: con 4 gol si perde tutto, con 0-3
    # o 5+ si perde solo una gamba
    assert st["open_liability"] == pytest.approx(12.53, abs=0.05)
    p4 = E.net_pnl_by_total([under_leg(size=10.0, price=1.5), over_leg(size=2.53, price=6.0)], 0.05)
    assert st["open_liability"] == pytest.approx(-min(p4.values()), abs=0.05)
    assert db.events["E1"]["live"]["liability"] == st["open_liability"]


# ===========================================================================
# M5 — "se chiudo ora" SEMPRE netto, lato servizio
# ===========================================================================
def test_m5_cashout_netto_esposto_per_la_ui():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg(size=20.0, price=1.5)),
                                  asdict(over_leg(size=4.0, price=8.0))])
    # book SOTTO la soglia del 5%: la posizione resta aperta e la card mostra
    # "se chiudo ora" (Under lay 1.33 → +2.43 netto, Over lay 12.5 → -1.44)
    p = payload(inplay=True, minute=40, sh=0, sa=0, ko=NOW - timedelta(hours=1),
                u35=(1.32, 1.33, 99.0, 99.0), o45=(12.0, 12.5, 99.0, 99.0))
    run(db, mk, NOW, [row(p)])
    assert state(db) == "LIVE_COVERED"
    co = db.events["E1"]["live"]["cashout"]
    for key in ("net", "gross", "base", "per", "complete", "commission"):
        assert key in co
    assert co["commission"] == 0.05 and co["base"] == 24.0
    assert co["net"] < co["gross"]                     # netto SEMPRE, mai lordo
    assert set(co["per"]) == {"OU35|UNDER", "OU45|OVER"}
    assert co["net"] == pytest.approx(sum(co["per"].values()), abs=0.02)


# ===========================================================================
# M6 — giornata operativa = giorno di PIAZZAMENTO (Europe/Rome)
# ===========================================================================
def test_m6_aggregati_per_giorno_di_piazzamento():
    day_start = datetime(2026, 9, 11, 22, 0, tzinfo=timezone.utc)   # mezzanotte Rome del 12
    rows = [
        # apertura di IERI regolata OGGI: NON e' della giornata di oggi
        {"id": 1, "event_id": "A", "status": "won", "pnl": 2.0,
         "placed_at": "2026-09-11T20:00:00+00:00", "settled_at": "2026-09-12T09:00:00+00:00"},
        # apertura di OGGI + chiusura di oggi
        {"id": 2, "event_id": "B", "status": "lost", "pnl": -1.0,
         "placed_at": "2026-09-12T08:00:00+00:00", "settled_at": "2026-09-12T10:00:00+00:00"},
        {"id": 3, "event_id": "B", "closes_trade_id": 2, "status": "won", "pnl": 0.5,
         "placed_at": "2026-09-12T09:00:00+00:00", "settled_at": "2026-09-12T10:00:00+00:00"},
    ]
    agg = MDB.aggregate_rows(rows, day_start)
    assert agg["realized_total"] == 1.5
    assert agg["realized_today"] == -0.5           # solo la posizione APERTA oggi
    assert agg["cycles_today"] == 1 and agg["events_today"] == 1
    # il CICLO (apertura + chiusura) e' UNA posizione persa, non 1 vinta + 1 persa
    assert (agg["won"], agg["lost"]) == (1, 1)
    assert (agg["won_today"], agg["lost_today"]) == (0, 1)


# ===========================================================================
# M7 — fedelta' paper: nessun fill a feed stantio
# ===========================================================================
def test_m7_nessun_fill_paper_con_feed_stantio():
    db = FakeDB(params={"stake": 10, "pre_exit_mode": "taker"})
    db.scanner = {"updated_at": (NOW - timedelta(minutes=5)).isoformat(), "payload": {}}
    mk = FakeMarket()
    old = NOW - timedelta(minutes=10)
    info = F.event_info("E1", payload())
    leg = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                price=1.50, size=10.0, ref="under_entry-0-1")
    book = E.Book(best_back=1.50, back_size=30.0, best_lay=1.52, lay_size=25.0)
    out = S.execute_place(db=db, market=mk, info=info, leg=leg, book=book, mode="paper",
                          params=C.merge_params({"stake": 10}), now=NOW, dry=False,
                          feed_fresh=False)
    assert out == "cancelled" and leg.matched == 0.0
    assert [pl["reason"] for k, pl, _ in db.activity if k == "no_fill"] == ["feed_stantio"]
    assert db.trades == []                         # nessuna riserva, nessun ordine
    assert old < NOW


def test_m7_nessun_fill_resting_con_feed_stantio():
    db = FakeDB(params={"stake": 10, "pre_exit_mode": "resting"})
    db.scanner = {"updated_at": (NOW - timedelta(minutes=5)).isoformat(), "payload": {}}
    mk = FakeMarket()
    resting = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                    price=1.48, size=10.14, ref="under_green-1-2", status="pending")
    db.events["E1"] = live_event([asdict(under_leg(role="under_entry")), asdict(resting)],
                                 state_="PRE_OPEN", ko=NOW + timedelta(hours=2))
    old = NOW - timedelta(minutes=10)
    run(db, mk, NOW, [row(payload(u35=(1.40, 1.42, 30.0, 25.0)), updated=old)])
    got = [l for l in legs(db) if l["ref"] == "under_green-1-2"][0]
    assert got["matched"] == 0.0 and "fill_resting" not in db.kinds()


# ===========================================================================
# M8 — finestra di ingresso incoerente con il ramo pre-KO dello scanner
# ===========================================================================
def test_m8_config_warn_se_la_finestra_supera_il_ramo_pre_ko(monkeypatch):
    monkeypatch.setenv("SAFE_PRE_KO_OU_HOURS", "3")
    db = FakeDB(params={"stake": 10, "entry_hours_before_ko": 6})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    warns = [pl for k, pl, _ in db.activity if k == "config_warn"]
    assert warns and warns[0]["critical"] is True
    assert warns[0]["entry_hours_before_ko"] == 6 and warns[0]["scanner_pre_ko_hours"] == 3
    assert "SAFE_PRE_KO_OU_HOURS" in warns[0]["message"]
    # non si ripete a ogni ciclo
    run(db, mk, NOW + timedelta(seconds=2), [row(payload(), updated=NOW + timedelta(seconds=2))])
    assert len([1 for k, _, _ in db.activity if k == "config_warn"]) == 1


def test_m8_config_warn_se_il_ramo_pre_ko_e_spento(monkeypatch):
    monkeypatch.setenv("SAFE_PRE_KO_OU_HOURS", "")
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    warns = [pl for k, pl, _ in db.activity if k == "config_warn"]
    assert warns and "SPENTO" in warns[0]["message"]


# ===========================================================================
# M9 — mercato VOID / partita abbandonata
# ===========================================================================
def test_m9_riconoscimento_mercato_annullato():
    assert S.market_voided({"status": "CLOSED", "runners": [{"status": "REMOVED"},
                                                            {"status": "REMOVED"}]}) is True
    # C4 (review): 'INACTIVE' NON e' un void Betfair (mercato non ancora attivo)
    assert S.market_voided({"status": "INACTIVE", "runners": []}) is False
    assert S.market_voided({"status": "VOIDED", "runners": []}) is True
    assert S.market_voided({"status": "CLOSED", "runners": [{"status": "WINNER"},
                                                            {"status": "LOSER"}]}) is False
    assert S.market_voided({"status": "OPEN", "runners": [{"status": "ACTIVE"}]}) is False
    assert S.market_voided(None) is False


def test_m9_mercato_void_regola_la_partita_a_zero():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    db.events["E1"] = live_event([asdict(under_leg()), asdict(over_leg())], state_="LIVE_COVERED",
                                 ctx={"seen_inplay": True, "last_goals": 1,
                                      "selections": {"OU35|UNDER": 1222344, "OU35|OVER": 1222345,
                                                     "OU45|UNDER": 1222347, "OU45|OVER": 1222346}},
                                 ko=NOW - timedelta(hours=2))
    db.trades = [{"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open", "pnl": 0},
                 {"id": 2, "event_id": "E1", "signal_key": "over_cover-1-2", "status": "open", "pnl": 0}]
    void_book = {"status": "CLOSED", "runners": [{"selection_id": 1222344, "status": "REMOVED"},
                                                 {"selection_id": 1222345, "status": "REMOVED"}]}
    mk.books["1.35"] = dict(void_book, market_id="1.35")
    mk.books["1.45"] = dict(void_book, market_id="1.45")
    res = run(db, mk, NOW, [])                   # riga sparita + mercato annullato
    assert res["settled"] == 1 and state(db) == "SETTLED"
    assert db.events["E1"]["settled_pnl"] == 0.0
    assert [t["status"] for t in db.trades] == ["void", "void"]
    assert all(t["pnl"] == 0.0 for t in db.trades)
    settled = [pl for k, pl, _ in db.activity if k == "settled"][0]
    assert settled["void"] is True and settled["reason"] == "mercato_annullato"


# ===========================================================================
# M10 / R2 — le RPC Mike passano TUTTI gli argomenti (firma unica)
# ===========================================================================
def test_r2_le_rpc_mike_passano_8_e_4_argomenti_con_day_by_placed():
    sql = (MIGRATIONS / "mike_history_v2.sql").read_text(encoding="utf-8")
    # le firme VECCHIE vengono eliminate: mai piu' "function ... is not unique"
    assert "DROP FUNCTION IF EXISTS public.trading_daily_history(text,text,text,text,date,date,numeric);" in sql
    assert "DROP FUNCTION IF EXISTS public.trading_day_trades(text,text,date);" in sql
    # una sola firma viva, 8 e 4 argomenti, con mike_trades ammessa
    assert "p_day_by        text DEFAULT 'settled'" in sql
    assert "p_day_by      text DEFAULT 'settled'" in sql
    assert sql.count("'omega_trades', 'safe_strategy_trades', 'mike_trades'") == 2
    # get_mike_daily: 8 argomenti, l'ultimo 'placed'
    daily = sql.split("CREATE OR REPLACE FUNCTION public.get_mike_daily")[1]
    call = daily.split("public.trading_daily_history(")[1].split(");")[0]
    args = [a.strip() for a in call.split(",\n")]
    assert len(args) == 8 and args[-1] == "'placed'"
    # get_mike_day_trades: 4 argomenti, l'ultimo 'placed'
    assert "public.trading_day_trades('mike_trades', NULL, p_day, 'placed')" in sql


def test_m17_l08_nella_migrazione_dello_storico():
    sql = (MIGRATIONS / "mike_history_v2.sql").read_text(encoding="utf-8")
    # M-17: clamp a 400 giorni, non un errore
    assert "v_from_d := p_to - 400;" in sql and "v_clamped := true;" in sql
    assert "intervallo troppo ampio" not in sql
    assert "'window_clamped', true" in sql
    # L-08: hedged_closed non conta i pending; commissione per mercato
    assert "c.status NOT IN ('error','pending')" in sql
    assert "WHEN paid IS NOT NULL THEN paid" in sql
    # obiettivo dichiarato come NON snapshot (Mike non ha obiettivo giornaliero)
    assert "'goal_snapshot', false" in sql


def test_mike_bot_v2_espone_il_contratto_per_la_ui():
    sql = (MIGRATIONS / "mike_bot_v2.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS closes_trade_id" in sql
    assert "'pending','processing','done','rejected','error'" in sql
    for key in ("'requests'", "'aggregates'", "'activity'", "'events'", "'trades'"):
        assert key in sql
    for key in ("open_count", "open_liability", "realized_today", "realized_total",
                "won_today", "lost_today", "cycles_today", "events_today", "live_now"):
        assert key in sql
    assert "'day_by',          'placed'" in sql


# ===========================================================================
# L1..L5
# ===========================================================================
def test_l1_gli_ordini_live_di_mike_portano_il_ref_di_mike():
    class FakeOmegaMarket:
        CUSTOMER_STRATEGY_REF = "omega"

    fake = FakeOmegaMarket()
    S._RealMarket._bind_strategy_ref(fake)
    assert fake.CUSTOMER_STRATEGY_REF == "mike" == C.CUSTOMER_STRATEGY_REF
    assert S._STRATEGY_REF == "mike"


def test_l2_lo_stop_giornaliero_usa_il_giorno_di_roma():
    # 11/09 23:30 UTC = 12/09 01:30 a Roma: giornata operativa del 12
    late = datetime(2026, 9, 11, 23, 30, tzinfo=timezone.utc)
    assert S._operating_day_key(late) == "2026-09-12"
    assert S._operating_day_key(datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)) == "2026-09-11"


def test_l3_lo_stop_giornaliero_vede_anche_il_bloccato():
    """Un ciclo chiuso in perdita ma non ancora pagato dal mercato DEVE contare."""
    db = FakeDB(params={"stake": 10, "daily_loss_stop": 5})
    mk = FakeMarket()
    back = under_leg(size=100.0, price=1.50, role="under_entry")
    back.placed_at = NOW.timestamp() - 600
    lay = fill(E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                     price=1.70, size=88.24, ref="under_close-1-2",
                     placed_at=NOW.timestamp() - 300))
    db.events["E1"] = live_event([asdict(back), asdict(lay)], state_="FLAT")
    locked = E.locked_pnl([back, lay], 0.05)
    assert locked is not None and locked < -5
    res = run(db, mk, NOW, [row(payload(inplay=True, minute=50, sh=1, sa=1,
                                        ko=NOW - timedelta(hours=1)))])
    assert res["stats"]["daily_stop"] is True
    assert res["stats"]["locked_open"] == pytest.approx(locked, abs=0.02)
    assert res["stats"]["realized_today"] == 0.0       # nulla e' ancora REGOLATO
    stop_log = [pl for k, pl, _ in db.activity if k == "daily_stop"]
    assert stop_log and stop_log[0]["day"] == "2026-09-12"


def test_l3_una_partita_ancora_viva_non_conta_nel_bloccato():
    assert E.locked_pnl([under_leg()], 0.05) is None   # esposizione aperta: nulla e' deciso


def test_l4_partite_gia_in_gioco_non_vengono_armate():
    p_live = payload(inplay=True, minute=10, sh=0, sa=0, ko=NOW - timedelta(minutes=10))
    info = F.event_info("E1", p_live)
    assert F.is_candidate(info, p_live, now=NOW.timestamp(), params=C.merge_params(None)) is False


def test_l5_tutti_i_kind_di_attivita_sono_dichiarati():
    """L5 — l'elenco dei kind e' il CONTRATTO con la UI: se il backend ne
    aggiunge uno senza dichiararlo, la UI mostra un badge grigio in inglese."""
    src = (Path(S.__file__)).read_text(encoding="utf-8")
    import re

    found = set(re.findall(r'db\.log\(\s*"([a-z_]+)"', src))
    found |= set(re.findall(r'_log_throttled\([^\n]*?"([a-z_]+)",\s*$', src, re.M))
    declared = {
        "armed", "state", "place", "place_pending", "place_deferred", "place_resting",
        "fill_resting", "cancel", "skip", "no_fill", "would_place", "size_legalized",
        "pre_cycle", "cover", "cover_wait", "settled", "settle_fallback", "settling_reverted",
        "error", "stop", "daily_stop", "loss_exit", "cashout", "close_retries_exhausted",
        "reconcile_pending", "reconcile_fix", "resting_live_unsupported", "feed_line_missing",
        "config_warn", "schema_warn", "skip_event", "resume_event",
    }
    assert found - declared == set(), f"kind non dichiarati: {sorted(found - declared)}"


# ===========================================================================
# C1/C2 feed: la funzione dello scanner resta retro-compatibile
# ===========================================================================
def test_scanner_le_linee_di_mike_restano_vive_anche_se_decise():
    # comportamento invariato senza il flag (motore opportunita')
    assert SC.is_opp_market_live("OVER_UNDER_35", 3.5, 60, 2, 2) is False
    assert SC.is_opp_market_live("OVER_UNDER_45", 4.5, 60, 2, 2) is True
    # partita seguita da Mike: entrambe le linee restano nel feed
    assert SC.is_opp_market_live("OVER_UNDER_35", 3.5, 60, 2, 2, mike=True) is True
    assert SC.is_opp_market_live("OVER_UNDER_45", 4.5, 60, 3, 2, mike=True) is True
    # gli altri mercati non sono toccati dal flag
    assert SC.is_opp_market_live("OVER_UNDER_25", 2.5, 60, 2, 1, mike=True) is False
    assert SC.is_opp_market_live("BOTH_TEAMS_TO_SCORE", None, 60, 1, 1, mike=True) is False


def test_scanner_pre_ko_resta_invariato():
    assert SC.is_opp_market_live("OVER_UNDER_35", 3.5, None, None, None, pre_ko=True) is True
    assert SC.is_opp_market_live("OVER_UNDER_25", 2.5, None, None, None, pre_ko=True) is False


# ===========================================================================
# Trader mindset: nessuna posizione invisibile, nessun fill fantasma
# ===========================================================================
def test_nessuna_posizione_invisibile_dopo_un_crash_a_meta_ciclo():
    """Il servizio muore dopo l'ordine e prima della persistenza dell'evento:
    al ciclo dopo la riga c'e' e la gamba viene ritrovata dalla riconciliazione."""
    db = FakeDB(params={"stake": 10, "pre_exit_mode": "taker"})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    assert len(db.trades) == 1 and db.trades[0]["status"] == "open"
    # simulazione del crash: lo stato dell'evento torna indietro (gamba persa)
    db.events["E1"]["positions"] = []
    db.events["E1"]["state"] = "WATCH"
    t = NOW + timedelta(seconds=2)
    run(db, mk, t, [row(payload(), updated=t)])
    ghost = db.trades[0]
    assert ghost["meta"]["orphan"] is True         # la riga NON resta muta
    assert any(pl.get("action") == "riga_orfana" for k, pl, _ in db.activity
               if k == "reconcile_fix")


def test_h5_la_riconciliazione_non_legge_nulla_se_lo_specchio_combacia():
    """H5 — il pre-controllo usa UNA query (``open_trades``) per tutto il ciclo:
    se righe e gambe combaciano non si legge partita per partita."""
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    reads = []
    orig = db.trades_for_event
    db.trades_for_event = lambda eid: (reads.append(eid), orig(eid))[1]
    db.events["E1"] = live_event([asdict(under_leg()), asdict(over_leg())])
    db.trades = [
        {"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open", "pnl": 0,
         "liability": 10.0, "meta": {}},
        {"id": 2, "event_id": "E1", "signal_key": "over_cover-1-2", "status": "open", "pnl": 0,
         "liability": 2.53, "meta": {}},
    ]
    p = payload(inplay=True, minute=30, sh=0, sa=0, ko=NOW - timedelta(hours=1))
    run(db, mk, NOW, [row(p)])
    assert reads == []                             # nessuna lettura per partita
    # se manca una riga il pre-controllo se ne accorge e la riconciliazione parte
    db.trades = [db.trades[0]]
    t = NOW + timedelta(seconds=3)
    run(db, mk, t, [row(p, updated=t)])
    assert reads and "reconcile_fix" in db.kinds()


def test_h5_pre_controllo_puro():
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[under_leg(), over_leg()], cycle_no=1)
    idx = {"E1": {"under_last-1-1", "over_cover-1-2"}}
    assert S._mirror_is_aligned(ctx, idx, "E1") is True
    assert S._mirror_is_aligned(ctx, {"E1": {"under_last-1-1"}}, "E1") is False   # gamba senza riga
    assert S._mirror_is_aligned(ctx, {"E1": idx["E1"] | {"x-1-9"}}, "E1") is False  # riga orfana
    assert S._mirror_is_aligned(ctx, None, "E1") is False                          # indice assente
    # una gamba ARCHIVIATA (ciclo chiuso) non deve far scattare la lettura
    for leg in ctx.legs:
        leg.archived = True
    assert S._mirror_is_aligned(ctx, {"E1": set()}, "E1") is True
