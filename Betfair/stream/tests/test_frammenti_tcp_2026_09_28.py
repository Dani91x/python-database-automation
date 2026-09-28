"""Cantiere B (28/09), punto 2 del coordinatore: il frammento aperto a caldo
ESEGUITO DAVVERO, su un finto server dello stream Betfair in TLS su 127.0.0.1.

Vero: ``GestoreFrammenti`` con l'avvio vero (``Thread.start``),
``FrammentoMarketStream.run`` -> ``MarketStream.run`` di flumine ->
``APIClient.streaming.create_stream`` -> ``BetfairStream`` di betfairlightweight
(socket TLS, lettura a CRLF, autenticazione, ``marketSubscription``), il
``FrammentoListener`` (tee + battito), la coda di output di flumine
(``handle_output`` -> ``handler_queue``) e ``Flumine._process_market_books``
(lo stesso che gira nel ciclo principale) fino a ``process_market_book`` della
strategia.

Unico ritocco: dove si connette betfairlightweight. ``BetfairStream.HOSTS`` e'
un ``defaultdict`` che manda qualunque host sconosciuto a
``stream-api.betfair.com`` (``betfairstream.py:24-28``) e la porta e' la
costante di classe ``__port = 443`` (``betfairstream.py:20``): nessun
parametro pubblico permette 127.0.0.1, quindi il test sostituisce la voce
``HOSTS[None]`` e ``_BetfairStream__port`` (monkeypatch). TLS resta vero
(certificato autofirmato generato al volo; bflw non verifica il certificato,
``betfairstream.py:216-218``).

Il finto server parla il protocollo della Exchange Stream API con le chiavi
e i tipi dei messaggi veri (docs Betfair; il ``marketDefinition`` e i prezzi
vengono dalla registrazione raw ``_live_raw/35784105/35784105.raw.jsonl``,
exchange .it, ``regulators: ["MR_ITA"]``):
  connection -> {"op":"connection","connectionId":...}
  authentication -> status SUCCESS con connectionsAvailable (o FAILURE
                    MAX_CONNECTION_LIMIT_EXCEEDED con connectionClosed)
  marketSubscription -> status SUCCESS, mcm SUB_IMAGE (initialClk/clk),
                    mcm HEARTBEAT
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import queue
import socket
import ssl
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

import pytest
from betfairlightweight.streaming.betfairstream import BetfairStream
from flumine import BaseStrategy

from Betfair.stream import frammenti_mercato as FR
from Betfair.stream import sottoscrizione_a_caldo as SC

from .test_frammenti_mercato_2026_09_28 import _collega, _framework, _ids, _market_streams

MID = "1.259691614"
# marketDefinition VERO (registrazione .it del 06/07/2026, evento 35784105)
DEF_VERA = {
    "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
    "marketBaseRate": 5, "eventId": "35784105", "eventTypeId": "1", "numberOfWinners": 1,
    "bettingType": "ODDS", "marketType": "MATCH_ODDS", "marketTime": "2026-07-06T19:00:00.000Z",
    "suspendTime": "2026-07-06T19:00:00.000Z", "bspReconciled": False, "complete": True,
    "inPlay": True, "crossMatching": True, "runnersVoidable": False,
    "numberOfActiveRunners": 3, "betDelay": 5, "status": "OPEN", "betDelayModels": ["PASSIVE"],
    "runners": [{"status": "ACTIVE", "sortPriority": 1, "id": 19},
                {"status": "ACTIVE", "sortPriority": 2, "id": 22},
                {"status": "ACTIVE", "sortPriority": 3, "id": 58805}],
    "regulators": ["MR_ITA"], "discountAllowed": True, "timezone": "GMT",
    "openDate": "2026-07-06T19:00:00.000Z", "version": 7484715449,
    "priceLadderDefinition": {"type": "CLASSIC"},
}
RC_VERO = [{"atb": [[1.26, 8.54], [1.25, 54.68]], "atl": [[2.02, 1.71]],
            "trd": [[1.31, 252.82]], "ltp": 1.31, "tv": 252.82, "id": 19}]


def _cert(cartella: str) -> "tuple[str, str]":
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    chiave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    ora = _dt.datetime.now(_dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
            .public_key(chiave.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(ora - _dt.timedelta(days=1))
            .not_valid_after(ora + _dt.timedelta(days=1)).sign(chiave, hashes.SHA256()))
    pc, pk = os.path.join(cartella, "c.pem"), os.path.join(cartella, "k.pem")
    with open(pc, "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(pk, "wb") as fh:
        fh.write(chiave.private_bytes(serialization.Encoding.PEM,
                                      serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    return pc, pk


class ServerStream:
    """Finto server della Exchange Stream API (TLS, messaggi JSON a CRLF)."""

    def __init__(self, modo: str) -> None:
        self.modo = modo                  # "ok" | "rifiuto" | "cade"
        self.cartella = tempfile.mkdtemp(prefix="cantB_")
        cert, chiave = _cert(self.cartella)
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(cert, chiave)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.porta = self.sock.getsockname()[1]
        self.connessioni = 0
        self.ricevuti: List[Dict[str, Any]] = []
        self.sottoscrizioni: List[Dict[str, Any]] = []
        self._stop = False
        self._conn: List[Any] = []
        threading.Thread(target=self._accetta, daemon=True).start()

    def _accetta(self) -> None:
        while not self._stop:
            try:
                grezzo, _ = self.sock.accept()
            except OSError:
                return
            self.connessioni += 1
            threading.Thread(target=self._servi, args=(grezzo, self.connessioni),
                             daemon=True).start()

    @staticmethod
    def _manda(c: Any, d: Dict[str, Any]) -> None:
        c.sendall((json.dumps(d, separators=(",", ":")) + "\r\n").encode("utf-8"))

    def _servi(self, grezzo: Any, n: int) -> None:
        try:
            c = self.ctx.wrap_socket(grezzo, server_side=True)
        except OSError:
            return
        self._conn.append(c)
        buf = b""
        try:
            self._manda(c, {"op": "connection", "connectionId": "002-%012d-000001" % n})
            while not self._stop:
                pezzo = c.recv(4096)
                if not pezzo:
                    return
                buf += pezzo
                while b"\r\n" in buf:
                    riga, buf = buf.split(b"\r\n", 1)
                    if riga:
                        self._rispondi(c, json.loads(riga.decode("utf-8")), n)
        except OSError:
            return

    def _rispondi(self, c: Any, m: Dict[str, Any], n: int) -> None:
        self.ricevuti.append(m)
        if m.get("op") == "authentication":
            if self.modo == "rifiuto":
                self._manda(c, {"op": "status", "id": m["id"], "statusCode": "FAILURE",
                                "errorCode": "MAX_CONNECTION_LIMIT_EXCEEDED",
                                "errorMessage": "You have exceeded your max connection limit "
                                                "which is: 10 connection(s).",
                                "connectionClosed": True,
                                "connectionId": "002-%012d-000001" % n})
                c.close()
                return
            self._manda(c, {"op": "status", "id": m["id"], "statusCode": "SUCCESS",
                            "connectionClosed": False, "connectionsAvailable": 7})
        elif m.get("op") == "marketSubscription":
            self.sottoscrizioni.append(m)
            self._manda(c, {"op": "status", "id": m["id"], "statusCode": "SUCCESS",
                            "connectionClosed": False})
            pt = int(time.time() * 1000)
            if len(self.sottoscrizioni) == 1:
                self._manda(c, {"op": "mcm", "id": m["id"], "initialClk": "INIT-1",
                                "clk": "CLK-1", "conflateMs": 0, "heartbeatMs": 5000,
                                "pt": pt, "ct": "SUB_IMAGE",
                                "mc": [{"id": MID, "marketDefinition": DEF_VERA,
                                        "rc": RC_VERO, "img": True}]})
                if self.modo == "cade":
                    c.close()                     # la connessione cade
                    return
                self._manda(c, {"op": "mcm", "id": m["id"], "clk": "CLK-2", "pt": pt + 5000,
                                "ct": "HEARTBEAT"})
            else:
                # riconnessione: delta dopo il clk ricevuto
                self._manda(c, {"op": "mcm", "id": m["id"], "clk": "CLK-3", "pt": pt,
                                "mc": [{"id": MID, "rc": [{"atb": [[1.27, 10.0]], "id": 19}]}]})

    def chiudi(self) -> None:
        self._stop = True
        for c in list(self._conn):
            try:
                c.close()
            except OSError:
                pass
        self.sock.close()


class _Spia(BaseStrategy):
    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.libri: List[Any] = []

    def check_market_book(self, market: Any, market_book: Any) -> bool:
        return True

    def process_market_book(self, market: Any, market_book: Any) -> None:
        self.libri.append(market_book)


@pytest.fixture
def ambiente(monkeypatch):
    server: List[ServerStream] = []

    def avvia(modo: str):
        s = ServerStream(modo)
        server.append(s)
        monkeypatch.setitem(BetfairStream.HOSTS, None, "127.0.0.1")
        monkeypatch.setattr(BetfairStream, "_BetfairStream__port", s.porta)
        fw, rec, live = _framework(_ids(0, 180))
        fw.clients.get_default().betting_client.set_session_token("tok-finto")
        spia = _Spia(**FR.kwargs_stream_condiviso(rec), name="spia_tcp")
        fw.add_strategy(spia)
        _collega(_market_streams(fw)[0])     # frammento 0: 180 mercati gia' pieni
        g = FR.GestoreFrammenti(per_conn=180, max_conn=3, riserva=0)   # avvio VERO
        return s, fw, spia, g
    yield avvia
    for s in server:
        s.chiudi()


def _attendi(cond, secondi: float = 15.0) -> bool:
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.05)
    return False


def _fino_a(fw: Any, cond, secondi: float = 15.0) -> bool:
    """Il ciclo principale di flumine, per gli eventi di mercato: preleva dalla
    coda VERA (``handler_queue``, riempita da ``MarketStream.handle_output``) e
    chiama ``Flumine._process_market_books`` VERO, finche' ``cond()``."""
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if cond():
            return True
        try:
            ev = fw.handler_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if type(ev).__name__ == "MarketBookEvent":
            fw._process_market_books(ev)
    return cond()


def test_frammento_aperto_a_caldo_arriva_a_process_market_book(ambiente):
    server, fw, spia, g = ambiente("ok")
    g.applica(fw, _ids(0, 180) + [MID])
    nuovo = FR.GestoreFrammenti.frammenti(fw)[1]
    try:
        assert _attendi(lambda: nuovo._listener.autenticato_una_volta)
        assert _fino_a(fw, lambda: any(b.market_id == MID for b in spia.libri))
        libro = [b for b in spia.libri if b.market_id == MID][-1]
        assert libro.streaming_unique_id == nuovo.stream_id
        assert libro.runners[0].ex.available_to_back[0]["price"] == 1.26
        assert libro.market_definition.regulators == ["MR_ITA"]
        # cosa ha ricevuto Betfair (il finto): autenticazione e sottoscrizione vere
        auth = [m for m in server.ricevuti if m["op"] == "authentication"][0]
        assert auth["appKey"] == "k" and auth["session"] == "tok-finto"
        sub = server.sottoscrizioni[0]
        assert sub["marketFilter"] == {"marketIds": [MID]}
        assert sub["marketDataFilter"] == _market_streams(fw)[0].market_data_filter
        assert sub["segmentationEnabled"] is True
        # battito del frammento: heartbeat e connectionsAvailable dal socket vero
        assert _attendi(lambda: nuovo._listener.connessioni_disponibili == 7)
        li = nuovo._listener
        assert li.autenticato and li.ultimo_msg_mono > 0 and li.ultimo_dato_mono > 0
        st = g.stato(fw)
        assert st["connessioni_di_mercato"] == 2 and st["frammenti"][1]["connesso"] is True
    finally:
        nuovo.stop()
    assert _attendi(lambda: not nuovo.is_alive(), 10.0), "il frammento chiuso gira ancora"


def test_rifiuto_max_connection_limit_chiude_e_non_ritenta(ambiente):
    server, fw, _spia, g = ambiente("rifiuto")
    g.applica(fw, _ids(0, 180) + [MID])
    nuovo = FR.GestoreFrammenti.frammenti(fw)[1]
    assert _attendi(lambda: nuovo._listener.ultimo_errore == "MAX_CONNECTION_LIMIT_EXCEEDED")
    persi = g.manutenzione(fw)
    assert persi == {MID} and nuovo.chiuso
    assert g.capacita(fw) == 180
    assert _attendi(lambda: not nuovo.is_alive(), 10.0)
    n = server.connessioni
    time.sleep(3.0)                              # oltre il primo backoff (2 s)
    assert server.connessioni == n, "il frammento rifiutato continua a riconnettersi"


def test_connessione_che_cade_si_riconnette_con_initialclk_e_clk(ambiente):
    server, fw, spia, g = ambiente("cade")
    g.applica(fw, _ids(0, 180) + [MID])
    nuovo = FR.GestoreFrammenti.frammenti(fw)[1]
    try:
        assert _attendi(lambda: len(server.sottoscrizioni) >= 2, 20.0)
        seconda = server.sottoscrizioni[1]
        assert seconda["initialClk"] == "INIT-1" and seconda["clk"] == "CLK-1"
        assert seconda["marketFilter"] == {"marketIds": [MID]}
        assert server.connessioni == 2 and nuovo.riconnessioni >= 1
        assert _fino_a(fw, lambda: any(
            b.market_id == MID and b.runners[0].ex.available_to_back[0]["price"] == 1.27
            for b in spia.libri))
        assert SC.mercati_dello_stream(nuovo) == [MID]
    finally:
        nuovo.stop()
    assert _attendi(lambda: not nuovo.is_alive(), 10.0)


def test_uscita_ordinata_chiude_tutte_le_connessioni_a_caldo(ambiente):
    """Incrocio A+B: all'uscita ordinata del runner (``arresto_worker`` ->
    ``_stop_framework`` -> ``Flumine.__exit__``) flumine chiama
    ``streams.stop()`` (baseflumine.py:523): anche il frammento aperto a caldo,
    con il suo thread VERO connesso al server, si chiude e non si riconnette."""
    server, fw, _spia, g = ambiente("ok")
    g.applica(fw, _ids(0, 180) + [MID])
    base, nuovo = FR.GestoreFrammenti.frammenti(fw)
    assert _attendi(lambda: nuovo._listener.autenticato_una_volta)
    n = server.connessioni
    fw.streams.stop()
    assert base.chiuso and nuovo.chiuso
    assert _attendi(lambda: not nuovo.is_alive(), 10.0), "thread del frammento ancora vivo"
    time.sleep(2.5)
    assert server.connessioni == n
    with pytest.raises(SC.NonPronto):
        g.applica(fw, _ids(0, 180) + [MID, "1.999999"])
