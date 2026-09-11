"""GREEN-UP AUTOMATICO di Omega (10/09/2026, COSTITUZIONE §12) — fake, nessuna rete.

Garanzie:
  - trigger per DISTANZA (il risultato bancato è a ≤1 gol): uscita dopo il
    ritardo di assestamento, kind 'loss', numeri nel log 'greenup';
  - trigger per CROLLO DELLA QUOTA (lay ≤ ratio × ingresso): decisione a modello
    (decide_time_exit) con riserva della P implicita del feed;
  - HOLD quando la P(perdita) del modello è minuscola (log 'greenup_hold' una volta);
  - TAKE-PROFIT: al minuto ≥ soglia se il cash-out blocca ≥ frac dello stake;
  - RESIDUO (fill cappato dalla liquidità): ritentato con cooldown e cap;
  - mai un doppio invio con una chiusura 'pending'; bot fermo → gestisce lo stesso;
  - hook di CALIBRAZIONE della selezione guardato (modulo assente / rotto → P grezza);
  - parametri con default e clamp.
"""
from __future__ import annotations

import sys
import types
from datetime import timedelta

import pytest

from Betfair.omega import omega_config
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_model as M
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import NOW, FakeDB, FakeMarket, _open_snapshot

EID = "e1"
CS_MID = "m-e1-CS"
HT_MID = "m-e1-HT"


# ---------------------------------------------------------------------------
# fake
# ---------------------------------------------------------------------------
class _DB(FakeDB):
    """FakeDB storico + accessor del cash-out (get_trade/closing_trades_for/hedged)."""

    def __init__(self, control, events=None):
        super().__init__(control)
        self.events = events or {}

    def get_event(self, event_id):
        return self.events.get(event_id)

    def insert_trade(self, trade):
        # fedeltà a migrations/omega_cashout.sql §2b: gli unique parziali
        # (gamba / gamba automatica) ESCLUDONO le chiusure (closes_trade_id NOT NULL)
        if trade.get("closes_trade_id"):
            self._id += 1
            row = dict(trade)
            row["id"] = self._id
            row.setdefault("placed_at", NOW.isoformat())
            self.trades.append(row)
            return self._id
        return super().insert_trade(trade)

    def get_trade(self, trade_id):
        return next((t for t in self.trades if t["id"] == int(trade_id)), None)

    def hedged_trades(self):
        return self.list_trades("hedged")

    def closing_trades_for(self, ids):
        return [t for t in self.trades if t.get("closes_trade_id") in set(int(i) for i in ids)]

    def traded_legs(self):
        return {(t["event_id"], t.get("phase")) for t in self.trades}


def _params(**over):
    # P "grezza" del modello (fattore di coda 1, calibratore spento, λ certi): i numeri
    # dei test storici restano quelli; il green-up con la P CALIBRATA è testato a parte
    base = {"execution_mode": "rest", "commission_pct": 5, "greenup_settle_delay_s": 30,
            "model_tail_factor": 1.0, "model_calibration": "off", "model_lambda_cv": 0.0}
    base.update(over)
    return omega_config.resolve_params(base)


def _sel(sid, name, lay, back, *, lay_size=40.0, back_size=100.0):
    return {"selection_id": sid, "name": name, "lay": lay, "lay_size": lay_size,
            "back": back, "back_size": back_size, "runner_status": "ACTIVE"}


def _payload(minute, sh, sa, *, cs=None, ht=None, cs_status="OPEN"):
    p = {"minute": minute, "score_home": sh, "score_away": sa, "inplay": True,
         "red_home": 0, "red_away": 0, "event_name": "Nord v Sud"}
    if cs is not None:
        p["cs"] = {"market_id": CS_MID, "status": cs_status, "inplay": True, "selections": cs}
    if ht is not None:
        p["ht"] = {"market_id": HT_MID, "status": "OPEN", "inplay": True, "selections": ht}
    return p


def _trade(db, *, phase="ft_cs", market_id=CS_MID, sid=14, name="1 - 3", price=55.0, size=5.0,
           score="1-0", minute=60, origin="auto", meta=None):
    tid = db.insert_trade({
        "event_id": EID, "event_name": "Nord v Sud", "market_id": market_id, "selection_id": sid,
        "runner_name": name, "side": "lay", "mode": "paper", "origin": origin, "price": price,
        "size": size, "liability": E.liability_from_lay(size, price), "commission": 0.05,
        "target": 2.5, "minute_at_entry": minute, "score_at_entry": score, "phase": phase,
        "status": "open", "pnl": 0.0, "meta": meta or {},
    })
    return db.get_trade(tid)


def _run(db, payload, params=None, *, now=NOW, market=None):
    return S.process_auto_greenup(params=params or _params(), market=market or FakeMarket([], None, _open_snapshot()),
                                  db=db, now=now, feed=lambda eid: payload if eid == EID else None)


def _closings(db, tid):
    return [t for t in db.trades if t.get("closes_trade_id") == tid]


def _logs(db, kind):
    return [p for k, p in db.activity if k == kind]


@pytest.fixture
def lambdas(monkeypatch):
    import Betfair.stream.db as sdb
    monkeypatch.setattr(sdb, "get_fixture_prematch_lambdas", lambda fid: (1.6, 1.1, 135))
    S._LAMBDA_CACHE.clear()


@pytest.fixture
def no_lambdas():
    S._LAMBDA_CACHE.clear()


def _db_with_model():
    return _DB({"id": 1, "status": "running", "mode": "paper", "daily_goal": 100.0, "params": {}},
               events={EID: {"fixture_id": 7, "league_id": 135}})


# ---------------------------------------------------------------------------
# trigger per DISTANZA + ritardo di assestamento + uscita col rischio reale
# ---------------------------------------------------------------------------
def test_trigger_gol_esce_dopo_assestamento_e_marca_le_due_righe(lambdas):
    db = _db_with_model()
    tr = _trade(db)                                   # lay 1-3 @55 sull'1-0
    # 1-2 al 70': il bancato è a UN gol; modello p≈0.147 (< cap 0.15) ma il back 8.0
    # offre almeno l'EV del tenere (bloccato −29.4 ≥ EV −35.5) → si esce
    goal = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.2, 8.0)])
    assert _run(db, goal, now=NOW) == 0               # gol appena visto: si aspetta l'assestamento
    assert _closings(db, tr["id"]) == []
    assert _run(db, goal, now=NOW + timedelta(seconds=29)) == 0
    assert _run(db, goal, now=NOW + timedelta(seconds=30)) == 1
    legs = _closings(db, tr["id"])
    assert len(legs) == 1 and legs[0]["side"] == "back" and legs[0]["status"] == "open"
    assert legs[0]["origin"] == "auto" and legs[0]["phase"] == "ft_cs"
    opened = db.get_trade(tr["id"])
    assert opened["status"] == "hedged"               # fill pieno → posizione chiusa
    # AUDIT 11/09 (H-01) + review H3: exit_kind dal VOCABOLARIO CONDIVISO
    # (exits.ui_exit_kind): 'greenup' SOLO se integrale e bloccato >= 0. Qui la
    # chiusura blocca una PERDITA -> 'loss' (il badge "CHIUSO IN GREEN-UP" su una
    # perdita sarebbe una bugia); la regola che ha deciso sta in greenup.kind.
    assert opened["meta"]["exit_kind"] == "loss" and opened["meta"]["exit_reason"]
    assert opened["meta"]["exit_profit"] is False
    assert opened["meta"]["greenup"]["kind"] == "loss"
    assert opened["meta"]["greenup"]["state"] == "done"
    assert legs[0]["meta"]["exit_kind"] == "loss" and legs[0]["meta"]["exit_reason"] == opened["meta"]["exit_reason"]
    assert opened["meta"]["locked_pnl"] < 0
    log = _logs(db, "greenup")
    assert len(log) == 1
    g = log[0]
    assert g["trigger"] == "goal" and g["minute"] == 70 and g["score"] == "1-2" and g["laid_score"] == "1-3"
    assert g["p_lose"] is not None and 0.02 < g["p_lose"] < 0.15 and g["p_source"] == "model"
    assert g["locked_pnl"] < 0 and g["back_price"] == 8.0 and g["size"] > 0 and g["trade_id"] == tr["id"]
    assert g["ev_hold"] is not None and g["locked_pnl"] >= g["ev_hold"] - 0.10 and g["decision"] == "exit"
    assert g["exit_kind"] == "loss" and g["kind"] == "loss" and g["state"] == "done"
    # ciclo successivo: posizione chiusa → nulla da fare (mai un secondo invio)
    assert _run(db, goal, now=NOW + timedelta(seconds=60)) == 0
    assert len(_closings(db, tr["id"])) == 1


def test_ritardo_zero_esce_subito_e_bot_off_non_fa_nulla(lambdas):
    db = _db_with_model()
    tr = _trade(db)
    goal = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.2, 8.0)])
    assert _run(db, goal, params=_params(greenup_mode="off")) == 0
    assert _run(db, goal, params=_params(greenup_enabled=False)) == 0
    assert _closings(db, tr["id"]) == []
    assert _run(db, goal, params=_params(greenup_settle_delay_s=0)) == 1


def test_trigger_gol_tiene_se_p_lose_bassa_poi_esce_oltre_il_cap(monkeypatch, lambdas):
    db = _db_with_model()
    tr = _trade(db)
    goal = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 6.0, 5.8)])   # bloccato −42.4
    monkeypatch.setattr(M, "score_probs", lambda **kw: {(1, 3): 0.01})
    p = _params(greenup_settle_delay_s=0)
    assert _run(db, goal, p) == 0
    assert _run(db, goal, p, now=NOW + timedelta(seconds=20)) == 0
    holds = _logs(db, "greenup_hold")
    assert len(holds) == 1 and holds[0]["p_lose"] == 0.01 and holds[0]["trigger"] == "goal"
    # profitto del tenere al NETTO della commissione 5 % (§16 review MED-3): 5 → 4,75
    assert holds[0]["decision"] == "hold" and holds[0]["ev_hold"] == pytest.approx(0.99 * 4.75 - 0.01 * 270, abs=0.01)
    assert db.get_trade(tr["id"])["meta"]["greenup_hold"]["p_lose"] == 0.01
    assert _closings(db, tr["id"]) == []
    # p 0.05: EV(tengo) = 0.95·5 − 0.05·270 = −8.75 > bloccato −42.4 → ancora tengo
    monkeypatch.setattr(M, "score_probs", lambda **kw: {(1, 3): 0.05})
    assert _run(db, goal, p, now=NOW + timedelta(seconds=40)) == 0
    assert len(_logs(db, "greenup_hold")) == 2
    # p 0.16 ≥ cap 0.15 → esco
    monkeypatch.setattr(M, "score_probs", lambda **kw: {(1, 3): 0.16})
    assert _run(db, goal, p, now=NOW + timedelta(seconds=60)) == 1
    opened = db.get_trade(tr["id"])
    assert opened["status"] == "hedged" and "greenup_hold" not in opened["meta"]
    assert _logs(db, "greenup")[0]["p_lose"] == 0.16


def test_caso_vivo_trade_70_tiene_a_p_012_esce_a_016_e_a_distanza_zero(monkeypatch, lambdas):
    """Lay 1-2 @55, stake 2.16, liability 116.64; gol → 1-1 al 28', back 4.90:
    bloccato −22.1, EV(tengo) = 0.88·2.16 − 0.12·116.64 = −12.1 → uscire butta 10 €."""
    db = _db_with_model()
    tr = _trade(db, phase=None, sid=12, name="1 - 2", price=55.0, size=2.16, score="1-0", minute=20)
    goal = _payload(28, 1, 1, cs=[_sel(12, "1 - 2", 5.0, 4.90)])
    p = _params(greenup_settle_delay_s=0)
    monkeypatch.setattr(M, "score_probs", lambda **kw: {(1, 2): 0.12})
    assert _run(db, goal, p) == 0
    h = _logs(db, "greenup_hold")[0]
    assert h["decision"] == "hold" and h["p_lose"] == 0.12
    assert h["locked_pnl"] == pytest.approx(-22.08, abs=0.05)
    # hold_profit al NETTO della commissione (§16 MED-3): 2,16·0,95 = 2,052 → EV −12,19
    assert h["ev_hold"] == pytest.approx(-12.19, abs=0.02)
    assert h["loss_if_lose"] == pytest.approx(116.64, abs=0.01) and h["hold_profit"] == pytest.approx(2.05, abs=0.01)
    assert _closings(db, tr["id"]) == []
    # stessa situazione, p 0.16 ≥ cap 0.15 → esco
    monkeypatch.setattr(M, "score_probs", lambda **kw: {(1, 2): 0.16})
    assert _run(db, goal, p, now=NOW + timedelta(seconds=20)) == 1
    g = _logs(db, "greenup")[0]
    assert g["decision"] == "exit" and g["p_lose"] == 0.16 and g["ev_hold"] is not None
    # DISTANZA 0: il bancato è il punteggio corrente → esco anche con p minuscola
    db2 = _db_with_model()
    tr2 = _trade(db2, phase=None, sid=12, name="1 - 2", price=55.0, size=2.16, score="1-0", minute=20)
    monkeypatch.setattr(M, "score_probs", lambda **kw: {(1, 2): 0.01})
    assert _run(db2, _payload(35, 1, 2, cs=[_sel(12, "1 - 2", 1.8, 1.7)]), p) == 1
    g2 = _logs(db2, "greenup")[0]
    assert g2["distance"] == 0 and g2["p_lose"] == 0.01
    assert g2["exit_kind"] == "loss" and g2["kind"] == "loss"
    assert db2.get_trade(tr2["id"])["status"] == "hedged"


def test_bancato_irraggiungibile_o_lontano_nessuna_azione(lambdas):
    db = _db_with_model()
    tr = _trade(db)
    assert _run(db, _payload(70, 2, 0, cs=[_sel(14, "1 - 3", 900.0, 800.0)]), _params(greenup_settle_delay_s=0)) == 0
    assert _run(db, _payload(70, 1, 0, cs=[_sel(14, "1 - 3", 50.0, 48.0)]), _params(greenup_settle_delay_s=0)) == 0
    assert _closings(db, tr["id"]) == []
    assert db.get_trade(tr["id"])["status"] == "open"


# ---------------------------------------------------------------------------
# trigger per CROLLO DELLA QUOTA
# ---------------------------------------------------------------------------
def test_trigger_quota_decisione_a_modello_con_riserva_di_mercato(no_lambdas):
    db = _DB({"id": 1, "status": "running", "mode": "paper", "daily_goal": 100.0, "params": {}})
    tr = _trade(db)                                  # ingresso @55
    p = _params(greenup_settle_delay_s=0)
    assert _run(db, _payload(70, 1, 0, cs=[_sel(14, "1 - 3", 30.0, 28.0)]), p) == 0   # 30/55 > 0.5
    assert _run(db, _payload(70, 1, 0, cs=[_sel(14, "1 - 3", 20.0, 19.0)]), p) == 1   # 20/55 ≤ 0.5
    g = _logs(db, "greenup")[0]
    assert g["trigger"] == "price" and g["p_source"] == "market" and g["p_lose"] == pytest.approx(1 / 19, abs=1e-4)
    assert g["exit_kind"] == "loss" and g["kind"] == "loss"
    assert db.get_trade(tr["id"])["status"] == "hedged"


def test_trigger_quota_tiene_con_modello_a_margine_ampio(monkeypatch, lambdas):
    db = _db_with_model()
    tr = _trade(db)
    monkeypatch.setattr(M, "score_probs", lambda **kw: {(1, 3): 0.005})
    crash = _payload(70, 1, 0, cs=[_sel(14, "1 - 3", 20.0, 19.0)])
    assert _run(db, crash, _params(greenup_settle_delay_s=0)) == 0
    assert _logs(db, "greenup_hold")[0]["trigger"] == "price"
    assert _closings(db, tr["id"]) == []


# ---------------------------------------------------------------------------
# TAKE-PROFIT
# ---------------------------------------------------------------------------
def test_take_profit_blocca_il_profitto_quasi_pieno(lambdas):
    db = _db_with_model()
    tr = _trade(db)                                  # stake 5 → serve locked ≥ 4.5
    p = _params(greenup_settle_delay_s=0)
    assert _run(db, _payload(70, 1, 0, cs=[_sel(14, "1 - 3", 1000.0, 990.0)]), p) == 0   # minuto < 80
    assert _run(db, _payload(85, 1, 0, cs=[_sel(14, "1 - 3", 320.0, 300.0)]), p) == 0    # 5·(1−55/300)=4.08 < 4.5
    assert _run(db, _payload(85, 1, 0, cs=[_sel(14, "1 - 3", 1000.0, 990.0)]), p) == 1
    g = _logs(db, "greenup")[0]
    # take-profit INTEGRALE in utile: questo e' il green-up VERO -> 'greenup'
    assert g["trigger"] == "take_profit" and g["exit_kind"] == "greenup" and g["locked_pnl"] >= 4.5
    assert g["kind"] == "profit"
    opened = db.get_trade(tr["id"])
    assert opened["status"] == "hedged" and opened["meta"]["exit_kind"] == "greenup"
    assert opened["meta"]["exit_profit"] is True
    assert _closings(db, tr["id"])[0]["meta"]["exit_kind"] == "greenup"


# ---------------------------------------------------------------------------
# RESIDUO, cooldown, cap, mai doppio invio
# ---------------------------------------------------------------------------
def test_residuo_ritentato_con_cooldown_e_cap(lambdas):
    db = _db_with_model()
    tr = _trade(db)
    p = _params(greenup_settle_delay_s=0, greenup_retry_s=20, greenup_max_attempts=2)
    thin = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.2, 8.0, back_size=1.0)])   # liquidità al best: 1 €
    assert _run(db, thin, p, now=NOW) == 1
    opened = db.get_trade(tr["id"])
    assert opened["status"] == "open" and opened["meta"]["residual_size"] > 0
    assert opened["meta"]["greenup"]["sent"] is True and opened["meta"]["greenup"]["attempts"] == 1
    assert _run(db, thin, p, now=NOW + timedelta(seconds=10)) == 0        # cooldown
    assert len(_closings(db, tr["id"])) == 1
    assert _run(db, thin, p, now=NOW + timedelta(seconds=21)) == 1        # residuo: secondo invio
    legs = _closings(db, tr["id"])
    # chiusure PARZIALI che bloccano una perdita: 'loss', non 'greenup'
    assert len(legs) == 2 and all(l["meta"]["exit_kind"] == "loss" for l in legs)
    assert _logs(db, "greenup")[1]["attempt"] == 2 and _logs(db, "greenup")[1]["residual_before"] > 0
    # cap raggiunto: nessun terzo invio, marcatura 'failed' + log error una volta sola
    assert _run(db, thin, p, now=NOW + timedelta(seconds=42)) == 0
    assert _run(db, thin, p, now=NOW + timedelta(seconds=63)) == 0
    assert len(_closings(db, tr["id"])) == 2
    assert db.get_trade(tr["id"])["meta"]["greenup"]["failed"] is True
    assert len([e for e in _logs(db, "error") if e.get("reason") == "greenup_attempts_exhausted"]) == 1


def test_mai_doppio_invio_con_chiusura_pending(lambdas):
    db = _db_with_model()
    tr = _trade(db)
    # una gamba di chiusura ancora 'pending' (fill flumine in arrivo)
    cid = db.insert_trade({"event_id": EID, "market_id": CS_MID, "selection_id": 14, "side": "back",
                           "mode": "paper", "origin": "auto", "price": 6.0, "size": 5.0, "status": "pending",
                           "closes_trade_id": tr["id"], "meta": {"cashout": True}})
    db.update_trade(tr["id"], meta={"hedge_pending_ids": [cid], "closing_trade_id": cid})
    goal = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 6.0, 5.8)])
    assert _run(db, goal, _params(greenup_settle_delay_s=0)) == 0
    assert len(_closings(db, tr["id"])) == 1
    assert _logs(db, "greenup") == []


def test_feed_assente_o_mercato_sospeso_si_aspetta(lambdas):
    db = _db_with_model()
    tr = _trade(db)
    p = _params(greenup_settle_delay_s=0)
    assert S.process_auto_greenup(params=p, market=FakeMarket([], None, _open_snapshot()), db=db, now=NOW,
                                  feed=lambda eid: None) == 0
    susp = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 6.0, 5.8)], cs_status="SUSPENDED")
    assert _run(db, susp, p) == 0
    assert _closings(db, tr["id"]) == []
    assert any(w.get("wait") == "mercato_sospeso" for w in _logs(db, "greenup_wait"))


def test_gamba_ht_usa_il_blocco_ht_e_orizzonte_primo_tempo(lambdas):
    db = _db_with_model()
    tr = _trade(db, phase="ht_cs", market_id=HT_MID, sid=5, name="0 - 3", price=70.0, score="0-0", minute=30)
    seen = {}
    real = M.score_probs

    def spy(**kw):
        seen.update(kw)
        real(**kw)
        return {(0, 3): 0.5}      # p ≥ cap → esce (qui si collauda il blocco HT + orizzonte)
    import Betfair.omega.omega_model as MM
    MM_real = MM.score_probs
    try:
        MM.score_probs = spy
        pay = _payload(40, 0, 2, ht=[_sel(5, "0 - 3", 4.0, 3.8)], cs=[_sel(14, "1 - 3", 60.0, 58.0)])
        assert _run(db, pay, _params(greenup_settle_delay_s=0)) == 1
    finally:
        MM.score_probs = MM_real
    assert seen.get("half") is True
    leg = _closings(db, tr["id"])[0]
    assert leg["market_id"] == HT_MID and leg["phase"] == "ht_cs"


def test_bot_fermo_gestisce_comunque_le_uscite(lambdas):
    db = _db_with_model()
    db.control["status"] = "stopped"
    db.control["params"] = {"execution_mode": "rest", "greenup_settle_delay_s": 0}
    tr = _trade(db)
    goal = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.2, 8.0)])
    out = S.run_once(market=FakeMarket([], None, _open_snapshot()), db=db, now=NOW,
                     greenup_feed=lambda eid: goal)
    assert out.get("idle") is True and out.get("greenup") == 1
    assert db.get_trade(tr["id"])["status"] == "hedged"
    assert len(_closings(db, tr["id"])) == 1


# ---------------------------------------------------------------------------
# calibrazione della selezione (hook guardato)
# ---------------------------------------------------------------------------
def _runner(sid, name, lay, size):
    return E.ScoreRunner(selection_id=sid, name=name, lay_price=lay, lay_size=size)


def _fake_calibration_module(factor=3.0, broken=False):
    mod = types.ModuleType("Betfair.safe_strategy.calibration")

    class Calibrator:
        loaded: list = []

        @classmethod
        def load(cls, path=None):
            cls.loaded.append(path)
            return cls()

        def apply(self, p, family, minute):
            if broken:
                raise RuntimeError("boom")
            return min(1.0, p * factor) if family == "cs" else p
    mod.Calibrator = Calibrator
    return mod


def test_calibrazione_hook_guardato(monkeypatch):
    st = M.LiveState(60, 1, 0)
    probs = {(1, 3): 0.004, (4, 0): 0.005}
    runners = [_runner(14, "1 - 3", 55.0, 40), _runner(15, "4 - 0", 60.0, 40)]
    kw = dict(state=st, price_min=20, price_max=120, min_liquidity=5, p_max=0.02)
    # modulo presente → P calibrata usata nella selezione, grezza nell'audit
    _fake = _fake_calibration_module()
    monkeypatch.setitem(sys.modules, "Betfair.safe_strategy.calibration", _fake)
    # se il modulo reale e' gia' stato importato da altri test, `from pkg import x`
    # legge l'ATTRIBUTO del package: va sostituito anche quello
    import Betfair.safe_strategy as _pkg
    monkeypatch.setattr(_pkg, "calibration", _fake, raising=False)
    M.reset_calibration_cache()
    cal = M.load_calibrator("")
    assert cal is not None
    sel = M.select_by_model(runners, probs, calibrator=cal, family="cs", **kw)
    assert sel.name == "1 - 3" and sel.p_model_raw == 0.004 and sel.p_model == pytest.approx(0.012)
    audit = M.audit_block(sel, lh_pre=1.5, la_pre=1.0, source="fixture", state=st, half=False)
    assert audit["p_model_raw"] == 0.004 and audit["p_model"] == pytest.approx(0.012) and audit["calibrated"] is True
    # famiglia HT: il fake non tocca → grezza; la calibrazione può ESCLUDERE (p_max) un runner
    assert M.select_by_model(runners, probs, calibrator=cal, family="hts", **kw).p_model == 0.004
    assert M.select_by_model(runners, probs, calibrator=cal, family="cs", **{**kw, "p_max": 0.01}) is None
    # apply rotto → P grezza, mai un crash
    _broken = _fake_calibration_module(broken=True)
    monkeypatch.setitem(sys.modules, "Betfair.safe_strategy.calibration", _broken)
    monkeypatch.setattr(_pkg, "calibration", _broken, raising=False)
    M.reset_calibration_cache()
    sel = M.select_by_model(runners, probs, calibrator=M.load_calibrator(""), family="cs", **kw)
    assert sel.p_model == sel.p_model_raw == 0.004
    # modulo assente → nessun calibratore, selezione grezza
    monkeypatch.setitem(sys.modules, "Betfair.safe_strategy.calibration", None)
    monkeypatch.setattr(_pkg, "calibration", None, raising=False)
    M.reset_calibration_cache()
    assert M.load_calibrator("") is None
    sel = M.select_by_model(runners, probs, calibrator=None, **kw)
    assert sel.p_model == sel.p_model_raw == 0.004
    audit = M.audit_block(sel, lh_pre=1.5, la_pre=1.0, source="fixture", state=st, half=False)
    assert audit["calibrated"] is False and audit["p_model_raw"] == audit["p_model"]
    M.reset_calibration_cache()   # niente fake in cache per i test successivi


def test_model_select_rispetta_il_parametro_model_calibration(monkeypatch, lambdas):
    calls = []
    monkeypatch.setattr(M, "load_calibrator", lambda path=None: calls.append(path) or None)
    db = _db_with_model()
    snap = _open_snapshot()
    st = M.LiveState(60, 1, 0)
    S._model_select(db=db, event_id=EID, payload=None, snapshot=snap, state=st, half=False,
                    params=_params(model_calibration="off"), size_needed=1.0)
    assert calls == []
    S._model_select(db=db, event_id=EID, payload=None, snapshot=snap, state=st, half=False,
                    params=_params(model_calibration="auto", model_calibration_path="x.json"), size_needed=1.0)
    assert calls == ["x.json"]


# ---------------------------------------------------------------------------
# parametri
# ---------------------------------------------------------------------------
def test_parametri_greenup_default_e_clamp():
    p = omega_config.resolve_params({})
    assert p["greenup_enabled"] is True and p["greenup_mode"] == "auto"
    assert p["greenup_trigger_distance"] == 1 and p["greenup_price_trigger_ratio"] == 0.5
    assert p["greenup_settle_delay_s"] == 30
    assert p["greenup_hold_max_risk"] == 0.02 and p["greenup_risk_cap"] == 0.15 and p["greenup_ev_margin"] == 0.10
    assert p["greenup_take_profit_frac"] == 0.9 and p["greenup_take_profit_minute"] == 80
    assert p["greenup_retry_s"] == 20 and p["greenup_max_attempts"] == 15
    assert p["model_calibration"] == "off" and p["model_calibration_path"] == ""   # §16 F-03: off di default
    p = omega_config.resolve_params({"greenup_mode": "boh", "greenup_price_trigger_ratio": 5,
                                     "greenup_hold_max_risk": 0.5, "greenup_risk_cap": 0.1,
                                     "greenup_trigger_distance": 9, "model_calibration": "x",
                                     "greenup_take_profit_frac": 0})
    assert p["greenup_mode"] == "auto" and p["greenup_price_trigger_ratio"] == 1.0
    assert p["greenup_hold_max_risk"] == 0.1 and p["greenup_trigger_distance"] == 3
    assert p["model_calibration"] == "off" and p["greenup_take_profit_frac"] == 0.1   # valore ignoto → default (off)
    assert omega_config.resolve_params({"greenup_mode": "off"})["greenup_mode"] == "off"
