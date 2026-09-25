"""25/09 (residui B17) - il CASH OUT GLOBALE DI PARTITA dichiara per id gli
ordini che genera.

La scheda della Control Room (`CashOutPartita`) segue ogni ordine del cash out
fino all'abbinamento; le gambe le prende SOLO dagli id che il servizio scrive
nel risultato della richiesta (`closing_trade_ids`, `gambe`), mai dalle righe
nuove della partita. Qui si inchioda che il servizio li scrive, con le righe e
il mercato finti di `test_chiusura_dell_utente` (stesse chiavi del vero), e
che niente cambia nella decisione (stesse righe chiuse, stessi rami).
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X

from test_bot_service import NOW, FakeDB, _feed_row
from test_chiusura_dell_utente_2026_09_16 import MercatoConConto, _riga


@pytest.fixture(autouse=True)
def _indice_pulito():
    S._EVENTI_CHIUSI.clear()
    S._CONTO_LETTO_A.clear()
    yield
    S._EVENTI_CHIUSI.clear()
    S._CONTO_LETTO_A.clear()


def _cashout(db, mercato):
    return S._request_cashout_event(
        db=db, market=mercato, rows_by_event={"1.1": _feed_row()},
        payload={"event_id": "1.1"}, params={}, now=NOW)


def test_gli_ordini_del_cashout_globale_sono_dichiarati_per_id():
    db = FakeDB(mode="live")
    a = _riga(db)
    b = _riga(db, signal_key="1.1:esatto:away:1-1", selection_name="Away")
    mercato = MercatoConConto()
    mercato.book = {"status": "OPEN", "runners": {}}
    res = _cashout(db, mercato)
    assert res["ok"] is True
    figlie = {t["closes_trade_id"]: t["id"] for t in db.trades if t.get("closes_trade_id")}
    # gli id dichiarati sono ESATTAMENTE le gambe di chiusura nate, nell'ordine
    # delle posizioni chiuse
    assert res["closing_trade_ids"] == [figlie[a["id"]], figlie[b["id"]]]
    assert res["gambe"] == [
        {"trade_id": a["id"], "closing_trade_id": figlie[a["id"]], "ok": True},
        {"trade_id": b["id"], "closing_trade_id": figlie[b["id"]], "ok": True},
    ]
    # la decisione non cambia: stesse posizioni chiuse, nessuna non chiusa
    assert res["chiuse"] == [a["id"], b["id"]] and res["non_chiuse"] == []
    # e il risultato che la UI legge (`_request_result`) li conserva
    out = S._request_result(res)
    assert out["closing_trade_ids"] == res["closing_trade_ids"]


def test_una_posizione_rifiutata_non_genera_id_e_resta_non_chiusa():
    """Una riga in riconciliazione non si chiude: nessun ordine, nessun id;
    il motivo resta in `non_chiuse`."""
    db = FakeDB(mode="live")
    a = _riga(db)
    _riga(db, signal_key="1.1:esatto:away:1-1", selection_name="Away",
          status="open", meta={"reason": "place_exception_reconciling"})
    mercato = MercatoConConto()
    mercato.book = {"status": "OPEN", "runners": {}}
    res = _cashout(db, mercato)
    figlie = [t for t in db.trades if t.get("closes_trade_id")]
    assert [f["closes_trade_id"] for f in figlie] == [a["id"]]
    assert res["closing_trade_ids"] == [figlie[0]["id"]]
    assert len(res["non_chiuse"]) == 1
    assert "closing_trade_id" not in res["non_chiuse"][0]


def test_invio_fallito_dopo_la_riserva_dichiara_comunque_l_ordine(monkeypatch):
    """`execution.close_trade` torna 'chiusura_non_eseguita' CON
    `closing_trade_id` quando l'ordine e' partito ed e' fallito: quell'ordine
    esiste (riga 'error'), la scheda lo deve mostrare come rifiutato."""
    db = FakeDB(mode="live")
    a = _riga(db)

    def finto_close(**kw):
        return {"error": "chiusura_non_eseguita", "detail": "INSUFFICIENT_FUNDS",
                "closing_trade_id": 999}

    monkeypatch.setattr(X, "close_trade", finto_close)
    mercato = MercatoConConto()
    mercato.book = {"status": "OPEN", "runners": {}}
    res = _cashout(db, mercato)
    assert res["closing_trade_ids"] == [999]
    assert res["gambe"] == [{"trade_id": a["id"], "closing_trade_id": 999, "ok": False}]
    assert res["non_chiuse"] == [{"trade_id": a["id"], "motivo": "chiusura_non_eseguita",
                                  "closing_trade_id": 999}]


@pytest.mark.parametrize("v,atteso", [(7, 7), ("12", 12), (0, None), (-3, None),
                                      (None, None), ("x", None)])
def test_id_ordine_mai_zero_ne_inventato(v, atteso):
    assert S._id_ordine(v) == atteso
