"""30/09 - LA POSIZIONE DI CONTO DALLO STREAM ORDINI, lato RUNNER.

Fatto del 30/09 (live, 36130526): l'utente chiude dal sito Betfair alle 15:30:45
circa, Mike se ne accorge alle 15:32:13 (REST ogni ``reconcile_every_s``). Il
runner LIVE riceve lo STREAM ORDINI di tutto il conto (flumine: nessun filtro
``customerStrategyRefs``), ma flumine scarta gli ordini che non sono di una sua
strategia. Da oggi il runner li pubblica sul canale (topic ``conto``).

Tutto con oggetti VERI:
  * la cache VERA dello stream ordini di ``betfairlightweight``
    (``OrderBookCache.update_cache`` con un messaggio ``oc`` nella grafia di
    Betfair, ``create_resource`` -> ``CurrentOrders`` di ``CurrentOrder``);
  * il ``Flumine`` VERO con un ``BetfairClient`` VERO (nessun login: il costruttore
    non tocca la rete), il suo ``_process_current_orders`` e il suo
    ``CurrentOrdersEvent``;
  * ``LiveTradingStrategy`` VERA (``start`` come la chiama flumine);
  * ``LocalChannel`` VERO su una porta libera e client ``websockets`` veri.

Ogni test e' stato FALSIFICATO (referto
``AUDIT_2026-09-30/MIKE_CHIUSURA_UTENTE_TEMPO_REALE.md``). ASCII-only.
"""
from __future__ import annotations

import json
import socket
import time
from typing import Any, Dict, List

import pytest

from Betfair.omega import omega_market as OM
from Betfair.stream import esiti_ordini_canale as EO
from Betfair.stream import local_channel as LC
from Betfair.stream.engine import live_trading_strategy as LTS

MERCATO = "1.35"
SEL = 47999
PT = 1_700_000_100_000


def _uo(bet_id: str, *, side: str, sm: float, rfo: Any, rfs: Any, stato: str = "EC",
        p: float = 1.5, pd: int = PT - 60_000) -> Dict[str, Any]:
    """Un ordine nella grafia dello STREAM di Betfair (``uo``)."""
    return {"id": bet_id, "p": p, "s": sm, "side": side, "status": stato, "pt": "L",
            "ot": "L", "pd": pd, "md": pd + 500, "avp": p, "sm": sm,
            "sr": 0.0 if stato == "EC" else 1.0, "sl": 0.0, "sc": 0.0, "sv": 0.0,
            "rfo": rfo, "rfs": rfs}


def _ordini_dello_stream(uo: List[Dict[str, Any]], *, market_id: str = MERCATO) -> Any:
    """La cache VERA dello stream ordini -> ``CurrentOrders`` VERO."""
    from betfairlightweight.streaming.cache import OrderBookCache

    cache = OrderBookCache(market_id, PT, False)
    cache.update_cache({"id": market_id, "orc": [{"id": SEL, "uo": uo}]}, PT)
    return cache.create_resource(0)


def _client(paper: bool) -> Any:
    from betfairlightweight import APIClient
    from flumine import clients

    return clients.BetfairClient(APIClient("u", "p", app_key="k"), paper_trade=paper,
                                 order_stream=True)


def _framework(client: Any) -> Any:
    from flumine import Flumine

    return Flumine(client=client)


def _evento(*ordini_mercato: Any) -> Any:
    from flumine.events.events import CurrentOrdersEvent

    return CurrentOrdersEvent(list(ordini_mercato))


def _chiusura_dal_sito() -> List[Dict[str, Any]]:
    """Il back di Mike (ref ``mike-t1``, strategia ``mike``) e la lay con cui
    l'utente chiude dal sito (nessun ref)."""
    return [_uo("B1", side="B", sm=10.0, rfo="mike-t1", rfs="mike"),
            _uo("U1", side="L", sm=10.0, rfo=None, rfs=None, p=1.45, pd=PT)]


def _porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _aspetta(cond, secondi: float = 5.0) -> bool:
    fine = time.time() + secondi
    while time.time() < fine:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


# ===========================================================================
# 1. FLUMINE SCARTA GLI ORDINI NON SUOI: la prova del perche'
# ===========================================================================
def test_flumine_scarta_lordine_dal_sito_e_nessuna_strategia_lo_vede():
    """La lay dell'utente (nessun ``customerOrderRef``) e il back di Mike (ref
    non di una strategia flumine) arrivano nell'evento dello stream, ma dopo
    ``process_current_orders`` il blotter non ne contiene nessuno."""
    client = _client(paper=False)
    fw = _framework(client)
    co = _ordini_dello_stream(_chiusura_dal_sito())
    co.client = client
    assert {o.bet_id for o in co.orders} == {"B1", "U1"}, "lo stream porta tutto il conto"
    fw._process_current_orders(_evento(co))
    assert fw.markets.markets == {} or all(
        not m.blotter._orders for m in fw.markets.markets.values()), \
        "flumine non crea ordini per chi non e' una sua strategia"


# ===========================================================================
# 2. IL RUNNER LIVE PUBBLICA IL CONTO; IL PAPER NO
# ===========================================================================
def _monta(monkeypatch, mode: str, paper_client: bool):
    pubblicati: List[tuple] = []
    monkeypatch.setattr(LC, "publish", lambda t, d: pubblicati.append((t, d)))
    client = _client(paper=paper_client)
    fw = _framework(client)
    strat = LTS.LiveTradingStrategy(market_filter={}, mode=mode,
                                    name="LTS-%s-%d" % (mode, id(fw)))
    strat.start(fw)
    return fw, client, pubblicati


def test_la_strategia_LIVE_pubblica_gli_ordini_del_conto(monkeypatch):
    fw, client, pubblicati = _monta(monkeypatch, "live", paper_client=False)
    co = _ordini_dello_stream(_chiusura_dal_sito())
    co.client = client
    fw._process_current_orders(_evento(co))
    assert len(pubblicati) == 1
    topic, p = pubblicati[0]
    assert topic == EO.TOPIC_CONTO == "conto"
    assert p["market_id"] == MERCATO and p["fonte"] == "stream_ordini"
    assert p["publish_time_ms"] == PT and isinstance(p["ricevuto_ms"], int)
    per_id = {o["betId"]: o for o in p["ordini"]}
    assert set(per_id) == {"B1", "U1"}, "anche l'ordine SENZA ref (dal sito) viaggia"
    assert per_id["U1"]["customerOrderRef"] is None and per_id["U1"]["side"] == "LAY"
    assert per_id["B1"]["customerOrderRef"] == "mike-t1"
    json.dumps({"t": topic, "d": p})      # viaggia sul canale senza ``default=str``


def test_la_riga_del_canale_normalizzata_e_quella_della_REST(monkeypatch):
    """Il contratto che tiene UNA sola aritmetica: la riga del canale, passata
    per ``omega_market._riga_corrente`` (la normalizzazione della REST), ha le
    STESSE chiavi, gli stessi tipi e gli stessi valori della riga che la REST
    produce per lo stesso ordine (``listCurrentOrders``, camelCase)."""
    fw, client, pubblicati = _monta(monkeypatch, "live", paper_client=False)
    co = _ordini_dello_stream(_chiusura_dal_sito())
    co.client = client
    fw._process_current_orders(_evento(co))
    dal_canale = {r["bet_id"]: r for r in
                  (OM._riga_corrente(o) for o in pubblicati[0][1]["ordini"])}
    # la stessa lay come la scrive listCurrentOrders (JSON di Betfair)
    rest = OM._riga_corrente({
        "betId": "U1", "marketId": MERCATO, "selectionId": SEL, "side": "LAY",
        "status": "EXECUTION_COMPLETE", "sizeMatched": 10.0, "averagePriceMatched": 1.45,
        "sizeRemaining": 0.0, "sizeCancelled": 0.0, "sizeLapsed": 0.0, "sizeVoided": 0.0,
        "placedDate": "2023-11-14T22:15:00.000Z", "matchedDate": "2023-11-14T22:15:00.500Z",
        "priceSize": {"price": 1.45, "size": 10.0}})
    canale = dal_canale["U1"]
    assert set(canale) == set(rest)
    for k in rest:
        if k in ("placed_date", "matched_date"):
            continue    # stesso istante, grafia ISO diversa (millisecondi)
        assert canale[k] == rest[k] and type(canale[k]) is type(rest[k]), k


def test_gli_eventi_del_client_PAPER_affiancato_non_si_pubblicano(monkeypatch):
    """Nel runner LIVE c'e' anche il client PAPER affiancato: i suoi eventi
    (``SimulatedOrderStream``) non sono il conto e non si pubblicano."""
    fw, _client_vero, pubblicati = _monta(monkeypatch, "live", paper_client=False)
    finto = _client(paper=True)
    co = _ordini_dello_stream(_chiusura_dal_sito())
    co.client = finto
    fw._process_current_orders(_evento(co))
    assert pubblicati == []


def test_la_strategia_PAPER_non_monta_niente(monkeypatch):
    fw, client, pubblicati = _monta(monkeypatch, "paper", paper_client=True)
    assert not getattr(fw, "_conto_osservato", False)
    co = _ordini_dello_stream(_chiusura_dal_sito())
    co.client = _client(paper=False)
    fw._process_current_orders(_evento(co))
    assert pubblicati == [], "il runner PAPER non ha un conto da pubblicare"


def test_il_montaggio_e_idempotente_e_non_cambia_flumine(monkeypatch):
    fw, client, pubblicati = _monta(monkeypatch, "live", paper_client=False)
    assert EO.osserva_conto_su_flumine(fw, LC.publish) is False, "gia' montato"
    chiamate: List[Any] = []
    fw2 = _framework(client)
    originale = fw2._process_current_orders
    fw2._process_current_orders = lambda ev: (chiamate.append(ev), originale(ev))
    assert EO.osserva_conto_su_flumine(fw2, lambda t, d: None) is True
    ev = _evento()
    fw2._process_current_orders(ev)
    assert chiamate == [ev], "flumine riceve lo STESSO evento, una volta"


def test_una_pubblicazione_che_esplode_non_ferma_flumine():
    client = _client(paper=False)
    fw = _framework(client)

    def esplode(_t, _d):
        raise RuntimeError("canale rotto")

    assert EO.osserva_conto_su_flumine(fw, esplode)
    co = _ordini_dello_stream(_chiusura_dal_sito())
    co.client = client
    fw._process_current_orders(_evento(co))      # nessuna eccezione


def test_il_framework_simulato_non_si_monta():
    from types import SimpleNamespace

    fw = SimpleNamespace(SIMULATED=True, _process_current_orders=lambda ev: None)
    assert EO.osserva_conto_su_flumine(fw, lambda t, d: None) is False


# ===========================================================================
# 3. IL CANALE: il lettore del conto riceve il conto, Omega e Safe no
# ===========================================================================
def test_canale_vero_il_conto_arriva_al_lettore_del_conto_e_non_a_quello_degli_esiti():
    from websockets.sync.client import connect

    porta = _porta_libera()
    ch = LC.LocalChannel(porta, "calcio")
    assert ch.start()
    memoria = EO.MemoriaConto()
    client_conto = EO.ClientEsiti(memoria, topic=EO.TOPIC_CONTO, porta_ws=porta)
    assert client_conto.url.endswith("/lettore/conto")
    client_conto.avvia()
    try:
        with connect("ws://127.0.0.1:%d%s" % (porta, EO.PERCORSO), open_timeout=5) as esiti:
            assert json.loads(esiti.recv(timeout=5))["t"] == "hello"
            assert _aspetta(lambda: ch._n_clients == 2 and client_conto.collegato)
            assert ch.is_active() is False, "due lettori non sono un desktop"
            fw = _framework(_client(paper=False))
            assert EO.osserva_conto_su_flumine(fw, ch.publish)
            co = _ordini_dello_stream(_chiusura_dal_sito())
            co.client = _client(paper=False)
            t0 = time.time()
            fw._process_current_orders(_evento(co))
            assert _aspetta(lambda: memoria.mercato(MERCATO) is not None, 5.0)
            ritardo_ms = (time.time() - t0) * 1000.0
            f = memoria.mercato(MERCATO)
            assert {o["betId"] for o in f["ordini"]} == {"B1", "U1"}
            assert ritardo_ms < 1000.0, ritardo_ms
            ch.publish("order", {"client_order_ref": "awlq1"})
            msg = json.loads(esiti.recv(timeout=5))
            assert msg["t"] == "order", "il lettore degli esiti NON riceve il conto"
    finally:
        client_conto.ferma()


# ===========================================================================
# 4. LA MEMORIA DEL CONTO
# ===========================================================================
def test_memoria_conto_versione_e_fotografia_piu_vecchia():
    m = EO.MemoriaConto(orologio=lambda: 5.0)
    assert m.ricevi({"market_id": "1.1", "ordini": [], "publish_time_ms": 10}) is True
    v1 = m.mercato("1.1")["versione"]
    assert m.ricevi({"market_id": "1.1", "ordini": [], "publish_time_ms": 9}) is False
    assert m.ricevi({"market_id": "1.1", "ordini": [{"betId": "X"}],
                     "publish_time_ms": 11}) is True
    f = m.mercato("1.1")
    assert f["versione"] > v1 and f["ordini"] == [{"betId": "X"}] and f["arrivato_s"] == 5.0
    assert m.ricevi("rotto") is False and m.ricevi({"ordini": []}) is False
    assert m.azzera() is True and m.mercato("1.1") is None


def test_il_client_esiti_di_serie_resta_sul_topic_order():
    """Omega e Safe costruiscono ``ClientEsiti`` senza ``topic``: stesso URL e
    stesso filtro di prima."""
    c = EO.ClientEsiti(EO.MemoriaEsiti(), porta_ws=47331)
    assert c.url == "ws://127.0.0.1:47331/lettore/order"
    assert c.incassa(json.dumps({"t": "conto", "d": {"market_id": "1.1", "ordini": []}})) is False


# ===========================================================================
# 30/09 sera (backend per la UI): ``pnl_letto_at`` sul topic ``conto``
# ===========================================================================
def test_payload_conto_porta_pnl_letto_at_iso_utc_uguale_a_ricevuto_ms():
    """Il payload VERO (CurrentOrders della cache dello stream) porta
    ``pnl_letto_at``: ISO-8601 UTC al millisecondo con la ``Z``, lo STESSO
    istante di ``ricevuto_ms`` (la lettura), non il publishTime di Betfair."""
    from datetime import datetime, timezone
    import re

    co = _ordini_dello_stream(_chiusura_dal_sito())
    ric = 1_759_255_768_231            # 2025-09-30T18:09:28.231Z
    p = EO.payload_conto(co, ricevuto_ms=ric)
    assert p["pnl_letto_at"] == "2025-09-30T18:09:28.231Z"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", p["pnl_letto_at"])
    letto = datetime.fromisoformat(p["pnl_letto_at"].replace("Z", "+00:00"))
    assert letto.tzinfo is not None and letto.utcoffset() == timezone.utc.utcoffset(None)
    assert int(letto.timestamp() * 1000) == p["ricevuto_ms"] == ric
    assert p["publish_time_ms"] == PT       # il tempo di Betfair resta a parte
    # le chiavi di prima ci sono tutte (chiave ADDITIVA)
    assert {"market_id", "ordini", "fonte", "ricevuto_ms", "publish_time_ms",
            "snap"} <= set(p)
    json.dumps(p)


def test_la_memoria_conto_accetta_il_payload_con_pnl_letto_at():
    """Il consumatore esistente (``MemoriaConto``, usato da Mike) non cambia."""
    m = EO.MemoriaConto()
    p = EO.payload_conto(_ordini_dello_stream(_chiusura_dal_sito()), ricevuto_ms=PT + 5)
    assert m.ricevi(p) is True
    assert m.mercato(MERCATO)["ricevuto_ms"] == PT + 5


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
