"""FIX-C (26/09/2026) - PROVA D'INSIEME "rete giu' 60 s, poi su" (finti, nessuna rete).

Cosa si mette insieme, con il codice di PRODUZIONE:
  * lo SCANNER vero (``safe_strategy.service.Scanner.tick`` + ``publish_status``)
    con un pool stream finto che smette di consegnare quando cade la rete e un
    client Betfair finto (.it) a cui la keepAlive cade proprio durante la caduta;
  * il loop del bot SAFE (``bot_service._control_per_il_giro``): Supabase giu'
    per 60 s, il giro deve proseguire in protezione con l'ultimo control noto;
  * il percorso d'ordine LIVE REST comune a Omega/Mike/Safe
    (``omega_market.place_order_live`` -> ``call_mutating``) contro un exchange
    finto: al rientro la sessione e' scaduta e il PRIMO ordine non deve fallire
    ne' partire due volte.

Si verifica: nessuna eccezione non gestita, un avviso di ripiego e uno di
rientro (non di piu'), la fonte tornata a ``stream``, la sessione del feed
valida, un solo ordine sull'exchange.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
import requests
from betfairlightweight.exceptions import APIError, KeepAliveError

from Betfair.safe_strategy import bot_service as BS
from Betfair.safe_strategy import service


class Rete:
    def __init__(self) -> None:
        self.t = 0.0
        self.giu = False


class ClientFeedFinto:
    """Client betfairlightweight del FEED (scanner): vita sessione ridotta a
    200 s, cosi' senza il fix la sessione scade dentro la prova."""

    def __init__(self, rete: Rete, vita: float = 200.0) -> None:
        self.rete = rete
        self.session_timeout = vita
        self.session_token = "FEED-1"
        self._rinnovata = rete.t
        self.chiamate: List[str] = []

    def valida(self) -> bool:
        return self.rete.t - self._rinnovata < self.session_timeout

    def keep_alive(self):
        self.chiamate.append("keep_alive")
        if self.rete.giu:
            raise APIError(None, exception=requests.ConnectionError(
                "NameResolutionError: [Errno 11001] getaddrinfo failed"))
        if not self.valida():
            raise KeepAliveError({"status": "FAIL", "error": "NO_SESSION"})
        self._rinnovata = self.rete.t

    def login(self):
        self.chiamate.append("login")
        if self.rete.giu:
            raise APIError(None, exception=requests.ConnectionError("getaddrinfo failed"))
        self.session_token = "FEED-2"
        self._rinnovata = self.rete.t


class PoolFinto:
    """Il pool stream: consegna solo a rete su (e 5 s dopo il rientro, il
    tempo di riconnettersi)."""

    capacity = 720

    def __init__(self, rete: Rete) -> None:
        self.rete = rete
        self.giu_fino = -1.0

    def _serve(self) -> bool:
        if self.rete.giu:
            self.giu_fino = self.rete.t
            return False
        return self.rete.t - self.giu_fino > 5.0

    def set_markets(self, ids): pass
    def drain(self): return []
    def covered_ids(self): return set()
    def subscribed_ids(self): return set()
    def serving(self): return self._serve()
    def healthy(self): return self._serve()
    def active_connections(self): return 1 if self._serve() else 0
    def stato_shard(self): return []
    def stop(self): pass


class ExchangeFinto:
    """``Betfair.client.BetfairClient`` finto (stesse porte usate da
    ``omega_market``): errori con il TESTO che produce ``BetfairClient._rpc``."""

    ordini: List[Dict[str, Any]] = []
    login_fatti = 0
    rete: Rete = None  # type: ignore[assignment]
    vita = 200.0
    rinnovata = 0.0

    def __init__(self) -> None:
        self._session_token = None

    def login_cert(self, max_retries: int = 3):
        if ExchangeFinto.rete.giu:
            raise RuntimeError("Login Betfair cert fallito dopo 3 tentativi. Ultimo errore: "
                               "Network error: getaddrinfo failed")
        ExchangeFinto.login_fatti += 1
        ExchangeFinto.rinnovata = ExchangeFinto.rete.t
        self._session_token = f"OMEGA-{ExchangeFinto.login_fatti}"

    def place_orders(self, market_id, instructions, customer_ref=None,
                     customer_strategy_ref=None, market_version=None, max_retries=2):
        if ExchangeFinto.rete.giu:
            raise RuntimeError("Betting RPC failed after 2 retries. Last error: "
                               "Network error: getaddrinfo failed")
        if ExchangeFinto.rete.t - ExchangeFinto.rinnovata >= ExchangeFinto.vita:
            raise RuntimeError(
                "Betting RPC failed after 2 retries. Last error: RPC error: "
                "{'code': -32099, 'message': 'ANGX-0003', 'data': {'APINGException': "
                "{'errorCode': 'INVALID_SESSION_INFORMATION'}}}")
        ins = instructions[0]
        ExchangeFinto.ordini.append({"market_id": market_id, "customer_ref": customer_ref,
                                     "ref_ordine": ins.get("customerOrderRef")})
        return {"status": "SUCCESS", "instructionReports": [{
            "status": "SUCCESS", "orderStatus": "EXECUTION_COMPLETE",
            "sizeMatched": ins["limitOrder"]["size"],
            "averagePriceMatched": ins["limitOrder"]["price"], "betId": "B1"}]}


class DbSafeFinto:
    """``safe_strategy.bot_db`` ridotto alla lettura del control."""

    def __init__(self, rete: Rete) -> None:
        self.rete = rete

    def read_control(self):
        if self.rete.giu:
            raise requests.ConnectionError("getaddrinfo failed")
        return {"status": "running", "mode": "paper", "params": {"poll_interval_s": 2}}


@pytest.fixture
def exchange(monkeypatch):
    from Betfair import client as bf_client
    from Betfair import odds_refresh

    monkeypatch.setattr(bf_client, "BetfairClient", ExchangeFinto)
    monkeypatch.setattr(odds_refresh, "_client", None)
    ExchangeFinto.ordini = []
    ExchangeFinto.login_fatti = 0
    yield ExchangeFinto
    odds_refresh._client = None


def test_rete_giu_60s_poi_su_tutto_torna_da_solo(monkeypatch, exchange):
    from Betfair.omega import omega_market

    rete = Rete()
    ExchangeFinto.rete = rete
    ExchangeFinto.rinnovata = 0.0
    monkeypatch.setattr(service.time, "monotonic", lambda: rete.t)
    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    # keepAlive del feed dovuto a t=150, cioe' DENTRO la caduta (120-180)
    monkeypatch.setattr(service, "_KEEPALIVE_PERIOD_SEC", 150.0)
    client = ClientFeedFinto(rete)
    scan = service.Scanner(api_client=client, dry=False, use_stream=False)
    scan.stream = PoolFinto(rete)
    for nome in ("refresh_catalogue", "poll_books", "poll_scores", "poll_timelines"):
        setattr(scan, nome, lambda *a, **k: None)
    scan.hydrate_schede = lambda now=None: 0            # type: ignore[method-assign]
    scan.hydrate_pre_ko = lambda: 0                     # type: ignore[method-assign]
    scan.publish = lambda now: (0, 0)                   # type: ignore[method-assign]
    scan._mike_followed = lambda now_mono=None: []      # type: ignore[method-assign]

    avvisi: List[str] = []

    def scrivi_avviso(level, code, msg):
        if rete.giu:
            raise requests.ConnectionError("getaddrinfo failed")
        avvisi.append(code)

    monkeypatch.setattr(service, "_scrivi_avviso", scrivi_avviso)
    stati: List[dict] = []

    def upsert_status(p):
        if rete.giu:
            raise requests.ConnectionError("getaddrinfo failed")
        stati.append(p)

    monkeypatch.setattr(service.scan_db, "upsert_status", upsert_status)

    db_safe = DbSafeFinto(rete)
    BS._LAST_CONTROL.clear()
    control_letti: List[str] = []
    risultati_ordine: List[Any] = []

    # ---- 10 minuti simulati, un secondo per passo ----
    while rete.t < 600.0:
        rete.t += 1.0
        rete.giu = 120.0 <= rete.t < 180.0
        if rete.t == 1.0:
            omega_market.get_client()                   # il servizio fa login all'avvio
        scan.tick()                                     # non deve sollevare
        if int(rete.t) % 10 == 0:
            try:
                scan.publish_status(0)
            except requests.ConnectionError:
                pass                                    # la scrittura dello stato a rete giu'
        if int(rete.t) % 2 == 0:
            ctrl = BS._control_per_il_giro(db_safe)     # il loop del bot Safe
            control_letti.append(str(ctrl.get("status")))
            if not rete.giu:
                BS._LAST_CONTROL["value"] = dict(ctrl)  # lo fa run_once a lettura riuscita
        if rete.t == 300.0:
            # il PRIMO ordine LIVE dopo il rientro: sessione Omega scaduta (vita 200 s)
            risultati_ordine.append(omega_market.place_order_live(
                market_id="1.262887882", selection_id=11, price=3.0, size=2.0,
                event_id="36111770", side="lay", customer_ref="omega-t4242"))
    BS._LAST_CONTROL.clear()

    # un avviso di ripiego e uno di rientro, non di piu'
    assert avvisi == ["FEED_RIPIEGO_REST", "FEED_RIENTRO_STREAM"], avvisi
    # la fonte e' tornata sullo stream e lo stato lo dice
    assert scan.last_source == "stream"
    assert stati[-1]["source"] == "stream" and stati[-1]["fonte"]["attuale"] == "stream"
    # la sessione del feed e' viva (senza il fix sarebbe scaduta a t=200)
    assert client.valida()
    assert stati[-1]["sessione"]["fallimenti"] == 0
    # il bot Safe ha girato anche a DB giu' (control noto, niente eccezioni)
    assert len(control_letti) == 300 and set(control_letti) == {"running"}
    # UN solo ordine sull'exchange, riuscito, con il ref deterministico
    assert len(ExchangeFinto.ordini) == 1
    assert ExchangeFinto.ordini[0]["ref_ordine"] == "omega-t4242"
    assert risultati_ordine and risultati_ordine[0].ok is True
    assert ExchangeFinto.login_fatti == 2               # login iniziale + rifatto


def test_safe_control_del_giro_senza_nulla_in_memoria_solleva():
    """A DB giu' dall'avvio non si inventa un control: l'errore sale come prima
    (il giro salta, e ``run_once`` non apre niente comunque)."""
    BS._LAST_CONTROL.clear()
    rete = Rete()
    rete.giu = True
    with pytest.raises(requests.ConnectionError):
        BS._control_per_il_giro(DbSafeFinto(rete))


def test_safe_control_del_giro_usa_l_ultimo_noto():
    rete = Rete()
    rete.giu = True
    BS._LAST_CONTROL.clear()
    BS._LAST_CONTROL["value"] = {"status": "running", "mode": "live", "params": {"x": 1}}
    try:
        ctrl = BS._control_per_il_giro(DbSafeFinto(rete))
        assert ctrl == {"status": "running", "mode": "live", "params": {"x": 1}}
        ctrl["status"] = "toccato"                      # e' una copia
        assert BS._LAST_CONTROL["value"]["status"] == "running"
    finally:
        BS._LAST_CONTROL.clear()


def test_riconciliazione_vede_gli_ordini_tennis_di_safe():
    """Esito IGNOTO di un place REST (timeout a rete giu'): la riconciliazione
    cerca l'ordine per customerOrderRef. Dal 25/09 il tennis scrive
    ``safe_tennis-t<id>`` (``porta_ordini.ref_ordine``), ma il filtro degli
    ordini di Safe teneva solo ``safe-``: l'ordine VERO spariva dalla lista e
    la riga finiva in ``reconcile_ordine_assente``."""
    from Betfair.safe_strategy import porta_ordini as PO

    righe = [  # la forma di ``omega_market.list_current_orders`` (omega_market.py:1398)
        {"bet_id": "1", "customer_order_ref": PO.ref_ordine(7, sport="tennis")},
        {"bet_id": "2", "customer_order_ref": PO.ref_ordine(8, sport="calcio")},
        {"bet_id": "3", "customer_order_ref": "omega-t9"},
        {"bet_id": "4", "customer_order_ref": None},
    ]
    tenuti = [r["bet_id"] for r in BS._solo_ordini_di_safe(righe)]
    assert tenuti == ["1", "2"]


def test_safe_main_legge_il_control_dal_ramo_protetto():
    import inspect

    src = inspect.getsource(BS.main)
    assert "_control_per_il_giro(_real_db)" in src
    assert "_real_db.read_control()" not in src
