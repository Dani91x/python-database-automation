"""W1-A2 - stream degli ordini del CONTO (``flusso_ordini_conto.py``).

Due livelli, entrambi sulla catena VERA di betfairlightweight:
1. messaggi ``ocm`` nel formato ufficiale passati a ``ListenerConto.on_data``
   (``StreamListener`` -> ``OrderStream`` -> ``OrderBookCache``/``UnmatchedOrder``
   -> conversione): tutte le chiavi, parziali, annullati, scaduti, annullati da
   Betfair, piu' strategie e ordini senza riferimento (sito), segmenti, immagine
   piena dopo una caduta;
2. la connessione intera su un server finto TLS (``test_a2_finti``): autenticazione,
   ``orderSubscription`` senza filtro di strategia, caduta e ripresa con
   ``initialClk``/``clk``, ``INVALID_CLOCK``, sessione scaduta, 503, muto, ``ferma``.

Formato ``ocm`` dalla documentazione Betfair (Exchange Stream API, OrderChangeMessage):
``{"op":"ocm","id":..,"initialClk":..,"clk":..,"pt":..,"ct":"SUB_IMAGE","oc":[{"id":
market,"fullImage":true,"orc":[{"id":selection,"hc":0,"fullImage":true,"uo":[{"id":
bet,"p":..,"s":..,"side":"B"|"L","status":"E"|"EC","pt":"L"|"P"|"MOC","ot":"L"|"MOC"|"LOC",
"pd":ms,"md":ms,"sm":..,"sr":..,"sl":..,"sc":..,"sv":..,"avp":..,"rac":"","rc":"REG_GGC",
"rfo":"","rfs":""}],"mb":[[p,s]],"ml":[[p,s]]}]}]}``.
"""
from __future__ import annotations

import inspect
import json
import subprocess
import sys
import threading
from typing import Any, Dict, List

import pytest

from Betfair.nucleo.betfair import flusso_ordini_conto as FOC
from Betfair.nucleo.betfair.contratto import FlussoOrdiniConto, OrdineDalConto

from .test_a2_finti import CHIUDI, SessioneFinta, attendi, conforme, server_stream  # noqa: F401

MID = "1.259475523"
MID2 = "1.259475600"
PT0 = 1782831952415


def uo(bet: str, **kw: Any) -> Dict[str, Any]:
    """Un ordine ``uo`` con TUTTE le chiavi dello stream (valori sovrascrivibili)."""
    base = {"id": bet, "p": 2.5, "s": 10.0, "side": "B", "status": "E", "pt": "L", "ot": "L",
            "pd": PT0 - 5000, "sm": 0.0, "sr": 10.0, "sl": 0.0, "sc": 0.0, "sv": 0.0,
            "rac": "", "rc": "REG_GGC", "rfo": "", "rfs": ""}
    base.update(kw)
    return base


def ocm(oc: List[Dict[str, Any]], *, ct: str = None, clk: str = None, initial: str = None,
        pt: int = PT0, sid: int = 5, **extra: Any) -> str:
    d: Dict[str, Any] = {"op": "ocm", "id": sid, "pt": pt, "oc": oc}
    if ct:
        d["ct"] = ct
    if clk:
        d["clk"] = clk
    if initial:
        d["initialClk"] = initial
    d.update(extra)
    return json.dumps(d)


def mercato(mid: str, runners: List[Dict[str, Any]], full: bool = False, **extra: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {"id": mid, "orc": runners}
    if full:
        d["fullImage"] = True
    d.update(extra)
    return d


def runner(sel: int, ordini: List[Dict[str, Any]], full: bool = False, **extra: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {"id": sel, "hc": 0, "uo": ordini}
    if full:
        d["fullImage"] = True
    d.update(extra)
    return d


class Raccolta:
    def __init__(self) -> None:
        self.lotti: List[List[OrdineDalConto]] = []
        self.info: List[Dict[str, Any]] = []

    def __call__(self, ordini: List[OrdineDalConto], info: Dict[str, Any]) -> None:
        self.lotti.append(list(ordini))
        self.info.append(info)

    @property
    def ultimi(self) -> Dict[str, OrdineDalConto]:
        out: Dict[str, OrdineDalConto] = {}
        for lotto in self.lotti:
            for o in lotto:
                out[o.bet_id] = o
        return out


def listener_vero(ora_ms: float = 1.0e12):
    r = Raccolta()
    li = FOC.ListenerConto(r, lambda: ora_ms)
    li.register_stream(5, "orderSubscription")     # come fa subscribe_to_orders
    return li, r


# ---------------------------------------------------------------------------
# 1. catena della libreria, senza rete
# ---------------------------------------------------------------------------
def test_tutte_le_chiavi_ocm_arrivano_in_ordine_dal_conto():
    li, r = listener_vero(ora_ms=1782831952500.0)
    grezzo = uo("228302937743", p=1.83, s=12.5, side="L", status="E", pt="P", ot="L",
                pd=1782831947123, md=1782831950999, sm=2.5, sr=10.0, sl=0.0, sc=0.0, sv=0.0,
                avp=1.82, rfo="m-abc-001", rfs="mike_live", rc="REG_GGC")
    li.on_data(ocm([mercato(MID, [runner(2542448, [grezzo], full=True)], full=True)],
                   ct="SUB_IMAGE", clk="AAA", initial="III"))
    (o,) = r.lotti[0]
    assert o == OrdineDalConto(
        bet_id="228302937743", market_id=MID, selection_id=2542448, handicap=0.0, lato="lay",
        prezzo=1.83, importo=12.5, stato="EXECUTABLE", persistenza="PERSIST", tipo="LIMIT",
        piazzato_ms=1782831947123, abbinato_ms=1782831950999, abbinato=2.5, residuo=10.0,
        scaduto=0.0, annullato=0.0, annullato_da_betfair=0.0, prezzo_medio=1.82,
        customer_order_ref="m-abc-001", customer_strategy_ref="mike_live",
        regulator_code="REG_GGC", ricevuto_ms=1782831952500)
    assert (li.initial_clk, li.clk) == ("III", "AAA")


def test_ordine_del_sito_senza_riferimenti_e_avp_assente():
    li, r = listener_vero()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1", ot="MOC", pt="MOC")])])], ct="SUB_IMAGE"))
    (o,) = r.lotti[0]
    assert o.customer_order_ref is None and o.customer_strategy_ref is None
    assert o.prezzo_medio is None            # la libreria serializzando metterebbe 0.0
    assert o.abbinato_ms is None
    assert (o.tipo, o.persistenza, o.lato) == ("MARKET_ON_CLOSE", "MARKET_ON_CLOSE", "back")


def _senza(d: Dict[str, Any], *chiavi: str) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k not in chiavi}


def test_ordine_del_sito_SENZA_rfo_rfs_rc_non_fa_cadere_la_cache():
    """Reperto di W1-C2 (09/10): in betfairlightweight 2.23.2 ``UnmatchedOrder`` vuole
    ``rfo`` e ``rfs``; un ordine del sito (o di un'altra app) che non li porta
    mandava la cache in ``TypeError``. Formato ufficiale (schema ESA: nessuna chiave
    dell'Order e' obbligatoria), chiavi tolte, catena vera della libreria."""
    from betfairlightweight.streaming.cache import UnmatchedOrder

    obbligatori = {n for n, q in inspect.signature(UnmatchedOrder.__init__).parameters.items()
                   if q.default is q.empty}
    assert {"rfo", "rfs"} <= obbligatori                       # il difetto della libreria c'e'
    with pytest.raises(TypeError):
        UnmatchedOrder(PT0, **_senza(uo("x"), "rfo", "rfs", "rac", "rc"))
    li, r = listener_vero()
    li.on_data(ocm([mercato(MID, [runner(19, [_senza(uo("SITO1"), "rfo", "rfs", "rac", "rc"),
                                              uo("BOT1", rfs="mike_live", rfo="mk-1")])], full=True)],
                   ct="SUB_IMAGE", clk="1"))
    li.on_data(ocm([mercato(MID, [runner(19, [_senza(uo("SITO1", sm=4.0, sr=6.0, avp=2.5), "rfo", "rfs", "rac", "rc")])])],
                   clk="2", pt=PT0 + 10))
    u = r.ultimi
    assert set(u) == {"SITO1", "BOT1"}
    assert (u["SITO1"].customer_order_ref, u["SITO1"].customer_strategy_ref,
            u["SITO1"].regulator_code) == (None, None, None)
    assert (u["SITO1"].abbinato, u["SITO1"].prezzo_medio) == (4.0, 2.5)
    assert u["BOT1"].customer_strategy_ref == "mike_live"
    assert li.clk == "2" and not li.errore_elaborazione


def test_esempio_UFFICIALE_senza_rfo_rfs_parziale_poi_completo():
    """I tre messaggi ``ocm`` dell'esempio della documentazione ufficiale, VERBATIM
    (``AUDIT_2026-10-02/_fonti_betfair/bf_2687396.txt:1108-1114``): gli ordini NON
    portano ``rfo``/``rfs``. Con la libreria da sola il primo messaggio fa ``TypeError``."""
    righe = [
        '{"op":"ocm","id":2,"clk":"AK0CAPsBALEC","pt":1467219304831,"oc":[{"id":"1.102151675","orc":[{"fullImage":true,"id":6113662,"uo":[{"id":"10822867886","p":12,"s":2,"side":"B","status":"E","pt":"L","ot":"L","pd":1467219304000,"sm":0,"sr":2,"sl":0,"sc":0,"sv":0,"rac":"","rc":"REG_GGC"}]}]}]}',
        '{"op":"ocm","id":2,"clk":"AK0CAPsBALMC","pt":1467219316709,"oc":[{"id":"1.102151675","orc":[{"id":6113662,"uo":[{"id":"10822867886","p":12,"s":2,"side":"B","status":"EC","pt":"L","ot":"L","pd":1467219304000,"md":1467219316000,"avp":12,"sm":2,"sr":0,"sl":0,"sc":0,"sv":0}],"mb":[[12,2]]}]}]}',
        '{"op":"ocm","id":2,"clk":"AK0CAJACALsC","pt":1467219376611,"oc":[{"id":"1.102151675","orc":[{"id":6113662,"uo":[{"id":"10822867886","p":12,"s":2,"side":"B","status":"EC","pt":"L","ot":"L","pd":1467219304000,"md":1467219316000,"avp":9.47,"sm":2,"sr":0,"sl":0,"sc":0,"sv":0}],"mb":[[9.47,2],[12,0]]}]}]}',
    ]
    r = Raccolta()
    li = FOC.ListenerConto(r, lambda: 1.0e12)
    li.register_stream(2, "orderSubscription")
    for riga in righe:
        li.on_data(riga)
    o = r.ultimi["10822867886"]
    assert (o.stato, o.abbinato, o.residuo, o.prezzo_medio) == ("EXECUTION_COMPLETE", 2.0, 0.0, 9.47)
    assert (o.customer_order_ref, o.customer_strategy_ref, o.regulator_code) == (None, None, None)
    assert (o.piazzato_ms, o.abbinato_ms) == (1467219304000, 1467219316000)
    assert li.clk == "AK0CAJACALsC" and not li.errore_elaborazione
    assert r.info[-1]["posizioni"][("1.102151675", 6113662, 0.0)]["abbinati_back"] == [[9.47, 2]]


def test_ordine_BSP_senza_prezzo_ne_size_resta_con_valori_assenti():
    """BSP (MARKET_ON_CLOSE) senza ``p``/``s`` (non verificato dal vivo): l'ordine resta,
    prezzo e importo ASSENTI (None, mai 0), la liability non si inventa."""
    li, r = listener_vero()
    bsp = _senza(uo("BSP1", ot="MOC", pt="MOC", bsp=10.0), "p", "s", "rfo", "rfs", "sc")
    li.on_data(ocm([mercato(MID, [runner(19, [bsp, uo("NORMALE")])], full=True)],
                   ct="SUB_IMAGE", clk="1"))
    u = r.ultimi
    assert set(u) == {"BSP1", "NORMALE"}
    assert (u["BSP1"].prezzo, u["BSP1"].importo, u["BSP1"].tipo) == (None, None, "MARKET_ON_CLOSE")
    assert u["BSP1"].annullato == 0.0


def test_ordine_non_applicabile_si_scarta_e_si_segnala_il_resto_passa():
    """Un ordine senza ``side`` o con un codice sconosciuto: provato con la classe vera
    PRIMA della cache, tolto dal messaggio (gli altri passano), contato e segnalato."""
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    li = f._listener
    li.register_stream(5, "orderSubscription")
    li.on_data(ocm([mercato(MID, [runner(19, [_senza(uo("SENZA_LATO"), "side"), uo("X1", side="X"),
                                              uo("BUONO")])], full=True)],
                   ct="SUB_IMAGE", clk="1"))
    assert [o.bet_id for o in f.ordini()] == ["BUONO"]
    assert {"SENZA_LATO", "X1"} <= f.ordini_non_confermati()   # il comparto C li riconcilia via REST
    st = f.stato()
    assert st["ordini_scartati"] == 2 and st["riconnessioni"] == 0
    assert li.clk == "1" and not li.errore_elaborazione


def test_parziale_poi_completo_poi_annullato_scaduto_e_annullato_da_betfair():
    li, r = listener_vero()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("A"), uo("B"), uo("C"), uo("D")])])],
                   ct="SUB_IMAGE", clk="1"))
    li.on_data(ocm([mercato(MID, [runner(19, [uo("A", sm=4.0, sr=6.0, avp=2.5,
                                                 md=PT0 + 10)])])], clk="2", pt=PT0 + 20))
    assert r.ultimi["A"].abbinato == 4.0 and r.ultimi["A"].residuo == 6.0
    assert r.ultimi["A"].stato == "EXECUTABLE"
    li.on_data(ocm([mercato(MID, [runner(19, [
        uo("A", status="EC", sm=10.0, sr=0.0, avp=2.52, md=PT0 + 30),
        uo("B", status="EC", sm=0.0, sr=0.0, sc=10.0),
        uo("C", status="EC", sm=3.0, sr=0.0, sl=7.0, avp=2.5),
        uo("D", status="EC", sm=0.0, sr=0.0, sv=10.0),
    ])])], clk="3", pt=PT0 + 40))
    u = r.ultimi
    assert (u["A"].stato, u["A"].abbinato, u["A"].prezzo_medio) == ("EXECUTION_COMPLETE", 10.0, 2.52)
    assert (u["B"].annullato, u["B"].residuo) == (10.0, 0.0)
    assert (u["C"].scaduto, u["C"].abbinato) == (7.0, 3.0)
    assert u["D"].annullato_da_betfair == 10.0
    # solo gli ordini toccati dal messaggio escono, non tutto il mercato
    assert [o.bet_id for o in r.lotti[1]] == ["A"]


def test_ordini_di_piu_strategie_e_del_sito_tutti_presenti():
    li, r = listener_vero()
    li.on_data(ocm([
        mercato(MID, [runner(19, [uo("1", rfs="mike_live", rfo="mk-1"),
                                  uo("2", rfs="scalper_ev1", rfo="sc-9")]),
                      runner(22, [uo("3")])], full=True),
        mercato(MID2, [runner(58805, [uo("4", rfs="omega")])], full=True),
    ], ct="SUB_IMAGE", clk="1"))
    refs = {o.bet_id: o.customer_strategy_ref for o in r.lotti[0]}
    assert refs == {"1": "mike_live", "2": "scalper_ev1", "3": None, "4": "omega"}
    assert {o.market_id for o in r.lotti[0]} == {MID, MID2}


def test_posizione_complessiva_mb_ml_in_delta():
    li, r = listener_vero()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1", sm=5, sr=5)], full=True,
                                         mb=[[2.5, 5.0]], ml=[[3.0, 2.0]])], full=True)],
                   ct="SUB_IMAGE"))
    pos = r.info[0]["posizioni"][(MID, 19, 0.0)]
    assert pos == {"abbinati_back": [[2.5, 5.0]], "abbinati_lay": [[3.0, 2.0]]}
    li.on_data(ocm([mercato(MID, [{"id": 19, "hc": 0, "mb": [[2.5, 8.0], [2.6, 1.0]],
                                   "ml": [[3.0, 0]]}])], pt=PT0 + 5))
    pos = r.info[1]["posizioni"][(MID, 19, 0.0)]
    assert pos == {"abbinati_back": [[2.5, 8.0], [2.6, 1.0]], "abbinati_lay": []}


def test_messaggi_segmentati_clk_solo_a_fine_segmento():
    li, r = listener_vero()
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1")])], full=True)], ct="SUB_IMAGE",
                   segmentType="SEG_START", initial="INI"))
    assert li.clk is None                   # nessun clk prima della fine
    li.on_data(ocm([mercato(MID2, [runner(22, [uo("2")])], full=True)], ct="SUB_IMAGE",
                   segmentType="SEG"))
    li.on_data(ocm([mercato("1.3", [runner(7, [uo("3")])], full=True)], ct="SUB_IMAGE",
                   segmentType="SEG_END", clk="FINE"))
    assert sorted(r.ultimi) == ["1", "2", "3"]
    assert (li.initial_clk, li.clk) == ("INI", "FINE")


def test_immagine_piena_dopo_caduta_segnala_gli_eseguiti_mentre_era_giu():
    sess = SessioneFinta()
    f = FOC.FlussoOrdiniContoBetfair(sess)
    li = f._listener
    li.register_stream(5, "orderSubscription")
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1"), uo("2")])], full=True)], ct="SUB_IMAGE"))
    assert f.ordini_non_confermati() == set()
    # nuova immagine (senza clk valido): "2" non c'e' piu' -> concluso a connessione giu'
    li.register_stream(6, "orderSubscription")
    li.on_data(ocm([mercato(MID, [runner(19, [uo("1", sm=1.0, sr=9.0)])], full=True)],
                   ct="SUB_IMAGE", sid=6))
    assert f.ordini_non_confermati() == {"2"}
    assert {o.bet_id for o in f.ordini(MID)} == {"1", "2"}       # nessuno sparisce
    assert f.ordini(MID2) == ()


def test_sola_lettura_nessun_metodo_che_piazza_o_annulla():
    pubblici = {n for n, v in inspect.getmembers(FOC.FlussoOrdiniContoBetfair)
                if not n.startswith("_") and callable(v)}
    assert pubblici == {"avvia", "ferma", "aggiungi_consumatore", "ordini", "posizioni",
                        "ordini_non_confermati", "stato"}
    sorgente = inspect.getsource(FOC)
    for vietato in ("place_order", "cancel_order", "replace_order", "update_order",
                    ".betting."):
        assert vietato not in sorgente
    assert conforme(FOC.FlussoOrdiniContoBetfair, FlussoOrdiniConto) == []


def test_filtro_senza_strategia_con_posizione_complessiva():
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    assert f.filtro_ordini == {"includeOverallPosition": True,
                               "partitionMatchedByStrategyRef": False}


def test_importare_il_modulo_non_crea_thread_ne_socket():
    codice = ("import threading, socket\n"
              "aperti = []\n"
              "orig = socket.socket.connect\n"
              "socket.socket.connect = lambda s, *a: aperti.append(a)\n"
              "import Betfair.nucleo.betfair.flusso_ordini_conto, Betfair.nucleo.betfair.flusso\n"
              "import Betfair.nucleo.betfair.ladder, Betfair.nucleo.betfair.profili\n"
              "print(threading.active_count(), len(aperti))\n")
    esito = subprocess.run([sys.executable, "-c", codice], capture_output=True, text=True,
                           timeout=120, cwd=_radice())
    assert esito.returncode == 0, esito.stderr[-2000:]
    assert esito.stdout.split()[-2:] == ["1", "0"]


def _radice() -> str:
    import os
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


# ---------------------------------------------------------------------------
# 2. la connessione intera (server finto TLS, BetfairStream vero)
# ---------------------------------------------------------------------------
@pytest.fixture
def backoff_breve(monkeypatch):
    monkeypatch.setattr(FOC, "BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(FOC, "BACKOFF_MAX_S", 0.2)


def _immagine(k: int) -> Dict[str, Any]:
    return {"op": "ocm", "initialClk": "INI-%d" % k, "clk": "CLK-%d" % k, "pt": PT0,
            "heartbeatMs": 5000, "ct": "SUB_IMAGE",
            "oc": [mercato(MID, [runner(19, [uo("1", rfs="mike_live"), uo("2")])], full=True)]}


def test_connessione_vera_sottoscrive_senza_filtro_e_riprende_con_clk(server_stream, backoff_breve):
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        if k == 1:
            return [_immagine(1), {"op": "ocm", "clk": "CLK-2", "pt": PT0 + 50,
                                   "oc": [mercato(MID, [runner(19, [uo("1", sm=2.0, sr=8.0,
                                                                       rfs="mike_live")])])]},
                    CHIUDI]
        return [{"op": "ocm", "clk": "CLK-3", "pt": PT0 + 90, "ct": "RESUB_DELTA",
                 "oc": [mercato(MID, [runner(19, [uo("2", status="EC", sm=10.0, sr=0.0,
                                                     avp=2.5)])])]}]
    srv = server_stream(risposta)
    sess = SessioneFinta()
    f = FOC.FlussoOrdiniContoBetfair(sess)
    visti: List[OrdineDalConto] = []
    f.aggiungi_consumatore(visti.append)
    f.avvia()
    try:
        assert attendi(lambda: len(srv.sottoscrizioni_di("orderSubscription")) >= 2)
        assert attendi(lambda: any(o.bet_id == "2" and o.stato == "EXECUTION_COMPLETE"
                                   for o in f.ordini()))
        prima, seconda = srv.sottoscrizioni_di("orderSubscription")[:2]
        assert prima["orderFilter"] == {"includeOverallPosition": True,
                                        "partitionMatchedByStrategyRef": False}
        assert "customerStrategyRefs" not in prima["orderFilter"]
        assert (prima["initialClk"], prima["clk"]) == (None, None)
        assert (prima["heartbeatMs"], prima["segmentationEnabled"]) == (5000, True)
        # ripresa: gli ultimi clk ricevuti PRIMA della caduta
        assert (seconda["initialClk"], seconda["clk"]) == ("INI-1", "CLK-2")
        assert seconda["orderFilter"] == prima["orderFilter"]
        auth = [m for _, m in srv.ricevuti if m["op"] == "authentication"]
        assert auth[0]["appKey"] == "chiave_finta" and auth[0]["session"] == "token-finto-1"
        st = f.stato()
        assert st["riprese_con_clk"] == 1 and st["immagini_piene"] == 1
        assert (st["sottoscrizione"], st["seme_rest_necessario"]) == ("ripresa_clk", False)
        assert st["riconnessioni"] >= 1 and st["ultimo_clk"] == "CLK-3"
        assert attendi(lambda: {o.bet_id for o in visti} == {"1", "2"})
        uno = [o for o in f.ordini() if o.bet_id == "1"][0]
        assert (uno.abbinato, uno.residuo) == (2.0, 8.0)
        assert sess.chiamate_vietate == []
    finally:
        f.ferma()
    assert not any(t.name.startswith("ordini-conto") and t.is_alive() for t in threading.enumerate())


def test_invalid_clock_riparte_da_immagine_piena(server_stream, backoff_breve):
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        if k == 1:
            return [_immagine(1), CHIUDI]
        if k == 2:
            return [{"op": "status", "statusCode": "FAILURE", "errorCode": "INVALID_CLOCK",
                     "errorMessage": "clock non valido", "connectionClosed": True}]
        return [_immagine(3)]
    srv = server_stream(risposta)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    f.avvia()
    try:
        assert attendi(lambda: len(srv.sottoscrizioni_di("orderSubscription")) >= 3)
        subs = srv.sottoscrizioni_di("orderSubscription")
        assert subs[1]["clk"] == "CLK-1"
        assert (subs[2]["initialClk"], subs[2]["clk"]) == (None, None)
        assert attendi(lambda: f.stato()["ultimo_clk"] == "CLK-3")
        assert (f.stato()["sottoscrizione"], f.stato()["seme_rest_necessario"]) == ("da_zero", True)
    finally:
        f.ferma()


def test_sessione_scaduta_rinnova_e_riprova(server_stream, backoff_breve):
    def autentica(n: int) -> Dict[str, Any]:
        if n == 1:
            return {"op": "status", "statusCode": "FAILURE", "errorCode": "NO_SESSION",
                    "errorMessage": "sessione scaduta", "connectionClosed": True}
        return {"op": "status", "statusCode": "SUCCESS", "connectionClosed": False,
                "connectionsAvailable": 0}
    srv = server_stream(lambda n, m, k: [_immagine(k)], autentica)
    sess = SessioneFinta()
    f = FOC.FlussoOrdiniContoBetfair(sess)
    f.avvia()
    try:
        assert attendi(lambda: len(f.ordini()) == 2)
        assert sess.rinnovi == 1
        auth = [m for _, m in srv.ricevuti if m["op"] == "authentication"]
        assert [a["session"] for a in auth[:2]] == ["token-finto-1", "token-finto-2"]
        assert f.stato()["connessioni_disponibili"] == 0       # lo 0 si tiene
    finally:
        f.ferma()


def test_vivo_poi_muto_poi_latente_503(server_stream):
    ora = {"ms": 1.0e12}
    srv = server_stream(lambda n, m, k: [_immagine(1)])
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta(), orologio_ms=lambda: ora["ms"])
    assert f.stato()["stato"] == "assente"
    f.avvia()
    try:
        assert attendi(lambda: len(f.ordini()) == 2)
        assert f.stato()["stato"] == "vivo"
        ora["ms"] += 15_001                    # piu' di 3 heartbeat da 5000 ms
        st = f.stato()
        assert (st["stato"], st["motivo"]) == ("muto", "flusso_interrotto")
        srv.manda(1, {"op": "ocm", "clk": "CLK-9", "pt": PT0 + 99, "ct": "HEARTBEAT",
                      "status": 503})
        assert attendi(lambda: f.stato()["latente"])
        st = f.stato()
        assert (st["stato"], st["motivo"]) == ("muto", "stream_latente")
    finally:
        f.ferma()


def test_consumatore_per_mercato_e_consumatore_che_solleva(server_stream):
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        return [{"op": "ocm", "initialClk": "I", "clk": "C", "pt": PT0, "ct": "SUB_IMAGE",
                 "oc": [mercato(MID, [runner(19, [uo("1")])], full=True),
                        mercato(MID2, [runner(22, [uo("2")])], full=True)]}]
    server_stream(risposta)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    solo_mid2: List[str] = []
    tutti: List[str] = []

    def rotto(o: OrdineDalConto) -> None:
        raise RuntimeError("consumatore rotto")
    f.aggiungi_consumatore(rotto)
    f.aggiungi_consumatore(lambda o: solo_mid2.append(o.bet_id), mercati={MID2})
    f.aggiungi_consumatore(lambda o: tutti.append(o.bet_id))
    f.avvia()
    try:
        assert attendi(lambda: sorted(tutti) == ["1", "2"])
        assert solo_mid2 == ["2"]
        assert f.stato()["errori_consumatori"] == 2
    finally:
        f.ferma()


def test_connessione_vera_regge_l_ordine_del_sito_senza_riferimenti(server_stream, backoff_breve):
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        return [{"op": "ocm", "initialClk": "I", "clk": "C1", "pt": PT0, "ct": "SUB_IMAGE",
                 "oc": [mercato(MID, [runner(19, [uo("1", rfs="mike_live")])], full=True)]},
                {"op": "ocm", "clk": "C2", "pt": PT0 + 5,
                 "oc": [mercato(MID, [runner(19, [_senza(uo("SITO"), "rfo", "rfs", "rac", "rc")])])]}]
    srv = server_stream(risposta)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    f.avvia()
    try:
        assert attendi(lambda: {o.bet_id for o in f.ordini()} == {"1", "SITO"})
        assert not attendi(lambda: len(srv.sottoscrizioni) > 1, secondi=0.5)   # nessuna caduta
        assert f.stato()["riconnessioni"] == 0 and f.stato()["ultimo_clk"] == "C2"
    finally:
        f.ferma()


def test_messaggio_malformato_si_riconnette_da_immagine_piena(server_stream, backoff_breve):
    """Un ``oc`` senza id di mercato fa sollevare la libreria (``stream.py`` ``_process``)."""
    """La libreria segna ``clk`` = CLK-X prima di fallire sul messaggio: riprendere
    da li' lo salterebbe. Si riparte da immagine piena (clk nulli)."""
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        if k == 1:
            return [_immagine(1), {"op": "ocm", "clk": "CLK-X", "pt": PT0 + 5,
                                   "oc": [{"orc": [runner(19, [uo("9")])]}]}]   # oc senza id
        return [{"op": "ocm", "initialClk": "INI-2", "clk": "CLK-4", "pt": PT0 + 9,
                 "ct": "SUB_IMAGE",
                 "oc": [mercato(MID, [runner(19, [uo("1"), uo("2"), uo("9")])], full=True)]}]
    srv = server_stream(risposta)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    f.avvia()
    try:
        assert attendi(lambda: any(o.bet_id == "9" for o in f.ordini()))
        seconda = srv.sottoscrizioni_di("orderSubscription")[1]
        assert (seconda["initialClk"], seconda["clk"]) == (None, None)
        assert f.stato()["riconnessioni"] == 1
    finally:
        f.ferma()


def test_ferma_non_riconnette_piu(server_stream, backoff_breve):
    srv = server_stream(lambda n, m, k: [_immagine(k)])
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    f.avvia()
    assert attendi(lambda: len(f.ordini()) == 2)
    f.ferma()
    n = srv.connessioni
    srv.chiudi_connessione(1)
    assert not attendi(lambda: srv.connessioni > n, secondi=0.6)
    assert f.stato()["stato"] == "assente"
