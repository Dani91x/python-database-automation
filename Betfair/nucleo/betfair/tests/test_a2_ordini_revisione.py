"""W1-A2 - stream degli ordini del conto: le prove della REVISIONE indipendente (09/10).

Incorporati (con nomi nostri e asserzioni sul comportamento CORRETTO) i test del
revisore (``test_rev_ordini.py`` R1-R7, ``test_rev_sopravvissute.py`` X1, X2, X8) e
le prove delle correzioni: ordini non confermati a fine immagine (anche vuota, anche
di runner), posizioni sostituite dalla ``fullImage`` di mercato, importi assenti mai 0,
backoff azzerato dopo una connessione sana, watchdog del flusso muto, slot di
connessione (``connectionsAvailable``), sessione segnalata, potatura dei completati.
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
# A3 - backoff azzerato dopo una connessione sana
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


def _stream_che_cade(sana: bool):
    class StreamFinto:
        """Uno stream della libreria che riceve l'immagine (se ``sana``) e poi cade."""

        def __init__(self, li: Any) -> None:
            self.li = li
            self.running = False

        def subscribe_to_orders(self, **kw: Any) -> int:
            self.li.register_stream(7, "orderSubscription")
            return 7

        def start(self) -> None:
            self.running = True
            if sana:
                self.li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True)],
                                    ct="SUB_IMAGE", clk="C", initial="I", sid=7))
            raise ConnectionError("caduta")

        def stop(self) -> None:
            self.running = False
    return StreamFinto


@pytest.mark.parametrize("sana,massimo", [(True, 2.0), (False, 60.0)])
def test_backoff_si_azzera_dopo_una_connessione_sana(sana, massimo):
    """(R5) Ogni connessione riceve dati e poi cade: l'attesa resta 2 s. Se invece
    non arriva NIENTE, il backoff cresce fino a 60 s (nessun martellamento)."""
    classe = _stream_che_cade(sana)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), crea_stream=lambda c, i, li: classe(li))
    ev = _EventoFinto(12)
    f._fermo = ev
    f._ciclo()
    assert max(ev.attese[-3:]) == massimo
    assert f.conti["riconnessioni"] == 12


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


# ---------------------------------------------------------------------------
# connectionsAvailable: non rubare lo slot; rifiuto -> pausa
# ---------------------------------------------------------------------------
def test_senza_slot_libero_non_apre_e_lo_dice(server_stream, monkeypatch):
    monkeypatch.setattr(FOC, "ATTESA_SLOT_S", 0.05)
    srv = server_stream(lambda n, m, k: [_immagine(k)])
    libere = {"n": 1}
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), disponibili=lambda: libere["n"])
    f.avvia()
    try:
        assert attendi(lambda: f.stato()["slot"] == "in_attesa")
        assert not attendi(lambda: srv.connessioni > 0, secondi=0.4)   # riserva 1: non apre
        libere["n"] = 3
        assert attendi(lambda: len(f.ordini()) == 2)
        assert f.stato()["slot"] is None and f.stato()["attese_di_slot"] >= 1
    finally:
        f.ferma()


def test_rifiuto_di_betfair_mette_in_pausa_lo_stream_ordini(server_stream, backoff_breve):
    srv = server_stream(lambda n, m, k: [], autentica=lambda n: {
        "op": "status", "statusCode": "FAILURE", "errorCode": "MAX_CONNECTION_LIMIT_EXCEEDED",
        "errorMessage": "You have exceeded your max connection limit which is: 10 connection(s).",
        "connectionClosed": True})
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    f.avvia()
    try:
        assert attendi(lambda: f.stato()["slot"] == "negato")
        assert not attendi(lambda: srv.connessioni > 1, secondi=0.5)   # niente martellamento
        assert f.stato()["slot_negati"] == 1
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
