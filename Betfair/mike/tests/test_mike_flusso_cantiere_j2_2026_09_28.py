"""CANTIERE J2 (28/09/2026) - MIKE sul master di D1: il veto del FLUSSO vale
PRIMA dell'invio al runner (paper) e anche per la lay appoggiata.

Decisione dell'utente (28/09): se i prezzi di una partita non sono vivi nessun
bot apre ne' chiude a mercato su quei prezzi. In paper gli ordini di Mike li
esegue il RUNNER (D1, ``porta_ordini``): qui si prova, sul ciclo VERO
(``run_once``), che con le linee di Mike col flusso fermo (o col giro dello
scanner bloccato) al runner non arriva NESSUN comando, e che lo si DICE
(attivita' ``flusso_interrotto``, critica se c'e' una posizione).

Finti: ``FakeDB``/``FakeMarket`` di ``test_mike_service`` (le firme di
``mike/db.py``), righe del feed di ``test_mike_feed`` con il blocco ``flusso``
nelle chiavi e nei tipi che scrive lo scanner (``service.flusso_evento``), il
runner finto sul protocollo vero (fixture ``runner``). ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, legs, run
from Betfair.stream import flusso_prezzi as FP


def _ms(dt) -> int:
    return int(dt.timestamp() * 1000)


def _con_flusso(p: Dict[str, Any], fermi: List[str], quando=NOW) -> Dict[str, Any]:
    p = dict(p)
    p["flusso"] = {"vivo": True, "motivo": None, "dal_ms": _ms(quando) - 1000,
                   "mercati_fermi": list(fermi)}
    return p


def _scanner_nuovo(db: FakeDB, calcolato=NOW) -> None:
    db.scanner = {"updated_at": NOW.isoformat(),
                  "payload": {"flusso": {"calcolato_ms": _ms(calcolato), "eventi_fermi": {},
                                         "eventi_fermi_n": 0}}}


def _flusso(db: FakeDB) -> List[Dict[str, Any]]:
    return [p for k, p, _e in db.activity if k == "flusso_interrotto"]


def test_linee_ferme_nessuna_apertura_nessun_comando_al_runner(runner):
    db = FakeDB(params={"stake": 10})
    _scanner_nuovo(db)
    run(db, FakeMarket(), NOW, [row(_con_flusso(payload(), ["1.35", "1.45"]))])
    assert runner.comandi == [], "ordine inviato al runner su prezzi non vivi"
    assert db.trades == []
    f = _flusso(db)
    assert f and f[0]["reason"] == FP.MOTIVO_MERCATO_FERMO
    assert set(f[0]["mercati"]) == {"1.35", "1.45"}


def test_controllo_linee_vive_l_apertura_va_al_runner(runner):
    db = FakeDB(params={"stake": 10})
    _scanner_nuovo(db)
    run(db, FakeMarket(), NOW, [row(_con_flusso(payload(), []))])
    assert runner.comandi and runner.comandi[0]["side"] == "BACK"
    assert _flusso(db) == []


def test_giro_dello_scanner_bloccato_nessun_comando(runner):
    db = FakeDB(params={"stake": 10})
    _scanner_nuovo(db, calcolato=NOW - timedelta(seconds=FP.STATO_CALCOLO_MAX_S + 15))
    run(db, FakeMarket(), NOW, [row(_con_flusso(payload(), []))])
    assert runner.comandi == []
    f = _flusso(db)
    assert f and f[0]["reason"] == FP.MOTIVO_SCANNER_BLOCCATO


def test_posizione_aperta_la_lay_appoggiata_non_parte_col_flusso_fermo(runner):
    """Ingresso abbinato con i prezzi vivi; al giro dopo le linee si fermano: la
    lay di green-up (appoggiata, in paper sul book del runner) NON parte, e
    l'attivita' grida (critica: c'e' una posizione)."""
    db = FakeDB(params={"stake": 10})
    _scanner_nuovo(db)
    mk = FakeMarket()
    run(db, mk, NOW, [row(_con_flusso(payload(), []))])
    assert legs(db)[0]["status"] == "open", "precondizione: ingresso abbinato"
    n_prima = len(runner.comandi)
    dopo = NOW + timedelta(seconds=2)
    _scanner_nuovo(db, calcolato=dopo)
    run(db, mk, dopo, [row(_con_flusso(payload(), ["1.35", "1.45"], dopo), updated=dopo)])
    assert len(runner.comandi) == n_prima, "lay appoggiata inviata su prezzi non vivi"
    f = _flusso(db)
    assert f and f[-1]["critical"] is True
    # controllo: al rientro dei prezzi la lay parte
    rientro = NOW + timedelta(seconds=4)
    _scanner_nuovo(db, calcolato=rientro)
    run(db, mk, rientro, [row(_con_flusso(payload(), [], rientro), updated=rientro)])
    assert len(runner.comandi) == n_prima + 1 and runner.comandi[-1]["side"] == "LAY"


# ===========================================================================
# REGOLA UNICA (reperto A del coordinatore, 28/09)
# ===========================================================================
def _book_rest(market_id: str, sels) -> Dict[str, Any]:
    """``omega_market.read_book`` (chiavi vere): status, inplay, runners."""
    return {"market_id": market_id, "status": "OPEN", "inplay": False, "runners": [
        {"selection_id": sid, "name": nome, "status": "ACTIVE", "back_price": b, "back_size": bs,
         "lay_price": l, "lay_size": ls, "lay_ladder": [[l, ls]]}
        for sid, nome, b, l, bs, ls in sels]}


def _rest_vivo(mk: FakeMarket) -> None:
    mk.books["1.35"] = _book_rest("1.35", [(1222344, "Under 3.5 Goals", 1.50, 1.52, 30.0, 25.0),
                                           (1222345, "Over 3.5 Goals", 2.6, 2.7, 20.0, 15.0)])
    mk.books["1.45"] = _book_rest("1.45", [(1222347, "Under 4.5 Goals", 1.18, 1.19, 50.0, 40.0),
                                           (1222346, "Over 4.5 Goals", 6.0, 6.4, 12.0, 9.0)])


def _posizione_aperta(runner):
    from Betfair.mike import service as S

    S.svuota_le_cache() if hasattr(S, "svuota_le_cache") else None
    db = FakeDB(params={"stake": 10})
    _scanner_nuovo(db)
    mk = FakeMarket()
    run(db, mk, NOW, [row(_con_flusso(payload(), []))])
    assert legs(db)[0]["status"] == "open", "precondizione: ingresso abbinato"
    return db, mk


def test_regola_unica_mike_flusso_fermo_rest_vivo_la_chiusura_parte_coi_prezzi_rest(runner):
    db, mk = _posizione_aperta(runner)
    _rest_vivo(mk)
    n_prima = len(runner.comandi)
    dopo = NOW + timedelta(seconds=2)
    _scanner_nuovo(db, calcolato=dopo)
    run(db, mk, dopo, [row(_con_flusso(payload(), ["1.35", "1.45"], dopo), updated=dopo)])
    assert "1.35" in mk.calls, "il ripiego REST non e' stato letto"
    nuovi = runner.comandi[n_prima:]
    assert len(nuovi) == 1 and nuovi[0]["side"] == "LAY", nuovi   # green-up a riposo
    assert [p for k, p, _e in db.activity if k == "ripiego_rest"][0]["fonte"] == "rest_ripiego"


def test_regola_unica_mike_flusso_fermo_rest_muto_nessun_ordine_e_riga_critica(runner):
    db, mk = _posizione_aperta(runner)
    n_prima = len(runner.comandi)
    for k in range(3):
        t = NOW + timedelta(seconds=2 + 12 * k)
        _scanner_nuovo(db, calcolato=t)
        run(db, mk, t, [row(_con_flusso(payload(), ["1.35", "1.45"], t), updated=t)])
    assert len(runner.comandi) == n_prima
    crit = [p for k, p, _e in db.activity if k == "flusso_interrotto_senza_rest"]
    assert len(crit) == 1 and crit[0]["critical"] is True
    assert crit[0]["esposizione_eur"] and crit[0]["esposizione_eur"] > 0
    assert crit[0]["da_secondi"] is not None


def test_regola_unica_mike_nessuna_apertura_anche_col_rest_vivo(runner):
    """Senza posizione: nessuna lettura REST e nessun ingresso col flusso fermo."""
    db = FakeDB(params={"stake": 10})
    _scanner_nuovo(db)
    mk = FakeMarket()
    _rest_vivo(mk)
    run(db, mk, NOW, [row(_con_flusso(payload(), ["1.35", "1.45"]))])
    assert runner.comandi == [] and mk.calls == [] and db.trades == []


def test_regola_unica_mike_cash_out_dell_utente_col_flusso_fermo(runner):
    """La chiusura chiesta dall'utente: REST vivo = accettata (fonte REST
    scritta); REST muto = rifiutata col nome ``flusso_interrotto``."""
    db, mk = _posizione_aperta(runner)
    t = NOW + timedelta(seconds=2)
    _scanner_nuovo(db, calcolato=t)
    db.requests.append({"id": 1, "kind": "cashout", "payload": {"event_id": "E1"},
                        "status": "pending"})
    run(db, mk, t, [row(_con_flusso(payload(), ["1.35", "1.45"], t), updated=t)])
    assert db.requests[0]["status"] != "done"
    assert (db.requests[0]["result"] or {}).get("code") == "flusso_interrotto", db.requests[0]
    _rest_vivo(mk)
    t2 = NOW + timedelta(seconds=4)
    _scanner_nuovo(db, calcolato=t2)
    db.requests.append({"id": 2, "kind": "cashout", "payload": {"event_id": "E1"},
                        "status": "pending"})
    run(db, mk, t2, [row(_con_flusso(payload(), ["1.35", "1.45"], t2), updated=t2)])
    assert db.requests[1]["status"] == "done", db.requests[1]
    assert any(k == "ripiego_rest" and p.get("azione") == "cashout" for k, p, _e in db.activity)


def test_regola_unica_mike_execute_place_rifiuta_un_apertura_sui_prezzi_rest(runner):
    from datetime import timezone as _tz

    from Betfair.mike import engine as E
    from Betfair.mike import service as S
    from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import db_vuoto, info_vera

    leg = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                price=1.50, size=10.0, ref="under_entry-0-1", cycle_no=0,
                placed_at=NOW.timestamp())
    bk = E.Book(status="OPEN", best_back=1.50, back_size=100.0, best_lay=1.52, lay_size=100.0,
                inplay=False)
    db = db_vuoto()
    esito = S.execute_place(db=db, market=None, info=info_vera(), leg=leg, book=bk, mode="paper",
                            params=dict(S.C.merge_params(None)), now=NOW.astimezone(_tz.utc),
                            dry=False, feed_fresh=True, fonte_prezzi="rest_ripiego")
    assert esito == "cancelled" and runner.comandi == []
    assert any(k == "no_fill" and p.get("reason") == "flusso_interrotto"
               for k, p, _e in db.attivita)
