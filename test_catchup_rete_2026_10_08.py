"""08/10/2026 - Seasons Catchup resiliente ai guasti di RETE/GATEWAY.

Run rosse reali (AUDIT_2026-10-08/action_catchup/REFERTO.md):
  - 37743110569 (08/10): POST /rest/v1/rpc/season_detail_gaps -> HTTP 520 con pagina HTML
    di Cloudflare, APIError code 520 'JSON could not be generated', traceback, exit 1;
  - 37049359939 (02/10) e 37141249749 (03/10): <ConnectionTerminated error_code:0,
    last_stream_id:19999> su insert/delete (connessione HTTP/2 chiusa dal server dopo
    10.000 richieste) -> partita 'parziale' -> BUCO VECCHIO 'errore API ripetuto' -> exit 1.

I finti qui NON sono finti di postgrest: il client e' il VERO client supabase/postgrest/httpx
del .venv, con un httpx.MockTransport al posto della rete. Gli errori nascono quindi dal
codice vero (APIError costruita da postgrest sulla risposta 520 HTML, httpx.RemoteProtocolError
sollevata dal trasporto come la solleva httpcore), con il corpo vero della pagina Cloudflare
(inizio e titolo copiati dal log del run 37743110569).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")
os.environ.setdefault("API_FOOTBALL_KEY", "x")

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import httpx  # noqa: E402
import pytest  # noqa: E402
import supabase  # noqa: E402
from postgrest.exceptions import APIError  # noqa: E402
from supabase import ClientOptions  # noqa: E402

import db_client  # noqa: E402
import per_fixture_backfill as pfb  # noqa: E402
import season_gaps as sg  # noqa: E402
import seasons_catchup as sc  # noqa: E402
import test_backfill_automatico_2026_09_25 as tba  # noqa: E402

# inizio e titolo VERI della pagina del run 37743110569 (il resto e' grafica di Cloudflare)
HTML_520 = (b'<!DOCTYPE html>\n<!--[if lt IE 7]> <html class="no-js ie6 oldie" lang="en-US"> <![endif]-->\n'
            b'<!--[if IE 7]>    <html class="no-js ie7 oldie" lang="en-US"> <![endif]-->\n'
            b'<!--[if IE 8]>    <html class="no-js ie8 oldie" lang="en-US"> <![endif]-->\n'
            b'<!--[if gt IE 8]><!--> <html class="no-js" lang="en-US"> <!--<![endif]-->\n<head>\n\n'
            b'<title>supabase.co | 520: Web server is returning an unknown error</title>\n'
            b'<meta charset="UTF-8" />\n</head>\n<body>\n</body>\n</html>')
# messaggio VERO di httpx quando httpcore riceve il GOAWAY (str dell'evento h2)
GOAWAY = "<ConnectionTerminated error_code:0, last_stream_id:19999, additional_data:None>"
# corpi VERI di PostgREST
CORPO_57014 = {"code": "57014", "details": None, "hint": None,
               "message": "canceling statement due to statement timeout"}
CORPO_PGRST202 = {"code": "PGRST202", "details": "Searched for the function public.season_detail_gaps with "
                  "parameters p_fixture_ids, p_league_id, p_season_year", "hint": None,
                  "message": "Could not find the function public.season_detail_gaps(p_fixture_ids, p_league_id, "
                             "p_season_year) in the schema cache"}
CORPO_23505 = {"code": "23505", "details": "Key (fixture_id, tabella)=(1, match_events) already exists.",
               "hint": None, "message": "duplicate key value violates unique constraint"}
CORPO_42501 = {"code": "42501", "details": None, "hint": None, "message": "permission denied for table matches"}


# ---------------------------------------------------------------------------
# PostgREST finto DIETRO il client vero
# ---------------------------------------------------------------------------
def html_520(_req: httpx.Request) -> httpx.Response:
    return httpx.Response(520, content=HTML_520, headers={"content-type": "text/html; charset=UTF-8"})


def goaway(req: httpx.Request) -> httpx.Response:
    raise httpx.RemoteProtocolError(GOAWAY, request=req)


def json_errore(stato: int, corpo: Dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _req: httpx.Response(stato, json=corpo)


class PostgrestFinto:
    """Risponde alle rotte che la catena usa. `copione[(metodo, rotta)]` = azioni da usare
    nell'ordine (una per richiesta) prima del comportamento normale."""

    def __init__(self) -> None:
        self.richieste: List[Tuple[int, str, str]] = []           # (client n., metodo, rotta)
        self.copione: Dict[Tuple[str, str], List[Callable[[httpx.Request], Any]]] = {}
        self.checks: Dict[Tuple[int, str], Dict[str, Any]] = {}
        self.righe: Dict[str, List[Dict[str, Any]]] = {"match_events": []}
        self.gaps: List[Dict[str, Any]] = [{"tabella": "_partite", "stato": "ft", "n": 3, "fixture_ids": None},
                                           {"tabella": "_partite", "stato": "tutte", "n": 3, "fixture_ids": None},
                                           {"tabella": "match_events", "stato": "da_chiamare", "n": 1,
                                            "fixture_ids": [11]}]

    def trasporto(self, n: int) -> httpx.MockTransport:
        return httpx.MockTransport(lambda req: self.gestisci(n, req))

    def gestisci(self, n: int, req: httpx.Request) -> httpx.Response:
        rotta = req.url.path.replace("/rest/v1", "")
        self.richieste.append((n, req.method, rotta))
        azioni = self.copione.get((req.method, rotta))
        if azioni:
            azione = azioni.pop(0)                                   # None = risposta normale
            r = azione(req) if azione is not None else None
            if r is not None:
                return r
        return self.normale(req, rotta)

    def applica(self, req: httpx.Request) -> None:
        """La richiesta ARRIVA al DB (effetto applicato), poi la risposta si perde."""
        self.normale(req, req.url.path.replace("/rest/v1", ""))

    def normale(self, req: httpx.Request, rotta: str) -> httpx.Response:
        q = {k: v[0] for k, v in parse_qs(req.url.query.decode()).items()}
        corpo = json.loads(req.content or b"null") if req.method in ("POST", "PATCH") else None
        if rotta == "/rpc/season_detail_gaps":
            return httpx.Response(200, json=self.gaps)
        if rotta == "/rpc/season_gaps_summary":
            out = [{"league_id": l, "season_year": s, "tabella": "_partite", "stato": "ft", "n": 5}
                   for l, s in zip(corpo["p_league_ids"], corpo["p_season_years"])]
            return httpx.Response(200, json=out)
        if rotta == "/rpc/record_fixture_detail_checks":
            adesso = datetime.now(timezone.utc).isoformat()
            for r in corpo["p_rows"]:
                k = (int(r["fixture_id"]), r["tabella"])
                if r["esito"] == "ok":
                    self.checks.pop(k, None)
                elif r["esito"] in ("vuoto", "errore", "parziale"):
                    c = self.checks.setdefault(k, {"fixture_id": k[0], "tabella": k[1], "vuoti": 0, "errori": 0})
                    c["esito"] = r["esito"]
                    c["vuoti"] += 1 if r["esito"] == "vuoto" else 0
                    c["errori"] += 1 if r["esito"] in ("errore", "parziale") else 0
                    c["ultimo_controllo_at"] = adesso
            return httpx.Response(200, json=len(corpo["p_rows"]))
        if rotta == "/fixture_detail_checks" and req.method == "GET":
            fid, tab = int(q["fixture_id"].split(".", 1)[1]), q["tabella"].split(".", 1)[1]
            riga = self.checks.get((fid, tab))
            return httpx.Response(200, json=[{"esito": riga["esito"],
                                              "ultimo_controllo_at": riga["ultimo_controllo_at"]}] if riga else [])
        tabella = rotta.strip("/")
        if tabella in self.righe:
            if req.method == "DELETE":
                fid = int(q["fixture_id"].split(".", 1)[1])
                via = [r for r in self.righe[tabella] if r["fixture_id"] == fid]
                self.righe[tabella] = [r for r in self.righe[tabella] if r["fixture_id"] != fid]
                return httpx.Response(200, json=via)
            if req.method == "POST":
                nuove = corpo if isinstance(corpo, list) else [corpo]
                self.righe[tabella].extend(nuove)
                return httpx.Response(201, json=nuove)
        return httpx.Response(200, json=[])


@pytest.fixture
def server(monkeypatch):
    """Ogni client creato da db_client.get_supabase_client e' un client supabase VERO su
    un trasporto finto numerato (per vedere quale client ha fatto ogni richiesta)."""
    srv = PostgrestFinto()
    creati: List[Any] = []

    def crea(_url: str, _key: str, options: Any = None) -> Any:
        n = len(creati)
        c = supabase.create_client("https://abc.supabase.co", "x" * 40,
                                   options=ClientOptions(httpx_client=httpx.Client(transport=srv.trasporto(n))))
        creati.append(c)
        return c
    monkeypatch.setattr(db_client, "create_client", crea)
    monkeypatch.setattr(db_client._TLS, "client", None, raising=False)
    srv.creati = creati  # type: ignore[attr-defined]
    return srv


@pytest.fixture(autouse=True)
def stato_rete_pulito(monkeypatch):
    """Lo stato di rete di db_client e' di processo: pulito prima e dopo ogni test
    (interruttore, statistiche, rinnovo) e nessuna attesa vera."""
    sonni: List[float] = []
    monkeypatch.setattr(db_client._time, "sleep", sonni.append)
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0})
    db_client.STATISTICHE_RETE.update({"ritentativi": 0, "riusciti_dopo_ritentativo": 0,
                                       "guasti_persistenti": 0, "rinnovi_client": 0})
    db_client.STATISTICHE_RETE["per_classe"].clear()
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    yield sonni
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0})
    db_client._TLS.client = None


# ---------------------------------------------------------------------------
# 1. Classificazione con le eccezioni VERE
# ---------------------------------------------------------------------------
def _errore_vero(server: PostgrestFinto, azione: Callable[[httpx.Request], Any]) -> BaseException:
    server.copione[("POST", "/rpc/season_detail_gaps")] = [azione]
    with pytest.raises(Exception) as info:
        db_client.get_supabase_client().rpc("season_detail_gaps", {"p_league_id": 0}).execute()
    return info.value


def test_classificazione_sulle_eccezioni_vere(server):
    e520 = _errore_vero(server, html_520)
    assert isinstance(e520, APIError) and e520.code == 520 and e520.message == "JSON could not be generated"
    assert db_client.classifica_guasto_rete(e520) == "gateway"
    assert "520: Web server is returning an unknown error" in db_client.descrivi_errore(e520)
    assert len(db_client.descrivi_errore(e520)) <= 300                  # niente 7.800 caratteri di HTML nel log
    eterm = _errore_vero(server, goaway)
    assert isinstance(eterm, httpx.RemoteProtocolError) and str(eterm) == GOAWAY
    assert db_client.classifica_guasto_rete(eterm) == "connessione_terminata"
    assert db_client.classifica_guasto_rete(_errore_vero(server, json_errore(503, {
        "code": "PGRST002", "details": None, "hint": None,
        "message": "Could not query the database for the schema cache. Retrying."}))) == "gateway"
    for stato, corpo in ((500, CORPO_57014), (404, CORPO_PGRST202), (409, CORPO_23505), (403, CORPO_42501),
                         (507, {"code": "53100", "details": None, "hint": None,
                                "message": "could not extend file: No space left on device"})):
        e = _errore_vero(server, json_errore(stato, corpo))
        assert isinstance(e, APIError)
        assert db_client.classifica_guasto_rete(e) is None, corpo["code"]
    req = httpx.Request("POST", "https://abc.supabase.co/rest/v1/rpc/x")
    assert db_client.classifica_guasto_rete(httpx.ReadTimeout("timed out", request=req)) == "timeout_rete"
    assert db_client.classifica_guasto_rete(httpx.ConnectError("[Errno -3]", request=req)) == "connessione"
    assert db_client.classifica_guasto_rete(ValueError("x")) is None


# ---------------------------------------------------------------------------
# 2. 520 HTML, poi successo (il caso di oggi: verifica_migrazione -> lacune_stagione)
# ---------------------------------------------------------------------------
def test_520_html_poi_successo_nessun_traceback(server, stato_rete_pulito):
    server.copione[("POST", "/rpc/season_detail_gaps")] = [html_520]
    lac = sg.lacune_stagione(db_client.ClientResiliente(), 135, 2026)
    assert lac.ft_totali == 3 and lac.da_chiamare_per_fixture({"events": True}) == {11: ["events"]}
    rpc = [r for r in server.richieste if r[2] == "/rpc/season_detail_gaps"]
    assert len(rpc) == 2                                                 # 1 fallita + 1 riuscita
    assert len(stato_rete_pulito) == 1 and 1.5 <= stato_rete_pulito[0] <= 2.5   # 2 s +-25%
    assert db_client.STATISTICHE_RETE["per_classe"]["gateway"] == 1
    assert db_client.STATISTICHE_RETE["riusciti_dopo_ritentativo"] == 1


def test_verifica_migrazione_regge_il_520(server):
    """Il punto esatto del traceback del run 37743110569 (season_gaps.py:369 -> :227)."""
    server.copione[("POST", "/rpc/season_detail_gaps")] = [html_520, html_520]
    sg.verifica_migrazione(db_client.ClientResiliente())
    assert [r[2] for r in server.richieste].count("/rpc/season_detail_gaps") == 3


# ---------------------------------------------------------------------------
# 3. ConnectionTerminated, poi successo con un client NUOVO
# ---------------------------------------------------------------------------
def test_connessione_terminata_ricrea_il_client(server):
    sb = db_client.get_supabase_client()                                # come lo tiene chi chiama
    server.copione[("POST", "/rpc/season_detail_gaps")] = [goaway]
    lac = sg.lacune_stagione(sb, 135, 2026)
    assert lac.ft_totali == 3
    rpc = [r for r in server.richieste if r[2] == "/rpc/season_detail_gaps"]
    assert [r[0] for r in rpc] == [0, 1]                               # 2o tentativo dal client n.1
    assert len(server.creati) == 2 and server.creati[1] is not server.creati[0]
    assert db_client.get_supabase_client() is server.creati[1]
    assert db_client.STATISTICHE_RETE["rinnovi_client"] == 1


def test_per_fixture_accessore_segue_il_client_nuovo(server):
    """per_fixture_backfill._supabase catturato all'import: dopo il rinnovo si usava ancora
    il client vecchio. Ora get_supabase() e' un accessore."""
    primo = pfb.get_supabase()
    db_client.rinnova_client()
    assert pfb.get_supabase() is not primo
    assert not hasattr(pfb, "_supabase")


def test_insert_dopo_goaway_unita_delete_insert_senza_doppioni(server, monkeypatch):
    """GOAWAY sull'insert DOPO che il DB l'ha applicato (last_stream_id = lo stream in volo):
    ripetere il solo insert raddoppierebbe le righe; l'unita' delete+insert no."""
    server.righe["match_events"] = [{"fixture_id": 11, "vecchia": True}]

    def applica_poi_goaway(req: httpx.Request) -> None:
        server.applica(req)
        raise httpx.RemoteProtocolError(GOAWAY, request=req)
    server.copione[("POST", "/match_events")] = [applica_poi_goaway]
    righe = [{"fixture_id": 11, "n": 1}, {"fixture_id": 11, "n": 2}]
    inserite, errori = pfb._sostituisci_righe("match_events", 11, righe)
    assert (inserite, errori) == (2, 0)
    assert server.righe["match_events"] == righe                         # niente vecchie, niente doppioni
    metodi = [(r[0], r[1]) for r in server.richieste if r[2] == "/match_events"]
    assert metodi == [(0, "DELETE"), (0, "POST"), (1, "DELETE"), (1, "POST")]


def test_registro_esiti_non_si_riapplica_se_era_arrivato(server):
    """record_fixture_detail_checks incrementa `vuoti`: due 'vuoto' = vuoto_definitivo.
    Se la RPC e' arrivata al DB e la risposta si e' persa, NON si riapplica."""
    def applica_poi_520(req: httpx.Request) -> httpx.Response:
        server.applica(req)
        return html_520(req)
    server.copione[("POST", "/rpc/record_fixture_detail_checks")] = [applica_poi_520]
    righe = [{"fixture_id": 11, "tabella": "match_events", "league_id": 135, "season_year": 2026, "esito": "vuoto"}]
    assert sg.registra_esiti(pfb.get_supabase(), righe, obbligatorio=True) is True
    assert server.checks[(11, "match_events")]["vuoti"] == 1
    assert [r[2] for r in server.richieste].count("/rpc/record_fixture_detail_checks") == 1


def test_registro_esiti_si_riapplica_se_non_era_arrivato(server):
    server.copione[("POST", "/rpc/record_fixture_detail_checks")] = [html_520]
    righe = [{"fixture_id": 11, "tabella": "match_events", "league_id": 135, "season_year": 2026, "esito": "vuoto"}]
    assert sg.registra_esiti(pfb.get_supabase(), righe, obbligatorio=True) is True
    assert server.checks[(11, "match_events")]["vuoti"] == 1
    assert [r[2] for r in server.richieste].count("/rpc/record_fixture_detail_checks") == 2


# ---------------------------------------------------------------------------
# 4. Tutti i tentativi falliti -> rinvio dichiarato, nessun traceback
# ---------------------------------------------------------------------------
def test_tutti_i_tentativi_falliti_guasto_rete_dopo_6_esecuzioni(server, stato_rete_pulito):
    server.copione[("POST", "/rpc/season_detail_gaps")] = [html_520] * 6
    with pytest.raises(db_client.GuastoRete) as info:
        sg.lacune_stagione(db_client.ClientResiliente(), 135, 2026)
    assert info.value.classe == "gateway" and info.value.tentativi == 6
    assert len([r for r in server.richieste if r[2] == "/rpc/season_detail_gaps"]) == 6
    attese = stato_rete_pulito
    assert len(attese) == 5
    for a, base in zip(attese, db_client.ATTESE_RETE_S):
        assert 0.75 * base <= a <= 1.25 * base
    assert "<!DOCTYPE" not in str(info.value)                           # messaggio corto


def test_riepilogo_lacune_blocco_in_guasto_diventa_rinviato(server):
    coppie = [(1, 2026), (2, 2026), (3, 2026)]
    server.copione[("POST", "/rpc/season_gaps_summary")] = [html_520] * 6
    rinviate: List[Tuple[int, int]] = []
    log: List[str] = []
    out, degradate = sg.riepilogo_lacune(db_client.ClientResiliente(), coppie, blocco=2, stampa=log.append,
                                         rinviate_rete=rinviate)
    assert rinviate == [(1, 2026), (2, 2026)] and degradate == []
    assert out[(3, 2026)].ft_totali == 5                                # il blocco dopo e' verificato
    assert any("RINVIATE" in r for r in log)


def test_interruttore_dopo_due_guasti_un_tentativo_solo(server, stato_rete_pulito):
    server.copione[("POST", "/rpc/season_gaps_summary")] = [html_520] * 13
    rinviate: List[Tuple[int, int]] = []
    sg.riepilogo_lacune(db_client.ClientResiliente(), [(1, 2026), (2, 2026), (3, 2026)], blocco=1,
                        stampa=lambda s: None, rinviate_rete=rinviate)
    assert rinviate == [(1, 2026), (2, 2026), (3, 2026)]
    # 6 + 6 esecuzioni per i primi due blocchi, poi interruttore aperto: 1 sola
    assert len([r for r in server.richieste if r[2] == "/rpc/season_gaps_summary"]) == 13
    assert len(stato_rete_pulito) == 10


def test_per_fixture_guasto_persistente_ferma_la_lega_stagione(server, monkeypatch):
    monkeypatch.setattr(pfb.time, "sleep", lambda s: None)
    api = tba.FintoServer()
    client = tba.FintoClient(api)
    server.copione[("POST", "/match_events")] = [goaway] * 6
    lac = sg.Lacune(135, 2026, partite_totali=2, ft_totali=2,
                    per_tabella={"match_events": {"da_chiamare": {11, 12}}})
    st = pfb.backfill_per_fixture_for_league_season(135, 2026, lacune=lac, coverage={"events": True},
                                                    client=client, registro_obbligatorio=True)
    assert st["fermato_per"] == db_client.MOTIVO_GUASTO_RETE
    assert st["fixtures_fatte"] == 1 and client.richieste_http == 1     # la 12 non si chiama: quota salva
    assert server.checks[(11, "match_events")]["esito"] == "parziale"   # esito vero registrato


def test_referto_rinvio_sotto_soglia_exit0_dichiarato(monkeypatch):
    ris = sc.Risultato()
    ris.considerate = 10
    ris.rinviate_rete = {(135, 2026): "verifica delle lacune (season_gaps_summary)"}
    ris.rinviate_rete_consecutivi = {(135, 2026): 1}
    righe: List[str] = []
    codice = sc.referto_buchi([], ris, tba_quota(), 3, {}, righe.append, date(2026, 10, 8))
    log = "\n".join(righe)
    assert codice == 0
    assert "RINVIATE PER GATEWAY/RETE: 1 lega-stagioni (10.0% delle 10 considerate, soglia 50%)" in log
    assert "RINVIATA PER GATEWAY/RETE: lega 135 stagione 2026" in log


def test_referto_rinvii_oltre_soglia_exit1():
    ris = sc.Risultato()
    ris.considerate = 3
    ris.rinviate_rete = {(1, 2026): "x", (2, 2026): "x"}
    righe: List[str] = []
    assert sc.referto_buchi([], ris, tba_quota(), 3, {}, righe.append, date(2026, 10, 8)) == 1
    assert "rinvii oltre la soglia (66.7% > 50%)" in "\n".join(righe)


def test_referto_rinvio_persistente_oltre_n_giorni_exit1():
    ris = sc.Risultato()
    ris.considerate = 100
    ris.rinviate_rete = {(1, 2026): "x"}
    ris.rinviate_rete_consecutivi = {(1, 2026): 4}
    righe: List[str] = []
    assert sc.referto_buchi([], ris, tba_quota(), 3, {}, righe.append, date(2026, 10, 8)) == 1
    assert "rinviata da 4 giorni consecutivi (> 3)" in "\n".join(righe)


def test_giorni_consecutivi_contano_giorni_non_run():
    oggi = date(2026, 10, 8)
    assert sg.giorni_consecutivi(None, oggi) == 1
    assert sg.giorni_consecutivi({"consecutivi": 2, "ultimo_at": "2026-10-08"}, oggi) == 2   # 2a run del giorno
    assert sg.giorni_consecutivi({"consecutivi": 2, "ultimo_at": "2026-10-07"}, oggi) == 3
    assert sg.giorni_consecutivi({"consecutivi": 5, "ultimo_at": "2026-10-05"}, oggi) == 1   # buco: si riparte


def test_main_guasto_in_fase_comune_exit1_senza_traceback(monkeypatch, capsys):
    import api_client
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: object())
    monkeypatch.setattr(api_client, "APIFootballClient", lambda: object())
    monkeypatch.setattr(sc, "ControlloConcorrenza", lambda: "conc")
    monkeypatch.setattr(sc, "GestoreQuota", lambda **kw: "quota")
    monkeypatch.setattr(sc, "attendi_action_concorrenti", lambda *a, **k: None)
    req = httpx.Request("POST", "https://abc.supabase.co/rest/v1/rpc/season_detail_gaps")
    ultimo = httpx.RemoteProtocolError(GOAWAY, request=req)

    def esegui(*a: Any, **k: Any) -> Any:
        raise db_client.GuastoRete("connessione_terminata", 6, "rpc season_detail_gaps", ultimo)
    monkeypatch.setattr(sc, "esegui_catchup", esegui)
    assert sc.main([]) == 1
    out = capsys.readouterr().out
    assert "RINVIATE PER GATEWAY/RETE: TUTTA LA RUN" in out and "Traceback" not in out


# ---------------------------------------------------------------------------
# 5. 4xx: nessun ritentativo. 57014: al meccanismo R-CATCHUP-2, invariato
# ---------------------------------------------------------------------------
def test_4xx_nessun_ritentativo(server, stato_rete_pulito):
    server.copione[("POST", "/rpc/season_detail_gaps")] = [json_errore(404, CORPO_PGRST202)]
    with pytest.raises(sg.MigrazioneMancante):
        sg.lacune_stagione(db_client.ClientResiliente(), 0, 0)
    server.copione[("POST", "/rpc/season_detail_gaps")] = [json_errore(403, CORPO_42501)]
    with pytest.raises(APIError, match="42501"):
        sg.lacune_stagione(db_client.ClientResiliente(), 0, 0)
    assert len([r for r in server.richieste if r[2] == "/rpc/season_detail_gaps"]) == 2   # 1 + 1
    assert stato_rete_pulito == [] and db_client.STATISTICHE_RETE["ritentativi"] == 0


def test_insert_dal_proxy_mai_ritentato(server):
    """ClientResiliente: un insert puro (season_aggregates) si esegue UNA volta."""
    server.copione[("POST", "/match_events")] = [goaway]
    with pytest.raises(httpx.RemoteProtocolError):
        db_client.ClientResiliente().table("match_events").insert([{"fixture_id": 1}]).execute()
    assert len([r for r in server.richieste if r[2] == "/match_events"]) == 1


def test_57014_resta_al_meccanismo_esistente(server, stato_rete_pulito):
    """Blocco di 2 in 57014 -> dimezzato (1 + 1), la seconda da sola in 57014 -> DEGRADATA.
    Nessun ritentativo di rete in mezzo (ogni RPC esattamente una volta)."""
    server.copione[("POST", "/rpc/season_gaps_summary")] = [json_errore(500, CORPO_57014), None,
                                                             json_errore(500, CORPO_57014)]
    rinviate: List[Tuple[int, int]] = []
    out, degradate = sg.riepilogo_lacune(db_client.ClientResiliente(), [(1, 2026), (2, 2026)], blocco=2,
                                         stampa=lambda s: None, rinviate_rete=rinviate)
    assert degradate == [(2, 2026)] and rinviate == []
    assert out[(1, 2026)].ft_totali == 5
    assert len([r for r in server.richieste if r[2] == "/rpc/season_gaps_summary"]) == 3
    assert stato_rete_pulito == []


# ---------------------------------------------------------------------------
# 6. Prevenzione: client rinnovato ogni N richieste (GOAWAY a 10.000)
# ---------------------------------------------------------------------------
def test_rinnovo_preventivo_ogni_n_richieste(server):
    db_client.attiva_rinnovo_connessioni(3)
    sb = db_client.ClientResiliente()
    for _ in range(7):
        sg.lacune_stagione(sb, 135, 2026)
    assert [r[0] for r in server.richieste] == [0, 0, 0, 1, 1, 1, 2]
    assert db_client.STATISTICHE_RETE["rinnovi_client"] == 2


def test_senza_attivazione_nessun_rinnovo(server):
    sb = db_client.ClientResiliente()
    for _ in range(7):
        sg.lacune_stagione(sb, 135, 2026)
    assert {r[0] for r in server.richieste} == {0}


def tba_quota() -> Any:
    class QuotaFinta:
        stato = None

        def capacita_giornaliera(self) -> int:
            return 7000
    return QuotaFinta()


# ---------------------------------------------------------------------------
# 7. Catena intera (esegui_catchup) sul mondo finto di test_backfill_automatico
# ---------------------------------------------------------------------------
from postgrest.exceptions import generate_default_error_message  # noqa: E402

from test_backfill_automatico_2026_09_25 import mondo  # noqa: E402,F401  (fixture)

BUONA = (135, 2026)
RETE = (777, 2018)


def _errore_520_vero() -> APIError:
    """La stessa costruzione di postgrest (request_builder.execute) sulla risposta 520 HTML."""
    return APIError(generate_default_error_message(httpx.Response(520, content=HTML_520)))


def test_esegui_catchup_blocco_in_guasto_rinviato_nessuno_stato_falso(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"] += [tba.coverage(*BUONA),
                                       tba.coverage(*RETE, current=False, fine="2019-05-30", inizio="2018-08-20")]
    for fid in (1, 2):
        db.partita(fid, *BUONA)
    for fid in (7001, 7002):
        db.partita(fid, *RETE, giorni_fa=3000)
    originale = db.rpc

    class _Rpc520:
        def execute(self) -> None:
            raise _errore_520_vero()

    def rpc(nome: str, params: Dict[str, Any]) -> Any:
        if nome == "season_gaps_summary" and RETE[0] in params["p_league_ids"]:
            return _Rpc520()
        return originale(nome, params)
    db.rpc = rpc
    client = tba.FintoClient(server)
    righe: List[str] = []
    ris = sc.esegui_catchup(db, client, tba.quota_per(db, server, client), None,
                            env={"CATCHUP_LEGHE_PRIORITARIE": "135"}, oggi=tba.OGGI, stampa=righe.append)
    testo = "\n".join(righe)
    assert RETE in ris.rinviate_rete and ris.errori == []
    assert "RINVIATE PER GATEWAY/RETE" in testo and ("DB SENZA BUCHI" in testo or "BUCHI APERTI" in testo)
    for r in db.t["season_backfill_state"]:
        if (r["league_id"], r["season_year"]) == RETE:
            assert "buchi_aperti" not in r["stats_json"]                 # nessuno stato v2 fabbricato
            assert (r["stats_json"].get("meta") or {}).get("version") != "v2"
            assert r["stats_json"]["rinviato_rete"]["consecutivi"] == 1
    assert RETE not in ris.fatte and RETE not in ris.aperto_dal
    # stesso blocco = stessa sorte (la RPC e' una sola): 2 su 2 rinviate -> oltre soglia -> exit 1
    assert set(ris.rinviate_rete) == {BUONA, RETE} and ris.codice == 1


def test_esegui_catchup_goaway_persistente_sull_insert_rinvia_e_ferma(mondo, monkeypatch):
    db, server = mondo
    completa = (136, 2026)
    db.t["api_coverage_by_season"] += [tba.coverage(*BUONA), tba.coverage(*completa)]
    for fid in (1, 2):
        db.partita(fid, *BUONA)
    db.partita(3, *completa)
    for tab in tba.TABELLE:
        db.dettaglio(tab, 3, *completa)
    req = httpx.Request("POST", "https://abc.supabase.co/rest/v1/match_events")

    def insert_goaway(table: str, rows: List[Dict[str, Any]], batch_size: int = 200) -> Tuple[int, int]:
        raise httpx.RemoteProtocolError(GOAWAY, request=req)
    monkeypatch.setattr(pfb, "insert_rows", insert_goaway)
    client = tba.FintoClient(server)
    righe: List[str] = []
    ris = sc.esegui_catchup(db, client, tba.quota_per(db, server, client), None,
                            env={"CATCHUP_LEGHE_PRIORITARIE": "135"}, oggi=tba.OGGI, stampa=righe.append)
    testo = "\n".join(righe)
    assert list(ris.rinviate_rete) == [BUONA] and ris.errori == []
    assert ris.fermato_per == db_client.MOTIVO_GUASTO_RETE
    assert "Fermato per: guasto rete/gateway" in testo and "RINVIATA PER GATEWAY/RETE: lega 135 stagione 2026" in testo
    assert ris.codice == 0                                               # 1 su 2 (50%): sotto soglia, dichiarato
    assert "Traceback" not in testo
