"""W1-A2 - gestore dei flussi e ladder: le prove della REVISIONE indipendente (09/10).

Incorporati (con nomi nostri e asserzioni sul comportamento CORRETTO) i test del
revisore (``test_rev_ladder_flusso.py`` L1, L2, F1; ``test_rev_sopravvissute.py`` X15,
X18) e le prove delle correzioni: un errore di pubblicazione non perde il mercato ne'
il lotto, meta in ritardo, chiusura sull'ULTIMO book ricevuto, riparo dopo invii
saltati dal canale, nessuna rete sotto i lock della consegna (niente deadlock),
backoff azzerato, watchdog, eventi del contratto, potatura dei book.
Seconda revisione (09/10): backoff azzerato SOLO dopo una connessione rimasta su oltre
``VIVA_DOPO_S`` (anche dal watchdog), soglia del watchdog dalla sottoscrizione,
``imposta_mercati`` mai un errore di rete a chi chiama (immagine piena dopo), socket
ricollegato dentro l'invio chiuso, nessun book di mercati tolti, riparo che non si
autoalimenta, meta assente senza giri a vuoto, una riga di log al minuto per mercato.
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

from .test_a2_finti import CHIUDI, SessioneFinta, attendi, server_stream  # noqa: F401
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
        # prima si aspetta il primo tentativo (sotto carico il thread puo' partire tardi),
        # poi una finestra fissa: il tetto e' la proprieta' (~ogni 0,2 s a raddoppiare, non migliaia)
        assert attendi(lambda: lad.conti["senza_meta"] >= 1)
        time.sleep(0.6)
        assert 1 <= lad.conti["senza_meta"] <= 10
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


def test_riparo_non_si_autoalimenta_con_un_client_lento():
    """(M5, seconda revisione) Un client indietro salta OGNI invio: il riparo
    ripubblica una volta e rilegge il contatore DOPO; senza book nuovi non riparte."""
    _lb, a, b = _due_mercati()
    ora = Orologio()
    pub: List[str] = []
    saltati = {"n": 0}

    def pubblica(t: str, riga: Dict[str, Any]) -> None:
        pub.append(riga["market_id"])
        saltati["n"] += 1                                    # il client lento salta anche questo
    lad = L.LadderEvento(L.profilo_ladder("calcio", {}), meta=_meta2, pubblica=pubblica,
                         saltati=lambda: saltati["n"], orologio=ora)
    lad.consumatore(a)
    lad.consumatore(b)
    lad.esegui_scaduti()
    assert len(pub) == 2
    ora.t += 1.0
    lad.esegui_scaduti()
    assert len(pub) == 4 and lad.conti["ripari"] == 1
    for _ in range(10):
        ora.t += 1.0
        lad.esegui_scaduti()
    assert len(pub) == 4 and lad.conti["ripari"] == 1


def test_senza_meta_e_senza_book_non_si_riprova_finche_non_arriva_un_push():
    """(M3, Y10) Nessun book e nessun meta: il mercato NON si riprova a vuoto."""
    ora = Orologio()
    chiamate = {"meta": 0}

    def meta(mid: str) -> Optional[L.MetaLadder]:
        chiamate["meta"] += 1
        return None
    lad = L.LadderEvento(L.profilo_ladder("calcio", {}), meta=meta, pubblica=lambda t, r: None,
                         sorgente=lambda mid: None, orologio=ora)
    lad.push_a_ogni_cambio(MID)
    assert lad.esegui_scaduti() is None
    for _ in range(10):
        ora.t += 1.0
        assert lad.esegui_scaduti() is None
    assert lad.stato()["in_attesa"] == 0 and lad.conti["senza_meta"] == 0
    assert chiamate["meta"] == 1


def test_senza_meta_con_book_si_riprova_a_intervalli_crescenti_e_un_book_nuovo_riparte():
    """(M3) Il book c'e', il meta no: 0,2 s, poi intervalli doppi fino a 5 s (mai 5
    giri al secondo per sempre); un book nuovo fa riprovare subito da 0,2 s."""
    lb = Libri()
    ora = Orologio()
    lad = L.LadderEvento(L.profilo_ladder("calcio", {}), meta=lambda m: None,
                         pubblica=lambda t, r: None, orologio=ora)
    lad.consumatore(lb.immagine())
    attese: List[float] = []
    for _ in range(8):
        prossima = lad.esegui_scaduti()
        attese.append(round(prossima - ora.t, 3))
        ora.t = prossima
    assert attese == [0.2, 0.4, 0.8, 1.6, 3.2, 5.0, 5.0, 5.0]
    lad.consumatore(lb.prezzo(1.9, 7.0))
    assert round(lad.esegui_scaduti() - ora.t, 3) == 0.2


def test_errore_di_pubblicazione_permanente_una_riga_al_minuto_per_mercato(caplog):
    """(M2) Un mercato che solleva SEMPRE: al massimo una riga di log al minuto (si
    riprova lo stesso a ogni giro); l'altro mercato esce."""
    _lb, a, b = _due_mercati()
    ora = Orologio()
    pub: List[str] = []

    def pubblica(t: str, riga: Dict[str, Any]) -> None:
        if riga["market_id"] == MID:
            raise RuntimeError("canale rotto")
        pub.append(riga["market_id"])
    lad = L.LadderEvento(L.profilo_ladder("calcio", {}), meta=_meta2, pubblica=pubblica,
                         orologio=ora)
    lad.consumatore(a)
    lad.consumatore(b)

    def righe() -> int:
        return len([r for r in caplog.records if "pubblicazione KO" in r.getMessage()])
    with caplog.at_level("WARNING", logger=L.logger.name):
        for _ in range(290):                                # 58 s a passi di 0,2 s
            lad.esegui_scaduti()
            ora.t += 0.2
        assert righe() == 1 and lad.conti["errori"] >= 250 and pub == ["1.777"]
        ora.t += 3.0
        lad.esegui_scaduti()
        assert righe() == 2


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
    book = copy.deepcopy(Libri().immagine())
    book.market_id = "1.1"                                   # mercato dell'insieme pianificato
    c = F._Connessione(g, 1, {"1.1"})                        # il thread NON parte
    c.stream = type("S", (), {"running": True})()
    c._sottoscrivi = lambda s, ripresa: None
    g._connessioni = [c]
    c._lock.acquire()
    t = threading.Thread(target=lambda: g.imposta_mercati(["1.1", "1.2"]), daemon=True)
    t.start()
    # il piano e' fatto (sotto il lock del gestore, gia' lasciato): il thread e' alla
    # risottoscrizione, fermo sul lock della connessione (niente sleep a tempo fisso)
    assert attendi(lambda: c.piano == {"1.1", "1.2"}, secondi=5.0)
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
    g._coperti = frozenset({MID})                            # come dopo imposta_mercati([MID])
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
    # ``mercati`` cambia sotto il lock della connessione subito prima di ``_invio``: da qui
    # il thread e' in "rete" (fermo su ``_invio``), niente sleep a tempo fisso
    assert attendi(lambda: c.mercati == {"1.1", "1.2"}, secondi=5.0)
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


def _stream_prezzi_che_cade(ora: Orologio, su_per_s: float, con_dati: bool, veglia: Any = None):
    msg = dict(immagine(["1.1"], 1), id=7)

    class StreamFinto:
        """Uno stream della libreria che riceve l'immagine (se ``con_dati``), resta su
        ``su_per_s`` secondi dell'orologio finto e cade (o lo chiude il watchdog)."""

        def __init__(self, li: Any) -> None:
            self.li = li
            self.running = False

        def subscribe_to_markets(self, **kw: Any) -> int:
            self.li.register_stream(7, "marketSubscription")
            return 7

        def start(self) -> None:
            self.running = True
            if con_dati:
                self.li.on_data(json.dumps(msg))
            ora.t += su_per_s
            if veglia is not None:
                assert veglia() is True and self.running is False
                return                      # come la libreria: la lettura finisce dopo stop()
            raise ConnectionError("caduta")

        def stop(self) -> None:
            self.running = False
    return StreamFinto


#: le attese di serie, a backoff che cresce: 2, 4, 8, 16, 32, 60, 60
CRESCE = [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]
AZZERATO = [2.0] * 7


def _gestore_con(ora: Orologio, classe: Any) -> F.GestoreFlussi:
    return F.GestoreFlussi(SessioneFinta(), P.profilo("runner_tennis", {}),
                           crea_stream=lambda c, i, li: classe(li),
                           cambio=CambioGbpEur(fisso=CAMBIO), orologio=ora)


@pytest.mark.parametrize("con_dati,su_per_s,attese", [
    (True, 0.0, CRESCE),        # tempesta: immagine e chiusura a ogni giro (seconda revisione A3-1)
    (False, 0.0, CRESCE),       # cade subito senza niente
    (True, 59.0, CRESCE),       # su meno di VIVA_DOPO_S = 60 s: non basta
    (True, 61.0, AZZERATO),     # su oltre 60 s: sana
    (False, 61.0, AZZERATO),    # su oltre 60 s anche senza book (solo heartbeat): sana
])
def test_backoff_della_connessione_si_azzera_solo_se_rimasta_su(con_dati, su_per_s, attese):
    """DIVERGENZA MIGLIORATIVA dichiarata rispetto a ``FrammentoMarketStream.run``."""
    ora = Orologio(1000.0)
    g = _gestore_con(ora, _stream_prezzi_che_cade(ora, su_per_s, con_dati))
    c = F._Connessione(g, 1, {"1.1"})
    c._pausa = _PausaFinta(c, 7)
    c._ciclo()
    assert c._pausa.attese == attese and list(c.attese) == attese and c.riconnessioni == 7


@pytest.mark.parametrize("su_per_s,attese", [(3600.0, AZZERATO), (0.0, CRESCE)])
def test_watchdog_su_una_connessione_su_da_ore_non_raddoppia_il_backoff(su_per_s, attese):
    """(A3-2) La connessione lavora per un'ora e poi diventa muta: il watchdog la
    chiude e la ripresa parte dal backoff minimo. Muta dalla sottoscrizione: cresce."""
    ora = Orologio(1000.0)
    tieni: Dict[str, Any] = {}

    def veglia() -> bool:
        ora.t += 3 * 5.0 + 1.0                      # muta oltre 3 heartbeat da 5 s
        return tieni["g"].veglia() == [1]
    g = _gestore_con(ora, _stream_prezzi_che_cade(ora, su_per_s, True, veglia))
    c = F._Connessione(g, 1, {"1.1"})
    g._connessioni = [c]
    tieni["g"] = g
    c._pausa = _PausaFinta(c, 7)
    c._ciclo()
    assert c._pausa.attese == attese and g.conti["riavvii_watchdog"] == 7


def test_watchdog_prezzi_soglia_di_3_heartbeat_contati_dalla_sottoscrizione():
    """(M1, Y7) Il battito della connessione PRECEDENTE non conta: si parte dalla
    sottoscrizione; soglia 3 heartbeat da 5 s."""
    ora = Orologio(1000.0)
    g = _gestore("runner_tennis", orologio=ora)
    c = F._Connessione(g, 1, {"1.1"})                        # il thread NON parte
    s = SessioneFinta().client().streaming.create_stream(unique_id=1, listener=c.listener)
    s._running = True                                        # BetfairStream vero, senza socket
    c.stream = s
    g._connessioni = [c]
    c.listener.heartbeat_ms_server = 5000
    c.sottoscritta_mono = 1000.0
    c.listener.ultimo_msg_mono = 940.0
    ora.t = 1000.0 + 3 * 5.0 - 0.01
    assert g.veglia() == [] and s.running is True
    ora.t = 1000.0 + 3 * 5.0 + 0.01
    assert g.veglia() == [1] and s.running is False


def test_tempesta_vera_prezzi_immagine_e_chiusura_le_attese_crescono(server_stream, monkeypatch):
    """(A3-1, server TLS) Betfair accetta, manda l'immagine e chiude, ogni volta: le
    attese raddoppiano (prima della correzione restavano al minimo: tempesta)."""
    monkeypatch.setattr(F, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(F, "BACKOFF_MAX_S", 0.4)
    srv = server_stream(lambda n, m, k: [immagine(m["marketFilter"]["marketIds"], k), CHIUDI])
    g = _gestore("runner_tennis")
    try:
        g.imposta_mercati(_ids(0, 3))
        assert attendi(lambda: len(g.stato()["frammenti"][0]["ultime_attese_s"]) >= 5)
        assert g.stato()["frammenti"][0]["ultime_attese_s"][:5] == [0.05, 0.1, 0.2, 0.4, 0.4]
        assert len(srv.sottoscrizioni) >= 5
    finally:
        g.ferma()


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


# ---------------------------------------------------------------------------
# seconda revisione: N1 (rete mai a chi chiama), connessione orfana, N2 (book stantii)
# ---------------------------------------------------------------------------
class _StreamCheFallisce:
    """Uno stream VERO della libreria, con l'invio della risottoscrizione che trova il
    socket morto (RST) dopo che la connessione era su (prova S8 del revisore)."""

    def __init__(self, reale: Any, stato: Dict[str, Any]) -> None:
        self._r = reale
        self._st = stato

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._r, nome)

    def subscribe_to_markets(self, **kw: Any) -> int:
        if self._st.get("rompi") and self._st.get("avviato"):
            self._st["rompi"] = False
            self._r.stop()
            from betfairlightweight.exceptions import SocketError
            raise SocketError("Socket [Errno 104] Connection reset by peer")
        return self._r.subscribe_to_markets(**kw)

    def start(self) -> None:
        self._st["avviato"] = True
        return self._r.start()


def test_risottoscrizione_fallita_non_solleva_e_riparte_da_immagine_piena(server_stream,
                                                                          monkeypatch):
    """(N1) ``imposta_mercati`` non solleva per la rete: la connessione si chiude e
    riparte da immagine PIENA con l'insieme nuovo (mai una ripresa con filtro diverso)."""
    monkeypatch.setattr(F, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(F, "BACKOFF_MAX_S", 0.2)
    stato: Dict[str, Any] = {}
    srv = server_stream(_risposta_immagine)
    g = _gestore("runner_tennis", crea_stream=lambda client, uid, li: _StreamCheFallisce(
        F._crea_stream_libreria(client, uid, li), stato))
    try:
        g.imposta_mercati(_ids(0, 3))
        assert attendi(lambda: all(g.book(m) is not None for m in _ids(0, 3)))
        stato["rompi"] = True
        assert g.imposta_mercati(_ids(0, 3) + _ids(10, 12)) == set()      # nessuna eccezione
        assert attendi(lambda: all(g.book(m) is not None for m in _ids(10, 12)))
        ultima = srv.sottoscrizioni[-1][1]
        assert sorted(ultima["marketFilter"]["marketIds"]) == sorted(_ids(0, 3) + _ids(10, 12))
        assert (ultima.get("initialClk"), ultima.get("clk")) == (None, None)
        assert g.stato()["conti"]["risottoscrizioni_fallite"] == 1
    finally:
        g.ferma()


class _StreamMorente:
    """Uno stream VERO il cui socket muore DOPO il controllo ``running`` di
    ``risottoscrivi``: la libreria, nell'invio, lo ricollega nel thread di chi chiama
    (``BetfairStream._send``). Si aspetta che la lettura della connessione sia finita,
    cosi' il socket ricollegato non lo legge nessuno (prova S9 del revisore)."""

    def __init__(self, reale: Any, stato: Dict[str, Any]) -> None:
        self._r = reale
        self._st = stato

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._r, nome)

    def subscribe_to_markets(self, **kw: Any) -> int:
        if self._st.get("rompi") and self._st.get("avviato"):
            self._st["rompi"] = False
            conn = self._st["conn"]
            prima = conn.riconnessioni
            self._r.stop()
            assert attendi(lambda: conn.riconnessioni > prima, secondi=5.0)
        return self._r.subscribe_to_markets(**kw)

    def start(self) -> None:
        self._st["avviato"] = True
        return self._r.start()


def test_stream_ricollegato_dentro_l_invio_si_chiude_nessuna_connessione_orfana(server_stream,
                                                                                 monkeypatch):
    import gc

    from betfairlightweight.streaming.betfairstream import BetfairStream
    monkeypatch.setattr(F, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(F, "BACKOFF_MAX_S", 0.2)
    stato: Dict[str, Any] = {}
    server_stream(_risposta_immagine)
    g = _gestore("runner_tennis", crea_stream=lambda client, uid, li: _StreamMorente(
        F._crea_stream_libreria(client, uid, li), stato))

    def aperti() -> List[Any]:
        return [o for o in gc.get_objects() if isinstance(o, BetfairStream)
                and getattr(o, "_running", False) and getattr(o, "_socket", None) is not None]
    try:
        g.imposta_mercati(_ids(0, 3))
        assert attendi(lambda: all(g.book(m) is not None for m in _ids(0, 3)))
        stato["conn"] = g._vive()[0]
        stato["rompi"] = True
        assert g.imposta_mercati(_ids(0, 3) + _ids(10, 12)) == set()
        assert attendi(lambda: all(g.book(m) is not None for m in _ids(10, 12)))
        assert g.stato()["conti"]["connessioni_orfane_chiuse"] == 1
        reale = g._vive()[0].stream._r
        assert [o for o in aperti() if o is not reale] == []
    finally:
        g.ferma()


def test_book_in_volo_di_un_mercato_tolto_non_si_scrive_ne_si_consegna(server_stream):
    """(N2) Un book del mercato appena tolto, ancora in coda, non torna in ``book()`` e
    non arriva ai consumatori."""
    server_stream(_risposta_immagine)
    g = _gestore("runner_tennis")
    visti: List[str] = []
    g.aggiungi_consumatore(lambda b: visti.append(str(b.market_id)))
    try:
        g.imposta_mercati(_ids(0, 3))
        assert attendi(lambda: all(g.book(m) is not None for m in _ids(0, 3)))
        vecchio = g.book("1.000002")
        g.imposta_mercati(_ids(0, 2))
        assert g.book("1.000002") is None
        n = len(visti)
        g._inoltra([vecchio])                                  # in volo: arriva DOPO il cambio
        assert attendi(lambda: g.stato()["conti"]["book_fuori_insieme"] >= 1, secondi=3.0)
        assert attendi(lambda: g._coda.empty())
        time.sleep(0.2)
        assert g.book("1.000002") is None
        assert "1.000002" not in visti[n:]
    finally:
        g.ferma()


def test_risottoscrizione_di_un_piano_vecchio_non_vince_su_quella_nuova():
    """Due ``imposta_mercati`` concorrenti: il thread del piano VECCHIO arriva per
    ultimo alla connessione; vince comunque il piano nuovo (generazione)."""
    g = F.GestoreFlussi(SessioneFinta(), P.profilo("runner_calcio", {}),
                        cambio=CambioGbpEur(fisso=CAMBIO))
    c = F._Connessione(g, 1, {"1.1"})                        # il thread NON parte
    c.stream = type("S", (), {"running": True})()
    mandati: List[List[str]] = []
    c._sottoscrivi = lambda s, ripresa: mandati.append(sorted(c.mercati))
    assert c.risottoscrivi({"1.1", "1.2"}, 5) is True
    assert c.risottoscrivi({"1.1"}, 4) is False
    assert c.mercati == {"1.1", "1.2"} and mandati == [["1.1", "1.2"]]


def _chiudi_forte(srv: Any, n: int) -> None:
    """Il server chiude la connessione n come un RST (shutdown, poi close): il client lo vede subito."""
    import socket as _socket
    c = srv._conn.get(n)
    if c is not None:
        try:
            c.shutdown(_socket.SHUT_RDWR)
        except OSError:
            pass
    srv.chiudi_connessione(n)


# ---------------------------------------------------------------------------
# terza revisione: F1 (durata dalla CONNESSIONE), F2 (mai clk con filtro nuovo), invio vero fallito
# ---------------------------------------------------------------------------
def test_risottoscrizioni_frequenti_non_azzerano_la_durata_della_connessione():
    """(F1) Connessione su 61 s con un cambio di mercati a 59 s (auto-follow in gioco):
    la durata conta dalla CONNESSIONE, non dall'ultima risottoscrizione."""
    ora = Orologio(1000.0)
    tieni: Dict[str, Any] = {}
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
            self.li.on_data(json.dumps(msg))
            ora.t += 59.0
            assert tieni["c"].risottoscrivi({"1.1", "1.2"}) is True
            ora.t += 2.0
            raise ConnectionError("caduta")

        def stop(self) -> None:
            self.running = False
    g = _gestore_con(ora, StreamFinto)
    c = F._Connessione(g, 1, {"1.1"})
    tieni["c"] = c
    c._pausa = _PausaFinta(c, 7)
    c._ciclo()
    assert c._pausa.attese == AZZERATO


def test_su_a_lungo_con_risottoscrizioni_ogni_0_4_s_riparte_dal_minimo(server_stream, monkeypatch):
    """(F1, scenario 1d del revisore) Tempesta, poi una connessione su 2,6 s (> VIVA_DOPO_S =
    1 s nel test) con un cambio di mercati ogni 0,4 s: alla caduta il backoff riparte da 0,05."""
    monkeypatch.setattr(F, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(F, "BACKOFF_MAX_S", 0.4)
    monkeypatch.setattr(F, "VIVA_DOPO_S", 1.0)

    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        if k <= 3:
            return [immagine(m["marketFilter"]["marketIds"], k), CHIUDI]
        if k == 4:
            threading.Timer(2.6, _chiudi_forte, [srv, n]).start()
        return [immagine(m["marketFilter"]["marketIds"], k)]
    srv = server_stream(risposta)
    g = _gestore()
    try:
        g.imposta_mercati(_ids(0, 3))
        assert attendi(lambda: len(srv.sottoscrizioni) >= 4, 20)
        t0 = time.monotonic()
        i = 3
        while time.monotonic() - t0 < 2.4:
            time.sleep(0.4)
            g.imposta_mercati(_ids(0, 3 + i))
            i += 1
        assert attendi(lambda: len(g.stato()["frammenti"][0]["ultime_attese_s"]) >= 4, 10)
        a = g.stato()["frammenti"][0]["ultime_attese_s"]
        assert a[:4] == [0.05, 0.1, 0.2, 0.05], a
    finally:
        g.ferma()


def test_cambio_di_mercati_durante_il_ricollegamento_mai_clk_col_filtro_nuovo(server_stream,
                                                                             monkeypatch):
    """(F2, scenario 3e del revisore) La ripresa con clk e' gia' decisa quando i mercati
    cambiano: la sottoscrizione parte da immagine piena, MAI clk con il filtro nuovo."""
    monkeypatch.setattr(F, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(F, "BACKOFF_MAX_S", 0.2)
    blocca = threading.Event()
    sbloccato = threading.Event()
    stato = {"crea": 0}

    def crea(client: Any, uid: int, li: Any) -> Any:
        stato["crea"] += 1
        if stato["crea"] == 2:
            blocca.set()
            assert sbloccato.wait(10)
        return F._crea_stream_libreria(client, uid, li)

    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        if k == 1:
            threading.Timer(0.3, _chiudi_forte, [srv, n]).start()
        return [immagine(m["marketFilter"]["marketIds"], k)]
    srv = server_stream(risposta)
    g = _gestore(crea_stream=crea)
    try:
        g.imposta_mercati(_ids(0, 3))
        assert blocca.wait(10)                          # ricollegamento in corso, ripresa decisa
        g.imposta_mercati(_ids(0, 3) + _ids(10, 12))    # insieme nuovo MENTRE si ricollega
        sbloccato.set()
        assert attendi(lambda: all(g.book(m) is not None for m in _ids(10, 12)))
        dopo = [m for n, m in srv.sottoscrizioni[1:]]
        assert dopo, srv.sottoscrizioni
        assert all(m.get("clk") is None and m.get("initialClk") is None for m in dopo), [
            (m.get("clk"), len(m["marketFilter"]["marketIds"])) for m in dopo]
        assert sorted(dopo[-1]["marketFilter"]["marketIds"]) == sorted(_ids(0, 3) + _ids(10, 12))
    finally:
        sbloccato.set()
        g.ferma()


def test_invio_vero_fallito_con_econnreset_riparte_da_immagine_piena(server_stream):
    """(scenario 3c del revisore) Il cammino REALE di ``_abbandona``: ``BetfairStream`` vero,
    ECONNRESET su ``sendall`` (la libreria fa ``stop`` e solleva ``SocketError`` DOPO aver
    gia' registrato la sottoscrizione nuova)."""
    srv = server_stream(_risposta_immagine)
    g = _gestore()
    try:
        g.imposta_mercati(_ids(0, 5))
        assert attendi(lambda: g.stato()["conti"]["book"] >= 5, 10)
        s = g._vive()[0].stream

        class Rotto:
            def __init__(self, vero: Any) -> None:
                self.vero = vero

            def sendall(self, *a: Any, **k: Any) -> None:
                raise OSError(104, "Connection reset by peer")

            def __getattr__(self, n: str) -> Any:
                return getattr(self.vero, n)
        s._socket = Rotto(s._socket)
        assert g.imposta_mercati(_ids(0, 9)) == set()      # nessuna eccezione
        assert attendi(lambda: len(srv.sottoscrizioni) >= 2, 10)
        assert attendi(lambda: g.book(_ids(8, 9)[0]) is not None, 10)
        ultima = srv.sottoscrizioni[-1][1]
        assert ultima["initialClk"] is None and ultima["clk"] is None
        assert len(ultima["marketFilter"]["marketIds"]) == 9
        assert g.stato()["conti"]["risottoscrizioni_fallite"] == 1
    finally:
        g.ferma()


def test_disponibili_con_istante_dice_quando_e_stato_letto():
    ora = Orologio(1000.0)
    g = _gestore("runner_tennis", orologio=ora)
    c = F._Connessione(g, 1, {"1.1"})                        # il thread NON parte
    g._connessioni = [c]
    assert g.disponibili_con_istante() == (None, None)
    ora.t = 1005.0
    c.listener.on_data(json.dumps({"op": "status", "id": 1, "statusCode": "SUCCESS",
                                   "connectionClosed": False, "connectionsAvailable": 3}))
    assert g.disponibili_con_istante() == (3, 1005.0)
