"""OMEGA v2 (09/09 sera): modello condizionato + due gambe per partita.

Garanzie (nessuna rete/DB):
  - griglia dei gol residui normalizzata, traslata sul punteggio corrente,
    orizzonte HT ridotto rispetto al FT, più gol residui a inizio partita;
  - selezione PER MODELLO: mai aggregati, mai irraggiungibili/adiacenti, mai
    P>p_max né P≥1/quota; vince la P più bassa, poi il prezzo più basso;
  - target di gamba: metà partita, intero se la 1T è mancata;
  - scan_and_place_legs: 1T → HALF_TIME_SCORE, 2T → CORRECT_SCORE, una sola
    volta per gamba, trade con phase + audit modello, gate obiettivo/max eventi;
  - run_once dispatch 'legs' (default) vs 'single'; trade v1 senza gamba = evento chiuso.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from Betfair.omega import omega_config
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_model as M
from Betfair.omega import omega_service as S

NOW = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------- modello
def test_score_probs_normalizzate_e_traslate():
    st = M.LiveState(minute=60, score_home=1, score_away=0)
    probs = M.score_probs(lh_pre=1.5, la_pre=1.1, rho=-0.13, state=st, league_id=None, half=False)
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    assert all(h >= 1 and a >= 0 for (h, a) in probs)          # mai sotto il punteggio corrente
    assert probs[(1, 0)] > probs[(3, 3)] > probs[(5, 5)]        # la coda è coda
    assert (0, 0) not in probs


def test_orizzonte_ht_meno_gol_del_ft_e_piu_gol_a_inizio_partita():
    st = M.LiveState(minute=25, score_home=0, score_away=0)
    p_ht = M.score_probs(lh_pre=1.4, la_pre=1.2, rho=-0.13, state=st, league_id=None, half=True)
    p_ft = M.score_probs(lh_pre=1.4, la_pre=1.2, rho=-0.13, state=st, league_id=None, half=False)
    assert p_ht[(0, 0)] > p_ft[(0, 0)]                          # al 45' lo 0-0 è più probabile che al 90'
    lh25, _ = M.residual_lambdas(1.4, 1.2, st, None, half=False)
    lh70, _ = M.residual_lambdas(1.4, 1.2, M.LiveState(70, 0, 0), None, half=False)
    assert lh25 > lh70


def test_lambda_da_quote_pre_ko_e_devig():
    probs = M.devig_1x2(2.0, 3.5, 4.0)
    assert probs is not None and abs(sum(probs) - 1.0) < 1e-9 and probs[0] > probs[2]
    lam = M.lambdas_from_pre_ko({"home": 2.0, "draw": 3.5, "away": 4.0})
    assert lam is not None and lam[0] > lam[1] and abs(sum(lam) - M.DEFAULT_TOTAL_GOALS) < 1e-6
    assert M.lambdas_from_pre_ko(None) is None and M.lambdas_from_pre_ko({"home": 0}) is None


def _runner(sid, name, lay, size):
    return E.ScoreRunner(selection_id=sid, name=name, lay_price=lay, lay_size=size)


def test_select_by_model_regole():
    st = M.LiveState(minute=60, score_home=1, score_away=0)
    probs = M.score_probs(lh_pre=1.5, la_pre=1.0, rho=-0.13, state=st, league_id=None, half=False)
    runners = [
        _runner(1, "1 - 0", 3.0, 100),                # adiacente / troppo probabile
        _runner(2, "2 - 0", 6.0, 100),                # distanza 1 → escluso
        _runner(3, "1 - 3", 60.0, 50),                # candidato
        _runner(4, "4 - 0", 80.0, 50),                # candidato
        _runner(5, "0 - 3", 200.0, 50),               # irraggiungibile (casa già 1)
        _runner(6, "Any Other Home Win", 30.0, 500),  # aggregato: mai
        _runner(7, "3 - 3", 90.0, 1.0),               # liquidità insufficiente
    ]
    sel = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120,
                            min_liquidity=5, p_max=0.02, size_needed=4.0)
    assert sel is not None and sel.name in ("1 - 3", "4 - 0")
    other = "4 - 0" if sel.name == "1 - 3" else "1 - 3"
    assert sel.p_model <= probs[E.parse_scoreline(other)]      # vince la P più bassa
    assert sel.p_model < sel.p_implied and sel.edge > 0
    # p_max stretto → nessuno; fascia prezzi stretta → nessuno
    assert M.select_by_model(runners, probs, state=st, price_min=20, price_max=120,
                             min_liquidity=5, p_max=1e-9) is None
    assert M.select_by_model(runners, probs, state=st, price_min=200, price_max=300,
                             min_liquidity=5, p_max=0.5) is None


def test_select_by_model_mai_piu_probabile_del_mercato():
    st = M.LiveState(minute=30, score_home=0, score_away=0)
    probs = {(2, 2): 0.10, (3, 0): 0.001}
    runners = [_runner(1, "2 - 2", 5.0, 100), _runner(2, "3 - 0", 40.0, 100)]
    sel = M.select_by_model(runners, probs, state=st, price_min=1.01, price_max=1000,
                            min_liquidity=1, p_max=0.5)
    assert sel is not None and sel.name == "3 - 0"      # 2-2: P(0.10) ≥ 1/5 → escluso


def test_leg_target():
    assert M.leg_target(4.0, "ht_cs", ht_done=False) == 2.0
    assert M.leg_target(4.0, "ft_cs", ht_done=True) == 2.0
    assert M.leg_target(4.0, "ft_cs", ht_done=False) == 4.0     # 1T mancata: la 2T porta tutto
    assert M.leg_target(-1.0, "ht_cs", ht_done=False) == 0.0


def test_config_v2_default_e_clamp():
    p = omega_config.resolve_params({})
    assert p["engine"] == "legs" and p["ht_entry_max"] <= 45 and p["ft_entry_min"] >= 45
    p = omega_config.resolve_params({"engine": "boh", "ht_entry_min": 44, "ht_entry_max": 10, "model_p_max_pct": 0})
    assert p["engine"] == "legs" and p["ht_entry_min"] == 10 and p["ht_entry_max"] == 44
    assert p["model_p_max_pct"] == 0.01
    assert omega_config.resolve_params({"engine": "single"})["engine"] == "single"


# --------------------------------------------------------------- servizio v2
class _Market:
    """Mercato fake: HT e FT per evento, book configurabile, place paper."""

    def __init__(self, books):
        self.books = books      # (event_id, market_type) → list[ScoreRunner]
        self.placed = []

    def get_event_market_by_type(self, event_id, event_name, market_type):
        if (event_id, market_type) not in self.books:
            return None
        return SimpleNamespace(market_id=f"m-{event_id}-{market_type}", event_id=event_id,
                               event_name=event_name, market_start_time=NOW - timedelta(minutes=60),
                               runner_names={r.selection_id: r.name for r in self.books[(event_id, market_type)]})

    def read_market(self, cs):
        key = (cs.event_id, cs.market_id.split("-", 2)[2])
        return SimpleNamespace(status="OPEN", inplay=True, closed=False, voided=False,
                               winner_selection_id=None, runners=list(self.books[key]))

    def read_book(self, market_id, runner_names):
        return None

    def place_lay_live(self, **kw):
        raise AssertionError("mai live nei test")


class _DB:
    def __init__(self, control, events=None):
        self.control = control
        self.trades = []
        self.activity = []
        self.events = events or {}
        self._id = 0

    def read_control(self):
        return self.control

    def log(self, kind, payload=None):
        self.activity.append((kind, payload or {}))

    def get_event(self, event_id):
        return self.events.get(event_id)

    def insert_trade(self, trade):
        if any(t["event_id"] == trade["event_id"] and (t.get("phase") or "") == (trade.get("phase") or "")
               and t.get("origin", "auto") == "auto" for t in self.trades):
            raise Exception("unique auto leg")
        self._id += 1
        row = dict(trade); row["id"] = self._id
        self.trades.append(row)
        return self._id

    def update_trade(self, trade_id, **fields):
        for t in self.trades:
            if t["id"] == trade_id:
                t.update(fields)

    def delete_trade(self, trade_id):
        self.trades = [t for t in self.trades if t["id"] != trade_id]

    def traded_event_ids(self):
        return {t["event_id"] for t in self.trades}

    def traded_legs(self):
        out = set()
        for t in self.trades:
            if t.get("status") == "error":
                continue
            ph = t.get("phase")
            out |= {(t["event_id"], ph)} if ph else {(t["event_id"], "ht_cs"), (t["event_id"], "ft_cs")}
        return out


def _books(event_id):
    ht = [_runner(1, "0 - 0", 2.5, 200), _runner(2, "1 - 0", 4.0, 100), _runner(3, "2 - 1", 30.0, 60),
          _runner(4, "3 - 0", 45.0, 40), _runner(5, "0 - 3", 70.0, 40)]
    ft = [_runner(11, "1 - 0", 3.0, 200), _runner(12, "2 - 0", 5.0, 100), _runner(13, "3 - 0", 25.0, 60),
          _runner(14, "1 - 3", 55.0, 40), _runner(15, "4 - 1", 90.0, 40), _runner(16, "Any Other Away Win", 40.0, 500)]
    return {(event_id, "HALF_TIME_SCORE"): ht, (event_id, "CORRECT_SCORE"): ft}


def _params(**over):
    base = {"engine": "legs", "price_min": 20, "price_max": 120, "min_lay_liquidity": 5,
            "model_p_max_pct": 3.0, "execution_mode": "rest", "commission_pct": 5}
    base.update(over)
    return omega_config.resolve_params(base)


def _lookup(minute, sh, sa):
    return lambda eid: S.LiveScore(minute=minute, score_home=sh, score_away=sa, updated_at=NOW.isoformat())


@pytest.fixture
def lambdas(monkeypatch):
    import Betfair.stream.db as sdb
    monkeypatch.setattr(sdb, "get_fixture_prematch_lambdas", lambda fid: (1.6, 1.1, 135))
    S._LAMBDA_CACHE.clear()


def _run(db, market, ev, params, minute, sh, sa, legs=None):
    agg = {"realized_today": 0.0, "matches_traded_today": 0, "open_liability": 0.0}
    # obiettivo 10 € su 1 partita → 5 € a gamba: size ≈5.3 € (entro la liquidità dei book fake)
    return S.scan_and_place_legs(
        control={"daily_goal": 10.0, "mode": "paper"}, params=params, events=[ev],
        traded_ids=set(), traded_legs=legs if legs is not None else set(), aggregates=agg,
        market=market, db=db, now=NOW, score_lookup=_lookup(minute, sh, sa))


def test_gamba_1t_sul_half_time_score(lambdas):
    ev = SimpleNamespace(event_id="e1", name="Nord v Sud", open_date=NOW - timedelta(minutes=31))
    db = _DB({"daily_goal": 100.0, "mode": "paper"}, events={"e1": {"fixture_id": 7, "league_id": 135}})
    market = _Market(_books("e1"))
    assert _run(db, market, ev, _params(), minute=30, sh=0, sa=0) == 1, db.activity
    t = db.trades[0]
    assert t["phase"] == "ht_cs" and t["market_id"] == "m-e1-HALF_TIME_SCORE"
    assert t["minute_at_entry"] == 30 and t["score_at_entry"] == "0-0" and t["status"] == "open"
    assert t["runner_name"] in ("3 - 0", "0 - 3") and t["meta"]["model"]["horizon"] == "HT"
    assert t["meta"]["model"]["p_model"] < t["meta"]["model"]["p_implied"]
    assert t["target"] == 5.0                      # (10−0)/1 partita → metà alla gamba 1T
    # stesso ciclo/gamba di nuovo → nulla (già in traded_legs)
    assert _run(db, market, ev, _params(), minute=32, sh=0, sa=0, legs=db.traded_legs()) == 0


def test_gamba_2t_sul_correct_score_e_target_intero_se_1t_mancata(lambdas):
    ev = SimpleNamespace(event_id="e2", name="Nord v Sud", open_date=NOW - timedelta(minutes=70))
    db = _DB({"daily_goal": 100.0, "mode": "paper"}, events={"e2": {"fixture_id": 7, "league_id": 135}})
    market = _Market(_books("e2"))
    assert _run(db, market, ev, _params(), minute=60, sh=1, sa=0) == 1, db.activity
    t = db.trades[0]
    assert t["phase"] == "ft_cs" and t["market_id"] == "m-e2-CORRECT_SCORE"
    assert t["runner_name"] in ("1 - 3", "4 - 1") and t["target"] == 10.0    # 1T mancata → tutto il target
    assert t["score_at_entry"] == "1-0"


def test_fuori_finestra_o_fase_sbagliata_niente(lambdas):
    ev = SimpleNamespace(event_id="e3", name="A v B", open_date=NOW - timedelta(minutes=10))
    db = _DB({"daily_goal": 100.0, "mode": "paper"}, events={"e3": {"fixture_id": 7, "league_id": 135}})
    market = _Market(_books("e3"))
    assert _run(db, market, ev, _params(), minute=10, sh=0, sa=0) == 0        # prima della finestra 1T
    assert _run(db, market, ev, _params(), minute=44, sh=0, sa=0) == 0        # dopo ht_entry_max
    assert _run(db, market, ev, _params(), minute=85, sh=0, sa=0) == 0        # dopo ft_entry_max
    assert db.trades == []


def test_senza_lambda_si_salta_mai_a_occhi_chiusi():
    S._LAMBDA_CACHE.clear()
    ev = SimpleNamespace(event_id="e4", name="A v B", open_date=NOW - timedelta(minutes=31))
    db = _DB({"daily_goal": 100.0, "mode": "paper"}, events={})   # nessuna fixture, nessun pre-KO
    market = _Market(_books("e4"))
    assert _run(db, market, ev, _params(), minute=30, sh=0, sa=0) == 0
    assert any(k == "skip" and p.get("reason") == "no_model_lambdas" for k, p in db.activity)


def test_gate_obiettivo_e_max_eventi(lambdas):
    ev = SimpleNamespace(event_id="e5", name="A v B", open_date=NOW - timedelta(minutes=31))
    db = _DB({"daily_goal": 100.0, "mode": "paper"}, events={"e5": {"fixture_id": 7, "league_id": 135}})
    market = _Market(_books("e5"))
    agg = {"realized_today": 100.0, "matches_traded_today": 0, "open_liability": 0.0}
    assert S.scan_and_place_legs(control={"daily_goal": 100.0, "mode": "paper"}, params=_params(),
                                 events=[ev], traded_ids=set(), traded_legs=set(), aggregates=agg,
                                 market=market, db=db, now=NOW, score_lookup=_lookup(30, 0, 0)) == 0
    agg = {"realized_today": 0.0, "matches_traded_today": 1, "open_liability": 0.0}
    assert S.scan_and_place_legs(control={"daily_goal": 100.0, "mode": "paper"}, params=_params(max_events=1),
                                 events=[ev], traded_ids=set(), traded_legs=set(), aggregates=agg,
                                 market=market, db=db, now=NOW, score_lookup=_lookup(30, 0, 0)) == 0


def test_trade_v1_senza_gamba_chiude_l_evento(lambdas):
    ev = SimpleNamespace(event_id="e6", name="A v B", open_date=NOW - timedelta(minutes=31))
    db = _DB({"daily_goal": 100.0, "mode": "paper"}, events={"e6": {"fixture_id": 7, "league_id": 135}})
    db.trades.append({"id": 99, "event_id": "e6", "phase": None, "status": "open", "origin": "auto"})
    market = _Market(_books("e6"))
    assert _run(db, market, ev, _params(), minute=30, sh=0, sa=0, legs=db.traded_legs()) == 0


def test_fake_market_non_tocca_il_feed():
    assert S._feed_state(SimpleNamespace(), "x") is None
    assert S._entry_marks(SimpleNamespace(), "x", NOW) == {}
