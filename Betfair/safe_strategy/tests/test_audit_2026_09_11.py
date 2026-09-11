"""Test delle correzioni dell'indagine 11/09/2026 sulla SAFE STRATEGY.

Riferimento: Betfair/AUDIT_2026-09-11_omega_safe_mike.md, sezione 2.
Un blocco per item (C-01, C-03, C-04, H-01, H-03, H-05, H-14..H-21, M-04..M-33,
L-01..L-15). Nessuna rete, nessun Supabase. File ASCII-only (console cp1252).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from Betfair.omega import omega_market as M
from Betfair.safe_strategy import bot_db as DB
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import exits as XE
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, FakeMarket, ReconMarket, _feed_row, _order, _place_payload,
    _reset_module_state, _signal, FakeEngine,
)


@pytest.fixture(autouse=True)
def _clean_module_state():
    _reset_module_state()
    yield
    _reset_module_state()


def _run(db, market=None, **kw):
    return S.run_once(db=db, market=market or FakeMarket(), now=NOW, **kw)


def _closed(winner_id, sid=7):
    return M.MarketSnapshot(
        status="CLOSED", inplay=False, closed=True, winner_selection_id=winner_id,
        runners=[], voided=False,
    )


def _kinds(db, kind):
    return [p for k, p in db.activity if k == kind]


# ===========================================================================
# C-01 - GIORNATA OPERATIVA = giorno di PIAZZAMENTO per TUTTO
# ===========================================================================
def test_c01_realizzato_di_oggi_per_giorno_di_piazzamento():
    """Una posizione piazzata IERI e regolata OGGI resta di ieri; la chiusura
    (green-up di mezzanotte) segue il giorno dell'apertura."""
    day_start = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
    ieri = datetime(2026, 9, 10, 22, 0, tzinfo=timezone.utc).isoformat()
    oggi = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc).isoformat()
    rows = [
        # aperta ieri, regolata oggi: NON e' della giornata di oggi
        {"id": 1, "event_id": "e1", "status": "won", "pnl": 5.0, "liability": 10.0,
         "placed_at": ieri, "settled_at": oggi, "meta": {}},
        # sua chiusura: segue il giorno del PADRE (ieri)
        {"id": 2, "event_id": "e1", "status": "lost", "pnl": -1.0, "liability": 1.0,
         "placed_at": oggi, "settled_at": oggi, "closes_trade_id": 1, "meta": {}},
        # aperta oggi
        {"id": 3, "event_id": "e2", "status": "won", "pnl": 2.0, "liability": 20.0,
         "placed_at": oggi, "settled_at": oggi, "meta": {}},
    ]
    agg = DB.aggregate_rows(rows, day_start=day_start)
    assert agg["realized_total"] == 6.0
    assert agg["realized_today"] == 2.0, "ieri resta ieri, chiusura compresa"
    assert agg["legs_today"] == 1 and agg["events_today"] == 1
    assert agg["day_liability"] == 20.0


def test_c01_le_statistiche_del_servizio_portano_la_giornata_intera():
    db = FakeDB(status="stopped")
    db.insert_trade({"event_id": "e1", "status": "won", "pnl": 3.0, "liability": 10.0,
                     "side": "back", "size": 10.0, "price": 2.0,
                     "settled_at": NOW.isoformat(), "meta": {}})
    res = _run(db)
    st = res["stats"]
    for k in ("realized_today", "won_today", "lost_today", "legs_today",
              "events_today", "reconciling_liability", "params_effective"):
        assert k in st, f"chiave {k} assente dalle stats"
    assert st["won_today"] == 1 and st["lost_today"] == 0
    assert st["risk"]["reconciling_liability"] == 0.0


def test_m16_vinte_e_perse_per_segno_del_pnl_della_posizione():
    """Green-up in utile: apertura 'lost' (-2) + chiusura 'won' (+5) = +3 = UNA
    posizione VINTA, non una vinta e una persa."""
    day = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
    t = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc).isoformat()
    rows = [
        {"id": 1, "event_id": "e1", "status": "lost", "pnl": -2.0, "liability": 10.0,
         "placed_at": t, "settled_at": t, "meta": {}},
        {"id": 2, "event_id": "e1", "status": "won", "pnl": 5.0, "liability": 3.0,
         "placed_at": t, "settled_at": t, "closes_trade_id": 1, "meta": {}},
    ]
    agg = DB.aggregate_rows(rows, day_start=day)
    assert agg["won_today"] == 1 and agg["lost_today"] == 0
    assert agg["realized_today"] == 3.0


# ===========================================================================
# C-03 - cancel VIETATO su una riga in riconciliazione, e la riconciliazione
#        deve CONCLUDERSI
# ===========================================================================
def _pending_reconciling(db, **kw):
    row = {"event_id": "1.1", "market_id": "m1", "selection_id": 7, "side": "back",
           "size": 10.0, "price": 3.0, "status": "pending", "mode": "live",
           "commission": 0.05, "origin": "auto", "signal_key": "k1",
           "meta": {"phase": "reserved", "reason": "place_exception_reconciling"}}
    row.update(kw)
    return db.insert_trade(row)


def test_c03_cancel_di_una_riserva_in_riconciliazione_e_rifiutato():
    db = FakeDB(status="stopped")
    tid = _pending_reconciling(db)
    db.requests.append({"id": 1, "kind": "cancel", "status": "pending",
                        "payload": {"trade_id": tid}})
    # market SENZA api ordini: la riconciliazione non decide, la riga resta viva
    _run(db, market=FakeMarket())
    assert db.requests[0]["status"] == "rejected"
    assert db.requests[0]["result"]["rejected"] == "in riconciliazione"
    assert "riconciliazione" in db.requests[0]["result"]["message"]
    assert db.get_trade(tid) is not None, "mai perdere di vista un ordine reale"
    assert _kinds(db, "cancel_rejected")[0]["trade_id"] == tid


def test_c03_riconciliazione_conclude_ordine_vivo_diventa_open():
    db = FakeDB(status="stopped")
    tid = _pending_reconciling(db)
    mk = ReconMarket(current=[_order(f"safe-t{tid}", matched=10.0, price=3.0)])
    res = _run(db, market=mk)
    assert res["reconciled"] == 1
    assert db.get_trade(tid)["status"] == "open"


def test_c03_riconciliazione_conclude_ordine_assente_diventa_error_con_meta():
    db = FakeDB(status="stopped")
    tid = _pending_reconciling(db,
                               placed_at=(NOW - timedelta(minutes=10)).isoformat())
    res = _run(db, market=ReconMarket())
    assert res["reconciled"] == 1
    t = db.get_trade(tid)
    assert t["status"] == "error"
    assert t["meta"]["reason"] == "reconcile_ordine_assente"
    assert t["meta"]["error_final"] is True and t["settled_at"]


def test_c03_cashout_su_riga_in_riconciliazione_rifiutato():
    db = FakeDB(status="stopped")
    tid = _pending_reconciling(db)
    db.scan_rows = [_feed_row()]
    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": tid}})
    _run(db, market=FakeMarket())
    assert db.requests[0]["status"] == "rejected"


# ===========================================================================
# C-04 - 'niente_da_chiudere' NON e' terminale
# ===========================================================================
def _exit_row(minute, sh, sa, *, back=3.0, lay=3.1, updated_at=None, sid=7):
    ts = (updated_at or NOW).isoformat()
    return {"event_id": "1.1", "sport": "calcio", "updated_at": ts,
            "payload": {"event_name": "Home v Away", "inplay": True, "minute": minute,
                        "score_home": sh, "score_away": sa, "mo_status": "OPEN",
                        "odds": {"home": {"selection_id": sid, "back": back, "lay": lay,
                                          "back_size": 500.0, "lay_size": 500.0},
                                 "away": {"selection_id": 8, "back": 10.0, "lay": 11.0,
                                          "back_size": 100.0, "lay_size": 100.0}}}}


def _base_trade(db, **kw):
    row = {"event_id": "1.1", "event_name": "Home v Away", "sport": "calcio",
           "strategy": "base", "market_id": "m1", "market_type": "MATCH_ODDS",
           "selection_id": 8, "selection_name": "Away", "side": "lay",
           "price": 10.0, "size": 2.0, "liability": 18.0, "commission": 0.05,
           "status": "open", "mode": "paper", "origin": "auto",
           "signal_key": "1.1:base:1-0", "minute_at_entry": 55,
           "score_at_entry": "1-0", "meta": {}}
    row.update(kw)
    return db.insert_trade(row)


class NoPriceMarket(FakeMarket):
    """read_book assente: nessun prezzo opposto -> 'niente_da_chiudere'."""


def _cycle(db, row, market=None, at=None):
    db.scan_rows = [row]
    return S.run_once(db=db, market=market or FakeMarket(), now=at or NOW)


def test_c04_niente_da_chiudere_non_e_terminale_e_si_ritenta():
    db = FakeDB(status="running")
    tid = _base_trade(db)
    # uscita in PERDITA (la sfavorita bancata pareggia): incondizionata, non
    # passa dal gate a modello. La posizione e' un LAY: per chiuderla serve il
    # BACK, che manca dal libro (il lay c'e', quindi la selezione e' nel feed).
    _cycle(db, _exit_row(60, 1, 0))
    at = NOW + timedelta(seconds=1)
    _cycle(db, _exit_row(70, 1, 1, updated_at=at), at=at)   # gol: assestamento 30 s
    at = NOW + timedelta(seconds=35)
    row = _exit_row(70, 1, 1, updated_at=at)
    row["payload"]["odds"]["away"].update({"back": None, "back_size": None})
    r = _cycle(db, row, at=at)
    assert r["exits"] == 0
    meta = db.get_trade(tid)["meta"]
    # nessun invio dichiarato e stato VISIBILE 'waiting_price'
    assert meta["exit_requested"]["sent"] is False
    assert meta["exit"]["state"] == "waiting_price"
    assert meta["exit"]["next_retry_at"]
    assert meta["exit_requested"]["attempts"] == 0, "il tentativo non si consuma"
    waits = [p for p in _kinds(db, "exit_wait") if p.get("wait") == "niente_da_chiudere"]
    assert len(waits) == 1
    # il prezzo torna: si chiude (la liability non resta scoperta)
    at = NOW + timedelta(seconds=60)
    r = _cycle(db, _exit_row(71, 1, 1, updated_at=at), at=at)
    assert r["exits"] == 1
    assert db.get_trade(tid)["meta"]["exit"]["state"] == "done"
    assert db.get_trade(tid)["meta"]["exit_kind"] == "loss"


# ===========================================================================
# H-01 - vocabolario CHIUSO di exit_kind + exit_reason su ogni chiusura
# ===========================================================================
def test_h01_vocabolario_exit_kind():
    assert XE.ui_exit_kind("profit", locked=1.5) == "greenup"
    assert XE.ui_exit_kind("time", locked=0.0) == "greenup"
    assert XE.ui_exit_kind("time", locked=-3.0) == "time"
    assert XE.ui_exit_kind("profit", locked=None) == "profit"
    assert XE.ui_exit_kind("profit", locked=1.0, integral=False) == "profit"
    assert XE.ui_exit_kind("loss", locked=-1.0) == "loss"
    assert XE.ui_exit_kind("red_card", locked=-1.0) == "red_card"
    assert XE.ui_exit_kind("mandatory", locked=1.0) == "forced"
    assert XE.ui_exit_kind("profit", locked=1.0, manual=True) == "manual"
    assert XE.ui_exit_kind("qualcosa_di_nuovo", locked=None) == "other"
    for k in ("greenup", "profit", "loss", "time", "red_card", "forced",
              "manual", "other"):
        assert k in XE.EXIT_KINDS


def test_h01_cash_out_manuale_marcato_manual_su_apertura_e_chiusura():
    db = FakeDB(status="stopped")
    tid = _base_trade(db)
    db.scan_rows = [_exit_row(60, 1, 0)]
    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": tid}})
    _run(db)
    assert db.requests[0]["status"] == "done"
    parent = db.get_trade(tid)
    assert parent["meta"]["exit_kind"] == "manual"
    assert "Cash out manuale" in parent["meta"]["exit_reason"]
    legs = [t for t in db.trades if t.get("closes_trade_id") == tid]
    assert legs and legs[0]["meta"]["exit_kind"] == "manual"
    assert legs[0]["meta"]["exit_reason"]


# ===========================================================================
# H-03 - i pending in RICONCILIAZIONE nella liability, ed esposti a parte
# ===========================================================================
def test_h03_liability_dei_pending_in_riconciliazione():
    rows = [
        {"id": 1, "event_id": "e1", "status": "pending", "pnl": 0.0, "liability": 18.0,
         "placed_at": NOW.isoformat(),
         "meta": {"reason": "place_exception_reconciling"}},
        {"id": 2, "event_id": "e2", "status": "open", "pnl": 0.0, "liability": 5.0,
         "placed_at": NOW.isoformat(), "meta": {}},
    ]
    agg = DB.aggregate_rows(rows)
    assert agg["open_liability"] == 23.0, "l'ordine ignoto puo' essere vivo"
    assert agg["reconciling_liability"] == 18.0
    assert agg["open_count"] == 2


# ===========================================================================
# H-05 / H-17 - nessuno stato terminale: backoff crescente
# ===========================================================================
def test_h05_backoff_crescente():
    assert XE.retry_backoff_s(0) == 0.0
    assert XE.retry_backoff_s(1) == 5.0
    assert XE.retry_backoff_s(2) == 15.0
    assert XE.retry_backoff_s(3) == 60.0
    assert XE.retry_backoff_s(4) == 300.0
    assert XE.retry_backoff_s(99) == 300.0, "oltre la scala si ripete l'ultimo"


def test_h05_uscita_fallita_ha_stato_visibile_e_ritenta_per_sempre():
    class NoClosingDB(FakeDB):
        def insert_trade(self, trade):
            if trade.get("closes_trade_id"):
                raise RuntimeError("db ko")
            return super().insert_trade(trade)

    db = NoClosingDB(status="running")
    tid = _base_trade(db)
    _cycle(db, _exit_row(81, 1, 0))
    st = db.get_trade(tid)["meta"]["exit"]
    assert st["state"] == "retrying" and st["attempts"] == 1
    assert st["last_error"] == "riserva_chiusura_fallita"
    # dentro il backoff non si ritenta
    at = NOW + timedelta(seconds=2)
    _cycle(db, _exit_row(81, 1, 0, updated_at=at), at=at)
    assert db.get_trade(tid)["meta"]["exit"]["attempts"] == 1
    # scaduto il backoff si riprova
    at = NOW + timedelta(seconds=6)
    _cycle(db, _exit_row(81, 1, 0, updated_at=at), at=at)
    assert db.get_trade(tid)["meta"]["exit"]["attempts"] == 2
    assert _kinds(db, "exit_retry")


# ===========================================================================
# H-14 / H-15 - parametri: normalizzazione, clamp scritti sul DB, effettivi
# ===========================================================================
def test_h14_variants_vuote_tornano_ai_default():
    assert S.normalize_variants([]) == ["base", "esatto", "punta", "tennis"]
    assert S.normalize_variants(None) == ["base", "esatto", "punta", "tennis"]
    assert S.normalize_variants(["pippo"]) == ["base", "esatto", "punta", "tennis"]
    assert S.normalize_variants(["tennis", "base"]) == ["base", "tennis"]
    p = S.resolve_params({"variants": []})
    assert p["variants"] == ["base", "esatto", "punta", "tennis"]


def test_h14_variants_vuote_loggano_params_invalid_e_il_db_viene_riallineato():
    db = FakeDB(status="running", params={"variants": []})
    _run(db)
    assert db.control["params"]["variants"] == ["base", "esatto", "punta", "tennis"]
    inv = _kinds(db, "params_invalid")
    assert inv and "variants" in inv[0]["keys"]
    # idempotente: al ciclo successivo non riscrive nulla
    db.activity.clear()
    _run(db)
    assert _kinds(db, "params_invalid") == []


def test_h15_valori_clampati_esposti_ma_mai_riscritti_sul_db():
    """review H2: un clamp NON si persiste. Salvare 0 su daily_loss_stop
    spegnerebbe lo stop perdite per sempre e cancellerebbe l'impostazione."""
    db = FakeDB(status="stopped", params={"risk": {"daily_loss_stop": 50},
                                          "commission_pct": 99})
    res = _run(db)
    # il DB resta come l'utente l'ha scritto
    assert db.control["params"]["risk"]["daily_loss_stop"] == 50
    assert db.control["params"]["commission_pct"] == 99
    # ma il servizio dice a voce alta cosa usa davvero
    cl = _kinds(db, "params_clamped")
    assert cl and cl[0]["persisted"] == []
    eff = res["stats"]["params_effective"]
    assert eff["commission_pct"] == 20.0
    # 50 letto come "-50": lo stop perdite resta ATTIVO
    assert eff["risk"]["daily_loss_stop"] == -50.0
    assert eff["variants"] == ["base", "esatto", "punta", "tennis"]


def test_h15_parametri_coerenti_non_vengono_riscritti():
    db = FakeDB(status="stopped", params={"commission_pct": 5})
    _run(db)
    assert _kinds(db, "params_clamped") == [] and _kinds(db, "params_invalid") == []


# ===========================================================================
# H-18 - cecita' del feed
# ===========================================================================
def test_h18_posizione_viva_senza_riga_feed_logga_feed_blind():
    db = FakeDB(status="stopped")
    tid = _base_trade(db)
    db.scan_rows = []
    res = _run(db)
    assert res["blind"] == 1
    blind = _kinds(db, "feed_blind")
    assert len(blind) == 1 and blind[0]["trade_id"] == tid
    assert db.get_trade(tid)["meta"]["blind_since"]
    # non si ripete a ogni ciclo (2 s): una volta, poi ogni 60 s
    at = NOW + timedelta(seconds=10)
    S.run_once(db=db, market=FakeMarket(), now=at)
    assert len(_kinds(db, "feed_blind")) == 1
    at = NOW + timedelta(seconds=61)
    S.run_once(db=db, market=FakeMarket(), now=at)
    assert len(_kinds(db, "feed_blind")) == 2
    # la riga torna: blind_since sparisce
    db.scan_rows = [_exit_row(60, 1, 0, updated_at=at)]
    S.run_once(db=db, market=FakeMarket(), now=at)
    assert "blind_since" not in db.get_trade(tid)["meta"]
    assert _kinds(db, "feed_back")


# ===========================================================================
# H-19 - budget delle chiamate REST
# ===========================================================================
def test_h19_rest_gate_cadenza_e_budget():
    st = {"last": {}, "cycle_ts": 0.0, "used": 0}
    assert S.rest_gate("m1", 1000.0, state=st) is True
    assert S.rest_gate("m1", 1001.0, state=st) is False, "cadenza minima 10 s"
    assert S.rest_gate("m1", 1011.0, state=st) is True
    used = sum(1 for i in range(20) if S.rest_gate(f"x{i}", 2000.0, state=st))
    assert used == S.REST_BUDGET_PER_CYCLE, "tetto per ciclo"


def test_h19_settlement_non_chiama_betfair_se_il_feed_dice_mercato_aperto():
    class CountingMarket(FakeMarket):
        def __init__(self):
            super().__init__()
            self.reads = 0

        def read_market(self, cs):
            self.reads += 1
            return self.snapshot

    db = FakeDB(status="stopped")
    _base_trade(db)
    mk = CountingMarket()
    mk.snapshot = _closed(999)
    db.scan_rows = [_exit_row(60, 1, 0)]
    S.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW,
                  rows_by_event={"1.1": db.scan_rows[0]})
    assert mk.reads == 0, "mercato aperto nel feed: niente REST"
    # senza riga nel feed la REST si fa
    S.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW,
                  rows_by_event={})
    assert mk.reads == 1


# ===========================================================================
# H-20 - COMBO tutto-o-niente anche DOPO il fill
# ===========================================================================
def test_h20_combo_gamba_non_abbinabile_in_paper_ferma_tutto_prima_della_riserva():
    db = FakeDB(status="running")
    row = _combo_feed_row()
    n = S._auto_trade_combos(db=db, market=FakeMarket(), payload=row["payload"],
                             event_id="1.1", combos=[_combo(avail2=0.0)],
                             params=S.resolve_params({}), mode="paper", now=NOW,
                             rows_by_event={"1.1": row})
    assert n == 0
    assert [t for t in db.trades if t.get("status") == "open"] == []
    assert [p for p in _kinds(db, "skip")
            if p.get("reason") == "combo_gamba_non_abbinabile"]


def _combo_feed_row():
    row = _exit_row(30, 0, 0)
    row["payload"]["ou"] = [{"market_id": "ou25", "status": "OPEN", "selections": [
        {"selection_id": 101, "name": "Under 2.5 Goals", "back": 2.0, "lay": 2.02,
         "back_size": 500.0, "lay_size": 500.0}]}]
    return row


def _combo(avail2=500.0):
    return {"id": "c1", "confidence": 1.0, "edge": 0.5, "rationale": "test",
            "legs": [
                {"market_id": "ou25", "market_type": "OVER_UNDER", "selection_id": 101,
                 "selection_name": "Under 2.5 Goals", "side": "back", "price": 2.0,
                 "size_available": 500.0, "stake_ratio": 0.5},
                {"market_id": "m1", "market_type": "MATCH_ODDS", "selection_id": 7,
                 "selection_name": "Home", "side": "back", "price": 3.0,
                 "size_available": avail2, "stake_ratio": 0.5}]}


def test_h20_combo_incompleta_dopo_il_fill_chiude_subito_la_gamba_fillata():
    """H-20: in LIVE la prima gamba si abbina, la seconda viene rifiutata
    dall'exchange: la posizione NUDA non resta aperta un ciclo di piu'."""
    class HalfMarket(FakeMarket):
        def place_order_live(self, **kw):
            if kw["market_id"] == "m1" and kw["size"] >= 5.0:
                return M.PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                                     size_matched=0.0, avg_price_matched=None)
            return super().place_order_live(**kw)

    db = FakeDB(status="running")
    row = _combo_feed_row()
    mk = HalfMarket()
    n = S._auto_trade_combos(db=db, market=mk, payload=row["payload"],
                             event_id="1.1", combos=[_combo()],
                             params=S.resolve_params({}), mode="live", now=NOW,
                             rows_by_event={"1.1": row})
    assert n == 0, "la combo non e' andata"
    assert _kinds(db, "combo_incomplete")
    # la gamba fillata (ou25) e' stata CHIUSA subito, non e' rimasta nuda
    opened = [t for t in db.trades if not t.get("closes_trade_id")
              and t.get("market_id") == "ou25"]
    assert len(opened) == 1
    closings = [t for t in db.trades if t.get("closes_trade_id") == opened[0]["id"]]
    assert closings, "gamba nuda non chiusa"
    assert closings[0]["meta"]["exit_kind"] == "forced"
    assert "combo incompleta" in closings[0]["meta"]["exit_reason"]
    assert db.get_trade(opened[0]["id"])["status"] == "hedged"


def test_h20_uscita_di_una_gamba_chiude_tutta_la_combo():
    db = FakeDB(status="running")
    row = _exit_row(81, 1, 0)
    row["payload"]["ou"] = [{"market_id": "ou25", "status": "OPEN", "selections": [
        {"selection_id": 101, "name": "Under 2.5 Goals", "back": 1.5, "lay": 1.52,
         "back_size": 500.0, "lay_size": 500.0}]}]
    # gamba 1: strategia 'base' con regola a tempo (innesca l'uscita)
    t1 = _base_trade(db, meta={"combo_id": "c1", "combo_legs": 2})
    # gamba 2: stessa combo, sul mercato O/U
    t2 = _base_trade(db, strategy="model", market_id="ou25",
                     market_type="OVER_UNDER", selection_id=101,
                     selection_name="Under 2.5 Goals", side="back", price=1.5,
                     size=5.0, liability=5.0, signal_key="combo:c1:1",
                     meta={"combo_id": "c1", "combo_legs": 2, "kind": "combo"})
    r = _cycle(db, row)
    assert r["exits"] == 1
    assert [t for t in db.trades if t.get("closes_trade_id") == t1]
    legs2 = [t for t in db.trades if t.get("closes_trade_id") == t2]
    assert legs2, "la gamba sorella deve essere chiusa (o la combo intera o niente)"
    assert legs2[0]["meta"]["exit_kind"] == "forced"
    assert db.get_trade(t2)["meta"]["exit_kind"] == "forced"


# ===========================================================================
# H-21 - budget dei ritentativi del piazzamento
# ===========================================================================
class RejectMarket(FakeMarket):
    def place_order_live(self, **kw):
        return M.PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                             size_matched=0.0, avg_price_matched=None)


def test_h21_piazzamento_rifiutato_ha_un_budget_e_un_backoff():
    db = FakeDB(status="running", mode="live",
                params={"min_size_available_factor": 0, "place_max_attempts": 2})
    eng = FakeEngine([_signal()])
    mk = RejectMarket()
    db.scan_rows = [_feed_row()]
    # 1o tentativo: errore + place_retry
    r = S.run_once(db=db, market=mk, engine=eng, now=NOW)
    assert r["placed"] == 0
    assert _kinds(db, "place_retry"), "primo rifiuto: si ritenta"
    t = [x for x in db.trades if x["status"] == "error"][0]
    assert t["meta"]["place"]["attempts"] == 1 and t["meta"]["place"]["next_retry_at"]
    assert t["meta"]["error_final"] is True and t["settled_at"]
    # dentro il backoff: nessun nuovo ordine
    n_before = len(db.trades)
    S.run_once(db=db, market=mk, engine=eng, now=NOW + timedelta(seconds=2))
    assert len(db.trades) == n_before, "backoff: nessun FOK ogni 2 s"
    # scaduto il backoff: secondo (e ultimo) tentativo
    S.run_once(db=db, market=mk, engine=eng, now=NOW + timedelta(seconds=6))
    assert _kinds(db, "place_exhausted")
    n_before = len(db.trades)
    S.run_once(db=db, market=mk, engine=eng, now=NOW + timedelta(seconds=600))
    assert len(db.trades) == n_before, "budget esaurito: la chiave e' chiusa"


def test_h21_meta_della_riserva_conservato_nell_errore():
    """L-09: il meta della riserva (variant, headline, idempotency_key) non
    viene sovrascritto dal motivo dell'errore."""
    db = FakeDB(status="running", mode="live", params={"min_size_available_factor": 0})
    db.scan_rows = [_feed_row()]
    S.run_once(db=db, market=RejectMarket(), engine=FakeEngine([_signal()]), now=NOW)
    t = [x for x in db.trades if x["status"] == "error"][0]
    assert t["meta"]["variant"] == "base" and t["meta"]["headline"] == "test"
    assert t["meta"]["reason"].startswith("live_not_matched")


# ===========================================================================
# M-04 / M-05 - settlement per POSIZIONE, gamba in errore terminale
# ===========================================================================
def test_m04_settlement_per_posizione_un_solo_evento_e_pnl_totale():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(999)
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0, "status": "hedged",
                           "commission": 0.05, "mode": "paper", "meta": {}})
    cid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "back", "size": 12.0, "price": 5.0, "status": "open",
                           "commission": 0.05, "mode": "paper", "closes_trade_id": tid})
    res = _run(db, market=mk)
    assert res["settled"] == 1
    pos = _kinds(db, "settle_position")
    assert len(pos) == 1, "UN SOLO evento di regolazione per posizione"
    total = round(db.get_trade(tid)["pnl"] + db.get_trade(cid)["pnl"], 2)
    assert pos[0]["position_pnl"] == pytest.approx(total, abs=0.01)
    assert pos[0]["position_result"] in ("won", "lost", "flat")
    # ogni gamba porta l'esito della POSIZIONE (la UI non deve dedurlo)
    for t in (db.get_trade(tid), db.get_trade(cid)):
        assert t["meta"]["position_id"] == tid
        assert t["meta"]["position_pnl"] == pytest.approx(total, abs=0.01)
        assert t["meta"]["position_result"] == pos[0]["position_result"]


def test_m05_gamba_in_errore_e_terminale():
    """Una chiusura non eseguita viene chiusa con settled_at + error_final:
    non resta 'in corso per sempre' negli aggregati."""
    db = FakeDB(status="stopped")

    class NoFillMarket(FakeMarket):
        def place_order_live(self, **kw):
            return M.PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                                 size_matched=0.0, avg_price_matched=None)

    tid = _base_trade(db, mode="live")
    prices = {"back": 9.0, "back_size": 100.0, "lay": 10.0, "lay_size": 100.0}
    res = X.close_trade(db=db, market=NoFillMarket(), trade=db.get_trade(tid),
                        prices=prices, mode="live", now=NOW,
                        params={"commission_pct": 5.0})
    assert res["error"] == "chiusura_non_eseguita"
    leg = db.get_trade(res["closing_trade_id"])
    assert leg["status"] == "error" and leg["settled_at"]
    assert leg["meta"]["error_final"] is True
    assert leg["meta"]["plan_note"], "meta della riserva conservato"


# ===========================================================================
# M-06 / L-01 / M-26 - copertura parziale visibile, chiudibile, e liability
# ===========================================================================
def test_m06_copertura_parziale_espone_meta_hedge():
    db = FakeDB(status="stopped")
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0, "status": "open",
                           "commission": 0.05, "mode": "paper", "liability": 50.0,
                           "meta": {}})
    prices = {"back": 6.0, "back_size": 4.0, "lay": 6.2, "lay_size": 100.0}
    res = X.close_trade(db=db, market=FakeMarket(), trade=db.get_trade(tid),
                        prices=prices, now=NOW, params={"commission_pct": 5.0})
    assert res["ok"] is True and res["residual_size"] > 0.01
    hedge = db.get_trade(tid)["meta"]["hedge"]
    assert 0 < hedge["fraction"] < 1
    assert hedge["remaining_liability"] > 0 and hedge["complete"] is False
    # L-11: su un parziale il P&L NON e' bloccato
    assert res["locked_pnl"] is None and res["planned_lock"] is not None
    # il RESIDUO resta chiudibile
    res2 = X.close_trade(db=db, market=FakeMarket(), trade=db.get_trade(tid),
                         prices={"back": 6.0, "back_size": 100.0, "lay": 6.2,
                                 "lay_size": 100.0},
                         fraction=1.0, now=NOW, params={"commission_pct": 5.0})
    assert res2["ok"] is True
    hedge = db.get_trade(tid)["meta"]["hedge"]
    assert hedge["complete"] is True and hedge["remaining_liability"] == 0.0


def test_l01_meta_hedging_scritto_mentre_una_chiusura_e_in_volo():
    db = FakeDB(status="stopped")
    tid = db.insert_trade({"event_id": "1.1", "side": "lay", "size": 10.0,
                           "price": 6.0, "status": "open", "meta": {}})
    legs = [{"id": 2, "status": "pending", "size": 10.0, "price": 6.0,
             "closes_trade_id": tid}]
    X.apply_hedge_state(db, db.get_trade(tid), legs, NOW)
    assert db.get_trade(tid)["meta"]["hedging"] is True
    legs = [{"id": 2, "status": "open", "size": 10.0, "price": 6.0,
             "closes_trade_id": tid}]
    X.apply_hedge_state(db, db.get_trade(tid), legs, NOW)
    assert db.get_trade(tid)["meta"]["hedging"] is False


def test_m26_liability_residua_dopo_la_copertura():
    # copertura COMPLETA in perdita: la perdita e' BLOCCATA, non e' piu' rischio
    complete = {"liability": 118.0, "meta": {"hedged_size": 2.0, "residual_size": 0.0,
                                             "worst_case": -4.0,
                                             "hedge": {"remaining_liability": 0.0,
                                                       "complete": True}}}
    assert X.residual_liability(complete) == 0.0
    partial = {"liability": 118.0, "meta": {"hedged_size": 1.0, "residual_size": 1.0,
                                            "worst_case": -60.0,
                                            "hedge": {"remaining_liability": 60.0}}}
    assert X.residual_liability(partial) == 60.0
    nude = {"liability": 118.0, "meta": {}}
    assert X.residual_liability(nude) == 118.0
    # e gli aggregati la usano
    rows = [{"id": 1, "event_id": "e1", "status": "open", "pnl": 0.0,
             "placed_at": NOW.isoformat(), **complete}]
    assert DB.aggregate_rows(rows)["open_liability"] == 0.0


# ===========================================================================
# M-21 - esito delle richieste della UI
# ===========================================================================
def test_m21_stati_e_messaggi_delle_richieste():
    assert S._request_state({"ok": True}) == "done"
    assert S._request_state({"error": "x"}) == "error"
    assert S._request_state({"rejected": "in riconciliazione"}) == "rejected"
    assert "eseguito" in S._request_result({"ok": True})["message"]
    assert S._request_result({"rejected": "mercato sospeso"})["message"].startswith(
        "rifiutato: mercato sospeso")
    assert S._request_result({"error": "risk_block", "reason": "cap"})["message"]
    assert "rejected" in DB.REQUEST_STATES


def test_m21_cancel_di_una_riserva_pulita_funziona_ancora():
    db = FakeDB(status="stopped")
    tid = db.insert_trade({"event_id": "1.1", "status": "pending", "side": "back",
                           "meta": {}})
    db.requests.append({"id": 1, "kind": "cancel", "status": "pending",
                        "payload": {"trade_id": tid}})
    _run(db)
    assert db.requests[0]["status"] == "done"
    assert db.requests[0]["result"]["message"] == "riserva annullata"
    assert db.get_trade(tid) is None


# ===========================================================================
# M-23 - market_open legge lo status del MERCATO DELLA POSIZIONE
# ===========================================================================
def test_m23_stato_del_mercato_per_tipo():
    payload = {
        "mo_status": "OPEN",
        "cs": {"market_id": "cs1", "status": "SUSPENDED"},
        "btts": {"market_id": "b1", "status": "SUSPENDED"},
        "ht_result": {"market_id": "h1", "status": "OPEN"},
        "ht": {"market_id": "hts1", "status": "SUSPENDED"},
        "ou": [{"market_id": "ou15", "status": "OPEN"},
               {"market_id": "ou25", "status": "SUSPENDED"}],
    }
    assert XE.market_open({"market_type": "MATCH_ODDS", "market_id": "m1"}, payload) is True
    assert XE.market_open({"market_type": "CORRECT_SCORE", "market_id": "cs1"}, payload) is False
    assert XE.market_open({"market_type": "BOTH_TEAMS_TO_SCORE", "market_id": "b1"},
                          payload) is False
    assert XE.market_open({"market_type": "HALF_TIME", "market_id": "h1"}, payload) is True
    assert XE.market_open({"market_type": "HALF_TIME_SCORE", "market_id": "hts1"},
                          payload) is False
    assert XE.market_open({"market_type": "OVER_UNDER", "market_id": "ou15"},
                          payload) is True
    assert XE.market_open({"market_type": "OVER_UNDER", "market_id": "ou25"},
                          payload) is False, "la linea sbagliata non decide per l'altra"
    # status assente = IGNOTO (non si blocca e non si inventa)
    assert XE.market_open({"market_type": "OVER_UNDER", "market_id": "ou99"}, {}) is None


# ===========================================================================
# M-24 - tetto duro di freschezza del feed
# ===========================================================================
def test_m24_tetto_duro_di_freschezza():
    now_ts = 1000.0
    fresh = {"updated_at": datetime.fromtimestamp(now_ts - 5, timezone.utc).isoformat()}
    mid = {"updated_at": datetime.fromtimestamp(now_ts - 60, timezone.utc).isoformat()}
    old = {"updated_at": datetime.fromtimestamp(now_ts - 300, timezone.utc).isoformat()}
    assert XE.feed_is_fresh(fresh, now_ts) is True
    # scanner vivo: una riga di 60 s passa (nulla e' cambiato)
    assert XE.feed_is_fresh(mid, now_ts, now_ts - 1) is True
    # ma oltre il tetto duro NO, nemmeno con lo scanner vivo
    assert XE.feed_is_fresh(old, now_ts, now_ts - 1) is False
    assert XE.FEED_HARD_MAX_S == 120.0


def test_l15_cash_out_manuale_rifiutato_su_feed_stantio_o_mercato_sospeso():
    db = FakeDB(status="stopped")
    tid = _base_trade(db)
    old = NOW - timedelta(seconds=600)
    db.scan_rows = [_exit_row(60, 1, 0, updated_at=old)]
    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": tid}})
    _run(db)
    # H5: sul feed stantio si tenta il book REST; senza book (FakeMarket lo ha
    # a None) si rifiuta, dicendo che non ci sono quote utilizzabili
    assert db.requests[0]["status"] == "rejected"
    assert db.requests[0]["result"]["rejected"] == "quote non disponibili"
    # mercato sospeso
    db2 = FakeDB(status="stopped")
    tid2 = _base_trade(db2)
    row = _exit_row(60, 1, 0)
    row["payload"]["mo_status"] = "SUSPENDED"
    db2.scan_rows = [row]
    db2.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                         "payload": {"trade_id": tid2}})
    _run(db2)
    assert db2.requests[0]["status"] == "rejected"
    assert "sospeso" in db2.requests[0]["result"]["rejected"]


# ===========================================================================
# M-25 - mercato sparito al settlement
# ===========================================================================
def test_m25_mercato_sparito_logga_una_volta_poi_ogni_5_minuti():
    class MissingMarket(FakeMarket):
        def read_market(self, cs):
            return None

    db = FakeDB(status="stopped")
    tid = _base_trade(db)
    mk = MissingMarket()
    # M11: una singola lettura KO (timeout di rete) NON e' un mercato sparito.
    # Le letture sono distanziate >= 10 s per passare il gate REST (H-19).
    for i, s in enumerate((0, 11, 22)):
        at = NOW + timedelta(seconds=s)
        S.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=at,
                      rows_by_event={})
        if i < S.MARKET_MISSING_MIN_FAILS - 1:
            assert _kinds(db, "market_missing") == [], "un KO isolato non allarma"
    assert len(_kinds(db, "market_missing")) == 1, "ne' silenzio ne' flood"
    assert _kinds(db, "market_missing")[0]["fails"] == S.MARKET_MISSING_MIN_FAILS
    assert db.get_trade(tid)["meta"]["market_missing_since"]
    S.settle_open(params={"commission_pct": 5.0}, market=mk, db=db,
                  now=NOW + timedelta(seconds=400), rows_by_event={})
    assert len(_kinds(db, "market_missing")) == 2
    # letture riuscite: il contatore si azzera
    mk2 = FakeMarket()
    mk2.snapshot = None
    S.settle_open(params={"commission_pct": 5.0}, market=mk2, db=db,
                  now=NOW + timedelta(seconds=500), rows_by_event={})


# ===========================================================================
# M-27 - decisione a modello al NETTO della commissione
# ===========================================================================
def test_m27_netto_di_commissione():
    assert XE.net_of_commission(1.0, 0.05) == 0.95
    assert XE.net_of_commission(-4.0, 0.05) == -4.0, "le perdite non pagano nulla"
    assert XE.net_of_commission(None, 0.05) is None
    assert XE.net_of_commission(2.0, None) == 2.0


# ===========================================================================
# M-28 - exit_hold non riscritto a ogni ciclo
# ===========================================================================
def test_m28_firma_stabile_del_motivo_di_hold():
    a = "margine ampio: P(perdita)=0.4%, tengo fino al settlement"
    b = "margine ampio: P(perdita)=0.9%, tengo fino al settlement"
    c = "rischio alto: P(perdita)=15.0% >= 10%, esco"
    assert XE.hold_code(a) == XE.hold_code(b)
    assert XE.hold_code(a) != XE.hold_code(c)


# ===========================================================================
# M-29 - aggregati da UNA RPC, con ripiego
# ===========================================================================
def test_m29_aggregates_usa_la_rpc_e_ripiega_se_manca(monkeypatch):
    calls = {"rpc": 0, "table": 0}

    class FakeRes:
        def __init__(self, data):
            self.data = data

    class FakeQuery:
        def select(self, *a, **k):
            return self

        def order(self, *a, **k):
            return self

        def range(self, *a, **k):
            return self

        def execute(self):
            calls["table"] += 1
            return FakeRes([])

    class FakeSb:
        def __init__(self, ok):
            self.ok = ok

        def rpc(self, name, args):
            calls["rpc"] += 1
            assert name == "get_safe_aggregates"
            if not self.ok:
                raise RuntimeError("function does not exist")
            return _Exec({k: 1 for k in DB._AGG_KEYS})

        def table(self, name):
            return FakeQuery()

    class _Exec:
        def __init__(self, data):
            self._data = data

        def execute(self):
            return FakeRes(self._data)

    monkeypatch.setattr(DB, "_sb", lambda: FakeSb(True))
    agg = DB.aggregates()
    assert calls["rpc"] == 1 and calls["table"] == 0
    assert set(agg) == set(DB._AGG_KEYS)
    monkeypatch.setattr(DB, "_sb", lambda: FakeSb(False))
    agg = DB.aggregates()
    assert calls["table"] == 1, "migrazione non applicata: si ripiega"
    assert agg["open_liability"] == 0


# ===========================================================================
# M-30 - "Salva" ricostruisce i modelli a caldo
# ===========================================================================
def test_m30_firma_dei_parametri_cambia_con_i_parametri():
    a = S.params_signature(S.resolve_params({"opps_stake": 5}))
    b = S.params_signature(S.resolve_params({"opps_stake": 7}))
    assert a != b
    assert a == S.params_signature(S.resolve_params({"opps_stake": 5}))


# ===========================================================================
# M-31 - size minima Betfair 2 EUR in live
# ===========================================================================
def test_m31_size_sotto_il_minimo_non_arriva_a_betfair():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    out = X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=1.5,
                  client_ref="safe-t1", trade_id=1, now=NOW, params={})
    assert out.status == "error"
    assert out.fill_note.startswith("size_sotto_minimo_betfair")
    assert mk.placed == [], "nessuna chiamata buttata"
    out = X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=2.0,
                  client_ref="safe-t1", trade_id=1, now=NOW, params={})
    assert out.status == "open" and len(mk.placed) == 1


def test_m31_il_minimo_non_vale_in_paper():
    db = FakeDB(status="stopped")
    out = X.place(db=db, market=FakeMarket(), mode="paper", event_id="1.1",
                  market_id="m1", selection_id=7, side="back", price=3.0, size=0.5,
                  best_size=100.0, client_ref="safe-t1", trade_id=1, now=NOW, params={})
    assert out.status == "open"


# ===========================================================================
# M-32 - clamp delle soglie delle opportunita'
# ===========================================================================
def test_m32_clamp_delle_soglie_opportunita():
    p = S.resolve_params({"opps_min_confidence": "alto", "opps_min_edge": None})
    assert p["opps_min_confidence"] == 0.7 and p["opps_min_edge"] == 0.03
    p = S.resolve_params({"opps_min_confidence": 5, "opps_min_edge": -9})
    assert p["opps_min_confidence"] == 1.0 and p["opps_min_edge"] == -1.0
    p = S.resolve_params({"place_max_attempts": 0})
    assert p["place_max_attempts"] == 1


# ===========================================================================
# M-33 - chiusura orfana con le SORELLE
# ===========================================================================
def test_m33_orfana_regolata_tenendo_conto_delle_sorelle():
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(999)
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0, "status": "lost",
                           "pnl": -50.0, "settled_at": "old", "commission": 0.05,
                           "mode": "paper", "meta": {}})
    # sorella GIA' regolata + orfana ancora viva
    db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                     "side": "back", "size": 5.0, "price": 5.0, "status": "won",
                     "pnl": 20.0, "settled_at": "old", "commission": 0.05,
                     "mode": "paper", "closes_trade_id": tid})
    orph = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                            "side": "back", "size": 5.0, "price": 5.0, "status": "open",
                            "commission": 0.05, "mode": "paper", "closes_trade_id": tid})
    res = S.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW,
                        rows_by_event={})
    assert res == 1
    # padre -50 + sorella +20 + orfana X = netto della coppia completa
    gross = -50.0 + 20.0 + 20.0
    assert db.get_trade(orph)["pnl"] == pytest.approx(gross - (-50.0 + 20.0), abs=0.01)


# ===========================================================================
# L-02 - commissione della gamba di chiusura sempre valorizzata
# ===========================================================================
def test_l02_commissione_della_chiusura_mai_nulla():
    db = FakeDB(status="stopped")
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0, "status": "open",
                           "mode": "paper", "commission": None, "meta": {}})
    res = X.close_trade(db=db, market=FakeMarket(), trade=db.get_trade(tid),
                        prices={"back": 6.0, "back_size": 100.0, "lay": 6.2,
                                "lay_size": 100.0},
                        now=NOW, params={"commission_pct": 5.0})
    leg = db.get_trade(res["closing_trade_id"])
    assert leg["commission"] == 0.05


# ===========================================================================
# L-12 - formato del match nel tennis
# ===========================================================================
def test_l12_best_of_dal_torneo_non_solo_dai_set_giocati():
    assert S._best_of({"competition": "ATP Roland Garros"}, (1, 0)) == 5
    assert S._best_of({"competition": "WTA Roland Garros"}, (1, 0)) == 3
    assert S._best_of({"competition": "ITF Challenger"}, (1, 0)) == 3
    assert S._best_of({}, (2, 1)) == 5, "3 set giocati: e' un bo5"


# ===========================================================================
# L-14 - TTL della cache delle lambda
# ===========================================================================
def test_l14_ttl_della_cache_lambda():
    state = {"lambdas": {"e1": {"lambdas": (1.0, 1.0), "source": "fixture_match",
                                "ts": NOW.timestamp() - 10}}}
    calls = {"n": 0}

    class Opp:
        @staticmethod
        def resolve_lambdas(payload, fixture=None):
            calls["n"] += 1
            return (1.5, 1.2, None, "pre_ko")

    db = FakeDB(status="stopped")
    out = S.resolve_event_lambdas(db=db, event_id="e1", payload={}, opp_mod=Opp,
                                  now=NOW, state=state)
    assert out["source"] == "fixture_match" and calls["n"] == 0, "dentro il TTL"
    state["lambdas"]["e1"]["ts"] = NOW.timestamp() - (S.LAMBDA_TTL_S + 10)
    out = S.resolve_event_lambdas(db=db, event_id="e1", payload={}, opp_mod=Opp,
                                  now=NOW, state=state)
    assert calls["n"] == 1, "scaduto il TTL: la catena si rifa'"


# ===========================================================================
# H-16 - il servizio scrive attivita' leggibili (catalogo dei kind)
# ===========================================================================
def test_h16_accessor_delle_attivita_esiste():
    assert callable(getattr(DB, "recent_activity", None))
    assert callable(getattr(DB, "place_attempts", None))


def test_chiavi_dell_esecuzione_condivisa_sono_dichiarate_e_clampate():
    """La Safe Strategy non deve EREDITARE in silenzio i default di Omega per il
    codice condiviso della coda (min_stake 0,50 invece del minimo reale 2 EUR)."""
    p = S.resolve_params(None)
    assert p["min_stake"] == 2.0
    assert p["paper_fill_ttl_s"] == 45 and p["live_fill_deadline_s"] == 20
    assert p["execution_mode"] == "auto" and p["omega_live_via_flumine"] is True
    p = S.resolve_params({"paper_fill_ttl_s": 0, "live_fill_deadline_s": 9999,
                          "min_stake": -3, "execution_mode": "pippo"})
    assert p["paper_fill_ttl_s"] == 5 and p["live_fill_deadline_s"] == 300
    assert p["min_stake"] == 0.0 and p["execution_mode"] == "auto"
    assert S.params_effective(p)["min_stake"] == 0.0


def test_h16_catalogo_dei_kind_di_attivita():
    """Contratto col frontend: l'elenco dei kind che il servizio scrive.
    Se se ne aggiunge uno va aggiunto qui E nella mappa etichette della UI."""
    attesi = {
        # ciclo e parametri
        "stop", "error", "params_invalid", "params_clamped",
        # piazzamento
        "place", "place_pending", "place_retry", "place_exhausted",
        "place_exception", "skip", "risk_block", "confirm_failed",
        "flumine_enqueue",
        # riconciliazione
        "reconcile_error", "reconciled_open", "reconciled_free", "reconciled_error",
        # uscite e cash out
        "exit", "exit_hold", "exit_wait", "exit_retry", "exit_failed",
        "cashout", "cashout_error", "cancel", "cancel_rejected",
        # combo
        "combo_incomplete",
        # settlement
        "settle", "settle_position", "settle_wait", "settle_error",
        "settle_orphan_closing", "market_missing",
        # feed
        "feed_blind", "feed_back",
    }
    import re as _re
    from pathlib import Path

    src = ""
    for name in ("bot_service.py", "execution.py"):
        src += Path("Betfair/safe_strategy", name).read_text(encoding="utf-8")
    scritti = set(_re.findall(r'_log\(db, "([a-z_]+)"', src))
    scritti |= set(_re.findall(r'db\.log\("([a-z_]+)"', src))
    scritti |= {"risk_block"}   # passato come parametro kind a _log_skip
    assert scritti <= attesi, f"kind non documentati: {sorted(scritti - attesi)}"


def test_h15_normalizzazione_e_idempotente_anche_con_none_e_bool():
    """Nessun loop di scritture sul control: valori identici (None, bool,
    stringhe) non sono 'correzioni'."""
    db = FakeDB(status="stopped", params={
        "risk": {"max_open_trades": None, "daily_liability_cap": 500.0},
        "exits": {"enabled": True, "red_card_fav_exit": True},
        "execution_mode": "auto", "variants": ["base", "esatto", "punta", "tennis"],
    })
    for _ in range(3):
        _run(db)
    assert _kinds(db, "params_clamped") == []
    assert _kinds(db, "params_invalid") == []
    assert S.params_corrections(db.control["params"],
                                S.resolve_params(db.control["params"])) == {}


# ===========================================================================
# REVIEW 11/09 (seconda passata) - C1, C2, H1, H2, H4, H5, H6, M1..M12, L1..L4
# ===========================================================================
def test_rev_c1_copertura_in_volo_non_azzera_la_liability():
    """Una chiusura ancora PENDING (coda flumine) non copre NULLA: il rischio
    resta pieno. Prima ``remaining_liability`` tornava 0 e i cap si liberavano
    con il 100% dell'esposizione ancora a mercato."""
    db = FakeDB(status="stopped")
    tid = db.insert_trade({"event_id": "1.1", "side": "lay", "size": 2.0,
                           "price": 60.0, "liability": 118.0, "status": "open",
                           "mode": "paper", "meta": {}})
    trade = db.get_trade(tid)
    legs = [{"id": 99, "status": "pending", "size": 2.0, "price": 60.0,
             "closes_trade_id": tid}]
    st = X.hedge_state(trade, legs)
    assert st["worst_case"] is None and st["blocked"] is True
    assert X.remaining_liability(trade, st) == 118.0
    X.apply_hedge_state(db, trade, legs, NOW)
    row = db.get_trade(tid)
    assert row["meta"]["hedge"]["remaining_liability"] == 118.0
    assert row["meta"]["hedging"] is True
    assert X.residual_liability(row) == 118.0
    assert DB.aggregate_rows([row])["open_liability"] == 118.0
    # il fill arriva: ora la copertura e' vera e il rischio scende a 0
    legs = [{"id": 99, "status": "open", "size": 2.0, "price": 60.0,
             "closes_trade_id": tid}]
    X.apply_hedge_state(db, db.get_trade(tid), legs, NOW)
    row = db.get_trade(tid)
    assert row["meta"]["hedge"]["complete"] is True
    assert row["meta"]["hedge"]["remaining_liability"] == 0.0
    assert X.residual_liability(row) == 0.0


def test_rev_m10_meta_incompleto_conta_la_liability_piena():
    """Chiavi assenti = IGNOTO = rischio PIENO. Mai 0 per default."""
    assert X.residual_liability({"liability": 50.0, "meta": {"hedged_size": 1.0}}) == 50.0
    assert X.residual_liability({"liability": 50.0,
                                 "meta": {"hedged_size": 1.0, "residual_size": 0.0,
                                          "hedge_pending_ids": [7]}}) == 50.0
    assert X.residual_liability({"liability": 50.0, "meta": {}}) == 50.0
    assert X.residual_liability({"liability": 50.0,
                                 "meta": {"hedge": {"remaining_liability": "x"}}}) == 50.0


def test_rev_c2_il_minimo_2_euro_non_blocca_le_chiusure():
    """Betfair ACCETTA gli ordini sotto minimo che RIDUCONO una posizione: un
    residuo da 1,40 EUR deve poter essere chiuso."""
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    # APERTURA sotto minimo: rifiutata (nessuna chiamata buttata)
    out = X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=1.4,
                  client_ref="safe-t1", trade_id=1, now=NOW, params={})
    assert out.status == "error" and mk.placed == []
    # CHIUSURA sotto minimo: passa
    out = X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                  selection_id=7, side="lay", price=3.0, size=1.4,
                  client_ref="safe-t2", trade_id=2, now=NOW, params={},
                  meta={"cashout": True, "closes_trade_id": 1})
    assert out.status == "open" and len(mk.placed) == 1
    out = X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1",
                  selection_id=7, side="lay", price=3.0, size=1.4,
                  client_ref="safe-t3", trade_id=3, now=NOW, params={},
                  meta={"closes_trade_id": 1})
    assert out.status == "open" and len(mk.placed) == 2


def test_rev_h1_il_cap_giornaliero_non_si_libera_coprendo():
    """``day_liability`` = capitale IMPEGNATO: una posizione coperta non
    restituisce margine al cap del giorno."""
    day = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
    t = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc).isoformat()
    coperta = {"id": 1, "event_id": "e1", "status": "open", "pnl": 0.0,
               "liability": 118.0, "placed_at": t, "bet_id": "b1",
               "meta": {"hedged_size": 2.0, "residual_size": 0.0,
                        "worst_case": -4.0,
                        "hedge": {"remaining_liability": 0.0, "complete": True}}}
    agg = DB.aggregate_rows([coperta], day_start=day)
    assert agg["open_liability"] == 0.0, "rischio vivo: nessuno"
    assert agg["day_liability"] == 118.0, "capitale impegnato: tutto"
    assert agg["day_liability_model"] == 0.0


def test_rev_h2_loss_stop_positivo_non_spegne_lo_stop():
    from Betfair.safe_strategy import risk as RK

    p = S.resolve_params({"risk": {"daily_loss_stop": 50}})
    assert p["risk"]["daily_loss_stop"] == -50.0
    assert RK.loss_stop_active(-60.0, p) is True
    assert RK.loss_stop_active(-10.0, p) is False


def test_rev_h2_chiavi_money_critical_mai_riscritte_sul_db():
    db = FakeDB(status="stopped", params={
        "risk": {"daily_loss_stop": 50, "daily_liability_cap": -5},
        "commission_pct": 99, "max_liability_per_trade": -1, "min_stake": -2,
        "variants": [],
    })
    _run(db)
    stored = db.control["params"]
    # money-critical: intatte
    assert stored["risk"]["daily_loss_stop"] == 50
    assert stored["risk"]["daily_liability_cap"] == -5
    assert stored["commission_pct"] == 99
    assert stored["max_liability_per_trade"] == -1 and stored["min_stake"] == -2
    # strutturalmente invalido e NON money-critical: normalizzato
    assert stored["variants"] == ["base", "esatto", "punta", "tennis"]
    inv = _kinds(db, "params_invalid")[0]
    assert inv["persisted"] == ["variants"]


def test_rev_h4_il_tracciamento_gira_anche_durante_il_backoff():
    """Il backoff frena l'INVIO, non il TRACCIAMENTO: i gol osservati durante
    l'attesa devono restare in meta.exit_track."""
    class NoClosingDB(FakeDB):
        def insert_trade(self, trade):
            if trade.get("closes_trade_id"):
                raise RuntimeError("db ko")
            return super().insert_trade(trade)

    db = NoClosingDB(status="running")
    tid = _base_trade(db)
    _cycle(db, _exit_row(81, 1, 0))                     # 1o tentativo: fallisce
    assert db.get_trade(tid)["meta"]["exit"]["state"] == "retrying"
    # dentro il backoff arriva un GOL: il tracciamento lo deve registrare
    at = NOW + timedelta(seconds=2)
    _cycle(db, _exit_row(82, 2, 0, updated_at=at), at=at)
    tr = db.get_trade(tid)["meta"]["exit_track"]
    assert tr["last_home"] == 2 and tr["goals_since_entry_home"] == 1
    assert tr["last_goal_ts"] is not None


def test_rev_h4_una_uscita_in_perdita_non_aspetta_il_backoff():
    """Una regola URGENTE nuova (la bancata pareggia) scavalca il backoff di un
    tentativo precedente: aspettare 5 minuti costa soldi."""
    calls = {"n": 0}

    class OnceFailingDB(FakeDB):
        def insert_trade(self, trade):
            if trade.get("closes_trade_id"):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("db ko")
            return super().insert_trade(trade)

    db = OnceFailingDB(status="running")
    tid = _base_trade(db)
    _cycle(db, _exit_row(81, 1, 0))                     # uscita a TEMPO: fallisce
    st = db.get_trade(tid)["meta"]["exit"]
    assert st["state"] == "retrying" and st["kind"] == "time" and st["next_retry_at"]
    # 1 s dopo la sfavorita PAREGGIA: uscita in perdita
    at = NOW + timedelta(seconds=1)
    _cycle(db, _exit_row(82, 1, 1, updated_at=at), at=at)
    at = NOW + timedelta(seconds=32)                    # scaduto l'assestamento
    r = _cycle(db, _exit_row(83, 1, 1, updated_at=at), at=at)
    assert r["exits"] == 1, "la perdita non aspetta il backoff dell'uscita a tempo"
    assert db.get_trade(tid)["meta"]["exit_kind"] == "loss"


def test_rev_h5_cash_out_manuale_usa_il_book_rest_se_il_feed_e_stantio():
    db = FakeDB(status="stopped")
    tid = _base_trade(db)
    mk = FakeMarket()
    mk.book = {"status": "OPEN", "runners": [
        {"selection_id": 8, "back_price": 9.0, "back_size": 200.0,
         "lay_price": 10.0, "lay_size": 200.0}]}
    old = NOW - timedelta(seconds=600)
    db.scan_rows = [_exit_row(60, 1, 0, updated_at=old)]
    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": tid}})
    _run(db, market=mk)
    res = db.requests[0]["result"]
    assert db.requests[0]["status"] == "done", res
    assert res["source"] == "rest"
    assert [t for t in db.trades if t.get("closes_trade_id") == tid]


def test_rev_h6_combo_in_coda_svolta_appena_il_fill_e_confermato():
    """H6: la gamba in coda (pending) di una combo rotta viene MARCATA e chiusa
    dal ciclo successivo, appena il poll conferma il fill."""
    db = FakeDB(status="stopped")
    row = _combo_feed_row()
    tid = _base_trade(db, strategy="model", market_id="ou25",
                      market_type="OVER_UNDER", selection_id=101,
                      selection_name="Under 2.5 Goals", side="back", price=2.0,
                      size=5.0, liability=5.0, signal_key="combo:c1:0",
                      meta={"combo_id": "c1", "combo_incomplete": True})
    n = S.unwind_incomplete_combos(db=db, market=FakeMarket(),
                                   rows_by_event={"1.1": row},
                                   params=S.resolve_params({}), now=NOW)
    assert n == 1
    legs = [t for t in db.trades if t.get("closes_trade_id") == tid]
    assert legs and legs[0]["meta"]["exit_kind"] == "forced"
    # idempotente: al ciclo dopo non chiude due volte
    assert S.unwind_incomplete_combos(db=db, market=FakeMarket(),
                                      rows_by_event={"1.1": row},
                                      params=S.resolve_params({}), now=NOW) == 0


def test_rev_h6_marker_scritto_su_tutte_le_gambe_vive():
    """Combo incompleta in LIVE con una gamba in CODA: il marker c'e' anche su
    quella (il fill arrivera' dopo)."""
    class QueueMarket(FakeMarket):
        def place_order_live(self, **kw):
            if kw["market_id"] == "m1":
                return M.PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                                     size_matched=0.0, avg_price_matched=None)
            return super().place_order_live(**kw)

    db = FakeDB(status="running")
    db.follow = "STREAMING"          # gate flumine APERTO: la gamba va in coda
    row = _combo_feed_row()
    S._auto_trade_combos(db=db, market=QueueMarket(), payload=row["payload"],
                         event_id="1.1", combos=[_combo()],
                         params=S.resolve_params({}), mode="live", now=NOW,
                         rows_by_event={"1.1": row})
    assert _kinds(db, "combo_incomplete"), "combo incompleta non segnalata"
    marcate = [t for t in db.trades
               if (t.get("meta") or {}).get("combo_incomplete")]
    assert marcate, "nessuna gamba marcata: il fill in coda resterebbe nudo"


def test_rev_m1_una_sola_lettura_delle_posizioni_per_ciclo():
    class CountingDB(FakeDB):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.open_reads = 0

        def open_trades(self):
            self.open_reads += 1
            return super().open_trades()

    db = CountingDB(status="running")
    _base_trade(db, meta={"combo_id": "c1"})
    _base_trade(db, strategy="model", market_id="ou25", market_type="OVER_UNDER",
                selection_id=101, side="back", price=2.0, size=5.0,
                signal_key="combo:c1:1", meta={"combo_id": "c1"})
    db.scan_rows = [_exit_row(60, 1, 0)]
    S.run_once(db=db, market=FakeMarket(), now=NOW)
    # settle_open + build_risk_ctx: uscite, combo e unwind riusano la lista
    assert db.open_reads <= 2, f"troppe letture di open_trades: {db.open_reads}"


def test_rev_m2_una_posizione_pre_ko_non_e_cieca():
    db = FakeDB(status="stopped")
    # pre-KO: nessun minuto d'ingresso, nessun tracciamento in-play
    db.insert_trade({"event_id": "9.9", "status": "open", "side": "back",
                     "size": 5.0, "price": 2.0, "liability": 5.0, "sport": "calcio",
                     "origin": "manual", "strategy": "manual", "meta": {}})
    res = _run(db)
    assert res["blind"] == 0 and _kinds(db, "feed_blind") == []
    # in-play (minuto d'ingresso): la cecita' e' un allarme vero
    db2 = FakeDB(status="stopped")
    _base_trade(db2)
    assert _run(db2)["blind"] == 1


def test_rev_m3_green_up_in_coda_resta_greenup():
    """Con la coda flumine il fill arriva dopo: ``residual_size`` e' ancora
    pieno ma la chiusura e' INTEGRALE -> 'greenup', non 'profit'."""
    assert XE.ui_exit_kind("time", locked=1.0, integral=True) == "greenup"
    db = FakeDB(status="running")
    db.follow = "STREAMING"          # gate flumine aperto: fill differito
    tid = _base_trade(db, price=3.0, size=2.0, liability=4.0, selection_id=8)
    r = _cycle(db, _exit_row(81, 1, 0, back=1.5, lay=1.52))
    assert r["exits"] == 1
    meta = db.get_trade(tid)["meta"]
    assert meta["exit_requested"]["pending_fill"] is True
    assert meta["exit_kind"] == "greenup", "in live un green-up non e' 'profit'"


def test_rev_m9_due_orfane_sulla_stessa_apertura():
    """Ogni orfana vede le SORELLE aggiornate: la somma delle gambe resta il
    netto esatto della posizione."""
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(999)
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0, "status": "lost",
                           "pnl": -50.0, "settled_at": "old", "commission": 0.05,
                           "mode": "paper", "meta": {}})
    a = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                         "side": "back", "size": 5.0, "price": 5.0, "status": "open",
                         "commission": 0.05, "mode": "paper", "closes_trade_id": tid})
    b = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                         "side": "back", "size": 5.0, "price": 5.0, "status": "open",
                         "commission": 0.05, "mode": "paper", "closes_trade_id": tid})
    assert S.settle_open(params={"commission_pct": 5.0}, market=mk, db=db, now=NOW,
                         rows_by_event={}) == 2
    gross = -50.0 + 20.0 + 20.0          # lay perde, i due back vincono
    total = round(gross - (gross * 0.05 if gross > 0 else 0.0), 2)
    somma = round(db.get_trade(tid)["pnl"] + db.get_trade(a)["pnl"]
                  + db.get_trade(b)["pnl"], 2)
    assert somma == pytest.approx(total, abs=0.01)


def test_rev_m12_settle_non_perde_il_meta_scritto_nel_frattempo():
    """Il meta della posizione (hedge, exit_kind) sopravvive al settlement."""
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = _closed(999)
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0, "status": "hedged",
                           "commission": 0.05, "mode": "paper",
                           "meta": {"exit_kind": "greenup", "hedge": {"complete": True}}})
    db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                     "side": "back", "size": 12.0, "price": 5.0, "status": "open",
                     "commission": 0.05, "mode": "paper", "closes_trade_id": tid})
    _run(db, market=mk)
    meta = db.get_trade(tid)["meta"]
    assert meta["exit_kind"] == "greenup" and meta["hedge"]["complete"] is True
    assert meta["position_result"] in ("won", "lost", "flat")


def test_rev_l1_gate_rest_cablato_nei_chiamanti():
    import inspect

    sig = inspect.signature(S.prices_for)
    assert "rest_now_ts" in sig.parameters and "allow_rest" in sig.parameters
    mk = FakeMarket()
    mk.book = {"status": "OPEN", "runners": [
        {"selection_id": 7, "back_price": 3.0, "back_size": 10.0,
         "lay_price": 3.1, "lay_size": 10.0}]}
    # senza rest_now_ts il gate NON si applica (azione manuale dell'utente)
    p = S.prices_for(market=mk, rows_by_event={}, event_id="1.1", market_id="mX",
                     market_type="MATCH_ODDS", selection_id=7)
    assert p and p["back"] == 3.0
    # allow_rest=False: solo feed
    assert S.prices_for(market=mk, rows_by_event={}, event_id="1.1", market_id="mX",
                        market_type="MATCH_ODDS", selection_id=7,
                        allow_rest=False) is None
    # col gate e cadenza non rispettata: None
    S._REST_STATE.update({"last": {"mY": 1000.0}, "cycle_ts": 1000.0, "used": 0})
    assert S.prices_for(market=mk, rows_by_event={}, event_id="1.1", market_id="mY",
                        market_type="MATCH_ODDS", selection_id=7,
                        rest_now_ts=1001.0) is None


def test_rev_l3_rpc_con_risposta_inattesa_non_ritenta_ogni_ciclo(monkeypatch):
    calls = {"rpc": 0}

    class FakeRes:
        def __init__(self, data):
            self.data = data

    class FakeQuery:
        def select(self, *a, **k):
            return self

        def order(self, *a, **k):
            return self

        def range(self, *a, **k):
            return self

        def execute(self):
            return FakeRes([])

    class _Exec:
        def execute(self):
            return FakeRes("non un dict")

    class FakeSb:
        def rpc(self, name, args):
            calls["rpc"] += 1
            return _Exec()

        def table(self, name):
            return FakeQuery()

    monkeypatch.setattr(DB, "_sb", lambda: FakeSb())
    DB._AGG_RPC["ko_ts"] = 0.0
    base = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    DB.aggregates(now=base)
    DB.aggregates(now=base + timedelta(seconds=2))
    DB.aggregates(now=base + timedelta(seconds=4))
    assert calls["rpc"] == 1, "risposta inattesa: non si ritenta a ogni ciclo"
    DB.aggregates(now=base + timedelta(seconds=400))
    assert calls["rpc"] == 2
    DB._AGG_RPC["ko_ts"] = 0.0


def test_rev_l4_vocabolario_position_result():
    assert X.position_result(1.0) == "won"
    assert X.position_result(-1.0) == "lost"
    assert X.position_result(0.0) == "flat"
    db = FakeDB(status="stopped")
    mk = FakeMarket()
    mk.snapshot = M.MarketSnapshot(status="CLOSED", inplay=False, closed=True,
                                   winner_selection_id=None, runners=[], voided=True)
    tid = db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                           "side": "lay", "size": 10.0, "price": 6.0, "status": "open",
                           "commission": 0.05, "mode": "paper", "meta": {}})
    _run(db, market=mk)
    assert db.get_trade(tid)["meta"]["position_result"] == "void"
