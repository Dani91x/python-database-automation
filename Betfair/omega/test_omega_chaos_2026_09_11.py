"""CHAOS TEST Omega (11/09/2026): le fasi che toccano gli ORDINI devono sopravvivere a
crash, DB irraggiungibile, rete che cade DOPO l'invio, activity log KO — con due
invarianti che non si negoziano, in ogni scenario e a ogni ripresa:

  1. MAI un secondo ordine reale per la stessa gamba (nessun doppio);
  2. OGNI ordine reale inviato finisce tracciato nel DB (riga open con bet_id o
     pending in riconciliazione), mai una posizione viva invisibile.

Modalità LIVE con fake (nessuna rete). Ogni scenario: guasto → ripresa → 3 cicli.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as OM
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import NOW, FakeDB, FakeMarket, _control, _cs, _event, _open_snapshot


class FlakyDB(FakeDB):
    """FakeDB che fallisce le chiamate indicate in ``fail`` (nome → n. di fallimenti)."""

    def __init__(self, control, fail=None):
        super().__init__(control)
        self.fail = dict(fail or {})

    def _maybe_fail(self, name):
        n = self.fail.get(name, 0)
        if n > 0:
            self.fail[name] = n - 1
            raise RuntimeError(f"DB irraggiungibile ({name})")

    def insert_trade(self, trade):
        self._maybe_fail("insert_trade")
        return super().insert_trade(trade)

    def update_trade(self, trade_id, **fields):
        if fields.get("status") == "open":
            self._maybe_fail("confirm")
        return super().update_trade(trade_id, **fields)

    def log(self, kind, payload=None):
        # come omega_db.log reale: l'activity log KO NON solleva mai (riga persa, bot vivo)
        try:
            self._maybe_fail("log")
        except RuntimeError:
            self.lost_logs = getattr(self, "lost_logs", 0) + 1
            return None
        return super().log(kind, payload)

    def list_trades(self, status=None):
        self._maybe_fail("list_trades")
        return super().list_trades(status)


class LiveMarket(FakeMarket):
    """Betfair finto: ogni place accettato diventa un ordine REALE visibile in
    listCurrentOrders (come sull'exchange). ``raise_after_send`` = la rete cade
    DOPO che l'ordine è stato accettato."""

    def __init__(self, *a, raise_after_send=0, **kw):
        super().__init__(*a, **kw)
        self.raise_after_send = raise_after_send
        self.current_orders = []

    def _accept(self, kw, side):
        bet_id = f"b{len(self.placed) + 1}"
        self.placed.append(kw)
        self.current_orders.append({
            "customer_order_ref": kw.get("customer_ref"), "market_id": kw["market_id"],
            "selection_id": kw["selection_id"], "side": side, "size_matched": kw["size"],
            "size_remaining": 0.0, "avg_price_matched": kw["price"], "bet_id": bet_id,
        })
        if self.raise_after_send > 0:
            self.raise_after_send -= 1
            raise RuntimeError("read timeout dopo placeOrders")
        return OM.PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id=bet_id,
                              size_matched=kw["size"], avg_price_matched=kw["price"])

    def place_lay_live(self, **kw):
        return self._accept(kw, "LAY")

    def place_order_live(self, **kw):
        return self._accept(kw, "LAY" if kw.get("side", "lay") == "lay" else "BACK")


def _cycles(market, db, n=3, start=NOW, step=140):
    """n cicli distanziati oltre il grace della riconciliazione (120 s)."""
    for i in range(n):
        S.run_once(market=market, db=db, now=start + timedelta(seconds=step * i))


def _invariants(market, db):
    real = market.placed
    assert len(real) <= 1, f"DOPPIO ORDINE: {real}"
    rows = [t for t in db.trades if t.get("status") != "error"]
    if real:
        # ogni ordine reale è tracciato: open con bet_id, oppure pending in riconciliazione
        tracked = [t for t in rows if t.get("status") == "open" and t.get("bet_id")]
        pending = [t for t in rows if t.get("status") == "pending"]
        assert tracked or pending, f"ORDINE REALE NON TRACCIATO: trades={db.trades}"
    open_rows = [t for t in db.trades if t.get("status") == "open"]
    assert len(open_rows) <= 1


@pytest.mark.parametrize("scenario", [
    "db_giu_prima_della_riserva",
    "rete_cade_dopo_invio",
    "db_giu_alla_conferma",
    "activity_log_giu",
    "db_giu_alla_lettura_pending",
])
def test_chaos_ingresso_live(scenario, monkeypatch):
    monkeypatch.setattr(S.time, "sleep", lambda s: None)     # backoff della conferma: istantaneo
    fail = {"db_giu_prima_della_riserva": {"insert_trade": 1},
            "db_giu_alla_conferma": {"confirm": 3},
            "activity_log_giu": {"log": 6},
            "db_giu_alla_lettura_pending": {"list_trades": 2}}.get(scenario, {})
    db = FlakyDB(_control(mode="live"), fail=fail)
    market = LiveMarket([_event()], _cs(), _open_snapshot(),
                        raise_after_send=1 if scenario == "rete_cade_dopo_invio" else 0)
    for i in range(4):
        try:
            S.run_once(market=market, db=db, now=NOW + timedelta(seconds=140 * i))
        except Exception:  # noqa: BLE001 — il main loop del servizio cattura e riparte
            pass
        _invariants(market, db)
    # a regime: UN ordine reale, UNA riga open col suo bet_id e il ref per gamba
    assert len(market.placed) == 1
    open_rows = [t for t in db.trades if t["status"] == "open"]
    assert len(open_rows) == 1 and open_rows[0]["bet_id"] == "b1"
    assert market.placed[0]["customer_ref"] == f"omega-t{open_rows[0]['id']}"
    assert not [t for t in db.trades if t["status"] == "pending"]
    if scenario == "activity_log_giu":
        assert getattr(db, "lost_logs", 0) > 0          # righe di log perse, ordine intatto


def test_chaos_crash_fra_riserva_e_ordine_non_perde_la_gamba(monkeypatch):
    """Processo morto DOPO la riserva e PRIMA dell'ordine: la riga pending senza
    ordine su Betfair viene liberata dopo il grace e la gamba si ripiazza UNA volta."""
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    db = FlakyDB(_control(mode="live"))
    market = LiveMarket([_event()], _cs(), _open_snapshot())
    real_place = S._place_one

    def crash(**kw):
        # riserva scritta, poi il processo muore
        trade_id = db.insert_trade({"event_id": kw["ev"].event_id, "market_id": kw["cs"].market_id,
                                    "selection_id": kw["sel"].selection_id, "side": "lay", "mode": "live",
                                    "origin": "auto", "price": kw["price"], "size": kw["size"],
                                    "status": "pending", "placed_at": NOW.isoformat(), "meta": {}})
        raise RuntimeError(f"crash dopo riserva {trade_id}")
    monkeypatch.setattr(S, "_place_one", crash)
    try:
        S.run_once(market=market, db=db, now=NOW)
    except Exception:  # noqa: BLE001
        pass
    assert market.placed == [] and db.trades[0]["status"] == "pending"
    monkeypatch.setattr(S, "_place_one", real_place)
    # riavvio: dentro il grace non si tocca nulla, dopo il grace la riserva orfana si libera
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=30))
    assert market.placed == [] and db.trades[0]["status"] == "pending"
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=150))
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=300))
    assert len(market.placed) == 1
    open_rows = [t for t in db.trades if t["status"] == "open"]
    assert len(open_rows) == 1 and open_rows[0]["bet_id"] == "b1"


def test_chaos_betfair_irraggiungibile_alla_riconciliazione_non_decide():
    """Ordine a esito ignoto + Betfair giù: la riga resta pending (mai 'free' o
    'error' al buio, mai un secondo ordine) finché Betfair non risponde."""
    db = FlakyDB(_control(mode="live"))
    market = LiveMarket([_event()], _cs(), _open_snapshot(), raise_after_send=1)
    S.run_once(market=market, db=db, now=NOW)
    assert db.trades[0]["status"] == "pending"
    market.orders_raise = True
    for i in range(1, 4):
        S.run_once(market=market, db=db, now=NOW + timedelta(seconds=200 * i))
        assert db.trades[0]["status"] == "pending" and len(market.placed) == 1
    market.orders_raise = False
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=1000))
    assert db.trades[0]["status"] == "open" and db.trades[0]["bet_id"] == "b1" and len(market.placed) == 1


def test_chaos_doppia_istanza_del_servizio_bloccata():
    """Due servizi insieme: il lock single-instance nega il secondo; e comunque
    l'unique del DB rifiuta una seconda gamba automatica sulla stessa partita."""
    first = S._acquire_single_instance_lock()
    if first is None:
        # un servizio Omega REALE sta girando su questa macchina: il lock è suo
        assert S._acquire_single_instance_lock() is None
    else:
        try:
            assert S._acquire_single_instance_lock() is None
        finally:
            first.close()
    db = FakeDB(_control(mode="live"))
    market = LiveMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    with pytest.raises(Exception):
        db.insert_trade({"event_id": "1.100", "origin": "auto", "phase": None, "status": "pending"})
    assert len(market.placed) == 1
