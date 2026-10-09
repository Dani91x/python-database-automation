"""Il Betfair FINTO dei test W1-A1, a livello di TRASPORTO HTTP, e le sue prove.

L'``APIClient`` e' quello vero di betfairlightweight, costruito da
``auth.build_client`` (il codice di oggi); la sua ``requests.Session`` e' vera e
monta un ``HTTPAdapter`` che, al posto della rete, risponde come Betfair:

  * corpi JSON nel formato UFFICIALE (certlogin, keepAlive, logout, JSON-RPC
    ``listMarketBook``/``listCurrentOrders``/``listMarketProfitAndLoss``/
    ``placeOrders``..., errori ``APINGException`` con ``errorCode``);
  * risposta compressa GZIP con ``Content-Encoding: gzip`` dentro un
    ``urllib3.HTTPResponse`` vero: la decompressione la fa requests come in rete;
  * regole di Betfair applicate dal finto con una tabella PROPRIA (indipendente
    da ``limiti.py``): 200 punti di peso (``TOO_MUCH_DATA``), 3 richieste
    concorrenti per conto sui metodi contesi (``TOO_MANY_REQUESTS``), sessione
    .it di 1200 s rinnovata solo da keepAlive/login (``NO_SESSION``,
    ``INVALID_SESSION_INFORMATION``), 100 login al minuto poi ban di 20 minuti
    (``TEMPORARY_BAN_TOO_MANY_REQUESTS``);
  * guasti programmabili per metodo (rete, timeout, codici di errore, HTTP 503).

Il file contiene anche le prove del finto stesso (che i suoi JSON diventino
oggetti VERI di betfairlightweight e che le sue regole scattino).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import collections
import gzip
import io
import json
import threading
import time
from typing import Any, Deque, Dict, List, Optional

import pytest
import requests
from urllib3.response import HTTPResponse

# ---------------------------------------------------------------------------
# tabella dei pesi DEL FINTO (scritta dalla doc ufficiale, NON importata da limiti.py)
# ---------------------------------------------------------------------------
_PESI_FINTO = {"": 2, "SP_AVAILABLE": 3, "SP_TRADED": 7, "EX_BEST_OFFERS": 5, "EX_ALL_OFFERS": 17,
               "EX_TRADED": 17, "EX_BEST_OFFERS+EX_TRADED": 20, "EX_ALL_OFFERS+EX_TRADED": 32}
_CONTESI_FINTO = ("listCurrentOrders", "listMarketProfitAndLoss")
VITA_SESSIONE_FINTO_S = 1200.0


def peso_finto(price_projection: Optional[dict]) -> float:
    """Peso per mercato secondo il finto (con bestPricesDepth: x profondita'/3)."""
    pp = price_projection or {}
    voci = set(pp.get("priceData") or [])
    if "EX_ALL_OFFERS" in voci:
        voci.discard("EX_BEST_OFFERS")
    peso = 0.0
    tr = "EX_TRADED" in voci
    if "EX_ALL_OFFERS" in voci:
        peso += _PESI_FINTO["EX_ALL_OFFERS+EX_TRADED" if tr else "EX_ALL_OFFERS"]
    elif "EX_BEST_OFFERS" in voci:
        base = _PESI_FINTO["EX_BEST_OFFERS+EX_TRADED" if tr else "EX_BEST_OFFERS"]
        d = (pp.get("exBestOffersOverrides") or {}).get("bestPricesDepth")
        peso += base * (d / 3.0) if d else base
    elif tr:
        peso += _PESI_FINTO["EX_TRADED"]
    for sp in ("SP_AVAILABLE", "SP_TRADED"):
        if sp in voci:
            peso += _PESI_FINTO[sp]
    return peso or float(_PESI_FINTO[""])


class OrologioFinto:
    """Orologio monotono finto, condiviso da finto, custode e freno."""

    def __init__(self, t0: float = 1000.0) -> None:
        self.t = float(t0)
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self.t

    def avanza(self, s: float) -> None:
        with self._lock:
            self.t += float(s)


def book_ufficiale(market_id: str) -> Dict[str, Any]:
    """Un MarketBook nel formato JSON di ``listMarketBook`` (EX_BEST_OFFERS)."""
    base = (int(market_id.split(".")[-1]) % 50) / 100.0
    runners = []
    for i, sel in enumerate((47972, 47973, 58805)):
        b = round(1.5 + base + i, 2)
        runners.append({
            "selectionId": sel, "handicap": 0.0, "status": "ACTIVE",
            "lastPriceTraded": b, "totalMatched": 1000.0 + i,
            "ex": {"availableToBack": [{"price": b, "size": 120.5}, {"price": round(b - 0.02, 2), "size": 40.0}],
                   "availableToLay": [{"price": round(b + 0.02, 2), "size": 88.0}],
                   "tradedVolume": []},
        })
    return {"marketId": market_id, "isMarketDataDelayed": False, "status": "OPEN", "betDelay": 0,
            "bspReconciled": False, "complete": True, "inplay": False, "numberOfWinners": 1,
            "numberOfRunners": 3, "numberOfActiveRunners": 3, "lastMatchTime": "2026-10-09T12:00:00.000Z",
            "totalMatched": 12345.67, "totalAvailable": 45678.9, "crossMatching": True,
            "runnersVoidable": False, "version": 4567890123, "runners": runners}


def errore_aping(codice: str, id_rpc: int = 1) -> Dict[str, Any]:
    """Un errore APINGException JSON-RPC come lo manda Betfair (HTTP 200)."""
    angx = {"TOO_MUCH_DATA": "ANGX-0001", "INVALID_INPUT_DATA": "ANGX-0002",
            "INVALID_SESSION_INFORMATION": "ANGX-0003", "NO_APP_KEY": "ANGX-0004",
            "NO_SESSION": "ANGX-0005", "UNEXPECTED_ERROR": "ANGX-0006", "INVALID_APP_KEY": "ANGX-0007",
            "TOO_MANY_REQUESTS": "ANGX-0008", "SERVICE_BUSY": "ANGX-0009"}.get(codice, "ANGX-0006")
    return {"jsonrpc": "2.0", "id": id_rpc, "error": {
        "code": -32099, "message": angx,
        "data": {"exceptionname": "APINGException",
                 "APINGException": {"requestUUID": "prdang001-00000000-0000abcd",
                                    "errorCode": codice, "errorDetails": "finto"}}}}


class ServerBetfairFinto:
    """Lo stato del Betfair finto (token, contatori, regole, guasti, registro)."""

    def __init__(self, ora: Optional[OrologioFinto] = None, *, applica_concorrenza: bool = True) -> None:
        self.ora = ora or OrologioFinto()
        self.applica_concorrenza = applica_concorrenza
        self._lock = threading.Lock()
        self.richieste: List[Dict[str, Any]] = []
        self.token_rinnovo: Dict[str, float] = {}
        self.login_ok: Deque[float] = collections.deque()
        self.ban_fino: Optional[float] = None
        self.n_token = 0
        self.guasti: Dict[str, Deque[str]] = collections.defaultdict(collections.deque)
        self.ritardo_s: Dict[str, float] = {}
        self.avanza_orologio_s: Dict[str, float] = {}
        self.in_volo: Dict[str, int] = collections.defaultdict(int)
        self.max_in_volo: Dict[str, int] = collections.defaultdict(int)
        self.contesi_in_volo = 0
        self.max_contesi_in_volo = 0
        self.sessioni_http: set = set()

    # ------------------------------------------------------------ comodi
    def conta(self, tipo: str) -> int:
        with self._lock:
            return sum(1 for r in self.richieste if r["tipo"] == tipo)

    def tipi(self) -> List[str]:
        with self._lock:
            return [r["tipo"] for r in self.richieste]

    def guasta(self, tipo: str, *voci: str) -> None:
        self.guasti[tipo].extend(voci)

    def invalida_tutti(self) -> None:
        with self._lock:
            self.token_rinnovo.clear()

    # ------------------------------------------------------------ regole
    def _token_valido(self, tok: Optional[str]) -> bool:
        t = self.token_rinnovo.get(tok or "")
        return t is not None and self.ora() - t < VITA_SESSIONE_FINTO_S

    def _login(self) -> Dict[str, Any]:
        a = self.ora()
        while self.login_ok and self.login_ok[0] <= a - 60.0:
            self.login_ok.popleft()
        if self.ban_fino is not None and a < self.ban_fino:
            return {"loginStatus": "TEMPORARY_BAN_TOO_MANY_REQUESTS"}
        if len(self.login_ok) >= 100:
            self.ban_fino = a + 1200.0
            return {"loginStatus": "TEMPORARY_BAN_TOO_MANY_REQUESTS"}
        self.n_token += 1
        tok = f"TOKSEGRETO{self.n_token:04d}"
        self.token_rinnovo[tok] = a
        self.login_ok.append(a)
        return {"sessionToken": tok, "loginStatus": "SUCCESS"}

    def _keep_alive(self, tok: Optional[str]) -> Dict[str, Any]:
        if self._token_valido(tok):
            self.token_rinnovo[tok or ""] = self.ora()
            return {"token": tok, "product": "APPKEY", "status": "SUCCESS", "error": ""}
        return {"token": tok, "product": "APPKEY", "status": "FAIL", "error": "NO_SESSION"}

    def _rpc(self, metodo: str, params: Dict[str, Any], tok: Optional[str]) -> Dict[str, Any]:
        if not self._token_valido(tok):
            return errore_aping("INVALID_SESSION_INFORMATION")
        if metodo == "listMarketBook":
            ids = params.get("marketIds") or []
            if peso_finto(params.get("priceProjection")) * len(ids) > 200:
                return errore_aping("TOO_MUCH_DATA")
            return {"jsonrpc": "2.0", "id": 1, "result": [book_ufficiale(m) for m in ids]}
        if metodo == "listMarketProfitAndLoss":
            ids = params.get("marketIds") or []
            if 4 * len(ids) > 200:
                return errore_aping("TOO_MUCH_DATA")
            return {"jsonrpc": "2.0", "id": 1, "result": [
                {"marketId": m, "profitAndLosses": [{"selectionId": 47972, "ifWin": 1.5}]} for m in ids]}
        if metodo == "listCurrentOrders":
            return {"jsonrpc": "2.0", "id": 1, "result": {"currentOrders": [], "moreAvailable": False}}
        if metodo == "listEventTypes":
            return {"jsonrpc": "2.0", "id": 1, "result": [
                {"eventType": {"id": "1", "name": "Soccer"}, "marketCount": 1234}]}
        if metodo == "getAccountFunds":
            return {"jsonrpc": "2.0", "id": 1, "result": {
                "availableToBetBalance": 100.0, "exposure": 0.0, "retainedCommission": 0.0,
                "exposureLimit": -10000.0, "discountRate": 0.0, "pointsBalance": 0, "wallet": "UK"}}
        if metodo in ("placeOrders", "cancelOrders", "replaceOrders", "updateOrders"):
            istr = (params.get("instructions") or [{}])[0]
            piazzato = {"status": "SUCCESS", "instruction": istr, "betId": "345678901234",
                        "placedDate": "2026-10-09T12:00:00.000Z", "averagePriceMatched": 0.0,
                        "sizeMatched": 0.0, "orderStatus": "EXECUTABLE"}
            annullato = {"status": "SUCCESS", "instruction": {"betId": istr.get("betId")},
                         "sizeCancelled": 2.0, "cancelledDate": "2026-10-09T12:00:01.000Z"}
            report = {"placeOrders": piazzato, "cancelOrders": annullato,
                      "updateOrders": {"status": "SUCCESS", "instruction": istr},
                      "replaceOrders": {"status": "SUCCESS", "cancelInstructionReport": annullato,
                                        "placeInstructionReport": {**piazzato, "instruction": {
                                            "selectionId": 47972, "handicap": 0.0, "side": "BACK",
                                            "orderType": "LIMIT", "limitOrder": {
                                                "size": 2.0, "price": istr.get("newPrice"),
                                                "persistenceType": "LAPSE"}}}}}[metodo]
            return {"jsonrpc": "2.0", "id": 1, "result": {
                "customerRef": params.get("customerRef"), "status": "SUCCESS",
                "marketId": params.get("marketId"), "instructionReports": [report]}}
        return {"jsonrpc": "2.0", "id": 1, "result": []}

    # ------------------------------------------------------------ ingresso
    def rispondi(self, request: requests.PreparedRequest, cert: Any, id_sessione: int) -> tuple:
        """(status, corpo dict) oppure solleva un'eccezione di trasporto."""
        url = request.url or ""
        tok = request.headers.get("X-Authentication")
        corpo = request.body
        if isinstance(corpo, bytes):
            corpo = corpo.decode("utf-8")
        if "certlogin" in url:
            tipo, params = "login", {}
        elif "keepAlive" in url:
            tipo, params = "keepAlive", {}
        elif "logout" in url:
            tipo, params = "logout", {}
        else:
            rpc = json.loads(corpo or "{}")
            tipo = str(rpc.get("method", "")).rsplit("/", 1)[-1]
            params = rpc.get("params") or {}
        conteso = tipo in _CONTESI_FINTO or (tipo == "listMarketBook" and (
            params.get("orderProjection") is not None or params.get("matchProjection") is not None))
        with self._lock:
            self.richieste.append({"tipo": tipo, "url": url, "headers": dict(request.headers),
                                   "params": params, "cert": cert, "t": self.ora(),
                                   "thread": threading.get_ident(), "sessione_http": id_sessione})
            self.sessioni_http.add(id_sessione)
            guasto = self.guasti[tipo].popleft() if self.guasti.get(tipo) else None
            self.in_volo[tipo] += 1
            self.max_in_volo[tipo] = max(self.max_in_volo[tipo], self.in_volo[tipo])
            if conteso:
                self.contesi_in_volo += 1
                self.max_contesi_in_volo = max(self.max_contesi_in_volo, self.contesi_in_volo)
            troppi = conteso and self.applica_concorrenza and self.contesi_in_volo > 3
        try:
            if self.ritardo_s.get(tipo):
                time.sleep(self.ritardo_s[tipo])
            if self.avanza_orologio_s.get(tipo):
                self.ora.avanza(self.avanza_orologio_s[tipo])
            if guasto == "rete":
                raise requests.ConnectionError("finto: connessione caduta")
            if guasto == "timeout":
                raise requests.ReadTimeout("finto: timeout di lettura")
            if guasto == "http503":
                return 503, {"finto": "servizio non disponibile"}
            with self._lock:
                if guasto:
                    return 200, (errore_aping(guasto) if tipo not in ("login", "keepAlive")
                                 else ({"loginStatus": guasto} if tipo == "login"
                                       else {"token": tok, "status": "FAIL", "error": guasto}))
                if troppi:
                    return 200, errore_aping("TOO_MANY_REQUESTS")
                if tipo == "login":
                    return 200, self._login()
                if tipo == "keepAlive":
                    return 200, self._keep_alive(tok)
                if tipo == "logout":
                    self.token_rinnovo.pop(tok or "", None)
                    return 200, {"token": tok, "product": "APPKEY", "status": "SUCCESS", "error": ""}
                return 200, self._rpc(tipo, params, tok)
        finally:
            with self._lock:
                self.in_volo[tipo] -= 1
                if conteso:
                    self.contesi_in_volo -= 1


class AdattatoreFinto(requests.adapters.HTTPAdapter):
    """Trasporto di requests: al posto del socket, il ``ServerBetfairFinto``.
    La risposta passa da ``urllib3.HTTPResponse`` + ``build_response`` (gzip
    decompresso da requests come in rete)."""

    def __init__(self, server: ServerBetfairFinto, id_sessione: int) -> None:
        super().__init__()
        self.server = server
        self.id_sessione = id_sessione

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):  # type: ignore[override]
        status, corpo = self.server.rispondi(request, cert, self.id_sessione)
        grezzo = gzip.compress(json.dumps(corpo).encode("utf-8"))
        resp = HTTPResponse(body=io.BytesIO(grezzo), status=status, preload_content=False,
                            decode_content=True, request_method="POST", request_url=request.url,
                            headers={"Content-Type": "application/json;charset=UTF-8",
                                     "Content-Encoding": "gzip", "Content-Length": str(len(grezzo))})
        return self.build_response(request, resp)


def installa_finto(monkeypatch: pytest.MonkeyPatch, server: ServerBetfairFinto) -> None:
    """``auth.build_client`` (codice di oggi) crea APIClient con la sessione HTTP
    che monta l'adattatore finto; credenziali finte ma non vuote."""
    from Betfair.stream import auth

    for nome in ("BETFAIR_APP_KEY", "BETFAIR_USERNAME", "BETFAIR_PASSWORD", "BETFAIR_CERT_FILE",
                 "BETFAIR_KEY_FILE"):
        monkeypatch.setattr(auth, nome, {"BETFAIR_USERNAME": "conto_finto",
                                         "BETFAIR_CERT_FILE": "/finto/client-2048.crt",
                                         "BETFAIR_KEY_FILE": "/finto/client-2048.key"}.get(nome, "finto"))
    vera = requests.Session
    contatore = [0]

    def _sessione() -> requests.Session:
        s = vera()
        contatore[0] += 1
        s.mount("https://", AdattatoreFinto(server, contatore[0]))
        return s

    monkeypatch.setattr(auth.requests, "Session", _sessione)


# ===========================================================================
# PROVE DEL FINTO
# ===========================================================================
@pytest.fixture
def finto(monkeypatch):
    server = ServerBetfairFinto()
    installa_finto(monkeypatch, server)
    return server


def _client_loggato():
    from Betfair.stream import auth

    return auth.build_client(login=True)


def test_finto_json_diventano_oggetti_veri(finto):
    from betfairlightweight.resources import MarketBook

    c = _client_loggato()
    books = c.betting.list_market_book(market_ids=["1.101", "1.102"])
    assert [type(b) for b in books] == [MarketBook, MarketBook]
    assert books[0].market_id == "1.101"
    assert books[0].runners[0].ex.available_to_back[0]["price"] == pytest.approx(1.51)
    assert books[0].runners[0].ex.available_to_lay[0]["price"] == pytest.approx(1.53)
    assert books[1].status == "OPEN" and books[1].version == 4567890123


def test_finto_gzip_decompresso_da_requests(finto):
    c = _client_loggato()
    visti = []
    c.session.hooks["response"].append(lambda r, *a, **k: visti.append(r))
    c.betting.list_event_types(lightweight=True)
    assert visti[-1].headers["Content-Encoding"] == "gzip"
    assert visti[-1].json()["result"][0]["eventType"]["name"] == "Soccer"


def test_finto_regole_peso_e_sessione(finto):
    from betfairlightweight.exceptions import APIError

    c = _client_loggato()
    pp = {"priceData": ["EX_ALL_OFFERS"]}
    c.betting.list_market_book(market_ids=[f"1.{i}" for i in range(11)], price_projection=pp)
    with pytest.raises(APIError, match="TOO_MUCH_DATA"):
        c.betting.list_market_book(market_ids=[f"1.{i}" for i in range(12)], price_projection=pp)
    finto.ora.avanza(1199)
    c.keep_alive()                                   # rinnova entro i 20 minuti
    finto.ora.avanza(1199)
    c.betting.list_event_types()
    finto.ora.avanza(1201)                           # oltre i 20 minuti senza keepAlive
    with pytest.raises(APIError, match="INVALID_SESSION_INFORMATION"):
        c.betting.list_event_types()


def test_finto_ban_dei_login_oltre_100_al_minuto(finto):
    from betfairlightweight.exceptions import LoginError

    c = _client_loggato()
    for _ in range(99):
        c.login()
    with pytest.raises(LoginError, match="TEMPORARY_BAN_TOO_MANY_REQUESTS"):
        c.login()
    finto.ora.avanza(61)
    with pytest.raises(LoginError, match="TEMPORARY_BAN_TOO_MANY_REQUESTS"):
        c.login()                                    # il ban dura 20 minuti
    finto.ora.avanza(1200)
    c.login()


def test_finto_quarta_richiesta_contesa_too_many_requests(finto):
    from betfairlightweight.exceptions import APIError

    c = _client_loggato()
    finto.ritardo_s["listCurrentOrders"] = 0.2
    barriera = threading.Barrier(4)
    errori = []

    def _lavoro():
        barriera.wait()
        try:
            c.betting.list_current_orders()
        except APIError as e:
            errori.append(str(e))

    fili = [threading.Thread(target=_lavoro) for _ in range(4)]
    for f in fili:
        f.start()
    for f in fili:
        f.join(10)
    assert len(errori) == 1 and "TOO_MANY_REQUESTS" in errori[0]
