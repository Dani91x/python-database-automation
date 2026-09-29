"""P4 BLOCCO 5 (29/09) - test mancanti trovati dalle mutazioni del coordinatore
sul blocco 3 (V2, V7, V8). Il codice e' giusto: qui si prova che rompendolo in
quei punti qualcosa diventa rosso.

Finti: `DbMemoria` del banco comune e `FakeDB` (firme di `mike/db.py`), runner
finto sul protocollo vero del canale (`runner_finto`), `EventInfo`/`Book` veri.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_d1_paper_sul_runner_2026_09_29 import (  # noqa: F401
    ORA, _book, _freni_aperti, _params, _taker)
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import EVENTO, db_vuoto, info_vera
from Betfair.mike.tests.test_mike_service import FakeDB


# ===========================================================================
# V2 - ordine paper senza risposta: UNA riconciliazione, non una a ogni giro
# ===========================================================================
def test_senza_risposta_gia_in_riconciliazione_non_si_ripete(runner):
    runner.trattieni = True
    db = db_vuoto()
    aggiornamenti: List[Dict[str, Any]] = []
    vero = db.update_trade

    def conta(tid, **kw):
        aggiornamenti.append(dict(kw, id=tid))
        return vero(tid, **kw)
    db.update_trade = conta
    leg = _taker()
    ctx = E.MatchCtx(legs=[leg])
    assert S.execute_place(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                           book=_book(), mode="paper", params=_params(), now=ORA, dry=False,
                           feed_fresh=True, ctx=ctx) == "pending"
    prima = len(aggiornamenti)
    tardi = ORA.timestamp() + S._SCADENZA_TAKER_PAPER_S + 1
    for i in range(3):
        S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                        now_ts=tardi + 5 * i, params=_params())
    assert leg.needs_reconcile
    righe = [p for k, p, _e in db.attivita
             if k == "reconcile_pending" and p.get("reason") == "runner_senza_esito"]
    assert len(righe) == 1, righe
    assert len(aggiornamenti) - prima == 1, aggiornamenti[prima:]


# ===========================================================================
# V7 / V8 - episodi di dato assente
# ===========================================================================
def _giro_dato(db, extra, ts, mancanti):
    S._episodio_dato_assente(db, extra, ts, "E1", "quote_assenti", mancanti,
                             S._DATO_ASSENTE_AVVISO_S,
                             {"reason": "linee assenti dal feed", "selections": mancanti,
                              "critical": True})


def _righe(db, kind, reason):
    return [p for k, p, _e in db.activity if k == kind and p.get("reason") == reason]


def test_quota_sparita_3_s_e_tornata_nessuna_riga_di_ritorno():
    db, extra = FakeDB(), {}
    for s in (0.0, 1.5, 3.0):
        _giro_dato(db, extra, 1000.0 + s, ["OU35|UNDER"])
    _giro_dato(db, extra, 1004.0, [])
    assert db.activity == [], db.activity           # mai avvisata, niente «tornato»
    assert "quote_assenti" not in extra


def test_episodio_chiuso_poi_nuovo_episodio():
    db, extra = FakeDB(), {}
    for s in (0.0, 5.0, 11.0):
        _giro_dato(db, extra, 1000.0 + s, ["OU35|UNDER"])
    _giro_dato(db, extra, 1012.0, [])
    assert len(_righe(db, "feed_line_missing", "linee assenti dal feed")) == 1
    assert len(_righe(db, "skip", "quote_assenti_tornato")) == 1
    for s in (13.0, 14.0, 15.0):                    # dato presente: niente di nuovo
        _giro_dato(db, extra, 1000.0 + s, [])
    assert len(db.activity) == 2 and "quote_assenti" not in extra
    for s in (100.0, 105.0, 111.0):                 # seconda assenza lunga
        _giro_dato(db, extra, 1000.0 + s, ["OU35|UNDER"])
    avvisi = _righe(db, "feed_line_missing", "linee assenti dal feed")
    assert len(avvisi) == 2 and avvisi[-1]["da_secondi"] == 11.0
