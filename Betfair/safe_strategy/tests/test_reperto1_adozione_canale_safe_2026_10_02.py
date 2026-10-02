"""02/10/2026 - REPERTO 1: Safe ritrova per MERCATO l'ordine del canale senza eventi.

Il difetto (preesistente, non solo dei tradotti): il mercato di Safe tiene solo gli ordini
col ref ``safe-`` (``bot_service._solo_ordini_di_safe``), ma il runner piazza col ref di
flumine (``<hash>-<id>``). Una riga LIVE mandata sul canale e rimasta senza NESSUN evento
(porta caduta, memoria persa) non veniva mai ritrovata per ref: dopo la grazia diventava
``reconcile_ordine_assente`` mentre l'ordine era ABBINATO su Betfair, e la gamba di
chiusura si rifaceva (doppia chiusura).

La correzione porta a Safe l'adozione per mercato di Omega (``_adotta_per_mercato``) con
l'impronta ESATTA: ordini della strategia ``safe`` sullo stesso mercato, selezione e lato,
quota e size chieste identiche a quelle MANDATE (``meta.canale_inviato``, scritto prima
dell'invio), piazzato nella finestra dell'invio, mai un bet_id gia' di un'altra riga; piu'
candidati = indecisa (resta in verifica). Nessuna condotta di strategia cambia.

Finti: DB storico di Safe, rete Betfair a livello di ``OM.call`` (funzioni vere di
``omega_market``), mercato di produzione di Safe (``_MercatoSafe``). ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from Betfair.omega import omega_market as OM
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy.tests.test_bot_service import FakeDB
from Betfair.stream.tests.tradotti_comuni import MID, NOW, OVER, UNDER, corrente_grezzo, monta_rete

REF_FLUMINE = "9f8e7d6c-1234567890"


def _db() -> FakeDB:
    db = FakeDB(status="stopped", mode="live")
    db.heartbeat = {"ts": NOW.isoformat(), "mode": "LIVE"}
    return db


def _apertura(db: FakeDB) -> dict:
    tid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": "back", "mode": "live", "origin": "manual",
                           "status": "open", "price": 3.0, "size": 5.0,
                           "liability": 5.0, "pnl": 0.0, "commission": 0.05,
                           "market_type": "OVER_UNDER_45", "bet_id": "APERTURA1", "meta": {}})
    return db.get_trade(tid)


def _chiusura_canale_muta(db: FakeDB, parent: dict, *, price: float = 2.5,
                          size: float = 6.0) -> dict:
    """La chiusura come la lascia ``_place_via_canale`` quando NESSUN evento arriva."""
    tid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": "lay", "mode": "live", "origin": "manual",
                           "status": "pending", "price": price, "size": size,
                           "closes_trade_id": parent["id"], "placed_at": NOW.isoformat(),
                           "market_type": "OVER_UNDER_45", "commission": 0.05,
                           "meta": {"cashout": True, "closes_trade_id": parent["id"],
                                    "canale_ref": "safe-t%d" % (parent["id"] + 1),
                                    "canale_inviato_at": NOW.isoformat(),
                                    "canale_inviato": {"selection_id": OVER, "side": "lay",
                                                       "price": price, "size": size},
                                    "reason": "place_exception_reconciling",
                                    "err": "canale_in_volo"}})
    return db.get_trade(tid)


def _ordine(bet: str = "B77", *, sel: int = OVER, side: str = "lay", price: float = 2.5,
            size: float = 6.0, matched: float = 6.0, ref: str = REF_FLUMINE,
            placed: str = "2026-10-02T20:00:01.000Z") -> dict:
    o = corrente_grezzo(bet_id=bet, selection_id=sel, side=side, price=price, size=size,
                        matched=matched, remaining=round(size - matched, 2), ref=ref)
    o["placedDate"] = placed
    return o


def _riconcilia(db: FakeDB, secondi: float) -> None:
    S.reconcile_pending(market=S._MercatoSafe(OM), db=db,
                        now=NOW + timedelta(seconds=secondi))


def test_r1_riga_del_canale_senza_eventi_ordine_abbinato_adottato_nessuna_seconda_chiusura(
        monkeypatch):
    rete = monta_rete(monkeypatch)
    db = _db()
    parent = _apertura(db)
    tr = _chiusura_canale_muta(db, parent)
    rete.correnti = [_ordine()]
    # oltre la scadenza del canale E oltre la grazia: prima del 02/10 qui la chiusura
    # diventava ``reconcile_ordine_assente`` con l'ordine abbinato su Betfair
    _riconcilia(db, 30)
    _riconcilia(db, 200)
    # nessuna seconda chiusura: l'apertura risulta coperta (prima: la chiusura in errore
    # lasciava l'apertura scoperta e un secondo cash-out mandava una seconda gamba)
    n = len(db.trades)
    out = X.close_trade(db=db, market=S._MercatoSafe(OM), trade=db.get_trade(parent["id"]),
                        prices={"back": 2.48, "lay": 2.5, "back_size": 500.0,
                                "lay_size": 500.0},
                        now=NOW + timedelta(seconds=210),
                        extra_row={"market_type": "OVER_UNDER_45"})
    assert out.get("ok") is not True, ("SECONDA CHIUSURA", out)
    assert len(db.trades) == n and db.queue == [] and rete.piazzati == []
    c = db.get_trade(tr["id"])
    assert c["status"] == "open", c["meta"].get("reason")
    assert (c["bet_id"], c["size"], c["price"]) == ("B77", 6.0, 2.5)
    assert c["meta"]["canale_bet_id_da"] == "mercato_selezione_lato"
    assert db.get_trade(parent["id"])["status"] == "hedged"


def test_r1_ordine_di_un_altro_bot_mai_adottato(monkeypatch):
    """Gli ordini si leggono SOLO della strategia ``safe``: il mercato chiede
    ``list_current_orders("safe")`` (mai la lista del conto intero)."""
    rete = monta_rete(monkeypatch)
    viste = []
    vero = OM.list_current_orders
    monkeypatch.setattr(OM, "list_current_orders",
                        lambda strategy_ref=None: viste.append(strategy_ref) or vero(strategy_ref))
    db = _db()
    tr = _chiusura_canale_muta(db, _apertura(db))
    rete.correnti = [_ordine()]
    _riconcilia(db, 30)
    assert db.get_trade(tr["id"])["status"] == "open"
    assert S.SAFE_STRATEGY_REF in viste or [S.SAFE_STRATEGY_REF] in viste


@pytest.mark.parametrize("diverso", [
    {"size": 6.5}, {"price": 2.52}, {"side": "back"}, {"sel": UNDER},
    {"placed": "2026-10-02T19:50:00.000Z"},
])
def test_r1_impronta_diversa_non_si_adotta(monkeypatch, diverso):
    rete = monta_rete(monkeypatch)
    db = _db()
    tr = _chiusura_canale_muta(db, _apertura(db))
    kw = dict(diverso)
    rete.correnti = [_ordine(**kw)]
    _riconcilia(db, 30)
    assert db.get_trade(tr["id"])["status"] == "pending"
    assert not db.get_trade(tr["id"]).get("bet_id")


def test_r1_due_candidati_indecisa_resta_in_verifica_con_avviso(monkeypatch):
    rete = monta_rete(monkeypatch)
    db = _db()
    tr = _chiusura_canale_muta(db, _apertura(db))
    rete.correnti = [_ordine("B1"), _ordine("B2")]
    _riconcilia(db, 200)
    r = db.get_trade(tr["id"])
    assert r["status"] == "pending" and not r.get("bet_id")
    assert any(k == "canale_orfano" for k, _p in db.activity)


def test_r1_bet_id_gia_di_un_altra_riga_mai_adottato(monkeypatch):
    rete = monta_rete(monkeypatch)
    db = _db()
    parent = _apertura(db)
    tr = _chiusura_canale_muta(db, parent)
    db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER, "side": "lay",
                     "mode": "live", "origin": "manual", "status": "open", "price": 2.5,
                     "size": 6.0, "bet_id": "B77", "meta": {}})
    rete.correnti = [_ordine("B77")]
    _riconcilia(db, 30)
    assert db.get_trade(tr["id"])["status"] == "pending"


def test_r1_nessun_ordine_resta_la_regola_di_prima(monkeypatch):
    """Nessun ordine su Betfair: dopo la grazia ``reconcile_ordine_assente`` come prima."""
    monta_rete(monkeypatch)
    db = _db()
    tr = _chiusura_canale_muta(db, _apertura(db))
    _riconcilia(db, 200)
    r = db.get_trade(tr["id"])
    assert r["status"] == "error" and r["meta"]["reason"] == "reconcile_ordine_assente"


def test_r1_il_canale_scrive_cosa_ha_mandato_prima_dell_invio():
    """``_place_via_canale`` scrive ``meta.canale_inviato`` (selezione, lato, quota, size
    MANDATE) nella stessa scrittura write-ahead di ``canale_ref``."""
    import inspect

    src = inspect.getsource(X._place_via_canale)
    i_inviato = src.index('"canale_inviato"')
    i_write = src.index("db.update_trade(tid, meta=pre)")
    assert i_inviato < i_write
