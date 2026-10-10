"""W1-C2 - correzioni dopo la revisione indipendente (09/10/2026).

G3 seme da listCurrentOrders e verifica con mb/ml dello stream; M1 regressioni
rifiutate; M2 tetto che non cambia il P&L in silenzio; M3 indizi senza crescita;
consegna ai consumatori mai fuori ordine; ombra senza falsi
``specchio_senza_conto`` quando il seme manca; tolleranza dell'abbinato oltre il
centesimo. Ogni test era rosso sul codice di ``5b958ba7`` (referto par. 10).
Ordini VERI (``CurrentOrder`` dal JSON di Betfair). ASCII-only.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, List, Optional, Sequence


from Betfair.nucleo.ordini import attribuzione as A
from Betfair.nucleo.ordini import libro_conto as L
from Betfair.nucleo.ordini import riconciliazione as R
from Betfair.nucleo.ordini.tests.test_c2_aiuti import (AWAY, HOME, MKT, FlussoFinto, correnti,
                                                       dal_conto, ordine_json)


class ContoRest:
    """Una ``SorgenteOrdiniCorrenti``: la risposta di ``listCurrentOrders`` (JSON di
    Betfair) trasformata in ``CurrentOrder`` dalla libreria vera."""

    def __init__(self, *ordini: dict, rotto: bool = False) -> None:
        self.ordini = list(ordini)
        self.rotto = rotto
        self.chiamate = 0

    def ordini_correnti(self, market_ids: Optional[Sequence[str]] = None) -> List[Any]:
        self.chiamate += 1
        if self.rotto:
            raise ConnectionError("listCurrentOrders KO")
        return correnti(*self.ordini)


def _odds(lib: L.LibroConto, runner=(HOME, AWAY)) -> None:
    lib.imposta_mercato(MKT, runner=list(runner), tipo_scommessa="ODDS", vincitori=1)


# --------------------------------------------------------------------------- G3
def test_g3_senza_seme_il_completo_manca_e_lo_si_dice():
    """Lo stream (nuova sottoscrizione) porta solo l'EXECUTABLE; l'ordine gia'
    abbinato per intero e' solo in listCurrentOrders."""
    vivo = ordine_json("1", "BACK", 0.0, 2.0, residuo=5.0, csr="mike", cor="mike-t1")
    completo = ordine_json("2", "BACK", 10.0, 3.0, csr="mike", cor="mike-t2")
    lib = L.LibroConto()
    _odds(lib)
    lib.collega_live(FlussoFinto((dal_conto(vivo),)))
    c = lib.calcolo_posizione(MKT, "live")
    assert "seme_non_fatto" in c.motivi and not lib.seme_fatto()
    assert c.posizione.se_vince[HOME] == 0.0               # il +20 manca: DETTO, non nascosto
    rest = ContoRest(vivo, completo)
    assert lib.semina(rest, ricevuto_ms=500) == 2
    c = lib.calcolo_posizione(MKT, "live")
    assert lib.seme_fatto() and "seme_non_fatto" not in c.motivi
    assert c.posizione.se_vince == {HOME: 20.0, AWAY: -10.0}


def test_g3_collega_con_seme_e_riconnessione_senza_ripresa():
    completo = ordine_json("2", "BACK", 10.0, 3.0, csr="mike", cor="mike-t2")
    rest = ContoRest(completo)
    lib = L.LibroConto()
    lib.collega_live(FlussoFinto(), correnti=rest)
    assert lib.seme_fatto() and rest.chiamate == 1 and lib.ordine("2", "live").abbinato == 10.0
    lib.riconnesso(con_ripresa=True, correnti=rest)
    assert rest.chiamate == 1 and lib.seme_fatto()        # con ripresa: niente da rifare
    lib.riconnesso(con_ripresa=False)
    assert not lib.seme_fatto()
    lib.riconnesso(con_ripresa=False, correnti=rest)
    assert lib.seme_fatto() and rest.chiamate == 2


def test_g3_seme_ko_resta_da_fare_e_si_dice(caplog):
    lib = L.LibroConto()
    with caplog.at_level(logging.WARNING):
        assert lib.semina(ContoRest(rotto=True)) == -1
    assert not lib.seme_fatto() and lib.stato()["conti"]["semi_ko"] == 1
    assert "seme" in caplog.text


def test_g3_mb_ml_dello_stream_segnalano_l_abbinato_mancante(caplog):
    lib = L.LibroConto()
    _odds(lib)
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 4.0, 2.0, residuo=1.0, csr="mike",
                                          cor="mike-t1")))
    # OrderRunnerChange: mb = abbinato del conto per prezzo (anche i completi di prima)
    with caplog.at_level(logging.WARNING):
        m = lib.verifica_abbinato(MKT, HOME, 0.0, mb=[[2.0, 4.0], [3.0, 10.0]], ml=[])
    assert m == {"back": 10.0} and "abbinato_mancante" in lib.calcolo_posizione(MKT, "live").motivi
    assert "seme mancante" in caplog.text
    assert lib.verifica_abbinato(MKT, HOME, 0.0, mb=[[2.0, 4.0]], ml=None) is None
    assert "abbinato_mancante" not in lib.calcolo_posizione(MKT, "live").motivi


def test_g3_ombra_senza_seme_non_inventa_specchio_senza_conto():
    rec = R.RiconciliatoreOmbra(modo="live")
    spec = [{"bet_id": "77", "client_order_ref": "awlq7", "size_matched": 2.0,
             "status": "EXECUTABLE", "source": "runner", "mode": "live"}]
    diario = [{"tipo": "inviato", "ref": "omega-t9", "mode": "live"},
              {"tipo": "ordine", "ref": "omega-t9", "cor": "abcdef0123456-9"}]
    for _ in range(3):
        ref = rec.giro([], spec, diario=diario, conto_completo=False)
        assert ref.per_tipo("specchio_senza_conto") == ()
        assert [d.tipo for d in ref.per_tipo("seme_non_fatto")] == ["seme_non_fatto"]
        assert ref.per_tipo("in_volo_non_trovato") == ()
        assert [d.ref for d in ref.per_tipo("in_volo_da_verificare")] == ["omega-t9"]
    # col seme: il primo giro e' il PRIMO (i giri senza seme non contano)
    ref = rec.giro([], spec, conto_completo=True)
    assert [d.dettagli["giri"] for d in ref.per_tipo("specchio_senza_conto")] == [1]


# --------------------------------------------------------------------------- M1
def test_m1_seme_piu_vecchio_consegnato_dopo_non_fa_regredire(caplog):
    lib = L.LibroConto()
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 10.0, 2.0, csr="omega", cor="omega-t1"),
                              ricevuto_ms=2000))
    with caplog.at_level(logging.WARNING):
        lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 4.0, 2.0, residuo=6.0, csr="omega",
                                              cor="omega-t1"), ricevuto_ms=2500))
    o = lib.ordine("1", "live")
    assert (o.abbinato, o.residuo, o.stato) == (10.0, 0.0, "abbinato")
    assert lib.stato()["conti"]["regressioni"] == 1 and "regressione" in caplog.text


def test_m1_annullo_di_betfair_puo_ridurre_l_abbinato():
    lib = L.LibroConto()
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 10.0, 2.0, csr="omega", cor="omega-t1"), 1))
    voided = ordine_json("1", "BACK", 6.0, 2.0, csr="omega", cor="omega-t1")
    voided["sizeVoided"] = 4.0
    lib.ricevi_live(dal_conto(voided, 2))
    assert lib.ordine("1", "live").abbinato == 6.0 and lib.stato()["conti"]["regressioni"] == 0


def test_m1_duplicati_e_messaggio_vecchio_in_coda():
    lib = L.LibroConto()
    e = dal_conto(ordine_json("1", "BACK", 0.0, 2.0, csr="omega", cor="omega-t1", residuo=5.0), 1)
    c = dal_conto(ordine_json("1", "BACK", 5.0, 2.0, csr="omega", cor="omega-t1"), 2)
    for o in (e, c, c, e):
        lib.ricevi_live(o)
    assert lib.ordine("1", "live").stato == "abbinato" and len(lib.ordini(MKT, "live")) == 1
    assert lib.stato()["conti"]["fuori_ordine"] == 1


# --------------------------------------------------------------------------- M2
def test_m2_tetto_su_mercato_aperto_non_cambia_il_pnl(caplog):
    lib = L.LibroConto(max_ordini=2)
    _odds(lib)
    with caplog.at_level(logging.WARNING):
        for i, ms in enumerate((1000, 2000, 3000)):
            lib.ricevi_live(dal_conto(ordine_json(str(i), "BACK", 10.0, 2.0, csr="omega",
                                                  cor="omega-t1"), ricevuto_ms=ms))
    assert len(lib.ordini(MKT, "live")) == 2
    c = lib.calcolo_posizione(MKT, "live")
    assert c.posizione.se_vince[HOME] == 30.0 and c.posizione.abbinato_back[HOME] == 30.0
    assert "ordini_riassunti" in c.motivi and "APERTI" in caplog.text
    assert c.posizione.se_vince_per_autore["omega"][HOME] == 30.0


def test_m2_tetto_dimentica_prima_i_mercati_chiusi():
    lib = L.LibroConto(max_ordini=2)
    lib.ricevi_live(dal_conto(ordine_json("c", "BACK", 1.0, 2.0, market="1.900", csr="mike",
                                          cor="mike-t1"), 9000))
    lib.imposta_mercato("1.900", chiuso=True)
    lib.ricevi_live(dal_conto(ordine_json("a1", "BACK", 1.0, 2.0, csr="mike", cor="mike-t2"), 1))
    lib.ricevi_live(dal_conto(ordine_json("a2", "BACK", 1.0, 2.0, csr="mike", cor="mike-t3"), 2))
    assert lib.ordine("c", "live") is None                 # il chiuso, anche se piu' recente
    assert {o.bet_id for o in lib.ordini(MKT, "live")} == {"a1", "a2"}
    assert lib.stato()["conti"]["dimenticati_aperti"] == 0


# --------------------------------------------------------------------------- M3
def test_m3_indizi_senza_duplicati_ne_crescita():
    lib = L.LibroConto(max_indizi=10)
    for _ in range(1000):
        lib.aggiungi_indizi("7", [A.Indizio("tabella", "omega_trades")])
    assert lib._indizi["7"] == (A.Indizio("tabella", "omega_trades"),)
    for i in range(100):
        lib.aggiungi_indizi(f"x{i}", [A.Indizio("tabella", "mike_trades")])
    assert len(lib._indizi) <= 10
    lib.ricevi_live(dal_conto(ordine_json("8", "BACK", 1.0, 2.0, csr="live")))
    lib.aggiungi_indizi("8", [A.Indizio("tabella", "omega_trades")])
    assert "8" in lib._indizi
    lib.dimentica_mercato(MKT)
    assert "8" not in lib._indizi


# ------------------------------------------------------------ consegna in ordine
def test_consegna_ai_consumatori_mai_una_versione_vecchia_dopo_una_nuova():
    """Due scrittori sullo stesso ordine: il primo consegna la sua versione
    mentre il secondo ne scrive una piu' nuova. Prima la consegna v1 arrivava DOPO
    la v2; adesso le consegne sono in fila e sempre dello stato piu' recente."""
    lib = L.LibroConto()
    A.regole_di_oggi()
    v1 = dal_conto(ordine_json("1", "BACK", 1.0, 2.0, residuo=4.0, csr="omega", cor="omega-t1"), 1)
    v2 = dal_conto(ordine_json("1", "BACK", 3.0, 2.0, residuo=2.0, csr="omega", cor="omega-t1"), 2)
    lib.ricevi_live(dal_conto(ordine_json("0", "BACK", 1.0, 2.0, csr="omega", cor="omega-t0"), 0))
    sblocca, primo = threading.Event(), threading.Event()
    visti: List[float] = []

    def cb(o):
        if o.bet_id != "1":
            return
        if not primo.is_set():
            primo.set()
            assert sblocca.wait(5)
        visti.append(o.abbinato)

    lib.aggiungi_consumatore(cb)
    a = threading.Thread(target=lib.ricevi_live, args=(v1,))
    a.start()
    assert primo.wait(5)
    b = threading.Thread(target=lib.ricevi_live, args=(v2,))
    b.start()
    time.sleep(0.3)
    sblocca.set()
    a.join()
    b.join()
    assert visti == sorted(visti) and visti[-1] == 3.0, visti


# ------------------------------------------------------------ tolleranza R1
def test_tolleranza_abbinato_oltre_un_centesimo_e_divergenza():
    from Betfair.nucleo.ordini.tests.test_c2_riconciliazione import riga_specchio

    js = [ordine_json("1", "BACK", 3.0, 2.0, residuo=1.0, csr="live"),
          ordine_json("2", "BACK", 3.0, 2.0, residuo=1.0, csr="live")]
    conto = [L.ordine_da_corrente(c, ricevuto_ms=1) for c in correnti(*js)]
    sp = [riga_specchio("1", matched=2.98), riga_specchio("2", matched=2.995)]
    ref = R.RiconciliatoreOmbra(modo="live").giro(conto, sp)
    assert {d.bet_id for d in ref.per_tipo("numeri_diversi")} == {"1"}


# ------------------------------------------------------------ dal revisore
def test_stress_concorrenza_1200_ordini():
    lib = L.LibroConto()
    A.regole_di_oggi()
    errori: List[BaseException] = []

    def w(k):
        try:
            for i in range(300):
                lib.ricevi_live(dal_conto(ordine_json(f"{k}-{i}", "BACK", 1.0, 2.0, csr="omega",
                                                      cor="omega-t1"), ricevuto_ms=i + 1))
        except BaseException as ex:  # noqa: BLE001
            errori.append(ex)

    def r():
        try:
            for _ in range(100):
                lib.posizione(MKT, "live")
                lib.ordini(MKT)
        except BaseException as ex:  # noqa: BLE001
            errori.append(ex)

    ts = [threading.Thread(target=w, args=(k,)) for k in range(4)] + \
         [threading.Thread(target=r) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errori and len(lib.ordini(MKT, "live")) == 1200


def test_somma_per_autore_contro_totale():
    rnd = random.Random(1)
    peggio = 0.0
    for _ in range(200):
        lib = L.LibroConto()
        _odds(lib)
        for i in range(6):
            csr, cor = rnd.choice([("omega", "omega-t1"), ("mike", "mike-t2"), ("safe", "safe-t3")])
            lib.ricevi_live(dal_conto(ordine_json(
                str(i), rnd.choice(["BACK", "LAY"]), round(rnd.uniform(.5, 20), 2),
                round(rnd.uniform(1.2, 6), 2), csr=csr, cor=cor, sel=rnd.choice([HOME, AWAY])),
                ricevuto_ms=i + 1))
        p = lib.posizione(MKT, "live")
        for s in (HOME, AWAY):
            peggio = max(peggio, abs(sum(v[s] for v in p.se_vince_per_autore.values())
                                     - p.se_vince[s]))
    assert peggio <= 0.015                                 # 3 autori x mezzo centesimo


# ------------------------------------------- verifica del coordinatore (09/10)
# Ogni ramo delle correzioni G1-G3/M1-M5 ha un test proprio (e una mutazione in
# ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni.py).
def test_m1_abbinato_che_cala_fra_due_eseguibili_si_rifiuta():
    lib = L.LibroConto()
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 6.0, 2.0, residuo=4.0, csr="omega",
                                          cor="omega-t1"), 1))
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 4.0, 2.0, residuo=6.0, csr="omega",
                                          cor="omega-t1"), 2))
    o = lib.ordine("1", "live")
    assert (o.abbinato, o.residuo) == (6.0, 4.0)
    assert lib.stato()["conti"]["regressioni"] == 1


def test_m1_abbinato_che_cala_fra_due_completi_senza_void_si_rifiuta():
    lib = L.LibroConto()
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 10.0, 2.0, csr="omega", cor="omega-t1"), 1))
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 8.0, 2.0, annullato=2.0, csr="omega",
                                          cor="omega-t1"), 2))
    assert lib.ordine("1", "live").abbinato == 10.0
    assert lib.stato()["conti"]["regressioni"] == 1


def test_m1_completo_che_torna_eseguibile_a_parita_di_abbinato_si_rifiuta():
    lib = L.LibroConto()
    # annullato dopo un parziale: completo, abbinato 5
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 5.0, 2.0, annullato=5.0, csr="omega",
                                          cor="omega-t1"), 1))
    # un seme REST piu' vecchio: ancora eseguibile, stesso abbinato
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 5.0, 2.0, residuo=5.0, csr="omega",
                                          cor="omega-t1"), 2))
    o = lib.ordine("1", "live")
    assert (o.stato, o.residuo) == ("annullato", 0.0)
    assert lib.stato()["conti"]["regressioni"] == 1


def test_g1_specchio_bot_tennis_non_toglie_il_provvisorio():
    """La riga ``bot:tennis`` che R1 scrive per il terminale tennis non dice di
    piu' del ref: l'ordine resta provvisorio."""
    o = dal_conto(ordine_json("1", "BACK", 1.0, 2.0, csr="tennis", cor="h-1"))
    a = A.attribuisci(o, [A.Indizio("specchio", "bot:tennis")])
    assert (a.autore, a.provvisoria, a.fonte) == ("sconosciuto", True, "riferimenti")


def test_g1_riga_utente_di_mike_conferma_il_terminale():
    o = dal_conto(ordine_json("1", "BACK", 1.0, 2.0, csr="live", cor="h-1"))
    a = A.attribuisci(o, [A.indizio_da_riga_bot("mike_trades", {"role": "utente"})])
    assert (a.autore, a.provvisoria) == ("desktop", False)


def test_g1_ack_del_desktop_e_un_indizio_dell_utente():
    ind = A.indizio_ack_desktop(" 77 ")
    assert ind == A.Indizio("utente", "ack_desktop:77")
    o = dal_conto(ordine_json("77", "BACK", 1.0, 2.0, csr="tennis", cor="h-1"))
    assert A.attribuisci(o, [ind]).autore == "desktop"


def test_g1_riga_di_coda_del_risk_non_e_dell_utente():
    assert A.indizi_da_riga_coda({"action": "place", "client_ref": "risk3cp1", "params": {}}) == (
        A.Indizio("coda", "rischio:risk3cp1"),)


class _Rotto:
    """Un oggetto che non e' un CurrentOrder (lettura REST corrotta)."""

    bet_id = "rotto"


class _ContoMisto:
    def ordini_correnti(self, market_ids=None):
        return [_Rotto()] + correnti(ordine_json("2", "BACK", 10.0, 3.0, csr="mike", cor="mike-t2"))


def test_g3_seme_con_un_ordine_illeggibile_tiene_gli_altri():
    lib = L.LibroConto()
    assert lib.semina(_ContoMisto()) == 2
    assert lib.seme_fatto() and lib.ordine("2", "live").abbinato == 10.0
    assert lib.stato()["conti"]["scartati"] == 1


def test_g3_riconnessione_senza_ripresa_toglie_il_seme_anche_senza_sorgente():
    lib = L.LibroConto()
    lib.semina(ContoRest())
    assert lib.seme_fatto()
    lib.riconnesso(con_ripresa=False)
    assert not lib.seme_fatto()
    assert "seme_non_fatto" in lib.calcolo_posizione(MKT, "live").motivi


def test_g3_mancanza_su_altra_selezione_o_lato_lay():
    lib = L.LibroConto()
    _odds(lib)
    lib.ricevi_live(dal_conto(ordine_json("1", "LAY", 2.0, 3.0, sel=AWAY, csr="mike", cor="mike-t1")))
    assert lib.verifica_abbinato(MKT, AWAY, 0.0, mb=None, ml=[[3.0, 2.0]]) is None
    assert lib.verifica_abbinato(MKT, AWAY, 0.0, mb=None, ml=[[3.0, 2.0], [4.0, 1.5]]) == {"lay": 1.5}
    assert lib.verifica_abbinato(MKT, HOME, 0.0, mb=[[2.0, 1.0]], ml=None) == {"back": 1.0}


def test_m2_ordine_terminale_senza_abbinato_su_mercato_aperto():
    """Un annullato senza abbinato dimenticato dal tetto non entra nel riassunto
    (niente divisione per zero, P&L invariato)."""
    lib = L.LibroConto(max_ordini=1)
    _odds(lib)
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 0.0, 2.0, annullato=2.0, csr="mike",
                                          cor="mike-t1"), 1))
    lib.ricevi_live(dal_conto(ordine_json("2", "BACK", 4.0, 2.0, csr="mike", cor="mike-t2"), 2))
    c = lib.calcolo_posizione(MKT, "live")
    assert c.posizione.se_vince[HOME] == 4.0 and "ordini_riassunti" not in c.motivi


def test_dimentica_mercato_toglie_riassunti_mancanze_e_info():
    lib = L.LibroConto(max_ordini=1)
    _odds(lib)
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 4.0, 2.0, csr="mike", cor="mike-t1"), 1))
    lib.ricevi_live(dal_conto(ordine_json("2", "BACK", 4.0, 2.0, csr="mike", cor="mike-t2"), 2))
    lib.verifica_abbinato(MKT, HOME, 0.0, mb=[[2.0, 50.0]], ml=None)
    assert {"ordini_riassunti", "abbinato_mancante"} <= set(lib.calcolo_posizione(MKT, "live").motivi)
    lib.dimentica_mercato(MKT)
    c = lib.calcolo_posizione(MKT, "live")
    assert c.posizione.abbinato_back == {} and not {"ordini_riassunti", "abbinato_mancante"} & set(c.motivi)
    assert "tipo_ignoto" in c.motivi                        # anche runner/tipo dimenticati


def test_imposta_mercato_vincitori_e_tipo_dal_book():
    lib = L.LibroConto()
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 4.0, 2.0, csr="mike", cor="mike-t1")))
    lib.imposta_mercato(MKT, runner=[HOME, AWAY], tipo_scommessa="ODDS", vincitori=2)
    assert "vincitori:2" in lib.calcolo_posizione(MKT, "live").motivi
    lib.imposta_mercato(MKT, vincitori=1)
    assert lib.posizione(MKT, "live").se_vince == {HOME: 4.0, AWAY: -4.0}
    lib.imposta_mercato(MKT, tipo_scommessa="LINE")
    # decisione 5 dell'utente (10/10): il "se vince" c'e' anche sui mercati LINE
    # (quota 2,0: qui il prezzo e' gia' 2,0), con la qualita' per_selezione
    c = lib.calcolo_posizione(MKT, "live")
    assert c.posizione.se_vince == {HOME: 4.0, AWAY: -4.0}
    assert c.qualita == "per_selezione" and "linea_a_quota_2" in c.motivi


def test_g2_tipo_non_odds_dichiarato():
    from Betfair.nucleo.ordini import pnl_mercato as P
    from Betfair.nucleo.ordini.contratto import OrdineConto

    o = OrdineConto("1", MKT, HOME, 0.0, "back", 2.0, 4.0, 4.0, 0.0, 2.0, "abbinato", "mike",
                    None, "live", 1)  # type: ignore[arg-type]
    c = P.calcola(MKT, "live", [o], runner=[HOME, AWAY], tipo_scommessa="LINE")
    assert not c.supportato and "tipo_non_supportato:LINE" in c.motivi
