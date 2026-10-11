"""M-1 (11/10/2026): il registratore dello stream ordini e delle REST con soldi.

Finti con le chiavi e i tipi del vero:
  * APIClient VERO di betfairlightweight costruito da ``auth.build_client`` VERO,
    con l'adattatore di requests sostituito (le risposte sono buste JSON-RPC con
    le chiavi di Betfair: ``instructionReports``, ``betId``, ``errorCode``...);
  * ``BetfairClient`` VERO del repo (``Betfair/client.py``) con lo stesso adattatore;
  * ``OrderStream`` VERO di flumine sul ``BetfairClient`` VERO di flumine (LIVE):
    gira ``run`` vero (``create_stream`` -> ``subscribe_to_orders`` -> ``start``) con
    il solo socket sostituito da uno che restituisce righe dello stream ordini
    Betfair (``connection``, ``status``, ``ocm`` SUB_IMAGE/UPDATE/HEARTBEAT), che
    il listener VERO di betfairlightweight trasforma in ``CurrentOrders``;
  * ordine VERO di flumine per ``tempi_ordine.place``.

Prove: spento non scrive e non tocca niente; acceso registra; un'eccezione del
registratore non arriva al bot; il tetto di disco pota e poi smette; la lettura
della giornata ricostruisce sequenze, latenze, ordini del sito, ocm prima della
risposta e buchi.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import threading
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
import requests

from Betfair.monitor import analisi_ordini as AO
from Betfair.monitor import registratore_ordini as RO

MID = "1.248734017"
SEL = 47972
TOKEN = "TOKEN-SEGRETO-0123456789abcdef"
APPKEY = "APPKEY-SEGRETA-0123456789"
PT0 = 1_760_176_800_000


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------
def _thread_registro() -> List[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "registro-ordini"]


@pytest.fixture(autouse=True)
def _avvisi_azzerati():
    """Gli avvisi sono limitati a uno al minuto per motivo: ogni test parte pulito."""
    RO._ULTIMO_AVVISO.clear()
    yield
    RO._ULTIMO_AVVISO.clear()


@pytest.fixture
def spento(monkeypatch, tmp_path):
    """Interruttore a 0 (di serie), pytest e banco NON lo spengono: decide solo
    l'interruttore."""
    monkeypatch.setenv(RO.ENV, "0")
    monkeypatch.setenv(RO.ENV_DIR, str(tmp_path / "ordini"))
    monkeypatch.setattr(RO, "_consenti_in_test", True)
    monkeypatch.setattr(RO, "nel_banco", lambda: False)
    RO._azzera_per_test(None)
    yield tmp_path / "ordini"
    assert RO._SCRITTORE is None, "spento ma scrittore creato"
    assert not (tmp_path / "ordini").exists(), "spento ma cartella creata"
    RO._azzera_per_test(None)


@pytest.fixture
def acceso(monkeypatch, tmp_path):
    monkeypatch.setenv(RO.ENV, "1")
    monkeypatch.setattr(RO, "_consenti_in_test", True)
    monkeypatch.setattr(RO, "nel_banco", lambda: False)
    scr = RO.Scrittore(cartella=str(tmp_path / "ordini"), servizio="prova", avvia_thread=False)
    RO._azzera_per_test(scr)
    yield scr
    scr.chiudi()
    RO._azzera_per_test(None)


def _righe(scr: RO.Scrittore) -> List[Dict[str, Any]]:
    scr.giro(forza_svuota=True)
    scr.chiudi()
    files = sorted(p for p in _tutti_i_file(scr.cartella()))
    out: List[Dict[str, Any]] = []
    for p in files:
        righe, info = AO.leggi_file(p)
        assert info["rotte"] == 0 and not info["troncato"]
        out.extend(righe)
    return out


def _tutti_i_file(base: str) -> List[str]:
    out = []
    for radice, _d, files in os.walk(base):
        out.extend(os.path.join(radice, f) for f in files)
    return out


# ---------------------------------------------------------------------------
# REST: risposte Betfair finte con le chiavi vere
# ---------------------------------------------------------------------------
def _risultato(metodo: str, params: Dict[str, Any]) -> Dict[str, Any]:
    mid = params.get("marketId")
    if mid == "1.999":
        # errore JSON-RPC (APINGException) che, per prova, ECHEGGIA token e app key
        return {"jsonrpc": "2.0", "id": 1, "error": {
            "code": -32099, "message": "ANGX-0003 " + TOKEN,
            "data": {"exceptionname": "APINGException", "APINGException": {
                "requestUUID": "prd-x", "errorCode": "INVALID_SESSION_INFORMATION",
                "errorDetails": "app " + APPKEY}}}}
    if metodo == "placeOrders":
        istr = params["instructions"][0]
        if istr["limitOrder"]["size"] == 999:
            res = {"customerRef": params.get("customerRef"), "status": "FAILURE",
                   "errorCode": "INSUFFICIENT_FUNDS", "marketId": mid,
                   "instructionReports": [{"status": "FAILURE", "errorCode": "INSUFFICIENT_FUNDS",
                                           "instruction": istr}]}
        else:
            res = {"customerRef": params.get("customerRef"), "status": "SUCCESS", "marketId": mid,
                   "instructionReports": [{"status": "SUCCESS", "instruction": istr,
                                           "betId": "381200000001",
                                           "placedDate": "2026-10-11T10:00:00.400Z",
                                           "averagePriceMatched": 0.0, "sizeMatched": 0.0,
                                           "orderStatus": "EXECUTABLE"}]}
    elif metodo == "cancelOrders":
        res = {"customerRef": params.get("customerRef"), "status": "SUCCESS", "marketId": mid,
               "instructionReports": [{"status": "SUCCESS", "instruction": i, "sizeCancelled": 2.0,
                                       "cancelledDate": "2026-10-11T10:00:05.000Z"}
                                      for i in params["instructions"]]}
    elif metodo == "replaceOrders":
        i = params["instructions"][0]
        res = {"customerRef": params.get("customerRef"), "status": "SUCCESS", "marketId": mid,
               "instructionReports": [{
                   "status": "SUCCESS",
                   "cancelInstructionReport": {"status": "SUCCESS", "instruction": {"betId": i["betId"]},
                                               "sizeCancelled": 4.0,
                                               "cancelledDate": "2026-10-11T10:00:06.000Z"},
                   "placeInstructionReport": {
                       "status": "SUCCESS",
                       "instruction": {"selectionId": SEL, "handicap": 0.0,
                                       "limitOrder": {"size": 4.0, "price": i["newPrice"],
                                                      "persistenceType": "LAPSE"},
                                       "orderType": "LIMIT", "side": "BACK"},
                       "betId": "381200000002", "placedDate": "2026-10-11T10:00:06.100Z",
                       "averagePriceMatched": 0.0, "sizeMatched": 0.0,
                       "orderStatus": "EXECUTABLE"}}]}
    elif metodo == "updateOrders":
        res = {"customerRef": params.get("customerRef"), "status": "SUCCESS", "marketId": mid,
               "instructionReports": [{"status": "SUCCESS", "instruction": i}
                                      for i in params["instructions"]]}
    else:
        res = []
    return {"jsonrpc": "2.0", "result": res, "id": 1}


class _Adattatore(requests.adapters.HTTPAdapter):
    def send(self, request, **kw):  # type: ignore[override]
        r = requests.Response()
        r.status_code = 200
        r.url = request.url
        r.request = request
        if "certlogin" in request.url:
            corpo: Any = {"loginStatus": "SUCCESS", "sessionToken": TOKEN}
        elif "keepAlive" in request.url:
            corpo = {"token": TOKEN, "status": "SUCCESS", "error": ""}
        else:
            body = request.body
            if isinstance(body, bytes):
                body = body.decode()
            d = json.loads(body)
            corpo = _risultato(d["method"].rsplit("/", 1)[-1], d.get("params") or {})
        r._content = json.dumps(corpo).encode()
        r.headers["Content-Type"] = "application/json"
        return r


def _build_client(monkeypatch):
    from Betfair.stream import auth

    for nome in ("BETFAIR_USERNAME", "BETFAIR_PASSWORD", "BETFAIR_CERT_FILE", "BETFAIR_KEY_FILE"):
        monkeypatch.setattr(auth, nome, "finto")
    monkeypatch.setattr(auth, "BETFAIR_APP_KEY", APPKEY)
    vera = requests.Session

    def _sessione():
        s = vera()
        s.mount("https://", _Adattatore())
        return s

    monkeypatch.setattr(auth.requests, "Session", _sessione)
    return auth.build_client(login=True)


def _istr(size: float = 4.0, cor: str = "6279886fde090-1401") -> Dict[str, Any]:
    return {"orderType": "LIMIT", "selectionId": SEL, "handicap": 0, "side": "BACK",
            "limitOrder": {"size": size, "price": 2.5, "persistenceType": "LAPSE"},
            "customerOrderRef": cor}


def _giro_rest(c) -> Dict[str, Any]:
    """Le chiamate che fa flumine (``BetfairExecution``): stessi argomenti."""
    out: Dict[str, Any] = {}
    r = c.betting.place_orders(market_id=MID, instructions=[_istr()], customer_ref="a" * 32,
                               customer_strategy_ref="live", async_=False)
    out["place"] = (r.status, r.place_instruction_reports[0].bet_id,
                    r.place_instruction_reports[0].order_status)
    r = c.betting.place_orders(market_id=MID, instructions=[_istr(size=999)],
                               customer_ref="b" * 32, customer_strategy_ref="mike")
    out["rifiuto"] = (r.status, r.error_code, r.place_instruction_reports[0].error_code)
    r = c.betting.cancel_orders(market_id=MID, instructions=[{"betId": "381200000001",
                                                              "sizeReduction": 2.0}],
                                customer_ref="c" * 32)
    out["cancel"] = (r.status, r.cancel_instruction_reports[0].size_cancelled)
    r = c.betting.replace_orders(market_id=MID, instructions=[{"betId": "381200000001",
                                                               "newPrice": 2.6}],
                                 customer_ref="d" * 32)
    out["replace"] = (r.status, r.replace_instruction_reports[0].place_instruction_reports.bet_id)
    r = c.betting.update_orders(market_id=MID, instructions=[{"betId": "381200000002",
                                                              "newPersistenceType": "PERSIST"}],
                                customer_ref="e" * 32)
    out["update"] = r.status
    with pytest.raises(Exception) as ei:
        c.betting.place_orders(market_id="1.999", instructions=[_istr()], customer_ref="f" * 32)
    out["errore"] = (type(ei.value).__name__, "INVALID_SESSION_INFORMATION" in str(ei.value))
    # una lettura (nessun soldo): non si registra
    c.betting.list_market_book(market_ids=[MID], lightweight=True)
    return out


# ---------------------------------------------------------------------------
# stream ordini: socket finto, righe dello stream ordini Betfair
# ---------------------------------------------------------------------------
class _SocketFinto:
    def __init__(self, righe: List[str]) -> None:
        self._dati = [(r + "\r\n").encode() for r in righe]
        self.inviati: List[bytes] = []

    def recv(self, n):  # noqa: ARG002
        return self._dati.pop(0) if self._dati else b""

    def sendall(self, b):
        self.inviati.append(b)

    def shutdown(self, how):  # noqa: ARG002
        pass

    def close(self):
        pass


def _uo(bet: str, status: str, sm: float, sr: float, **extra: Any) -> Dict[str, Any]:
    d = {"id": bet, "p": 2.5, "s": 4, "side": "B", "status": status, "pt": "L", "ot": "L",
         "pd": PT0 + 400, "sm": sm, "sr": sr, "sl": 0, "sc": 0, "sv": 0, "rac": "",
         "rc": "REG_GGC", "rfo": "6279886fde090-1401", "rfs": "live"}
    d.update(extra)
    return d


def righe_stream_ordini(sid_sub: int, sid_auth: int) -> List[str]:
    """La forma dello stream ordini Betfair (Exchange Stream API, ``ocm``)."""
    oc = lambda uo, **k: [{"id": MID, "orc": [dict({"id": SEL, "uo": [uo]}, **k)]}]  # noqa: E731
    msgs = [
        {"op": "connection", "connectionId": "002-051134157842-432409"},
        {"op": "status", "id": sid_auth, "statusCode": "SUCCESS", "connectionClosed": False,
         "connectionsAvailable": 9},
        {"op": "status", "id": sid_sub, "statusCode": "SUCCESS", "connectionClosed": False},
        {"op": "ocm", "id": sid_sub, "initialClk": "GpOQ5bEdIp+asKYeGtW3+bIdGr+9jhw=",
         "clk": "AAAAAAAAAAAAAA==", "conflateMs": 0, "heartbeatMs": 5000, "pt": PT0,
         "ct": "SUB_IMAGE"},
        {"op": "ocm", "id": sid_sub, "clk": "AAEAAAAAAAAA", "pt": PT0 + 500,
         "oc": oc(_uo("381200000001", "E", 0, 4), fullImage=True)},
        {"op": "ocm", "id": sid_sub, "clk": "AAIAAAAAAAAA", "pt": PT0 + 900,
         "oc": oc(_uo("381200000001", "E", 1.5, 2.5, md=PT0 + 880, avp=2.5),
                  mb=[[2.5, 1.5]])},
        {"op": "ocm", "id": sid_sub, "clk": "AAMAAAAAAAAA", "pt": PT0 + 1500,
         "oc": oc(_uo("381200000001", "EC", 4, 0, md=PT0 + 1480, avp=2.5), mb=[[2.5, 4]])},
        {"op": "ocm", "id": sid_sub, "clk": "AAQAAAAAAAAA", "pt": PT0 + 6500, "ct": "HEARTBEAT"},
    ]
    return [json.dumps(m, separators=(",", ":")) for m in msgs]


def _gira_order_stream(monkeypatch, api_client, stream_id: int = 1000):
    """``OrderStream.run`` VERO di flumine sul client LIVE; ritorna (stream, righe)."""
    from betfairlightweight.exceptions import SocketError
    from betfairlightweight.streaming.betfairstream import BetfairStream
    from flumine import clients
    from flumine.streams.orderstream import OrderStream

    righe = righe_stream_ordini(stream_id + 1, stream_id + 2)
    sock = _SocketFinto(righe)
    monkeypatch.setattr(BetfairStream, "_create_socket", lambda self: sock)
    client = clients.BetfairClient(api_client, order_stream=True, paper_trade=False,
                                   min_bet_validation=False)
    st = OrderStream(flumine=SimpleNamespace(), stream_id=stream_id, conflate_ms=None,
                     streaming_timeout=0.25, client=client)
    with pytest.raises(SocketError):
        OrderStream.run.__wrapped__(st)  # senza il retry infinito di tenacity
    libri = []
    while not st._output_queue.empty():
        for ob in st._output_queue.get_nowait():
            libri.append(sorted((o.market_id, o.bet_id, o.status, o.size_matched,
                                 o.size_remaining) for o in ob.orders))
    return righe, libri, sock


# ---------------------------------------------------------------------------
# 1. SPENTO: non scrive niente e non tocca niente
# ---------------------------------------------------------------------------
def test_spento_build_client_non_avvolge_niente_e_non_scrive(monkeypatch, spento):
    c = _build_client(monkeypatch)
    assert "request" not in vars(c.betting), "spento ma betting.request avvolto"
    assert "create_stream" not in vars(c.streaming), "spento ma create_stream avvolto"
    esiti = _giro_rest(c)
    assert esiti["place"] == ("SUCCESS", "381200000001", "EXECUTABLE")
    righe, libri, _s = _gira_order_stream(monkeypatch, c)
    assert libri, "il listener vero non ha prodotto ordini"
    assert not _thread_registro()


def test_spento_client_rest_nostro_e_tempi_ordine_non_scrivono(monkeypatch, spento):
    c = _client_nostro()
    assert c.place_orders(MID, [_istr()], customer_ref="x1", customer_strategy_ref="watchlist")
    _decisione_vera()
    assert not _thread_registro()


def test_spento_e_il_valore_di_serie(monkeypatch, tmp_path):
    monkeypatch.delenv(RO.ENV, raising=False)
    monkeypatch.setattr(RO, "_consenti_in_test", True)
    monkeypatch.setattr(RO, "nel_banco", lambda: False)
    RO._azzera_per_test(None)
    try:
        assert RO.attivo() is False
        for v in ("", "0", "true", "si", " 2"):
            monkeypatch.setenv(RO.ENV, v)
            RO._azzera_per_test(None)
            assert RO.attivo() is False, v
        monkeypatch.setenv(RO.ENV, "1")
        RO._azzera_per_test(None)
        assert RO.attivo() is True
    finally:
        RO._azzera_per_test(None)


def test_acceso_ma_banco_o_pytest_lo_spengono(monkeypatch):
    import sys

    monkeypatch.setenv(RO.ENV, "1")
    RO._azzera_per_test(None)
    try:
        monkeypatch.setattr(RO, "_consenti_in_test", False)
        assert RO.attivo() is False, "sotto pytest deve restare spento"
        RO._azzera_per_test(None)
        monkeypatch.setattr(RO, "_consenti_in_test", True)
        monkeypatch.setitem(sys.modules, "Betfair.stream.backtest.finto_m1", SimpleNamespace())
        assert RO.attivo() is False, "nel banco deve restare spento"
    finally:
        RO._azzera_per_test(None)


# ---------------------------------------------------------------------------
# 2. ACCESO: registra (REST betfairlightweight, REST nostro, stream ordini)
# ---------------------------------------------------------------------------
def test_acceso_rest_bflw_registra_e_non_cambia_gli_esiti(monkeypatch, acceso, tmp_path):
    c = _build_client(monkeypatch)
    assert getattr(vars(c.betting)["request"], RO._MARCA, False)
    esiti = _giro_rest(c)
    assert esiti == {
        "place": ("SUCCESS", "381200000001", "EXECUTABLE"),
        "rifiuto": ("FAILURE", "INSUFFICIENT_FUNDS", "INSUFFICIENT_FUNDS"),
        "cancel": ("SUCCESS", 2.0),
        "replace": ("SUCCESS", "381200000002"),
        "update": "SUCCESS",
        "errore": ("APIError", True),
    }
    righe = _righe(acceso)
    rest = [r for r in righe if r["k"] == "rest"]
    assert [r["metodo"] for r in rest] == ["placeOrders", "placeOrders", "cancelOrders",
                                           "replaceOrders", "updateOrders", "placeOrders"]
    p = rest[0]
    assert p["via"] == "bflw" and p["market_id"] == MID and p["attore"] == "desktop"
    assert p["csr"] == "live" and p["cref"] == "a" * 32
    assert p["corefs"] == ["6279886fde090-1401"]
    assert p["richiesta"]["instructions"][0]["limitOrder"]["size"] == 4.0
    assert p["risposta"]["result"]["instructionReports"][0]["betId"] == "381200000001"
    assert p["stato"] == "SUCCESS" and p["errore"] is None
    assert p["risposta_mono_us"] >= p["mono_us"] and p["durata_ms"] >= 0
    assert p["risposta_ep_us"] >= p["ep_us"] > 1_700_000_000_000_000
    assert rest[1]["attore"] == "bot:mike"
    assert rest[1]["errore"] == "INSUFFICIENT_FUNDS" and rest[1]["codici"] == ["INSUFFICIENT_FUNDS"]
    assert rest[2]["attore"] == "?"
    e = rest[5]
    assert e["eccezione"].startswith("APIError") and e["errore"] == "INVALID_SESSION_INFORMATION"
    # mai segreti su disco, anche quando Betfair li echeggia nell'errore
    grezzo = b"".join(gzip.open(p, "rb").read() for p in _tutti_i_file(acceso.cartella()))
    assert TOKEN.encode() not in grezzo and APPKEY.encode() not in grezzo
    assert b"***" in grezzo
    assert b"listMarketBook" not in grezzo


def test_acceso_rest_bflw_esiti_identici_a_spento(monkeypatch, tmp_path):
    """Lo stesso giro REST con registratore spento e acceso: esiti identici."""
    monkeypatch.setattr(RO, "_consenti_in_test", True)
    monkeypatch.setattr(RO, "nel_banco", lambda: False)
    esiti = {}
    for v in ("0", "1"):
        monkeypatch.setenv(RO.ENV, v)
        scr = RO.Scrittore(cartella=str(tmp_path / v), servizio="p", avvia_thread=False)
        RO._azzera_per_test(scr)
        try:
            esiti[v] = _giro_rest(_build_client(monkeypatch))
        finally:
            scr.chiudi()
            RO._azzera_per_test(None)
    assert esiti["0"] == esiti["1"]
    assert not (tmp_path / "0").exists() and (tmp_path / "1").exists()


def _client_nostro():
    from Betfair.client import BetfairClient

    c = BetfairClient(app_key=APPKEY, username="u", password="p", cert_file="c", key_file="k",
                      identity_url="https://identitysso-cert.betfair.it/api/certlogin")
    c._http.mount("https://", _Adattatore())
    c._session_token = TOKEN
    return c


def test_acceso_rest_nostro_registra(acceso, monkeypatch):
    import Betfair.client as BC

    monkeypatch.setattr(BC.time, "sleep", lambda s: None)  # i ritentativi di _rpc
    c = _client_nostro()
    r = c.place_orders(MID, [_istr()], customer_ref="x1", customer_strategy_ref="watchlist")
    assert r["instructionReports"][0]["betId"] == "381200000001"
    r2 = c.betting_rpc("SportsAPING/v1.0/cancelOrders",
                       {"marketId": MID, "instructions": [{"betId": "381200000001"}]})
    assert r2["status"] == "SUCCESS"
    assert c.betting_rpc("SportsAPING/v1.0/listMarketBook", {"marketIds": [MID]}) == []
    with pytest.raises(RuntimeError):
        c.place_orders("1.999", [_istr()], customer_ref="x2", max_retries=1)
    righe = _righe(acceso)
    rest = [r for r in righe if r["k"] == "rest"]
    assert [(r["via"], r["metodo"]) for r in rest] == [
        ("rest_nostro", "placeOrders"), ("rest_nostro", "cancelOrders"),
        ("rest_nostro", "placeOrders")]
    assert rest[0]["attore"] == "desktop_watchlist" and rest[0]["market_id"] == MID
    assert rest[0]["risposta"]["instructionReports"][0]["betId"] == "381200000001"
    assert rest[2]["eccezione"].startswith("RuntimeError")
    grezzo = b"".join(gzip.open(p, "rb").read() for p in _tutti_i_file(acceso.cartella()))
    assert TOKEN.encode() not in grezzo and APPKEY.encode() not in grezzo


def test_acceso_stream_ordini_flumine_vero_registra_verbatim(monkeypatch, acceso):
    c = _build_client(monkeypatch)
    righe_in, libri, sock = _gira_order_stream(monkeypatch, c)
    # il listener vero ha visto gli ordini come sempre
    assert libri[-1] == [(MID, "381200000001", "EXECUTION_COMPLETE", 4, 0)]
    righe = _righe(acceso)
    sub = [r for r in righe if r["k"] == "sub"]
    assert len(sub) == 1 and sub[0]["ripresa"] is False
    assert sub[0]["filtro"]["partitionMatchedByStrategyRef"] is True
    stream = [r for r in righe if r["k"] == "stream"]
    assert [r["msg"] for r in stream] == [json.loads(x) for x in righe_in], "righe non verbatim"
    assert len({r["sid"] for r in stream}) == 1
    eps = [r["ep_us"] for r in stream]
    assert eps == sorted(eps)
    seqs = sorted(r["seq"] for r in righe if r.get("seq"))
    assert seqs == list(range(1, len(seqs) + 1)), "sequenza con buchi"
    # nessun segreto: la richiesta d'autenticazione non passa dal listener
    grezzo = b"".join(gzip.open(p, "rb").read() for p in _tutti_i_file(acceso.cartella()))
    assert TOKEN.encode() not in grezzo and APPKEY.encode() not in grezzo


def test_acceso_stream_esiti_identici_a_spento(monkeypatch, tmp_path):
    monkeypatch.setattr(RO, "_consenti_in_test", True)
    monkeypatch.setattr(RO, "nel_banco", lambda: False)
    out = {}
    for v in ("0", "1"):
        monkeypatch.setenv(RO.ENV, v)
        scr = RO.Scrittore(cartella=str(tmp_path / v), servizio="p", avvia_thread=False)
        RO._azzera_per_test(scr)
        try:
            _r, libri, sock = _gira_order_stream(monkeypatch, _build_client(monkeypatch))
            out[v] = (libri, sock.inviati)
        finally:
            scr.chiudi()
            RO._azzera_per_test(None)
    assert out["0"] == out["1"], "lo stream ordini cambia col registratore acceso"


def test_acceso_stream_dei_prezzi_non_registrato(monkeypatch, acceso):
    from betfairlightweight import StreamListener
    from betfairlightweight.streaming.betfairstream import BetfairStream

    c = _build_client(monkeypatch)
    sock = _SocketFinto([json.dumps({"op": "connection", "connectionId": "x"}),
                         json.dumps({"op": "status", "id": 3, "statusCode": "SUCCESS"})])
    monkeypatch.setattr(BetfairStream, "_create_socket", lambda self: sock)
    lis = StreamListener()
    st = c.streaming.create_stream(unique_id=1, listener=lis)
    st.subscribe_to_markets(market_filter={"marketIds": [MID]}, market_data_filter={})
    assert "on_data" not in vars(lis), "tee montato su uno stream dei prezzi"
    assert [r for r in _righe(acceso) if r["k"] in ("stream", "sub")] == []


def _decisione_vera():
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade
    from flumine.strategy.strategy import BaseStrategy

    from Betfair.stream import tempi_ordine as TO

    s = BaseStrategy(market_filter={}, name="prova-m1")
    o = Trade(MID, SEL, 0, s).create_order("BACK", LimitOrder(2.5, 4.0))
    TO._azzera_per_test()
    TO.nuovo("cmd-1", "comando", azione="place", mode="live", rif="r1",
             decisione_ms=PT0 - 50)
    TO.presa("cmd-1")
    TO.place(o)
    TO.fine("cmd-1", True)
    TO._azzera_per_test()
    return o


def test_acceso_decisione_legata_al_customer_order_ref(acceso):
    o = _decisione_vera()
    dec = [r for r in _righe(acceso) if r["k"] == "dec"]
    assert len(dec) == 1
    assert dec[0]["cor"] == o.customer_order_ref and dec[0]["chiave"] == "cmd-1"
    assert dec[0]["decisione_ms"] == PT0 - 50 and dec[0]["strada"] == "comando"


# ---------------------------------------------------------------------------
# 3. un'eccezione del registratore non arriva al bot
# ---------------------------------------------------------------------------
def _esplode(*a, **k):
    raise RuntimeError("guasto iniettato M-1")


def test_metti_non_solleva_mai(acceso, monkeypatch, caplog):
    """Strato interno: le due porte della coda non sollevano mai."""
    with caplog.at_level(logging.WARNING, logger=RO.__name__):
        monkeypatch.setattr(RO, "adesso_us", _esplode)
        acceso.metti_stream(1, '{"op":"ocm"}')
        monkeypatch.setattr(RO.Scrittore, "_accoda", _esplode)
        acceso.metti_record({"k": "rest"})
        # le funzioni pubbliche chiamate dagli agganci, da sole
        monkeypatch.setattr(RO.Scrittore, "metti_record", _esplode)
        RO.decisione(SimpleNamespace(id=1, customer_order_ref="x"), {"chiave": "c"})
        RO.registra_rest(via="bflw", method="placeOrders", params={}, invio=(0, 0),
                         risposta=(0, 0), esito={})
    assert caplog.text.count("guasto iniettato M-1") >= 4


def test_eccezioni_del_registratore_non_arrivano_al_bot(monkeypatch, acceso, caplog):
    """Strato esterno: anche se le porte della coda sollevassero, gli agganci
    (REST, tee dello stream, sottoscrizione, decisione) non lo lasciano passare."""
    c = _build_client(monkeypatch)
    monkeypatch.setattr(RO, "adesso_us", _esplode)
    monkeypatch.setattr(RO.Scrittore, "metti_stream", _esplode)
    monkeypatch.setattr(RO.Scrittore, "metti_record", _esplode)
    with caplog.at_level(logging.WARNING, logger=RO.__name__):
        esiti = _giro_rest(c)
        assert esiti["place"] == ("SUCCESS", "381200000001", "EXECUTABLE")
        assert esiti["errore"] == ("APIError", True)
        _r, libri, _s = _gira_order_stream(monkeypatch, c)
        assert libri[-1] == [(MID, "381200000001", "EXECUTION_COMPLETE", 4, 0)]
        assert _client_nostro().place_orders(MID, [_istr()], customer_ref="z")
        _decisione_vera()
    testo = caplog.text
    assert "guasto iniettato M-1" in testo, "errore non loggato col motivo"


def test_errore_di_disco_non_arriva_al_bot(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv(RO.ENV, "1")
    monkeypatch.setattr(RO, "_consenti_in_test", True)
    monkeypatch.setattr(RO, "nel_banco", lambda: False)
    finto_file = tmp_path / "non_una_cartella"
    finto_file.write_text("x")
    scr = RO.Scrittore(cartella=str(finto_file / "sotto"), servizio="p", avvia_thread=False)
    RO._azzera_per_test(scr)
    try:
        with caplog.at_level(logging.WARNING, logger=RO.__name__):
            c = _build_client(monkeypatch)
            assert _giro_rest(c)["place"] == ("SUCCESS", "381200000001", "EXECUTABLE")
            assert scr.giro(forza_svuota=True) == 0
        assert scr.errori_scrittura >= 1
        assert "apertura KO" in caplog.text
    finally:
        scr.chiudi()
        RO._azzera_per_test(None)


def test_coda_piena_perde_e_conta_senza_bloccare(acceso, monkeypatch):
    monkeypatch.setattr(RO, "CODA_MAX", 3)
    for i in range(5):
        acceso.metti_stream(1, '{"op":"ocm","id":1,"pt":%d,"ct":"HEARTBEAT"}' % i)
    assert acceso.persi_coda == 2
    righe = _righe(acceso)
    assert sum(1 for r in righe if r["k"] == "stream") == 3
    ch = [r for r in righe if r["k"] == "chiusura"][-1]
    assert ch["persi_coda"] == 2


# ---------------------------------------------------------------------------
# 4. tetto di disco e rotazione
# ---------------------------------------------------------------------------
def _file_vecchio(base, giorno: str, nome: str, kb: int, mtime: float) -> str:
    d = os.path.join(base, giorno)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, nome)
    with open(p, "wb") as fh:
        fh.write(os.urandom(kb * 1024))
    os.utime(p, (mtime, mtime))
    return p


def test_tetto_pota_i_piu_vecchi_e_mai_il_proprio(tmp_path):
    base = str(tmp_path / "ordini")
    v1 = _file_vecchio(base, "20261001", "ordini_a_1.jsonl.gz", 600, 1_000_000)
    v2 = _file_vecchio(base, "20261002", "ordini_a_2.jsonl.gz", 600, 2_000_000)
    v3 = _file_vecchio(base, "20261003", "ordini_a_3.jsonl.gz", 500, 3_000_000)
    altro = _file_vecchio(base, "20261001", "non_mio.txt", 900, 500_000)
    scr = RO.Scrittore(cartella=base, servizio="p", tetto=1024 * 1024, avvia_thread=False)
    scr.metti_stream(1, '{"op":"ocm","id":1,"pt":1,"ct":"HEARTBEAT"}')
    scr.giro(forza_svuota=True)
    assert not os.path.exists(v1) and not os.path.exists(v2), "i piu' vecchi non potati"
    assert os.path.exists(v3) and os.path.exists(altro)
    assert os.path.exists(scr._percorso) and scr.file_potati == 2
    assert not scr._pieno
    scr.chiudi()


def test_tetto_non_pota_il_file_vivo_di_un_altro_processo(tmp_path):
    import time as _t

    base = str(tmp_path / "ordini")
    vecchio = _file_vecchio(base, "20261001", "ordini_a_1.jsonl.gz", 600, 1_000_000)
    vivo = _file_vecchio(base, "20261011", "ordini_b_9.jsonl.gz", 1100, _t.time() - 5)
    scr = RO.Scrittore(cartella=base, servizio="p", tetto=1024 * 1024, avvia_thread=False)
    scr.metti_stream(1, '{"op":"ocm","id":1,"pt":1,"ct":"HEARTBEAT"}')
    scr.giro(forza_svuota=True)
    assert not os.path.exists(vecchio) and os.path.exists(vivo)
    assert scr._pieno, "oltre il tetto col solo file vivo: deve smettere di scrivere"
    scr.chiudi()


def test_tetto_pieno_smette_di_scrivere_e_conta(tmp_path, caplog, monkeypatch):
    """Il solo file aperto supera il tetto: al controllo dopo (qui a ogni giro)
    si smette di scrivere, le righe si contano, il bot non se ne accorge."""
    monkeypatch.setattr(RO, "POTATURA_S", 0.0)
    base = str(tmp_path / "ordini")
    scr = RO.Scrittore(cartella=base, servizio="p", tetto=10, avvia_thread=False)
    with caplog.at_level(logging.WARNING, logger=RO.__name__):
        for i in range(4):
            scr.metti_stream(1, '{"op":"ocm","id":1,"pt":%d,"ct":"HEARTBEAT"}' % i)
        scr.giro(forza_svuota=True)
        assert scr._pieno and scr.righe_scritte == 4
        for i in range(3):
            scr.metti_stream(1, '{"op":"ocm","id":1,"pt":%d,"ct":"HEARTBEAT"}' % i)
        scr.giro(forza_svuota=True)
    assert scr.scartati_tetto == 3 and scr.righe_scritte == 4
    assert "tetto di disco" in caplog.text
    scr.chiudi()
    righe, info = AO.leggi_file(scr._percorso)
    assert info["chiusura"]["scartati_tetto"] == 3


def test_tetto_letto_dall_ambiente(monkeypatch):
    monkeypatch.setenv(RO.ENV_TETTO, "2")
    assert RO.tetto_byte() == 2 * 1024 * 1024
    for v in ("", "x", "-5", "0"):
        monkeypatch.setenv(RO.ENV_TETTO, v)
        assert RO.tetto_byte() == int(RO.TETTO_DEFAULT_MB * 1024 * 1024)


def test_rotazione_giornaliera(tmp_path, monkeypatch):
    giorni = iter(["20261011"] * 3 + ["20261012"] * 10)
    monkeypatch.setattr(RO, "giorno_utc", lambda ep_s=None: next(giorni))
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p", avvia_thread=False)
    for i in range(4):
        scr.metti_stream(1, '{"op":"ocm","id":1,"pt":%d,"ct":"HEARTBEAT"}' % i)
        scr.giro(forza_svuota=True)
    scr.chiudi()
    f1 = AO.file_del_giorno(str(tmp_path), "20261011")
    f2 = AO.file_del_giorno(str(tmp_path), "20261012")
    assert len(f1) == 1 and len(f2) == 1
    r1, i1 = AO.leggi_file(f1[0])
    r2, i2 = AO.leggi_file(f2[0])
    assert i1["chiusura"]["motivo"] == "giorno" and i2["chiusura"]["motivo"] == "fine_processo"
    assert sum(r["k"] == "stream" for r in r1) == 3 and sum(r["k"] == "stream" for r in r2) == 1


def test_thread_vero_scrive_e_chiude(tmp_path, monkeypatch):
    monkeypatch.setattr(RO, "GIRO_S", 0.01)
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p")
    scr.metti_stream(1, '{"op":"ocm","id":1,"pt":1,"ct":"HEARTBEAT"}')
    assert scr._thread is not None and scr._thread.daemon
    scr.chiudi()
    scr._thread.join(2)
    righe, info = AO.leggi_file(_tutti_i_file(str(tmp_path))[0])
    assert [r["k"] for r in righe] == ["avvio", "stream", "chiusura"]


# ---------------------------------------------------------------------------
# 5. lettura e analisi di una giornata
# ---------------------------------------------------------------------------
class _Orologio:
    def __init__(self) -> None:
        self.ep = PT0 * 1000
        self.mono = 10_000_000

    def __call__(self):
        return self.ep, self.mono

    def avanza(self, ms: float) -> None:
        self.ep += int(ms * 1000)
        self.mono += int(ms * 1000)


def _giornata(tmp_path, monkeypatch) -> str:
    """Due processi: il runner (REST + stream) e una sessione scalper (solo
    stream, vede gli stessi ordini). Istanti controllati."""
    base = str(tmp_path / "giorno")
    monkeypatch.setattr(RO, "giorno_utc", lambda ep_s=None: "20261011")
    oro = _Orologio()
    monkeypatch.setattr(RO, "adesso_us", oro)

    def ocm(clk, pt, uo=None, ct=None):
        m = {"op": "ocm", "id": 5, "clk": clk, "pt": pt}
        if ct:
            m["ct"] = ct
        if uo is not None:
            m["oc"] = [{"id": MID, "orc": [{"id": SEL, "uo": [uo]}]}]
        return json.dumps(m)

    a = RO.Scrittore(cartella=base, servizio="runner", avvia_thread=False)
    s2 = RO.Scrittore(cartella=base, servizio="scalper", avvia_thread=False)
    monkeypatch.setattr(os, "getpid", lambda: 111)
    RO._azzera_per_test(a)
    a.metti_record({"k": "sub", "ep_us": oro.ep, "mono_us": oro.mono, "sid": 1,
                    "ripresa": False, "heartbeat_ms": None, "conflate_ms": None})
    a.metti_stream(1, ocm("c0", PT0, ct="SUB_IMAGE"))
    a.metti_record({"k": "dec", "ep_us": oro.ep, "mono_us": oro.mono,
                    "cor": "6279886fde090-1401", "chiave": "cmd-1", "decisione_ms": PT0 - 30})
    invio = oro()
    oro.avanza(40)
    # il primo ocm arriva PRIMA della risposta della REST (succede in produzione)
    a.metti_stream(1, ocm("c1", PT0 + 40, _uo("381200000001", "E", 0, 4)))
    oro.avanza(25)
    params = {"marketId": MID, "instructions": [_istr()], "customerRef": "a" * 32,
              "customerStrategyRef": "live"}
    RO.registra_rest(via="bflw", method="SportsAPING/v1.0/placeOrders", params=params,
                     invio=invio, risposta=oro(), esito=_risultato("placeOrders", params))
    oro.avanza(300)
    a.metti_stream(1, ocm("c2", PT0 + 400, _uo("381200000001", "E", 1.5, 2.5, avp=2.5)))
    oro.avanza(500)
    a.metti_stream(1, ocm("c3", PT0 + 900, _uo("381200000001", "EC", 4, 0, avp=2.5)))
    # ordine dal SITO: nessun rfo/rfs
    oro.avanza(1000)
    sito = _uo("381299999999", "E", 0, 10)
    del sito["rfo"], sito["rfs"]
    a.metti_stream(1, ocm("c4", PT0 + 1900, sito))
    # ordine di un ALTRO processo (riferimenti di un bot, nessuna REST registrata)
    altro = _uo("381277777777", "E", 0, 2, rfo="abc-1", rfs="omega")
    a.metti_stream(1, ocm("c4b", PT0 + 1950, altro))
    # silenzio di 40 s, poi una ripartenza dello stream (nuova sottoscrizione)
    oro.avanza(40_000)
    a.metti_stream(1, ocm("c5", PT0 + 41_900, ct="HEARTBEAT"))
    a.metti_record({"k": "sub", "ep_us": oro.ep, "mono_us": oro.mono, "sid": 2,
                    "ripresa": False})
    a.metti_stream(2, json.dumps({"op": "status", "id": 6, "statusCode": "FAILURE",
                                  "errorCode": "TIMEOUT", "connectionClosed": True}))
    a.metti_stream(2, ocm("d0", PT0 + 42_000, ct="SUB_IMAGE"))
    a.giro(forza_svuota=True)
    a.chiudi()
    # la sessione scalper vede lo stesso ordine (copia) e muore senza chiusura
    monkeypatch.setattr(os, "getpid", lambda: 222)
    s2.metti_record({"k": "sub", "ep_us": oro.ep, "mono_us": oro.mono, "sid": 1,
                     "ripresa": False})
    s2.metti_stream(1, ocm("c3", PT0 + 900, _uo("381200000001", "EC", 4, 0, avp=2.5)))
    s2.giro(forza_svuota=True)
    s2._fh.close()  # processo morto: nessuna riga di chiusura
    s2._fh = None
    s2._chiuso = True
    RO._azzera_per_test(None)
    return base


def test_analisi_giornata(tmp_path, monkeypatch):
    base = _giornata(tmp_path, monkeypatch)
    a = AO.analizza_giorno(base, "20261011")
    assert len(a["file"]) == 2
    seq = {r["bet_id"]: r for r in a["sequenze"]}
    o = seq["381200000001"]
    assert o["origine"] == "nostro" and o["attore"] == "desktop"
    passi = [(e["tipo"], e.get("stato"), e.get("sm")) for e in o["eventi"]]
    assert passi == [("ocm", "EXECUTABLE", 0), ("ocm", "EXECUTABLE", 1.5),
                     ("ocm", "EXECUTION_COMPLETE", 4)]
    assert o["stato_finale"] == "EXECUTION_COMPLETE" and o["parziali"] == 1
    assert o["copie_ocm"] == 1, "la copia della sessione scalper non riconosciuta"
    assert o["place"]["durata_ms"] == 65.0
    assert o["risposta_primo_ocm_ms"] == -25.0 and o["invio_primo_ocm_ms"] == 40.0
    assert o["decisione"]["chiave"] == "cmd-1" and o["decisione_invio_ms"] == 30.0
    assert [x["bet_id"] for x in a["ocm_prima_della_risposta"]] == ["381200000001"]
    assert a["ocm_prima_della_risposta"][0]["anticipo_ms"] == 25.0
    assert [x["bet_id"] for x in a["ordini_sito"]] == ["381299999999"]
    assert seq["381277777777"]["origine"] == "altro_processo"
    assert seq["381277777777"]["attore"] == "bot:omega"
    assert a["conteggi"]["ordini_altri_processi"] == 1
    assert a["latenze"]["rest_ms_per_metodo"]["placeOrders"]["p50"] == 65.0
    b = {x["servizio"]: x for x in a["buchi"]}
    assert b["runner"]["ripartenze"] == 1 and len(b["runner"]["silenzi"]) == 1
    assert b["runner"]["silenzi"][0]["secondi"] == 40.0
    assert b["runner"]["status_errori"][0]["errorCode"] == "TIMEOUT"
    assert b["runner"]["fine_pulita"] and b["runner"]["seq_mancanti"] == 0
    assert b["scalper"]["fine_pulita"] is False
    assert a["ci_sono_buchi"] is True
    testo = AO.formatta(a)
    assert "OCM PRIMA DELLA RISPOSTA REST: 1" in testo and "ORDINI DEL SITO: 1" in testo
    assert testo.isascii()


def test_analisi_senza_buchi_dice_nessuno(tmp_path, monkeypatch):
    monkeypatch.setattr(RO, "giorno_utc", lambda ep_s=None: "20261011")
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p", avvia_thread=False)
    scr.metti_record({"k": "sub", "ep_us": 1, "mono_us": 1, "sid": 1, "ripresa": False})
    scr.metti_stream(1, json.dumps({"op": "ocm", "id": 1, "clk": "a", "pt": 1, "ct": "SUB_IMAGE"}))
    scr.giro(forza_svuota=True)
    scr.chiudi()
    a = AO.analizza_giorno(str(tmp_path), "20261011")
    assert a["ci_sono_buchi"] is False
    assert "BUCHI: nessuno" in AO.formatta(a)


def test_analisi_righe_perse_e_coda_tronca(tmp_path, monkeypatch):
    monkeypatch.setattr(RO, "giorno_utc", lambda ep_s=None: "20261011")
    monkeypatch.setattr(RO, "CODA_MAX", 2)
    scr = RO.Scrittore(cartella=str(tmp_path), servizio="p", avvia_thread=False)
    for i in range(4):  # 2 accodate, 2 perse (buco di sequenza in mezzo)
        scr.metti_stream(1, json.dumps({"op": "ocm", "id": 1, "clk": str(i), "pt": i,
                                        "ct": "HEARTBEAT"}))
        if i == 0:
            scr.giro()
    scr.giro(forza_svuota=True)
    for i in range(50):
        scr.metti_stream(1, json.dumps({"op": "ocm", "id": 1, "clk": "z%d" % i, "pt": i,
                                        "ct": "HEARTBEAT"}))
        scr.giro(forza_svuota=True)
    percorso = scr._percorso
    scr._fh.close()
    scr._fh = None
    scr._chiuso = True
    with open(percorso, "rb") as fh:
        dati = fh.read()
    with open(percorso, "wb") as fh:
        fh.write(dati[:-7])  # coda del gzip tronca (processo morto)
    righe, info = AO.leggi_file(percorso)
    assert info["troncato"] is True and len(righe) >= 40
    a = AO.analizza([(righe, info)])
    b = a["buchi"][0]
    assert b["seq_mancanti"] >= 1 and b["coda_gzip_tronca"] and a["ci_sono_buchi"]


def test_analisi_da_riga_di_comando(tmp_path, monkeypatch, capsys):
    base = _giornata(tmp_path, monkeypatch)
    out = tmp_path / "a.json"
    assert AO.main(["--cartella", base, "--giorno", "20261011", "--json", str(out)]) == 0
    assert "REGISTRO ORDINI - file: 2" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="ascii"))["conteggi"]["ordini_sito"] == 1


# ---------------------------------------------------------------------------
# 6. codice ASCII e agganci di UNA riga
# ---------------------------------------------------------------------------
def test_moduli_ascii():
    for m in (RO, AO):
        with open(m.__file__, "rb") as fh:
            assert fh.read().isascii(), m.__file__


@pytest.mark.parametrize("percorso,attesa", [
    ("Betfair/stream/auth.py", "_ro.aggancia_api_client(client)"),
    ("Betfair/client.py", "_ro.rest_nostro(method, params"),
    ("Betfair/stream/tempi_ordine.py", "_ro.decisione(order, voce)"),
])
def test_agganci_di_una_riga_dietro_l_interruttore(percorso, attesa):
    radice = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    with open(os.path.join(radice, percorso), encoding="utf-8") as fh:
        righe = [r for r in fh if "_ro." in r and "import" not in r]
    assert len(righe) == 1 and attesa in righe[0] and "if _ro.attivo()" in righe[0]
