"""M-2 (11/10/2026, mappatura dei flussi): le misure in piu' del modulo "Salute".

Per ogni misura tre prove sullo STESSO codice vero:
  * monitor SPENTO (di serie): nessun campo, nessun contatore, comportamento
    identico (canale, ladder, lettore dello scanner);
  * monitor ACCESO: il campo c'e' ed e' coerente (stesso orologio, stessa
    chiave, paper e live separati, calcio e tennis separati);
  * ERRORE: un ingresso storto o un registro che solleva non risale MAI al
    chiamante.

Finti con le chiavi e i tipi del vero: listener, LiveSession/TennisLiveSession,
recorder e capture VERI per il ladder; LocalChannel VERO mai avviato (loop finto
che esegue subito); ClientScan VERO; tempi_ordine VERO; APIClient VERO di
betfairlightweight con l'adattatore di requests sostituito; record di log con
gli ``extra`` che flumine scrive davvero (``baseexecution``/``betfairexecution``).
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import queue
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
import requests

from Betfair.monitor import referto as R
from Betfair.monitor import sonde as M
from Betfair.monitor.registro import BORDI_MS

PT0 = 1_758_600_000_000


@pytest.fixture
def spento(monkeypatch):
    monkeypatch.setenv(M.ENV, "0")
    M.ferma()
    M.REGISTRO.azzera_tutto()
    yield M
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"] == {} and f["tratti"] == {}, "monitor spento ma registro scritto"
    assert not M._RX_PT, "monitor spento ma pt -> rx ricordati"


def _mcm(pt: int, mid: str = "1.900") -> str:
    return json.dumps({"op": "mcm", "id": 1, "clk": "AAA", "pt": pt,
                       "mc": [{"id": mid, "rc": [{"id": 11, "atb": [[2.0, 5]]}]}]})


# ---------------------------------------------------------------------------
# M1 b: rx_ms nel ladder del canale (calcio e tennis)
# ---------------------------------------------------------------------------
def _book(pt: int, size_back: float = 50.0, mid: str = "1.900") -> Any:
    from betfairlightweight.resources.bettingresources import PriceSize

    runners = [SimpleNamespace(
        selection_id=sel, handicap=0.0, status="ACTIVE", last_price_traded=2.0, total_matched=100.0,
        ex=SimpleNamespace(available_to_back=[PriceSize(2.0, size_back)],
                           available_to_lay=[PriceSize(2.02, 40.0)],
                           traded_volume=[PriceSize(2.0, 80.0)]))
        for sel in (11, 12)]
    return SimpleNamespace(market_id=mid, publish_time_epoch=pt, inplay=True, status="OPEN",
                           total_matched=200.0, runners=runners,
                           market_definition=SimpleNamespace(market_type="MATCH_ODDS", in_play=True,
                                                             bet_delay=5))


def _giro_calcio(tmp_path, monkeypatch):
    from betfairlightweight.filters import streaming_market_data_filter, streaming_market_filter

    from Betfair.stream import ladder_canale, local_channel, raw_listener, runner
    from Betfair.stream.recorder import MarketRecorderStrategy

    raw_listener.RawTeeStreamListener(output_queue=queue.Queue(), max_latency=None).on_data(_mcm(PT0))
    rec = MarketRecorderStrategy(
        market_filter=streaming_market_filter(market_ids=["1.900"]),
        market_data_filter=streaming_market_data_filter(fields=["EX_ALL_OFFERS"], ladder_levels=10),
        context={"data_dir": str(tmp_path), "market_to_event": {"1.900": "35.1"}, "depth": 10,
                 "record_events": lambda: set()})
    sess = runner.LiveSession()
    sess.recorder = rec
    sess.markets_by_event["35.1"] = [{"market_id": "1.900", "market_type": "MATCH_ODDS",
                                      "market_name": "Esito finale"}]
    sess.selection_names["1.900"] = {"11": "Casa", "12": "Ospite"}
    sess._stato_ladder = ladder_canale.StatoLadder(2.0, 200, orologio=lambda: 1000.0)
    pubblicati: List[Dict[str, Any]] = []
    db_rows: List[Dict[str, Any]] = []
    monkeypatch.setattr(local_channel, "channel_active", lambda: True)
    monkeypatch.setattr(local_channel, "publish", lambda topic, payload: pubblicati.append(payload))
    monkeypatch.setattr(runner.db, "upsert_live_ladder", lambda row: db_rows.append(dict(row)))
    rec.process_market_book(object(), _book(PT0))
    runner.ladder_worker({}, None, sess)
    return pubblicati, db_rows


def _giro_tennis(monkeypatch):
    from Betfair.stream import ladder_canale, local_channel
    from Betfair.stream.tennis_live import tennis_db, tennis_recorder, tennis_runner

    tennis_recorder._TennisRecListener(output_queue=queue.Queue(), max_latency=None).on_data(_mcm(PT0))
    sess = tennis_runner.TennisLiveSession(trading=None)
    cap = tennis_runner._make_capture("1.900", "35.1")
    sess.capture["35.1"] = cap
    sess.market_meta["35.1"] = {"market_id": "1.900", "market_type": "MATCH_ODDS",
                                "market_name": "Vincente", "selection_names": {"11": "A", "12": "B"}}
    sess._stato_ladder = ladder_canale.StatoLadder(2.0, 200, orologio=lambda: 1000.0)
    pubblicati: List[Dict[str, Any]] = []
    db_rows: List[Dict[str, Any]] = []
    monkeypatch.setattr(local_channel, "channel_active", lambda: True)
    monkeypatch.setattr(local_channel, "publish", lambda topic, payload: pubblicati.append(payload))
    monkeypatch.setattr(tennis_db, "upsert_tennis_ladder", lambda row: db_rows.append(dict(row)))
    cap.process_market_book(object(), _book(PT0))
    tennis_runner.ladder_worker({}, None, sess)
    return pubblicati, db_rows


@pytest.mark.parametrize("giro", ["calcio", "tennis"])
def test_ladder_spento_identico(giro, tmp_path, monkeypatch, spento):
    pubblicati, db_rows = (_giro_calcio(tmp_path, monkeypatch) if giro == "calcio"
                           else _giro_tennis(monkeypatch))
    assert len(pubblicati) == 1 and len(db_rows) == 1
    assert pubblicati[0] == db_rows[0]
    assert not {"ts_pub_ms", "pt", "rx_ms"} & set(pubblicati[0])


@pytest.mark.parametrize("giro", ["calcio", "tennis"])
def test_ladder_acceso_rx_ms_e_tratto_sullo_stesso_orologio(giro, tmp_path, monkeypatch, monitor_acceso):
    prima = M.ora_ms()
    pubblicati, db_rows = (_giro_calcio(tmp_path, monkeypatch) if giro == "calcio"
                           else _giro_tennis(monkeypatch))
    p = pubblicati[0]
    assert p["pt"] == PT0
    assert prima <= p["rx_ms"] <= p["ts_pub_ms"] <= M.ora_ms()
    assert {k: v for k, v in p.items() if k not in ("ts_pub_ms", "pt", "rx_ms")} == db_rows[0]
    assert set(db_rows[0]) == {"event_id", "market_id", "market_type", "market_name", "status", "ladder"}
    t = M.REGISTRO.fotografa_e_azzera()["tratti"]
    assert t["ladder_rx_pub_ms"]["n"] == 1
    assert 0 <= t["ladder_rx_pub_ms"]["max"] == pytest.approx(p["ts_pub_ms"] - p["rx_ms"], abs=1.0)
    assert t["ladder_pub_pt_ms"]["n"] == 1


def test_ladder_senza_messaggio_visto_niente_rx(monitor_acceso):
    out = M.marca_ladder({"market_id": "1.1"}, {"pt": PT0 + 77})
    assert "rx_ms" not in out and out["pt"] == PT0 + 77
    assert "ladder_rx_pub_ms" not in M.REGISTRO.fotografa_e_azzera()["tratti"]


def test_rx_per_pt_primo_arrivo_e_tetto(monitor_acceso):
    M._ricorda_rx(5, 100.0)
    M._ricorda_rx(5, 900.0)                       # stesso pt: conta il primo arrivo
    assert M.rx_di_pt(5) == 100.0
    for i in range(M.RX_PT_MAX + 10):
        M._ricorda_rx(1000 + i, float(i))
    assert len(M._RX_PT) == M.RX_PT_MAX
    assert M.rx_di_pt(5) is None and M.rx_di_pt(1000 + M.RX_PT_MAX + 9) == float(M.RX_PT_MAX + 9)
    assert M.rx_di_pt("non un numero") is None


# ---------------------------------------------------------------------------
# messaggi mcm e ocm per processo
# ---------------------------------------------------------------------------
def test_ocm_contati_a_parte_dai_mcm(monitor_acceso):
    M.osserva_stream("calcio", _mcm(PT0))
    ocm = json.dumps({"op": "ocm", "id": 2, "clk": "B", "pt": PT0, "oc": []})
    M.osserva_stream("ordini-calcio", ocm)
    M.osserva_stream("ordini-calcio", ocm)
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["stream_msg"] == {"calcio": 1}
    assert f["contatori"]["stream_ocm"] == {"ordini-calcio": 2}
    assert f["tratti"]["ordini_rx_pt_ms.ordini-calcio"]["n"] == 2
    assert "stream_altri" not in f["contatori"]


def test_ocm_spento(spento):
    M.osserva_stream("ordini", json.dumps({"op": "ocm", "pt": PT0}))


# ---------------------------------------------------------------------------
# canale locale: busta con ``ts`` e lettura nel bot (scanner -> bot)
# ---------------------------------------------------------------------------
class _LoopSubito:
    def __init__(self) -> None:
        self.testi: List[str] = []

    def call_soon_threadsafe(self, fn):
        fn()

    def create_task(self, x):
        self.testi.append(x)


def _canale_con_un_client():
    from Betfair.stream.local_channel import LocalChannel

    ch = LocalChannel(0, sport="scanner", solo_lettura=True, token="t", origini=[])
    loop = _LoopSubito()
    ws = object()
    ch._loop = loop
    ch._clients = {ws}
    ch._n_clients = 1
    ch._client_pronti = 1
    ch._safe_send = lambda w, text: text
    return ch, loop


def test_busta_spenta_identica(spento):
    ch, loop = _canale_con_un_client()
    ch.publish("scan_calcio", {"event_id": "35.1", "x": 1.5})
    assert loop.testi == [json.dumps({"t": "scan_calcio", "d": {"event_id": "35.1", "x": 1.5}})]


def test_busta_funzione_spenta_senza_ts(spento):
    """Seconda guardia: anche chiamata a monitor spento la busta e' quella di sempre."""
    assert M.busta("order", {"a": 1}) == {"t": "order", "d": {"a": 1}}


def test_busta_registro_che_solleva(monkeypatch, monitor_acceso):
    monkeypatch.setattr(M.REGISTRO, "conta", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    b = M.busta("order", {"a": 1})
    assert b["d"] == {"a": 1} and b["t"] == "order"
    M.ricevuto_canale({"t": "x", "ts": 5})
    M.ricevuto_canale("non una busta")


def test_busta_accesa_ts_in_piu_e_conteggio(monitor_acceso):
    ch, loop = _canale_con_un_client()
    prima = M.ora_ms()
    ch.publish("scan_calcio", {"event_id": "35.1"})
    b = json.loads(loop.testi[0])
    assert prima <= b.pop("ts") <= M.ora_ms()
    assert b == {"t": "scan_calcio", "d": {"event_id": "35.1"}}
    assert M.REGISTRO.fotografa_e_azzera()["contatori"]["canale_pub"] == {"scan_calcio": 1}


def _client_scan():
    from Betfair.safe_strategy import canale_scan as CS

    return CS.ClientScan(0, CS.CacheScan())


def _riga_scan():
    return {"event_id": "35.1", "updated_at": "2026-10-11T10:00:00+00:00",
            "payload": {"odds_ts_ms": PT0}}


def test_lettore_scanner_spento_identico(spento):
    c = _client_scan()
    assert c.incassa(json.dumps({"t": "scan_calcio", "d": _riga_scan(), "ts": PT0})) is True
    assert c.incassa(json.dumps({"t": "hello", "d": {}})) is False


def test_lettore_scanner_acceso_latenza_per_topic(monitor_acceso):
    c = _client_scan()
    ts = M.ora_ms() - 3
    assert c.incassa(json.dumps({"t": "scan_calcio", "d": _riga_scan(), "ts": ts})) is True
    assert c.incassa(json.dumps({"t": "scanner_stato", "d": {}, "ts": ts})) is False
    c.incassa(json.dumps({"t": "scan_calcio", "d": dict(_riga_scan(), event_id="35.2")}))  # senza ts
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["canale_ric"] == {"scan_calcio": 2, "scanner_stato": 1}
    assert f["tratti"]["canale_ricezione_ms.scan_calcio"]["n"] == 1      # senza ts: nessun tratto
    assert f["tratti"]["canale_ricezione_ms.scan_calcio"]["min"] >= 3
    assert f["tratti"]["canale_ricezione_ms.scanner_stato"]["n"] == 1


# ---------------------------------------------------------------------------
# M1 c-d: il riassunto della PAGINA sul canale gia' aperto
# ---------------------------------------------------------------------------
def _riassunto(n_dipinti: int = 2) -> Dict[str, Any]:
    secchi = [0] * (len(BORDI_MS) + 1)
    secchi[7] = n_dipinti                 # (10, 20] ms
    return {"v": 1, "bordi": list(BORDI_MS),
            "tratti": {"pagina_dipinto_ms": {"n": n_dipinti, "somma": 15.0 * n_dipinti, "min": 12.0, "max": 18.0,
                                             "secchi": secchi}},
            "contatori": {"push_ladder": 5, "dipinti": n_dipinti}}


def _canale_runner():
    from Betfair.stream.local_channel import LocalChannel

    ch = LocalChannel(0, sport="calcio", solo_lettura=False, token="t", origini=[])
    inviati: List[Dict[str, Any]] = []
    ch._send = lambda ws, payload: inviati.append(payload)
    return ch, inviati


def test_pagina_spento_metodo_sconosciuto_come_prima(spento):
    ch, inviati = _canale_runner()
    ch._on_message(object(), json.dumps({"id": 4, "m": "salute", "p": _riassunto()}))
    assert inviati == [{"id": 4, "ok": False, "e": "metodo sconosciuto: salute"}]
    assert ch.pop_requests() == []


def test_pagina_acceso_fusa_nel_registro_mai_in_coda(monitor_acceso):
    ch, inviati = _canale_runner()
    ws = object()
    ch._on_message(ws, json.dumps({"id": 4, "m": "salute", "p": _riassunto(2)}))
    ch._on_message(ws, json.dumps({"id": 5, "m": "salute", "p": _riassunto(3)}))
    assert inviati == [{"id": 4, "ok": True, "d": {"tratti": 1}}, {"id": 5, "ok": True, "d": {"tratti": 1}}]
    assert ch.pop_requests() == []                       # nessun comando in coda
    f = M.REGISTRO.fotografa_e_azzera()
    t = f["tratti"]["pagina_dipinto_ms"]
    assert t["n"] == 5 and t["somma"] == 75.0 and t["min"] == 12.0 and t["max"] == 18.0
    assert t["secchi"][7] == 5 and t["p50"] == 18.0       # bordo 20, limitato al massimo visto
    assert f["contatori"]["pagina"] == {"push_ladder": 10, "dipinti": 5, "riassunti_accolti": 2}


@pytest.mark.parametrize("guasto", [
    lambda p: p.update(bordi=list(BORDI_MS)[:-1] + [99999.0]),              # bordi diversi
    lambda p: p.update(v=2),                                                 # versione
    lambda p: p["tratti"].update(ordine_finto_ms=p["tratti"]["pagina_dipinto_ms"]),  # tratto non ammesso
    lambda p: p["tratti"]["pagina_dipinto_ms"].update(n=7),                  # n != somma secchi
    lambda p: p["tratti"]["pagina_dipinto_ms"]["secchi"].append(0),          # secchi in piu'
    lambda p: p["tratti"]["pagina_dipinto_ms"].update(min=None),             # min mancante con n>0
    lambda p: p["tratti"]["pagina_dipinto_ms"].update(somma=float("nan")),
    lambda p: p["contatori"].update(ordini=1),                               # contatore non ammesso
    lambda p: p["contatori"].update(dipinti=-1),
    lambda p: p.update(tratti=[1, 2]),
])
def test_pagina_riassunto_storto_rifiutato_per_intero(guasto, monitor_acceso):
    p = _riassunto()
    p["tratti"]["pagina_canale_ms"] = dict(p["tratti"]["pagina_dipinto_ms"],
                                           secchi=list(p["tratti"]["pagina_dipinto_ms"]["secchi"]))
    guasto(p)
    r = M.misure_pagina(9, p)
    assert r["ok"] is False and r["id"] == 9 and r["e"].startswith("riassunto rifiutato")
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["tratti"] == {}                               # tutto o niente
    assert f["contatori"] == {"pagina": {"riassunti_rifiutati": 1}}


def test_pagina_non_oggetto_e_registro_che_solleva(monkeypatch, monitor_acceso):
    for p in (None, "x", 3, [], {"v": 1}):
        assert M.misure_pagina(1, p)["ok"] is False
    monkeypatch.setattr(M.REGISTRO, "fondi", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("giu")))
    assert M.misure_pagina(1, _riassunto())["ok"] is False


# ---------------------------------------------------------------------------
# M2: il CLIC della pagina (emesso_ms nell'``order`` del canale)
# ---------------------------------------------------------------------------
def _ordine_dal_canale(ch, p):
    ws = object()
    ch._autorizzati.add(ws)
    ch._on_message(ws, json.dumps({"id": 1, "m": "order", "p": p}))
    return ch.pop_requests()


def test_clic_spento_nessuna_misura_comando_identico(spento):
    ch, _ = _canale_runner()
    p = {"action": "place", "mode": "paper", "market_id": "1.1", "client_ref": "x", "emesso_ms": PT0}
    r = _ordine_dal_canale(ch, p)
    assert len(r) == 1 and r[0].params == p and r[0].ricevuto_ms == 0


def test_clic_acceso_tratti_per_modo(monitor_acceso):
    ch, _ = _canale_runner()
    adesso = M.ora_ms()
    for modo, eta in (("paper", 40), ("live", 15), ("live", 25)):
        p = {"action": "place", "mode": modo, "market_id": "1.1", "client_ref": "u", "emesso_ms": adesso - eta}
        r = _ordine_dal_canale(ch, p)
        assert r[0].params == p                          # il comando arriva intatto
    _ordine_dal_canale(ch, {"action": "place", "mode": "live", "market_id": "1.1"})   # senza clic
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["ordini_emessi"] == {"desktop": 3}
    assert f["tratti"]["clic_canale_ms.paper"]["n"] == 1
    assert f["tratti"]["clic_canale_ms.live"]["n"] == 2
    assert f["tratti"]["clic_canale_ms.paper"]["min"] >= 40
    assert f["tratti"]["clic_presa_ms.live"]["n"] == 2
    assert f["tratti"]["clic_presa_ms.live"]["min"] >= 15


@pytest.mark.parametrize("em", ["x", True, -1, 0, float("nan"), None, [1]])
def test_clic_storto_ignorato(em, monitor_acceso):
    M.drenate([SimpleNamespace(method="order", ricevuto_ms=M.ora_ms(),
                               params={"mode": "paper", "emesso_ms": em})])
    assert not [k for k in M.REGISTRO.fotografa_e_azzera()["tratti"] if k.startswith("clic_")]


def test_drenate_registro_che_solleva(monkeypatch, monitor_acceso):
    monkeypatch.setattr(M.REGISTRO, "tratto", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    M.drenate([SimpleNamespace(method="order", ricevuto_ms=1, params={"emesso_ms": 1})])
    M.drenate([object(), None])


# ---------------------------------------------------------------------------
# M2 per attore: le righe di tempi_ordine
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rif,attore", [
    ("mike-t12", "mike"), ("omega-t5", "omega"), ("safe-t6", "safe"), ("risk-3-x", "risk"),
    ("1b4e28ba-2fa1-11d2-883f-0016d3cca427", "desktop"), ("na", "ignoto"), (None, "ignoto"),
    ("awlq12", "altro"), ("XY-1", "altro"), ("x-1", "altro"), ("scalper-7", "scalper"),
    ("UI-3", "ui"), ("zzzz-9", "altro"),
])
def test_attore_da_rif(rif, attore):
    assert M.attore_da_rif(rif) == attore


def _ordine_tempi(chiave: str, *, rif: str, strada: str = "comando", mode: str = "paper",
                  azione: str = "place"):
    """Una richiesta passata per il modulo VERO ``tempi_ordine``: decisione 30 ms
    prima della lettura, invio 10 ms prima, place 5 ms dopo, risposta 40 ms dopo
    il place."""
    from Betfair.stream import tempi_ordine as TO

    mono0, wall0 = TO.ora()
    TO.nuovo(chiave, strada, t=(mono0, wall0), azione=azione, mode=mode, rif=rif,
             decisione_ms=wall0 - 30.0, invio=wall0 - 10.0)
    TO.presa(chiave)
    risposta = _dt.datetime.fromtimestamp((wall0 + 45.0) / 1000.0, tz=_dt.timezone.utc)
    ordine = SimpleNamespace(id="o-" + chiave, size_matched=0.0,
                             status=SimpleNamespace(name="EXECUTION_COMPLETE"),
                             responses=SimpleNamespace(_date_time_placed=risposta, place_response=None,
                                                       current_order=None))
    TO.place(ordine, t=(mono0 + 0.005, wall0 + 5.0))
    TO.fine(chiave, True)


def test_tempi_spento_nessuna_misura(spento, caplog):
    caplog.set_level(logging.INFO)
    from Betfair.stream import tempi_ordine as TO

    TO._azzera_per_test()
    _ordine_tempi("k0", rif="mike-t1")


def test_tempi_acceso_tratti_per_attore_strada_modo(monitor_acceso, caplog):
    from Betfair.stream import tempi_ordine as TO

    TO._azzera_per_test()
    with caplog.at_level(logging.INFO, logger="Betfair.stream.tempi_ordine"):
        _ordine_tempi("k1", rif="mike-t1")
        _ordine_tempi("k2", rif="1b4e28ba-2fa1-11d2-883f-0016d3cca427", strada="canale", mode="live")
        _ordine_tempi("k3", rif="omega-t9", azione="cancel")
    assert sum(1 for r in caplog.records if str(r.msg).startswith("tempi_ordine ")) == 3
    f = M.REGISTRO.fotografa_e_azzera()
    t = f["tratti"]
    assert t["decisione_invio_ms.mike.comando.paper"]["min"] == pytest.approx(20.0, abs=0.01)
    assert t["invio_presa_ms.mike.comando.paper"]["min"] == pytest.approx(10.0, abs=0.01)
    assert t["presa_place_ms.mike.comando.paper"]["min"] == pytest.approx(5.0, abs=0.01)
    assert t["place_risposta_ms.mike.comando.paper"]["min"] == pytest.approx(40.0, abs=1.0)
    assert t["decisione_risposta_ms.mike.comando.paper"]["min"] == pytest.approx(75.0, abs=1.0)
    assert t["decisione_risposta_ms.desktop.canale.live"]["n"] == 1     # live mai sommato al paper
    assert not [k for k in t if ".omega." in k]                        # il cancel non e' un piazzamento
    assert f["contatori"]["tempi_altre_azioni"] == {"cancel": 1}
    assert f["contatori"]["ordini_misurati"] == {"desktop.canale.live": 1, "mike.comando.paper": 1}


def test_tempi_riga_storta_e_registro_che_solleva(monkeypatch, monitor_acceso, caplog):
    caplog.set_level(logging.INFO)
    lg = logging.getLogger("Betfair.stream.tempi_ordine")
    lg.info("tempi_ordine azione=place decisione_ms=abc rif=mike-t1 strada")      # campi storti
    monkeypatch.setattr(M.REGISTRO, "tratto", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    lg.info("tempi_ordine ref=a strada=coda azione=place mode=paper decisione_ms=3 rif=safe-t1")


# ---------------------------------------------------------------------------
# pacchetto -> risposta di placeOrders (log di flumine), stream aperti, connessioni
# ---------------------------------------------------------------------------
def _log_execute(nome_logger: str, el_s: float) -> None:
    logging.getLogger(nome_logger).info(
        "execute_place", extra={"trading_function": "place", "elapsed_time": 0.08, "response": {},
                                "order_package": {"order_count": 1, "package_type": "Place",
                                                  "elapsed_seconds": el_s}})


def test_pacchetto_risposta_solo_live(monitor_acceso, caplog):
    caplog.set_level(logging.INFO)      # come i servizi: basicConfig(level=INFO)
    _log_execute("flumine.execution.betfairexecution", 0.25)
    _log_execute("flumine.execution.simulatedexecution", 0.5)
    t = M.REGISTRO.fotografa_e_azzera()["tratti"]
    assert t["pacchetto_risposta_ms"]["n"] == 1 and t["pacchetto_risposta_ms"]["max"] == 250.0


def test_stream_aperti_e_connessioni(monitor_acceso, caplog):
    caplog.set_level(logging.INFO)
    ms = logging.getLogger("flumine.streams.marketstream")
    os_ = logging.getLogger("flumine.streams.orderstream")
    ms.info("Starting MarketStream %s", 3)
    ms.info("Starting output_thread (MarketStream %s)", 3)
    ms.info("Starting MarketStream %s", 3)                  # retry: stessa connessione
    ms.info("Starting MarketStream %s", 4)
    os_.info("Starting OrderStream %s", 5)
    lis = logging.getLogger("betfairlightweight.streaming.listener")
    lis.info("[%s: %s]: connection_id: %s", "MarketStream", 3, "002-1")
    lis.info("[%s: %s]: connection_id: %s", "MarketStream", 4, "002-2")
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["valori"]["stream_aperti"] == {"MarketStream": 2, "OrderStream": 1}
    assert f["contatori"]["stream_connessioni"] == {"aperte": 2}
    ms.info("Stopped MarketStream %s", 4)
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["valori"]["stream_aperti"] == {"MarketStream": 1, "OrderStream": 1}
    assert f["contatori"]["stream_arresti"] == {"MarketStream": 1}


def test_gestore_che_solleva_non_risale_al_chiamante(monkeypatch, monitor_acceso, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(M.REGISTRO, "conta", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    logging.getLogger("flumine.streams.marketstream").info("Starting MarketStream %s", 3)
    _log_execute("flumine.execution.betfairexecution", 0.1)
    logging.getLogger("betfairlightweight.streaming.listener").info("[%s: %s]: connection_id: %s", "a", 1, "b")


def test_stream_spenti_nessun_handler(spento, caplog):
    caplog.set_level(logging.INFO)
    logging.getLogger("flumine.streams.marketstream").info("Starting MarketStream %s", 3)
    _log_execute("flumine.execution.betfairexecution", 0.1)


# ---------------------------------------------------------------------------
# peso delle richieste REST
# ---------------------------------------------------------------------------
def _corpo(metodo: str, params: Dict[str, Any]) -> str:
    return json.dumps({"jsonrpc": "2.0", "method": "SportsAPING/v1.0/" + metodo, "params": params, "id": 1})


@pytest.mark.parametrize("metodo,params,peso", [
    ("listMarketBook", {"marketIds": ["1.1", "1.2"]}, 4.0),
    ("listMarketBook", {"marketIds": ["1.1"], "priceProjection": {"priceData": ["EX_BEST_OFFERS"]}}, 5.0),
    ("listMarketBook", {"marketIds": ["1.1"] * 3,
                        "priceProjection": {"priceData": ["EX_ALL_OFFERS", "EX_TRADED"]}}, 51.0),
    ("listMarketBook", {"marketIds": ["1.1"], "priceProjection": {
        "priceData": ["EX_BEST_OFFERS", "SP_TRADED"], "exBestOffersOverrides": {"bestPricesDepth": 6}}}, 17.0),
    ("listRunnerBook", {"marketId": "1.1", "priceProjection": {"priceData": ["EX_TRADED"]}}, 17.0),
    ("listMarketCatalogue", {"marketProjection": ["RUNNER_DESCRIPTION", "MARKET_DESCRIPTION",
                                                  "RUNNER_METADATA"], "maxResults": 100}, 200.0),
    ("listMarketProfitAndLoss", {"marketIds": ["1.1", "1.2"]}, 8.0),
    ("placeOrders", {"marketId": "1.1"}, None),
])
def test_peso_richiesta(metodo, params, peso):
    assert M.peso_richiesta(metodo, _corpo(metodo, params)) == peso
    assert M.peso_richiesta(metodo, _corpo(metodo, params).encode()) == peso


class _Adattatore(requests.adapters.HTTPAdapter):
    def send(self, request, **kw):  # type: ignore[override]
        r = requests.Response()
        r.status_code = 200
        r.url = request.url
        r.request = request
        if "certlogin" in request.url:
            r._content = json.dumps({"loginStatus": "SUCCESS", "sessionToken": "tok"}).encode()
        else:
            r._content = json.dumps({"jsonrpc": "2.0", "result": [], "id": 1}).encode()
        r.headers["Content-Type"] = "application/json"
        return r


def _client_betfair(monkeypatch):
    from betfairlightweight import filters

    from Betfair.stream import auth

    for nome in ("BETFAIR_APP_KEY", "BETFAIR_USERNAME", "BETFAIR_PASSWORD", "BETFAIR_CERT_FILE",
                 "BETFAIR_KEY_FILE"):
        monkeypatch.setattr(auth, nome, "finto")
    vera = requests.Session

    def _sessione():
        s = vera()
        s.mount("https://", _Adattatore())
        return s

    monkeypatch.setattr(auth.requests, "Session", _sessione)
    c = auth.build_client(login=True)
    pp = filters.price_projection(price_data=["EX_BEST_OFFERS", "EX_TRADED"])
    c.betting.list_market_book(market_ids=["1.2", "1.3"], price_projection=pp, lightweight=True)
    c.betting.list_market_book(market_ids=["1.%d" % i for i in range(10)],
                               price_projection=filters.price_projection(price_data=["EX_ALL_OFFERS"]),
                               lightweight=True)
    return c


def test_peso_rest_acceso_con_apiclient_vero(monkeypatch, monitor_acceso):
    _client_betfair(monkeypatch)
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["betfair_rest"]["listMarketBook"] == 2
    assert f["contatori"]["betfair_rest_peso"] == {"listMarketBook": 44 + 170}
    assert f["tratti"]["rest_peso.listMarketBook"]["n"] == 2
    assert f["tratti"]["rest_peso.listMarketBook"]["max"] == 170.0
    assert "betfair_rest_oltre_peso" not in f["contatori"]


def test_peso_rest_corpo_storto_mai_propagato(monitor_acceso):
    for corpo in (b"\xff\xfe", "non json", "[1,2]", json.dumps({"params": [1]}), None):
        req = SimpleNamespace(url="https://api.betfair.com/exchange/betting/json-rpc/v1", body=corpo)
        M._bf_risposta(SimpleNamespace(request=req, status_code=200, elapsed=None))
    req = SimpleNamespace(url="x", body=_corpo("listMarketBook", {
        "marketIds": ["1.1"] * 20, "priceProjection": {"priceData": ["EX_ALL_OFFERS"]}}))
    M._bf_risposta(SimpleNamespace(request=req, status_code=200, elapsed=None))
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["betfair_rest_oltre_peso"] == {"listMarketBook": 1}


def test_peso_rest_spento(monkeypatch, spento):
    c = _client_betfair(monkeypatch)
    assert c.session.hooks["response"] == []


# ---------------------------------------------------------------------------
# referto: p50/p95/p99 per attore e sport, paper e live separati
# ---------------------------------------------------------------------------
def _ist(valori: List[float]) -> Dict[str, Any]:
    from Betfair.monitor.registro import Istogramma

    h = Istogramma()
    for v in valori:
        h.aggiungi(v)
    return h.riassunto()


def _riga(servizio: str, sport: str, ts: str, tratti: Dict[str, Any], contatori=None, valori=None):
    return {"ts": ts, "servizio": servizio, "sport": sport, "pid": 1, "host": "pc",
            "avvio_ts": "2026-10-10T06:00:00+00:00", "uptime_s": 100.0, "cpu_pct": 1.0, "rss_mb": 50.0,
            "db_richieste": 0, "rest_richieste": 0,
            "metriche": {"v": 1, "finestra_s": 30.0, "processo": {}, "contatori": contatori or {},
                         "tratti": tratti, "valori": valori or {}}}


def _righe_m2():
    return [
        _riga("runner-calcio", "calcio", "2026-10-10T08:00:00+00:00", {
            "pagina_rx_dipinto_ms": _ist([12.0, 14.0, 30.0]),
            "ladder_rx_pub_ms": _ist([1.0]),
            "decisione_risposta_ms.mike.comando.paper": _ist([80.0, 90.0]),
            "decisione_risposta_ms.mike.comando.live": _ist([400.0]),
            "clic_canale_ms.live": _ist([3.0]),
        }, contatori={"stream_msg": {"calcio": 300}, "stream_ocm": {"ordini": 30},
                      "betfair_rest": {"listMarketBook": 4}, "betfair_rest_peso": {"listMarketBook": 80},
                      "stream_connessioni": {"aperte": 2}},
            valori={"stream_aperti": {"MarketStream": 1, "OrderStream": 1}}),
        _riga("runner-calcio", "calcio", "2026-10-10T08:00:30+00:00", {
            "pagina_rx_dipinto_ms": _ist([16.0]),
            "rest_peso.listMarketBook": _ist([20.0, 20.0]),
        }, contatori={"stream_msg": {"calcio": 600}}),
        _riga("runner-tennis", "tennis", "2026-10-10T08:00:00+00:00", {
            "pagina_rx_dipinto_ms": _ist([40.0]),
            "pacchetto_risposta_ms": _ist([120.0]),
        }),
        _riga("mike-service", "calcio", "2026-10-10T08:00:00+00:00", {
            "canale_ricezione_ms.scan_calcio": _ist([0.4, 0.6]),
        }),
    ]


def test_referto_m1_m2_per_sport_attore_e_modo():
    x = R.misure_m2(_righe_m2())
    m1 = {(t["sport"], t["tratto"]): t for t in x["m1"]}
    assert m1[("calcio", "pagina_rx_dipinto_ms")]["n"] == 4           # due finestre sommate
    assert m1[("calcio", "pagina_rx_dipinto_ms")]["p50"] == 20.0
    assert m1[("tennis", "pagina_rx_dipinto_ms")]["n"] == 1           # tennis MAI col calcio
    m2 = {(t["sport"], t["attore"], t["strada"], t["modo"], t["tratto"]): t for t in x["m2"]}
    assert m2[("calcio", "mike", "comando", "paper", "decisione_risposta_ms")]["n"] == 2
    assert m2[("calcio", "mike", "comando", "live", "decisione_risposta_ms")]["n"] == 1   # MAI sommati
    assert m2[("calcio", "desktop", "canale", "live", "clic_canale_ms")]["n"] == 1
    assert m2[("tennis", "processo:runner-tennis", "processo", "live", "pacchetto_risposta_ms")]["max"] == 120.0
    for t in x["m1"] + x["m2"]:
        assert {"p50", "p95", "p99", "max", "n"} <= set(t)
    assert x["canale"] == [dict(servizio="mike-service", topic="scan_calcio", n=2, min=0.4,
                                p50=0.5, p95=0.6, p99=0.6, max=0.6)]
    st = {(s["sorgente"], s["tipo"]): s for s in x["stream"]}
    assert st[("calcio", "mcm")]["messaggi"] == 900 and st[("calcio", "mcm")]["al_s_max"] == 20.0
    assert st[("ordini", "ocm")]["al_s_p50"] == 1.0
    assert x["stream_aperti"] == {"runner-calcio": {"MarketStream": 1, "OrderStream": 1}}
    assert x["connessioni_aperte"] == {"runner-calcio": 2}
    assert x["rest_peso"] == [{"servizio": "runner-calcio", "metodo": "listMarketBook", "richieste": 4,
                               "punti": 80.0, "punti_medi": 20.0, "p95": 20.0, "max": 20.0,
                               "oltre_200": 0}]


def test_referto_m2_stesse_righe_stessi_byte(tmp_path):
    a = R.costruisci("2026-10-10", R.filtra_giorno(_righe_m2(), *R.finestra_del_giorno("2026-10-10")),
                     fonte="test")
    b = R.costruisci("2026-10-10", R.filtra_giorno(list(reversed(_righe_m2())),
                                                   *R.finestra_del_giorno("2026-10-10")), fonte="test")
    pa, ja = R.scrivi(a, tmp_path / "a")
    pb, jb = R.scrivi(b, tmp_path / "b")
    assert pa.read_bytes() == pb.read_bytes() and ja.read_bytes() == jb.read_bytes()
    md = pa.read_text(encoding="utf-8")
    assert "## M1 - messaggio Betfair -> ladder a schermo, per sport" in md
    assert "| calcio | mike | comando | live | decisione_risposta_ms | 1 |" in md
    assert "| tennis | pagina_rx_dipinto_ms | 1 |" in md
    assert "peso REST runner-calcio listMarketBook: 4 richieste, 80 punti" in md


def test_referto_senza_misure_m2():
    x = R.misure_m2([_riga("omega-service", "calcio", "2026-10-10T08:00:00+00:00", {"db_ms": _ist([5.0])})])
    assert x == {"m1": [], "m2": [], "canale": [], "stream": [], "stream_aperti": {},
                 "connessioni_aperte": {}, "rest_peso": []}


# ---------------------------------------------------------------------------
# revisione indipendente dell'11/10 (M-1, M-2, T-1, T-2)
# ---------------------------------------------------------------------------
def _uno(n=2, somma=30.0, mn=12.0, mx=18.0, secchi=None):
    if secchi is None:
        secchi = [0] * (len(BORDI_MS) + 1)
        secchi[7] = n
    return {"v": 1, "bordi": list(BORDI_MS),
            "tratti": {"pagina_dipinto_ms": {"n": n, "somma": somma, "min": mn, "max": mx, "secchi": secchi}}}


def _secchi(**pos):
    s = [0] * (len(BORDI_MS) + 1)
    for k, v in pos.items():
        s[int(k[1:])] = v
    return s


@pytest.mark.parametrize("p", [
    _uno(mn=-1e300),                                   # valori avvelenati che passavano
    _uno(somma=1e300),
    _uno(mn=12.0, mx=1e8, secchi=_secchi(b7=1, b18=1)),  # oltre VALORE_MAX_MS
    _uno(mn=18.0, mx=12.0),                            # min > max
    _uno(somma=100.0),                                 # somma > n*max
    _uno(somma=1.0),                                   # somma < n*min
    _uno(mn=3.0, secchi=_secchi(b7=2)),                # min fuori dal primo secchio pieno
    _uno(mx=19.0, mn=12.0, secchi=_secchi(b7=1, b9=1)),  # max fuori dall'ultimo secchio pieno
    _uno(n=0, somma=5.0, mn=None, mx=None, secchi=_secchi()),   # somma senza misure
])
def test_pagina_valori_avvelenati_rifiutati(p, monitor_acceso):
    assert M.misure_pagina(1, p)["ok"] is False
    assert M.REGISTRO.fotografa_e_azzera()["tratti"] == {}


def test_pagina_bordi_enormi_rifiutati_senza_leggerli(monitor_acceso):
    class _Esplode(list):
        def __iter__(self):
            raise AssertionError("letti gli elementi prima della lunghezza")
    p = _uno()
    p["bordi"] = _Esplode([0.1] * 100_000)
    r = M.misure_pagina(1, p)
    assert r["ok"] is False and "bordi" in r["e"]


def test_pagina_valori_coerenti_e_scartati_accolti(monitor_acceso):
    p = _uno(n=3, somma=40.0, mn=12.0, mx=15.0)
    p["contatori"] = {"push_ladder": 4, "dipinti": 3, "scartati": 1}
    assert M.misure_pagina(1, p)["ok"] is True
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["pagina"]["scartati"] == 1 and f["tratti"]["pagina_dipinto_ms"]["n"] == 3


def test_registro_conta_le_chiavi_scartate_dal_tetto():
    from Betfair.monitor.registro import GRUPPO_SCARTATI, MAX_CHIAVI, Registro

    r = Registro()
    for i in range(MAX_CHIAVI + 3):
        r.tratto("t%d" % i, 1.0)
    for i in range(MAX_CHIAVI + 2):
        r.valore("g", "k%d" % i, i)
    f = r.fotografa_e_azzera()
    assert len(f["tratti"]) == MAX_CHIAVI
    assert f["contatori"][GRUPPO_SCARTATI] == {"tratti": 3, "valori.g": 2}


def test_tempi_con_un_tratto_mancante_nessun_totale(monitor_acceso, caplog):
    caplog.set_level(logging.INFO)
    logging.getLogger("Betfair.stream.tempi_ordine").info(
        "tempi_ordine ref=a strada=canale via=canale azione=place mode=live ordine=o1 decisione_ms=na "
        "ricezione_ms=4 presa_ms=1 place_ms=1 risposta_ms=30 abbinato_ms=na interno_ms=2 "
        "risposta_bf_ms=na abbinato_fonte=na orologi=na esito=ok rif=mike-t1")
    t = M.REGISTRO.fotografa_e_azzera()["tratti"]
    assert t["invio_presa_ms.mike.canale.live"]["n"] == 1
    assert t["place_risposta_ms.mike.canale.live"]["max"] == 30.0
    assert "decisione_invio_ms.mike.canale.live" not in t
    assert not [k for k in t if k.startswith("decisione_risposta_ms.")]


def test_clic_valori_esatti_ricevuto_diverso_da_adesso(monkeypatch, monitor_acceso):
    import time as _t

    monkeypatch.setattr(M, "time", SimpleNamespace(time=lambda: 2_000.0, perf_counter=_t.perf_counter,
                                                   monotonic=_t.monotonic))
    M.drenate([SimpleNamespace(method="order", ricevuto_ms=1_999_990,
                               params={"mode": "live", "emesso_ms": 1_999_950})])
    t = M.REGISTRO.fotografa_e_azzera()["tratti"]
    assert t["clic_canale_ms.live"]["min"] == t["clic_canale_ms.live"]["max"] == 40.0
    assert t["clic_presa_ms.live"]["min"] == t["clic_presa_ms.live"]["max"] == 50.0
    assert t["canale_coda_ms"]["max"] == 10.0
