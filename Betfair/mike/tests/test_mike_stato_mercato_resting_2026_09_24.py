# -*- coding: utf-8 -*-
"""D2 (24/09) - MIKE: la lay appoggiata guarda lo stato del mercato.

La mappa del 24/09 ha trovato UNA strada d'invio di Mike senza controllo di
stato: la lay APPOGGIATA (``_is_resting_leg``). A mercato sospeso in live
l'ordine partiva e Betfair lo rifiutava (`_rifiutata`: la green al prezzo fisso
non veniva piu' riproposta), in paper si scriveva la riga pending su un mercato
sospeso (paper e live divergevano). Ora: nessun ordine, nessuna riga, UNA
attivita' ``attesa_riapertura``, e alla riapertura il motore la ripropone con
le condizioni di quel momento.

Il ciclo e' quello VERO (``service.run_once``) sul feed con le chiavi dello
scanner (``test_mike_feed.payload``: ``status``/``inplay``/``bet_delay`` per
blocco). ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from datetime import timedelta

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, legs, run, state
from Betfair.stream.trading import stato_mercato as SM


def _green(db):
    return [l for l in legs(db) if l["role"] == "under_green"]


def test_green_appoggiata_a_mercato_sospeso_aspetta_e_riparte_alla_riapertura():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    assert state(db) == "PRE_ENTRY_PENDING"
    n_righe = len(db.trades)
    # il mercato SOSPENDE proprio quando la green andrebbe appoggiata: tre giri
    for k in range(3):
        run(db, mk, NOW + timedelta(seconds=2 + 2 * k), [row(payload(status="SUSPENDED"))])
    assert "place_resting" not in db.kinds()
    assert len(db.trades) == n_righe                  # nessuna riga di riserva
    attese = [p for kd, p, _ in db.activity if kd == SM.KIND_ATTESA]
    assert len(attese) == 1                            # UNA riga per sospensione
    assert attese[0]["motivo"] == "SUSPENDED" and attese[0]["role"] == "under_green"
    assert all(g["status"] == "cancelled" for g in _green(db))
    # riapre: il motore ripropone la green, con le condizioni di adesso
    run(db, mk, NOW + timedelta(seconds=10), [row(payload())])
    assert "place_resting" in db.kinds()
    vive = [g for g in _green(db) if g["status"] == "pending"]
    assert len(vive) == 1 and vive[0]["price"] == 1.48


def test_a_mercato_aperto_la_green_si_appoggia_subito_come_prima():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    run(db, mk, NOW + timedelta(seconds=2), [row(payload())])
    assert "place_resting" in db.kinds()
    assert SM.KIND_ATTESA not in db.kinds()


def _gamba() -> E.Leg:
    return E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                 side="lay", price=1.48, size=10.14, ref="under_green-1-2")


def test_guardia_resting_stati():
    db = FakeDB()
    aperto = E.Book(best_back=1.5, best_lay=1.52, status="OPEN", inplay=False)
    assert S._resting_in_attesa(db, "E9", _gamba(), aperto) is False
    for st in ("SUSPENDED", "CLOSED", "INACTIVE"):
        g = _gamba()
        assert S._resting_in_attesa(db, "E9", g, E.Book(best_back=1.5, status=st)) is True
        assert g.status == "cancelled"
    # stato IGNOTO (nessun book): Mike non opera (M-17), come `execute_place`
    g = _gamba()
    assert S._resting_in_attesa(db, "E9", g, None) is True and g.status == "cancelled"
