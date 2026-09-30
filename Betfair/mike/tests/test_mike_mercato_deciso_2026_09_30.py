"""30/09/2026 - Mike e il mercato DECISO dal punteggio (correzione).

Completa i test dell'indagine del 29/09
(``test_mike_indagine_mercato_deciso_2026_09_29.py``) sui punti della
correzione che quei test non fissano:
  * lo stato del mercato nello snapshot si legge dalla linea ANCORA IN GIOCO;
  * "partita chiusa" (regolamento) solo se e' CLOSED la linea in gioco: con 5+
    gol tutte e due sono decise e il 3,5 chiuso porta al regolamento come prima;
  * il ripiego REST non cerca la linea decisa;
  * consapevolezza: UNA riga ``mercato_deciso`` per linea nel diario.
Finti: ``payload``/``row`` di ``test_mike_feed`` e ``FakeDB``/``FakeMarket`` di
``test_mike_service`` (chiavi e tipi dello scanner e di ``mike/db.py``).
ASCII-only.
"""
from __future__ import annotations

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import row
from Betfair.mike.tests.test_mike_indagine_mercato_deciso_2026_09_29 import (
    OU35, OU45, SEL_O35, SEL_O45, SEL_U35, SEL_U45, _chiusure_over45, _evento_coperto,
    _payload, _snap)
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, run


def _libro_45_aperto():
    return {"market_id": OU45, "status": "OPEN", "inplay": True, "runners": [
        {"selection_id": SEL_U45, "name": "Under 4.5 Goals", "status": "ACTIVE",
         "back_price": 3.85, "back_size": 20.0, "lay_price": 4.8, "lay_size": 15.0},
        {"selection_id": SEL_O45, "name": "Over 4.5 Goals", "status": "ACTIVE",
         "back_price": 1.27, "back_size": 60.0, "lay_price": 1.35, "lay_size": 40.0}]}


def _libro_35_chiuso():
    return {"market_id": OU35, "status": "CLOSED", "inplay": True,
            "runners": [{"selection_id": SEL_U35, "status": "LOSER"},
                        {"selection_id": SEL_O35, "status": "WINNER"}]}


# ---------------------------------------------------------------------------
# 1) snapshot: lo stato del mercato dalla linea ancora in gioco
# ---------------------------------------------------------------------------
def test_snapshot_stato_del_mercato_dalla_linea_in_gioco():
    """4 gol, 3,5 CLOSED, 4,5 aperto: lo snapshot NON dice CLOSED. Con 3 gol
    (3,5 ancora in gioco) il 3,5 CLOSED resta CLOSED (confine)."""
    s4 = _snap(_payload([], stato35="CLOSED"))
    assert s4.goals == 4 and s4.market_status == "OPEN"
    s3 = _snap(_payload([], gol_casa=3, stato35="CLOSED"))
    assert s3.goals == 3 and s3.market_status == "CLOSED"


def test_linea_di_riferimento_segue_i_gol():
    assert F.linea_di_riferimento(None) == E.MARKET_OU35
    assert F.linea_di_riferimento(3) == E.MARKET_OU35
    assert F.linea_di_riferimento(4) == E.MARKET_OU45
    # 5+ gol: tutte e due decise, resta il 3,5 (regolamento come prima)
    assert F.linea_di_riferimento(5) == E.MARKET_OU35


# ---------------------------------------------------------------------------
# 2) servizio: regolamento solo se e' chiusa la linea in gioco
# ---------------------------------------------------------------------------
def test_con_4_gol_il_4_5_chiuso_porta_al_regolamento():
    """Confine: con 4 gol, se e' CLOSED anche il 4,5 (la linea in gioco) la
    partita e' finita e Mike va al regolamento (letture REST dei due libri)."""
    db = FakeDB(params={"stake": 10})
    _evento_coperto(db)
    mk = FakeMarket()
    mk.books[OU35] = _libro_35_chiuso()
    mk.books[OU45] = _libro_45_aperto()
    p = _payload([], stato35="CLOSED")
    p["ou"][1]["status"] = "CLOSED"
    run(db, mk, NOW, [row(p)])
    assert OU35 in mk.calls and OU45 in mk.calls, mk.calls
    assert "settle_first_ts" in db.events["E1"]["ctx"]


def test_con_5_gol_il_3_5_chiuso_porta_al_regolamento(runner):
    """Confine: con 5 gol le due linee sono decise (Under 3,5 perso, Over 4,5
    vinto): il 3,5 CLOSED porta al regolamento come prima della correzione, e
    nessun ordine parte."""
    db = FakeDB(params={"stake": 10})
    _evento_coperto(db)
    db.events["E1"]["ctx"]["last_goals"] = 5
    mk = FakeMarket()
    mk.books[OU35] = _libro_35_chiuso()
    mk.books[OU45] = _libro_45_aperto()
    run(db, mk, NOW, [row(_payload([], gol_casa=5, stato35="CLOSED"))])
    assert OU35 in mk.calls, mk.calls
    assert "settle_first_ts" in db.events["E1"]["ctx"]
    assert _chiusure_over45(runner) == []


def test_con_4_gol_e_3_5_chiuso_nessun_regolamento():
    """Il ramo di produzione del difetto: 3,5 CLOSED, 4,5 aperto -> nessuna
    lettura di regolamento, nessun ``settle_first_ts``."""
    db = FakeDB(params={"stake": 10})
    _evento_coperto(db)
    mk = FakeMarket()
    mk.books[OU35] = _libro_35_chiuso()
    mk.books[OU45] = _libro_45_aperto()
    run(db, mk, NOW, [row(_payload([], stato35="CLOSED"))])
    assert "settle_first_ts" not in db.events["E1"]["ctx"]
    assert db.events["E1"]["state"] != "SETTLING"


# ---------------------------------------------------------------------------
# 3) ripiego REST: la linea decisa non si cerca
# ---------------------------------------------------------------------------
def test_ripiego_rest_non_cerca_la_linea_decisa():
    """Senza elenco dei fermi (giro dello scanner bloccato) il ripiego legge le
    linee di Mike: con 4 gol il 3,5 e' deciso e NON si legge nemmeno (anche se
    un libro dicesse OPEN). Con 3 gol si leggono tutte e due (confine)."""
    info = F.event_info("E1", _payload([]))
    mk = FakeMarket()
    mk.books[OU35] = {**_libro_45_aperto(), "market_id": OU35}
    mk.books[OU45] = _libro_45_aperto()
    out = S._books_ripiego_rest(mk, info, (), NOW.timestamp(), con_tetto=False, goals=4)
    assert set(out) == {E.MARKET_OU45} and mk.calls == [OU45]
    mk.calls.clear()
    out3 = S._books_ripiego_rest(mk, info, (), NOW.timestamp(), con_tetto=False, goals=3)
    assert set(out3) == {E.MARKET_OU35, E.MARKET_OU45}


# ---------------------------------------------------------------------------
# 4) consapevolezza: una riga ``mercato_deciso`` per linea
# ---------------------------------------------------------------------------
def test_mercato_deciso_scritto_una_volta_con_chiavi_e_tipi():
    db = FakeDB(params={"stake": 10})
    _evento_coperto(db)
    mk = FakeMarket()
    from datetime import timedelta
    run(db, mk, NOW, [row(_payload([OU35]))])
    t = NOW + timedelta(seconds=3)
    run(db, mk, t, [row(_payload([OU35]), updated=t)])
    righe = [(p, e) for k, p, e in db.activity if k == "mercato_deciso"]
    assert len(righe) == 1, righe
    p, eid = righe[0]
    assert eid == "E1"
    assert p["market"] == E.MARKET_OU35 and p["market_id"] == OU35
    assert p["goals"] == 4 and isinstance(p["goals"], int)
    assert p["stato_mercato"] == "SUSPENDED"
    assert p["esito"] == {"OU35|UNDER": "persa"}
    assert isinstance(p["state"], str)
    assert db.events["E1"]["ctx"]["linee_decise"] == [E.MARKET_OU35]


def test_mercato_deciso_con_5_gol_scrive_anche_il_4_5():
    db = FakeDB(params={"stake": 10})
    _evento_coperto(db)
    run(db, FakeMarket(), NOW, [row(_payload([], gol_casa=5))])
    righe = [p for k, p, _e in db.activity if k == "mercato_deciso"]
    assert [p["market"] for p in righe] == [E.MARKET_OU35, E.MARKET_OU45]
    assert righe[1]["esito"] == {"OU45|OVER": "vinta"}


# ---------------------------------------------------------------------------
# 5) il controllo di condotta M1 del banco
# ---------------------------------------------------------------------------
def _m1(p, vivo=None, rifiuti=(), invecchiata=False):
    from Betfair.mike import certificazione as CERT

    sol = {}
    if vivo is None:
        vivo = F.flusso_esito(row(p), None, NOW.timestamp()).vivo   # la lettura di Mike
    out = CERT.verifica_mercato_deciso(p, vivo, list(rifiuti), None,
                                       riga_invecchiata=invecchiata, sollecitati=sol)
    return out, sol.get("M1", 0)


def test_m1_e_nell_elenco_dei_controlli():
    from Betfair.mike import certificazione as CERT

    assert "M1" in {c for c, _r in CERT.elenco_controlli()}
    assert "M1" in {c for c, _r in CERT.mai_sollecitati({})}


def test_m1_sano_con_la_correzione_sulla_riga_vera_del_quarto_gol():
    out, n = _m1(_payload([OU35]))
    assert n == 1 and out == []


def test_m1_scatta_se_il_bot_dichiara_fermo_o_rifiuta_sulla_linea_viva():
    out, n = _m1(_payload([OU35]), vivo=False)
    assert n == 1 and [v.codice for v in out] == ["M1"]
    out, n = _m1(_payload([OU35]), vivo=True, rifiuti=[OU45])
    assert n == 1 and [v.codice for v in out] == ["M1"] and "feed_stantio" in out[0].dettaglio


def test_m1_scatta_se_il_servizio_va_al_regolamento_con_la_linea_viva():
    from Betfair.mike import certificazione as CERT

    p = _payload([], stato35="CLOSED")
    sol = {}
    out = CERT.verifica_mercato_deciso(p, True, [], None, sollecitati=sol, in_regolamento=True)
    assert sol == {"M1": 1} and [v.codice for v in out] == ["M1"]
    assert "regolamento" in out[0].dettaglio
    # confine: anche il 4,5 CHIUSO = partita finita, il regolamento e' giusto
    p["ou"][1]["status"] = "CLOSED"
    sol = {}
    assert CERT.verifica_mercato_deciso(p, True, [], None, sollecitati=sol,
                                        in_regolamento=True) == [] and sol == {}


def test_m1_nessun_caso_ai_confini():
    # la linea IN GIOCO e' ferma davvero: bloccare e' giusto
    assert _m1(_payload([OU45]), vivo=False) == ([], 0)
    # 3 gol: nessuna linea decisa
    assert _m1(_payload([OU35], gol_casa=3), vivo=False) == ([], 0)
    # 5 gol: tutte e due decise, niente di vivo da difendere
    assert _m1(_payload([], gol_casa=5), vivo=False) == ([], 0)
    # riga invecchiata dallo scenario (feed stantio vero)
    assert _m1(_payload([OU35]), vivo=False, invecchiata=True) == ([], 0)


def test_nessun_mercato_deciso_sotto_la_linea():
    db = FakeDB(params={"stake": 10})
    _evento_coperto(db)
    db.events["E1"]["ctx"]["last_goals"] = 3
    run(db, FakeMarket(), NOW, [row(_payload([], gol_casa=3))])
    assert "mercato_deciso" not in db.kinds()
    assert C  # import usato dai finti condivisi
