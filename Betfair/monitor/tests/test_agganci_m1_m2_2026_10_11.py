"""Agganci M-2 lasciati dopo M-1 (11/10/2026, ``M2_MISURE.md`` "Cosa resta a M-1").

Tre agganci, tutti dietro ``MONITOR_SALUTE`` (``_mon.ATTIVO``), spenti di serie:

  1. ``ocm`` dello stream ORDINI contati in "Salute": il tee di M-1 sul listener
     dello stream ordini (``registratore_ordini._monta_tee``) chiama
     ``sonde.osserva_stream("ordini-<sport>", riga)``. ``auth.build_client``
     aggancia il client se ALMENO UNO fra registratore (``REGISTRO_ORDINI``) e
     monitor e' acceso: i due interruttori sono indipendenti;
  2. latenza esito -> bot: ``ClientEsiti.incassa`` (lettore degli esiti ordini
     dei bot, ``esiti_ordini_canale.py``) chiama ``sonde.ricevuto_canale`` col
     modo della riga (paper e live MAI sommati);
  3. ``invio=req.ricevuto_ms`` nel ``tempi_ordine.nuovo`` della strada canale di
     ``live_order_worker._process_local_requests``: il totale M2 del clic
     (``decisione_risposta_ms.desktop.canale.<modo>``) non resta ``na``. Con
     ``ricevuto_ms`` = 0 (monitor spento) nessuna misura.

Finti con le chiavi e i tipi del vero (gli stessi dei test M-1, M-2 e F0):
APIClient VERO di betfairlightweight da ``auth.build_client`` VERO con
l'adattatore di requests sostituito; ``OrderStream.run`` VERO di flumine con il
solo socket sostituito (righe ``connection``/``status``/``ocm`` dello stream
ordini Betfair), listener VERO; ``LocalChannel`` VERO (publish e
``_on_message``), ``ClientEsiti`` VERO, righe dello specchio da
``LiveTradingStrategy._order_row`` VERA; ``LocalRequest`` VERE, worker VERO,
``tempi_ordine`` VERO e handler di log VERO della Salute.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.monitor import registratore_ordini as RO
from Betfair.monitor import sonde as M
from Betfair.monitor.tests.test_registratore_ordini_2026_10_11 import (  # noqa: F401
    MID, _build_client, _gira_righe, _righe, _SocketFinto, _thread_registro,
    righe_stream_ordini)

# ---------------------------------------------------------------------------
# fixture: i due interruttori, indipendenti
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    """Ogni test parte col monitor e il registratore SPENTI e senza avvisi."""
    monkeypatch.setattr(RO, "_consenti_in_test", True)
    monkeypatch.setattr(RO, "nel_banco", lambda: False)
    monkeypatch.setenv(RO.ENV, "0")
    RO._azzera_per_test(None)
    RO._ULTIMO_AVVISO.clear()
    M.ferma()
    M.REGISTRO.azzera_tutto()
    yield
    M.ferma()
    M.REGISTRO.azzera_tutto()
    RO._azzera_per_test(None)
    RO._ULTIMO_AVVISO.clear()


def _accendi_monitor(monkeypatch, sport: Any = "calcio", servizio: str = "prova-test") -> None:
    monkeypatch.setenv(M.ENV, "1")
    monkeypatch.setattr(M, "nel_banco", lambda: False)
    assert M.avvia(servizio, sport=sport, scrittore=False, _consenti_in_test=True)


def _accendi_registratore(monkeypatch, tmp_path) -> RO.Scrittore:
    monkeypatch.setenv(RO.ENV, "1")
    scr = RO.Scrittore(cartella=str(tmp_path / "ordini"), servizio="prova", avvia_thread=False)
    RO._azzera_per_test(scr)
    return scr


# ---------------------------------------------------------------------------
# 1. ocm dello stream ORDINI in Salute
# ---------------------------------------------------------------------------
def _righe_fresche(ritardo_ms: int = 40) -> List[str]:
    """Le righe dello stream ordini dei test M-1, con ``pt`` = adesso - ritardo
    (cosi' ``rx - pt`` e' controllabile)."""
    pt = int(time.time() * 1000) - ritardo_ms
    out = []
    for r in righe_stream_ordini(1001, 1002):
        d = json.loads(r)
        if "pt" in d:
            d["pt"] = pt
        out.append(json.dumps(d, separators=(",", ":")))
    return out


def _gira(monkeypatch, righe: List[str]):
    """``OrderStream.run`` VERO; ritorna (errore, id, byte inviati, libri) e il client."""
    c = _build_client(monkeypatch)
    return _gira_righe(monkeypatch, c, list(righe)), c


def test_ocm_tutto_spento_nessun_wrapper_nessuna_misura(monkeypatch, tmp_path):
    monkeypatch.setenv(RO.ENV_DIR, str(tmp_path / "ordini"))
    esito, c = _gira(monkeypatch, _righe_fresche())
    assert "request" not in vars(c.betting), "tutto spento ma betting.request avvolto"
    assert "create_stream" not in vars(c.streaming), "tutto spento ma create_stream avvolto"
    assert esito[3] > 0, "il listener vero non ha prodotto ordini"
    f = M.REGISTRO.fotografa_e_azzera()
    assert f == {"contatori": {}, "tratti": {}, "valori": {}}
    assert RO._SCRITTORE is None and not (tmp_path / "ordini").exists()
    assert not _thread_registro()


def test_ocm_solo_monitor_conta_e_non_registra(monkeypatch, tmp_path):
    monkeypatch.setenv(RO.ENV_DIR, str(tmp_path / "ordini"))
    righe = _righe_fresche(40)
    rif, _c0 = _gira(monkeypatch, righe)            # riferimento: tutto spento
    _accendi_monitor(monkeypatch, sport="calcio")
    M.REGISTRO.azzera_tutto()
    t0 = time.time() * 1000.0
    esito, c = _gira(monkeypatch, righe)
    t1 = time.time() * 1000.0
    # registratore spento: SOLO create_stream e' avvolto (mai la REST)
    assert "request" not in vars(c.betting), "registratore spento ma REST avvolta"
    assert "create_stream" in vars(c.streaming)
    # flumine vede lo stesso: stesso esito, stesso id, stessi byte, stessi libri
    assert esito == rif, "il tee della Salute cambia cio' che vede flumine"
    # nessuna traccia del registratore
    assert RO._SCRITTORE is None, "registratore spento ma scrittore creato"
    assert not (tmp_path / "ordini").exists() and not _thread_registro()
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["stream_ocm"] == {"ordini-calcio": 5}     # SUB_IMAGE, 3 dati, battito
    assert f["contatori"]["stream_status"] == {"ordini-calcio SUCCESS": 2}
    assert f["contatori"]["stream_altri"] == {"ordini-calcio": 1}   # ``connection``
    assert f["valori"]["connessioni_disponibili"] == {"ordini-calcio": 9}
    tr = f["tratti"]["ordini_rx_pt_ms.ordini-calcio"]
    assert tr["n"] == 5
    assert tr["min"] >= 40 and tr["max"] <= 40 + (t1 - t0) + 50
    assert "stream_msg" not in f["contatori"], "ocm contati come mcm"


def test_ocm_entrambi_accesi_registra_e_conta(monkeypatch, tmp_path):
    scr = _accendi_registratore(monkeypatch, tmp_path)
    _accendi_monitor(monkeypatch, sport="calcio")
    M.REGISTRO.azzera_tutto()
    righe = _righe_fresche()
    try:
        esito, c = _gira(monkeypatch, righe)
        assert "request" in vars(c.betting) and "create_stream" in vars(c.streaming)
        f = M.REGISTRO.fotografa_e_azzera()
        assert f["contatori"]["stream_ocm"] == {"ordini-calcio": 5}
        su_disco = _righe(scr)
    finally:
        scr.chiudi()
    assert [r["msg"] for r in su_disco if r["k"] == "stream"] == [json.loads(x) for x in righe]
    assert len([r for r in su_disco if r["k"] == "sub"]) == 1


def test_ocm_solo_registratore_nessuna_misura_come_prima(monkeypatch, tmp_path):
    scr = _accendi_registratore(monkeypatch, tmp_path)
    righe = _righe_fresche()
    try:
        _gira(monkeypatch, righe)
        su_disco = _righe(scr)
    finally:
        scr.chiudi()
    assert len([r for r in su_disco if r["k"] == "stream"]) == len(righe)
    assert M.REGISTRO.fotografa_e_azzera() == {"contatori": {}, "tratti": {}, "valori": {}}


def test_ocm_sport_del_processo_tennis_mai_mischiato(monkeypatch, tmp_path):
    _accendi_monitor(monkeypatch, sport="tennis", servizio="runner-tennis")
    M.REGISTRO.azzera_tutto()
    _gira(monkeypatch, _righe_fresche())
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["stream_ocm"] == {"ordini-tennis": 5}
    assert set(k for k in f["tratti"] if k.startswith("ordini_rx_pt_ms.")) == {
        "ordini_rx_pt_ms.ordini-tennis"}


def test_ocm_sorgente_senza_sport_e_il_servizio(monkeypatch):
    assert RO.sorgente_salute() is None                       # monitor spento
    _accendi_monitor(monkeypatch, sport=None, servizio="scalper sessione/35.1")
    assert RO.sorgente_salute() == "ordini-scalper-sessione-35.1"


def test_ocm_false_del_listener_e_id_identici_con_misura(monkeypatch, tmp_path):
    """Lo ``status`` FAILURE con ``connectionClosed`` ferma lo stream con
    ListenerError: col tee della Salute deve succedere lo STESSO."""
    base = righe_stream_ordini(1001, 1002)
    righe = base[:5] + [json.dumps(
        {"op": "status", "id": 1001, "statusCode": "FAILURE", "errorCode": "TIMEOUT",
         "errorMessage": "x", "connectionClosed": True})] + base[5:]
    rif, _c = _gira(monkeypatch, righe)
    _accendi_monitor(monkeypatch)
    esito, _c = _gira(monkeypatch, righe)
    assert rif[0] == "ListenerError" and esito == rif and esito[1] == 1001


def test_ocm_misura_che_solleva_non_rompe_lo_stream(monkeypatch, tmp_path, caplog):
    righe = _righe_fresche()
    rif, _c = _gira(monkeypatch, righe)
    _accendi_monitor(monkeypatch)

    def _esplode(*_a, **_k):
        raise RuntimeError("sonda rotta (iniettata)")

    monkeypatch.setattr(M, "osserva_stream", _esplode)
    with caplog.at_level(logging.WARNING, logger=RO.__name__):
        esito, _c = _gira(monkeypatch, righe)
    assert esito == rif, "un errore della misura ha cambiato lo stream ordini"
    assert any("ocm non contato in Salute" in r.getMessage() for r in caplog.records)


def test_ocm_stream_dei_prezzi_non_toccato(monkeypatch):
    from betfairlightweight import StreamListener
    from betfairlightweight.streaming.betfairstream import BetfairStream

    _accendi_monitor(monkeypatch)
    c = _build_client(monkeypatch)
    sock = _SocketFinto([json.dumps({"op": "connection", "connectionId": "x"}),
                         json.dumps({"op": "status", "id": 3, "statusCode": "SUCCESS"})])
    monkeypatch.setattr(BetfairStream, "_create_socket", lambda self: sock)
    lis = StreamListener()
    st = c.streaming.create_stream(unique_id=1, listener=lis)
    st.subscribe_to_markets(market_filter={"marketIds": [MID]}, market_data_filter={})
    assert "on_data" not in vars(lis), "tee della Salute montato su uno stream dei prezzi"


def test_aggancio_auth_una_riga_coi_due_interruttori():
    radice = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    with open(os.path.join(radice, "Betfair", "stream", "auth.py"), encoding="utf-8") as fh:
        righe = [r for r in fh if "_ro.aggancia_api_client" in r]
    assert len(righe) == 1 and "if _ro.attivo() or _mon.ATTIVO:" in righe[0]


# ---------------------------------------------------------------------------
# 2. latenza esito -> bot (lettore degli esiti ordini dei bot)
# ---------------------------------------------------------------------------
class _LoopSubito:
    def __init__(self) -> None:
        self.testi: List[str] = []

    def call_soon_threadsafe(self, fn):
        fn()

    def create_task(self, x):
        self.testi.append(x)


def _canale_runner():
    """``LocalChannel`` VERO (mai avviato) con un lettore degli esiti collegato."""
    from Betfair.stream.esiti_ordini_canale import TOPIC_CONTO, TOPIC_CONTO_PAPER
    from Betfair.stream.local_channel import LocalChannel

    ch = LocalChannel(0, sport="calcio", solo_lettura=False, token="t", origini=[])
    loop = _LoopSubito()
    ws = object()
    ch._loop = loop
    ch._clients = {ws}
    ch._lettori = {ws: frozenset({"order", TOPIC_CONTO, TOPIC_CONTO_PAPER})}
    ch._ricalcola_lettori()
    ch._n_clients = 1
    ch._client_pronti = 1
    ch._safe_send = lambda w, text: text
    return ch, loop


def _riga_specchio(mode: str, rid: int, status: str = "EXECUTION_COMPLETE") -> Dict[str, Any]:
    """La riga che il runner PUBBLICA sul topic ``order``: ``_order_row`` VERO di
    ``LiveTradingStrategy`` + ``updated_at`` (come ``db.upsert_live_order``)."""
    from Betfair.stream.engine import live_trading_strategy as strat

    ot = SimpleNamespace(ORDER_TYPE=SimpleNamespace(name="LIMIT"), price=110.0, size=2.0,
                         persistence_type="LAPSE")
    ordine = SimpleNamespace(
        id="OID-%d" % rid, bet_id="sim%d" % rid, market_id="m-1.100", selection_id=4,
        handicap=0.0, side="LAY", status=SimpleNamespace(name=status), order_type=ot,
        size_matched=2.0, size_remaining=0.0, size_cancelled=0.0, size_lapsed=0.0,
        size_voided=0.0, average_price_matched=112.0, customer_order_ref="awlq%d" % rid,
        responses=SimpleNamespace(date_time_placed="2026-10-11T10:00:00+00:00"),
        date_time_status_update="2026-10-11T10:00:01+00:00")
    s = strat.LiveTradingStrategy(market_filter={"marketIds": ["m-1.100"]}, session=None,
                                  mode=mode)
    riga = s._order_row(ordine, event_id="1.100", market_id="m-1.100")
    riga["updated_at"] = "2026-10-11T10:00:01+00:00"
    return riga


def _client_esiti(topic: str = "order"):
    from Betfair.stream import esiti_ordini_canale as EO

    terminali: List[Dict[str, Any]] = []
    c = EO.ClientEsiti(EO.MemoriaEsiti(), su_terminale=terminali.append, porta_ws=0,
                       topic=topic)
    return c, terminali


def _giro_esiti() -> Dict[str, Any]:
    """Il runner pubblica (canale VERO), il bot incassa (lettore VERO): cosa ha
    fatto il bot, per confrontare spento e acceso."""
    ch, loop = _canale_runner()
    c, terminali = _client_esiti()
    ch.publish("order", _riga_specchio("paper", 1))
    ch.publish("order", _riga_specchio("live", 2))
    ch.publish("order", _riga_specchio("paper", 1))          # la stessa: vecchia, scartata
    ch.publish("scan_calcio", {"x": 1})       # non e' un topic del lettore: il canale non lo manda
    esiti = [c.incassa(t) for t in loop.testi]
    esiti.append(c.incassa(json.dumps({"t": "hello", "d": {}})))
    return {"esiti": esiti, "terminali": [(r["mode"], r["client_order_ref"]) for r in terminali],
            "memoria": c.memoria.stato(), "errori": c.errori,
            "buste": [sorted(json.loads(t)) for t in loop.testi]}


def test_esiti_spento_identico_nessuna_misura():
    out = _giro_esiti()
    assert out["esiti"] == [True, True, False, False]
    assert out["terminali"] == [("paper", "awlq1"), ("live", "awlq2")]
    assert all(b == ["d", "t"] for b in out["buste"]), "monitor spento ma busta con ts"
    assert M.REGISTRO.fotografa_e_azzera() == {"contatori": {}, "tratti": {}, "valori": {}}


def test_esiti_acceso_latenza_per_topic_e_modo(monkeypatch):
    spento = _giro_esiti()
    _accendi_monitor(monkeypatch)
    M.REGISTRO.azzera_tutto()
    t0 = time.time() * 1000.0
    acceso = _giro_esiti()
    t1 = time.time() * 1000.0
    # il bot fa esattamente lo stesso
    for k in ("esiti", "terminali", "memoria", "errori"):
        assert acceso[k] == spento[k], k
    assert all(b == ["d", "t", "ts"] for b in acceso["buste"])
    f = M.REGISTRO.fotografa_e_azzera()
    # paper e live in chiavi separate; ``scan_calcio`` e ``hello`` non sono del lettore
    assert f["contatori"]["canale_ric"] == {"order.live": 1, "order.paper": 2}
    assert f["tratti"]["canale_ricezione_ms.order.paper"]["n"] == 2
    assert f["tratti"]["canale_ricezione_ms.order.live"]["n"] == 1
    assert not [k for k in f["tratti"] if k == "canale_ricezione_ms.order"]
    for k in ("canale_ricezione_ms.order.paper", "canale_ricezione_ms.order.live"):
        assert 0 <= f["tratti"][k]["min"] and f["tratti"][k]["max"] <= (t1 - t0) + 2


def test_esiti_acceso_ts_zero_o_assente_nessuna_misura(monkeypatch):
    _accendi_monitor(monkeypatch)
    M.REGISTRO.azzera_tutto()
    c, _t = _client_esiti()
    riga = _riga_specchio("paper", 7)
    assert c.incassa(json.dumps({"t": "order", "d": riga, "ts": 0}, default=str)) is True
    riga2 = _riga_specchio("live", 8)
    assert c.incassa(json.dumps({"t": "order", "d": riga2}, default=str)) is True
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["canale_ric"] == {"order.live": 1, "order.paper": 1}
    assert f["tratti"] == {}, "ts 0 o assente ma latenza misurata"


def test_esiti_acceso_conto_live_e_paper_separati(monkeypatch):
    from Betfair.stream import esiti_ordini_canale as EO

    _accendi_monitor(monkeypatch)
    M.REGISTRO.azzera_tutto()
    c = EO.ClientEsiti(EO.MemoriaConto(), porta_ws=0, topic=EO.TOPIC_CONTO_TUTTI)
    adesso = int(time.time() * 1000)
    live = EO.payload_conto(SimpleNamespace(orders=[], streaming_update={"id": "1.5"},
                                            publish_time=adesso, streaming_snap=False),
                            ricevuto_ms=adesso)
    paper = EO.payload_conto_paper("1.5", [], ricevuto_ms=adesso)
    assert c.incassa(json.dumps({"t": EO.TOPIC_CONTO, "d": live, "ts": adesso - 2})) is True
    assert c.incassa(json.dumps({"t": EO.TOPIC_CONTO_PAPER, "d": paper, "ts": adesso - 2})) is True
    # una fotografia paper sul topic live: rifiutata come prima, ma la busta e' arrivata
    assert c.incassa(json.dumps({"t": EO.TOPIC_CONTO, "d": paper, "ts": adesso - 2})) is False
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["canale_ric"] == {"conto.live": 1, "conto.paper": 1,
                                            "conto_paper.paper": 1}
    assert f["tratti"]["canale_ricezione_ms.conto.live"]["min"] >= 2


def test_esiti_registro_che_solleva_non_arriva_al_bot(monkeypatch):
    _accendi_monitor(monkeypatch)

    def _esplode(*_a, **_k):
        raise RuntimeError("registro rotto (iniettato)")

    monkeypatch.setattr(M.REGISTRO, "conta", _esplode)
    monkeypatch.setattr(M.REGISTRO, "tratto", _esplode)
    c, terminali = _client_esiti()
    riga = _riga_specchio("paper", 3)
    assert c.incassa(json.dumps({"t": "order", "d": riga, "ts": int(time.time() * 1000)},
                                default=str)) is True
    assert [r["client_order_ref"] for r in terminali] == ["awlq3"] and c.errori == 0


def test_ricevuto_canale_senza_per_modo_come_prima(monkeypatch):
    """Il lettore dello scanner (``canale_scan``) non passa ``per_modo``: chiavi
    di sempre, nessun suffisso."""
    _accendi_monitor(monkeypatch)
    M.REGISTRO.azzera_tutto()
    M.ricevuto_canale({"t": "scan_calcio", "d": {"mode": "paper"}, "ts": M.ora_ms() - 1})
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["canale_ric"] == {"scan_calcio": 1}
    assert list(f["tratti"]) == ["canale_ricezione_ms.scan_calcio"]


# ---------------------------------------------------------------------------
# 3. ``invio=req.ricevuto_ms`` sulla strada canale del worker calcio
# ---------------------------------------------------------------------------
@pytest.fixture
def worker_paper(monkeypatch):
    """Il worker calcio VERO in PAPER (stesse sostituzioni dei test F0)."""
    from Betfair.stream import live_order_worker as wk
    from Betfair.stream import tempi_ordine as T

    monkeypatch.setenv("LIVE_TEMPI_ORDINE", "1")
    T._azzera_per_test()
    monkeypatch.setattr(wk, "_live_order_mode", lambda: "PAPER")
    monkeypatch.setattr(wk, "_modo_processo", lambda: "PAPER")
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_db_kill_switch", lambda: False)
    monkeypatch.setattr(wk, "_jurisdiction", lambda: "it")
    monkeypatch.setattr(wk, "_batch", lambda: 5)
    monkeypatch.setattr(wk, "_max_stake", lambda: 10.0)
    monkeypatch.setattr(wk, "_LOCAL_SEEN", {})
    yield wk
    T._azzera_per_test()


def _canale_ordini(monkeypatch):
    from Betfair.stream import local_channel as LC

    ch = LC.LocalChannel(59996, "calcio")
    risposte: List[tuple] = []
    monkeypatch.setattr(ch, "respond", lambda req, ok, data=None, error=None:
                        risposte.append((req.msg_id, ok, error)))
    monkeypatch.setattr(LC, "get_channel", lambda: ch)
    ws = object()
    ch._autorizzati.add(ws)            # la pagina col token giusto
    return ch, ws, risposte


def _comando_pagina(emesso_ms: int, market_id: str = "1.1") -> Dict[str, Any]:
    """Il comando ``order`` della pagina (``localOrderApi.send``) con ``emesso_ms``;
    ``client_ref`` = UUID nuovo a ogni clic, come la pagina (niente dedup fra i giri)."""
    return {"action": "place", "mode": "paper", "market_id": market_id, "selection_id": 47999,
            "handicap": 0, "side": "back", "order_type": "LIMIT", "price": 3.0, "size": 5.0,
            "persistence": "LAPSE", "client_ref": str(uuid.uuid4()), "emesso_ms": emesso_ms}


def _clic(monkeypatch, wk, caplog, *, via_canale: bool = True, market_id: str = "1.1",
          ritardo_canale_ms: int = 0) -> Dict[str, Any]:
    """Un clic della pagina servito dal worker VERO: comando nel canale VERO
    (``_on_message``, che scrive ``ricevuto_ms``), drenaggio e dispatch, risposta
    di Betfair e abbinamento come li registra flumine."""
    from Betfair.stream import local_channel as LC
    from Betfair.stream.tests.test_live_order_worker import _STRAT, _FakeFlumine, _FakeMarket
    from Betfair.stream.tests.test_tempi_ordine_f0_2026_09_25 import (
        _righe as _righe_tempi, _risposta_e_abbinamento, _SbSpia, _strategia_specchio)

    caplog.clear()
    ch, ws, risposte = _canale_ordini(monkeypatch)
    emesso = int(time.time() * 1000) - 7
    if via_canale:
        ch._on_message(ws, json.dumps({"id": 1, "m": "order",
                                       "p": _comando_pagina(emesso, market_id)}))
    else:
        ch._requests.put_nowait(LC.LocalRequest(ws=ws, msg_id=1, method="order",
                                                params=_comando_pagina(emesso, market_id)))
    if ritardo_canale_ms:
        time.sleep(ritardo_canale_ms / 1000.0)
    market = _FakeMarket("1.1")
    n = wk._process_local_requests(_SbSpia([]), _FakeFlumine({"1.1": market}), "paper", _STRAT)
    piazzati = []
    for _nome, order, kw in market.calls:
        piazzati.append((order.selection_id, order.side, order.order_type.price,
                         order.order_type.size, sorted(kw)))
        _risposta_e_abbinamento(order, int(time.time() * 1000))
        _strategia_specchio(monkeypatch).process_orders(market, [order])
    return {"n": n, "risposte": risposte, "piazzati": piazzati,
            "righe": _righe_tempi(caplog), "emesso": emesso}


def _num(c: Dict[str, str], k: str):
    v = c.get(k)
    return None if v in (None, "na") else float(v)


def test_clic_spento_identico_a_prima_nessuna_misura(monkeypatch, worker_paper, caplog):
    caplog.set_level(logging.INFO, logger="Betfair.stream.tempi_ordine")
    out = _clic(monkeypatch, worker_paper, caplog)
    assert out["n"] == 1 and out["risposte"][0][1] is True and len(out["piazzati"]) == 1
    (c,) = out["righe"]
    assert c["strada"] == "canale" and M.attore_da_rif(c["rif"]) == "desktop"
    # ``ricevuto_ms`` = 0 a monitor spento: invio assente, come prima
    assert c["decisione_ms"] == "na" and c["ricezione_ms"] == "na"
    assert M.REGISTRO.fotografa_e_azzera() == {"contatori": {}, "tratti": {}, "valori": {}}


def test_clic_acceso_totale_m2_presente_e_coerente(monkeypatch, worker_paper, caplog):
    caplog.set_level(logging.INFO, logger="Betfair.stream.tempi_ordine")
    spento = _clic(monkeypatch, worker_paper, caplog)
    _accendi_monitor(monkeypatch)
    M.REGISTRO.azzera_tutto()
    acceso = _clic(monkeypatch, worker_paper, caplog, ritardo_canale_ms=20)
    # l'ordine e la risposta al clic sono gli stessi
    assert acceso["piazzati"] == spento["piazzati"]
    assert [r[1:] for r in acceso["risposte"]] == [r[1:] for r in spento["risposte"]]
    (c,) = acceso["righe"]
    dec, ric = _num(c, "decisione_ms"), _num(c, "ricezione_ms")
    assert dec is not None and ric is not None, c
    assert 7 <= dec < 7 + 1000          # clic -> arrivo sul canale
    assert ric >= 19                    # arrivo -> drenaggio (il canale ha atteso 20 ms)
    # ``ricevuto_ms`` e' l'orologio del PC come il clic: nessun tratto a orologi misti
    assert "decisione:" not in c["orologi"] and "ricezione:" not in c["orologi"], c["orologi"]
    f = M.REGISTRO.fotografa_e_azzera()
    chiave = "desktop.canale.paper"
    for nome in ("decisione_invio_ms", "invio_presa_ms", "presa_place_ms",
                 "place_risposta_ms", "decisione_risposta_ms"):
        assert f["tratti"][nome + "." + chiave]["n"] == 1, nome
    somma = sum(f["tratti"][n + "." + chiave]["somma"] for n in (
        "decisione_invio_ms", "invio_presa_ms", "presa_place_ms", "place_risposta_ms"))
    assert f["tratti"]["decisione_risposta_ms." + chiave]["somma"] == pytest.approx(somma)
    assert f["contatori"]["ordini_misurati"] == {chiave: 1}


def test_clic_acceso_ricevuto_zero_nessuna_misura_falsa(monkeypatch, worker_paper, caplog):
    """Una ``LocalRequest`` con ``ricevuto_ms`` = 0 (di serie della dataclass,
    come a monitor spento): nessun invio, nessun totale, nessun tratto falso."""
    caplog.set_level(logging.INFO, logger="Betfair.stream.tempi_ordine")
    _accendi_monitor(monkeypatch)
    M.REGISTRO.azzera_tutto()
    out = _clic(monkeypatch, worker_paper, caplog, via_canale=False)
    (c,) = out["righe"]
    assert c["decisione_ms"] == "na" and c["ricezione_ms"] == "na"
    f = M.REGISTRO.fotografa_e_azzera()
    assert not [k for k in f["tratti"] if k.startswith(("decisione_invio_ms.",
                                                        "invio_presa_ms.",
                                                        "decisione_risposta_ms."))], f["tratti"]
    assert f["tratti"]["presa_place_ms.desktop.canale.paper"]["n"] == 1


def test_clic_acceso_errore_del_comando_invariato(monkeypatch, worker_paper, caplog):
    """Mercato non sottoscritto: il comando fallisce con lo STESSO errore a
    monitor spento e acceso (la misura non tocca gli esiti)."""
    caplog.set_level(logging.INFO, logger="Betfair.stream.tempi_ordine")
    spento = _clic(monkeypatch, worker_paper, caplog, market_id="1.404")
    _accendi_monitor(monkeypatch)
    acceso = _clic(monkeypatch, worker_paper, caplog, market_id="1.404")
    assert spento["risposte"][0][1] is False and spento["piazzati"] == []
    assert [r[1:] for r in acceso["risposte"]] == [r[1:] for r in spento["risposte"]]
    (c,) = acceso["righe"]
    assert c["esito"] == "errore" and _num(c, "decisione_ms") is not None


def test_tempi_invio_zero_e_assente():
    """``tempi_ordine._ms_da``: 0 (e negativi) = istante assente."""
    from Betfair.stream import tempi_ordine as T

    assert T._ms_da(0) is None and T._ms_da(-5) is None
    T._azzera_per_test()
    T.nuovo("k0", "canale", invio=0, decisione_ms=1_760_000_000_000)
    v = T._voci["k0"]
    assert v["invio_ms"] is None
    assert T.tratti(v, None)["decisione_ms"] is None and T.tratti(v, None)["ricezione_ms"] is None
    T._azzera_per_test()
