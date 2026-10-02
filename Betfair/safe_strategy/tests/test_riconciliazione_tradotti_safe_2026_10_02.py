"""02/10/2026 - RICONCILIAZIONE DEI TRADOTTI, lato SAFE (difetti D2 e D3).

D2: oltre la scadenza live del canale (20 s) Safe rilegge Betfair per bet_id
(``_reconcile_by_bet_id``) e confermava sulla riga di chiusura (banca Over 0,43 @18) i
numeri dell'ordine VERO che il runner aveva mandato (punta Under 7,31 @1,06): stato,
esposizione e P&L della riga sbagliati, e le decisioni dopo (residui, ritenti) partivano
da numeri falsi.

D3: sulla CODA e sul REST l'equivalente non c'era: una chiusura 0,43 su Over/Under era un
rifiuto certo deciso in casa, mentre sul canale passava (equivalente sull'altra
selezione). Ora le tre vie hanno lo STESSO verdetto (``live_order_build.verdetto_minimi``
con l'altra selezione letta dal book): il worker della coda traduce la riga che lo chiede
(``params.equivalente_ammesso``), il REST legge il book (``listMarketBook``) e piazza
l'equivalente; ogni lettura dopo (specchio, stato per bet_id, ordini correnti) torna nei
termini chiesti.

Finti: DB di Safe storico (``test_bot_service.FakeDB`` + runner paper finto), rete
Betfair a livello di ``OM.call``/``OM.call_mutating`` (funzioni vere di
``omega_market``), worker VERO (``live_order_worker._dispatch``) su un mercato flumine
finto a due/tre esiti, specchio dall'encoder di produzione. ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from Betfair.omega import omega_market as OM
from Betfair.omega import omega_service as OS
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as SPO
from Betfair.safe_strategy.tests.test_bot_service import FakeDB
from Betfair.stream import live_order_build as LB
from Betfair.stream import live_order_worker as LOW
from Betfair.stream.tests.test_cashout_pro_2026_09_10 import _STRAT, _Market, _Sb, _fl, _runner
from Betfair.stream.tests.tradotti_comuni import (
    MID,
    NOW,
    OVER,
    UNDER,
    book_grezzo,
    corrente_grezzo,
    evento_tradotto,
    monta_rete,
    riga_vera,
    tradotto_di,
)

BET = "330000000555"


def _db(mode: str = "live") -> FakeDB:
    db = FakeDB(status="stopped", mode=mode)
    db.heartbeat = {"ts": NOW.isoformat(), "mode": "LIVE" if mode == "live" else "PAPER"}
    return db


def _apertura(db: FakeDB, *, mode: str = "live", side: str = "back", price: float = 7.74,
              size: float = 1.0) -> dict:
    tid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": side, "mode": mode, "origin": "manual", "status": "open",
                           "price": price, "size": size,
                           "liability": X.liability_of(side, size, price), "pnl": 0.0,
                           "commission": 0.05, "bet_id": "APERTURA1", "meta": {}})
    return db.get_trade(tid)


def _chiusura_canale(db: FakeDB, parent: dict, *, bet_id: Any = None) -> dict:
    """La gamba di chiusura (banca Over 0,43 @18) come la lascia ``_place_via_canale``."""
    tid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": "lay", "mode": "live", "origin": "manual",
                           "status": "pending", "price": 18.0, "size": 0.43,
                           "liability": X.liability_of("lay", 0.43, 18.0), "pnl": 0.0,
                           "commission": 0.05, "closes_trade_id": parent["id"],
                           "bet_id": bet_id, "placed_at": NOW.isoformat(),
                           "meta": {"cashout": True, "closes_trade_id": parent["id"],
                                    "canale_ref": "safe-t%d" % (parent["id"] + 1),
                                    "canale_inviato_at": NOW.isoformat(),
                                    "reason": "place_exception_reconciling",
                                    "err": "canale_in_corso"}})
    return db.get_trade(tid)


def _under_abbinata() -> dict:
    return corrente_grezzo(bet_id=BET, selection_id=UNDER, side="back", price=1.06,
                           size=7.31, matched=7.31, remaining=0.0)


class _PortaStub:
    """La porta di Safe col solo ``esiti(ref)``: la memoria degli eventi del canale."""

    def __init__(self, eventi: dict) -> None:
        self.eventi = eventi

    def esiti(self, ref: str) -> Any:
        return self.eventi.get(ref)


# ===========================================================================
# D2 - il ripiego per bet_id oltre i 20 s confermava i numeri del VERO
# ===========================================================================
def test_d2_ripiego_per_bet_id_la_riga_resta_nei_termini_chiesti(monkeypatch):
    rete = monta_rete(monkeypatch)
    rete.correnti = [_under_abbinata()]
    db = _db()
    parent = _apertura(db)
    tr = _chiusura_canale(db, parent, bet_id=BET)
    S.reconcile_pending(market=S._MercatoSafe(OM), db=db, now=NOW + timedelta(seconds=30))
    r = db.get_trade(tr["id"])
    assert r["status"] == "open", r["meta"]
    assert (r["selection_id"], r["side"], r["size"], r["price"]) == (OVER, "lay", 0.43, 18.0)
    assert r["liability"] == round(0.43 * 17.0, 2)
    assert r["bet_id"] == BET
    # la riga dice anche cosa e' stato mandato davvero
    assert r["meta"][X.CHIAVE_TRADOTTO]["mandato"]["selection_id"] == UNDER
    # l'apertura e' coperta per intero (0,43 x 18 = 7,74 = 1,00 x 7,74)
    p = db.get_trade(parent["id"])
    assert p["status"] == "hedged", p.get("meta")


def test_d2_evento_accettato_salva_la_dichiarazione_poi_ripiego(monkeypatch):
    """L'evento intermedio del canale (nei termini chiesti, col bet_id VERO e la
    dichiarazione ``tradotto``) resta sulla riga; il ripiego per bet_id la usa anche se lo
    stato non dice selezione e lato."""
    db = _db()
    parent = _apertura(db)
    tr = _chiusura_canale(db, parent)
    t = tradotto_di("lay", 18.0, 0.43)
    ev = evento_tradotto(t, ref=tr["meta"]["canale_ref"], seq=2, fase="accettato_betfair",
                         matched=0.0, remaining=7.31, status="EXECUTABLE", bet_id=BET)
    monkeypatch.setattr(SPO, "porta_esistente",
                        lambda *a, **k: _PortaStub({tr["meta"]["canale_ref"]: ev}))

    class _Mercato:
        def list_current_orders(self) -> list:
            return []

        def list_cleared_orders(self) -> list:
            return []

        def order_state_by_bet_id(self, bet_id: str) -> dict:
            assert bet_id == BET
            return {"found": True, "size_matched": 7.31, "avg_price_matched": 1.06,
                    "size_remaining": 0.0, "matched_date": None, "placed_date": None}

    S.reconcile_pending(market=_Mercato(), db=db, now=NOW + timedelta(seconds=30))
    r = db.get_trade(tr["id"])
    assert r["status"] == "open" and (r["size"], r["price"]) == (0.43, 18.0)
    assert r["meta"][X.CHIAVE_TRADOTTO]["mandato"]["size"] == 7.31


def test_d2_non_tradotto_invariato(monkeypatch):
    """Una chiusura NON tradotta si conferma coi numeri di Betfair come prima."""
    rete = monta_rete(monkeypatch)
    rete.correnti = [corrente_grezzo(bet_id=BET, selection_id=OVER, side="lay", price=2.5,
                                     size=6.0, matched=6.0, remaining=0.0, avg=2.48)]
    db = _db()
    parent = _apertura(db, price=3.0, size=5.0)
    tr = _chiusura_canale(db, parent, bet_id=BET)
    db.update_trade(tr["id"], size=6.0, price=2.5)
    S.reconcile_pending(market=S._MercatoSafe(OM), db=db, now=NOW + timedelta(seconds=30))
    r = db.get_trade(tr["id"])
    assert r["status"] == "open" and (r["size"], r["price"]) == (6.0, 2.48)
    assert X.CHIAVE_TRADOTTO not in r["meta"]


# ===========================================================================
# IL CASO COMPLETO (Safe): canale -> tradotto -> esito oltre 20 s -> REST -> P&L
# ===========================================================================
def test_d2_caso_completo_pnl_della_riga_e_nessuna_seconda_chiusura(monkeypatch):
    rete = monta_rete(monkeypatch)
    db = _db()
    parent = _apertura(db)                     # punta Over 1,00 @7,74
    tr = _chiusura_canale(db, parent)          # banca Over 0,43 @18 sul canale
    t = tradotto_di("lay", 18.0, 0.43)
    ev = evento_tradotto(t, ref=tr["meta"]["canale_ref"], seq=2, fase="accettato_betfair",
                         matched=0.0, remaining=7.31, status="EXECUTABLE", bet_id=BET)
    eventi = {tr["meta"]["canale_ref"]: ev}
    monkeypatch.setattr(SPO, "porta_esistente", lambda *a, **k: _PortaStub(eventi))
    mercato = S._MercatoSafe(OM)
    # dentro la scadenza: solo l'evento intermedio (bet_id vero sulla riga)
    S.reconcile_pending(market=mercato, db=db, now=NOW + timedelta(seconds=5))
    assert db.get_trade(tr["id"])["bet_id"] == BET
    assert db.get_trade(tr["id"])["status"] == "pending"
    # la punta Under si abbina su Betfair, il canale tace: oltre i 20 s si legge Betfair
    rete.correnti = [_under_abbinata()]
    S.reconcile_pending(market=mercato, db=db, now=NOW + timedelta(seconds=30))
    c = db.get_trade(tr["id"])
    assert c["status"] == "open"
    assert (c["side"], c["size"], c["price"]) == ("lay", 0.43, 18.0)
    p = db.get_trade(parent["id"])
    assert p["status"] == "hedged"
    # nessuna seconda chiusura: la posizione risulta chiusa
    n_righe = len(db.trades)
    out = X.close_trade(db=db, market=mercato, trade=dict(p),
                        prices={"back": 17.5, "lay": 18.0, "back_size": 500.0,
                                "lay_size": 500.0},
                        now=NOW + timedelta(seconds=40))
    assert out.get("ok") is not True, out
    assert len(db.trades) == n_righe and rete.piazzati == []
    # P&L al regolamento (vince Under): calcolato dalla riga nei termini chiesti
    # apertura punta Over 1,00 @7,74 persa = -1,00; banca Over 0,43 @18 vinta = +0,43
    snap = SimpleNamespace(voided=False, winner_selection_id=UNDER, status="CLOSED")
    assert X.settle_position(db=db, trade=db.get_trade(parent["id"]),
                             closings=[db.get_trade(tr["id"])], snap=snap,
                             commission=0.05, now=NOW + timedelta(hours=2)) is True
    assert db.get_trade(tr["id"])["pnl"] == 0.43
    assert db.get_trade(parent["id"])["pnl"] == -1.0


def test_d2_pnl_dal_regolato_di_betfair_e_il_vero_al_centesimo(monkeypatch):
    """Con il regolato di Betfair ogni gamba prende il ``profit`` VERO della sua scommessa
    (per bet_id): la chiusura tradotta vale la vincita della punta Under (7,31 x 0,06 =
    0,4386 -> 0,44), non quella della banca chiesta (0,43). Il riportato ai termini
    chiesti e' prudente di un centesimo (``riporta_abbinato_all_originale``)."""
    db = _db()
    parent = _apertura(db)
    tr = _chiusura_canale(db, parent, bet_id=BET)
    db.update_trade(tr["id"], status="open", size=0.43, price=18.0)
    db.update_trade(parent["id"], status="hedged")
    regolati = [
        {"bet_id": "APERTURA1", "market_id": MID, "selection_id": OVER, "side": "back",
         "size_settled": 1.0, "profit": -1.0, "customer_order_ref": "safe-t1"},
        {"bet_id": BET, "market_id": MID, "selection_id": UNDER, "side": "back",
         "size_settled": 7.31, "profit": 0.44, "customer_order_ref": "4f1a2b-1"},
    ]
    snap = SimpleNamespace(voided=False, winner_selection_id=UNDER, status="CLOSED")
    assert X.settle_position(db=db, trade=db.get_trade(parent["id"]),
                             closings=[db.get_trade(tr["id"])], snap=snap, commission=0.05,
                             now=NOW + timedelta(hours=2), cleared_orders=regolati,
                             cleared_markets=[{"market_id": MID, "commission": 0.0}]) is True
    assert db.get_trade(tr["id"])["pnl"] == 0.44
    assert db.get_trade(parent["id"])["pnl"] == -1.0


# ===========================================================================
# D3 - CODA: la chiusura 0,43 non e' piu' un rifiuto in casa, va al runner
# ===========================================================================
def _place_chiusura_043(db: FakeDB, mercato: Any, mode: str, closing_id: int) -> Any:
    return X.place(db=db, market=mercato, mode=mode, event_id="E1", market_id=MID,
                   selection_id=OVER, side="lay", price=18.0, size=0.43,
                   client_ref="safe-t%d" % closing_id, trade_id=closing_id,
                   meta={"cashout": True, "closes_trade_id": 1}, now=NOW, params={})


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_d3_coda_chiusura_043_va_al_runner_con_l_equivalente_ammesso(mode):
    db = _db(mode)
    parent = _apertura(db, mode=mode)
    cid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": "lay", "mode": mode, "origin": "manual",
                           "status": "pending", "price": 18.0, "size": 0.43,
                           "closes_trade_id": parent["id"],
                           "meta": {"phase": "reserved", "cashout": True,
                                    "closes_trade_id": parent["id"]}})
    out = _place_chiusura_043(db, None, mode, cid)
    assert out.status == "pending", out.fill_note
    payload = db.queue[-1]
    assert payload["action"] == "place_submin" and payload["mode"] == mode
    assert payload["params"][LOW.PARAM_EQUIVALENTE] is True
    assert (payload["selection_id"], payload["side"], payload["size"]) == (OVER, "lay", 0.43)


def test_d3_coda_sotto_050_senza_equivalente_possibile_resta_rifiuto_in_casa():
    """Una banca 0,30 @1,50: l'equivalente (punta 0,15) e' anch'esso sotto il minimo:
    nessuna via legittima, rifiuto certo deciso in casa come prima (nessuna riga in coda)."""
    db = _db("paper")
    out = X.place(db=db, market=None, mode="paper", event_id="E1", market_id=MID,
                  selection_id=OVER, side="lay", price=1.5, size=0.30, client_ref="safe-t9",
                  trade_id=9, meta={"cashout": True, "closes_trade_id": 1}, now=NOW,
                  params={})
    assert out.status == "error" and out.error_code == "SOTTO_MINIMO_NON_PIAZZABILE"
    assert db.queue == []


def _worker_market(n_runner: int = 2) -> _Market:
    runners = [_runner(OVER, 17.5, 18.0), _runner(UNDER, 1.06, 1.07)]
    if n_runner == 3:
        runners.append(_runner(47974, 30.0, 32.0))
    return _Market(MID, runners=runners)


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setattr(LOW, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(LOW, "_max_stake", lambda: None)
    monkeypatch.setattr(LOW, "_kill_switch", lambda: False)
    monkeypatch.setattr(LOW, "_SETTINGS", {"kill_switch": False})
    # l'instradamento paper/live sul client della modalita' (F0) non e' l'oggetto di
    # questi test e ha i suoi: qui il mercato finto riceve il place senza client
    monkeypatch.setattr(LOW, "_client_for_mode", lambda *_a, **_k: None)
    yield


def _riga_coda(payload: dict, rid: int) -> dict:
    riga = dict(payload)
    riga.update({"id": rid, "status": "processing", "handicap": 0.0})
    return riga


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_d3_worker_traduce_la_riga_di_coda_come_il_canale(worker, mode):
    db = _db(mode)
    cid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": "lay", "mode": mode, "status": "pending", "price": 18.0,
                           "size": 0.43, "meta": {"phase": "reserved", "cashout": True,
                                                  "closes_trade_id": 1}})
    assert _place_chiusura_043(db, None, mode, cid).status == "pending"
    riga = _riga_coda(db.queue[-1], 7)
    sb = _Sb([riga])
    market = _worker_market(2)
    LOW._dispatch(sb, _fl(market), riga, mode, _STRAT)
    ordine = market.placed[-1]
    t = tradotto_di("lay", 18.0, 0.43)
    # lo STESSO ordine che manda il canale (verdetto vero del motore)
    assert (ordine.selection_id, ordine.side, ordine.order_type.price,
            ordine.order_type.size) == (UNDER, "BACK", t["mandato"]["price"],
                                        t["mandato"]["size"])
    assert riga["status"] == "done"
    res = riga["result"]
    assert (res["selection_id"], res["side"], res["price"], res["size"]) == \
        (OVER, "lay", 18.0, 0.43)
    assert res["riga_mandata"]["selection_id"] == UNDER
    assert res["tradotto"]["mandato"] == t["mandato"]


def test_d3_worker_tre_esiti_rifiuto_col_codice_nessun_ordine(worker):
    db = _db("live")
    assert _place_chiusura_043(db, None, "live", 5).status == "pending"
    riga = _riga_coda(db.queue[-1], 8)
    market = _worker_market(3)
    with pytest.raises(ValueError, match="SOTTO_MINIMO_NON_PIAZZABILE"):
        LOW._dispatch(_Sb([riga]), _fl(market), riga, "live", _STRAT)
    assert market.placed == []


def test_d3_worker_senza_flag_nessun_cambio(worker):
    """Una riga di coda che NON chiede l'equivalente (Omega, desktop, Mike) non cambia."""
    riga = {"id": 9, "action": "place_submin", "mode": "live", "market_id": MID,
            "selection_id": OVER, "handicap": 0.0, "side": "lay", "price": 18.0,
            "size": 0.43, "params": {"target_size": 0.43}}
    assert LOW._traduci_riga_coda(_fl(_worker_market(2)), riga) is None


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_d3_coda_completa_lo_specchio_si_legge_nei_termini_chiesti(worker, mode):
    """Safe accoda -> worker VERO traduce -> specchio dell'ordine vero (encoder di
    produzione) -> poll VERO della coda: la riga di chiusura dice 0,43 @18."""
    db = _db(mode)
    parent = _apertura(db, mode=mode)
    cid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": "lay", "mode": mode, "origin": "manual",
                           "status": "pending", "price": 18.0, "size": 0.43,
                           "closes_trade_id": parent["id"],
                           "meta": {"phase": "reserved", "cashout": True,
                                    "closes_trade_id": parent["id"]}})
    assert _place_chiusura_043(db, None, mode, cid).status == "pending"
    rid = int(db.get_trade(cid)["meta"]["flumine_request_id"])
    riga = _riga_coda(db.queue[-1], rid)
    sb = _Sb([riga])
    market = _worker_market(2)
    LOW._dispatch(sb, _fl(market), riga, mode, _STRAT)
    vero = market.placed[-1]
    db.coda_runner[rid].update({"status": "done", "result": riga["result"],
                                "bet_id": BET})
    db.specchi_runner["awlq%d" % rid] = riga_vera(
        selection_id=UNDER, side="back", price=vero.order_type.price,
        size=vero.order_type.size, matched=vero.order_type.size, remaining=0.0,
        status="EXECUTION_COMPLETE", bet_id=BET, avg=1.06, mode=mode,
        ref="awlq%d" % rid)
    OS.poll_flumine_pending(db=db, params={}, now=NOW + timedelta(seconds=2), market=None)
    c = db.get_trade(cid)
    assert c["status"] == "open", c["meta"]
    assert (c["selection_id"], c["side"], c["size"], c["price"]) == (OVER, "lay", 0.43, 18.0)


# ===========================================================================
# D3 - REST (runner giu', soldi veri): stesso verdetto, letto dal book di Betfair
# ===========================================================================
def _rest(db: FakeDB) -> None:
    db.follow = "NONE"                       # gate della coda chiuso: si va in REST


def test_d3_rest_chiusura_043_piazza_l_equivalente_e_conferma_nei_termini_chiesti(
        monkeypatch):
    rete = monta_rete(monkeypatch)
    rete.book = book_grezzo(OVER, UNDER)
    db = _db("live")
    _rest(db)
    out = _place_chiusura_043(db, S._MercatoSafe(OM), "live", 5)
    assert out.status == "open", out.fill_note
    assert len(rete.piazzati) == 1
    _mid, ins, kw = rete.piazzati[0]
    t = tradotto_di("lay", 18.0, 0.43)
    assert (ins["selectionId"], ins["side"], ins["limitOrder"]["price"],
            ins["limitOrder"]["size"]) == (UNDER, "BACK", t["mandato"]["price"],
                                           t["mandato"]["size"])
    assert ins["customerOrderRef"] == "safe-t5"
    assert kw["customer_strategy_ref"] == S.SAFE_STRATEGY_REF
    # l'esito nei termini chiesti: la riga dira' banca Over 0,43 @18
    assert (out.price, out.size, out.bet_id) == (18.0, 0.43, "PIAZZATO1")
    assert out.esecuzione["tradotto"]["mandato"] == t["mandato"]


def test_d3_rest_tre_esiti_rifiuto_certo_nessun_ordine(monkeypatch):
    rete = monta_rete(monkeypatch)
    rete.book = book_grezzo(OVER, UNDER, 47974)
    db = _db("live")
    _rest(db)
    out = _place_chiusura_043(db, S._MercatoSafe(OM), "live", 5)
    assert out.status == "error" and out.error_code == "SOTTO_MINIMO_NON_PIAZZABILE"
    assert rete.piazzati == []


@pytest.mark.parametrize("libro", ["runner_rimosso", "due_vincitori", "illeggibile"])
def test_d3_rest_due_runner_non_esaustivi_niente_equivalente(monkeypatch, libro):
    rete = monta_rete(monkeypatch)
    if libro == "runner_rimosso":
        rete.book = book_grezzo(OVER, UNDER, stato_runner="REMOVED")
    elif libro == "due_vincitori":
        rete.book = book_grezzo(OVER, UNDER, vincitori=2)
    else:
        rete.book = []
    db = _db("live")
    _rest(db)
    out = _place_chiusura_043(db, S._MercatoSafe(OM), "live", 5)
    assert out.status == "error" and out.error_code == "SOTTO_MINIMO_NON_PIAZZABILE"
    assert rete.piazzati == []


def test_d3_tre_vie_stesso_verdetto_stesso_ordine_stessa_riga(worker, monkeypatch):
    """Canale (verdetto del motore), coda (worker vero) e REST (book di Betfair): lo
    stesso ordine mandato e gli stessi numeri sulla riga del bot."""
    t = tradotto_di("lay", 18.0, 0.43)
    canale = (t["mandato"]["selection_id"], t["mandato"]["side"], t["mandato"]["price"],
              t["mandato"]["size"])
    # coda
    db = _db("live")
    assert _place_chiusura_043(db, None, "live", 5).status == "pending"
    riga = _riga_coda(db.queue[-1], 3)
    market = _worker_market(2)
    LOW._dispatch(_Sb([riga]), _fl(market), riga, "live", _STRAT)
    o = market.placed[-1]
    coda = (o.selection_id, o.side.lower(), o.order_type.price, o.order_type.size)
    # REST
    rete = monta_rete(monkeypatch)
    rete.book = book_grezzo(OVER, UNDER)
    db2 = _db("live")
    _rest(db2)
    out = _place_chiusura_043(db2, S._MercatoSafe(OM), "live", 6)
    ins = rete.piazzati[0][1]
    rest = (ins["selectionId"], ins["side"].lower(), ins["limitOrder"]["price"],
            ins["limitOrder"]["size"])
    assert canale == coda == rest
    assert (riga["result"]["size"], riga["result"]["price"]) == (out.size, out.price) == \
        (0.43, 18.0)
