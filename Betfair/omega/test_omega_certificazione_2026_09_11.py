"""CERTIFICAZIONE Omega §16 (11/09/2026) — un test per ogni correzione del servizio
uscita dalle quattro review (logica, matematica, SQL, motore). Fake, nessuna rete.

  C1  ref ordine PER GAMBA (omega-t<id>) sul lay automatico live
  H2  eventi con trade MANUALI esclusi dall'automatico (run_once → scan legs)
  H4  freschezza DURA del punteggio per le decisioni (30 s), morbida altrove
  H5  fit di mercato calcolato UNA volta per (evento, 5′, punteggio)
  H6  green-up 'failed' NON terminale: cooldown e nuovo giro
  H7  green-up CIECO (senza feed) → allarme una volta
  M1  cap max_events conta le PARTITE (events_today), non le gambe
  M3  cache λ: TTL sulle fonti di ripiego, fixture per processo
  M5  reconcile: meta FUSO (il blocco modello sopravvive)
  M10 reconcile/settle KO → il ciclo continua e logga
  M12 log skip ripetitivi dedupati (una riga ogni 10′)
  L5  settlement in coppia senza accessor delle chiusure → non regola
  F1/F2 green-up con la P CALIBRATA e tetto di fine gara
  C3  letture paginate (PostgREST tronca a 1000 righe)
"""
from __future__ import annotations

import time
from datetime import timedelta
from types import SimpleNamespace

import pytest

from Betfair.omega import omega_config
from Betfair.omega import omega_db
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_model as M
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import NOW, FakeDB, FakeMarket, _control, _cs, _event, _open_snapshot
from Betfair.omega.test_omega_giornata_gambe_2026_09_11 import _DB, _Market, _books, _params, _run
from Betfair.omega import test_omega_greenup_2026_09_10 as G
from Betfair.omega.test_omega_greenup_2026_09_10 import lambdas  # noqa: F401 (fixture)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    import Betfair.stream.db as sdb
    monkeypatch.setattr(sdb, "get_fixture_prematch_lambdas", lambda fid: None)
    S._LAMBDA_CACHE.clear()
    S._EMPIRICAL_CACHE.clear()
    S._MARKET_FIT_CACHE.clear()
    S._SKIP_SEEN.clear()
    S._BLIND_CYCLES.clear()
    S._DAILY_GOAL_WRITTEN.clear()


# ---------------------------------------------------------------- C1 ref per gamba
def test_c1_lay_live_automatico_porta_il_ref_per_gamba():
    db = FakeDB(_control(mode="live"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    assert S.run_once(market=market, db=db, now=NOW)["placed"] == 1
    tid = db.trades[0]["id"]
    assert market.placed[0]["customer_ref"] == f"omega-t{tid}"
    assert E.candidate_customer_refs(db.trades[0])[0] == f"omega-t{tid}"


# ---------------------------------------------------------------- H2 manuale escluso
def test_h2_evento_con_trade_manuale_escluso_dalle_gambe_automatiche(monkeypatch):
    db = FakeDB(_control(params={"engine": "legs"}))
    db.manual_event_ids = lambda: {"1.100"}
    seen = {}

    def fake_scan(**kw):
        seen.update(kw)
        return 0
    monkeypatch.setattr(S, "scan_and_place_legs", fake_scan)
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert "1.100" in seen["traded_ids"]
    # accessor rotto → NESSUN ingresso (mai a occhi chiusi), errore loggato
    db2 = FakeDB(_control(params={"engine": "legs"}))
    db2.manual_event_ids = lambda: 1 / 0
    seen.clear()
    res = S.run_once(market=market, db=db2, now=NOW)
    assert res.get("skipped") == "manual_ids_failed" and not seen


# ---------------------------------------------------------------- H4 freschezza dura
def test_h4_punteggio_vecchio_ok_per_le_stime_ma_non_per_decidere():
    ev = SimpleNamespace(event_id="e1", name="A v B", open_date=NOW - timedelta(minutes=60))
    old = lambda eid: S.LiveScore(minute=55, score_home=1, score_away=0,  # noqa: E731
                                  updated_at=(NOW - timedelta(seconds=45)).isoformat())
    st, _, _ = S._live_state_for(None, ev, old, NOW)
    assert st is not None and st.minute == 55                    # stime/statistiche: 180 s
    st, _, _ = S._live_state_for(None, ev, old, NOW, decision=True)
    assert st is None                                            # decisione: 30 s
    fresh = lambda eid: S.LiveScore(minute=55, score_home=1, score_away=0,  # noqa: E731
                                    updated_at=(NOW - timedelta(seconds=10)).isoformat())
    st, _, _ = S._live_state_for(None, ev, fresh, NOW, decision=True)
    assert st is not None
    assert S.DECISION_MAX_AGE_S == 25.0 and S.SELECT_SCORE_MAX_AGE_S == 25   # stesso tetto (F6)


# ---------------------------------------------------------------- H5 cache fit di mercato
def test_h5_fit_di_mercato_una_volta_per_evento_5min_punteggio(monkeypatch):
    calls = []
    monkeypatch.setattr(M, "lambdas_from_market_grid",
                        lambda payload, state, league_id, rho: calls.append(1) or (1.2, 0.9, {"loss": 0.1}))
    st = M.LiveState(minute=62, score_home=1, score_away=0)
    assert S._market_fit_cached("e1", {"cs": {}}, st, 135) == (1.2, 0.9, {"loss": 0.1})
    S._market_fit_cached("e1", {"cs": {}}, M.LiveState(minute=64, score_home=1, score_away=0), 135)
    assert len(calls) == 1                                       # stesso blocco di 5′: cache
    S._market_fit_cached("e1", {"cs": {}}, M.LiveState(minute=64, score_home=1, score_away=1), 135)
    S._market_fit_cached("e1", {"cs": {}}, M.LiveState(minute=66, score_home=1, score_away=1), 135)
    assert len(calls) == 3                                       # gol e nuovo blocco: ricalcolo


# ---------------------------------------------------------------- H6 cooldown del failed
def test_h6_greenup_failed_riprova_dopo_il_cooldown(lambdas):
    db = G._db_with_model()
    tr = G._trade(db)
    p = G._params(greenup_settle_delay_s=0, greenup_retry_s=20, greenup_max_attempts=2)
    thin = G._payload(70, 1, 2, cs=[G._sel(14, "1 - 3", 8.2, 8.0, back_size=1.0)])
    assert G._run(db, thin, p, now=NOW) == 1
    assert G._run(db, thin, p, now=NOW + timedelta(seconds=21)) == 1
    assert G._run(db, thin, p, now=NOW + timedelta(seconds=42)) == 0      # cap → failed
    g = db.get_trade(tr["id"])["meta"]["greenup"]
    assert g["failed"] is True and g.get("failed_ts")
    errs = [e for e in G._logs(db, "error") if e.get("reason") == "greenup_attempts_exhausted"]
    assert len(errs) == 1 and errs[0]["critical"] is True and errs[0]["retry_in_s"] == 300
    # dentro il cooldown: niente
    assert G._run(db, thin, p, now=NOW + timedelta(seconds=200)) == 0
    assert len(G._closings(db, tr["id"])) == 2
    # cooldown scaduto: NUOVO giro di tentativi (la posizione ha ancora liability)
    monkeypatch_time = NOW + timedelta(seconds=42 + 301)
    S._BLIND_CYCLES.clear()
    assert G._run(db, thin, p, now=monkeypatch_time) == 1
    g = db.get_trade(tr["id"])["meta"]["greenup"]
    assert g["failed"] is False and g["rounds"] == 1 and g["attempts"] == 1
    assert len(G._closings(db, tr["id"])) == 3


# ---------------------------------------------------------------- H7 green-up cieco
def test_h7_posizione_viva_senza_feed_allarme_una_volta(lambdas):
    db = G._db_with_model()
    tr = G._trade(db)
    p = G._params(greenup_settle_delay_s=0)
    for _ in range(5):
        assert S.process_auto_greenup(params=p, market=FakeMarket([], None, _open_snapshot()),
                                      db=db, now=NOW, feed=lambda eid: None) == 0
    blind = G._logs(db, "greenup_blind")
    assert len(blind) == 1 and blind[0]["trade_id"] == tr["id"] and blind[0]["cycles"] == 3
    # il feed torna: il contatore si azzera
    G._run(db, G._payload(50, 1, 0, cs=[G._sel(14, "1 - 3", 55.0, 50.0)]), p)
    assert S._BLIND_CYCLES.get(tr["id"]) is None


# ---------------------------------------------------------------- M1 cap per partita
def test_m1_cap_max_events_conta_le_partite_non_le_gambe():
    ev = SimpleNamespace(event_id="e1", name="A v B", open_date=NOW - timedelta(minutes=30))
    db = _DB({"daily_goal": 10.0, "mode": "paper"}, events={"e1": {"league_id": 135, "model": {
        "lambda_pre": [1.4, 1.1], "lambda_source": "pre_ko_odds"}}})
    market = _Market(_books("e1"))
    p = _params(max_events=2)
    # 4 gambe fatte su 2 partite (events_today=2) → cap raggiunto: nessuna partita nuova
    agg = {"realized_today": 0.0, "matches_traded_today": 4, "events_today": 2, "open_liability": 0.0}
    n = S.scan_and_place_legs(control={"daily_goal": 10.0, "mode": "paper"}, params=p, events=[ev],
                              traded_ids=set(), traded_legs=set(), aggregates=agg, market=market, db=db,
                              now=NOW, score_lookup=lambda eid: S.LiveScore(minute=30, score_home=0, score_away=0, updated_at=NOW.isoformat()))
    assert n == 0
    # 4 gambe ma su UNA sola partita → c'è ancora spazio per una seconda partita
    agg = {"realized_today": 0.0, "matches_traded_today": 4, "events_today": 1, "open_liability": 0.0}
    n = S.scan_and_place_legs(control={"daily_goal": 10.0, "mode": "paper"}, params=p, events=[ev],
                              traded_ids=set(), traded_legs=set(), aggregates=agg, market=market, db=db,
                              now=NOW, score_lookup=lambda eid: S.LiveScore(minute=30, score_home=0, score_away=0, updated_at=NOW.isoformat()))
    assert n == 1


# ---------------------------------------------------------------- M3 TTL della cache λ
def test_m3_cache_lambda_ttl_solo_sulle_fonti_di_ripiego(monkeypatch):
    db = _DB({}, events={"e1": {"league_id": 135, "model": {"lambda_pre": [1.5, 1.1], "lambda_source": "pre_ko_odds"}}})
    assert S._prematch_lambdas(db, "e1", None)[3] == "pre_ko_odds"
    # la stessa chiamata, con la cache scaduta, RILEGGE (la fixture può essere arrivata)
    val, ts = S._LAMBDA_CACHE["e1"]
    S._LAMBDA_CACHE["e1"] = (val, ts - S.LAMBDA_CACHE_TTL_S - 1)
    db.events["e1"]["model"] = {"lambda_pre": [1.7, 0.8], "lambda_source": "pre_ko_odds"}
    assert S._prematch_lambdas(db, "e1", None)[:2] == (1.7, 0.8)
    # una FIXTURE in cache non scade mai (i λ pre-match non cambiano)
    S._LAMBDA_CACHE["e1"] = ((1.0, 1.0, 135, "fixture"), 0.0)
    assert S._prematch_lambdas(db, "e1", None) == (1.0, 1.0, 135, "fixture")


# ---------------------------------------------------------------- M5 meta fuso nel reconcile
def test_m5_reconcile_paper_conserva_il_blocco_modello():
    db = FakeDB(_control())
    tid = db.insert_trade({"event_id": "1.100", "market_id": "m", "selection_id": 3, "runner_name": "2 - 1",
                           "side": "lay", "mode": "paper", "origin": "auto", "price": 75.0, "size": 2.0,
                           "liability": 148.0, "status": "pending", "phase": "ft_cs",
                           "meta": {"model": {"p_model": 0.004, "lambda_source": "fixture"}, "runners": {"3": "2 - 1"}}})
    assert S.reconcile_pending(market=FakeMarket([], None, _open_snapshot()), db=db, now=NOW) == 1
    t = next(x for x in db.trades if x["id"] == tid)
    assert t["status"] == "open" and t["meta"]["reconciled"] == "paper"
    assert t["meta"]["model"]["p_model"] == 0.004 and t["meta"]["runners"] == {"3": "2 - 1"}


# ---------------------------------------------------------------- M10 fasi protette
def test_m10_reconcile_o_settle_ko_non_fermano_il_ciclo(monkeypatch):
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    monkeypatch.setattr(S, "reconcile_pending", lambda **kw: 1 / 0)
    monkeypatch.setattr(S, "settle_open", lambda **kw: 1 / 0)
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1                                   # il ciclo è andato avanti
    reasons = {p.get("reason") for k, p in db.activity if k == "error"}
    assert {"reconcile_phase_failed", "settle_phase_failed"} <= reasons


# ---------------------------------------------------------------- M12 dedup dei log
def test_m12_skip_ripetuti_una_riga_ogni_dieci_minuti(monkeypatch):
    db = FakeDB(_control())
    t = [1000.0]
    monkeypatch.setattr(S.time, "time", lambda: t[0])
    for _ in range(5):
        S._log_dedup(db, ("e1", "ft_cs", "no_market"), "skip", {"event_id": "e1"})
    S._log_dedup(db, ("e2", "ft_cs", "no_market"), "skip", {"event_id": "e2"})
    assert len([1 for k, _ in db.activity if k == "skip"]) == 2
    t[0] += S.SKIP_LOG_EVERY_S + 1
    S._log_dedup(db, ("e1", "ft_cs", "no_market"), "skip", {"event_id": "e1"})
    assert len([1 for k, _ in db.activity if k == "skip"]) == 3


# ---------------------------------------------------------------- L5 senza accessor
def test_l5_apertura_con_chiusure_senza_accessor_non_si_regola_come_nuda():
    db = FakeDB(_control())
    db.trades.append({"id": 1, "event_id": "1.100", "market_id": "m-1.100", "selection_id": 3, "size": 2.0,
                      "price": 75.0, "commission": 0.05, "runner_name": "2 - 1", "side": "lay", "status": "open",
                      "placed_at": NOW.isoformat(), "meta": {"hedge_pending_ids": [2]}})
    market = FakeMarket([], None, SimpleNamespace(status="CLOSED", inplay=False, closed=True, voided=False,
                                                  winner_selection_id=1, runners=[]))
    assert S.settle_open(params=omega_config.resolve_params({}), market=market, db=db, now=NOW) == 0
    assert db.trades[0]["status"] == "open"


# ---------------------------------------------------------------- F1/F2 green-up a P calibrata
def test_f1_f2_greenup_usa_la_p_del_modello_con_tetto_di_fine_gara(monkeypatch, lambdas):
    db = G._db_with_model()
    G._trade(db, score="1-0", minute=60)
    st = M.LiveState(minute=70, score_home=1, score_away=2)
    monkeypatch.setattr(M, "score_probs", lambda **kw: {(1, 3): 0.04})
    tr = db.trades[0]
    # fattore di coda 1,3 e calibratore spento: P > grezza (la stessa P dell'ingresso)
    p, src = S._greenup_p_lose(db=db, tr=tr, payload={"cs": {}}, laid=(1, 3), state=st, half=False,
                               prices={"back": 20.0},
                               params=G._params(model_tail_factor=1.3, model_calibration="off"))
    assert src == "model" and 0.04 < p <= 0.052
    # grezza pura con fattore 1
    p0, _ = S._greenup_p_lose(db=db, tr=tr, payload={"cs": {}}, laid=(1, 3), state=st, half=False,
                              prices={"back": 20.0}, params=G._params(model_tail_factor=1.0))
    assert p0 == 0.04
    # 89′: il modello dice 0,1 % ma il back a 1,50 dice 67 % → vince il mercato
    monkeypatch.setattr(M, "score_probs", lambda **kw: {(1, 3): 0.001})
    p, src = S._greenup_p_lose(db=db, tr=tr, payload={"cs": {}}, laid=(1, 3),
                               state=M.LiveState(minute=89, score_home=1, score_away=3), half=False,
                               prices={"back": 1.5}, params=G._params())
    assert src == "model_floor_market" and p == pytest.approx(0.6667, abs=1e-3)
    # gamba HT: tetto dal 43′
    p, src = S._greenup_p_lose(db=db, tr=tr, payload={"ht": {}}, laid=(1, 3),
                               state=M.LiveState(minute=44, score_home=1, score_away=3), half=True,
                               prices={"back": 1.2}, params=G._params())
    assert src == "model_floor_market" and p == pytest.approx(0.8333, abs=1e-3)


# ---------------------------------------------------------------- C3 letture paginate
class _Q:
    """Fake del query builder PostgREST: pagina per range, ordina per id."""
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.lo, self.hi = 0, 999

    def select(self, cols):
        return self

    def eq(self, k, v):
        self.filters.append(lambda r: r.get(k) == v); return self

    def neq(self, k, v):
        self.filters.append(lambda r: r.get(k) != v); return self

    def in_(self, k, vals):
        self.filters.append(lambda r: r.get(k) in set(vals)); return self

    def order(self, k, desc=False):
        return self

    def range(self, lo, hi):
        self.lo, self.hi = lo, hi; return self

    def execute(self):
        rows = [r for r in sorted(self.rows, key=lambda r: r["id"]) if all(f(r) for f in self.filters)]
        return SimpleNamespace(data=rows[self.lo:self.hi + 1])


def test_c3_gambe_gia_trattate_oltre_le_1000_righe(monkeypatch):
    rows = [{"id": i, "event_id": f"e{i}", "phase": "ht_cs", "status": "won", "origin": "auto",
             "closes_trade_id": None} for i in range(1, 2501)]
    rows[-1]["origin"] = "manual"
    monkeypatch.setattr(omega_db, "_sb", lambda: SimpleNamespace(table=lambda name: _Q(rows)))
    legs = omega_db.traded_legs()
    assert ("e2500", "ht_cs") in legs and len(legs) == 2500          # prima: troncato a 1000
    assert omega_db.manual_event_ids() == {"e2500"}
    assert len(omega_db.traded_event_ids()) == 2500
    assert omega_db.minute_transitions(1, 0, "x") is None            # errore (RPC assente) → None, mai []


# =====================================================================================
# SECONDA PASSATA (test mentali sul codice corretto) — un test per ogni correzione
# =====================================================================================
class _MarketRaises(FakeMarket):
    """Il place LIVE solleva DOPO l'invio (timeout di rete): esito IGNOTO."""
    def place_lay_live(self, **kw):
        self.placed.append(kw)
        raise RuntimeError("read timeout dopo placeOrders")


class _MarketKilled(FakeMarket):
    """FOK ucciso da Betfair: esito CERTO negativo (nessun ordine vivo)."""
    def place_lay_live(self, **kw):
        self.placed.append(kw)
        from Betfair.omega import omega_market as OM
        return OM.PlaceResult(ok=True, order_status="EXPIRED", bet_id="bx", size_matched=0.0, avg_price_matched=None)


def test_2p_f1_place_live_a_esito_ignoto_resta_pending_in_riconciliazione():
    S._LEG_RETRY.clear()
    db = FakeDB(_control(mode="live"))
    market = _MarketRaises([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1                                   # gamba OCCUPATA, non ripiazzabile
    t = db.trades[0]
    assert t["status"] == "pending" and t["meta"]["reason"] == "place_exception_reconciling"
    assert t["meta"]["runners"]                                 # il meta della riserva sopravvive
    errs = [p for k, p in db.activity if k == "error" and p.get("reason") == "place_exception_reconciling"]
    assert len(errs) == 1 and errs[0]["critical"] is True
    # ciclo dopo: NESSUN secondo ordine (la riga pending è ancora lì)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5))
    assert len(market.placed) == 1


def test_2p_f3_esito_certo_negativo_libera_la_gamba_con_budget_di_tentativi():
    S._LEG_RETRY.clear()
    db = FakeDB(_control(mode="live"))
    market = _MarketKilled([_event()], _cs(), _open_snapshot())
    assert S.run_once(market=market, db=db, now=NOW)["placed"] == 0
    assert db.trades == []                                      # riserva cancellata, niente 'error'
    assert len(market.placed) == 1
    # entro 30 s: niente; dopo: nuovo tentativo; al 3° esaurito
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=10))
    assert len(market.placed) == 1
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=31))
    assert len(market.placed) == 2
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=62))
    assert len(market.placed) == 3
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=93))
    assert len(market.placed) == 3                              # budget esaurito per la partita
    skips = [p for k, p in db.activity if k == "skip" and p.get("reason") == "live_not_matched"]
    assert [s["attempt"] for s in skips] == [1, 2, 3]


def test_2p_f2_mercato_sospeso_non_si_entra():
    ev = SimpleNamespace(event_id="e1", name="A v B", open_date=NOW - timedelta(minutes=30))
    db = _DB({"daily_goal": 10.0, "mode": "paper"}, events={"e1": {"league_id": 135, "model": {
        "lambda_pre": [1.4, 1.1], "lambda_source": "pre_ko_odds"}}})

    class _Susp(_Market):
        def read_market(self, cs):
            snap = super().read_market(cs)
            snap.status = "SUSPENDED"
            return snap
    n = S.scan_and_place_legs(control={"daily_goal": 10.0, "mode": "paper"}, params=_params(), events=[ev],
                              traded_ids=set(), traded_legs=set(),
                              aggregates={"realized_today": 0.0, "events_today": 0, "open_liability": 0.0},
                              market=_Susp(_books("e1")), db=db, now=NOW,
                              score_lookup=lambda eid: S.LiveScore(minute=30, score_home=0, score_away=0, updated_at=NOW.isoformat()))
    assert n == 0 and db.trades == []
    assert any(k == "skip" and p.get("reason") == "market_suspended" for k, p in db.activity)


def test_2p_f5_un_evento_rotto_non_ferma_gli_altri(monkeypatch):
    ev1 = SimpleNamespace(event_id="bad", name="X v Y", open_date=NOW - timedelta(minutes=30))
    ev2 = SimpleNamespace(event_id="e1", name="A v B", open_date=NOW - timedelta(minutes=30))
    db = _DB({"daily_goal": 10.0, "mode": "paper"}, events={"e1": {"league_id": 135, "model": {
        "lambda_pre": [1.4, 1.1], "lambda_source": "pre_ko_odds"}}})
    real = S._leg_market

    def boom(market, ev, mtype, payload):
        if ev.event_id == "bad":
            raise RuntimeError("REST KO")
        return real(market, ev, mtype, payload)
    monkeypatch.setattr(S, "_leg_market", boom)
    n = S.scan_and_place_legs(control={"daily_goal": 10.0, "mode": "paper"}, params=_params(), events=[ev1, ev2],
                              traded_ids=set(), traded_legs=set(),
                              aggregates={"realized_today": 0.0, "events_today": 0, "open_liability": 0.0},
                              market=_Market(_books("e1")), db=db, now=NOW,
                              score_lookup=lambda eid: S.LiveScore(minute=30, score_home=0, score_away=0, updated_at=NOW.isoformat()))
    assert n == 1 and db.trades[0]["event_id"] == "e1"
    assert any(k == "error" and p.get("reason") == "scan_event_failed" and p["event_id"] == "bad" for k, p in db.activity)


def test_2p_f2_uscita_copertura_completa_con_residuo_di_arrotondamento():
    from Betfair.safe_strategy import execution as X
    tr = {"side": "lay", "price": 55.0, "size": 2.16, "commission": 0.05}
    # back 24,10 @ 4,90 copre 24,10·4,90/55 = 2,147 → 2,15 di stake: residuo 0,01 da arrotondamento
    closing = {"side": "back", "price": 4.90, "size": 24.10, "status": "open"}
    st = X.hedge_state(tr, [closing])
    assert st["hedged_size"] == 2.15 and st["residual_size"] == 0.01
    assert st["complete"] is True and st["locked_pnl"] is not None        # prima: 'open' per sempre
    # esposizioni già (quasi) uguali su ogni esito: hedge di fatto completo
    closing2 = {"side": "back", "price": 4.90, "size": 24.24, "status": "open"}
    st2 = X.hedge_state(tr, [closing2])
    assert st2["complete"] is True and abs(st2["if_win"] - st2["if_lose"]) < 0.05


def test_2p_f3_niente_da_chiudere_non_e_terminale(monkeypatch, lambdas):
    db = G._db_with_model()
    tr = G._trade(db, score="1-0", minute=60)
    from Betfair.safe_strategy import execution as X
    monkeypatch.setattr(X, "close_trade", lambda **kw: {"error": "niente_da_chiudere"})
    # distanza 0 (bancato = punteggio corrente) → exit incondizionato → close_trade "niente"
    pay = G._payload(70, 1, 3, cs=[G._sel(14, "1 - 3", 1.8, 1.7)])
    assert G._run(db, pay, G._params(greenup_settle_delay_s=0)) == 0
    g = db.get_trade(tr["id"])["meta"]["greenup"]
    assert g.get("sent") is not True and g["attempts"] == 0          # si riprova al ciclo dopo
    assert tr["id"] in [t["id"] for t in S._greenup_candidates(db)]  # ancora candidato


def test_2p_f3_senza_prezzo_opposto_si_aspetta(lambdas):
    db = G._db_with_model()
    tr = G._trade(db, score="1-0", minute=60)
    pay = G._payload(70, 1, 3, cs=[{"selection_id": 14, "name": "1 - 3", "lay": 1.8, "lay_size": 40.0,
                                    "back": None, "back_size": 0.0, "runner_status": "ACTIVE"}])
    assert G._run(db, pay, G._params(greenup_settle_delay_s=0)) == 0
    waits = G._logs(db, "greenup_wait")
    assert waits and waits[-1]["wait"] == "prezzo_opposto_non_disponibile"
    assert "greenup" not in db.get_trade(tr["id"])["meta"]           # nessuna "uscita inviata" fittizia


def test_2p_f5_chiusura_orfana_con_sorella_gia_regolata():
    from Betfair.safe_strategy import execution as X
    parent = {"id": 1, "side": "lay", "price": 55.0, "size": 2.16, "status": "lost", "pnl": -63.80, "commission": 0.05}
    sib = {"id": 2, "closes_trade_id": 1, "side": "back", "price": 4.90, "size": 12.12, "status": "won", "pnl": 46.5}
    orphan = {"id": 3, "closes_trade_id": 1, "side": "back", "price": 4.90, "size": 12.12, "status": "open"}
    db = FakeDB(_control())
    db.trades += [parent, sib, orphan]
    assert X.settle_orphan_closing(db=db, closing=orphan, parent=parent, commission=0.05, now=NOW, siblings=[sib])
    # netto di mercato con TUTTE le gambe: −116,64 + 47,27 + 47,27 = −22,1 → nessuna commissione
    net = -116.64 + 2 * 12.12 * 3.90
    assert parent["pnl"] + sib["pnl"] + orphan["pnl"] == pytest.approx(round(net, 2), abs=0.02)


def test_2p_f6_ordine_chiuso_senza_size_libera_la_riserva():
    tr = {"origin": "auto", "id": 7, "event_id": "1.100", "market_id": "m", "selection_id": 4, "side": "lay",
          "size": 2.0, "price": 50.0, "placed_at": "2026-09-11T10:00:00+00:00"}
    cleared = [{"customer_order_ref": "omega-t7", "market_id": "m", "selection_id": 4, "side": "LAY",
                "size_settled": 0.0, "price": 50.0, "bet_id": "b9"}]
    d = E.reconcile_decision(tr, [], cleared, "2026-09-11T10:05:00+00:00")
    assert d["action"] == "free"


def test_2p_f1_report_timeout_e_esito_ignoto(monkeypatch):
    from Betfair.omega import omega_market as OM
    monkeypatch.setattr(OM, "call_mutating", lambda fn: {"status": "TIMEOUT", "instructionReports": []})
    with pytest.raises(RuntimeError):
        OM.place_order_live(market_id="m", selection_id=4, price=50, size=2, event_id="1.1", side="lay",
                            customer_ref="omega-t7")
    monkeypatch.setattr(OM, "call_mutating", lambda fn: {"status": "FAILURE", "errorCode": "PROCESSED_WITH_ERRORS",
                                                         "instructionReports": [{"status": "FAILURE", "errorCode": "MARKET_SUSPENDED"}]})
    r = OM.place_order_live(market_id="m", selection_id=4, price=50, size=2, event_id="1.1", side="lay")
    assert r.ok is False and r.size_matched == 0.0                    # rifiuto CERTO, non eccezione


def test_2p_f7_batch_book_in_errore_non_e_mercato_sparito(monkeypatch):
    from Betfair.omega import omega_market as OM

    def _raise(fn):
        raise RuntimeError("5xx")
    monkeypatch.setattr(OM, "call", _raise)
    mk = OM.CorrectScoreMarket(market_id="m1", event_id="e", event_name="", market_start_time=None, runner_names={})
    assert OM.read_markets([mk]) == {}                                # assente ≠ None


def test_2p_f01_shrinkage_con_prior_limitato_e_wilson_sulla_media_pesata():
    from Betfair.omega import omega_empirical as EMP
    # 10 casi di lega senza uscite contro un globale piccolo (200, 0 uscite): ≈ globale, non 2,5× più basso
    assert EMP.shrunk_upper(0, 10, 0, 200) == pytest.approx(0.0126, abs=5e-4)
    assert EMP.p_upper(0, 200) == pytest.approx(0.0133, abs=5e-4)
    # lega grandissima (3000 casi, 0 uscite) contro globale 1 %: la lega parla davvero
    assert EMP.shrunk_upper(0, 3000, 100, 10000) < 0.004
    # con n_lega = 0 → globale puro
    assert EMP.shrunk_upper(0, 0, 3, 1000) == EMP.p_upper(3, 1000)


def test_2p_f02_gol_totali_dal_pareggio():
    p = M.devig_1x2(1.5, 4.2, 6.5)
    t = M.total_goals_from_1x2(p[0], p[2])
    assert 2.8 < t < 3.4                                                 # ≈ 3,05 (review)
    lh, la = M.split_lambdas_1x2(p[0], p[2], t)
    ph, pd, pa = M._full_match_1x2(lh, la, M.DEFAULT_RHO)
    assert abs(pd - p[1]) < 0.01 and abs(ph - p[0]) < 0.01
    # partita chiusa (tanti pareggi) → pochi gol
    q = M.devig_1x2(2.7, 2.9, 3.1)
    assert M.total_goals_from_1x2(q[0], q[2]) < t


def test_2p_f4_filtro_di_liquidita_con_la_size_cappata():
    st = M.LiveState(minute=60, score_home=0, score_away=0)
    probs = {(3, 1): 0.004, (1, 3): 0.005}
    runners = [E.ScoreRunner(1, "3 - 1", lay_price=80.0, lay_size=6.0, lay_ladder=((80.0, 6.0),)),
               E.ScoreRunner(2, "1 - 3", lay_price=90.0, lay_size=6.0, lay_ladder=((90.0, 6.0),))]
    # size "da target" 158 € ma cap di liability 100 € → a 80 la size vera è 1,26 €: 6 € al best bastano
    sel = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120, min_liquidity=1,
                            p_max=0.02, size_needed=158.0)
    assert sel is None
    sel = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120, min_liquidity=1,
                            p_max=0.02, size_needed=158.0, liability_cap=100.0)
    assert sel is not None and sel.name == "3 - 1"


def test_2p_m4_heartbeat_anche_a_bot_fermo():
    db = FakeDB(_control(status="stopped"))
    db.control.pop("heartbeat_at", None)
    S.run_once(market=FakeMarket([], None, _open_snapshot()), db=db, now=NOW)
    assert db.control.get("heartbeat_at") == NOW.isoformat()
