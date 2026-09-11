"""§14 (11/09/2026): giornata = partite del giorno, due gambe SEMPRE, risultati reali.

Garanzie (nessuna rete/DB):
  - aggregati: il P&L di oggi è quello delle POSIZIONI PIAZZATE oggi (le
    chiusure ereditano il giorno dell'apertura); ieri regolato oggi → ieri;
  - gambe residue: 2 per partita non toccata, 1 se una gamba è fatta o la sua
    finestra è passata, cap max_events; target di gamba = (G−R)/gambe;
  - λ: catena fixture → λ persistiti sull'evento → pre-KO → hint dal trade
    1T → OVER/UNDER live; persistenza best-effort; mai a occhi chiusi;
  - la gamba 2T viene piazzata ANCHE senza fixture né pre-KO (caso 10/09:
    746 skip 'no_model_lambdas') grazie al mercato O/U in stream;
  - risultati reali 1T/2T: dal feed (halfTimeScore/fullTimeScore, fase) e dal
    WINNER al settlement (meta.runners salvato al piazzamento);
  - tabella empirica HT→FT: shrinkage per lega, veto = max(modello, dati);
  - run_once: stats con gambe residue / target di gamba + snapshot obiettivo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from Betfair.omega import omega_config
from Betfair.omega import omega_empirical as EMP
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_model as M
from Betfair.omega import omega_service as S

NOW = datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc)          # 16:00 Europe/Rome
DAY = E.day_start_utc(NOW)                                        # 11/09 00:00 Rome


# ------------------------------------------------------------ aggregati per giornata
def test_aggregati_giornata_uguale_partite_del_giorno():
    yday = (DAY - timedelta(hours=8)).isoformat()      # ieri sera
    today = (DAY + timedelta(hours=10)).isoformat()    # oggi
    rows = [
        # gamba di IERI regolata OGGI (servizio riavviato al mattino): NON è di oggi
        {"id": 1, "status": "won", "pnl": 2.57, "placed_at": yday, "settled_at": today},
        # chiusura (green-up) di ieri regolata oggi → segue l'apertura: ieri
        {"id": 2, "status": "won", "pnl": 2.16, "placed_at": yday, "settled_at": today},
        {"id": 3, "status": "lost", "pnl": -24.24, "placed_at": yday, "settled_at": today, "closes_trade_id": 2},
        # posizione di OGGI regolata oggi
        {"id": 4, "status": "won", "pnl": 3.0, "placed_at": today, "settled_at": today},
        # aperta oggi
        {"id": 5, "status": "open", "pnl": 0.0, "liability": 50.0, "placed_at": today},
        # chiusura ancora aperta: mai una partita in più, mai liability doppia
        {"id": 6, "status": "open", "pnl": 0.0, "liability": 9.0, "placed_at": today, "closes_trade_id": 5},
    ]
    agg = E.aggregate_trades(rows, DAY)
    assert agg["realized_today"] == 3.0
    assert agg["realized_profit"] == pytest.approx(2.57 + 2.16 - 24.24 + 3.0)
    assert agg["matches_traded_today"] == 2 and agg["matches_traded"] == 4
    assert agg["open_liability"] == 50.0 and agg["matches_open"] == 1


def test_aggregati_chiusura_senza_apertura_nelle_righe_usa_il_proprio_giorno():
    today = (DAY + timedelta(hours=10)).isoformat()
    rows = [{"id": 9, "status": "lost", "pnl": -1.0, "placed_at": today, "settled_at": today, "closes_trade_id": 999}]
    assert E.aggregate_trades(rows, DAY)["realized_today"] == -1.0


# ------------------------------------------------------------------ gambe residue
def _ev(eid, minutes_ago):
    return SimpleNamespace(event_id=eid, open_date=NOW - timedelta(minutes=minutes_ago))


def test_legs_remaining_conta_le_gambe_piazzabili():
    events = [_ev("a", -60), _ev("b", 30), _ev("c", 60), _ev("d", 95), _ev("e", 30)]
    legs, matches = E.legs_remaining(events, {("e", "ht_cs")}, now=NOW, ht_entry_max=40, ft_entry_max=80)
    # orologio corretto dell'intervallo (review HIGH-1): a: 2 (non iniziata) · b: 2 ·
    # c (60′ orologio = 45′ reali): solo 2T · d (95′ orologio = 80′ reali): 2T ancora
    # in finestra · e: 1T fatta → solo 2T
    assert (legs, matches) == (7, 5)
    legs, matches = E.legs_remaining(events, {("e", "ht_cs"), ("e", "ft_cs")}, now=NOW,
                                     ht_entry_max=40, ft_entry_max=80, excluded_ids={"a"})
    assert (legs, matches) == (4, 3)
    # minuto REALE dal feed quando c'è: c al 66′ → solo 2T; d all'88′ → fuori finestra
    legs, matches = E.legs_remaining(events, set(), now=NOW, ht_entry_max=40, ft_entry_max=80,
                                     minute_of=lambda e: {"c": 66, "d": 88}.get(e))
    assert (legs, matches) == (7, 4)
    # nessun floor silenzioso: 0 gambe = 0
    assert E.legs_remaining([_ev("z", 95)], set(), now=NOW, ht_entry_max=40, ft_entry_max=70) == (0, 0)
    # cap max_events: 1 partita ancora ammessa → al più 2 gambe
    legs, matches = E.legs_remaining(events, set(), now=NOW, ht_entry_max=40, ft_entry_max=80,
                                     max_events=3, traded_count=2)
    assert (legs, matches) == (2, 1)
    assert E.legs_remaining([], set(), now=NOW, ht_entry_max=40, ft_entry_max=80) == (0, 0)


# -------------------------------------------------------------- risultati reali
def _payload(**over):
    base = {"minute": 60, "score_home": 1, "score_away": 0, "inplay": True,
            "score_raw": {"matchStatus": "SecondHalf",
                          "score": {"home": {"score": "1", "halfTimeScore": "0", "fullTimeScore": ""},
                                    "away": {"score": "0", "halfTimeScore": "0", "fullTimeScore": ""}}}}
    base.update(over)
    return base


def test_results_from_payload_ips_e_fase():
    assert E.results_from_payload(_payload(), now=NOW) == ("0-0", None)
    fin = _payload(score_home=2, score_away=1, score_raw={"matchStatus": "Finished",
                   "score": {"home": {"score": "2", "halfTimeScore": "0", "fullTimeScore": "2"},
                             "away": {"score": "1", "halfTimeScore": "0", "fullTimeScore": "1"}}})
    assert E.results_from_payload(fin, now=NOW) == ("0-0", "2-1")
    # intervallo senza halfTimeScore: il corrente È il 1T; 2T in corso: mai un finale
    ht = _payload(minute=45, score_raw={"matchStatus": "HalfTime", "score": {}})
    assert E.results_from_payload(ht, now=NOW) == ("1-0", None)
    assert E.results_from_payload(_payload(score_raw={"matchStatus": "SecondHalf", "score": {}}), now=NOW) == (None, None)
    assert E.results_from_payload(None) == (None, None)
    assert M.half_time_score(_payload()) == (0, 0) and M.half_time_score(ht) is None


def test_scoreline_names_e_winner():
    runners = [E.ScoreRunner(1, "0 - 0"), E.ScoreRunner(2, "2 - 1"), E.ScoreRunner(3, "Any Other Home Win")]
    names = E.scoreline_names(runners)
    assert names == {"1": "0 - 0", "2": "2 - 1"}
    assert E.winner_scoreline({"runners": names}, 2) == "2-1"
    assert E.winner_scoreline({"runners": names}, 3) is None and E.winner_scoreline({}, 2) is None
    assert E.result_key_for_trade({"phase": "ht_cs"}) == "result_ht"
    assert E.result_key_for_trade({"phase": None}) == "result_ft"
    assert E.result_key_for_trade({"phase": "scalp"}) is None


# --------------------------------------------------------- λ dal mercato O/U live
def _ou(line, over, under, status="OPEN"):
    return {"market_type": f"OVER_UNDER_{int(line)}5", "line": line, "status": status,
            "selections": [{"selection_id": 1, "name": f"Over {line} Goals", "back": over, "lay": over + 0.1},
                           {"selection_id": 2, "name": f"Under {line} Goals", "back": under, "lay": under + 0.02}]}


def test_lambdas_from_live_ou():
    st = M.LiveState(minute=60, score_home=0, score_away=0)
    payload = {"ou": [_ou(0.5, 1.5, 2.8), _ou(2.5, 6.0, 1.18), _ou(1.5, 2.6, 1.55), _ou(3.5, 15.0, 1.05, "SUSPENDED")]}
    est = M.residual_total_from_ou(payload, st)
    assert est is not None and est[1] == 2.5                       # la linea gol attuali + 2.5
    lam_res, _, p_over = est
    assert 0.1 < p_over < 0.25 and 1.0 < lam_res < 2.2
    live = M.lambdas_from_live_ou(payload, st, None)
    assert live is not None
    lh, la, info = live
    assert lh > la > 0 and info["line"] == 2.5 and info["lambda_residual"] == pytest.approx(lam_res, abs=1e-3)
    # con 2 gol già fatti la linea 1.5 è superata: si usa la 3.5 (aperta)
    st2 = M.LiveState(minute=70, score_home=2, score_away=0)
    payload2 = {"ou": [_ou(1.5, 1.01, 40.0), _ou(3.5, 3.0, 1.4)]}
    assert M.residual_total_from_ou(payload2, st2)[1] == 3.5
    assert M.lambdas_from_live_ou({"ou": []}, st, None) is None
    assert M.lambdas_from_live_ou({"ou": [_ou(2.5, 6.0, 1.18, "SUSPENDED")]}, st, None) is None
    assert M.lambdas_from_live_ou(None, st, None) is None


# ------------------------------------------------------------- tabella empirica
def _rows():
    rows = []
    # globale: dallo 0-0 al 45′ → 1000 partite
    for ft, n in (("0-0", 300), ("1-0", 200), ("0-1", 150), ("1-1", 150), ("2-0", 80), ("0-2", 50),
                  ("2-1", 30), ("1-2", 20), ("3-0", 10), ("0-3", 5), ("1-3", 3), ("3-1", 2)):
        rows.append({"league_id": 0, "ht": "0-0", "ft": ft, "n": n})
    # lega 135: 100 partite dallo 0-0, l'1-3 non è mai uscito, il 3-1 sì 5 volte
    for ft, n in (("0-0", 40), ("1-0", 30), ("1-1", 20), ("3-1", 5), ("2-0", 5)):
        rows.append({"league_id": 135, "ht": "0-0", "ft": ft, "n": n})
    return rows


def test_empirical_table_shrinkage_e_lookup():
    t = EMP.EmpiricalTable(_rows())
    assert not t.empty
    # stimatore PRUDENTE (limite superiore one-sided, review F13): mai la frequenza nuda
    p_glob, n = t.p_ft_given_ht((0, 0), (1, 3))
    assert n == 1000 and p_glob == pytest.approx(EMP.p_upper(3, 1000)) and p_glob > 0.003
    # lega: 3-1 uscito 5/100 contro 0,2% globale → conteggi shrinkati verso il globale (K=500)
    p_lega, _ = t.p_ft_given_ht((0, 0), (3, 1), league_id=135)
    # §16 seconda passata F-01: shrinkage col prior LIMITATO alle osservazioni globali e
    # larghezza di Wilson sulla varianza della media pesata (non su n+K come se il prior fosse certo)
    assert p_lega == pytest.approx(EMP.shrunk_upper(5, 100, 2, 1000))
    assert p_lega > p_glob                                          # la lega alza la P del 3-1
    # 1-3 mai in lega: si abbassa ma non azzera
    p13, _ = t.p_ft_given_ht((0, 0), (1, 3), league_id=135)
    assert 0 < p13 < 0.02          # limite superiore: con meno casi in lega la banda e' piu' larga, mai zero
    assert t.p_ft_given_ht((2, 2), (2, 2)) is None                 # 1T mai visto → nessuna opinione
    # regola del tre: un risultato MAI uscito su 1000 casi vale comunque ~0,27 %
    assert EMP.p_upper(0, 1000) == pytest.approx(1.64 ** 2 / (1000 + 1.64 ** 2), rel=0.05)
    # lookup: solo se il punteggio corrente È ancora quello del 45′
    fn = EMP.empirical_lookup(t, ht=(0, 0), current=(0, 0), league_id=None)
    assert fn is not None and fn(1, 3) == pytest.approx(p_glob) and fn(5, 5) == pytest.approx(EMP.p_upper(0, 1000))
    assert EMP.empirical_lookup(t, ht=(0, 0), current=(1, 0), league_id=None) is None
    assert EMP.empirical_lookup(t, ht=None, current=(0, 0), league_id=None) is None
    assert EMP.empirical_lookup(EMP.EmpiricalTable([]), ht=(0, 0), current=(0, 0), league_id=None) is None
    aud = EMP.audit_empirical(t, ht=(0, 0), current=(0, 0), league_id=135, ft=(3, 1))
    assert aud["ht_score"] == "0-0" and aud["empirical_n"] == 1000 and aud["empirical"] == pytest.approx(p_lega, abs=1e-6)
    assert EMP.audit_empirical(t, ht=(0, 0), current=(1, 0), league_id=None, ft=(3, 1))["empirical_note"] == "gol_nel_2t"


def _runner(sid, name, lay, size):
    return E.ScoreRunner(selection_id=sid, name=name, lay_price=lay, lay_size=size)


def test_select_by_model_con_veto_dai_dati():
    st = M.LiveState(minute=60, score_home=0, score_away=0)
    probs = {(3, 1): 0.004, (1, 3): 0.005, (0, 3): 0.006}
    runners = [_runner(1, "3 - 1", 80.0, 50), _runner(2, "1 - 3", 90.0, 50), _runner(3, "0 - 3", 100.0, 50)]
    # senza dati vince il 3-1 (P modello più bassa)
    sel = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120, min_liquidity=5, p_max=0.02)
    assert sel.name == "3 - 1" and sel.p_data is None and sel.p_selected == 0.004
    # i dati dicono che il 3-1 esce il 3% delle volte (> p_max) → escluso; 1-3 raro anche per i dati
    data = {(3, 1): 0.03, (1, 3): 0.002}.get
    sel = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120, min_liquidity=5,
                            p_max=0.02, p_data=lambda h, a: data((h, a)))
    assert sel.name == "1 - 3" and sel.p_data == 0.002 and sel.p_selected == 0.005   # max(modello, dati)
    aud = M.audit_block(sel, lh_pre=1.4, la_pre=1.1, source="live_ou", state=st, half=False)
    assert aud["p_data"] == 0.002 and aud["p_selected"] == 0.005 and aud["lambda_source"] == "live_ou"
    # dati rotti → ignorati, mai un crash
    sel = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120, min_liquidity=5,
                            p_max=0.02, p_data=lambda h, a: 1 / 0)
    assert sel.name == "3 - 1"


# ------------------------------------------------------------------ servizio
class _Market:
    def __init__(self, books, closed=None):
        self.books = books
        self.closed = closed or {}       # market_id → winner selection id

    def get_event_market_by_type(self, event_id, event_name, market_type):
        if (event_id, market_type) not in self.books:
            return None
        return SimpleNamespace(market_id=f"m-{event_id}-{market_type}", event_id=event_id,
                               event_name=event_name, market_start_time=NOW - timedelta(minutes=60),
                               runner_names={r.selection_id: r.name for r in self.books[(event_id, market_type)]})

    def read_market(self, cs):
        if cs.market_id in self.closed:
            return SimpleNamespace(status="CLOSED", inplay=False, closed=True, voided=False,
                                   winner_selection_id=self.closed[cs.market_id], runners=[])
        key = (cs.event_id, cs.market_id.split("-", 2)[2])
        return SimpleNamespace(status="OPEN", inplay=True, closed=False, voided=False,
                               winner_selection_id=None, runners=list(self.books[key]))

    def read_book(self, market_id, runner_names):
        return None

    def list_today_football_events(self):
        return []

    def place_lay_live(self, **kw):
        raise AssertionError("mai live nei test")


class _DB:
    def __init__(self, control, events=None, transitions=None):
        self.control = control
        self.trades = []
        self.activity = []
        self.events = events or {}
        self.saved_models = {}
        self.goals = {}
        self.transitions = transitions or []
        self._id = 0

    def read_control(self):
        return self.control

    def set_control(self, **fields):
        self.control.update(fields)

    def log(self, kind, payload=None):
        self.activity.append((kind, payload or {}))

    def get_event(self, event_id):
        return self.events.get(event_id)

    def save_event_model(self, event_id, model):
        self.saved_models[event_id] = model
        return True

    def event_lambda_hint(self, event_id):
        for t in reversed(self.trades):
            model = (t.get("meta") or {}).get("model")
            if t["event_id"] == event_id and isinstance(model, dict) and model.get("lambda_pre"):
                return {"lambda_pre": model["lambda_pre"], "lambda_source": model.get("lambda_source")}
        return None

    def ht_ft_transitions(self, league_id):
        return self.transitions

    def upsert_daily_goal(self, day, goal):
        self.goals[day] = goal
        return True

    def positions_for_results(self, since_iso):
        return [t for t in self.trades if not t.get("closes_trade_id") and t.get("status") != "error"]

    def insert_trade(self, trade):
        if any(t["event_id"] == trade["event_id"] and (t.get("phase") or "") == (trade.get("phase") or "")
               and t.get("origin", "auto") == "auto" and not trade.get("closes_trade_id") for t in self.trades):
            raise Exception("unique auto leg")
        self._id += 1
        row = dict(trade); row["id"] = self._id
        self.trades.append(row)
        return self._id

    def update_trade(self, trade_id, **fields):
        for t in self.trades:
            if t["id"] == trade_id:
                t.update(fields)

    def get_trade(self, trade_id):
        return next((t for t in self.trades if t["id"] == trade_id), None)

    def delete_trade(self, trade_id):
        self.trades = [t for t in self.trades if t["id"] != trade_id]

    def list_trades(self, status=None):
        return [t for t in self.trades if status is None or t.get("status") == status]

    def open_trades(self):
        return self.list_trades("open")

    def hedged_trades(self):
        return self.list_trades("hedged")

    def closing_trades_for(self, ids):
        return [t for t in self.trades if t.get("closes_trade_id") in ids]

    def traded_event_ids(self):
        return {t["event_id"] for t in self.trades}

    def mission_event_ids(self):
        return set()

    def pending_manual_requests(self):
        return []

    def active_missions(self):
        return []

    def aggregates(self, day_start=None):
        return E.aggregate_trades(self.trades, day_start)

    def traded_legs(self):
        out = set()
        for t in self.trades:
            if t.get("status") == "error" or t.get("closes_trade_id"):
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
    # P GREZZE del modello (niente calibratore, niente fattore di coda): questi test
    # verificano l'aritmetica di selezione/target, non la calibrazione (§15)
    base = {"engine": "legs", "price_min": 20, "price_max": 120, "min_lay_liquidity": 5,
            "model_p_max_pct": 3.0, "execution_mode": "rest", "commission_pct": 5,
            "model_calibration": "off", "model_tail_factor": 1.0}
    base.update(over)
    return omega_config.resolve_params(base)


def _lookup(minute, sh, sa):
    return lambda eid: S.LiveScore(minute=minute, score_home=sh, score_away=sa, updated_at=NOW.isoformat())


@pytest.fixture(autouse=True)
def _clean_caches(monkeypatch):
    import Betfair.stream.db as sdb
    monkeypatch.setattr(sdb, "get_fixture_prematch_lambdas", lambda fid: None)   # nessuna fixture
    S._LAMBDA_CACHE.clear()
    S._EMPIRICAL_CACHE.clear()
    S._DAILY_GOAL_WRITTEN.clear()


def _run(db, market, ev, params, minute, sh, sa, legs=None, goal=10.0):
    agg = {"realized_today": 0.0, "matches_traded_today": 0, "open_liability": 0.0}
    return S.scan_and_place_legs(
        control={"daily_goal": goal, "mode": "paper"}, params=params, events=[ev],
        traded_ids=set(), traded_legs=legs if legs is not None else set(), aggregates=agg,
        market=market, db=db, now=NOW, score_lookup=_lookup(minute, sh, sa))


def test_lambda_catena_evento_persistito_e_hint_dal_trade_1t():
    db = _DB({}, events={"e1": {"league_id": 135, "model": {"lambda_pre": [1.5, 1.1], "lambda_source": "pre_ko_odds"}}})
    assert S._prematch_lambdas(db, "e1", None) == (1.5, 1.1, 135, "pre_ko_odds")
    S._LAMBDA_CACHE.clear()
    db2 = _DB({}, events={"e2": {"league_id": 135}})
    db2.trades.append({"id": 1, "event_id": "e2", "phase": "ht_cs", "status": "won",
                       "meta": {"model": {"lambda_pre": [1.3, 0.9], "lambda_source": "fixture"}}})
    assert S._prematch_lambdas(db2, "e2", {"cs": {}}) == (1.3, 0.9, 135, "fixture")
    assert db2.saved_models["e2"]["lambda_pre"] == [1.3, 0.9]          # persistito sull'evento
    S._LAMBDA_CACHE.clear()
    assert S._prematch_lambdas(_DB({}), "e3", {"cs": {}}) is None       # nulla: mai a occhi chiusi


def test_lambda_da_over_under_live_solo_con_stato_e_parametro():
    db = _DB({}, events={"e4": {"league_id": None}})
    payload = {"ou": [_ou(2.5, 6.0, 1.18)]}
    st = M.LiveState(minute=60, score_home=0, score_away=0)
    assert S._prematch_lambdas(db, "e4", payload) is None               # senza stato: no
    S._LAMBDA_CACHE.clear()
    assert S._prematch_lambdas(db, "e4", payload, state=st, params={"lambda_live_fallback": False}) is None
    S._LAMBDA_CACHE.clear()
    lam = S._prematch_lambdas(db, "e4", payload, state=st, params={"lambda_live_fallback": True})
    assert lam is not None and lam[3] == "live_ou" and lam[0] > lam[1] > 0
    assert db.saved_models["e4"]["lambda_source"] == "live_ou"
    assert any(k == "model_lambda_live" and p["event_id"] == "e4" for k, p in db.activity)


def test_gamba_2t_piazzata_senza_fixture_ne_pre_ko_grazie_al_mercato_ou(monkeypatch):
    """Caso 10/09: 746 skip 'no_model_lambdas' sulla 2T. Ora la gamba parte."""
    ev = SimpleNamespace(event_id="e5", name="Teleoptik v Proleter", open_date=NOW - timedelta(minutes=70))
    db = _DB({"daily_goal": 10.0, "mode": "paper"}, events={"e5": {"league_id": None}})
    market = _Market(_books("e5"))
    payload = {"minute": 60, "score_home": 1, "score_away": 0, "inplay": True,
               "ou": [_ou(3.5, 5.5, 1.2)], "score_raw": {"matchStatus": "SecondHalf", "score": {}}}
    monkeypatch.setattr(S, "_feed_state", lambda market_, eid: payload)
    assert _run(db, market, ev, _params(), minute=60, sh=1, sa=0) == 1, db.activity
    t = db.trades[0]
    assert t["phase"] == "ft_cs" and t["status"] == "open"
    assert t["meta"]["model"]["lambda_source"] == "live_ou"
    assert t["meta"]["model"]["empirical_note"] == "tabella_assente"
    assert t["meta"]["runners"]["14"] == "1 - 3" and "16" not in t["meta"]["runners"]
    assert t["target"] == 10.0                                          # 1 sola gamba residua → tutto


def test_target_per_gamba_spalmato_sulle_gambe_residue(monkeypatch):
    ev = SimpleNamespace(event_id="e6", name="A v B", open_date=NOW - timedelta(minutes=31))
    ev2 = SimpleNamespace(event_id="e7", name="C v D", open_date=NOW + timedelta(minutes=120))   # 2 gambe future
    db = _DB({"daily_goal": 30.0, "mode": "paper"},
             events={"e6": {"league_id": 135, "model": {"lambda_pre": [1.6, 1.1], "lambda_source": "saved"}}})
    market = _Market(_books("e6"))
    monkeypatch.setattr(S, "_feed_state", lambda market_, eid: None)
    agg = {"realized_today": 0.0, "matches_traded_today": 0, "open_liability": 0.0}
    n = S.scan_and_place_legs(control={"daily_goal": 30.0, "mode": "paper"}, params=_params(), events=[ev, ev2],
                              traded_ids=set(), traded_legs=set(), aggregates=agg, market=market, db=db,
                              now=NOW, score_lookup=_lookup(30, 0, 0))
    assert n == 1 and db.trades[0]["phase"] == "ht_cs"
    assert db.trades[0]["target"] == 7.5                                # 30 € / 4 gambe (2 + 2)


def test_veto_empirico_sulla_gamba_2t(monkeypatch):
    ev = SimpleNamespace(event_id="e8", name="A v B", open_date=NOW - timedelta(minutes=70))
    rows = [{"league_id": 0, "ht": "1-0", "ft": ft, "n": n} for ft, n in
            (("1-0", 4000), ("2-0", 2500), ("1-1", 2000), ("2-1", 1000), ("3-0", 300), ("1-3", 150), ("4-1", 20))]
    db = _DB({"daily_goal": 10.0, "mode": "paper"},
             events={"e8": {"league_id": 135, "model": {"lambda_pre": [1.5, 1.0], "lambda_source": "saved"}}},
             transitions=rows)
    market = _Market(_books("e8"))
    payload = {"minute": 60, "score_home": 1, "score_away": 0, "inplay": True,
               "score_raw": {"matchStatus": "SecondHalf",
                             "score": {"home": {"halfTimeScore": "1"}, "away": {"halfTimeScore": "0"}}}}
    monkeypatch.setattr(S, "_feed_state", lambda market_, eid: payload)
    assert _run(db, market, ev, _params(model_p_max_pct=1.0), minute=60, sh=1, sa=0) == 1, db.activity
    m = db.trades[0]["meta"]["model"]
    # i dati (limite superiore): 1-3 ≈ 1,7 % (> 1 % → veto), 4-1 ≈ 0,35 % → resta il 4-1
    assert db.trades[0]["runner_name"] == "4 - 1"
    assert m["ht_score"] == "1-0" and m["empirical"] == pytest.approx(EMP.p_upper(20, 9970), abs=1e-6) and m["p_selected"] >= m["p_model"]
    # con model_empirical='off' i dati non contano
    db2 = _DB({"daily_goal": 10.0, "mode": "paper"}, events=db.events, transitions=rows)
    S._LAMBDA_CACHE.clear()
    assert _run(db2, _Market(_books("e8")), ev, _params(model_p_max_pct=1.0, model_empirical="off"), minute=60, sh=1, sa=0) == 1
    assert db2.trades[0]["meta"]["model"]["p_data"] is None


def test_track_event_results_e_stamp_al_settlement(monkeypatch):
    db = _DB({"daily_goal": 10.0, "mode": "paper"})
    db.trades += [
        {"id": 1, "event_id": "e9", "phase": "ht_cs", "status": "won", "placed_at": NOW.isoformat(),
         "meta": {"runners": {"5": "0 - 3", "1": "0 - 0"}}},
        {"id": 2, "event_id": "e9", "phase": "ft_cs", "status": "open", "placed_at": NOW.isoformat(),
         "market_id": "m-e9-CORRECT_SCORE", "selection_id": 14, "size": 2.0, "price": 55.0, "commission": 0.05,
         "runner_name": "1 - 3", "side": "lay", "meta": {"runners": {"14": "1 - 3", "12": "2 - 0"}}},
        {"id": 3, "event_id": "e9", "status": "open", "placed_at": NOW.isoformat(), "closes_trade_id": 2, "meta": {}},
    ]
    feed = {"e9": {"minute": 46, "score_home": 1, "score_away": 0, "score_raw": {"matchStatus": "HalfTime", "score": {}}}}
    assert S.track_event_results(db=db, market=None, now=NOW, feed=feed.get) == 2
    assert db.trades[0]["meta"]["result_ht"] == "1-0" and db.trades[1]["meta"]["result_ht"] == "1-0"
    assert "result_ht" not in db.trades[2]["meta"]                       # mai sulle chiusure
    assert S.track_event_results(db=db, market=None, now=NOW, feed=feed.get) == 0   # idempotente
    # settlement del CS: il WINNER (2-0) È il risultato finale, scritto su meta
    market = _Market({}, closed={"m-e9-CORRECT_SCORE": 12})
    # UNA posizione regolata IN COPPIA (§16 review HIGH-3: la chiusura la dice il DB,
    # non il marker nel meta): apertura lay 1-3 vinta + chiusura nettizzata insieme
    assert S.settle_open(params=_params(), market=market, db=db, now=NOW) == 1
    assert db.trades[1]["status"] == "won" and db.trades[1]["meta"]["result_ft"] == "2-0"
    assert db.trades[2]["status"] == "won" and db.trades[1]["pnl"] == pytest.approx(1.9, abs=0.01)
    assert db.trades[1]["meta"]["result_ht"] == "1-0"
    # dal feed a partita finita si completa anche l'altra gamba, senza sovrascrivere
    feed["e9"] = {"minute": 90, "score_home": 2, "score_away": 0, "score_raw": {"matchStatus": "Finished", "score": {}}}
    assert S.track_event_results(db=db, market=None, now=NOW, feed=feed.get) == 1
    assert db.trades[0]["meta"]["result_ft"] == "2-0"


def test_run_once_stats_gambe_residue_e_snapshot_obiettivo(monkeypatch):
    ev = SimpleNamespace(event_id="e10", name="A v B", open_date=NOW + timedelta(minutes=30))
    db = _DB({"status": "running", "mode": "paper", "daily_goal": 100.0, "params": {"execution_mode": "rest"}})
    market = _Market(_books("e10"))
    market.list_today_football_events = lambda: [ev]
    monkeypatch.setattr(S, "process_missions", lambda **kw: 0)
    monkeypatch.setattr(S, "process_manual", lambda **kw: 0)
    out = S.run_once(market=market, db=db, now=NOW)
    st = out["stats"]
    assert st["legs_remaining"] == 2 and st["matches_remaining"] == 1
    assert st["target_leg"] == 50.0 and st["target_match"] == 100.0 and st["realized_today"] == 0.0
    assert db.goals == {"2026-09-11": 100.0}
    # secondo ciclo, stesso obiettivo → nessuna riscrittura; obiettivo cambiato → nuova
    db.goals.clear()
    S.run_once(market=market, db=db, now=NOW)
    assert db.goals == {}
    db.control["daily_goal"] = 120.0
    S.run_once(market=market, db=db, now=NOW)
    assert db.goals == {"2026-09-11": 120.0}


# ------------------------------------------------- correzioni dalla review (11/09)
def test_legs_remaining_cap_max_events_non_tocca_le_seconde_gambe():
    """HIGH-2: con max_events raggiunto le 2T delle partite già in posizione restano piazzabili."""
    events = [_ev("a", 30), _ev("b", 30), _ev("c", 30), _ev("d", 30)]
    done = {("a", "ht_cs"), ("b", "ht_cs"), ("c", "ht_cs")}
    legs, matches = E.legs_remaining(events, done, now=NOW, ht_entry_max=40, ft_entry_max=80,
                                     max_events=3, traded_count=3)
    assert (legs, matches) == (3, 3)              # 3 seconde gambe; la partita nuova 'd' è fuori cap
    legs, matches = E.legs_remaining(events, done, now=NOW, ht_entry_max=40, ft_entry_max=80,
                                     max_events=4, traded_count=3)
    assert (legs, matches) == (5, 4)              # + le 2 gambe di 'd'


def test_scan_legs_con_cap_raggiunto_piazza_comunque_la_2t(monkeypatch):
    ev = SimpleNamespace(event_id="e11", name="A v B", open_date=NOW - timedelta(minutes=70))
    db = _DB({"daily_goal": 10.0, "mode": "paper"},
             events={"e11": {"league_id": 135, "model": {"lambda_pre": [1.5, 1.0], "lambda_source": "saved"}}})
    market = _Market(_books("e11"))
    monkeypatch.setattr(S, "_feed_state", lambda market_, eid: None)
    agg = {"realized_today": 0.0, "matches_traded_today": 1, "open_liability": 0.0}
    n = S.scan_and_place_legs(control={"daily_goal": 10.0, "mode": "paper"}, params=_params(max_events=1),
                              events=[ev], traded_ids=set(), traded_legs={("e11", "ht_cs")}, aggregates=agg,
                              market=market, db=db, now=NOW, score_lookup=_lookup(60, 1, 0))
    assert n == 1 and db.trades[0]["phase"] == "ft_cs" and db.trades[0]["target"] == 10.0


def test_veto_empirico_solo_a_inizio_ripresa(monkeypatch):
    """HIGH-3: la tabella copre tutto il 2T → oltre la finestra il veto non si applica."""
    ev = SimpleNamespace(event_id="e12", name="A v B", open_date=NOW - timedelta(minutes=85))
    rows = [{"league_id": 0, "ht": "1-0", "ft": ft, "n": n} for ft, n in
            (("1-0", 4000), ("2-0", 2500), ("1-1", 2000), ("2-1", 1000), ("3-0", 300), ("1-3", 150), ("4-1", 20))]
    db = _DB({"daily_goal": 10.0, "mode": "paper"},
             events={"e12": {"league_id": 135, "model": {"lambda_pre": [1.5, 1.0], "lambda_source": "saved"}}},
             transitions=rows)
    payload = {"minute": 75, "score_home": 1, "score_away": 0, "inplay": True,
               "score_raw": {"matchStatus": "SecondHalf",
                             "score": {"home": {"halfTimeScore": "1"}, "away": {"halfTimeScore": "0"}}}}
    monkeypatch.setattr(S, "_feed_state", lambda market_, eid: payload)
    assert _run(db, _Market(_books("e12")), ev, _params(), minute=75, sh=1, sa=0) == 1, db.activity
    m = db.trades[0]["meta"]["model"]
    assert m["p_data"] is None and m["empirical_note"] == "fuori_finestra" and m["ht_score"] == "1-0"


def test_results_finale_mai_dal_corrente_con_supplementari():
    et = {"minute": 105, "score_home": 2, "score_away": 1,
          "score_raw": {"matchStatus": "ExtraTimeSecondHalfEnd", "score": {}}}
    assert E.results_from_payload(et, now=NOW) == (None, None)
    et_ft = {"minute": 120, "score_home": 2, "score_away": 1,
             "score_raw": {"matchStatus": "Finished",
                           "score": {"home": {"halfTimeScore": "0", "fullTimeScore": "1"},
                                     "away": {"halfTimeScore": "0", "fullTimeScore": "1"}}}}
    assert E.results_from_payload(et_ft, now=NOW) == ("0-0", "1-1")   # fullTimeScore = 90′


def test_settle_open_non_resuscita_i_marker_di_mercato_sparito():
    """MED-3: meta ripulito e poi stampato col risultato senza reintrodurre i marker."""
    db = _DB({"daily_goal": 10.0, "mode": "paper"})
    db.trades.append({"id": 1, "event_id": "e13", "phase": "ft_cs", "status": "open", "placed_at": NOW.isoformat(),
                      "market_id": "m-e13-CORRECT_SCORE", "selection_id": 14, "size": 2.0, "price": 55.0,
                      "commission": 0.05, "runner_name": "1 - 3", "side": "lay",
                      "meta": {"runners": {"12": "2 - 0"}, "market_gone_since": "x", "orphan_alerted": True}})
    market = _Market({}, closed={"m-e13-CORRECT_SCORE": 12})
    assert S.settle_open(params=_params(), market=market, db=db, now=NOW) == 1
    meta = db.trades[0]["meta"]
    assert meta["result_ft"] == "2-0" and "market_gone_since" not in meta and "orphan_alerted" not in meta
