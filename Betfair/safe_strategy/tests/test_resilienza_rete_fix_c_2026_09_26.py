"""FIX-C (26/09/2026) - RESILIENZA ALLA CADUTA DI RETE del feed unico (scanner 47336).

Il fatto (referti `AUDIT_2026-09-25/E2E_FASE2_BOT_PAPER_2026-09-26.md` e campioni
`e2e_fase2/canali_ordini/scanner_*.jsonl`): alle 10:41:41Z la rete del PC e' caduta
per 28-55 s e il DNS ha fallito fino alle ~10:48Z. Da quel momento lo scanner ha
pubblicato ``source=rest``, ``stream_markets=0``, shard con ``subscribed=0`` e
``eta_resub_s`` che cresceva (ultimo subscribe 10:40:00Z) e ``quote assenti da
14262s`` - cioe' NE' lo stream NE' il REST hanno piu' consegnato un prezzo, per
4 ore, fino al riavvio dell'app.

La causa nel codice (prima di questo fix):
  * ``service.py`` ``Scanner.tick``: ``keep_alive(self.client)`` e poi
    ``self.keepalive_ts = now_mono`` SEMPRE, anche quando il keepAlive falliva
    (``auth.keep_alive`` ingoia l'eccezione): il tentativo successivo arrivava
    solo dopo UN PERIODO INTERO (900 s);
  * su betfair.it la sessione scade 20 minuti dopo l'ultimo keepAlive riuscito
    (``betfairlightweight`` ``SESSION_TIMEOUT[italy] = 20*60``; le chiamate API
    non la prolungano): keepAlive fallito a rete giu' + 900 s di attesa = sessione
    SCADUTA, e un keepAlive su una sessione scaduta risponde ``NO_SESSION``
    per sempre. Nessuno rifaceva il login: REST (``INVALID_SESSION_INFORMATION``)
    e autenticazione dello stream fallivano per tutto il resto della giornata.

I finti di questo file hanno i TIPI VERI di betfairlightweight
(``APIError(None, exception=ConnectionError)`` come lo solleva
``endpoints/keepalive.py`` a rete giu', ``KeepAliveError`` con la risposta
``{"status": "FAIL", "error": "NO_SESSION"}``, ``ListenerError`` / ``SocketError``
dello stream) e leggono il token dal client come ``Streaming.create_stream``.
"""
from __future__ import annotations

import socket
import threading
import time
from typing import Any, List, Optional

import pytest
import requests
from betfairlightweight.exceptions import (
    APIError,
    KeepAliveError,
    ListenerError,
    SocketError,
)

from Betfair.safe_strategy import service
from Betfair.safe_strategy import stream as ST


# ===========================================================================
# I FINTI: la rete, la sessione Betfair (.it) e lo stream
# ===========================================================================
class Rete:
    """Orologio simulato + interruttore della rete (DNS compreso)."""

    def __init__(self) -> None:
        self.t = 1000.0
        self.giu = False

    def ora(self) -> float:
        return self.t


class ClientBetfairFinto:
    """Un ``betfairlightweight.APIClient`` .it ridotto alle porte che si usano.

    Regole della sessione come su betfair.it: vale ``session_timeout`` secondi
    dall'ultimo keepAlive/login RIUSCITO; un keepAlive su sessione scaduta
    risponde ``NO_SESSION``; a rete giu' ogni chiamata solleva l'``APIError`` che
    betfairlightweight costruisce attorno a ``requests.ConnectionError``.
    """

    session_timeout = 20 * 60           # betfairlightweight SESSION_TIMEOUT[italy]

    def __init__(self, rete: Rete) -> None:
        self.rete = rete
        self.app_key = "APPKEY"
        self._n = 0
        self.session_token = self._nuovo_token()
        self._rinnovata = rete.ora()
        self.chiamate: List[str] = []
        self.streaming = _StreamingFinto(self)

    def _nuovo_token(self) -> str:
        self._n += 1
        return f"TOKEN-SEGRETO-{self._n}"

    def sessione_valida(self) -> bool:
        return self.rete.ora() - self._rinnovata < self.session_timeout

    def _rete_giu(self) -> None:
        if self.rete.giu:
            raise APIError(None, exception=requests.ConnectionError(
                "HTTPSConnectionPool(host='identitysso.betfair.it'): Max retries exceeded "
                "(NameResolutionError: [Errno 11001] getaddrinfo failed)"))

    def keep_alive(self):
        self.chiamate.append("keep_alive")
        self._rete_giu()
        if not self.sessione_valida():
            raise KeepAliveError({"token": self.session_token, "product": "APPKEY",
                                  "status": "FAIL", "error": "NO_SESSION"})
        self._rinnovata = self.rete.ora()
        return {"status": "SUCCESS"}

    def login(self):
        self.chiamate.append("login")
        self._rete_giu()
        self.session_token = self._nuovo_token()
        self._rinnovata = self.rete.ora()
        return {"loginStatus": "SUCCESS"}


class _StreamingFinto:
    """``client.streaming``: come il vero, legge il token AL MOMENTO della
    creazione (``endpoints/streaming.py`` -> ``session_token=self.client.session_token``)."""

    def __init__(self, client: ClientBetfairFinto) -> None:
        self.client = client
        self.creati: List["StreamCheMuore"] = []

    def create_stream(self, listener=None, **kw):
        st = StreamCheMuore(self.client, token=self.client.session_token)
        self.creati.append(st)
        return st


class StreamCheMuore:
    """Un BetfairStream finto: a rete giu' il connect fallisce con
    ``socket.gaierror`` (getaddrinfo), con un token scaduto l'autenticazione
    chiude la connessione con ``ListenerError`` (NO_SESSION), altrimenti
    ``start()`` blocca finche' la rete non cade (``SocketError``) o finche'
    non lo si ferma."""

    def __init__(self, client: ClientBetfairFinto, token: str) -> None:
        self.client = client
        self.token = token
        self._running = False
        self._socket = None
        self.sottoscritti: List[str] = []
        self._fermo = threading.Event()

    def _connetti(self) -> None:
        if self.client.rete.giu:
            raise socket.gaierror(11001, "getaddrinfo failed")
        if self.token != self.client.session_token or not self.client.sessione_valida():
            raise ListenerError("conn-1", '{"op":"status","statusCode":"FAILURE",'
                                '"errorCode":"NO_SESSION","connectionClosed":true}')
        self._running = True
        self._socket = object()

    def subscribe_to_markets(self, market_filter=None, market_data_filter=None,
                             conflate_ms=None, heartbeat_ms=None, **kw):
        if not self._running:
            self._connetti()
        self.sottoscritti = list(market_filter.get("marketIds") or [])

    def start(self):
        while not self._fermo.is_set():
            if self.client.rete.giu:
                self._running = False
                raise SocketError("[Connect: 1]: Socket timed out")
            self._fermo.wait(0.005)

    def stop(self):
        self._running = False
        self._socket = None
        self._fermo.set()


# ===========================================================================
# 1. LA CAUSA: la sessione deve sopravvivere a una caduta di rete
# ===========================================================================
def scanner_con_client(client: ClientBetfairFinto, monkeypatch, rete: Rete) -> service.Scanner:
    """Uno Scanner vero, dry, senza stream; tutte le chiamate di dati spente:
    resta SOLO la gestione della sessione, che e' cio' che si misura."""
    monkeypatch.setattr(service.time, "monotonic", rete.ora)
    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    scan = service.Scanner(api_client=client, dry=True, use_stream=False)
    scan.refresh_catalogue = lambda sport: None            # type: ignore[method-assign]
    scan.poll_books = lambda sport, ids: None              # type: ignore[method-assign]
    scan.poll_scores = lambda: None                        # type: ignore[method-assign]
    scan.poll_timelines = lambda: None                     # type: ignore[method-assign]
    scan.hydrate_schede = lambda now=None: 0               # type: ignore[method-assign]
    return scan


def gira(scan: service.Scanner, rete: Rete, fino_a: float, passo: float = 5.0,
         giu_da: Optional[float] = None, giu_a: Optional[float] = None) -> float:
    """Fa girare lo scanner; ritorna i SECONDI in cui, a rete SU, la sessione
    Betfair del feed era scaduta (= feed senza quote per colpa nostra)."""
    cieco = 0.0
    while rete.t < fino_a:
        rete.t += passo
        rete.giu = giu_da is not None and giu_da <= rete.t < (giu_a or 0.0)
        scan.tick()
        if not rete.giu and not scan.client.sessione_valida():
            cieco += passo
    return cieco


def test_rete_giu_al_momento_del_keepalive_la_sessione_resta_viva(monkeypatch):
    """Il 26/09: rete giu' proprio quando toccava il keepAlive. Dopo il rientro
    lo scanner deve avere una sessione VALIDA (keepAlive ritentato con backoff
    prima della scadenza dei 20', o login rifatto) e non restare cieco."""
    rete = Rete()
    client = ClientBetfairFinto(rete)
    scan = scanner_con_client(client, monkeypatch, rete)
    inizio = rete.t
    # rete giu' per 60 s a cavallo del primo keepAlive (a +900 s), poi su
    cieco = gira(scan, rete, fino_a=inizio + 4 * 3600, giu_da=inizio + 890, giu_a=inizio + 950)
    # a rete su la sessione non deve MAI risultare scaduta: il keepAlive
    # ritentato arriva prima dei 20' (con il ritentativo a un periodo intero
    # il feed restava senza sessione per ~10 minuti prima del login)
    assert cieco == 0.0, f"sessione scaduta per {cieco:.0f}s a rete su"
    assert client.sessione_valida(), (
        "dopo la caduta di rete la sessione Betfair e' scaduta e nessuno l'ha rifatta: "
        "lo scanner resta senza quote (REST e stream) per il resto della giornata")


def test_sessione_gia_scaduta_si_rifa_il_login(monkeypatch):
    """Rete giu' OLTRE i 20' di vita della sessione: al rientro il keepAlive
    risponde NO_SESSION e l'unica via e' il login."""
    rete = Rete()
    client = ClientBetfairFinto(rete)
    scan = scanner_con_client(client, monkeypatch, rete)
    inizio = rete.t
    gira(scan, rete, fino_a=inizio + 3 * 3600, giu_da=inizio + 890, giu_a=inizio + 890 + 1500)
    assert client.sessione_valida()
    assert "login" in client.chiamate


def test_a_regime_nessuna_chiamata_betfair_in_piu(monkeypatch):
    """Regola del feed unico: senza cadute il keepAlive resta UNO per periodo
    (900 s), nessun login, nessun ritentativo."""
    rete = Rete()
    client = ClientBetfairFinto(rete)
    scan = scanner_con_client(client, monkeypatch, rete)
    inizio = rete.t
    gira(scan, rete, fino_a=inizio + 3 * 3600)
    assert client.chiamate.count("login") == 0
    # uno per periodo (11 o 12 a seconda di dove cade il passo del giro), mai di piu'
    periodi = int(3 * 3600 // 900)
    assert client.chiamate.count("keep_alive") in (periodi - 1, periodi)


def test_ritentativi_a_rete_giu_hanno_un_backoff(monkeypatch):
    """A rete giu' non si martella: al massimo un tentativo ogni 15-60 s."""
    rete = Rete()
    client = ClientBetfairFinto(rete)
    scan = scanner_con_client(client, monkeypatch, rete)
    inizio = rete.t
    gira(scan, rete, fino_a=inizio + 900 + 600, passo=1.0,
         giu_da=inizio + 890, giu_a=inizio + 900 + 600)
    tentativi = client.chiamate.count("keep_alive") + client.chiamate.count("login")
    # 600 s di rete giu' con backoff 15/30/60/60...: una dozzina di tentativi, non 600
    assert 3 <= tentativi <= 15, tentativi


# ===========================================================================
# 2. il custode della sessione (Betfair/stream/auth.py)
# ===========================================================================
def test_custode_non_riporta_mai_il_token():
    from Betfair.stream.auth import CustodeSessione

    rete = Rete()
    client = ClientBetfairFinto(rete)
    c = CustodeSessione(client, periodo_s=900.0, ora=rete.ora)
    rete.t += 2000.0                    # sessione scaduta
    rete.giu = True
    assert c.tick() == "ko"
    rete.giu = False
    client._rinnovata = -1e9            # la sessione sul server e' morta
    esito = c.tick(rete.t + 60.0)
    assert esito == "relogin"
    testo = repr(c.stato(rete.t + 60.0))
    assert "TOKEN-SEGRETO" not in testo


def test_custode_no_session_dal_server_rifa_il_login_nello_stesso_giro():
    """La sessione puo' morire sul server prima del previsto (login altrove,
    revoca): keepAlive risponde NO_SESSION e il custode fa il login SUBITO,
    non al ritentativo dopo."""
    from Betfair.stream.auth import CustodeSessione

    rete = Rete()
    client = ClientBetfairFinto(rete)
    c = CustodeSessione(client, periodo_s=900.0, ora=rete.ora)
    rete.t += 900.0
    client._rinnovata = -1e9                     # morta sul server, giovane per il custode
    assert c.tick() == "relogin"
    assert client.chiamate == ["keep_alive", "login"] and client.sessione_valida()


def test_custode_login_preventivo_al_90_per_cento_della_vita():
    """Senza nessun errore: se dall'ultimo rinnovo riuscito e' passato almeno
    il 90% della vita della sessione (1200 s .it -> 1080 s), il custode rifa'
    il LOGIN invece del keepAlive (che potrebbe gia' dire NO_SESSION). Sotto
    la soglia fa il keepAlive normale. La sessione sul server qui e' ancora
    valida: il login e' davvero PREVENTIVO, non una reazione a un errore."""
    from Betfair.stream.auth import CustodeSessione

    rete = Rete()
    t0 = rete.t
    assert ClientBetfairFinto.session_timeout == 1200

    # sotto il 90% (1000 s): keepAlive, nessun login
    client_a = ClientBetfairFinto(rete)
    a = CustodeSessione(client_a, periodo_s=900.0, ora=rete.ora)
    assert a.tick(t0 + 1000.0) == "ok"
    assert client_a.chiamate == ["keep_alive"]

    # oltre il 90% (1081 s), senza errori: login preventivo
    client_b = ClientBetfairFinto(rete)
    b = CustodeSessione(client_b, periodo_s=900.0, ora=rete.ora)
    rete.t = t0 + 1081.0
    assert client_b.sessione_valida()               # il server l'accetterebbe ancora
    assert b.tick() == "relogin"
    assert client_b.chiamate == ["login"]
    assert b.stato()["relogin"] == 1 and b.stato()["fallimenti"] == 0


def test_custode_errore_di_sessione_anticipa_il_rinnovo():
    """Un ``INVALID_SESSION_INFORMATION`` dal REST o dallo stream non aspetta
    il periodo: il giro dopo si rifa' la sessione."""
    from Betfair.stream.auth import CustodeSessione, e_errore_di_sessione

    rete = Rete()
    client = ClientBetfairFinto(rete)
    c = CustodeSessione(client, periodo_s=900.0, ora=rete.ora)
    assert c.tick() is None                         # non e' ora
    errore = APIError({"error": {"code": -32099, "data": {"APINGException": {
        "errorCode": "INVALID_SESSION_INFORMATION"}}}}, method="SportsAPING/v1.0/listMarketBook")
    assert e_errore_di_sessione(errore)
    assert not e_errore_di_sessione(APIError(None, exception=requests.ConnectionError("x")))
    assert c.segnala_errore(errore) is True
    assert c.tick() == "relogin"
    assert client.chiamate == ["login"]


# ===========================================================================
# 3. il cambio di fonte si DICE: scanner_stato + live_alerts, una volta
# ===========================================================================
def test_sorveglia_fonte_un_avviso_per_ripiego_e_uno_per_rientro():
    f = service.SorvegliaFonte()
    eventi = []
    t = 0.0
    for _ in range(60):                               # stream stabile
        t += 1.0
        eventi.append(f.osserva("stream", t))
    for _ in range(60):                               # rete giu' 60 s: REST
        t += 1.0
        eventi.append(f.osserva("rest", t, motivo="stream senza book"))
    for _ in range(60):                               # rientro
        t += 1.0
        eventi.append(f.osserva("stream", t))
    avvisi = [e for e in eventi if e]
    assert [a["code"] for a in avvisi] == ["FEED_RIPIEGO_REST", "FEED_RIENTRO_STREAM"]
    assert avvisi[0]["level"] == "WARN" and avvisi[1]["level"] == "INFO"
    assert "stream senza book" in avvisi[0]["message"]
    st = f.stato(t)
    assert st["attuale"] == "stream" and st["ultimo_cambio"]["a"] == "stream"


def test_sorveglia_fonte_non_avvisa_per_uno_scatto_breve():
    """Il 26/09 alle 09:21Z un solo mercato core senza quote per 30 s ha fatto
    ``source=rest`` per un campione: non e' una caduta, niente allarme."""
    f = service.SorvegliaFonte()
    t = 0.0
    avvisi = []
    for fonte in ["stream"] * 20 + ["rest"] * 15 + ["stream"] * 20:
        t += 1.0
        e = f.osserva(fonte, t)
        if e:
            avvisi.append(e)
    assert avvisi == []


def test_sorveglia_fonte_avvio_non_e_un_ripiego():
    """All'avvio (e dopo ogni riavvio del watchdog) lo stream parte dopo il
    warm-up dei cataloghi: 90 s di REST iniziale non sono un ripiego. Se
    invece lo stream non parte MAI, oltre la grazia lo si dice, una volta."""
    f = service.SorvegliaFonte()
    t, avvisi = 0.0, []
    for fonte in ["rest"] * 90 + ["stream"] * 60:
        t += 1.0
        e = f.osserva(fonte, t)
        if e:
            avvisi.append(e["code"])
    assert avvisi == []
    g = service.SorvegliaFonte()
    t, avvisi = 0.0, []
    for _ in range(400):
        t += 1.0
        e = g.osserva("rest", t)
        if e:
            avvisi.append(e["code"])
    assert avvisi == ["FEED_RIPIEGO_REST"]


def test_tick_e_stato_portano_il_ripiego_e_il_rientro(monkeypatch):
    """Integrazione nello Scanner: pool che smette di servire e poi torna;
    ``publish_status`` scrive gli avvisi UNA volta e la fonte nello stato."""
    rete = Rete()
    client = ClientBetfairFinto(rete)
    scan = scanner_con_client(client, monkeypatch, rete)

    class Pool:
        serve = True
        capacity = 720

        def set_markets(self, ids): pass
        def drain(self): return []
        def covered_ids(self): return set()
        def subscribed_ids(self): return set()
        def serving(self): return self.serve
        def healthy(self): return self.serve
        def active_connections(self): return 1 if self.serve else 0
        def stato_shard(self): return []
        def stop(self): pass

    pool = Pool()
    scan.stream = pool
    scritti: list = []
    monkeypatch.setattr(service, "_scrivi_avviso", lambda l, c, m: scritti.append((l, c, m)))
    stati: list = []
    monkeypatch.setattr(service.scan_db, "upsert_status", lambda p: stati.append(p))
    scan.dry = False
    scan.publish = lambda now: (0, 0)                   # type: ignore[method-assign]
    scan.hydrate_pre_ko = lambda: 0                     # type: ignore[method-assign]
    for i in range(240):
        rete.t += 1.0
        pool.serve = not (60 <= i < 120)
        scan.tick()
        if i % 10 == 0:
            scan.publish_status(0)
    scan.publish_status(0)
    codici = [c for _, c, _ in scritti]
    assert codici == ["FEED_RIPIEGO_REST", "FEED_RIENTRO_STREAM"], codici
    ultimo = stati[-1]
    assert ultimo["source"] == "stream"
    assert ultimo["fonte"]["attuale"] == "stream"
    assert "sessione" in ultimo and ultimo["sessione"]["fallimenti"] == 0


def test_avviso_non_scritto_a_rete_giu_si_ritenta(monkeypatch):
    """Il ripiego nasce proprio quando la rete e' giu': l'avviso non si perde,
    resta in coda e parte al primo stato scritto dopo il rientro. Una volta."""
    rete = Rete()
    client = ClientBetfairFinto(rete)
    scan = scanner_con_client(client, monkeypatch, rete)
    scan.dry = False
    monkeypatch.setattr(service.scan_db, "upsert_status", lambda p: None)
    scritti: list = []
    giu = {"v": True}

    def scrivi(level, code, msg):
        if giu["v"]:
            raise requests.ConnectionError("getaddrinfo failed")
        scritti.append(code)

    monkeypatch.setattr(service, "_scrivi_avviso", scrivi)
    scan._avvisi_in_attesa.append({"level": "WARN", "code": "FEED_RIPIEGO_REST", "message": "m"})
    scan.publish_status(0)
    scan.publish_status(0)
    assert scritti == [] and len(scan._avvisi_in_attesa) == 1
    giu["v"] = False
    scan.publish_status(0)
    scan.publish_status(0)
    assert scritti == ["FEED_RIPIEGO_REST"]
    assert len(scan._avvisi_in_attesa) == 0


# ===========================================================================
# 4. lo stream: muore, ritenta con backoff, TORNA (e con il token nuovo)
# ===========================================================================
def test_shard_rientra_dopo_rete_giu_e_sessione_rifatta(monkeypatch):
    """Il thread dello shard vive una caduta vera: SocketError sul socket,
    getaddrinfo al riconnettersi, NO_SESSION finche' la sessione non e'
    rifatta; poi si risottoscrive col token NUOVO e lo stato lo racconta."""
    monkeypatch.setattr(ST, "_RECONNECT_BACKOFF", (0.01, 0.01, 0.01))
    rete = Rete()
    client = ClientBetfairFinto(rete)
    shard = ST.StreamShard(client, index=0)
    shard.set_markets({"1.100", "1.200"})
    try:
        _attendi(lambda: shard._subscribed == {"1.100", "1.200"})
        primo = client.streaming.creati[-1]
        rete.giu = True                                     # la rete cade
        _attendi(lambda: shard._subscribed == set() and shard.stato()["riconnessioni"] >= 1)
        _attendi(lambda: "gaierror" in (shard.stato()["ultimo_errore"] or ""))
        client._rinnovata = -1e9                            # sessione morta sul server
        rete.giu = False                                    # la rete torna
        _attendi(lambda: "ListenerError" in (shard.stato()["ultimo_errore"] or ""))
        assert shard._subscribed == set(), "con la sessione morta non si sottoscrive"
        client.login()                                      # il custode rifa' la sessione
        _attendi(lambda: shard._subscribed == {"1.100", "1.200"})
        ultimo = client.streaming.creati[-1]
        assert ultimo is not primo and ultimo.token == client.session_token
        st = shard.stato()
        assert st["subscribed"] == 2 and st["ultimo_errore"] is None
    finally:
        shard.stop()


def _attendi(cond, timeout: float = 5.0) -> None:
    fine = time.monotonic() + timeout
    while time.monotonic() < fine:
        if cond():
            return
        time.sleep(0.005)
    raise AssertionError("condizione mai raggiunta")
