"""§15 (11/09/2026): modello definitivo — mercato intero, tabella per minuto,
costo di copertura, gialli, validazione.

Garanzie (nessuna rete/DB):
  - market_cs_probs: devig (mid back/lay) normalizzato su tutte le selezioni,
    aggregati esclusi dai target ma pesati; troppo poche selezioni → {};
  - fit sul mercato: λ residui NOTI vengono ricostruiti (entro tolleranza) e la
    conversione a pre-match equivalente è coerente coi moltiplicatori live;
  - catena λ del servizio: senza fixture/pre-KO/hint la scala CS dà 'market_grid'
    (log model_lambda_market), la sola O/U dà 'live_ou';
  - MinuteTable: bucket, shrinkage per lega, lookup per entrambe le gambe; nel
    servizio la tabella per minuto ha la precedenza sul veto HT→FT;
  - costo di copertura: fra P equivalenti vince il più economico da coprire;
  - gialli dal feed nello stato live (moltiplicatori calibrati);
  - metriche di validazione: log-loss/Brier/affidabilità su casi noti.
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
from Betfair.omega import omega_validate as V
from Betfair.omega.test_omega_giornata_gambe_2026_09_11 import _DB, _Market, _books, _ou, _params, _lookup

NOW = datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc)


def _cs_payload(lh_res, la_res, state, *, tail=0.002, any_other=60.0, spread=0.03):
    grid = M.residual_grid(lh_res, la_res, -0.13, 8, dixon_coles=False)
    sels, sid = [], 1
    for (h, a), p in grid.items():
        if p < tail:
            continue
        q = 1.0 / p
        sels.append({"selection_id": sid, "name": f"{state.score_home + h} - {state.score_away + a}",
                     "back": round(q * (1 - spread), 2), "lay": round(q * (1 + spread), 2), "back_size": 50, "lay_size": 40})
        sid += 1
    sels.append({"selection_id": 99, "name": "Any Other Home Win", "back": any_other, "lay": any_other * 1.1})
    return {"cs": {"status": "OPEN", "market_id": "m-cs", "selections": sels}}


# ------------------------------------------------------------ mercato intero
def test_market_cs_probs_devig_e_soglia():
    st = M.LiveState(minute=60, score_home=1, score_away=0)
    payload = _cs_payload(0.6, 0.45, st)
    probs = M.market_cs_probs(payload, st)
    assert probs and abs(sum(probs.values()) - 1.0) < 0.05          # l'aggregato assorbe il resto
    assert all(h >= 1 for (h, a) in probs)                            # mai sotto il punteggio
    assert M.market_cs_probs({"cs": {"status": "SUSPENDED", "selections": payload["cs"]["selections"]}}, st) == {}
    few = {"cs": {"status": "OPEN", "selections": payload["cs"]["selections"][:3]}}
    assert M.market_cs_probs(few, st) == {}                           # troppo poche selezioni
    assert M.market_cs_probs(None, st) == {}


def test_fit_recupera_lambda_residui_noti():
    st = M.LiveState(minute=60, score_home=1, score_away=0)
    payload = _cs_payload(0.6, 0.45, st, tail=0.0005, any_other=2000.0, spread=0.0)
    cs = M.market_cs_probs(payload, st)
    fit = M.fit_residual_lambdas_to_market(cs, {}, st, rho=-0.13)
    assert fit is not None
    lh, la, loss = fit
    assert abs(lh - 0.6) < 0.06 and abs(la - 0.45) < 0.06 and loss < 1e-3
    # con le linee O/U coerenti il fit resta stabile
    ou = M.market_ou_probs({"ou": [_ou(2.5, 1 / 0.28 * 0.98, 1 / 0.72 * 0.98)]}, st)   # P(res ≥ 2) ≈ 0.28
    assert list(ou.keys()) == [1] and 0.25 < ou[1] < 0.31
    fit2 = M.fit_residual_lambdas_to_market(cs, ou, st, rho=-0.13)
    assert abs(fit2[0] + fit2[1] - 1.05) < 0.15
    assert M.fit_residual_lambdas_to_market({}, {}, st) is None


def test_lambdas_from_market_grid_pre_match_equivalenti():
    st = M.LiveState(minute=60, score_home=1, score_away=0, yellow_home=2)
    payload = _cs_payload(0.6, 0.45, st, tail=0.0005, any_other=2000.0, spread=0.0)
    got = M.lambdas_from_market_grid(payload, st, None)
    assert got is not None
    lh, la, info = got
    # riportati a pre-match: riapplicando i moltiplicatori live si ritrovano i residui
    res_h, res_a = M.residual_lambdas(lh, la, st, None, half=False)
    assert abs(res_h - info["lambda_residual"][0]) < 0.05 and abs(res_a - info["lambda_residual"][1]) < 0.05
    assert info["n_cs"] >= 6 and info["n_ou"] == 0
    assert M.lambdas_from_market_grid({"ou": []}, st, None) is None


def test_yellow_cards_dal_feed():
    p = {"score_raw": {"score": {"home": {"numberOfYellowCards": "3"}, "away": {"numberOfYellowCards": None}}}}
    assert M.yellow_cards(p) == (3, 0)
    assert M.yellow_cards({}) == (0, 0)
    assert M.yellow_cards({"score_raw": {"score": {"home": {"numberOfYellowCards": "x"}}}}) == (0, 0)


def test_catena_lambda_mercato_intero_prima_della_singola_ou(monkeypatch):
    import Betfair.stream.db as sdb
    monkeypatch.setattr(sdb, "get_fixture_prematch_lambdas", lambda fid: None)
    S._LAMBDA_CACHE.clear()
    st = M.LiveState(minute=60, score_home=1, score_away=0)
    payload = _cs_payload(0.6, 0.45, st)
    payload["ou"] = [_ou(3.5, 5.5, 1.2)]
    db = _DB({}, events={"m1": {"league_id": None}})
    lam = S._prematch_lambdas(db, "m1", payload, state=st, params={"lambda_market_grid": True, "lambda_live_fallback": True})
    assert lam is not None and lam[3] == "market_grid"
    assert any(k == "model_lambda_market" for k, _ in db.activity)
    assert db.saved_models["m1"]["lambda_source"] == "market_grid"
    # con la griglia spenta → singola linea O/U
    S._LAMBDA_CACHE.clear()
    db2 = _DB({}, events={"m1": {"league_id": None}})
    lam2 = S._prematch_lambdas(db2, "m1", payload, state=st, params={"lambda_market_grid": False, "lambda_live_fallback": True})
    assert lam2 is not None and lam2[3] == "live_ou"


# --------------------------------------------------------- tabella per minuto
def _minute_rows():
    rows = []
    for ft, n in (("1-0", 5000), ("2-0", 2000), ("1-1", 1500), ("2-1", 800), ("3-0", 400), ("1-2", 200), ("1-3", 60), ("4-1", 40)):
        rows.append({"league_id": 0, "bucket": 60, "score": "1-0", "target": "ft", "result": ft, "n": n})
    for ft, n in (("1-0", 60), ("2-0", 20), ("1-3", 5)):
        rows.append({"league_id": 135, "bucket": 60, "score": "1-0", "target": "ft", "result": ft, "n": n})
    for ht, n in (("0-0", 7000), ("1-0", 2000), ("0-1", 900), ("0-2", 100)):
        rows.append({"league_id": 0, "bucket": 20, "score": "0-0", "target": "ht", "result": ht, "n": n})
    return rows


def test_minute_bucket_e_tabella():
    assert EMP.minute_bucket(63, half=False) == 60 and EMP.minute_bucket(89, half=False) == 85
    assert EMP.minute_bucket(44, half=True) == 40 and EMP.minute_bucket(3, half=True) == 0
    t = EMP.MinuteTable(_minute_rows())
    assert not t.empty
    p, n = t.p_result(minute=62, score=(1, 0), result=(1, 3), half=False)
    assert n == 10000 and p == pytest.approx(EMP.p_upper(60, 10000)) and p > 0.006
    p_lega, _ = t.p_result(minute=62, score=(1, 0), result=(1, 3), half=False, league_id=135)
    assert p_lega == pytest.approx(EMP.shrunk_upper(5, 85, 60, 10000))
    assert t.p_result(minute=62, score=(3, 3), result=(3, 4), half=False) is None
    p_ht, n_ht = t.p_result(minute=22, score=(0, 0), result=(0, 2), half=True)
    assert n_ht == 10000 and p_ht == pytest.approx(EMP.p_upper(100, 10000))
    fn = EMP.minute_lookup(t, minute=61, current=(1, 0), half=False, league_id=None)
    assert fn(4, 1) == pytest.approx(EMP.p_upper(40, 10000)) and fn(9, 9) == pytest.approx(EMP.p_upper(0, 10000))
    assert EMP.minute_lookup(EMP.MinuteTable([]), minute=61, current=(1, 0), half=False, league_id=None) is None
    aud = EMP.audit_minute(t, minute=61, current=(1, 0), half=False, league_id=None, result=(1, 3))
    assert aud["empirical_source"] == "minute" and aud["empirical_bucket"] == 60 and aud["empirical_n"] == 10000


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    import Betfair.stream.db as sdb
    monkeypatch.setattr(sdb, "get_fixture_prematch_lambdas", lambda fid: None)
    S._LAMBDA_CACHE.clear()
    S._EMPIRICAL_CACHE.clear()
    S._MINUTE_CACHE.clear()


class _DBMinute(_DB):
    def __init__(self, *a, minute_rows=None, **k):
        super().__init__(*a, **k)
        self.minute_rows = minute_rows or []
        self.minute_calls = []

    def minute_transitions(self, league_id, bucket, target):
        self.minute_calls.append((league_id, bucket, target))
        return [r for r in self.minute_rows if r["bucket"] == bucket and r["target"] == target]


def _run(db, market, ev, params, minute, sh, sa, legs=None):
    agg = {"realized_today": 0.0, "matches_traded_today": 0, "open_liability": 0.0}
    return S.scan_and_place_legs(control={"daily_goal": 10.0, "mode": "paper"}, params=params, events=[ev],
                                 traded_ids=set(), traded_legs=legs or set(), aggregates=agg,
                                 market=market, db=db, now=NOW, score_lookup=_lookup(minute, sh, sa))


def test_servizio_usa_la_tabella_per_minuto_su_entrambe_le_gambe(monkeypatch):
    ev = SimpleNamespace(event_id="e20", name="A v B", open_date=NOW - timedelta(minutes=70))
    db = _DBMinute({"daily_goal": 10.0, "mode": "paper"},
                   events={"e20": {"league_id": 135, "model": {"lambda_pre": [1.5, 1.0], "lambda_source": "saved"}}},
                   minute_rows=_minute_rows())
    payload = {"minute": 62, "score_home": 1, "score_away": 0, "inplay": True,
               "score_raw": {"matchStatus": "SecondHalf", "score": {"home": {"numberOfYellowCards": "1"}, "away": {}}}}
    monkeypatch.setattr(S, "_feed_state", lambda market_, eid: payload)
    # p_max 2 %: i dati (limite superiore, lega shrinkata) dicono 1-3 ≈ 2,4 % (veto) → resta il 4-1 (≈ 0,8 %)
    assert _run(db, _Market(_books("e20")), ev, _params(), minute=62, sh=1, sa=0) == 1, db.activity
    t = db.trades[0]
    m = t["meta"]["model"]
    assert t["runner_name"] == "4 - 1"
    # P della lega 135: conteggi shrinkati verso il globale (k_eff = 0 + 500·0,004, n_eff = 85 + 500), limite superiore
    assert m["empirical_source"] == "minute" and m["empirical_bucket"] == 60
    assert m["p_data"] == pytest.approx(EMP.shrunk_upper(0, 85, 40, 10000), abs=1e-6)
    assert m["yellow"] == [1, 0] and m["cost_aware"] is True and "cover_cost" in m
    assert db.minute_calls == [(135, 60, "ft")]
    # gamba 1T: tabella 'ht' interrogata al bucket 20
    ev2 = SimpleNamespace(event_id="e21", name="A v B", open_date=NOW - timedelta(minutes=23))
    db2 = _DBMinute({"daily_goal": 10.0, "mode": "paper"},
                    events={"e21": {"league_id": 135, "model": {"lambda_pre": [1.5, 1.0], "lambda_source": "saved"}}},
                    minute_rows=_minute_rows())
    payload2 = {"minute": 22, "score_home": 0, "score_away": 0, "inplay": True, "score_raw": {"matchStatus": "FirstHalf", "score": {}}}
    monkeypatch.setattr(S, "_feed_state", lambda market_, eid: payload2)
    assert _run(db2, _Market(_books("e21")), ev2, _params(), minute=22, sh=0, sa=0) == 1, db2.activity
    assert db2.minute_calls == [(135, 20, "ht")] and db2.trades[0]["meta"]["model"]["empirical_source"] == "minute"


# --------------------------------------------------------- costo di copertura
def _r(sid, name, lay, size, back=None, back_size=0.0):
    return E.ScoreRunner(selection_id=sid, name=name, lay_price=lay, lay_size=size, back_price=back, back_size=back_size)


def test_selezione_con_costo_di_copertura():
    st = M.LiveState(minute=60, score_home=0, score_away=0)
    probs = {(3, 1): 0.0040, (1, 3): 0.0041, (0, 3): 0.0090}
    runners = [_r(1, "3 - 1", 80.0, 50, back=40.0, back_size=20),     # P minima ma copertura cara (L/B = 2)
               _r(2, "1 - 3", 90.0, 50, back=80.0, back_size=20),     # P quasi uguale, copertura economica
               _r(3, "0 - 3", 100.0, 50, back=95.0, back_size=20)]    # fuori banda (0.009 > 2×0.004)
    plain = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120, min_liquidity=5, p_max=0.02, size_needed=2.0)
    assert plain.name == "3 - 1"
    cheap = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120, min_liquidity=5, p_max=0.02,
                              size_needed=2.0, cost_aware=True, band_ratio=2.0)
    assert cheap.name == "1 - 3" and cheap.back_price == 80.0
    assert M.cover_cost(2.0, 90.0, 80.0) == pytest.approx(0.25) and M.cover_cost(2.0, 80.0, 40.0) == 2.0
    assert M.cover_cost(2.0, 80.0, None) is None
    # senza back noti la banda si riduce alla P più bassa
    runners2 = [_r(1, "3 - 1", 80.0, 50), _r(2, "1 - 3", 90.0, 50)]
    assert M.select_by_model(runners2, probs, state=st, price_min=20, price_max=120, min_liquidity=5, p_max=0.02,
                             size_needed=2.0, cost_aware=True).name == "3 - 1"
    # liquidità back insufficiente per coprire → preferito chi la ha
    runners3 = [_r(1, "3 - 1", 80.0, 50, back=78.0, back_size=0.5), _r(2, "1 - 3", 90.0, 50, back=60.0, back_size=50)]
    assert M.select_by_model(runners3, probs, state=st, price_min=20, price_max=120, min_liquidity=5, p_max=0.02,
                             size_needed=2.0, cost_aware=True).name == "1 - 3"


def test_config_v3_default():
    p = omega_config.resolve_params({})
    assert p["lambda_market_grid"] is True and p["select_cost_aware"] is True and p["select_p_band_ratio"] == 2.0
    assert p["model_use_yellow_cards"] is True


# ---------------------------------------------------------------- validazione
def test_metriche_di_validazione():
    preds = [(0.9, 1), (0.8, 1), (0.2, 0), (0.1, 0), (0.5, 1), (0.5, 0)]
    m = V.binary_metrics(preds)
    assert 0 < m["log_loss"] < 0.5 and 0 < m["brier"] < 0.2 and m["n"] == 6
    perfect = V.binary_metrics([(1.0, 1), (0.0, 0)])
    assert perfect["brier"] == 0.0
    rel = V.reliability([(0.01, 0)] * 99 + [(0.01, 1)], edges=(0.0, 0.02, 1.0))
    assert rel[0]["n"] == 100 and rel[0]["p_mean"] == pytest.approx(0.01) and rel[0]["hit_rate"] == pytest.approx(0.01)
    # confronto modelli: per ogni caso una distribuzione sui risultati → log-loss multiclasse
    cases = [({(1, 0): 0.7, (2, 0): 0.3}, (1, 0)), ({(1, 0): 0.2, (2, 0): 0.8}, (2, 0))]
    assert V.multiclass_log_loss(cases) == pytest.approx(-(0.5 * (V.math.log(0.7) + V.math.log(0.8))))
    tail = V.tail_calibration(cases + [({(0, 5): 0.001}, (1, 0))], p_max=0.02)
    assert tail["n"] == 1 and tail["hits"] == 0


def test_fattore_di_coda_e_calibratore_il_piu_prudente():
    # fattore CONTINUO (review F12): f0 per p→0, (1+f0)/2 a p = 5 %, →1 oltre; p·f(p) crescente
    assert M.apply_tail_factor(0.0001, 1.7) == pytest.approx(0.0001 * 1.7, rel=0.01)
    assert M.apply_tail_factor(0.05, 1.7) == pytest.approx(0.05 * 1.35)
    assert M.apply_tail_factor(0.20, 1.7) < 0.20 * 1.15 and M.apply_tail_factor(0.20, 1.7) > 0.20
    ps = [i / 1000 for i in range(1, 300)]
    out = [M.apply_tail_factor(p, 1.7) for p in ps]
    assert all(b > a for a, b in zip(out, out[1:]))            # monotono
    assert M.apply_tail_factor(0.9, 5.0) <= 1.0 and M.apply_tail_factor(0.01, 0) == 0.01 and M.apply_tail_factor(0.01, 1.0) == 0.01
    st = M.LiveState(minute=60, score_home=0, score_away=0)
    probs = {(3, 1): 0.010}
    runners = [_r(1, "3 - 1", 40.0, 50)]         # P implicita 2,5 %: sopra la P corretta (mercato la sovraprezza)
    # senza calibratore: fattore applicato (continuo) → ≈1,58 % (audit p_model), grezza 1,0 %
    sel = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120, min_liquidity=5, p_max=0.05, tail_factor=1.7)
    assert sel.p_model == pytest.approx(M.apply_tail_factor(0.010, 1.7)) and sel.raw == pytest.approx(0.010)
    # con un calibratore che agisce: vince la correzione PIÙ PRUDENTE (max), mai la somma
    class _Cal:
        def apply(self, p, family, minute):
            return p * 2.0
    sel2 = M.select_by_model(runners, probs, state=st, price_min=20, price_max=120, min_liquidity=5, p_max=0.05,
                             tail_factor=1.7, calibrator=_Cal())
    assert sel2.p_model == pytest.approx(0.020)
    # famiglie del calibratore condiviso: nomi REALI delle tabelle (cs_cell / hts_cell)
    assert M.CALIBRATION_FAMILY_FT == "cs_cell" and M.CALIBRATION_FAMILY_HT == "hts_cell"
    M.reset_calibration_cache()
    cal = M.load_calibrator(None)                                 # file di default del repo
    assert cal is not None
    ok, n = cal.lookup("cs_cell", 60)
    assert ok and n > 0
    assert M.apply_calibration(0.01, "cs_cell", 60, cal) > 0.01  # la coda del CS viene alzata
