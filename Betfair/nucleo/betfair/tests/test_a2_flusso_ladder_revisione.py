"""W1-A2 - gestore dei flussi e ladder: le prove della REVISIONE indipendente (09/10).

Incorporati (con nomi nostri e asserzioni sul comportamento CORRETTO) i test del
revisore (``test_rev_ladder_flusso.py`` L1, L2, F1; ``test_rev_sopravvissute.py`` X15,
X18) e le prove delle correzioni: un errore di pubblicazione non perde il mercato ne'
il lotto, meta in ritardo, chiusura sull'ULTIMO book ricevuto, riparo dopo invii
saltati dal canale, nessuna rete sotto i lock della consegna (niente deadlock),
backoff azzerato, watchdog, eventi del contratto, potatura dei book.
"""
from __future__ import annotations

import copy
import json
import random
import threading
import time
from typing import Any, Dict, List, Optional

import pytest

from Betfair.nucleo.betfair import flusso as F
from Betfair.nucleo.betfair import ladder as L
from Betfair.nucleo.betfair import profili as P
from Betfair.stream.recorder import serialize_book
from Betfair.stream.valuta import CambioGbpEur

from .test_a2_finti import SessioneFinta, attendi, server_stream  # noqa: F401
from .test_a2_flusso import CAMBIO, MODELLO, PT0, _gestore, _ids, _risposta_immagine, immagine
from .test_a2_ladder import MID, Libri, Orologio


def _meta2(mid: str) -> Optional[L.MetaLadder]:
    return L.MetaLadder("35760084", "MATCH_ODDS", "Esito finale", {}) if mid in (MID, "1.777") else None


def _due_mercati():
    lb = Libri()
    a = lb.immagine()
    b = copy.deepcopy(a)
    b.market_id = "1.777"
    return lb, a, b


# ---------------------------------------------------------------------------
# ladder
# ---------------------------------------------------------------------------
def test_errore_di_pubblicazione_non_perde_lo_stato_ne_il_resto_del_lotto():
    """(L1) Il canale solleva UNA volta sul primo mercato: l'altro esce nello stesso
    giro; il primo esce al giro dopo anche senza book nuovi."""
    _lb, a, b = _due_mercati()
    ora = Orologio()
    pub: List[str] = []
    stato = {"rompi": True}

    def pubblica(t: str, riga: Dict[str, Any]) -> None:
        if stato["rompi"] and riga["market_id"] == MID:
            stato["rompi"] = False
            raise RuntimeError("canale KO una volta")
        pub.append(riga["market_id"])
    lad = L.LadderEvento(L.profilo_ladder("calcio", {}), meta=_meta2, pubblica=pubblica, orologio=ora)
    lad.consumatore(a)
    lad.consumatore(b)
    prossima = lad.esegui_scaduti()
    assert pub == ["1.777"] and prossima is not None and lad.conti["errori"] == 1
    ora.t += 1.0
    lad.esegui_scaduti()
    assert sorted(pub) == sorted([MID, "1.777"])


def test_meta_che_arriva_dopo_il_book_riaccende_la_pubblicazione():
    """(L2) La sessione impara l'evento DOPO il primo book: il mercato non si perde."""
    lb = Libri()
    ora = Orologio()
    pub: List[str] = []
    pronto = {"si": False}
    lad = L.LadderEvento(L.profilo_ladder("calcio", {}),
                         meta=lambda m: _meta2(m) if pronto["si"] else None,
                         pubblica=lambda t, r: pub.append(r["market_id"]), orologio=ora)
    lad.consumatore(lb.immagine())
    prossima = lad.esegui_scaduti()
    assert pub == [] and prossima == pytest.approx(ora.t + L.RIPROVA_META_S)
    pronto["si"] = True
    for _ in range(5):
        ora.t += 1.0
        lad.esegui_scaduti()
    assert pub == [MID]


def test_meta_assente_non_fa_girare_a_vuoto_il_thread():
    lb = Libri()
    lad = L.LadderEvento(L.profilo_ladder("calcio", {}), meta=lambda m: None,
                         pubblica=lambda t, r: None)
    lad.avvia()
    try:
        lad.consumatore(lb.immagine())
        time.sleep(0.6)
        assert 1 <= lad.conti["senza_meta"] <= 10            # ~ogni 0,2 s, non migliaia
    finally:
        lad.ferma()


def test_chiusura_calcio_sull_ultimo_book_RICEVUTO_anche_se_fuso():
    """Il recorder di oggi serializza OGNI book: la chiusura marca l'ultimo ricevuto,
    anche se il ladder non l'aveva ancora pubblicato (fuso nei 20 ms)."""
    lb = Libri()
    ora = Orologio()
    pub: List[Dict[str, Any]] = []
    lad = L.LadderEvento(L.profilo_ladder("calcio", {}), meta=_meta2,
                         pubblica=lambda t, r: pub.append(r), orologio=ora)
    lad.consumatore(lb.immagine())
    lad.esegui_scaduti()
    ora.t += 0.005
    ultimo = lb.prezzo(1.9, 7.0)
    lad.consumatore(ultimo)                                  # fuso: non pubblicato
    chiuso = lb.stato("CLOSED")
    lad.consumatore(chiuso)
    ora.t += 0.05
    lad.esegui_scaduti()
    atteso = serialize_book(ultimo, 10)
    atteso["status"] = "CLOSED"
    assert pub[-1]["status"] == "CLOSED"
    assert pub[-1]["ladder"]["selections"] == L.payload_ladder(atteso, {}, 10, 3)["selections"]


def test_invii_saltati_dal_canale_ripubblicano_tutto():
    """(M5a) ``local_channel`` salta il fotogramma a un client indietro (oltre 64
    invii in volo): il contatore cresce e il ladder ripubblica i mercati, al massimo
    ogni ``RIPARO_MIN_S``."""
    _lb, a, b = _due_mercati()
    ora = Orologio()
    pub: List[str] = []
    saltati = {"n": 0}
    lad = L.LadderEvento(L.profilo_ladder("calcio", {}), meta=_meta2,
                         pubblica=lambda t, r: pub.append(r["market_id"]),
                         saltati=lambda: saltati["n"], orologio=ora)
    lad.consumatore(a)
    lad.consumatore(b)
    lad.esegui_scaduti()
    assert len(pub) == 2
    ora.t += 1.0
    lad.esegui_scaduti()
    assert len(pub) == 2                                     # niente saltato: niente di nuovo
    saltati["n"] = 3
    ora.t += 1.0
    lad.esegui_scaduti()
    assert len(pub) == 4 and lad.conti["ripari"] == 1
    saltati["n"] = 5
    ora.t += 0.1                                             # sotto RIPARO_MIN_S: si aspetta
    lad.esegui_scaduti()
    assert len(pub) == 4
    ora.t += 1.0
    lad.esegui_scaduti()
    assert len(pub) == 6 and lad.conti["ripari"] == 2


# ---------------------------------------------------------------------------
# flusso: concorrenza
# ---------------------------------------------------------------------------
def test_consegna_non_si_blocca_se_una_connessione_tiene_il_suo_lock():
    """(F1) Una connessione lenta tiene il SUO lock; un ``imposta_mercati`` aspetta
    quella connessione: i book delle ALTRE connessioni arrivano lo stesso."""
    g = F.GestoreFlussi(SessioneFinta(), P.profilo("runner_calcio", {}),
                        cambio=CambioGbpEur(fisso=CAMBIO))
    visti: List[Any] = []
    g.aggiungi_consumatore(visti.append)
    g.avvia()
    book = Libri().immagine()
    c = F._Connessione(g, 1, {"1.1"})                        # il thread NON parte
    c.stream = type("S", (), {"running": True})()
    c._sottoscrivi = lambda s, ripresa: None
    g._connessioni = [c]
    c._lock.acquire()
    t = threading.Thread(target=lambda: g.imposta_mercati(["1.1", "1.2"]), daemon=True)
    t.start()
    time.sleep(0.3)
    g._inoltra([book])
    try:
        assert attendi(lambda: len(visti) == 1, secondi=2.0)
    finally:
        c._lock.release()
        t.join(2)
        g.ferma()
    assert not t.is_alive()


def test_consegna_non_aspetta_il_lock_del_gestore():
    """Chiunque tenga il lock del GESTORE (piano, manutenzione, chiusure) non ferma
    la consegna dei book: i consumatori si leggono da una lista sostituita per intero."""
    g = F.GestoreFlussi(SessioneFinta(), P.profilo("runner_calcio", {}),
                        cambio=CambioGbpEur(fisso=CAMBIO))
    visti: List[Any] = []
    g.aggiungi_consumatore(visti.append)
    g.avvia()
    g._lock.acquire()
    try:
        g._inoltra([Libri().immagine()])
        assert attendi(lambda: len(visti) == 1, secondi=2.0)
    finally:
        g._lock.release()
        g.ferma()


def test_rete_lenta_di_una_connessione_non_blocca_il_gestore():
    """Una connessione e' in rete (``_invio`` tenuto: connessione, autenticazione o
    invio lento): ``imposta_mercati`` la aspetta FUORI dal lock del gestore, quindi
    manutenzione e nuovi consumatori non si fermano."""
    g = F.GestoreFlussi(SessioneFinta(), P.profilo("runner_calcio", {}),
                        cambio=CambioGbpEur(fisso=CAMBIO))
    g.avvia()
    c = F._Connessione(g, 1, {"1.1"})                        # il thread NON parte
    c.stream = type("S", (), {"running": True})()
    c._sottoscrivi = lambda s, ripresa: None
    g._connessioni = [c]
    c._invio.acquire()
    t = threading.Thread(target=lambda: g.imposta_mercati(["1.1", "1.2"]), daemon=True)
    t.start()
    time.sleep(0.3)
    fatto = threading.Event()

    def manutenzione() -> None:
        g.manutenzione()
        g.aggiungi_consumatore(lambda b: None)
        fatto.set()
    m = threading.Thread(target=manutenzione, daemon=True)
    m.start()
    try:
        assert fatto.wait(2.0), "il lock del gestore e' tenuto durante la rete"
    finally:
        c._invio.release()
        t.join(2)
        m.join(2)
        g.ferma()


def test_nessun_deadlock_con_operazioni_concorrenti(server_stream):
    """Piu' thread che cambiano i mercati, fanno manutenzione, leggono lo stato e il
    watchdog insieme, su connessioni vere: tutto finisce, i book arrivano."""
    server_stream(_risposta_immagine)
    g = _gestore()
    libri: List[str] = []
    g.aggiungi_consumatore(lambda b: libri.append(b.market_id))
    fine = time.monotonic() + 1.5
    errori: List[BaseException] = []

    def cambia(seme: int) -> None:
        rnd = random.Random(seme)
        try:
            while time.monotonic() < fine:
                g.imposta_mercati(_ids(0, rnd.choice([1, 50, 180, 300, 420])))
                time.sleep(0.01)
        except BaseException as e:  # noqa: BLE001 - registrato e asserito sotto
            errori.append(e)

    def guarda() -> None:
        try:
            while time.monotonic() < fine:
                g.manutenzione(), g.stato(), g.veglia(), g.capacita()
                [g.stato_flusso(m) for m in _ids(0, 5)]
        except BaseException as e:  # noqa: BLE001
            errori.append(e)
    fili = [threading.Thread(target=cambia, args=(k,), daemon=True) for k in range(3)]
    fili.append(threading.Thread(target=guarda, daemon=True))
    for f in fili:
        f.start()
    for f in fili:
        f.join(10)
    try:
        assert not [f for f in fili if f.is_alive()], "thread bloccato: deadlock"
        assert errori == []
        assert attendi(lambda: len(libri) > 0)
    finally:
        g.ferma()


# ---------------------------------------------------------------------------
# flusso: backoff, watchdog, eventi, potatura
# ---------------------------------------------------------------------------
class _PausaFinta:
    def __init__(self, conn: Any, n: int) -> None:
        self.attese: List[float] = []
        self.conn = conn
        self.n = n

    def wait(self, t: float = None) -> bool:
        self.attese.append(t)
        if len(self.attese) >= self.n:
            self.conn.chiusa = True
        return False

    def set(self) -> None:
        pass


@pytest.mark.parametrize("sana,massimo", [(True, 2.0), (False, 60.0)])
def test_backoff_della_connessione_si_azzera_dopo_dati(sana, massimo):
    """DIVERGENZA MIGLIORATIVA dichiarata rispetto a ``FrammentoMarketStream.run``."""
    msg = dict(immagine(["1.1"], 1), id=7)

    class StreamFinto:
        def __init__(self, li: Any) -> None:
            self.li = li
            self.running = False

        def subscribe_to_markets(self, **kw: Any) -> int:
            self.li.register_stream(7, "marketSubscription")
            return 7

        def start(self) -> None:
            self.running = True
            if sana:
                self.li.on_data(json.dumps(msg))
            raise ConnectionError("caduta")

        def stop(self) -> None:
            self.running = False
    g = F.GestoreFlussi(SessioneFinta(), P.profilo("runner_tennis", {}),
                        crea_stream=lambda c, i, li: StreamFinto(li), cambio=CambioGbpEur(fisso=CAMBIO))
    c = F._Connessione(g, 1, {"1.1"})
    c._pausa = _PausaFinta(c, 12)
    c._ciclo()
    assert max(c._pausa.attese[-3:]) == massimo and c.riconnessioni == 12


def test_watchdog_del_flusso_muto_riprende_con_clk_ed_emette_l_evento(server_stream):
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        img = immagine(m["marketFilter"]["marketIds"], k)
        img["heartbeatMs"] = 500
        return [img]                                         # poi silenzio, senza chiudere
    srv = server_stream(risposta)
    g = _gestore("runner_tennis")
    eventi: List[Any] = []
    g.aggiungi_osservatore(lambda nome, dato: eventi.append((nome, dato)))
    try:
        g.imposta_mercati(_ids(0, 3))
        assert attendi(lambda: len(srv.sottoscrizioni) >= 2, secondi=8)
        seconda = srv.sottoscrizioni[1][1]
        assert (seconda["initialClk"], seconda["clk"]) == ("INI-1", "CLK-1")
        assert (F.EVENTO_FLUSSO_MUTO, 1) in eventi
        assert g.stato()["conti"]["riavvii_watchdog"] >= 1
    finally:
        g.ferma()


def test_eventi_mercato_chiuso_e_capacita_cambiata(server_stream):
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        img = immagine(m["marketFilter"]["marketIds"], k)
        img["mc"][0]["marketDefinition"] = dict(MODELLO["marketDefinition"], status="CLOSED")
        return [img]
    server_stream(risposta, autentica=lambda n: {"op": "status", "statusCode": "SUCCESS",
                                                 "connectionClosed": False,
                                                 "connectionsAvailable": 1})
    g = _gestore()
    eventi: List[Any] = []
    g.aggiungi_osservatore(lambda nome, dato: eventi.append((nome, dato)))
    try:
        g.imposta_mercati(_ids(0, 2))
        assert attendi(lambda: (F.EVENTO_MERCATO_CHIUSO, "1.000000") in eventi)
        assert g.stato()["mercati_chiusi"] == ["1.000000"]
        assert attendi(lambda: g._disponibili() == 1)
        assert g.capacita() == 180
        assert (F.EVENTO_CAPACITA_CAMBIATA, 180) in eventi
    finally:
        g.ferma()


def test_book_dei_mercati_non_piu_sottoscritti_escono(server_stream):
    server_stream(_risposta_immagine)
    g = _gestore("runner_tennis")
    try:
        g.imposta_mercati(_ids(0, 3))
        assert attendi(lambda: all(g.book(m) is not None for m in _ids(0, 3)))
        g.imposta_mercati(_ids(0, 1))
        assert g.book("1.000000") is not None
        assert g.book("1.000001") is None and g.book("1.000002") is None
        assert g.stato()["conti"]["libri_potati"] == 2
    finally:
        g.ferma()


def test_connessione_rimasta_senza_mercati_si_chiude_non_si_sottoscrive_vuota(server_stream):
    """(X15)"""
    srv = server_stream(_risposta_immagine)
    g = _gestore()
    try:
        assert g.imposta_mercati(_ids(0, 400)) == set()
        assert attendi(lambda: len(srv.sottoscrizioni) == 3)
        prima = sorted(g._vive()[0].mercati)
        assert g.imposta_mercati(prima) == set()
        assert len(g._vive()) == 1
        assert g.stato()["conti"]["chiusure"] == 2
        assert all(len(m["marketFilter"]["marketIds"]) > 0 for _, m in srv.sottoscrizioni)
    finally:
        g.ferma()


def test_ogni_book_di_un_messaggio_con_piu_mercati_arriva_convertito(server_stream):
    """(X18) Un'immagine con 3 mercati in UN messaggio: tutti e tre GBP -> EUR."""
    srv = server_stream(_risposta_immagine)
    g = _gestore()
    visti: List[Any] = []
    g.aggiungi_consumatore(visti.append)
    try:
        assert g.imposta_mercati(_ids(0, 3)) == set()
        assert attendi(lambda: len({b.market_id for b in visti}) == 3)
        assert len(srv.sottoscrizioni) == 1                  # un solo messaggio, 3 book
        for b in visti:
            assert getattr(b, "size_gbp_convertite", False) is True, b.market_id
            assert b.cambio_gbp_eur == CAMBIO and b.valuta == "EUR"
        for mid in _ids(0, 3):
            assert g.book(mid).size_gbp_convertite is True
    finally:
        g.ferma()


def test_il_costruttore_non_permette_di_spegnere_la_conversione():
    import inspect

    assert "converti_valuta" not in inspect.signature(F.GestoreFlussi).parameters


def test_no_session_sulla_connessione_dei_prezzi_si_segnala(server_stream, monkeypatch):
    from .test_a2_ordini_revisione import SessioneSegnalabile

    monkeypatch.setattr(F, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(F, "BACKOFF_MAX_S", 0.2)

    def autentica(n: int) -> Dict[str, Any]:
        if n == 1:
            return {"op": "status", "statusCode": "FAILURE", "errorCode": "NO_SESSION",
                    "errorMessage": "sessione scaduta", "connectionClosed": True}
        return {"op": "status", "statusCode": "SUCCESS", "connectionClosed": False}
    srv = server_stream(_risposta_immagine, autentica)
    sess = SessioneSegnalabile()
    g = F.GestoreFlussi(sess, P.profilo("runner_tennis", {}), cambio=CambioGbpEur(fisso=CAMBIO))
    try:
        g.imposta_mercati(_ids(0, 2))
        assert attendi(lambda: g.book("1.000000") is not None)
        assert sess.segnalazioni == ["NO_SESSION"] and sess.rinnovi == 0
        auth = [m for _, m in srv.ricevuti if m["op"] == "authentication"]
        assert auth[1]["session"] == "token-dopo-segnalazione"
    finally:
        g.ferma()
