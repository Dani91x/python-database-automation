"""W1-G2 - il client cloud unico (``Betfair/nucleo/dati/cloud.py``) sul client Supabase VERO.

Modello: ``test_catchup_rete_2026_10_08.py``. Il client e' il vero supabase/postgrest/httpx con un
``httpx.MockTransport`` al posto della rete: gli errori nascono dal codice vero (APIError costruita
da postgrest sulla risposta, eccezioni httpx sollevate dal trasporto). Corpi VERI di PostgREST e
la pagina VERA di Cloudflare del run 37743110569 (presi da quel test, non riscritti).

PARITA': stessa classificazione dei guasti di ``db_client.py`` e stesso numero di tentativi di
``db_client.esegui_con_retry`` su una griglia di risposte (5xx, HTML, PGRST, 4xx, 57014, timeout,
connessione chiusa). REGOLE: si ritenta solo cio' che e' idempotente; mai insert, mai 4xx, mai 57014.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

import httpx
import pytest
import supabase
from postgrest.exceptions import APIError
from supabase import ClientOptions

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import db_client  # noqa: E402
from Betfair.nucleo.dati import cloud as C  # noqa: E402

# pagina VERA del run 37743110569 e corpi VERI di PostgREST (test_catchup_rete_2026_10_08.py:44-62)
HTML_520 = (b'<!DOCTYPE html>\n<!--[if lt IE 7]> <html class="no-js ie6 oldie" lang="en-US"> <![endif]-->\n'
            b'<head>\n\n<title>supabase.co | 520: Web server is returning an unknown error</title>\n'
            b'<meta charset="UTF-8" />\n</head>\n<body>\n</body>\n</html>')
GOAWAY = "<ConnectionTerminated error_code:0, last_stream_id:19999, additional_data:None>"
CORPO_57014 = {"code": "57014", "details": None, "hint": None,
               "message": "canceling statement due to statement timeout"}
CORPO_PGRST002 = {"code": "PGRST002", "details": None, "hint": None,
                  "message": "Could not query the database for the schema cache. Retrying."}
CORPO_PGRST202 = {"code": "PGRST202", "details": "Searched for the function public.x", "hint": None,
                  "message": "Could not find the function public.x in the schema cache"}
CORPO_23505 = {"code": "23505", "details": "Key (id)=(1) already exists.", "hint": None,
               "message": "duplicate key value violates unique constraint"}
CORPO_42501 = {"code": "42501", "details": None, "hint": None, "message": "permission denied for table x"}
CORPO_53100 = {"code": "53100", "details": None, "hint": None,
               "message": "could not extend file: No space left on device"}
CORPO_08006 = {"code": "08006", "details": None, "hint": None, "message": "connection failure"}


def html_520(_req: httpx.Request) -> httpx.Response:
    return httpx.Response(520, content=HTML_520, headers={"content-type": "text/html; charset=UTF-8"})


def risposta_504(_req: httpx.Request) -> httpx.Response:
    return httpx.Response(504, content=b"upstream request timeout", headers={"content-type": "text/plain"})


def goaway(req: httpx.Request) -> httpx.Response:
    raise httpx.RemoteProtocolError(GOAWAY, request=req)


def read_timeout(req: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("The read operation timed out", request=req)


def connect_error(req: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("[Errno 111] Connection refused", request=req)


def json_errore(stato: int, corpo: Dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _req: httpx.Response(stato, json=corpo)


#: la griglia: nome -> (azione, classe attesa da db_client: None = NON ritentabile)
GRIGLIA: Dict[str, Tuple[Callable[[httpx.Request], httpx.Response], Optional[str]]] = {
    "520_html_cloudflare": (html_520, "gateway"),
    "503_PGRST002": (json_errore(503, CORPO_PGRST002), "gateway"),
    "504_testo": (risposta_504, "gateway"),
    "500_08006": (json_errore(500, CORPO_08006), "gateway"),
    "goaway_connessione_chiusa": (goaway, "connessione_terminata"),
    "read_timeout": (read_timeout, "timeout_rete"),
    "connect_error": (connect_error, "connessione"),
    "500_57014_statement_timeout": (json_errore(500, CORPO_57014), None),
    "404_PGRST202": (json_errore(404, CORPO_PGRST202), None),
    "409_23505": (json_errore(409, CORPO_23505), None),
    "403_42501": (json_errore(403, CORPO_42501), None),
    "507_53100_disco_pieno": (json_errore(507, CORPO_53100), None),
}


class PostgrestFinto:
    """PostgREST finto DIETRO il client vero: ``copione[(metodo, rotta)]`` = azioni nell'ordine
    (una per richiesta, ``None`` = risposta normale); ``sempre[(metodo, rotta)]`` = azione fissa."""

    def __init__(self) -> None:
        self.richieste: List[Tuple[int, str, str, str]] = []      # (client n., metodo, rotta, query)
        self.corpi: List[Any] = []
        self.copione: Dict[Tuple[str, str], List[Optional[Callable[[httpx.Request], Any]]]] = {}
        self.sempre: Dict[Tuple[str, str], Callable[[httpx.Request], Any]] = {}
        self.righe: Dict[str, List[Dict[str, Any]]] = {"x": [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]}
        self.rpc: Dict[str, Any] = {"get_omega_ht_ft": [{"league_id": 0, "ht": "0-0", "ft": "1-0", "n": 10}]}

    def trasporto(self, n: int) -> httpx.MockTransport:
        return httpx.MockTransport(lambda req: self.gestisci(n, req))

    def gestisci(self, n: int, req: httpx.Request) -> httpx.Response:
        rotta = req.url.path.replace("/rest/v1", "")
        self.richieste.append((n, req.method, rotta, req.url.query.decode()))
        self.corpi.append(json.loads(req.content) if req.content else None)
        if (req.method, rotta) in self.sempre:
            return self.sempre[(req.method, rotta)](req)
        azioni = self.copione.get((req.method, rotta))
        if azioni:
            azione = azioni.pop(0)
            r = azione(req) if azione is not None else None
            if r is not None:
                return r
        if rotta.startswith("/rpc/"):
            return httpx.Response(200, json=self.rpc.get(rotta[5:], []))
        tabella = rotta.strip("/")
        if req.method == "GET":
            return httpx.Response(200, json=self.righe.get(tabella, []))
        corpo = json.loads(req.content or b"null")
        return httpx.Response(201 if req.method == "POST" else 200,
                              json=corpo if isinstance(corpo, list) else [corpo] if corpo else [])

    def conta(self, metodo: str, rotta: str) -> int:
        return sum(1 for r in self.richieste if r[1] == metodo and r[2] == rotta)


@pytest.fixture
def server(monkeypatch):
    """Ogni client creato da ``db_client.get_supabase_client`` e' un client supabase VERO su un
    trasporto finto numerato; le opzioni passate a ``create_client`` sono registrate."""
    srv = PostgrestFinto()
    creati: List[Any] = []
    opzioni: List[Any] = []

    def crea(_url: str, _key: str, options: Any = None) -> Any:
        opzioni.append(options)
        c = supabase.create_client("https://abc.supabase.co", "x" * 40,
                                   options=ClientOptions(httpx_client=httpx.Client(transport=srv.trasporto(len(creati)))))
        creati.append(c)
        return c
    monkeypatch.setattr(db_client, "create_client", crea)
    # niente monkeypatch su _TLS: lo ripristina gia' Betfair/conftest.py (stato di processo di db_client)
    db_client._TLS.client = None
    srv.creati = creati  # type: ignore[attr-defined]
    srv.opzioni = opzioni  # type: ignore[attr-defined]
    return srv


@pytest.fixture(autouse=True)
def stato_rete_pulito(monkeypatch):
    """Lo stato di rete di db_client e' di processo: pulito prima e dopo; nessuna attesa vera."""
    sonni: List[float] = []
    monkeypatch.setattr(db_client._time, "sleep", sonni.append)
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0})
    db_client.STATISTICHE_RETE["per_classe"].clear()
    monkeypatch.setitem(db_client._STATO, "timeout", None)
    yield sonni
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0})
    db_client._TLS.client = None


def _cliente(profilo: C.Profilo = "bot", sonni: Optional[List[float]] = None, **kw: Any) -> C.ClienteCloud:
    return C.ClienteCloud(profilo, dormi=(sonni.append if sonni is not None else (lambda _s: None)),
                          casuale=lambda: 0.5, **kw)


def _esito(chiamata: Callable[[], Any]) -> Tuple[str, Optional[str]]:
    """('ok'|'guasto'|'errore', classe o codice)."""
    db_client._STATO_RETE["guasti_di_fila"] = 0
    try:
        chiamata()
    except db_client.GuastoRete as e:
        return "guasto", e.classe
    except APIError as e:
        return "errore", str(e.code)
    except httpx.HTTPError as e:
        return "errore", type(e).__name__
    return "ok", None


# ---------------------------------------------------------------------------
# 1. PARITA' con db_client sulla griglia (classificazione e numero di tentativi)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("caso", sorted(GRIGLIA))
def test_parita_con_db_client_sulla_griglia(server, caso):
    azione, classe_attesa = GRIGLIA[caso]
    server.sempre[("GET", "/x")] = azione
    vecchio = _esito(lambda: db_client.esegui_con_retry(lambda c: c.table("x").select("*"),
                                                        etichetta="x", dormi=lambda _s: None,
                                                        casuale=lambda: 0.5))
    n_vecchio = server.conta("GET", "/x")
    nuovo = _esito(lambda: _cliente("catena").leggi("x", {}))
    n_nuovo = server.conta("GET", "/x") - n_vecchio
    assert nuovo == vecchio, (caso, vecchio, nuovo)
    assert n_nuovo == n_vecchio, (caso, n_vecchio, n_nuovo)
    if classe_attesa is None:
        assert n_nuovo == 1 and nuovo[0] == "errore", caso
    else:
        assert nuovo == ("guasto", classe_attesa)
        assert n_nuovo == 1 + len(db_client.ATTESE_RETE_S)


@pytest.mark.parametrize("caso", sorted(GRIGLIA))
def test_profilo_bot_ritenta_solo_i_transitori(server, caso):
    azione, classe_attesa = GRIGLIA[caso]
    server.sempre[("GET", "/x")] = azione
    sonni: List[float] = []
    esito = _esito(lambda: _cliente("bot", sonni).leggi("x", {"id": 1}))
    if classe_attesa is None:
        assert server.conta("GET", "/x") == 1 and sonni == [], caso            # mai 4xx, mai 57014
    else:
        assert esito == ("guasto", classe_attesa)
        assert server.conta("GET", "/x") == 3 and sonni == [0.15, 0.30], caso   # 0,15 e 0,30 s


def test_57014_e_4xx_mai_ritentati_neanche_negli_upsert(server):
    for azione in (json_errore(500, CORPO_57014), json_errore(409, CORPO_23505), json_errore(400, {
            "code": "22P02", "details": None, "hint": None, "message": "invalid input syntax for type bigint"})):
        server.richieste.clear()
        server.sempre[("POST", "/x")] = azione
        with pytest.raises(APIError):
            _cliente().scrivi("x", "upsert", [{"id": 1}], on_conflict="id")
        assert server.conta("POST", "/x") == 1


def test_transitorio_poi_successo_e_client_nuovo_dopo_goaway(server):
    server.copione[("GET", "/x")] = [goaway]
    righe = _cliente().leggi("x", {})
    assert righe == server.righe["x"]
    assert [r[0] for r in server.richieste] == [0, 1]                 # 2o tentativo da un client NUOVO
    assert db_client.STATISTICHE_RETE["per_classe"]["connessione_terminata"] == 1


# ---------------------------------------------------------------------------
# 2. Solo l'idempotente si ritenta
# ---------------------------------------------------------------------------
def test_insert_di_log_mai_ritentata(server):
    """L'insert su una tabella di log senza uid (mike_activity) NON si ritenta: un 520 (esito
    ambiguo: la riga potrebbe essere gia' scritta) risale com'e' dopo UNA richiesta."""
    server.copione[("POST", "/mike_activity")] = [html_520, None]
    with pytest.raises(APIError) as info:
        _cliente().scrivi("mike_activity", "insert", {"kind": "x", "message": "m"})
    assert info.value.code == 520 or str(info.value.code) == "520"
    assert server.conta("POST", "/mike_activity") == 1


def test_upsert_ritentato_patch_e_delete_no(server):
    server.copione[("POST", "/live_ladder")] = [html_520, None]
    out = _cliente().scrivi("live_ladder", "upsert", [{"event_id": "1", "market_id": "1.2"}],
                            on_conflict="event_id,market_id")
    assert out == [{"event_id": "1", "market_id": "1.2"}]
    assert server.conta("POST", "/live_ladder") == 2
    prefer = [r for r in server.richieste if r[2] == "/live_ladder"]
    assert parse_qs(prefer[0][3])["on_conflict"] == ["event_id,market_id"]
    for op, metodo in (("patch", "PATCH"), ("delete", "DELETE")):
        server.copione[(metodo, "/mike_control")] = [html_520, None]
        with pytest.raises(APIError):
            _cliente().scrivi("mike_control", op, {"status": "x"} if op == "patch" else None, filtri={"id": 1})
        assert server.conta(metodo, "/mike_control") == 1
    with pytest.raises(ValueError, match="senza filtri"):
        _cliente().scrivi("mike_control", "delete", None)


def test_rpc_di_lettura_ritentate_scriventi_mai(server):
    server.copione[("POST", "/rpc/get_omega_ht_ft")] = [html_520]
    assert _cliente().rpc("get_omega_ht_ft", {"p_league_id": 39}) == server.rpc["get_omega_ht_ft"]
    assert server.conta("POST", "/rpc/get_omega_ht_ft") == 2
    for nome in ("mike_activate", "request_betfair_live_order", "record_fixture_detail_checks",
                 "funzione_sconosciuta"):
        server.copione[("POST", f"/rpc/{nome}")] = [html_520, None]
        with pytest.raises(APIError):
            _cliente().rpc(nome, {})
        assert server.conta("POST", f"/rpc/{nome}") == 1, nome
    c = _cliente()
    assert c.rpc_ritentabile("get_live_settings") and c.rpc_ritentabile("season_gaps_summary")
    assert not c.rpc_ritentabile("set_live_kill_switch") and not c.rpc_ritentabile("omega_request")
    with pytest.raises(ValueError, match="cache_s"):
        c.rpc("mike_stop", {}, cache_s=10)


# ---------------------------------------------------------------------------
# 3. Cache per lettura
# ---------------------------------------------------------------------------
def test_cache_per_lettura_scade_e_non_tiene_gli_errori(server):
    adesso = [1000.0]
    c = _cliente(orologio=lambda: adesso[0])
    a = c.leggi("x", {"id": [1, 2]}, cache_s=30)
    a[0]["v"] = "MANOMESSO"                                   # la copia restituita non tocca la cache
    b = c.leggi("x", {"id": [2, 1]}, cache_s=30)              # filtri diversi -> chiave diversa
    assert server.conta("GET", "/x") == 2
    assert c.leggi("x", {"id": [1, 2]}, cache_s=30)[0]["v"] == "a"
    assert server.conta("GET", "/x") == 2 and c.statistiche()["colpi_cache"] == 1
    adesso[0] += 30.0                                          # scaduta
    c.leggi("x", {"id": [1, 2]}, cache_s=30)
    assert server.conta("GET", "/x") == 3
    server.sempre[("GET", "/x")] = json_errore(404, CORPO_PGRST202)
    for _ in range(2):                                         # l'errore non va in cache
        with pytest.raises(APIError):
            c.leggi("x", {"v": "z"}, cache_s=30)
    assert server.conta("GET", "/x") == 5
    del server.sempre[("GET", "/x")]
    assert c.rpc("get_omega_ht_ft", {"p_league_id": 1}, cache_s=60) == c.rpc("get_omega_ht_ft", {"p_league_id": 1},
                                                                             cache_s=60)
    assert server.conta("POST", "/rpc/get_omega_ht_ft") == 1
    assert b is not a


def test_filtri_tradotti_in_query_postgrest(server):
    _cliente().leggi("x", {"select": "id,v", "event_id": ["a", "b"], "fixture_id": 7, "chiuso": None,
                           "fixture_date__gte": "2026-10-09", "order": "built_at.desc", "limit": 1})
    q = parse_qs(server.richieste[-1][3])
    assert q["select"] == ["id,v"] and q["event_id"] == ["in.(a,b)"]
    assert q["fixture_id"] == ["eq.7"] and q["chiuso"] == ["is.null"] and q["fixture_date"] == ["gte.2026-10-09"]
    assert q["order"] == ["built_at.desc"] and q["limit"] == ["1"]
    with pytest.raises(ValueError, match="operatore"):
        _cliente().leggi("x", {"id__contiene": 1})


# ---------------------------------------------------------------------------
# 4. Timeout per profilo e interruttore
# ---------------------------------------------------------------------------
def test_timeout_per_profilo(server, monkeypatch):
    assert C.ClienteCloud("runner").attiva_profilo() is None
    _cliente("runner").leggi("x", {})
    assert server.opzioni[-1] is None                                    # 120 s di libreria, come oggi
    t = C.ClienteCloud("bot").attiva_profilo()
    assert (t.connect, t.read) == (db_client.BOT_CONNECT_S, db_client.BOT_LETTURA_S)
    _cliente("bot").leggi("x", {})                                      # client RICREATO col timeout
    assert server.opzioni[-1].postgrest_client_timeout is t
    assert C.politica("catena").attese_s == tuple(db_client.ATTESE_RETE_S)
    with pytest.raises(ValueError):
        C.politica("altro")  # type: ignore[arg-type]
    monkeypatch.delenv(C.ENV_INTERRUTTORE, raising=False)
    assert C.interruttore_client() == "vecchio"
    monkeypatch.setenv(C.ENV_INTERRUTTORE, "nuovo")
    assert C.interruttore_client() == "nuovo"
    monkeypatch.setenv(C.ENV_INTERRUTTORE, "boh")
    assert C.interruttore_client() == "vecchio"


def test_import_senza_file_socket_thread():
    """Importare il comparto non importa db_client (che legge .env), non apre thread."""
    codice = ("import sys, threading; import Betfair.nucleo.dati.cloud, Betfair.nucleo.dati.registro, "
              "Betfair.nucleo.dati.cache_cloud; "
              "print(int('db_client' in sys.modules), int('config' in sys.modules), "
              "int('supabase' in sys.modules), threading.active_count())")
    out = subprocess.run([sys.executable, "-c", codice], capture_output=True, text=True, timeout=120,
                         cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
                             os.path.dirname(os.path.abspath(__file__)))))))
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["0", "0", "0", "1"]
