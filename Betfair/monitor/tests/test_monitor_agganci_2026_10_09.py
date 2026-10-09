"""T0A "Salute" (09/10/2026): gli AGGANCI nei file di produzione.

Per ogni aggancio due prove sullo STESSO codice vero:
  * monitor SPENTO (di serie): comportamento identico - nessun campo in piu',
    nessun contatore, nessuna scrittura;
  * monitor ACCESO: la marca o il conteggio ci sono, e i dati dei bot (riga del
    DB del ladder, params della coda oltre ``emesso_ms``, righe del raw oltre
    ``rx``, riga del diario) restano identici.

Finti con le chiavi e i tipi del vero: client Supabase VERO (supabase-py) con il
trasporto httpx sostituito; APIClient VERO di betfairlightweight con l'adattatore
di requests sostituito; LiveSession e recorder VERI per il ladder; canale locale
VERO mai avviato; Diario VERO su cartella temporanea.
"""
from __future__ import annotations

import datetime as _dt
import json
import queue
from types import SimpleNamespace
from typing import Any, Dict, List

import httpx
import pytest
import requests

from Betfair.monitor import sonde as M

PT0 = 1_758_600_000_000


@pytest.fixture
def spento(monkeypatch):
    monkeypatch.setenv(M.ENV, "0")
    M.ferma()
    M.REGISTRO.azzera_tutto()
    yield M
    assert M.REGISTRO.fotografa_e_azzera()["contatori"] == {}, "monitor spento ma contatori scritti"


# ---------------------------------------------------------------------------
# raw_listener: ``rx`` nel raw registrato
# ---------------------------------------------------------------------------
def _scrivi_raw(tmp_path, nome):
    from Betfair.stream import raw_listener as RL

    st = RL._RawState()
    st.configure(str(tmp_path / nome), {"1.2": "ev1"}, True)
    msg = {"op": "mcm", "id": 1, "clk": "AAA", "pt": PT0, "mc": [{"id": "1.2", "rc": [{"id": 7, "atb": [[2.0, 5]]}]}]}
    st.write_message(json.dumps(msg))
    st.close()
    return (tmp_path / nome / "ev1" / "ev1.raw.jsonl").read_text(encoding="utf-8").splitlines()


def test_raw_spento_identico_acceso_solo_rx_in_piu(tmp_path, monkeypatch, spento):
    righe_spento = _scrivi_raw(tmp_path, "a")
    assert len(righe_spento) == 1 and "rx" not in json.loads(righe_spento[0])
    monkeypatch.setattr(M, "ATTIVO", True)
    righe_acceso = _scrivi_raw(tmp_path, "b")
    monkeypatch.setattr(M, "ATTIVO", False)
    d = json.loads(righe_acceso[0])
    assert isinstance(d.pop("rx"), int)
    assert d == json.loads(righe_spento[0])                     # tutto il resto identico


def test_listener_calcio_scanner_tennis_contano(monitor_acceso):
    from Betfair.safe_strategy import stream as SS
    from Betfair.stream import raw_listener as RL
    from Betfair.stream.tennis_live import tennis_recorder as TR

    stato = '{"op":"status","id":1,"statusCode":"SUCCESS","connectionClosed":false,"connectionsAvailable":%d}'
    RL.RawTeeStreamListener(output_queue=queue.Queue(), max_latency=None).on_data(stato % 3)
    SS._HealthListener(queue.Queue(), lambda: None).listener.on_data(stato % 0)
    TR._TennisRecListener(output_queue=queue.Queue(), max_latency=None).on_data(stato % 1)
    v = M.REGISTRO.fotografa_e_azzera()["valori"]["connessioni_disponibili"]
    assert v == {"calcio": 3, "scanner": 0, "tennis": 1}


def test_listener_spenti_non_contano(spento):
    from Betfair.safe_strategy import stream as SS
    from Betfair.stream import raw_listener as RL
    from Betfair.stream.tennis_live import tennis_recorder as TR

    stato = '{"op":"status","id":1,"statusCode":"SUCCESS","connectionClosed":false,"connectionsAvailable":2}'
    RL.RawTeeStreamListener(output_queue=queue.Queue(), max_latency=None).on_data(stato)
    SS._HealthListener(queue.Queue(), lambda: None).listener.on_data(stato)
    TR._TennisRecListener(output_queue=queue.Queue(), max_latency=None).on_data(stato)


# ---------------------------------------------------------------------------
# runner: ladder sul canale con ts_pub_ms/pt, riga del DB identica
# ---------------------------------------------------------------------------
def _market_book(pt: int, size_back: float) -> Any:
    from betfairlightweight.resources.bettingresources import PriceSize

    runners = [SimpleNamespace(
        selection_id=sel, handicap=0.0, status="ACTIVE", last_price_traded=2.0, total_matched=100.0,
        ex=SimpleNamespace(available_to_back=[PriceSize(2.0, size_back)],
                           available_to_lay=[PriceSize(2.02, 40.0)],
                           traded_volume=[PriceSize(2.0, 80.0)]))
        for sel in (11, 12)]
    return SimpleNamespace(market_id="1.900", publish_time_epoch=pt, inplay=True, status="OPEN",
                           total_matched=200.0, runners=runners,
                           market_definition=SimpleNamespace(market_type="MATCH_ODDS", in_play=True,
                                                             bet_delay=5))


def _giro_ladder(tmp_path, monkeypatch):
    from betfairlightweight.filters import streaming_market_data_filter, streaming_market_filter

    from Betfair.stream import ladder_canale, local_channel, runner
    from Betfair.stream.recorder import MarketRecorderStrategy

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
    rec.process_market_book(object(), _market_book(PT0, 50.0))
    runner.ladder_worker({}, None, sess)
    return pubblicati, db_rows


def test_ladder_spento_canale_e_db_identici(tmp_path, monkeypatch, spento):
    pubblicati, db_rows = _giro_ladder(tmp_path, monkeypatch)
    assert len(pubblicati) == 1 and len(db_rows) == 1
    assert "ts_pub_ms" not in pubblicati[0] and "pt" not in pubblicati[0]
    assert pubblicati[0] == db_rows[0]


def test_ladder_acceso_canale_marcato_db_pulito(tmp_path, monkeypatch, monitor_acceso):
    pubblicati, db_rows = _giro_ladder(tmp_path, monkeypatch)
    assert pubblicati[0]["pt"] == PT0 and pubblicati[0]["ts_pub_ms"] > PT0
    assert set(db_rows[0]) == {"event_id", "market_id", "market_type", "market_name", "status", "ladder"}
    assert {k: v for k, v in pubblicati[0].items() if k not in ("ts_pub_ms", "pt")} == db_rows[0]
    assert M.REGISTRO.fotografa_e_azzera()["tratti"]["ladder_pub_pt_ms"]["n"] == 1


# ---------------------------------------------------------------------------
# canale locale: ricevuto_ms e attesa in coda
# ---------------------------------------------------------------------------
def _canale():
    from Betfair.stream.local_channel import LocalChannel

    ch = LocalChannel(0, sport="calcio", solo_lettura=False, token="t", origini=[])
    ch._send = lambda ws, payload: None
    return ch


def test_canale_spento_ricevuto_zero(spento):
    ch = _canale()
    ch._on_message(object(), json.dumps({"id": 1, "m": "snapshot", "p": {}}))
    r = ch.pop_requests()
    assert len(r) == 1 and r[0].ricevuto_ms == 0 and r[0].method == "snapshot"


def test_canale_acceso_ricevuto_e_coda(monitor_acceso):
    ch = _canale()
    ch._on_message(object(), json.dumps({"id": 1, "m": "snapshot", "p": {"x": 1}}))
    r = ch.pop_requests()
    assert r[0].ricevuto_ms > PT0 and r[0].params == {"x": 1}
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["canale_richieste"] == {"snapshot": 1}
    assert f["tratti"]["canale_coda_ms"]["n"] == 1


# ---------------------------------------------------------------------------
# Omega e Safe: emesso_ms nei params della coda
# ---------------------------------------------------------------------------
class _DbBot:
    """Finto del db dei bot con i metodi e le firme usati dall'enqueue
    (``omega_db``/``safe_strategy.bot_db``: update_trade(id, **fields) - stessa
    firma del vero, R-6 della verifica del PC -,
    enqueue_live_order(payload) -> id, log(kind, payload), get_live_order_request_by_ref)."""

    def __init__(self) -> None:
        self.payload: List[Dict[str, Any]] = []

    def update_trade(self, trade_id: int, **fields: Any) -> None:
        pass

    def enqueue_live_order(self, payload: Dict[str, Any]) -> int:
        self.payload.append(json.loads(json.dumps(payload)))
        return 77

    def log(self, kind: str, payload: Dict[str, Any]) -> None:
        pass

    def get_live_order_request_by_ref(self, ref: str) -> None:
        return None


def _omega(db):
    from Betfair.omega import omega_service as OS

    return OS._flumine_enqueue_place(db=db, trade_id=5, event_id="35.1", market_id="1.2", selection_id=7,
                                     side="lay", price=3.0, size=2.0, base_meta={},
                                     now=_dt.datetime(2026, 10, 9, tzinfo=_dt.timezone.utc), mode="paper")


def _safe(db):
    from Betfair.safe_strategy import execution as X

    return X.enqueue_place(db=db, trade_id=6, client_ref="safe-t6", event_id="35.1", market_id="1.2",
                           selection_id=7, side="back", price=1.5, size=2.0, base_meta={},
                           now=_dt.datetime(2026, 10, 9, tzinfo=_dt.timezone.utc), mode="paper")


@pytest.mark.parametrize("chi,fonte", [(_omega, "omega"), (_safe, "safe")])
def test_params_spento_identici(chi, fonte, spento):
    db = _DbBot()
    assert chi(db) == 77
    assert db.payload[0]["params"] == {"source": fonte, "trade_id": 5 if fonte == "omega" else 6}


@pytest.mark.parametrize("chi,fonte", [(_omega, "omega"), (_safe, "safe")])
def test_params_acceso_emesso_ms_in_piu(chi, fonte, monitor_acceso):
    spento_db, acceso_db = _DbBot(), _DbBot()
    acceso_ms = M.ora_ms()
    chi(acceso_db)
    p = dict(acceso_db.payload[0]["params"])
    assert acceso_ms <= p.pop("emesso_ms") <= M.ora_ms()
    assert p == {"source": fonte, "trade_id": 5 if fonte == "omega" else 6}
    resto = {k: v for k, v in acceso_db.payload[0].items() if k != "params"}
    M.ATTIVO = False
    try:
        chi(spento_db)
    finally:
        M.ATTIVO = True
    assert resto == {k: v for k, v in spento_db.payload[0].items() if k != "params"}


def test_tempi_ordine_legge_emesso_ms():
    """La marca serve a F0: ``decisione_ms`` si calcola da ``emesso_ms``."""
    from Betfair.stream import tempi_ordine as TO

    assert "emesso_ms" in TO._CHIAVI_DECISIONE


# ---------------------------------------------------------------------------
# motore ordini: marca prima/dopo il fsync del diario
# ---------------------------------------------------------------------------
def _hook_diario(tmp_path):
    from Betfair.stream import motore_ordini as MO

    finto = SimpleNamespace(diario=MO.Diario(str(tmp_path), giorno=lambda: "2026-10-09"),
                            _ora_ms=lambda: 123)
    hook = MO.MotoreOrdini._pre_invio(finto, "ref-1")
    mercato = SimpleNamespace(market_id="1.2")
    ordine = SimpleNamespace(order_type=SimpleNamespace(price=2.0, size=3.0), selection_id=7, side="BACK",
                             customer_order_ref="cor", context={})
    hook(ordine, mercato, "place", None)
    return (tmp_path / "2026-10-09.jsonl").read_text(encoding="ascii")


def test_diario_spento_nessuna_misura(tmp_path, spento):
    riga = _hook_diario(tmp_path)
    assert json.loads(riga)["ref"] == "ref-1"


def test_diario_acceso_misura_e_riga_identica(tmp_path, monitor_acceso):
    riga = _hook_diario(tmp_path / "a")
    t = M.REGISTRO.fotografa_e_azzera()["tratti"]["diario_fsync_ms"]
    assert t["n"] == 1 and t["max"] >= 0
    M.ATTIVO = False
    try:
        assert _hook_diario(tmp_path / "b") == riga
    finally:
        M.ATTIVO = True


# ---------------------------------------------------------------------------
# client DB (supabase-py vero, trasporto httpx sostituito)
# ---------------------------------------------------------------------------
def _client_supabase():
    from supabase import create_client

    c = create_client("http://127.0.0.1:9", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")

    def _risposta(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/mike_control"):
            return httpx.Response(503, json={"code": "PGRST000"}, request=req)
        return httpx.Response(200, json=[{"a": 1}], request=req)

    c.postgrest.session._transport = httpx.MockTransport(_risposta)
    return c


def test_db_spento_nessun_gancio(spento):
    c = M.aggancia_client_db(_client_supabase())
    assert c.postgrest.session.event_hooks == {"request": [], "response": []}


def test_db_acceso_conta_per_tabella_e_errori(monitor_acceso):
    c = M.aggancia_client_db(_client_supabase())
    M.aggancia_client_db(c)                                   # idempotente
    assert len(c.postgrest.session.event_hooks["request"]) == 1
    c.table("mike_trades").select("*").eq("id", 1).execute()
    c.table("mike_trades").update({"x": 1}).eq("id", 1).execute()
    c.rpc("get_omega_ht_ft", {"p": 1}).execute()
    with pytest.raises(Exception):
        c.table("mike_control").select("*").execute()
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["db"] == {"GET mike_trades": 1, "PATCH mike_trades": 1,
                                    "POST rpc:get_omega_ht_ft": 1, "GET mike_control": 1}
    assert f["contatori"]["db_errori"] == {"503 GET mike_control": 1}
    assert f["tratti"]["db_ms"]["n"] == 4


def test_get_supabase_client_aggancia_solo_se_acceso(monkeypatch, monitor_acceso):
    import db_client

    monkeypatch.setattr(db_client, "create_client", lambda *a, **k: _client_supabase())
    monkeypatch.setattr(db_client._TLS, "client", None, raising=False)
    c = db_client.get_supabase_client()
    assert len(c.postgrest.session.event_hooks["request"]) == 1
    M.ATTIVO = False
    try:
        monkeypatch.setattr(db_client._TLS, "client", None, raising=False)
        c2 = db_client.get_supabase_client()
        assert c2.postgrest.session.event_hooks["request"] == []
    finally:
        M.ATTIVO = True


def test_tennis_client_aggancia_solo_se_acceso(monkeypatch, monitor_acceso):
    from Betfair.stream.tennis_live import tennis_db as TD

    monkeypatch.setattr(TD, "create_client", lambda *a, **k: _client_supabase())
    monkeypatch.setattr(TD._local, "client", None, raising=False)
    assert len(TD.get_tennis_client().postgrest.session.event_hooks["request"]) == 1
    M.ATTIVO = False
    try:
        monkeypatch.setattr(TD._local, "client", None, raising=False)
        assert TD.get_tennis_client().postgrest.session.event_hooks["request"] == []
    finally:
        M.ATTIVO = True


# ---------------------------------------------------------------------------
# client Betfair (APIClient vero, adattatore di requests sostituito)
# ---------------------------------------------------------------------------
class _Adattatore(requests.adapters.HTTPAdapter):
    def send(self, request, **kw):  # type: ignore[override]
        r = requests.Response()
        r.status_code = 200
        r.url = request.url
        r.request = request
        if "certlogin" in request.url:
            r._content = json.dumps({"loginStatus": "SUCCESS", "sessionToken": "tok"}).encode()
        elif "keepAlive" in request.url:
            r._content = json.dumps({"token": "tok", "status": "SUCCESS", "error": ""}).encode()
        else:
            r._content = json.dumps({"jsonrpc": "2.0", "result": [], "id": 1}).encode()
        r.headers["Content-Type"] = "application/json"
        return r


def _build_client(monkeypatch):
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
    c.betting.list_market_book(market_ids=["1.2"], lightweight=True)
    c.keep_alive()
    return c


def test_betfair_spento_nessun_gancio(monkeypatch, spento):
    c = _build_client(monkeypatch)
    assert c.session.hooks["response"] == []


def test_betfair_acceso_login_metodi_keepalive(monkeypatch, monitor_acceso):
    c = _build_client(monkeypatch)
    assert len(c.session.hooks["response"]) == 1
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["betfair_rest"] == {"certlogin": 1, "listMarketBook": 1, "keepAlive": 1}
    # ``elapsed`` lo misura requests (Session.send) attorno all'adattatore
    assert f["tratti"]["rest_ms.listMarketBook"]["n"] == 1
    assert f["tratti"]["rest_ms.listMarketBook"]["max"] >= 0.0
