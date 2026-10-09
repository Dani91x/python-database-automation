"""Finti del comparto A2: un server della Exchange Stream API su 127.0.0.1 (TLS vero).

Non e' un finto del cliente: dalla parte nostra gira la catena VERA di
betfairlightweight (``APIClient.streaming.create_stream`` -> ``BetfairStream``:
socket TLS, lettura a CRLF, autenticazione, ``marketSubscription`` /
``orderSubscription`` -> ``StreamListener`` -> cache). L'unico ritocco e' DOVE si
collega la libreria: ``BetfairStream.HOSTS[None]`` e la porta di classe
(``betfairstream.py:20-28``), come in ``Betfair/stream/tests/test_frammenti_tcp_2026_09_28.py``.

Il server parla il protocollo con le chiavi e i tipi dei messaggi veri (schema
ESA ufficiale, https://github.com/betfair/stream-api-sample-code): ``connection``,
``status`` (SUCCESS/FAILURE, ``connectionsAvailable``, ``connectionClosed``),
``mcm``/``ocm`` (``id``, ``clk``, ``initialClk``, ``pt``, ``ct``, ``segmentType``).
Le risposte alle sottoscrizioni le decide il test (``risposta``).

Contiene anche la ``SessioneFinta`` (protocollo ``contratto.Sessione``) con un
``APIClient`` VERO di betfairlightweight (nessun login: token impostato a mano;
le chiamate REST di scommessa sono sostituite da trappole che fanno fallire il test).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import socket
import ssl
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import betfairlightweight
import pytest
from betfairlightweight.streaming.betfairstream import BetfairStream

CHIUDI = "CHIUDI"


def _certificato(cartella: str) -> Tuple[str, str]:
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


Risposta = Callable[[int, Dict[str, Any], int], List[Any]]


class ServerStreamFinto:
    """Finto server della Exchange Stream API (TLS, JSON a CRLF).

    ``autentica(n)`` -> il messaggio ``status`` per la connessione n (1, 2, ...).
    ``risposta(n, sottoscrizione, k)`` -> la lista di cose da mandare dopo lo
    ``status`` SUCCESS della k-esima sottoscrizione (globale): dizionari (``id``
    aggiunto se manca) o ``CHIUDI`` (il server chiude la connessione)."""

    def __init__(self, risposta: Risposta,
                 autentica: Optional[Callable[[int], Dict[str, Any]]] = None) -> None:
        self.risposta = risposta
        self.autentica = autentica or (lambda n: {"op": "status", "statusCode": "SUCCESS",
                                                  "connectionClosed": False,
                                                  "connectionsAvailable": 9})
        self.cartella = tempfile.mkdtemp(prefix="a2_stream_")
        cert, chiave = _certificato(self.cartella)
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(cert, chiave)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.porta = self.sock.getsockname()[1]
        self.connessioni = 0
        self.ricevuti: List[Tuple[int, Dict[str, Any]]] = []
        self.sottoscrizioni: List[Tuple[int, Dict[str, Any]]] = []
        self._conn: Dict[int, Any] = {}
        self._ultimo_id: Dict[int, int] = {}
        self._lock = threading.Lock()
        self._stop = False
        threading.Thread(target=self._accetta, daemon=True).start()

    # ------------------------------------------------------------ API del test
    def manda(self, n: int, msg: Dict[str, Any]) -> None:
        """Manda ``msg`` alla connessione n (``id`` = ultima sottoscrizione)."""
        c = self._conn.get(n)
        if c is None:
            raise AssertionError("connessione %d assente" % n)
        self._manda(c, self._con_id(n, msg))

    def chiudi_connessione(self, n: int) -> None:
        c = self._conn.pop(n, None)
        if c is not None:
            try:
                c.close()
            except OSError:
                pass

    def sottoscrizioni_di(self, op: str) -> List[Dict[str, Any]]:
        return [m for _, m in self.sottoscrizioni if m.get("op") == op]

    def chiudi(self) -> None:
        self._stop = True
        for n in list(self._conn):
            self.chiudi_connessione(n)
        try:
            self.sock.close()
        except OSError:
            pass

    # ------------------------------------------------------------ interni
    def _con_id(self, n: int, msg: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(msg)
        if "id" not in d and d.get("op") in ("mcm", "ocm", "status"):
            d["id"] = self._ultimo_id.get(n, 0)
        return d

    def _accetta(self) -> None:
        while not self._stop:
            try:
                grezzo, _ = self.sock.accept()
            except OSError:
                return
            with self._lock:
                self.connessioni += 1
                n = self.connessioni
            threading.Thread(target=self._servi, args=(grezzo, n), daemon=True).start()

    @staticmethod
    def _manda(c: Any, d: Dict[str, Any]) -> None:
        c.sendall((json.dumps(d, separators=(",", ":")) + "\r\n").encode("utf-8"))

    def _servi(self, grezzo: Any, n: int) -> None:
        try:
            c = self.ctx.wrap_socket(grezzo, server_side=True)
        except OSError:
            return
        self._conn[n] = c
        buf = b""
        try:
            self._manda(c, {"op": "connection", "connectionId": "002-%012d-000001" % n})
            while not self._stop:
                pezzo = c.recv(65536)
                if not pezzo:
                    return
                buf += pezzo
                while b"\r\n" in buf:
                    riga, buf = buf.split(b"\r\n", 1)
                    if riga and not self._rispondi(c, json.loads(riga.decode("utf-8")), n):
                        return
        except OSError:
            return

    def _rispondi(self, c: Any, m: Dict[str, Any], n: int) -> bool:
        self.ricevuti.append((n, m))
        op = m.get("op")
        if op == "authentication":
            st = dict(self.autentica(n))
            st.setdefault("id", m["id"])
            self._manda(c, st)
            if st.get("connectionClosed"):
                self.chiudi_connessione(n)
                return False
            return True
        if op == "heartbeat":
            self._manda(c, {"op": "status", "id": m["id"], "statusCode": "SUCCESS",
                            "connectionClosed": False})
            return True
        if op in ("marketSubscription", "orderSubscription"):
            self.sottoscrizioni.append((n, m))
            self._ultimo_id[n] = m["id"]
            self._manda(c, {"op": "status", "id": m["id"], "statusCode": "SUCCESS",
                            "connectionClosed": False})
            for cosa in self.risposta(n, m, len(self.sottoscrizioni)):
                if cosa == CHIUDI:
                    self.chiudi_connessione(n)
                    return False
                self._manda(c, self._con_id(n, cosa))
        return True


class SessioneFinta:
    """``contratto.Sessione`` con un ``APIClient`` VERO (nessuna rete: token a mano).

    Le chiamate di scommessa (``place_orders``, ``cancel_orders``, ``replace_orders``,
    ``update_orders``) sono trappole: se il codice in prova le usa, il test lo sa."""

    def __init__(self) -> None:
        self.api = betfairlightweight.APIClient("utente_finto", "pw_finta", app_key="chiave_finta")
        self.api.set_session_token("token-finto-1")
        self.rinnovi = 0
        self.chiamate_vietate: List[str] = []
        for nome in ("place_orders", "cancel_orders", "replace_orders", "update_orders"):
            setattr(self.api.betting, nome, self._trappola(nome))

    def _trappola(self, nome: str) -> Callable[..., Any]:
        def _chiamata(*_a: Any, **_k: Any) -> Any:
            self.chiamate_vietate.append(nome)
            raise AssertionError("chiamata vietata: %s" % nome)
        return _chiamata

    def client(self) -> Any:
        return self.api

    def rinnova_se_serve(self) -> None:
        self.rinnovi += 1
        self.api.set_session_token("token-finto-%d" % (self.rinnovi + 1))

    def stato(self) -> Dict[str, Any]:
        return {"rinnovi": self.rinnovi}


@pytest.fixture
def server_stream(monkeypatch):
    """Fabbrica di server finti; ``BetfairStream`` si collega al primo creato."""
    creati: List[ServerStreamFinto] = []

    def crea(risposta: Risposta,
             autentica: Optional[Callable[[int], Dict[str, Any]]] = None) -> ServerStreamFinto:
        s = ServerStreamFinto(risposta, autentica)
        creati.append(s)
        monkeypatch.setitem(BetfairStream.HOSTS, None, "127.0.0.1")
        monkeypatch.setattr(BetfairStream, "_BetfairStream__port", s.porta)
        return s
    yield crea
    for s in creati:
        s.chiudi()


def attendi(cond: Callable[[], bool], secondi: float = 10.0) -> bool:
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


def test_il_server_finto_rifiuta_come_betfair(server_stream):
    """Il finto stesso: un'autenticazione FAILURE con ``connectionClosed`` chiude
    la connessione e la libreria vera solleva (``ListenerError``)."""
    from betfairlightweight.exceptions import ListenerError
    from betfairlightweight.streaming.listener import StreamListener

    srv = server_stream(lambda n, m, k: [], autentica=lambda n: {
        "op": "status", "statusCode": "FAILURE", "errorCode": "MAX_CONNECTION_LIMIT_EXCEEDED",
        "errorMessage": "You have exceeded your max connection limit which is: 10 connection(s).",
        "connectionClosed": True})
    api = SessioneFinta().client()
    stream = api.streaming.create_stream(unique_id=1, listener=StreamListener())
    with pytest.raises(ListenerError):
        stream.subscribe_to_orders()
    assert srv.connessioni == 1


def conforme(classe: type, protocollo: type) -> List[str]:
    """Le differenze fra ``classe`` e il protocollo del contratto (che non e'
    ``runtime_checkable``): ogni metodo del protocollo deve esistere con almeno
    gli stessi parametri posizionali, nello stesso ordine. Lista vuota = conforme."""
    import inspect

    diff: List[str] = []
    for nome, voce in vars(protocollo).items():
        if nome.startswith("_") or not callable(voce):
            continue
        impl = getattr(classe, nome, None)
        if impl is None or not callable(impl):
            diff.append("manca %s" % nome)
            continue
        attesi = [p for p in inspect.signature(voce).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        trovati = [p for p in inspect.signature(impl).parameters.values()
                   if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if [p.name for p in attesi] != [p.name for p in trovati][:len(attesi)]:
            diff.append("firma di %s: %s contro %s" % (nome, [p.name for p in attesi],
                                                       [p.name for p in trovati]))
        obbligatori_in_piu = [p.name for p in trovati[len(attesi):] if p.default is p.empty]
        if obbligatori_in_piu:
            diff.append("%s chiede in piu' %s" % (nome, obbligatori_in_piu))
    return diff


# ---------------------------------------------------------------------------
# registrazioni vere (registrazioni_banco/<ev>/<ev>.raw.jsonl.gz, o la copia
# scompattata in _live_raw/<ev>/ se c'e': stessi byte)
# ---------------------------------------------------------------------------
REGISTRAZIONI = ("35760084", "35797769")


def radice_repo() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


def righe_registrazione(ev: str):
    """Le righe ``mcm`` della registrazione (testo, come le scrive il tee raw)."""
    import gzip

    piana = os.path.join(radice_repo(), "_live_raw", ev, "%s.raw.jsonl" % ev)
    if os.path.exists(piana):
        with open(piana, "r", encoding="utf-8") as fh:
            for riga in fh:
                if riga.strip():
                    yield riga
        return
    gz = os.path.join(radice_repo(), "registrazioni_banco", ev, "%s.raw.jsonl.gz" % ev)
    if not os.path.exists(gz):
        pytest.skip("registrazione %s assente" % ev)
    with gzip.open(gz, "rt", encoding="utf-8") as fh:
        for riga in fh:
            if riga.strip():
                yield riga


def libri_registrazione(ev: str):
    """(pt in secondi, [MarketBook, ...]) per ogni messaggio, dal listener VERO di
    betfairlightweight (``StreamListener`` -> ``MarketStream`` -> ``MarketBookCache``
    -> ``MarketBook``), come ``HistoricalStream`` (id di stream 0)."""
    import queue as _q

    from betfairlightweight.streaming.listener import StreamListener

    coda: "_q.Queue[List[Any]]" = _q.Queue()
    li = StreamListener(output_queue=coda, max_latency=None)
    li.register_stream(0, "marketSubscription")
    t = 0.0
    for riga in righe_registrazione(ev):
        li.on_data(riga)
        pt = json.loads(riga).get("pt")
        if isinstance(pt, (int, float)):
            t = max(t, pt / 1000.0)
        libri: List[Any] = []
        while not coda.empty():
            libri.extend(coda.get_nowait())
        if libri:
            yield t, libri


def prima_immagine(ev: str) -> Dict[str, Any]:
    """Il primo messaggio ``mcm`` (SUB_IMAGE) della registrazione, decodificato."""
    for riga in righe_registrazione(ev):
        d = json.loads(riga)
        if d.get("ct") == "SUB_IMAGE":
            return d
    raise AssertionError("nessuna SUB_IMAGE in %s" % ev)
