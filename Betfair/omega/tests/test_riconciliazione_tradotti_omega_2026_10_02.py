"""02/10/2026 - RICONCILIAZIONE DEI TRADOTTI, lato OMEGA (difetto D1).

D1: quando l'esito di una chiusura mandata sul canale non arriva entro la scadenza live
(20 s), Omega rilegge Betfair (``_canale_live_oltre_scadenza``). Se il runner ha TRADOTTO
la chiusura nell'equivalente sull'altra selezione (banca Over 0,25 @19 -> punta Under
4,50 @1,06):
  - senza bet_id, ``_adotta_per_mercato`` cercava selezione Over e lato banca, non trovava
    la punta Under e marcava la chiusura FALLITA (``canale_mai_visto_su_betfair``) mentre
    l'ordine vero era ABBINATO: la posizione restava aperta e un secondo cash-out mandava
    una SECONDA chiusura (doppia esposizione);
  - con il bet_id, confermava la riga Over coi numeri della punta Under (4,50 @1,06).

Finti: rete Betfair a livello di ``OM.call`` (funzioni vere di ``omega_market``), eventi del
canale da ``motore_ordini._riporta_tradotto`` (``tradotti_comuni``), DB storico di Omega.
Nessuna rete, nessun ordine reale. ASCII-only.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest

from Betfair.omega import omega_market as OM
from Betfair.omega import omega_service as S
from Betfair.omega import porta_ordini as PO
from Betfair.omega.test_omega_flumine_paper import FakeQueueDB, _params
from Betfair.omega.test_omega_service import _control
from Betfair.omega.tests.test_porta_ordini_omega_f6_2026_09_24 import (
    TOKEN,
    FintoMotore,
    _attendi,
)
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as SPO
from Betfair.stream import live_order_build as LB
from Betfair.stream import motore_ordini as MO
from Betfair.stream.tests.tradotti_comuni import (
    MID,
    NOW,
    OVER,
    UNDER,
    corrente_grezzo,
    evento_tradotto,
    monta_rete,
    tradotto_di,
)

BET = "330000000777"


class _DBLive(FakeQueueDB):
    """Il DB storico di Omega in LIVE con gli accessor del cash-out che ha anche il finto
    del green-up (``test_omega_greenup_2026_09_10._DB``): le gambe di chiusura si leggono
    dal DB (``execution.known_closings``), come in produzione (``omega_db``)."""

    def closing_trades_for(self, ids: Any) -> list:
        volute = {int(i) for i in ids}
        return [t for t in self.trades if t.get("closes_trade_id") in volute]

    def hedged_trades(self) -> list:
        return self.list_trades("hedged")


def _db() -> FakeQueueDB:
    return _DBLive(_control(mode="live"), hb_mode="LIVE")


def _apertura(db: FakeQueueDB, *, side: str, price: float, size: float) -> dict:
    tid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": side, "mode": "live", "origin": "manual",
                           "status": "open", "price": price, "size": size,
                           "liability": X.liability_of(side, size, price), "pnl": 0.0,
                           "commission": 0.05, "bet_id": "APERTURA1", "meta": {}})
    return db.get_trade(tid)


def _chiusura_pending(db: FakeQueueDB, parent: dict, *, side: str, price: float,
                      size: float, bet_id: Any = None, meta: Any = None) -> dict:
    """Una gamba di chiusura mandata sul canale come la lascia ``_place_via_canale``."""
    tid = db.insert_trade({"event_id": "E1", "market_id": MID, "selection_id": OVER,
                           "side": side, "mode": "live", "origin": "manual",
                           "status": "pending", "price": price, "size": size,
                           "liability": X.liability_of(side, size, price), "pnl": 0.0,
                           "closes_trade_id": parent["id"], "bet_id": bet_id,
                           "placed_at": NOW.isoformat(),
                           "meta": {"cashout": True, "closes_trade_id": parent["id"],
                                    "canale_ref": "omega-t%d" % (parent["id"] + 1),
                                    "canale_inviato_at": NOW.isoformat(),
                                    "reason": "place_exception_reconciling",
                                    "err": "canale_in_corso", **(meta or {})}})
    return db.get_trade(tid)


def _ripiego(db: FakeQueueDB, tr: dict, secondi: float = 30.0) -> int:
    return S._canale_live_oltre_scadenza(
        tr, db=db, market=OM, now=NOW + timedelta(seconds=secondi), min_stake=0.5,
        eta=secondi, deadline_s=20.0)


# ===========================================================================
# D1 - ripiego oltre i 20 s senza bet_id: la punta Under abbinata e' la chiusura
# ===========================================================================
def test_d1_senza_bet_id_la_chiusura_tradotta_abbinata_non_e_fallita(monkeypatch):
    rete = monta_rete(monkeypatch)
    db = _db()
    parent = _apertura(db, side="back", price=4.75, size=1.0)
    tr = _chiusura_pending(db, parent, side="lay", price=19.0, size=0.25)
    t = tradotto_di("lay", 19.0, 0.25)
    m = t["mandato"]
    assert (m["side"], m["price"], m["size"]) == ("back", 1.06, 4.5)
    rete.correnti = [corrente_grezzo(bet_id=BET, selection_id=UNDER, side="back",
                                     price=1.06, size=4.5, matched=4.5, remaining=0.0)]
    # oltre la scadenza E oltre la grazia di propagazione: prima del 02/10 qui la
    # chiusura diventava FALLITA (``canale_mai_visto_su_betfair``) con l'ordine abbinato
    assert _ripiego(db, tr, 200.0) == 1
    r = db.get_trade(tr["id"])
    assert r["status"] == "open", r["meta"].get("reason")
    assert r["bet_id"] == BET
    # la riga dice la SUA chiusura (banca Over 0,25 @19), mai la punta Under
    assert (r["selection_id"], r["side"], r["size"], r["price"]) == (OVER, "lay", 0.25, 19.0)
    assert r["meta"][X.CHIAVE_TRADOTTO]["mandato"]["selection_id"] == UNDER


def test_d1_senza_bet_id_impronta_diversa_non_si_adotta(monkeypatch):
    """Un ordine sull'altra selezione che NON e' l'equivalente esatto (size diversa) non
    si adotta: resta la regola di prima (nessun ordine nostro = dopo la grazia FALLITA)."""
    rete = monta_rete(monkeypatch)
    db = _db()
    parent = _apertura(db, side="back", price=4.75, size=1.0)
    tr = _chiusura_pending(db, parent, side="lay", price=19.0, size=0.25)
    rete.correnti = [corrente_grezzo(bet_id=BET, selection_id=UNDER, side="back",
                                     price=1.06, size=9.99, matched=9.99, remaining=0.0)]
    assert _ripiego(db, tr, 30.0) == 0                     # grazia: si aspetta
    assert _ripiego(db, tr, 200.0) == 1
    r = db.get_trade(tr["id"])
    assert r["status"] == "error" and r["meta"]["reason"] == \
        "flumine_canale_mai_visto_su_betfair"
    assert not r.get("bet_id")


# ===========================================================================
# D1 - ripiego oltre i 20 s CON il bet_id (dall'evento accettato del canale)
# ===========================================================================
def test_d1_con_bet_id_lo_stato_rest_si_legge_nei_termini_chiesti(monkeypatch):
    rete = monta_rete(monkeypatch)
    db = _db()
    parent = _apertura(db, side="back", price=4.75, size=1.0)
    tr = _chiusura_pending(db, parent, side="lay", price=19.0, size=0.25, bet_id=BET)
    rete.correnti = [corrente_grezzo(bet_id=BET, selection_id=UNDER, side="back",
                                     price=1.06, size=4.5, matched=4.5, remaining=0.0)]
    assert _ripiego(db, tr) == 1
    r = db.get_trade(tr["id"])
    assert r["status"] == "open"
    assert (r["side"], r["size"], r["price"]) == ("lay", 0.25, 19.0)


def test_d1_evento_accettato_salva_la_dichiarazione_e_il_ripiego_la_usa(monkeypatch):
    """L'evento intermedio porta ``tradotto``: la riga lo conserva, e il ripiego traduce
    anche uno stato per bet_id che non dice selezione e lato (ogni lettura e' coperta)."""
    db = _db()
    parent = _apertura(db, side="back", price=4.75, size=1.0)
    tr = _chiusura_pending(db, parent, side="lay", price=19.0, size=0.25)
    t = tradotto_di("lay", 19.0, 0.25)
    ev = evento_tradotto(t, ref=tr["meta"]["canale_ref"], seq=3, fase="accettato_betfair",
                         matched=0.0, remaining=4.5, status="EXECUTABLE", bet_id=BET)
    assert (ev["selection_id"], ev["side"], ev["size"]) == (OVER, "lay", 0.25)
    S._aggiorna_da_evento(tr, ev, db=db)
    r = db.get_trade(tr["id"])
    assert r["bet_id"] == BET and r["meta"][X.CHIAVE_TRADOTTO]["mandato"]["size"] == 4.5

    class _Mercato:
        def order_state_by_bet_id(self, bet_id: str) -> dict:
            assert bet_id == BET
            return {"found": True, "size_matched": 4.5, "avg_price_matched": 1.06,
                    "size_remaining": 0.0, "matched_date": None, "placed_date": None}

    n = S._canale_live_oltre_scadenza(r, db=db, market=_Mercato(),
                                      now=NOW + timedelta(seconds=30), min_stake=0.5,
                                      eta=30.0, deadline_s=20.0)
    assert n == 1
    r = db.get_trade(tr["id"])
    assert r["status"] == "open" and (r["size"], r["price"]) == (0.25, 19.0)


def test_d1_evento_terminale_conferma_e_conserva_la_dichiarazione():
    db = _db()
    parent = _apertura(db, side="back", price=4.75, size=1.0)
    tr = _chiusura_pending(db, parent, side="lay", price=19.0, size=0.25)
    t = tradotto_di("lay", 19.0, 0.25)
    ev = evento_tradotto(t, ref=tr["meta"]["canale_ref"], seq=4, fase="abbinato",
                         matched=4.5, remaining=0.0, status="EXECUTION_COMPLETE",
                         bet_id=BET)
    assert S._chiudi_da_evento(tr, ev, db=db, mode="live", min_stake=0.5, now=NOW) == 1
    r = db.get_trade(tr["id"])
    assert r["status"] == "open" and (r["size"], r["price"]) == (0.25, 19.0)
    assert r["meta"][X.CHIAVE_TRADOTTO]["mandato"]["selection_id"] == UNDER


def test_d1_ordine_non_tradotto_invariato(monkeypatch):
    """Una chiusura NON tradotta (stessa selezione, stesso lato) si conferma coi numeri
    di Betfair come prima: nessuna regressione."""
    rete = monta_rete(monkeypatch)
    db = _db()
    parent = _apertura(db, side="back", price=3.0, size=5.0)
    tr = _chiusura_pending(db, parent, side="lay", price=2.5, size=6.0)
    rete.correnti = [corrente_grezzo(bet_id=BET, selection_id=OVER, side="lay",
                                     price=2.5, size=6.0, matched=6.0, remaining=0.0,
                                     avg=2.48)]
    assert _ripiego(db, tr) == 1
    r = db.get_trade(tr["id"])
    assert r["status"] == "open" and (r["size"], r["price"], r["bet_id"]) == (6.0, 2.48, BET)


# ===========================================================================
# D1 - IL CASO COMPLETO: chiusura sul canale tradotta, esito oltre i 20 s, nessuna
# seconda chiusura (entrambi i versi dell'equivalenza)
# ===========================================================================
class MotoreCheTraduce(FintoMotore):
    """Il finto del motore che, per un place sotto il minimo su un mercato a due esiti,
    fa cio' che fa ``MotoreOrdini``: verdetto VERO (``verdetto_minimi``), ordine
    equivalente sull'altra selezione, evento ``accettato_betfair`` riportato nei termini
    del chiesto (``_riporta_tradotto``). Poi TACE: l'esito arriva oltre la scadenza."""

    def __init__(self) -> None:
        super().__init__()
        self.mandati: list = []
        self.rifiutati: list = []

    def gestisci(self, ws: Any, testo: str) -> None:
        """Come il motore VERO (punto 11, ``_applica_minimi``): un attore fuori da
        ``minimi_it.ATTORI_CON_TRADUZIONE`` non ha l'equivalente; un place sotto il minimo
        e sotto 0,50 e' allora un rifiuto ``SOTTO_MINIMO_NON_PIAZZABILE`` (paper = live)."""
        from Betfair.stream.trading import minimi_it as MI

        msg = json.loads(testo)
        d = msg.get("d") or {}
        if (msg.get("t") == "comando" and d.get("azione") == "place"
                and d.get("attore") not in MI.ATTORI_CON_TRADUZIONE):
            v = LB.verdetto_minimi("it", d["side"].lower(), d["price"], d["size"],
                                   altra_selezione=None)
            if v.esito == LB.VERDETTO_IMPOSSIBILE:
                MO.valida_comando("omega", d)
                self.comandi.append(d)
                self.rifiutati.append(d)
                self._manda(ws, "ack", {"ref": d["ref"], "seq": self._nuovo_seq(),
                                        "accettato": False, "motivo": str(v.motivo),
                                        "ricevuto_ms": 1.0})
                return
        super().gestisci(ws, testo)

    def _fine(self, ws: Any, d: dict) -> None:
        from Betfair.stream.trading import minimi_it as MI

        if d["azione"] != "place" or d.get("attore") not in MI.ATTORI_CON_TRADUZIONE:
            return super()._fine(ws, d)
        v = LB.verdetto_minimi("it", d["side"].lower(), d["price"], d["size"],
                               altra_selezione=(UNDER, 0.0))
        if v.esito != LB.VERDETTO_EQUIVALENTE:
            return super()._fine(ws, d)
        t = tradotto_di(d["side"].lower(), d["price"], d["size"])
        self.mandati.append(t["mandato"])
        if self.fase_finale == "muto_dopo_ack":
            return
        ev = evento_tradotto(t, ref=d["ref"], seq=self._nuovo_seq(),
                             fase="accettato_betfair", matched=0.0,
                             remaining=t["mandato"]["size"], status="EXECUTABLE",
                             bet_id=BET, mode=d["mode"])
        self.eventi.append(ev)
        self._manda(ws, "order", ev)


@pytest.fixture
def traduzione_omega(monkeypatch):
    """Punto 11: la traduzione vale solo per ``ATTORI_CON_TRADUZIONE`` (oggi vuoto); i
    test del caso completo abilitano 'omega' SOLO per la prova, come i test del runner."""
    from Betfair.stream.trading import minimi_it as MI

    monkeypatch.setattr(MI, "ATTORI_CON_TRADUZIONE", frozenset({"omega"}))


@pytest.fixture
def motore(monkeypatch):
    m = MotoreCheTraduce()
    monkeypatch.setenv(PO.ENV_CANALE, "1")
    monkeypatch.setattr(SPO, "MAX_ETA_MS", 400)
    monkeypatch.setattr(PO, "_crea_porta", lambda: PO.PortaCanaleOmega(
        porta_ws=47331, attore="omega", sport="calcio", connetti=m.connetti,
        token_fn=lambda: TOKEN))
    PO.azzera()
    porta = PO.porta_omega()
    assert _attendi(porta.disponibile)
    yield m
    PO.azzera()


class _MercatoOU:
    """Il mercato di Omega per il cash-out: book REST (``read_book``, chiavi vere del
    lettore ``_cashout_prices``) e le letture VERE di ``omega_market`` sulla rete finta."""

    def __init__(self, back: float, lay: float) -> None:
        self.back, self.lay = back, lay

    def read_book(self, market_id: str, _names: dict) -> dict:
        return {"market_id": MID, "status": "OPEN", "inplay": True,
                "runners": [{"selection_id": OVER, "back_price": self.back,
                             "back_size": 500.0, "lay_price": self.lay, "lay_size": 500.0,
                             "lay_ladder": [[self.lay, 500.0]]},
                            {"selection_id": UNDER, "back_price": 1.06, "back_size": 500.0,
                             "lay_price": 1.07, "lay_size": 500.0,
                             "lay_ladder": [[1.07, 500.0]]}]}

    def __getattr__(self, nome: str) -> Any:
        return getattr(OM, nome)


@pytest.mark.parametrize("verso", ["banca_tradotta_in_punta", "punta_tradotta_in_banca"])
@pytest.mark.parametrize("con_bet_id", [True, False])
def test_d1_caso_completo_nessuna_seconda_chiusura(traduzione_omega, motore, monkeypatch,
                                                   verso, con_bet_id):
    rete = monta_rete(monkeypatch)
    db = _db()
    if verso == "banca_tradotta_in_punta":
        # aperta PUNTA Over 1,00 @4,75; chiusura = BANCA Over 1,00x4,75/19 = 0,25 @19
        parent = _apertura(db, side="back", price=4.75, size=1.0)
        mercato = _MercatoOU(back=18.5, lay=19.0)
    else:
        # aperta BANCA Over 1,00 @3,00; chiusura = PUNTA Over 1,00x3/6 = 0,50 @6
        parent = _apertura(db, side="lay", price=3.0, size=1.0)
        mercato = _MercatoOU(back=6.0, lay=6.2)
    if not con_bet_id:
        motore.fase_finale = "muto_dopo_ack"
    out = S._manual_cashout(market=mercato, db=db, payload={"trade_id": parent["id"]},
                            now=NOW)
    assert out.get("ok") is True and out.get("pending_fill") is True, out
    cmd = motore.comandi[-1]
    chiusura = next(t for t in db.trades if t.get("closes_trade_id") == parent["id"])
    assert motore.mandati, "il comando doveva essere sotto il minimo e tradotto"
    mand = motore.mandati[-1]
    porta = PO.porta_esistente()
    if con_bet_id:
        assert _attendi(lambda: (porta.esiti(cmd["ref"]) or {}).get("bet_id") == BET)
    # l'ordine VERO (l'equivalente) si abbina su Betfair; il canale tace oltre i 20 s
    rete.correnti = [corrente_grezzo(bet_id=BET, selection_id=UNDER, side=mand["side"],
                                     price=mand["price"], size=mand["size"],
                                     matched=mand["size"], remaining=0.0)]
    S.poll_flumine_pending(db=db, params=_params(), now=NOW + timedelta(seconds=25),
                           market=mercato)
    # oltre anche la grazia di propagazione: prima del 02/10, senza bet_id, qui la
    # chiusura diventava FALLITA con l'ordine vero abbinato
    S.poll_flumine_pending(db=db, params=_params(), now=NOW + timedelta(seconds=200),
                           market=mercato)
    S._settle_hedged(params=_params(), market=mercato, db=db,
                     now=NOW + timedelta(seconds=201))
    # NESSUNA seconda chiusura: la posizione e' chiusa (prima: un secondo cash-out
    # mandava un secondo comando, cioe' una posizione opposta aperta)
    n_comandi = len(motore.comandi)
    out2 = S._manual_cashout(market=mercato, db=db, payload={"trade_id": parent["id"]},
                             now=NOW + timedelta(seconds=210))
    assert len(motore.comandi) == n_comandi, ("SECONDA CHIUSURA mandata", out2)
    assert out2.get("ok") is not True, out2
    assert len([t for t in db.trades if t.get("closes_trade_id") == parent["id"]]) == 1
    c = db.get_trade(chiusura["id"])
    assert c["status"] == "open", c["meta"].get("reason")
    assert c["bet_id"] == BET
    # P&L e stato della riga dai numeri della SUA chiusura, al centesimo
    abb, quota = LB.riporta_abbinato_all_originale(cmd["side"].lower(), cmd["price"],
                                                   cmd["size"], mand["size"], mand["size"])
    assert (c["selection_id"], c["side"], c["size"], c["price"]) == \
        (OVER, cmd["side"].lower(), abb, quota)
    assert abb == round(cmd["size"], 2)
    p = db.get_trade(parent["id"])
    assert p["status"] == "hedged", p["status"]


@pytest.mark.parametrize("ammesso", [True, False])
def test_d1_il_finto_rispetta_gli_attori_con_traduzione(motore, monkeypatch, ammesso):
    """Il finto del motore traduce SOLO se l'attore e' in ``ATTORI_CON_TRADUZIONE``, come
    il motore vero: fuori dall'insieme la chiusura banca 0,25 @19 e' un rifiuto
    ``SOTTO_MINIMO_NON_PIAZZABILE`` (nessun ordine, posizione aperta e dichiarata)."""
    from Betfair.stream.trading import minimi_it as MI

    monkeypatch.setattr(MI, "ATTORI_CON_TRADUZIONE",
                        frozenset({"omega"}) if ammesso else frozenset())
    monta_rete(monkeypatch)
    db = _db()
    parent = _apertura(db, side="back", price=4.75, size=1.0)
    out = S._manual_cashout(market=_MercatoOU(back=18.5, lay=19.0), db=db,
                            payload={"trade_id": parent["id"]}, now=NOW)
    if ammesso:
        assert motore.mandati and not motore.rifiutati
        assert out.get("ok") is True
    else:
        assert motore.mandati == [] and len(motore.rifiutati) == 1
        assert out.get("ok") is not True
        chiusura = next(t for t in db.trades if t.get("closes_trade_id") == parent["id"])
        assert chiusura["status"] == "error"
        assert db.get_trade(parent["id"])["status"] == "open"


def test_d1_contratto_le_chiavi_dell_evento_del_finto_sono_quelle_del_motore():
    """L'evento tradotto del finto ha le chiavi dello specchio di produzione piu' quelle
    che il motore aggiunge (``riga_mandata``, ``tradotto``)."""
    t = tradotto_di("lay", 19.0, 0.25)
    ev = evento_tradotto(t, ref="omega-t1", seq=1, fase="accettato_betfair", matched=0.0,
                         remaining=4.5, status="EXECUTABLE", bet_id=BET)
    assert set(MO.CHIAVI_SPECCHIO) <= set(ev)
    assert set(ev["riga_mandata"]) >= set(LB.CHIAVI_RIGA_MANDATA)
    assert json.loads(json.dumps(ev)) == ev
