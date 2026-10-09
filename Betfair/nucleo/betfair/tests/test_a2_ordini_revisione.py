"""W1-A2 - stream degli ordini del conto: le prove della REVISIONE indipendente (09/10).

Incorporati (con nomi nostri e asserzioni sul comportamento CORRETTO) i test del
revisore (``test_rev_ordini.py`` R1-R7, ``test_rev_sopravvissute.py`` X1, X2, X8) e
le prove delle correzioni: ordini non confermati a fine immagine (anche vuota, anche
di runner), posizioni sostituite dalla ``fullImage`` di mercato, importi assenti mai 0,
watchdog del flusso muto, sessione segnalata, potatura dei completati.
Seconda revisione (09/10): backoff azzerato SOLO dopo una connessione rimasta su oltre
``VIVA_DOPO_S`` (tempesta immagine+chiusura, anche dal watchdog), soglia del watchdog
fissata (3 heartbeat dalla sottoscrizione), slot di connessione con la regola nuova
(riserva non applicata, 0 = un'attesa e poi si prova, rifiuto = backoff), eseguiti
noti mai "non confermati".
Catena VERA della libreria; connessioni sul server TLS finto (``test_a2_finti``).
"""
from __future__ import annotations

import json
import threading
from typing import Any, Dict, List

import pytest

from Betfair.nucleo.betfair import flusso_ordini_conto as FOC

from .test_a2_finti import CHIUDI, SessioneFinta, attendi, server_stream  # noqa: F401
from .test_a2_flusso_ordini_conto import (  # noqa: F401
    MID, MID2, PT0, _immagine, backoff_breve, mercato, ocm, runner, uo)


def _flusso(**kw: Any):
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), **kw)
    li = f._listener
    li.register_stream(5, "orderSubscription")        # come subscribe_to_orders
    return f, li


# ---------------------------------------------------------------------------
# A1 - ordini EXECUTABLE stantii dopo una ripartenza da zero
# ---------------------------------------------------------------------------
def test_ripartenza_da_zero_su_un_altro_mercato_segnala_gli_stantii():
    """(R1) Durante la caduta gli ordini 1 e 2 si sono conclusi; la nuova immagine porta
    solo un ordine di un ALTRO mercato: 1 e 2 non sono piu' confermati."""
    f, li = _flusso()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1"), uo("2")])], full=True)], ct="SUB_IMAGE"))
    li.register_stream(6, "orderSubscription")
    li.on_data(ocm([mercato(MID2, [runner(22, [uo("9")])], full=True)], ct="SUB_IMAGE", sid=6))
    assert f.ordini_non_confermati() == {"1", "2"}
    stati = {o.bet_id: o.confermato for o in f.ordini()}
    assert stati == {"1": False, "2": False, "9": True}


def test_ripartenza_da_zero_con_immagine_vuota_senza_oc():
    """(R2) Nessun ordine vivo sul conto dopo la caduta: l'immagine arriva SENZA ``oc``."""
    f, li = _flusso()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True)], ct="SUB_IMAGE"))
    li.register_stream(6, "orderSubscription")
    li.on_data(json.dumps({"op": "ocm", "id": 6, "ct": "SUB_IMAGE", "pt": PT0, "clk": "C",
                           "initialClk": "I"}))
    assert f.ordini_non_confermati() == {"1"}


@pytest.mark.parametrize("nel_secondo,attesi", [(True, set()), (False, {"2"})])
def test_immagine_a_segmenti_si_chiude_solo_a_fine_segmento(nel_secondo, attesi):
    f, li = _flusso()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True),
                    mercato(MID2, [runner(22, [uo("2")])], full=True)], ct="SUB_IMAGE"))
    li.register_stream(6, "orderSubscription")
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True)], ct="SUB_IMAGE", sid=6,
                   segmentType="SEG_START", initial="I"))
    assert f.ordini_non_confermati() == set()             # immagine non ancora finita
    oc = [mercato(MID2, [runner(22, [uo("2")])], full=True)] if nel_secondo else []
    li.on_data(ocm(oc, ct="SUB_IMAGE", sid=6, segmentType="SEG_END", clk="C"))
    assert f.ordini_non_confermati() == attesi


def test_fullimage_solo_di_runner_segnala_l_ordine_sparito():
    """(R3) Un'immagine di RUNNER (senza fullImage di mercato) non riporta l'ordine 2."""
    f, li = _flusso()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1"), uo("2")]), runner(22, [uo("3")])],
                            full=True)], ct="SUB_IMAGE"))
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1")], full=True)])], pt=PT0 + 5))
    assert f.ordini_non_confermati() == {"2"}             # 3 e' su un altro runner


def test_fullimage_di_mercato_in_una_ripresa_segnala_l_ordine_sparito():
    """Dopo una ripresa con clk (``RESUB_DELTA``) Betfair puo' rimandare un mercato con
    ``fullImage`` ("img"): e' un'immagine di MERCATO dentro un delta, non una
    sottoscrizione nuova. L'ordine 2 che non c'e' piu' non e' piu' confermato; l'altro
    mercato non si tocca."""
    f, li = _flusso()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1"), uo("2")])], full=True),
                    mercato(MID2, [runner(22, [uo("3")])], full=True)], ct="SUB_IMAGE", clk="A",
                   initial="I"))
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True)], ct="RESUB_DELTA",
                   clk="B", pt=PT0 + 7))
    assert f.ordini_non_confermati() == {"2"}


def test_ordine_non_confermato_che_si_rifa_vivo_torna_confermato():
    """(X1) Betfair riporta l'ordine 2 (ora concluso): non e' piu' dubbio."""
    f, li = _flusso()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1"), uo("2")])], full=True)], ct="SUB_IMAGE"))
    li.register_stream(6, "orderSubscription")
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True)], ct="SUB_IMAGE", sid=6))
    assert f.ordini_non_confermati() == {"2"}
    li.on_data(ocm([mercato(MID, [runner(19, [uo("2", status="EC", sm=10.0, sr=0.0, avp=2.5)])])],
                   sid=6, pt=PT0 + 3))
    assert f.ordini_non_confermati() == set()
    assert [o.confermato for o in f.ordini() if o.bet_id == "2"] == [True]


def test_consumatore_riceve_l_ordine_non_confermato():
    """(R7) Il consumatore (ladder, libro ordini) SA che l'ordine 2 e' stantio: lo
    riceve di nuovo con ``confermato=False``, senza dover interrogare a parte."""
    f, li = _flusso()
    visti: List[Any] = []
    f.aggiungi_consumatore(visti.append)
    f._thread_consegna = threading.Thread(target=f._consegna, daemon=True)
    f._thread_consegna.start()
    try:
        li.on_data(ocm([mercato(MID, [runner(19, [uo("1"), uo("2")])], full=True)], ct="SUB_IMAGE"))
        li.register_stream(6, "orderSubscription")
        li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True)], ct="SUB_IMAGE", sid=6))
        assert attendi(lambda: any(o.bet_id == "2" and not o.confermato for o in visti))
        o2 = [o for o in f.ordini() if o.bet_id == "2"][0]
        assert (o2.stato, o2.confermato) == ("EXECUTABLE", False)
    finally:
        f._coda.put(None)


def test_eseguito_noto_resta_confermato_dopo_una_ripartenza_da_zero():
    """(A1, Y1) Un ordine gia' EXECUTION_COMPLETE non torna nell'immagine di una
    ripartenza da zero (Betfair manda solo gli EXECUTABLE): NON e' da riconciliare."""
    f, li = _flusso()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1"), uo("2")])], full=True)], ct="SUB_IMAGE"))
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1", status="EC", sm=10.0, sr=0.0)])])],
                   pt=PT0 + 1))
    li.register_stream(6, "orderSubscription")
    li.on_data(ocm([mercato(MID2, [runner(22, [uo("9")])], full=True)], ct="SUB_IMAGE", sid=6))
    stati = {o.bet_id: (o.stato, o.confermato) for o in f.ordini()}
    assert stati == {"1": ("EXECUTION_COMPLETE", True), "2": ("EXECUTABLE", False),
                     "9": ("EXECUTABLE", True)}
    assert f.ordini_non_confermati() == {"2"}


# ---------------------------------------------------------------------------
# A2 - posizioni sostituite dalla fullImage di mercato
# ---------------------------------------------------------------------------
def test_posizione_di_un_runner_assente_dalla_nuova_immagine_di_mercato_esce():
    """(R6) Base del P&L di mercato del comparto C: deve essere esatta."""
    f, li = _flusso()
    li.on_data(ocm([mercato(MID, [{"id": 19, "hc": 0, "mb": [[2.0, 5.0]], "uo": [],
                                   "fullImage": True}], full=True)], ct="SUB_IMAGE"))
    li.on_data(ocm([mercato(MID2, [{"id": 7, "hc": 0, "ml": [[3.0, 2.0]], "fullImage": True}],
                            full=True)], pt=PT0 + 1))
    assert [p["selection_id"] for p in f.posizioni(MID)] == [19]
    li.on_data(ocm([mercato(MID, [{"id": 22, "hc": 0, "mb": [[3.0, 1.0]], "fullImage": True}],
                            full=True)], pt=PT0 + 9))
    assert [(p["selection_id"], p["abbinati_back"]) for p in f.posizioni(MID)] == [(22, [[3.0, 1.0]])]
    assert [p["selection_id"] for p in f.posizioni(MID2)] == [7]      # l'altro mercato resta


# ---------------------------------------------------------------------------
# M6 - importi assenti: None e dichiarati, mai 0
# ---------------------------------------------------------------------------
def test_importi_assenti_non_inventano_abbinato_ne_residuo():
    """(R4) Senza ``sm``/``sr`` un EXECUTABLE con ``md`` e ``avp`` non diventa
    "abbinato 0, residuo 0": i campi restano assenti e l'ordine lo dichiara."""
    f, li = _flusso()
    grezzo = uo("77", status="E", md=PT0 - 1000, avp=2.4)
    grezzo.pop("sm")
    grezzo.pop("sr")
    li.on_data(ocm([mercato(MID, [runner(19, [grezzo])], full=True)], ct="SUB_IMAGE"))
    (o,) = [x for x in f.ordini() if x.bet_id == "77"]
    assert (o.abbinato, o.residuo) == (None, None)
    assert set(o.campi_assenti) == {"sm", "sr"}
    assert o.prezzo_medio == 2.4 and o.stato == "EXECUTABLE"


# ---------------------------------------------------------------------------
# A3 - backoff: azzerato SOLO dopo una connessione rimasta su oltre VIVA_DOPO_S
# ---------------------------------------------------------------------------
class _EventoFinto:
    """Al posto di ``threading.Event`` in ``_ciclo``: registra le attese, si ferma dopo n."""

    def __init__(self, n: int) -> None:
        self.attese: List[float] = []
        self.n = n

    def is_set(self) -> bool:
        return len(self.attese) >= self.n

    def wait(self, t: float = None) -> bool:
        self.attese.append(t)
        return self.is_set()

    def set(self) -> None:
        self.attese.extend([0.0] * self.n)

    def clear(self) -> None:
        pass


class _Orologio:
    """Orologio MONOTONO finto (secondi), lo stesso per il flusso e il listener."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _stream_che_cade(orologio: _Orologio, su_per_s: float, con_dati: bool,
                     veglia: Any = None):
    class StreamFinto:
        """Uno stream della libreria che riceve l'immagine (se ``con_dati``), resta su
        ``su_per_s`` secondi dell'orologio finto e cade (o lo chiude il watchdog)."""

        def __init__(self, li: Any) -> None:
            self.li = li
            self.running = False

        def subscribe_to_orders(self, **kw: Any) -> int:
            self.li.register_stream(7, "orderSubscription")
            return 7

        def start(self) -> None:
            self.running = True
            if con_dati:
                self.li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True)],
                                    ct="SUB_IMAGE", clk="C", initial="I", sid=7))
            orologio.t += su_per_s
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


@pytest.mark.parametrize("con_dati,su_per_s,attese", [
    (True, 0.0, CRESCE),        # tempesta: immagine e chiusura a ogni giro (seconda revisione A3-1)
    (False, 0.0, CRESCE),       # cade subito senza niente
    (True, 59.0, CRESCE),       # su meno di VIVA_DOPO_S = 60 s: non basta
    (True, 61.0, AZZERATO),     # su oltre 60 s: sana
    (False, 61.0, AZZERATO),    # su oltre 60 s anche senza ordini (solo heartbeat): sana
])
def test_backoff_si_azzera_solo_dopo_una_connessione_rimasta_su(con_dati, su_per_s, attese):
    orologio = _Orologio()
    classe = _stream_che_cade(orologio, su_per_s, con_dati)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), crea_stream=lambda c, i, li: classe(li),
                                     orologio_mono=orologio)
    ev = _EventoFinto(7)
    f._fermo = ev
    f._ciclo()
    assert ev.attese == attese
    assert f.stato()["ultime_attese_s"] == attese and f.conti["riconnessioni"] == 7


@pytest.mark.parametrize("su_per_s,attese", [(3600.0, AZZERATO), (0.0, CRESCE)])
def test_watchdog_su_una_connessione_su_da_ore_non_raddoppia_il_backoff(su_per_s, attese):
    """(A3-2) La connessione lavora per un'ora e poi diventa muta: il watchdog la
    chiude e la ripresa parte dal backoff minimo. Muta dalla sottoscrizione: cresce."""
    orologio = _Orologio()
    tieni: Dict[str, Any] = {}

    def veglia() -> bool:
        orologio.t += 3 * 5.0 + 1.0                 # muta oltre 3 heartbeat da 5 s
        return tieni["f"]._veglia()
    classe = _stream_che_cade(orologio, su_per_s, True, veglia)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), crea_stream=lambda c, i, li: classe(li),
                                     orologio_mono=orologio)
    tieni["f"] = f
    ev = _EventoFinto(7)
    f._fermo = ev
    f._ciclo()
    assert ev.attese == attese and f.conti["riavvii_watchdog"] == 7


def test_tempesta_vera_immagine_e_chiusura_le_attese_crescono(server_stream, monkeypatch):
    """(A3-1, server TLS) Betfair accetta, manda l'immagine e chiude, ogni volta: le
    attese raddoppiano (prima della correzione restavano al minimo: tempesta)."""
    monkeypatch.setattr(FOC, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(FOC, "BACKOFF_MAX_S", 0.4)
    srv = server_stream(lambda n, m, k: [_immagine(k), CHIUDI])
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    f.avvia()
    try:
        assert attendi(lambda: len(f.stato()["ultime_attese_s"]) >= 5)
        assert f.stato()["ultime_attese_s"][:5] == [0.05, 0.1, 0.2, 0.4, 0.4]
        assert len(srv.sottoscrizioni_di("orderSubscription")) >= 5
    finally:
        f.ferma()


# ---------------------------------------------------------------------------
# X2, X8 - ripresa a meta' immagine; autenticazione nello stato
# ---------------------------------------------------------------------------
def test_caduta_a_meta_immagine_segmentata_riparte_da_zero(server_stream, backoff_breve):
    """(X2) Caduta fra SEG_START (ha initialClk, NON ha clk) e SEG_END: mai una
    ripresa con un clk solo (immagine parziale = ordini persi)."""
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        if k == 1:
            return [{"op": "ocm", "initialClk": "INI-1", "pt": PT0, "ct": "SUB_IMAGE",
                     "segmentType": "SEG_START",
                     "oc": [mercato(MID, [runner(19, [uo("1")])], full=True)]}, CHIUDI]
        return []
    srv = server_stream(risposta)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    f.avvia()
    try:
        assert attendi(lambda: len(srv.sottoscrizioni_di("orderSubscription")) >= 2)
        seconda = srv.sottoscrizioni_di("orderSubscription")[1]
        assert (seconda["initialClk"], seconda["clk"]) == (None, None)
        assert f.stato()["sottoscrizione"] == "da_zero"
    finally:
        f.ferma()


def test_dopo_l_autenticazione_lo_stato_dice_autenticato(server_stream):
    """(X8)"""
    server_stream(lambda n, m, k: [{"op": "ocm", "clk": "C", "initialClk": "I", "pt": PT0,
                                    "ct": "SUB_IMAGE", "oc": []}])
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    f.avvia()
    try:
        assert attendi(lambda: f.stato()["autenticato"] is True)
    finally:
        f.ferma()


# ---------------------------------------------------------------------------
# M1 - watchdog: il flusso muto si chiude e riparte con ripresa
# ---------------------------------------------------------------------------
def test_watchdog_chiude_lo_stream_muto_e_riprende_con_clk(server_stream, backoff_breve):
    """Il server smette di parlare SENZA chiudere: dopo 3 heartbeat (500 ms chiesti e
    rimandati) il watchdog chiude e la connessione riparte con initialClk/clk."""
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        img = _immagine(k)
        img["heartbeatMs"] = 500
        return [img] if k == 1 else [{"op": "ocm", "clk": "CLK-R", "pt": PT0 + 9,
                                      "heartbeatMs": 500, "ct": "RESUB_DELTA", "oc": []}]
    srv = server_stream(risposta)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), heartbeat_ms=500)
    f.avvia()
    try:
        assert attendi(lambda: len(srv.sottoscrizioni_di("orderSubscription")) >= 2, secondi=8)
        seconda = srv.sottoscrizioni_di("orderSubscription")[1]
        assert (seconda["initialClk"], seconda["clk"]) == ("INI-1", "CLK-1")
        assert seconda["heartbeatMs"] == 500
        st = f.stato()
        assert st["riavvii_watchdog"] >= 1 and st["soglia_muto_s"] == 1.5
        assert attendi(lambda: f.stato()["ultimo_clk"] == "CLK-R")
    finally:
        f.ferma()


def _stream_vero_non_collegato(f: Any) -> Any:
    """Un ``BetfairStream`` VERO della libreria (``create_stream``), segnato su senza socket."""
    s = SessioneFinta().client().streaming.create_stream(unique_id=1, listener=f._listener)
    s._running = True
    return s


def test_watchdog_ordini_soglia_di_3_heartbeat_contati_dalla_sottoscrizione():
    """(M1) Soglia = 3 heartbeat (5 s -> 15 s), contata dal piu' recente fra l'ultimo
    messaggio e la sottoscrizione: il battito della connessione PRECEDENTE non conta."""
    orologio = _Orologio(1000.0)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), heartbeat_ms=5000, orologio_mono=orologio)
    s = _stream_vero_non_collegato(f)
    f._stream = s
    f._sottoscrizione_mono = 1000.0
    f._listener.ultimo_msg_mono = 940.0          # dalla connessione di prima
    orologio.t = 1000.0 + 3 * 5.0 - 0.01
    assert f._veglia() is False and s.running is True
    orologio.t = 1000.0 + 3 * 5.0 + 0.01
    assert f._veglia() is True and s.running is False
    assert f.conti["riavvii_watchdog"] == 1 and f._sottoscrizione_mono is None


# ---------------------------------------------------------------------------
# connectionsAvailable (decisione del coordinatore 09/10): la riserva NON vale per lo
# stream ordini; con 0 aspetta e ritenta; rifiuto di Betfair -> backoff
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("libere", [1, 5, None])
def test_con_una_connessione_libera_o_valore_ignoto_lo_stream_ordini_apre(
        server_stream, monkeypatch, libere):
    monkeypatch.setattr(FOC, "ATTESA_SLOT_S", 30.0)
    server_stream(lambda n, m, k: [_immagine(k)])
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), disponibili=lambda: libere)
    f.avvia()
    try:
        assert attendi(lambda: len(f.ordini()) == 2, secondi=5.0)
        st = f.stato()
        assert st["slot"] is None and st["attese_di_slot"] == 0
    finally:
        f.ferma()


def test_con_zero_libere_aspetta_poi_ritenta_mai_in_attesa_per_sempre(server_stream, monkeypatch):
    """Il valore letto da un'altra connessione resta 0 (vecchio): lo stream ordini
    aspetta UNA volta, poi prova; Betfair concede e la NOSTRA autenticazione dice il
    valore vero."""
    monkeypatch.setattr(FOC, "ATTESA_SLOT_S", 0.5)
    srv = server_stream(lambda n, m, k: [_immagine(k)], autentica=lambda n: {
        "op": "status", "statusCode": "SUCCESS", "connectionClosed": False,
        "connectionsAvailable": 7})
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), disponibili=lambda: 0)
    f.avvia()
    try:
        assert attendi(lambda: f.stato()["slot"] == "in_attesa")
        assert srv.connessioni == 0                              # prima aspetta
        assert attendi(lambda: len(f.ordini()) == 2, secondi=5.0)  # poi ritenta
        st = f.stato()
        assert st["slot"] is None and st["attese_di_slot"] == 1
        assert st["connessioni_libere_note"] == 7 and st["connessioni_disponibili"] == 7
    finally:
        f.ferma()


def test_rifiuto_di_betfair_ritenta_con_il_backoff_e_poi_apre(server_stream, monkeypatch):
    """MAX_CONNECTION_LIMIT_EXCEEDED tre volte: si ritenta col backoff (mai 300 s fissi),
    alla quarta Betfair concede."""
    monkeypatch.setattr(FOC, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(FOC, "BACKOFF_MAX_S", 0.4)

    def autentica(n: int) -> Dict[str, Any]:
        if n <= 3:
            return {"op": "status", "statusCode": "FAILURE",
                    "errorCode": "MAX_CONNECTION_LIMIT_EXCEEDED",
                    "errorMessage": "You have exceeded your max connection limit which is: "
                                    "10 connection(s).", "connectionClosed": True}
        return {"op": "status", "statusCode": "SUCCESS", "connectionClosed": False,
                "connectionsAvailable": 2}
    server_stream(lambda n, m, k: [_immagine(k)], autentica)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    f.avvia()
    try:
        assert attendi(lambda: len(f.ordini()) == 2, secondi=8.0)
        st = f.stato()
        assert st["slot_negati"] == 3 and st["slot"] is None
        assert st["ultime_attese_s"] == [0.05, 0.1, 0.2]
        assert st["connessioni_libere_note"] == 2
    finally:
        f.ferma()


# ---------------------------------------------------------------------------
# sessione: segnalazione esplicita (SessioneConSegnalazione)
# ---------------------------------------------------------------------------
class SessioneSegnalabile(SessioneFinta):
    """``SessioneConSegnalazione`` finta: registra le segnalazioni."""

    def __init__(self) -> None:
        super().__init__()
        self.segnalazioni: List[str] = []

    def segnala_sessione_morta(self, motivo: str) -> None:
        self.segnalazioni.append(motivo)
        self.api.set_session_token("token-dopo-segnalazione")


def test_no_session_si_segnala_alla_sessione_senza_affidarsi_al_timer(server_stream, backoff_breve):
    def autentica(n: int) -> Dict[str, Any]:
        if n == 1:
            return {"op": "status", "statusCode": "FAILURE", "errorCode": "NO_SESSION",
                    "errorMessage": "sessione scaduta", "connectionClosed": True}
        return {"op": "status", "statusCode": "SUCCESS", "connectionClosed": False}
    srv = server_stream(lambda n, m, k: [_immagine(k)], autentica)
    sess = SessioneSegnalabile()
    f = FOC.FlussoOrdiniContoBetfair(sess)
    f.avvia()
    try:
        assert attendi(lambda: len(f.ordini()) == 2)
        assert sess.segnalazioni == ["NO_SESSION"] and sess.rinnovi == 0
        auth = [m for _, m in srv.ricevuti if m["op"] == "authentication"]
        assert auth[1]["session"] == "token-dopo-segnalazione"
        assert f.stato()["sessione_segnalata"] == "segnala_sessione_morta"
    finally:
        f.ferma()


# ---------------------------------------------------------------------------
# potatura dei completati e mercati chiusi
# ---------------------------------------------------------------------------
def test_potatura_dei_completati_oltre_il_tetto(monkeypatch):
    monkeypatch.setattr(FOC, "TETTO_COMPLETATI", 3)
    f, li = _flusso(orologio_ms=lambda: 1.0e12)
    li.on_data(ocm([mercato(MID, [runner(19, [uo("VIVO")])], full=True)], ct="SUB_IMAGE"))
    for k in range(6):
        li._ora_ms = (lambda k=k: 1.0e12 + 1 + k)              # ricevuto_ms crescente
        li.on_data(ocm([mercato(MID, [runner(19, [uo("C%d" % k, status="EC", sm=10.0, sr=0.0)])])],
                       pt=PT0 + k + 1))
    rimasti = sorted(o.bet_id for o in f.ordini())
    assert rimasti == ["C3", "C4", "C5", "VIVO"]
    assert f.stato()["completati_potati"] == 3


def test_mercato_chiuso_nello_stato():
    f, li = _flusso()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True)], ct="SUB_IMAGE"))
    li.on_data(ocm([mercato(MID, [], closed=True)], pt=PT0 + 1))
    assert f.stato()["mercati_chiusi"] == [MID]
