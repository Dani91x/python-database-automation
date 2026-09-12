"""AUDIT 11/09/2026 (sera) — sezione 3 OMEGA + R3 + item condivisi.

Un test per ogni item dell'audit (`Betfair/AUDIT_2026-09-11_omega_safe_mike.md`).
Tutto con fake, nessuna rete, nessun DB reale. Money-critical: la liability
deve essere quella VERA, un ordine a esito ignoto è denaro a rischio finché
non è riconciliato, uno stato di errore non si nasconde mai.
"""
from __future__ import annotations

import time
from datetime import timedelta

import pytest

from Betfair.omega import omega_config
from Betfair.omega import omega_db
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import NOW, FakeDB, FakeMarket, _control, _cs, _event, _open_snapshot


# ===========================================================================
# R3 / H-09 — omega_db.upsert_daily_goal: NameError 'datetime' inghiottito
# ===========================================================================
class _FakeTable:
    def __init__(self, sink):
        self.sink = sink

    def upsert(self, row, on_conflict=None):
        self.sink.append(("upsert", row, on_conflict))
        return self

    def execute(self):
        return type("R", (), {"data": [self.sink[-1][1]]})()


class _FakeSB:
    def __init__(self):
        self.calls: list = []

    def table(self, name):
        self.calls.append(("table", name))
        return _FakeTable(self.calls)


def test_r3_upsert_daily_goal_scrive_davvero(monkeypatch):
    """Il metodo veniva chiamato ogni ciclo e falliva SEMPRE (NameError
    'datetime' non importato, inghiottito dall'except): lo snapshot
    dell'obiettivo non arrivava mai al DB e lo storico usava l'obiettivo
    corrente per i giorni passati."""
    sb = _FakeSB()
    monkeypatch.setattr(omega_db, "_sb", lambda: sb)
    assert omega_db.upsert_daily_goal("2026-09-11", 100.0) is True
    upserts = [c for c in sb.calls if c[0] == "upsert"]
    assert len(upserts) == 1
    row = upserts[0][1]
    assert row["day"] == "2026-09-11" and row["goal"] == 100.0
    assert isinstance(row["updated_at"], str) and row["updated_at"].startswith("20")
    assert upserts[0][2] == "day"


def test_r3_snapshot_daily_goal_dal_servizio_scrive_una_volta_per_giorno():
    calls: list = []

    class _DB(FakeDB):
        def upsert_daily_goal(self, day, goal):
            calls.append((day, goal))
            return True

    db = _DB(_control())
    S._DAILY_GOAL_WRITTEN.clear()
    S._snapshot_daily_goal(db, 100.0, NOW)
    S._snapshot_daily_goal(db, 100.0, NOW)     # stesso giorno, stesso valore: una sola scrittura
    S._snapshot_daily_goal(db, 250.0, NOW)     # obiettivo cambiato: si riscrive
    assert [g for _, g in calls] == [100.0, 250.0]
    assert all(len(d) == 10 for d, _ in calls)


# ===========================================================================
# H-06 — liability aperta: una PERDITA BLOCCATA da copertura completa NON è
#        più rischio (rischio 0, P&L bloccato)
# ===========================================================================
def _pos(**over):
    row = {"id": 1, "event_id": "E1", "status": "open", "side": "lay", "price": 20.0,
           "size": 6.0, "liability": 114.0, "pnl": 0.0, "placed_at": NOW.isoformat(),
           "meta": {}}
    row.update(over)
    return row


def test_h06_copertura_completa_rischio_zero_e_pnl_bloccato():
    """Copertura COMPLETA in perdita (−22 bloccati): la perdita è già fatta,
    non è più a rischio. Prima contava 22 € di 'liability aperta'."""
    tr = _pos(status="hedged", meta={"hedged_size": 6.0, "residual_size": 0.0,
                                     "if_win": -22.0, "if_lose": -22.0, "locked_pnl": -22.0})
    assert E.residual_liability(tr) == 0.0
    assert E.locked_open_pnl(tr) == -22.0


def test_h06_copertura_parziale_resta_rischio():
    tr = _pos(meta={"hedged_size": 3.0, "residual_size": 3.0,
                    "if_win": -57.0, "if_lose": 2.0, "locked_pnl": None})
    assert E.residual_liability(tr) == 57.0
    assert E.locked_open_pnl(tr) is None


def test_h06_aggregati_separano_rischio_vivo_e_pnl_bloccato():
    rows = [
        _pos(id=1, status="hedged", meta={"hedged_size": 6.0, "residual_size": 0.0,
                                          "if_win": -22.0, "if_lose": -22.0, "locked_pnl": -22.0}),
        _pos(id=2, event_id="E2", meta={"hedged_size": 3.0, "residual_size": 3.0,
                                        "if_win": -40.0, "if_lose": 1.0, "locked_pnl": None}),
        _pos(id=3, event_id="E3", liability=100.0, meta={}),
    ]
    agg = E.aggregate_trades(rows, E.day_start_utc(NOW))
    assert agg["open_liability"] == 140.0          # 0 (bloccata) + 40 (parziale) + 100 (nuda)
    assert agg["locked_pnl_open"] == -22.0
    assert agg["matches_open"] == 3


# ===========================================================================
# H-02 — 'pending' in riconciliazione (ordine reale a esito IGNOTO): è denaro
#        a rischio e deve contare negli aggregati, con uno stato leggibile
# ===========================================================================
def test_h02_pending_in_riconciliazione_conta_nella_liability():
    rows = [_pos(id=1, status="pending", bet_id=None, liability=114.0,
                 meta={"reason": "place_exception_reconciling", "reconciling": True})]
    agg = E.aggregate_trades(rows, E.day_start_utc(NOW))
    assert agg["open_liability"] == 114.0
    assert agg["reconciling_liability"] == 114.0
    assert agg["matches_open"] == 1
    assert agg["events_today"] == 1


def test_h02_pending_riservato_senza_ordine_non_conta():
    rows = [_pos(id=1, status="pending", meta={"phase": "reserved"})]
    agg = E.aggregate_trades(rows, E.day_start_utc(NOW))
    assert agg["open_liability"] == 0.0 and agg["reconciling_liability"] == 0.0
    assert agg["matches_open"] == 0


def test_h02_place_live_esito_ignoto_scrive_meta_reconciling_e_kind_dedicato():
    class _Boom(FakeMarket):
        def place_lay_live(self, **kw):
            raise RuntimeError("timeout dopo l'accettazione")

    db = FakeDB(_control(mode="live", params={"execution_mode": "rest"}))
    market = _Boom([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["status"] == "pending"
    assert t["meta"]["reason"] == "place_exception_reconciling"
    assert t["meta"]["reconciling"] is True
    kinds = [k for k, _ in db.activity]
    assert "place_reconciling" in kinds          # kind LEGGIBILE dedicato (non solo 'error')
    p = next(p for k, p in db.activity if k == "place_reconciling")
    assert p["critical"] is True and p["trade_id"] == t["id"]
    # e l'aggregato lo conta come rischio vivo
    agg = E.aggregate_trades(db.trades, E.day_start_utc(NOW))
    assert agg["reconciling_liability"] > 0 and agg["open_liability"] > 0


# ===========================================================================
# H-08 — la giornata la dice UNA sola fonte: gli aggregati
# ===========================================================================
def test_h08_aggregati_espongono_tutte_le_chiavi_della_giornata():
    day = E.day_start_utc(NOW)
    ieri = (NOW - timedelta(days=1)).isoformat()
    rows = [
        # oggi: una vinta, una persa, una viva
        _pos(id=1, status="won", pnl=2.0, liability=0.0),
        _pos(id=2, event_id="E2", status="lost", pnl=-10.0, liability=0.0),
        _pos(id=3, event_id="E3", liability=50.0),
        # ieri: regolata (non conta nella giornata) e riserva mai piazzata (mai)
        _pos(id=4, event_id="E4", status="won", pnl=5.0, placed_at=ieri, liability=0.0),
        _pos(id=5, event_id="E5", status="error", liability=0.0),
        _pos(id=6, event_id="E6", status="pending", meta={"phase": "reserved"}),
    ]
    agg = E.aggregate_trades(rows, day)
    assert agg["won_today"] == 1 and agg["lost_today"] == 1
    assert agg["legs_today"] == 3          # error e riserva nuda escluse
    assert agg["events_today"] == 3
    assert agg["live_now"] == 1            # una sola posizione viva ADESSO
    assert agg["realized_today"] == -8.0
    assert agg["realized_profit"] == -3.0


# ===========================================================================
# H-12 — paper via coda flumine: un ERRORE della coda non è un fill pieno
# ===========================================================================
from Betfair.omega.test_omega_flumine_paper import FakeQueueDB, _control as _qcontrol, _mirror  # noqa: E402


def _placed_flumine(db, market, now=NOW):
    S.run_once(market=market, db=db, now=now)
    t = db.trades[0]
    return t, t["meta"]["flumine_request_id"]


def test_h12_coda_in_errore_non_e_un_fill(monkeypatch):
    db = FakeQueueDB(_qcontrol())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    db.queue[rid]["status"] = "error"
    db.queue[rid]["error"] = "market m-1.100 non sottoscritto nel runner"
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=20))
    rows = [x for x in db.trades if x["id"] == t["id"]]
    # riserva LIBERATA (gamba ritentabile) oppure marcata 'error': MAI 'open'
    assert all(r["status"] != "open" for r in rows)
    nf = [p for k, p in db.activity if k == "flumine_no_fill"]
    assert nf and str(nf[0]["reason"]).startswith("request_error")


def test_h12_runner_muto_oltre_deadline_non_e_un_fill():
    db = FakeQueueDB(_qcontrol())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)                     # nessuno specchio
    S.run_once(market=market, db=db,
               now=NOW + timedelta(seconds=45 + S.FLUMINE_CANCEL_GRACE_S + 5))
    rows = [x for x in db.trades if x["id"] == t["id"]]
    assert all(r["status"] != "open" for r in rows)
    assert any(k == "flumine_no_fill" for k, _ in db.activity)


def test_h12_fill_parziale_reale_resta_confermato():
    """La fedeltà non deve rompere il caso buono: € realmente matchati = posizione."""
    db = FakeQueueDB(_qcontrol())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    db.mirrors[f"awlq{rid}"] = _mirror(1.0, 110.0, "EXECUTION_COMPLETE", 0.0)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5))
    t2 = next(x for x in db.trades if x["id"] == t["id"])
    assert t2["status"] == "open" and t2["size"] == 1.0


# ===========================================================================
# H-13 — il retry di gamba (3×/30 s) vale ANCHE sul percorso flumine
# ===========================================================================
def test_h13_fok_ucciso_non_brucia_la_gamba_per_tutta_la_partita():
    db = FakeQueueDB(_qcontrol())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    tid = t["id"]
    db.mirrors[f"awlq{rid}"] = _mirror(0.0, 0.0, "EXPIRED", 0.0)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5))
    # la riserva non è più viva e la gamba è tentabile di nuovo
    assert not [x for x in db.trades if x["id"] == tid and x["status"] in ("open", "pending")]
    assert S._leg_retry_allowed("1.100", "", NOW + timedelta(seconds=40)) is True
    # secondo tentativo: nuova riserva accodata
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=40))
    assert any(x["status"] == "pending" for x in db.trades)


def test_h13_budget_tentativi_rispettato_anche_via_flumine():
    now = NOW
    for i in range(S.LEG_RETRY_MAX):
        S._leg_note_certain_failure("E-h13", "ft_cs", now + timedelta(seconds=60 * i), "flumine")
    assert S._leg_retry_allowed("E-h13", "ft_cs", now + timedelta(hours=1)) is False


# ===========================================================================
# H-04 / H-01 — UNA struttura di stato per il green-up + contratto delle uscite
# ===========================================================================
from Betfair.omega.test_omega_greenup_2026_09_10 import (  # noqa: E402
    _DB as _GDB, _closings, _logs, _params as _gparams, _payload, _run, _sel, _trade, EID, CS_MID,
)


def test_h04_greenup_riuscito_scrive_state_done_e_exit_kind_greenup():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0")
    # bancato 1-3, punteggio 1-2 → distanza 1: trigger 'goal'
    pay = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6, lay_size=500.0, back_size=500.0)])
    assert _run(db, pay, _gparams(greenup_settle_delay_s=0)) == 1
    opened = db.get_trade(tr["id"])
    g = opened["meta"]["greenup"]
    assert g["state"] == "done" and g["reason"] and g["at"]
    assert g["attempts"] == 1
    # H-01 + review H3: exit_kind dal VOCABOLARIO CONDIVISO (exits.ui_exit_kind):
    # questa chiusura blocca una PERDITA → 'loss', non 'greenup'
    assert opened["meta"]["locked_pnl"] < 0
    assert opened["meta"]["exit_kind"] == "loss"
    assert opened["meta"]["exit_reason"]
    assert _closings(db, tr["id"])[0]["meta"]["exit_kind"] == "loss"
    # la regola che ha deciso l'uscita resta leggibile a parte
    assert g["kind"] in ("profit", "loss")
    lg = _logs(db, "greenup")[0]
    assert lg["exit_kind"] == "loss" and lg["state"] == "done"


def test_h04_hold_scrive_state_hold_e_kind_attivita():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="0-0")
    # bancato 1-3 a 0-0: distanza 4, nessun trigger di gol; quota crollata → 'price'
    pay = _payload(50, 0, 0, cs=[_sel(14, "1 - 3", 20.0, 19.0, lay_size=500.0, back_size=500.0)])
    _run(db, pay, _gparams(greenup_settle_delay_s=0, greenup_hold_max_risk=0.9))
    opened = db.get_trade(tr["id"])
    g = opened["meta"].get("greenup") or {}
    assert g.get("state") == "hold" and g.get("reason")
    assert opened["meta"].get("greenup_hold")           # blocco storico per la UI
    assert _logs(db, "greenup_hold")


def test_h04_cieco_scrive_state_blind_e_logga():
    db = _GDB(_control(status="idle"))
    tr = _trade(db)
    for _ in range(S.BLIND_ALERT_CYCLES):
        _run(db, None)
    opened = db.get_trade(tr["id"])
    g = opened["meta"].get("greenup") or {}
    assert g.get("state") == "blind" and g.get("reason")
    assert _logs(db, "greenup_blind")


def test_h04_fallito_scrive_state_failed_next_retry_e_kind_dedicato(monkeypatch):
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0",
                meta={"greenup": {"trigger": "goal", "attempts": 2, "sent": False}})
    pay = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6, lay_size=500.0, back_size=500.0)])
    from Betfair.safe_strategy import execution as X
    monkeypatch.setattr(X, "close_trade", lambda **kw: {"error": "rifiutato_dal_book"})
    _run(db, pay, _gparams(greenup_settle_delay_s=0, greenup_max_attempts=3))
    g = db.get_trade(tr["id"])["meta"]["greenup"]
    assert g["state"] == "failed" and g["failed"] is True
    assert g["next_retry_at"] and g["reason"]
    assert _logs(db, "greenup_failed"), [k for k, _ in db.activity]


def test_h04_residuo_abbandonato_scrive_state_e_logga():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0",
                meta={"greenup": {"trigger": "goal", "attempts": 1, "sent": True, "kind": "loss"},
                      "hedged_size": 2.0, "residual_size": 3.0})
    # bancato 1-3 con punteggio 2-2: irraggiungibile → il residuo non va coperto
    pay = _payload(80, 2, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6)])
    _run(db, pay, _gparams(greenup_settle_delay_s=0))
    g = db.get_trade(tr["id"])["meta"]["greenup"]
    assert g["state"] == "residual_dropped" and g["residual_dropped"] is True
    assert _logs(db, "greenup_residual_dropped")


# ===========================================================================
# M-19 / H-01 — cash out MANUALE: exit_kind='manual' + motivo
# ===========================================================================
def test_m19_cash_out_manuale_scrive_exit_kind_manual():
    from Betfair.omega.test_omega_service import FakeMarket as FM
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0)
    pay = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6, lay_size=500.0, back_size=500.0)])

    class _M(FM):
        def read_book(self, market_id, runners):
            return {"market_id": CS_MID, "status": "OPEN",
                    "runners": [{"selection_id": 14, "back_price": 7.6, "back_size": 500.0,
                                 "lay_price": 8.0, "lay_size": 500.0, "lay_ladder": ((8.0, 500.0),)}]}

    res = S._manual_cashout(market=_M([], None, _open_snapshot()), db=db,
                            payload={"trade_id": tr["id"]}, now=NOW)
    assert res.get("ok") is True
    opened = db.get_trade(tr["id"])
    assert opened["meta"]["exit_kind"] == "manual"
    assert "cash out" in opened["meta"]["exit_reason"].lower()
    assert _closings(db, tr["id"])[0]["meta"]["exit_kind"] == "manual"
    assert pay is not None


# ===========================================================================
# M-06 / L-01 — copertura PARZIALE leggibile: meta.hedge + meta.hedging
# ===========================================================================
def test_m06_copertura_parziale_espone_frazione_e_residuo():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0")
    # liquidità di chiusura minuscola → fill cappato: copertura PARZIALE
    pay = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6, lay_size=2.0, back_size=2.0)])
    _run(db, pay, _gparams(greenup_settle_delay_s=0))
    opened = db.get_trade(tr["id"])
    h = opened["meta"]["hedge"]
    assert 0.0 < h["fraction"] < 1.0
    assert h["remaining_liability"] > 0 and h["complete"] is False
    # review H2: ``hedging`` = una gamba di chiusura è IN VOLO (semantica UNICA
    # dello strato condiviso); qui il fill è confermato e resta solo il residuo
    assert opened["meta"]["hedging"] is False
    assert h["residual_size"] > 0


def test_l01_hedging_falso_a_copertura_completa():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0")
    pay = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6, lay_size=500.0, back_size=500.0)])
    _run(db, pay, _gparams(greenup_settle_delay_s=0))
    opened = db.get_trade(tr["id"])
    assert opened["status"] == "hedged"
    assert opened["meta"]["hedging"] is False
    assert opened["meta"]["hedge"]["complete"] is True
    assert opened["meta"]["hedge"]["remaining_liability"] == 0.0


def test_l02_commissione_fissata_sul_trade():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["commission"] == pytest.approx(0.05)
    assert t["meta"]["commission"] == pytest.approx(0.05)   # leggibile anche dalla UI


# ===========================================================================
# M-11 — delete della riserva fallito: il reconcile PAPER non deve CONFERMARE
#        un fill mai avvenuto
# ===========================================================================
def test_m11_riserva_senza_fill_non_confermata_dal_reconcile():
    class _NoDelete(FakeDB):
        def delete_trade(self, trade_id):
            raise RuntimeError("DB KO")

    db = _NoDelete(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    tid = db.insert_trade({"event_id": "1.100", "market_id": "m-1.100", "selection_id": 9,
                           "side": "lay", "mode": "paper", "origin": "auto",
                           "status": "pending", "price": 50.0, "size": 1.0,
                           "liability": 49.0, "pnl": 0.0, "meta": {"phase": "reserved"}})
    S._leg_certain_failure(db, tid, "1.100", None, NOW, "paper_no_fill")
    tr = next(t for t in db.trades if t["id"] == tid)
    assert tr["meta"]["leg_failed"] is True
    # ora il reconcile paper NON deve aprirla
    S.reconcile_pending(market=market, db=db, now=NOW)
    tr = next(t for t in db.trades if t["id"] == tid)
    assert tr["status"] == "error"
    assert tr["meta"].get("error_final") is True
    assert any(k == "reconciled_error" for k, _ in db.activity)


def test_m11_reconcile_paper_conferma_e_logga_una_riserva_normale():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    tid = db.insert_trade({"event_id": "E-ok", "market_id": "m", "selection_id": 9,
                           "side": "lay", "mode": "paper", "origin": "auto",
                           "status": "pending", "price": 50.0, "size": 1.0,
                           "liability": 49.0, "pnl": 0.0, "meta": {"phase": "reserved"}})
    S.reconcile_pending(market=market, db=db, now=NOW)
    tr = next(t for t in db.trades if t["id"] == tid)
    assert tr["status"] == "open"
    # L-06: la conferma PAPER non era loggata da nessuna parte
    assert any(k == "reconciled_paper" for k, _ in db.activity)


# ===========================================================================
# M-14 — reconcile azione 'error': il meta NON si sovrascrive
# ===========================================================================
def test_m14_reconcile_error_non_perde_il_meta():
    class _M(FakeMarket):
        def list_current_orders(self):
            return []

        def list_cleared_orders(self):
            return []

    db = FakeDB(_control(mode="live"))
    old = (NOW - timedelta(hours=30)).isoformat()
    tid = db.insert_trade({"event_id": "E-live", "market_id": "m", "selection_id": 9,
                           "side": "lay", "mode": "live", "origin": "auto", "phase": "ft_cs",
                           "status": "pending", "price": 50.0, "size": 1.0, "liability": 49.0,
                           "pnl": 0.0, "placed_at": old,
                           "meta": {"model": {"p": 0.1}, "runners": {"9": "1 - 0"}}})
    S.reconcile_pending(market=_M([], None, _open_snapshot()), db=db, now=NOW)
    tr = next(t for t in db.trades if t["id"] == tid)
    assert tr["status"] == "error"
    assert tr["meta"]["reason"] == "reconcile_orphan_old"
    assert tr["meta"]["model"] == {"p": 0.1}        # meta PRESERVATO
    assert tr["meta"]["runners"] == {"9": "1 - 0"}
    assert tr["meta"]["error_final"] is True and tr["meta"]["error_at"]
    assert tr.get("settled_at") in (None, "")     # review L5: non è una regolazione


# ===========================================================================
# M-13 — posizione 'open' su un mercato che non si chiude mai: allarme
# ===========================================================================
def test_m13_posizione_open_troppo_vecchia_allarme_una_volta():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    tid = db.insert_trade({"event_id": "E-old", "market_id": "m-old", "selection_id": 9,
                           "side": "lay", "mode": "paper", "origin": "auto",
                           "status": "open", "price": 50.0, "size": 1.0, "liability": 49.0,
                           "pnl": 0.0, "placed_at": (NOW - timedelta(hours=9)).isoformat(),
                           "kickoff": (NOW - timedelta(hours=9)).isoformat(), "meta": {}})
    S.settle_open(params=omega_config.resolve_params({}), market=market, db=db, now=NOW)
    alerts = [p for k, p in db.activity if k == "stale_open_alert"]
    assert len(alerts) == 1 and alerts[0]["trade_id"] == tid
    S.settle_open(params=omega_config.resolve_params({}), market=market, db=db, now=NOW)
    assert len([p for k, p in db.activity if k == "stale_open_alert"]) == 1   # una volta sola


# ===========================================================================
# M-12 — lambda di ripiego persistiti: il TTL torna a valere
# ===========================================================================
def test_m12_lambda_di_ripiego_salvati_scadono():
    from datetime import datetime as _dt, timezone as _tz
    S._LAMBDA_CACHE.clear()
    real_now = _dt.now(_tz.utc)
    saved_at = (real_now - timedelta(hours=3)).isoformat()

    class _DB(FakeDB):
        def get_event(self, event_id):
            return {"event_id": event_id, "league_id": 135, "fixture_id": None,
                    "model": {"lambda_pre": [1.1, 0.9], "lambda_source": "live_ou",
                              "saved_at": saved_at}}

    db = _DB(_control())
    # nessun payload: la catena non puo' fare meglio -> il salvato STANTIO si usa
    # comunque (mai a occhi chiusi), ma marcato come tale
    out = S._prematch_lambdas(db, "E-m12", None, state=None, params={})
    assert out is not None and out[3].startswith("saved_stale:")
    S._LAMBDA_CACHE.clear()

    class _DB2(_DB):
        def get_event(self, event_id):
            row = super().get_event(event_id)
            row["model"]["saved_at"] = real_now.isoformat()
            return row

    out2 = S._prematch_lambdas(_DB2(_control()), "E-m12b", None, state=None, params={})
    assert out2 is not None and out2[3] == "live_ou"


# ===========================================================================
# L-03 — stats non stantii a bot fermo
# ===========================================================================
def test_l03_stats_azzerate_a_bot_fermo():
    db = FakeDB(_control(status="running"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.control["stats"]["events_total"] >= 1
    db.control["status"] = "stopped"
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5))
    st = db.control["stats"]
    assert st["events_total"] == 0 and st["target_leg"] == 0.0 and st["target_match"] == 0.0
    assert st["legs_remaining"] == 0 and st["matches_remaining"] == 0
    assert st["bot_running"] is False
    assert st["last_cycle"]


# ===========================================================================
# L-05 — gialli nel green-up; cache del fit di mercato senza errori
# ===========================================================================
def test_l05_greenup_usa_i_gialli(monkeypatch):
    seen: list = []

    def _probs(**kw):
        seen.append(kw.get("state"))
        return {(1, 3): 0.2}

    monkeypatch.setattr(S.M, "score_probs", _probs)
    db = _GDB(_control(status="idle"), events={EID: {"fixture_id": 7, "league_id": 135}})
    monkeypatch.setattr(S, "_prematch_lambdas", lambda *a, **k: (1.2, 1.0, 135, "fixture"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0")
    pay = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6, lay_size=500.0, back_size=500.0)])
    pay["score_raw"] = {"score": {"home": {"numberOfYellowCards": 3},
                                  "away": {"numberOfYellowCards": 1}}}
    _run(db, pay, _gparams(greenup_settle_delay_s=0))
    assert seen and (seen[0].yellow_home, seen[0].yellow_away) == (3, 1)
    assert tr is not None


def test_l05_fit_di_mercato_non_mette_in_cache_gli_errori(monkeypatch):
    S._MARKET_FIT_CACHE.clear()
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("grid KO")

    monkeypatch.setattr(S.M, "lambdas_from_market_grid", _boom)
    st = S.M.LiveState(70, 1, 0)
    assert S._market_fit_cached("E", {}, st, 135) is None
    assert S._market_fit_cached("E", {}, st, 135) is None
    assert calls["n"] == 2          # errore transitorio: si riprova, non resta in cache


# ===========================================================================
# L-06 — fasi 2-3 di run_once protette, dedup nel motore v1
# ===========================================================================
def test_l06_aggregati_ko_non_fanno_esplodere_il_ciclo():
    class _DB(FakeDB):
        def aggregates(self, day_start=None):
            raise RuntimeError("RPC giu")

    db = _DB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res.get("skipped") == "aggregates_failed"
    assert any(k == "error" and p.get("reason") == "aggregates_failed" for k, p in db.activity)


def test_l06_scan_ko_non_impedisce_heartbeat_e_stats(monkeypatch):
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())

    def _boom(**kw):
        raise RuntimeError("scan KO")

    monkeypatch.setattr(S, "scan_and_place", _boom)
    res = S.run_once(market=market, db=db, now=NOW)
    assert res.get("placed") == 0
    assert db.control.get("heartbeat_at")
    assert any(k == "error" and p.get("reason") == "scan_phase_failed" for k, p in db.activity)


def test_l06_motore_v1_dedup_dei_log_di_skip():
    # nessun runner nel range di prezzo -> skip 'no_runner_in_range' a ogni ciclo:
    # una riga ogni 10' invece di una ogni 5 s (746 righe in un giorno, review M12)
    db = FakeDB(_control(params={"price_min": 500, "price_max": 900}))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    for i in range(5):
        S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5 * i))
    skips = [p for k, p in db.activity if k == "skip"]
    assert len(skips) == 1


# ===========================================================================
# H-08 — le stats di omega_control portano le STESSE chiavi della RPC
# ===========================================================================
def test_h08_stats_del_controllo_hanno_le_chiavi_della_giornata():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    st = db.control["stats"]
    for k in ("legs_today", "events_today", "won_today", "lost_today", "live_now",
              "realized_today", "open_liability", "locked_pnl_open",
              "reconciling_liability", "bot_running"):
        assert k in st, k
    assert st["bot_running"] is True


# ===========================================================================
# M-04 / M-05 — settlement per POSIZIONE (apertura + chiusure), gamba 'error'
#               terminale
# ===========================================================================
def test_m04_posizione_greenata_regola_con_pnl_di_posizione():
    from Betfair.omega.test_omega_service import _closed_snapshot
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0")
    pay = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6, lay_size=500.0, back_size=500.0)])
    _run(db, pay, _gparams(greenup_settle_delay_s=0))
    assert db.get_trade(tr["id"])["status"] == "hedged"

    class _M(FakeMarket):
        def read_market(self, cs):
            return _closed_snapshot(14)          # il bancato 1-3 SI VERIFICA

    S.settle_open(params=_gparams(), market=_M([], None, _open_snapshot()), db=db, now=NOW)
    opened = db.get_trade(tr["id"])
    legs = _closings(db, tr["id"])
    assert opened["status"] in ("won", "lost") and legs[0]["status"] in ("won", "lost")
    # il P&L della POSIZIONE = somma delle gambe, scritto su ogni riga
    total = round(float(opened["pnl"]) + sum(float(x["pnl"]) for x in legs), 2)
    assert opened["meta"]["position_pnl"] == total
    assert legs[0]["meta"]["position_pnl"] == total
    assert opened["meta"]["position_result"] in ("won", "lost", "flat")


def test_m05_gamba_error_e_terminale_e_non_conta_come_viva():
    rows = [{"id": 1, "event_id": "E1", "status": "error", "side": "lay", "price": 50.0,
             "size": 1.0, "liability": 49.0, "pnl": 0.0, "placed_at": NOW.isoformat(),
             "settled_at": NOW.isoformat(),
             "meta": {"error_final": True, "leg_failed": True}}]
    agg = E.aggregate_trades(rows, E.day_start_utc(NOW))
    assert agg["open_liability"] == 0.0 and agg["matches_open"] == 0
    assert agg["legs_today"] == 0 and agg["live_now"] == 0


# ===========================================================================
# M-10 (backend) — model_use_yellow_cards non è più inerte
# ===========================================================================
def test_m10_parametro_gialli_spento_azzera_i_gialli_nel_modello():
    st = S.M.LiveState(70, 1, 0, 0, 0, yellow_home=4, yellow_away=2)
    assert S._state_for_model(st, {"model_use_yellow_cards": True}) is st
    off = S._state_for_model(st, {"model_use_yellow_cards": False})
    assert (off.yellow_home, off.yellow_away) == (0, 0)
    assert (off.minute, off.score_home, off.score_away) == (70, 1, 0)


# ===========================================================================
# L-06 — list_trades PAGINATA (PostgREST tronca a 1000 in silenzio)
# ===========================================================================
def test_l06_list_trades_paginata(monkeypatch):
    pages: list = []

    class _Q:
        def __init__(self, rows):
            self.rows = rows
            self._range = None

        def select(self, cols):
            return self

        def eq(self, k, v):
            return self

        def order(self, col, **kw):
            return self

        def range(self, a, b):
            self._range = (a, b)
            pages.append((a, b))
            return self

        def execute(self):
            a, b = self._range
            return type("R", (), {"data": self.rows[a:b + 1]})()

    rows = [{"id": i, "status": "open", "placed_at": f"2026-09-11T00:00:{i % 60:02d}"}
            for i in range(1, 2301)]

    class _SB:
        def table(self, name):
            return _Q(rows)

    monkeypatch.setattr(omega_db, "_sb", lambda: _SB())
    out = omega_db.list_trades("open")
    assert len(out) == 2300                      # nessun troncamento a 1000
    assert len(pages) == 3


# ===========================================================================
# L-06 — _LEG_RETRY: spurgo per ETÀ, mai un clear() che regala tentativi
# ===========================================================================
def test_l06_leg_retry_spurgo_per_eta():
    S._LEG_RETRY.clear()
    old = NOW - timedelta(hours=12)
    for i in range(2100):
        S._LEG_RETRY[(f"vecchio{i}", "ft_cs")] = (3, old.timestamp())
    # una gamba bruciata ADESSO non deve tornare tentabile per colpa dello spurgo
    for _ in range(S.LEG_RETRY_MAX):
        S._leg_note_certain_failure("E-vivo", "ft_cs", NOW, "flumine")
    S._leg_note_certain_failure("E-altro", "ht_cs", NOW, "flumine")
    assert len(S._LEG_RETRY) < 2100              # le vecchie sono state spurgate
    assert S._leg_retry_allowed("E-vivo", "ft_cs", NOW + timedelta(minutes=5)) is False


# ===========================================================================
# H-04 — il feed torna: lo stato non resta 'blind' per sempre
# ===========================================================================
def test_h04_feed_tornato_ripulisce_lo_stato_cieco():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="0-0")
    for _ in range(S.BLIND_ALERT_CYCLES):
        _run(db, None)
    assert db.get_trade(tr["id"])["meta"]["greenup"]["state"] == "blind"
    # punteggio lontano dal bancato: nessun trigger, ma il feed c'è
    _run(db, _payload(50, 0, 0, cs=[_sel(14, "1 - 3", 60.0, 58.0)]),
         _gparams(greenup_settle_delay_s=0))
    g = db.get_trade(tr["id"])["meta"].get("greenup")
    assert g is None or g.get("state") != "blind"


# ===========================================================================
# M-19 / M-06 — cash out manuale PARZIALE: motivo esplicito e residuo leggibile
# ===========================================================================
def test_m19_cash_out_manuale_parziale_dice_parziale_e_lascia_il_residuo():
    from Betfair.omega.test_omega_service import FakeMarket as FM

    class _M(FM):
        def read_book(self, market_id, runners):
            return {"market_id": CS_MID, "status": "OPEN",
                    "runners": [{"selection_id": 14, "back_price": 7.6, "back_size": 500.0,
                                 "lay_price": 8.0, "lay_size": 500.0,
                                 "lay_ladder": ((8.0, 500.0),)}]}

    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0)
    res = S._manual_cashout(market=_M([], None, _open_snapshot()), db=db,
                            payload={"trade_id": tr["id"], "fraction": 0.5}, now=NOW)
    assert res.get("ok") is True
    opened = db.get_trade(tr["id"])
    assert opened["meta"]["exit_kind"] == "manual"
    assert "parziale" in opened["meta"]["exit_reason"].lower()
    h = opened["meta"]["hedge"]
    assert h["complete"] is False and 0 < h["fraction"] < 1 and h["remaining_liability"] > 0
    assert opened["meta"]["hedging"] is False      # nessuna chiusura in volo (fill confermato)
    assert any(k == "cashout_manual" for k, _ in db.activity)


# ===========================================================================
# REVIEW 11/09 (sera) — correzioni alla prima passata dell'audit
# ===========================================================================

# --- H1: la perdita BLOCCATA deve restare visibile alle GUARDIE di rischio ---
def test_rev_h1_perdita_bloccata_conta_nello_stop_giornaliero_e_nel_target():
    agg = {"realized_today": -3.0, "locked_pnl_open": -22.0,
           "locked_pnl_open_today": -22.0, "open_liability": 50.0}
    # R "efficace" per stop-loss e target dinamico: il bloccato è denaro perso
    assert E.realized_effective(agg) == -25.0
    # cap di esposizione: la perdita bloccata occupa ancora capitale fino all'incasso
    assert E.open_liability_effective(agg) == 72.0
    # un bloccato POSITIVO non gonfia il rischio né anticipa il profitto
    agg2 = {"realized_today": 1.0, "locked_pnl_open": 8.0,
            "locked_pnl_open_today": 8.0, "open_liability": 10.0}
    assert E.realized_effective(agg2) == 1.0
    assert E.open_liability_effective(agg2) == 10.0


def test_rev_h1_stop_loss_scatta_con_dieci_greenup_bloccati_in_perdita():
    db = FakeDB(_control(params={"daily_loss_cap": 200, "engine": "single"}))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    # 10 posizioni greenate a −22 € bloccati: nessun P&L realizzato, ma −220 € persi
    for i in range(10):
        db.trades.append({
            "id": 900 + i, "event_id": f"EB{i}", "market_id": "m", "selection_id": 1,
            "side": "lay", "mode": "paper", "origin": "auto", "status": "hedged",
            "price": 20.0, "size": 6.0, "liability": 114.0, "pnl": 0.0,
            "placed_at": NOW.isoformat(),
            "meta": {"hedged_size": 6.0, "residual_size": 0.0, "if_win": -22.0,
                     "if_lose": -22.0, "locked_pnl": -22.0}})
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 0
    stops = [p for k, p in db.activity if k == "loss_stop"]
    assert stops and stops[0]["realized"] <= -200


def test_rev_h1_cap_liability_conta_la_perdita_bloccata():
    params = omega_config.resolve_params({"max_open_liability": 100})
    db = FakeDB(_control())
    agg = {"open_liability": 50.0, "locked_pnl_open": -40.0, "locked_pnl_open_today": -40.0}
    from types import SimpleNamespace as _NS
    sel = _NS(selection_id=4, name="3 - 2", price=110.0, lay_size_available=40.0,
              as_selection=lambda: None)
    n = S._size_and_place(
        ev=_event(), cs=_cs(), sel=sel, snapshot=_open_snapshot(), target=2.0,
        minute=42, score_str="1-0", mode="paper", commission=0.05, params=params,
        aggregates=agg, market=FakeMarket([], None, _open_snapshot()), db=db, now=NOW,
        phase="ft_cs")
    assert n == 0
    assert any(k == "skip" and p.get("reason") == "max_open_liability" for k, p in db.activity)


def test_rev_h1_bloccato_di_ieri_non_tocca_lo_stop_di_oggi():
    ieri = (NOW - timedelta(days=1)).isoformat()
    rows = [_pos(id=1, status="hedged", placed_at=ieri,
                 meta={"hedged_size": 6.0, "residual_size": 0.0, "if_win": -22.0,
                       "if_lose": -22.0, "locked_pnl": -22.0})]
    agg = E.aggregate_trades(rows, E.day_start_utc(NOW))
    assert agg["locked_pnl_open"] == -22.0          # rischio/capitale: senza giorno
    assert agg["locked_pnl_open_today"] == 0.0      # giornata: è una partita di ieri
    assert E.realized_effective(agg) == 0.0


# --- H2: UN SOLO writer di meta.hedge / meta.hedging (lo strato condiviso) ---
def test_rev_h2_un_solo_writer_dello_stato_hedge():
    assert not hasattr(S, "_stamp_hedge_meta"), "il writer duplicato va rimosso"


def test_rev_h2_stato_hedge_idempotente_nessuna_scrittura_a_vuoto():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0")
    pay = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6, lay_size=500.0, back_size=500.0)])
    _run(db, pay, _gparams(greenup_settle_delay_s=0))
    opened = db.get_trade(tr["id"])
    assert opened["status"] == "hedged"
    h = opened["meta"]["hedge"]
    assert h["complete"] is True and h["remaining_liability"] == 0.0
    assert opened["meta"]["hedging"] is False
    # nessuna chiave "privata" del vecchio writer duplicato
    assert "at" not in h and "size" not in h
    # cicli successivi: la posizione è chiusa, nessun'altra scrittura sull'hedge
    before = dict(opened["meta"]["hedge"])
    _run(db, pay, _gparams(greenup_settle_delay_s=0), now=NOW + timedelta(seconds=60))
    assert db.get_trade(tr["id"])["meta"]["hedge"] == before


# --- H3: green-up chiuso in PERDITA non è un "green-up" per la UI ---
def test_rev_h3_chiusura_in_perdita_e_exit_kind_loss():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0")
    pay = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.0, 7.6, lay_size=500.0, back_size=500.0)])
    _run(db, pay, _gparams(greenup_settle_delay_s=0))
    opened = db.get_trade(tr["id"])
    assert opened["meta"]["locked_pnl"] < 0
    assert opened["meta"]["exit_kind"] == "loss"          # vocabolario condiviso
    assert opened["meta"]["exit_profit"] is False
    assert _closings(db, tr["id"])[0]["meta"]["exit_kind"] == "loss"
    assert db.get_trade(tr["id"])["meta"]["greenup"]["state"] == "done"


def test_rev_h3_take_profit_integrale_e_greenup_vero():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="1-0")
    p = _gparams(greenup_settle_delay_s=0)
    _run(db, _payload(85, 1, 0, cs=[_sel(14, "1 - 3", 1000.0, 990.0,
                                         lay_size=500.0, back_size=500.0)]), p)
    opened = db.get_trade(tr["id"])
    assert opened["meta"]["locked_pnl"] >= 0
    assert opened["meta"]["exit_kind"] == "greenup" and opened["meta"]["exit_profit"] is True
    assert tr is not None


# --- H4: il budget dei tentativi sopravvive al riavvio (lo dice il DB) ---
def test_rev_h4_budget_tentativi_letto_dal_db_dopo_un_riavvio():
    S._LEG_RETRY.clear()
    S._LEG_RETRY_DB.clear()
    # il DB porta già 3 gambe bruciate per (E-h4, ft_cs): nessun nuovo tentativo
    S.load_failed_legs({("E-h4", "ft_cs"): (S.LEG_RETRY_MAX, NOW.timestamp())})
    assert S._leg_retry_allowed("E-h4", "ft_cs", NOW + timedelta(hours=2)) is False
    # una sola gamba bruciata: si riprova, ma non prima di LEG_RETRY_MIN_S
    S.load_failed_legs({("E-h4b", "ft_cs"): (1, NOW.timestamp())})
    assert S._leg_retry_allowed("E-h4b", "ft_cs", NOW + timedelta(seconds=5)) is False
    assert S._leg_retry_allowed("E-h4b", "ft_cs", NOW + timedelta(seconds=40)) is True


def test_rev_h4_lo_stesso_fallimento_non_si_conta_due_volte():
    """Memoria e DB sono due VISTE dello stesso fallimento: si prende il massimo,
    mai la somma — altrimenti il budget si dimezzerebbe a ogni ciclo."""
    S._LEG_RETRY.clear()
    S._LEG_RETRY_DB.clear()
    S._leg_note_certain_failure("E-h4c", "ft_cs", NOW, "flumine")   # ciclo N: 1 fallimento
    assert S._leg_attempts("E-h4c", "ft_cs")[0] == 1
    # ciclo N+1: il DB rilegge LO STESSO fallimento (la riga leg_failed appena scritta)
    S.load_failed_legs({("E-h4c", "ft_cs"): (1, NOW.timestamp())})
    assert S._leg_attempts("E-h4c", "ft_cs")[0] == 1
    assert S._leg_retry_allowed("E-h4c", "ft_cs", NOW + timedelta(seconds=40)) is True
    # un fallimento NUOVO incrementa (il budget parte dal conteggio reale)
    S._leg_note_certain_failure("E-h4c", "ft_cs", NOW + timedelta(seconds=40), "flumine")
    assert S._leg_attempts("E-h4c", "ft_cs")[0] == 2


def test_rev_h4_il_db_espone_le_gambe_bruciate(monkeypatch):
    rows = [
        {"id": 1, "event_id": "E1", "phase": "ft_cs", "closes_trade_id": None,
         "placed_at": "2026-09-11T10:00:00+00:00",
         "meta": {"leg_failed": True, "error_at": "2026-09-11T10:00:05+00:00"}},
        {"id": 2, "event_id": "E1", "phase": "ft_cs", "closes_trade_id": None,
         "placed_at": "2026-09-11T10:01:00+00:00", "meta": {"leg_failed": True}},
        {"id": 3, "event_id": "E1", "phase": "ht_cs", "closes_trade_id": None,
         "placed_at": "2026-09-11T09:00:00+00:00", "meta": {"leg_failed": True}},
        # una chiusura non è una gamba: mai contata
        {"id": 4, "event_id": "E1", "phase": "ft_cs", "closes_trade_id": 1,
         "placed_at": "2026-09-11T10:02:00+00:00", "meta": {"leg_failed": True}},
    ]

    class _Q:
        def select(self, cols):
            return self

        def eq(self, k, v):
            return self

        def gte(self, k, v):
            return self

        def order(self, c, **kw):
            return self

        def range(self, a, b):
            self._r = (a, b)
            return self

        def execute(self):
            a, b = self._r
            return type("R", (), {"data": rows[a:b + 1]})()

    monkeypatch.setattr(omega_db, "_sb", lambda: type("SB", (), {"table": lambda s, n: _Q()})())
    out = omega_db.failed_legs("2026-09-08T00:00:00+00:00")
    assert out[("E1", "ft_cs")][0] == 2
    assert out[("E1", "ht_cs")][0] == 1
    assert out[("E1", "ft_cs")][1] > 0


# --- M2: allarme anche sulle posizioni 'hedged' su mercato che non chiude ---
def test_rev_m2_allarme_stale_anche_sulle_hedged():
    db = _GDB(_control(status="idle"))
    tid = db.insert_trade({"event_id": "E-h", "market_id": "m-h", "selection_id": 9,
                           "side": "lay", "mode": "paper", "origin": "auto",
                           "status": "hedged", "price": 50.0, "size": 1.0,
                           "liability": 49.0, "pnl": 0.0,
                           "placed_at": (NOW - timedelta(hours=10)).isoformat(),
                           "kickoff": (NOW - timedelta(hours=10)).isoformat(),
                           "meta": {"hedged_size": 1.0, "residual_size": 0.0,
                                    "locked_pnl": -2.0, "if_win": -2.0, "if_lose": -2.0,
                                    "closing_ids": [999]}})
    db.insert_trade({"event_id": "E-h", "market_id": "m-h", "selection_id": 9,
                     "side": "back", "mode": "paper", "origin": "auto", "status": "open",
                     "price": 40.0, "size": 1.2, "liability": 0.0, "pnl": 0.0,
                     "closes_trade_id": tid, "meta": {"cashout": True}})
    S.settle_open(params=omega_config.resolve_params({}),
                  market=FakeMarket([], None, _open_snapshot()), db=db, now=NOW)
    alerts = [p for k, p in db.activity if k == "stale_open_alert"]
    assert len(alerts) == 1 and alerts[0]["trade_id"] == tid


# --- M3/M4: cash out manuale parziale ---
def test_rev_m3_exit_profit_del_parziale_dal_valore_pianificato():
    from Betfair.omega.test_omega_service import FakeMarket as FM

    class _M(FM):
        def read_book(self, market_id, runners):
            return {"market_id": CS_MID, "status": "OPEN",
                    "runners": [{"selection_id": 14, "back_price": 990.0, "back_size": 500.0,
                                 "lay_price": 1000.0, "lay_size": 500.0,
                                 "lay_ladder": ((1000.0, 500.0),)}]}

    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0)
    res = S._manual_cashout(market=_M([], None, _open_snapshot()), db=db,
                            payload={"trade_id": tr["id"], "fraction": 0.5}, now=NOW)
    assert res.get("ok") is True
    opened = db.get_trade(tr["id"])
    # sul PARZIALE locked_pnl è None: il segno lo dà planned_lock/worst_case —
    # non è più "sempre False per mancanza di dato" (review M3)
    ref = res.get("locked_pnl")
    if ref is None:
        ref = res.get("planned_lock") if res.get("planned_lock") is not None else res.get("worst_case")
    assert ref is not None
    assert opened["meta"]["exit_profit"] is bool(float(ref) >= 0.0)
    assert "parziale" in opened["meta"]["exit_reason"].lower()


def test_rev_m4_parziale_da_liquidita_riconosciuto():
    from Betfair.omega.test_omega_service import FakeMarket as FM

    class _M(FM):
        def read_book(self, market_id, runners):
            return {"market_id": CS_MID, "status": "OPEN",
                    "runners": [{"selection_id": 14, "back_price": 7.6, "back_size": 0.6,
                                 "lay_price": 8.0, "lay_size": 0.6,
                                 "lay_ladder": ((8.0, 0.6),)}]}

    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0)
    # fraction=1 (integrale richiesta) ma la liquidità copre solo una parte
    res = S._manual_cashout(market=_M([], None, _open_snapshot()), db=db,
                            payload={"trade_id": tr["id"]}, now=NOW)
    assert res.get("ok") is True and float(res.get("residual_size") or 0) > 0
    assert "parziale" in db.get_trade(tr["id"])["meta"]["exit_reason"].lower()


# --- M5: _leg_certain_failure non deve cancellare il meta ---
def test_rev_m5_esito_certo_negativo_conserva_il_meta():
    class _NoDelete(FakeDB):
        def delete_trade(self, trade_id):
            raise RuntimeError("DB KO")

    db = _NoDelete(_control())
    tid = db.insert_trade({"event_id": "E-m5", "market_id": "m", "selection_id": 9,
                           "side": "lay", "mode": "paper", "origin": "auto",
                           "status": "pending", "price": 50.0, "size": 1.0,
                           "liability": 49.0, "pnl": 0.0,
                           "meta": {"phase": "reserved", "model": {"p": 0.02},
                                    "runners": {"9": "1 - 0"}, "requested_size": 1.0}})
    S._leg_certain_failure(db, tid, "E-m5", "ft_cs", NOW, "paper_no_fill")
    m = next(t for t in db.trades if t["id"] == tid)["meta"]
    assert m["error_at"]
    assert m["leg_failed"] is True and m["error_final"] is True
    assert m["model"] == {"p": 0.02} and m["runners"] == {"9": "1 - 0"}
    assert m["requested_size"] == 1.0


# --- M6: a bot fermo non si riscrivono stats e aggregati a ogni ciclo ---
def test_rev_m6_a_bot_fermo_le_stats_non_si_riscrivono_ogni_ciclo():
    calls = {"n": 0}

    class _DB(FakeDB):
        def aggregates(self, day_start=None):
            calls["n"] += 1
            return E.aggregate_trades(self.trades, day_start)

    db = _DB(_control(status="stopped"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S._IDLE_STATS_AT.clear()
    for i in range(5):
        S.run_once(market=market, db=db, now=NOW + timedelta(seconds=5 * i))
    assert calls["n"] == 1                    # una sola RPC nella finestra
    assert db.control["stats"]["bot_running"] is False
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=120))
    assert calls["n"] == 2                    # ricalcolo dopo la finestra


# --- M7: uscita dal cieco: lo stato torna quello VERO, non 'pending' ---
@pytest.mark.parametrize("req,atteso", [
    # uscita INVIATA e residuo nullo → la posizione è coperta: 'done'
    ({"trigger": "goal", "attempts": 1, "sent": True, "kind": "loss",
      "residual_after": 0.0}, "done"),
    # uscita inviata con residuo ancora aperto → 'pending'
    ({"trigger": "goal", "attempts": 1, "sent": True, "kind": "loss",
      "residual_after": 2.5}, "pending"),
    # residuo abbandonato → resta 'residual_dropped'
    ({"trigger": "goal", "attempts": 1, "sent": True, "residual_dropped": True,
      "note": "non copribile"}, "residual_dropped"),
    # tentativi esauriti → resta 'failed'
    ({"trigger": "goal", "attempts": 3, "failed": True}, "failed"),
    # solo sorvegliata → 'hold'
    ({"trigger": "price"}, "hold"),
])
def test_rev_m7_uscita_dal_cieco_ripristina_lo_stato_reale(req, atteso):
    """review M7: tornato il feed, lo stato NON diventa sempre 'pending' — si
    ricostruisce dai fatti (inviata/residuo/fallita), altrimenti una posizione
    già chiusa risultava "in copertura" per il resto della partita."""
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="0-0",
                meta={"greenup": {**req, **S._greenup_state_fields("blind", "cieco", NOW)}})
    S._greenup_clear_blind(db, db.get_trade(tr["id"]), NOW)
    assert db.get_trade(tr["id"])["meta"]["greenup"]["state"] == atteso


def test_rev_m7_cieco_senza_richiesta_pulisce_del_tutto():
    db = _GDB(_control(status="idle"))
    tr = _trade(db, price=55.0, size=5.0, score="0-0",
                meta={"greenup": S._greenup_state_fields("blind", "cieco", NOW)})
    S._greenup_clear_blind(db, db.get_trade(tr["id"]), NOW)
    assert db.get_trade(tr["id"])["meta"].get("greenup") is None


# --- M8: anche quando una fase salta, heartbeat e stats si scrivono ---
def test_rev_m8_heartbeat_scritto_anche_con_aggregati_ko():
    class _DB(FakeDB):
        def aggregates(self, day_start=None):
            raise RuntimeError("RPC giu")

    db = _DB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res.get("skipped") == "aggregates_failed"
    assert db.control.get("heartbeat_at") == NOW.isoformat()
    assert db.control.get("stats", {}).get("last_cycle") == NOW.isoformat()


def test_rev_m8_heartbeat_scritto_anche_con_traded_ids_ko():
    class _DB(FakeDB):
        def traded_event_ids(self):
            raise RuntimeError("DB giu")

    db = _DB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res.get("skipped") == "traded_ids_failed"
    assert db.control.get("heartbeat_at") == NOW.isoformat()


# --- L2: list_trades ordina per DATA, non per stringa ---
def test_rev_l2_list_trades_ordina_per_data_vera(monkeypatch):
    rows = [
        {"id": 1, "status": "open", "placed_at": "2026-09-11T12:00:00Z"},
        {"id": 2, "status": "open", "placed_at": "2026-09-11T10:00:00+00:00"},
        {"id": 3, "status": "open", "placed_at": None},
        {"id": 4, "status": "open", "placed_at": "2026-09-11T11:00:00+02:00"},
    ]

    class _Q:
        def select(self, c):
            return self

        def eq(self, k, v):
            return self

        def order(self, c, **kw):
            return self

        def range(self, a, b):
            self._r = (a, b)
            return self

        def execute(self):
            a, b = self._r
            return type("R", (), {"data": rows[a:b + 1]})()

    monkeypatch.setattr(omega_db, "_sb", lambda: type("SB", (), {"table": lambda s, n: _Q()})())
    out = omega_db.list_trades("open")
    # 4 = 09:00Z, 2 = 10:00Z, 1 = 12:00Z; la riga senza data va IN CODA
    assert [r["id"] for r in out] == [4, 2, 1, 3]


# --- L3/L4: fallback senza RPC coerente con la RPC ---
def test_rev_l3_l4_aggregati_senza_giorno_sono_coerenti():
    rows = [_pos(id=1, status="won", pnl=2.0, liability=0.0),
            _pos(id=2, event_id="E2", status="lost", pnl=-5.0, liability=0.0)]
    agg = E.aggregate_trades(rows)          # nessun day_start
    assert agg["won_today"] == 1 and agg["lost_today"] == 1
    assert agg["matches_won"] == 1 and agg["matches_lost"] == 1
    assert agg["realized_today"] == agg["realized_profit"]
    day = E.aggregate_trades(rows, E.day_start_utc(NOW))
    assert day["matches_won"] == 1 and day["matches_lost"] == 1


# --- L5: una riga 'error' non finge di essere REGOLATA ---
def test_rev_l5_riga_error_senza_settled_at():
    db = FakeQueueDB(_qcontrol())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _placed_flumine(db, market)
    db.queue[rid]["status"] = "error"
    db.queue[rid]["error"] = "market non sottoscritto"
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=20))
    row = db.trades[0]
    assert row["status"] == "error"
    assert row.get("settled_at") in (None, "")       # NON è una regolazione
    assert row["meta"]["error_final"] is True and row["meta"]["error_at"]


# ---------------------------------------------------------------- §17 review (Costituzione)
def test_aggregati_rpc_importi_mai_troncati_a_intero(monkeypatch):
    """`locked_pnl_open_today` (e ogni chiave in euro) NON passa da int(): un
    −0,80 € bloccato non deve diventare 0 (falserebbe `realized_effective`)."""
    from Betfair.omega import omega_db

    class _Res:
        data = {"realized_today": 0.52, "locked_pnl_open_today": -0.80, "locked_pnl_open": -1.25,
                "reconciling_liability": 3.4, "open_liability": 12.34, "events_today": 3, "won_today": 2}

    class _Rpc:
        def __init__(self, *a, **k): pass
        def execute(self): return _Res()

    class _Sb:
        def rpc(self, *a, **k): return _Rpc()

    monkeypatch.setattr(omega_db, "_sb", lambda: _Sb())
    out = omega_db.aggregates(day_start="2026-09-11T22:00:00+00:00") if "day_start" in omega_db.aggregates.__code__.co_varnames else None
    if out is None:  # firma diversa: usa la regola direttamente
        assert omega_db._is_money_key("locked_pnl_open_today") and not omega_db._is_money_key("events_today")
        return
    assert out["locked_pnl_open_today"] == -0.80
    assert out["locked_pnl_open"] == -1.25 and out["reconciling_liability"] == 3.4
    assert out["events_today"] == 3 and isinstance(out["events_today"], int)
