"""W1-A2 - ``flusso.GestoreFlussi`` sulla connessione VERA (server finto TLS, ``test_a2_finti``).

Dalla parte nostra tutto e' libreria vera: ``APIClient.streaming.create_stream``,
``BetfairStream`` (socket, CRLF, autenticazione, ``marketSubscription``),
``StreamListener`` -> ``MarketBookCache`` -> ``MarketBook``. Il server risponde
con ``marketDefinition`` e prezzi presi dalla registrazione vera 35760084.

Provati: suddivisione 180 per connessione e mai oltre 200; sottoscrizione che
SOSTITUISCE (si rimanda l'insieme intero, solo sulla connessione che cambia);
filtri per profilo (calcio, scanner, scalper); ripresa con ``initialClk``/``clk``;
riserva e ``connectionsAvailable``; rifiuto di Betfair e pausa; salute per
mercato (vivo/muto/assente, 503); manutenzione delle connessioni mute;
consumatori; ``ferma``.
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Dict, List

import pytest

from Betfair.nucleo.betfair import flusso as F
from Betfair.nucleo.betfair import profili as P
from Betfair.nucleo.betfair.contratto import FlussoMercato

from .test_a2_finti import CHIUDI, SessioneFinta, attendi, conforme, prima_immagine, server_stream  # noqa: F401

PT0 = 1782831952415


def _modello() -> Dict[str, Any]:
    """Un mercato vero della registrazione (MATCH_ODDS: definizione e prezzi)."""
    for m in prima_immagine("35760084")["mc"]:
        if m["marketDefinition"]["marketType"] == "MATCH_ODDS":
            return m
    raise AssertionError("MATCH_ODDS assente")


MODELLO = _modello()
SEL = MODELLO["marketDefinition"]["runners"][0]["id"]


def _prezzi_back(libro: Any, sel: int) -> List[float]:
    if libro is None:
        return []
    for r in libro.runners:
        if r.selection_id == sel:
            return [lv["price"] for lv in r.ex.available_to_back]
    return []


def immagine(ids: List[str], k: int, *, salta: frozenset = frozenset()) -> Dict[str, Any]:
    mc = []
    for mid in ids:
        if mid in salta:
            continue
        m = copy.deepcopy(MODELLO)
        m["id"] = mid
        mc.append(m)
    return {"op": "mcm", "initialClk": "INI-%d" % k, "clk": "CLK-%d" % k, "pt": PT0 + k,
            "heartbeatMs": 5000, "conflateMs": 0, "ct": "SUB_IMAGE", "mc": mc}


def _ids(a: int, b: int) -> List[str]:
    return ["1.%06d" % i for i in range(a, b)]


def _risposta_immagine(n: int, m: Dict[str, Any], k: int) -> List[Any]:
    return [immagine(m["marketFilter"]["marketIds"], k)]


@pytest.fixture
def backoff_breve(monkeypatch):
    monkeypatch.setattr(F, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(F, "BACKOFF_MAX_S", 0.2)


#: cambio FISSO dei test (come il banco: ``valuta.cambio_banco``), mai la cache su disco
CAMBIO = 1.2


def _gestore(nome: str = "runner_calcio", ambiente: Dict[str, str] = None, **kw: Any) -> F.GestoreFlussi:
    from Betfair.stream.valuta import CambioGbpEur

    kw.setdefault("cambio", CambioGbpEur(fisso=CAMBIO))
    return F.GestoreFlussi(SessioneFinta(), P.profilo(nome, ambiente or {}), **kw)


def test_conforme_al_contratto():
    assert conforme(F.GestoreFlussi, FlussoMercato) == []


def test_sottoscrizione_vuota_rifiutata():
    with pytest.raises(ValueError):
        _gestore().imposta_mercati([])


def test_suddivisione_180_e_risottoscrizione_solo_della_connessione_che_cambia(server_stream):
    srv = server_stream(_risposta_immagine)
    g = _gestore()
    try:
        fuori = g.imposta_mercati(_ids(0, 400))
        assert fuori == set()
        assert attendi(lambda: len(srv.sottoscrizioni) == 3)
        assert attendi(lambda: g.stato()["conti"]["book"] >= 400)
        per_conn = {n: m for n, m in srv.sottoscrizioni}
        assert sorted(len(m["marketFilter"]["marketIds"]) for m in per_conn.values()) == [40, 180, 180]
        tutti = sorted(x for m in per_conn.values() for x in m["marketFilter"]["marketIds"])
        assert tutti == _ids(0, 400)                     # nessun doppione, nessuno perso
        for m in per_conn.values():
            assert m["marketFilter"]["marketIds"] == sorted(m["marketFilter"]["marketIds"])
            assert m["marketDataFilter"] == {"fields": list(P.CAMPI_CALCIO), "ladderLevels": 10}
            assert (m["conflateMs"], m["heartbeatMs"], m["segmentationEnabled"]) == (None, None, True)
            assert (m["initialClk"], m["clk"]) == (None, None)
        b = g.book("1.000123")
        assert type(b).__name__ == "MarketBook" and b.market_id == "1.000123"
        # la seconda connessione perde un mercato e ne prende uno nuovo: SOLO lei
        # risottoscrive, con l'insieme INTERO (sostitutiva), da immagine piena
        seconda = sorted(g._vive()[1].mercati)
        via, nuovo = seconda[7], "1.000777"
        voluti = (set(_ids(0, 400)) - {via}) | {nuovo}
        assert g.imposta_mercati(voluti) == set()
        assert attendi(lambda: len(srv.sottoscrizioni) == 4)
        n4, m4 = srv.sottoscrizioni[3]
        assert n4 == [n for n, m in srv.sottoscrizioni[:3] if seconda[0] in m["marketFilter"]["marketIds"]][0]
        assert m4["marketFilter"]["marketIds"] == sorted((set(seconda) - {via}) | {nuovo})
        assert (m4["initialClk"], m4["clk"]) == (None, None)
        assert srv.connessioni == 3                      # nessuna connessione in piu'
        assert attendi(lambda: g.stato_flusso(nuovo) == "vivo")
        assert g.stato_flusso(via) == "assente"
    finally:
        g.ferma()


def test_mai_oltre_200_per_sottoscrizione_anche_se_il_profilo_lo_chiede(server_stream):
    srv = server_stream(_risposta_immagine)
    g = _gestore("scansione", {"SAFE_STRATEGY_STREAM_MARKETS_PER_CONN": "900"})
    assert g.profilo.mercati_per_connessione == 900 and g.per_conn == 200
    try:
        assert g.imposta_mercati(_ids(0, 450)) == set()
        assert attendi(lambda: len(srv.sottoscrizioni) == 3)
        m = srv.sottoscrizioni[0][1]
        assert max(len(x["marketFilter"]["marketIds"]) for _n, x in srv.sottoscrizioni) == 200
        assert m["marketDataFilter"] == {"fields": ["EX_BEST_OFFERS", "EX_MARKET_DEF"], "ladderLevels": 1}
        assert (m["conflateMs"], m["heartbeatMs"]) == (1000, 5000)
    finally:
        g.ferma()


def test_filtro_dello_scalper_e_quello_di_serie_di_flumine(server_stream):
    from flumine.strategy.strategy import DEFAULT_MARKET_DATA_FILTER

    srv = server_stream(_risposta_immagine)
    g = _gestore("scalper_partita")
    try:
        g.imposta_mercati(_ids(0, 12))
        assert attendi(lambda: len(srv.sottoscrizioni) == 1)
        assert srv.sottoscrizioni[0][1]["marketDataFilter"] == DEFAULT_MARKET_DATA_FILTER
    finally:
        g.ferma()


def test_ripresa_con_initial_clk_e_clk_dopo_la_caduta(server_stream, backoff_breve):
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        ids = m["marketFilter"]["marketIds"]
        if k == 1:
            return [immagine(ids, 1), {"op": "mcm", "clk": "CLK-1b", "pt": PT0 + 5,
                                       "ct": "HEARTBEAT"}, CHIUDI]
        return [{"op": "mcm", "clk": "CLK-2", "pt": PT0 + 50, "ct": "RESUB_DELTA",
                 "mc": [{"id": ids[0], "rc": [{"atb": [[1.27, 10.0]], "id": SEL}]}]}]
    srv = server_stream(risposta)
    g = _gestore("runner_tennis")
    try:
        g.imposta_mercati(_ids(0, 5))
        assert attendi(lambda: len(srv.sottoscrizioni) == 2)
        prima, seconda = srv.sottoscrizioni[0][1], srv.sottoscrizioni[1][1]
        assert (seconda["initialClk"], seconda["clk"]) == ("INI-1", "CLK-1b")
        assert seconda["marketFilter"] == prima["marketFilter"]
        assert seconda["marketDataFilter"] == prima["marketDataFilter"]
        assert attendi(lambda: 1.27 in _prezzi_back(g.book(_ids(0, 1)[0]), SEL))
        assert g.stato()["conti"]["riprese_con_clk"] == 1
        assert g.stato()["frammenti"][0]["riconnessioni"] == 1
    finally:
        g.ferma()


def test_cambio_di_mercati_a_connessione_giu_riparte_da_immagine(server_stream, monkeypatch):
    """I criteri della ripresa devono essere IDENTICI: se i mercati cambiano
    mentre la connessione e' giu', la riconnessione non usa il clk (immagine piena)."""
    monkeypatch.setattr(F, "BACKOFF_MIN_S", 1.0)
    monkeypatch.setattr(F, "BACKOFF_MAX_S", 1.0)

    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        if k == 1:
            return [immagine(m["marketFilter"]["marketIds"], 1), CHIUDI]
        return [immagine(m["marketFilter"]["marketIds"], k)]
    srv = server_stream(risposta)
    g = _gestore("runner_tennis")
    try:
        g.imposta_mercati(_ids(0, 5))
        c = g._vive()[0]
        assert attendi(lambda: c.riconnessioni >= 1 and not c.connessa())
        assert g.imposta_mercati(_ids(0, 6)) == set()       # a connessione giu'
        assert attendi(lambda: len(srv.sottoscrizioni) == 2)
        seconda = srv.sottoscrizioni[1][1]
        assert seconda["marketFilter"]["marketIds"] == _ids(0, 6)
        assert (seconda["initialClk"], seconda["clk"]) == (None, None)
    finally:
        g.ferma()


def test_riserva_e_connections_available(server_stream):
    srv = server_stream(_risposta_immagine, autentica=lambda n: {
        "op": "status", "statusCode": "SUCCESS", "connectionClosed": False,
        "connectionsAvailable": 1})
    g = _gestore()                                        # calcio: max 3, riserva 1
    try:
        assert g.imposta_mercati(_ids(0, 100)) == set()
        assert attendi(lambda: g._disponibili() == 1)
        fuori = g.imposta_mercati(_ids(0, 300))
        assert fuori == set(_ids(180, 300))
        assert srv.connessioni == 1
        st = g.stato()
        assert st["connessioni_concesse_adesso"] == 1
        assert st["motivo_limite"] == ("Betfair dichiara 1 connessioni libere, riserva 1 per "
                                       "scanner/scalper/tennis")
    finally:
        g.ferma()


def test_rifiuto_di_betfair_chiude_mette_in_pausa_e_non_ritenta(server_stream, backoff_breve):
    def autentica(n: int) -> Dict[str, Any]:
        if n == 2:
            return {"op": "status", "statusCode": "FAILURE",
                    "errorCode": "MAX_CONNECTION_LIMIT_EXCEEDED",
                    "errorMessage": "You have exceeded your max connection limit which is: "
                                    "10 connection(s).", "connectionClosed": True}
        return {"op": "status", "statusCode": "SUCCESS", "connectionClosed": False,
                "connectionsAvailable": 5}
    srv = server_stream(_risposta_immagine, autentica)
    g = _gestore()
    try:
        g.imposta_mercati(_ids(0, 180))
        assert attendi(lambda: g._disponibili() == 5)
        g.imposta_mercati(_ids(0, 300))
        assert attendi(lambda: any(c.rifiutata for c in g._vive()))
        persi = g.manutenzione()
        assert persi == set(_ids(180, 300))
        st = g.stato()
        assert st["in_pausa_dopo_rifiuto"] and st["ultimo_rifiuto"] == "MAX_CONNECTION_LIMIT_EXCEEDED"
        assert g.imposta_mercati(_ids(0, 300)) == set(_ids(180, 300))
        assert not attendi(lambda: srv.connessioni > 2, secondi=0.5)
    finally:
        g.ferma()


class _Orologio:
    def __init__(self) -> None:
        self.t = 50_000.0

    def __call__(self) -> float:
        return self.t


def test_salute_vivo_muto_assente_e_503(server_stream):
    orologio = _Orologio()
    manca = "1.000003"
    srv = server_stream(lambda n, m, k: [immagine(m["marketFilter"]["marketIds"], k,
                                                  salta=frozenset({manca}))])
    g = _gestore("runner_tennis", orologio=orologio)
    try:
        g.imposta_mercati(_ids(0, 5))
        assert attendi(lambda: g.stato_flusso("1.000000") == "vivo")
        assert g.stato_flusso(manca) == "muto"             # sottoscritto, nessun book
        assert g.stato_flusso("1.999999") == "assente"
        orologio.t += 15.1                                  # > 3 heartbeat da 5000 ms
        assert g.stato_flusso("1.000000") == "muto"
        assert g.stato()["frammenti"][0]["motivo"] == "flusso_interrotto"
        srv.manda(1, {"op": "mcm", "clk": "CLK-9", "pt": PT0 + 99, "ct": "HEARTBEAT", "status": 503})
        assert attendi(lambda: g.stato()["frammenti"][0]["motivo"] == "stream_latente")
        assert g.stato_flusso("1.000000") == "muto"
    finally:
        g.ferma()


def test_manutenzione_chiude_la_connessione_muta_e_ripiazza(server_stream):
    orologio = _Orologio()
    srv = server_stream(_risposta_immagine)
    g = _gestore(orologio=orologio)
    try:
        g.imposta_mercati(_ids(0, 300))
        assert attendi(lambda: len(srv.sottoscrizioni) == 2)
        assert attendi(lambda: all(c.listener.autenticato_una_volta for c in g._vive()))
        assert attendi(lambda: all(len(c.listener.serviti) == len(c.mercati) for c in g._vive()))
        orologio.t += 200.0
        # il battito arriva solo alla connessione (lato server) della PRIMA del gestore
        prima = min(g._vive()[0].mercati)
        n_srv = [n for n, m in srv.sottoscrizioni if prima in m["marketFilter"]["marketIds"]][0]
        srv.manda(n_srv, {"op": "mcm", "clk": "CLK-7", "pt": PT0 + 7, "ct": "HEARTBEAT"})
        assert attendi(lambda: g._vive()[0].listener.ultimo_msg_mono == orologio.t)
        muti = [c for c in g._vive() if orologio.t - c.listener.ultimo_msg_mono > F.MUTO_S]
        assert len(muti) == 1
        persi = g.manutenzione()
        assert persi == set(muti[0].mercati) and g.stato()["conti"]["muti"] == 1
        assert g.imposta_mercati(_ids(0, 300)) == set()     # ripiazzati su una connessione nuova
        assert attendi(lambda: srv.connessioni == 3)
    finally:
        g.ferma()


def test_consumatori_filtro_trasformazione_ed_errori(server_stream):
    server_stream(_risposta_immagine)
    trasformati: List[str] = []

    def trasforma(b: Any) -> Any:
        trasformati.append(b.market_id)
        b.valuta = "EUR"
        return b
    g = _gestore("runner_tennis", trasforma=trasforma)
    tutti: List[str] = []
    solo: List[str] = []

    def rotto(b: Any) -> None:
        raise RuntimeError("consumatore rotto")
    g.aggiungi_consumatore(rotto)
    g.aggiungi_consumatore(lambda b: tutti.append(b.market_id))
    g.aggiungi_consumatore(lambda b: solo.append(b.market_id), mercati={"1.000002"})
    try:
        g.imposta_mercati(_ids(0, 4))
        assert attendi(lambda: sorted(tutti) == _ids(0, 4))
        assert solo == ["1.000002"]
        assert g.book("1.000001").valuta == "EUR" and sorted(trasformati) == _ids(0, 4)
        assert g.stato()["conti"]["errori_consumatori"] == 4
    finally:
        g.ferma()


def test_size_dello_stream_convertite_gbp_eur_alla_fonte(server_stream):
    """K1: lo stream dei mercati e' in GBP; ogni book consegnato e' gia' in EUR
    (``valuta.converti_libro``, marcato ``valuta='EUR'``), come oggi lo scanner e i
    middleware di flumine. Senza conversione la liquidita' sarebbe sottostimata del ~14%."""
    from Betfair.stream.recorder import serialize_book

    server_stream(_risposta_immagine)
    g = _gestore("runner_tennis")
    try:
        g.imposta_mercati(_ids(0, 1))
        assert attendi(lambda: g.book("1.000000") is not None)
        b = g.book("1.000000")
        assert b.valuta == "EUR" and b.size_gbp_convertite is True
        gbp = {r["id"]: r for r in MODELLO["rc"]}
        s = serialize_book(b, 10)
        assert s["valuta"] == "EUR"
        for sel, r in s["runners"].items():
            originale = gbp.get(int(sel), {}).get("atb") or []
            if originale and r["b"]:
                migliore = max(originale, key=lambda lv: lv[0])
                assert r["b"][0] == [migliore[0], round(migliore[1] * CAMBIO, 2)]
                break
        else:
            raise AssertionError("nessun livello back da confrontare")
    finally:
        g.ferma()


def test_ferma_chiude_tutto_e_non_riconnette(server_stream, backoff_breve):
    srv = server_stream(_risposta_immagine)
    g = _gestore()
    g.imposta_mercati(_ids(0, 200))
    assert attendi(lambda: len(srv.sottoscrizioni) == 2)
    g.ferma()
    n = srv.connessioni
    assert not attendi(lambda: srv.connessioni > n, secondi=0.5)
    assert not [t for t in threading.enumerate() if t.name.startswith("flusso-") and t.is_alive()]
    assert g.stato()["connessioni_di_mercato"] == 0
