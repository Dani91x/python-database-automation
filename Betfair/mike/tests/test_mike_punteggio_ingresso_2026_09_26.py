"""26/09 (F-5, test e2e FASE 3) - MIKE: ``score_at_entry`` era la STRINGA
'None-None' in pre-partita (f-string senza guardia in ``run_once``), e la
Control Room stampava «ingresso None-None». Senza punteggio si scrive
``None`` (null); con il punteggio 'casa-ospiti' come prima.

Il ciclo passa per il VERO ``run_once`` (FakeDB/FakeMarket di
``test_mike_service``, stesse chiavi di ``mike_*``): nessuna regola di
strategia toccata, il campo e' solo notizia sulla riga.

FALSIFICAZIONE (26/09): rimettendo
``score_str = f"{payload.get('score_home')}-{payload.get('score_away')}"`` il
primo test diventa rosso ('None-None' sulle righe).
"""
from __future__ import annotations

from datetime import timedelta

from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, payload, row, run


def test_prepartita_senza_punteggio_scrive_null_non_none_none():
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    run(db, mk, NOW + timedelta(seconds=2), [row(payload())])
    assert db.trades, "il ciclo pre-partita deve aver scritto almeno una riga"
    for t in db.trades:
        assert t["score_at_entry"] is None, t


def test_punteggio_ingresso_con_e_senza_valori():
    assert S._punteggio_ingresso({"score_home": 1, "score_away": 0}) == "1-0"
    assert S._punteggio_ingresso({"score_home": 0, "score_away": 0}) == "0-0"
    assert S._punteggio_ingresso({"score_home": None, "score_away": None}) is None
    assert S._punteggio_ingresso({"score_home": 2}) is None
    assert S._punteggio_ingresso({}) is None
