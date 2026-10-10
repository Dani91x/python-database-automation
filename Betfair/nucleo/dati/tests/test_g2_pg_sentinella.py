"""W1-G2 - decisione 10: la migrazione ``nucleo_sentinella_cloud_2026-10-10.sql`` su un PostgreSQL VERO.

Si accende SOLO con ``G2_PG_PSQL`` (es. ``"-h /var/tmp/pg_dg -p 54341 -U postgres"``) che punta a un PostgreSQL
USA-E-GETTA locale con i ruoli finti di Supabase (anon, authenticated, service_role BYPASSRLS e i privilegi di
default sulle tabelle di public). MAI un DB vero: il test rifiuta un host che non sia locale e ricrea SOLO le
tabelle che usa, con i tipi delle migrazioni del repo (``live_stream.sql:33``, ``omega_manual.sql:39``,
``omega_daily_v2.sql:600``, ``omega_models_v3.sql:49``, ``omega_transitions_catchup_2026-09-25.sql:123``);
``fixture_predictions`` non ha il CREATE TABLE nel repo: le cinque colonne del dossier con ``db_json_analisi``
di tipo ``json`` (il caso difficile: niente operatore di uguaglianza) e ``tactical_engine_json`` ``jsonb``.

Prova: migrazione applicata due volte (idempotente); il trigger cambia la versione SOLO quando cambia il dossier;
la RPC risponde col ponte nell'ordine di ``mike.db`` e con i permessi giusti; l'impronta di Omega della RPC e'
IDENTICA, carattere per carattere, a quella delle letture REST di oggi (``json_agg`` come PostgREST), anche con
un fuso diverso; il finto di ``test_g2_sorveglianza.py`` risponde come il vero; e un giro completo
(``Sorveglianza`` -> ``DossierPrematch`` -> ``mike.dossier.build_prematch``) col client supabase VERO su
``httpx.MockTransport`` che inoltra a ``psql``.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

import httpx
import pytest
import supabase
from supabase import ClientOptions

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import db_client  # noqa: E402
from Betfair.mike import db as mike_db  # noqa: E402
from Betfair.mike import dossier  # noqa: E402
from Betfair.nucleo.dati import cache_cloud as K  # noqa: E402
from Betfair.nucleo.dati.cloud import ClienteCloud  # noqa: E402
from Betfair.nucleo.dati.tests.test_g2_cache_cloud import FIXTURE, LIVE_FOLLOW, OMEGA_EVENTS  # noqa: E402
from Betfair.nucleo.dati.tests.test_g2_sorveglianza import CloudSentinella  # noqa: E402

ARGS = (os.environ.get("G2_PG_PSQL") or "").split() or None
pytestmark = pytest.mark.skipif(ARGS is None, reason="G2_PG_PSQL non impostata: PostgreSQL usa-e-getta assente")
MIGRAZIONE = Path(__file__).resolve().parents[4] / "migrations" / "nucleo_sentinella_cloud_2026-10-10.sql"
ID = re.compile(r"^[a-z_][a-z0-9_]*$")

SCHEMA = """
DROP TABLE IF EXISTS public.fixture_predictions, public.live_follow, public.omega_events,
    public.omega_transitions_state, public.omega_ht_ft_transitions, public.omega_build_jobs CASCADE;
DROP FUNCTION IF EXISTS public.nucleo_sentinella_cloud(text[], boolean);
DROP FUNCTION IF EXISTS public.nucleo_versione_dossier() CASCADE;
DROP SEQUENCE IF EXISTS public.nucleo_versione_dossier_seq;
CREATE TABLE public.live_follow (event_id TEXT PRIMARY KEY, fixture_id BIGINT, home_name TEXT NOT NULL DEFAULT 'A',
    status TEXT NOT NULL DEFAULT 'PENDING', updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE public.omega_events (event_id TEXT PRIMARY KEY, name TEXT, fixture_id BIGINT, league_id INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE public.fixture_predictions (fixture_id BIGINT PRIMARY KEY, league_id INTEGER,
    tactical_engine_json JSONB, db_json_analisi JSON, home_team_id INTEGER, away_team_id INTEGER,
    status TEXT, updated_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE public.omega_transitions_state (id INTEGER PRIMARY KEY, published_at TIMESTAMPTZ,
    min_league_matches INTEGER, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE public.omega_ht_ft_transitions (league_id BIGINT NOT NULL, ht TEXT NOT NULL, ft TEXT NOT NULL,
    n INTEGER NOT NULL, built_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (league_id, ht, ft));
CREATE TABLE public.omega_build_jobs (job TEXT PRIMARY KEY, last_id BIGINT NOT NULL DEFAULT 0,
    done BOOLEAN NOT NULL DEFAULT false, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
"""


def psql(sql: str, *, ruolo: Optional[str] = None) -> subprocess.CompletedProcess[str]:
    assert ARGS is not None
    testa = f"SET ROLE {ruolo};\n" if ruolo else ""
    return subprocess.run(["psql", *ARGS, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose"],
                          input=testa + sql, capture_output=True, text=True, timeout=60)


def sql(testo: str, **kw: Any) -> str:
    r = psql(testo, **kw)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _q(valore: Any) -> str:
    """Letterale SQL sicuro (dollar quoting con etichetta casuale)."""
    if valore is None:
        return "NULL"
    tag = "q" + uuid.uuid4().hex[:8]
    return f"${tag}${valore if isinstance(valore, str) else json.dumps(valore)}${tag}$"


def scrivi_previsione(riga: Dict[str, Any]) -> None:
    """Upsert sulla chiave naturale (come i workflow: ``on_conflict=fixture_id``)."""
    colonne = list(riga)
    valori = ", ".join(_q(json.dumps(riga[c]) if c in ("tactical_engine_json", "db_json_analisi")
                          and riga[c] is not None else riga[c]) for c in colonne)
    agg = ", ".join(f"{c} = EXCLUDED.{c}" for c in colonne if c != "fixture_id")
    sql(f"INSERT INTO public.fixture_predictions ({', '.join(colonne)}) VALUES ({valori}) "
        f"ON CONFLICT (fixture_id) DO UPDATE SET {agg};")


def versione(fixture_id: int) -> Optional[int]:
    v = sql(f"SELECT nucleo_versione FROM public.fixture_predictions WHERE fixture_id = {int(fixture_id)};")
    return int(v) if v else None


def rpc(eventi: List[str], omega: bool = True, ruolo: str = "service_role") -> Any:
    return json.loads(sql(f"SELECT public.nucleo_sentinella_cloud({_q('{' + ','.join(eventi) + '}')}::text[], "
                          f"{'true' if omega else 'false'});", ruolo=ruolo))


def _solo_locale() -> None:
    assert ARGS is not None
    host = ARGS[ARGS.index("-h") + 1] if "-h" in ARGS else ""
    assert host.startswith(("/tmp", "/var/tmp")) or host in ("127.0.0.1", "localhost"), f"host non locale: {host}"


@pytest.fixture(scope="module")
def migrata() -> None:
    _solo_locale()
    sql(SCHEMA)
    assert ARGS is not None
    for _ in range(2):                                                         # idempotente
        r = subprocess.run(["psql", *ARGS, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-f", str(MIGRAZIONE)],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr


@pytest.fixture
def dati(migrata: None) -> None:
    sql("TRUNCATE public.fixture_predictions, public.live_follow, public.omega_events, public.omega_transitions_state, "
        "public.omega_ht_ft_transitions, public.omega_build_jobs;")
    for ev, fid in LIVE_FOLLOW.items():
        sql(f"INSERT INTO public.live_follow (event_id, fixture_id) VALUES ({_q(ev)}, "
            f"{fid if isinstance(fid, int) else 'NULL'});")
    for ev, fid in OMEGA_EVENTS.items():
        sql(f"INSERT INTO public.omega_events (event_id, fixture_id) VALUES ({_q(ev)}, "
            f"{fid if isinstance(fid, int) else 'NULL'});")
    for riga in FIXTURE.values():
        scrivi_previsione(riga)
    sql("INSERT INTO public.omega_transitions_state (id, published_at, updated_at) VALUES "
        "(1, '2026-09-25 10:00:00+00', '2026-10-09 04:00:03.123456+00'), (2, NULL, '2020-01-01 00:00:00+00');"
        "INSERT INTO public.omega_ht_ft_transitions (league_id, ht, ft, n, built_at) VALUES "
        "(0, '1-0', '2-0', 5, '2026-10-09 04:00:00.17+00'), (39, '0-0', '1-1', 2, '2026-01-01 04:00:00+00');"
        "INSERT INTO public.omega_build_jobs (job, updated_at) VALUES ('minute', '2026-09-20 00:00:00+00'), "
        "('vecchio', '2026-01-01 00:00:00+00');")


# ---------------------------------------------------------------------------
# 1. Migrazione, permessi, trigger
# ---------------------------------------------------------------------------
def test_pg_permessi_e_tetto(dati) -> None:
    assert rpc(["ev1"])["formato"] == 1
    for ruolo in ("anon", "authenticated"):
        r = psql("SELECT public.nucleo_sentinella_cloud('{ev1}'::text[], true);", ruolo=ruolo)
        assert r.returncode != 0 and "permission denied for function" in r.stderr
    r = psql("SELECT public.nucleo_sentinella_cloud(ARRAY(SELECT 'e' || g FROM generate_series(1, 501) g), false);",
             ruolo="service_role")
    assert r.returncode != 0 and "22023" in r.stderr
    assert len(rpc([f"e{i}" for i in range(500)], omega=False)["eventi"]) == 500
    indici = sql("SELECT indexname FROM pg_indexes WHERE tablename = 'omega_ht_ft_transitions' ORDER BY 1;")
    assert "idx_omega_ht_ft_transitions_built_at" in indici.split()


def test_pg_trigger_versione_solo_quando_cambia_il_dossier(dati) -> None:
    base = FIXTURE[101]
    v0 = versione(101)
    assert v0 is not None
    sql("UPDATE public.fixture_predictions SET status = 'ok', updated_at = now() WHERE fixture_id = 101;")
    assert versione(101) == v0                                                  # colonna fuori dal dossier
    scrivi_previsione(dict(base))                                               # riscrittura identica (upsert)
    assert versione(101) == v0
    sql("UPDATE public.fixture_predictions SET db_json_analisi = db_json_analisi WHERE fixture_id = 101;")
    assert versione(101) == v0                                                  # json identico
    sql("UPDATE public.fixture_predictions SET nucleo_versione = 999999 WHERE fixture_id = 101;")
    assert versione(101) == v0                                                  # nessuno la forza
    passi = [{"tactical_engine_json": {"lambda_home": 2.0, "lambda_away": 1.0}},
             {"db_json_analisi": {"inputs": {"dc_rho": -0.2}}},
             {"league_id": 40}, {"home_team_id": 41}, {"away_team_id": 51},
             {"tactical_engine_json": None}]
    ultima = v0
    for passo in passi:
        scrivi_previsione({"fixture_id": 101, **passo})
        nuova = versione(101)
        assert nuova is not None and nuova > ultima, passo
        ultima = nuova
    # riga nata prima della migrazione: versione NULL finche' il dossier non cambia
    sql("ALTER TABLE public.fixture_predictions DISABLE TRIGGER trg_nucleo_versione_dossier;"
        "INSERT INTO public.fixture_predictions (fixture_id, league_id) VALUES (900, 39);"
        "ALTER TABLE public.fixture_predictions ENABLE TRIGGER trg_nucleo_versione_dossier;")
    sql("UPDATE public.fixture_predictions SET status = 'x' WHERE fixture_id = 900;")
    assert versione(900) is None
    sql(f"UPDATE public.fixture_predictions SET tactical_engine_json = {_q(json.dumps(base['tactical_engine_json']))}"
        f"::jsonb WHERE fixture_id = 900;")
    assert versione(900) is not None


def test_pg_rpc_ponte_nell_ordine_di_mike_db(dati) -> None:
    eventi = ["ev1", "ev2", "ev3", "ev5", "ev6", "ev10", "ev11", "ev11"]
    risposta = rpc(eventi, omega=False)
    assert risposta["omega"] is None
    per_evento = {r[0]: r[1:] for r in risposta["eventi"]}
    assert len(risposta["eventi"]) == len(set(eventi))                          # doppioni tolti
    assert per_evento["ev1"][:2] == [101, True] and per_evento["ev1"][2] == versione(101)
    assert per_evento["ev2"][:2] == [102, True]                                  # live_follow NULL -> omega_events
    assert per_evento["ev11"][:2] == [103, True]                                 # in entrambe: vince live_follow
    assert per_evento["ev5"] == [105, False, None]                               # ponte senza previsione
    assert per_evento["ev6"] == [None, False, None] and per_evento["ev10"] == [None, False, None]


@pytest.mark.parametrize("fuso", ["UTC", "Europe/Rome"])
def test_pg_impronta_omega_identica_alle_letture_rest(dati, fuso) -> None:
    """L'impronta della RPC (jsonb) e quella delle tre letture REST di oggi (PostgREST: ``json_agg``)
    sono la STESSA stringa: passare da un modo all'altro non simula una ricostruzione."""
    letture = (
        "SELECT updated_at, published_at FROM public.omega_transitions_state WHERE id = 1",
        "SELECT built_at FROM public.omega_ht_ft_transitions ORDER BY built_at DESC LIMIT 1",
        "SELECT job, updated_at FROM public.omega_build_jobs ORDER BY updated_at DESC LIMIT 1",
    )
    parti = [json.loads(sql(f"SET TimeZone = '{fuso}'; SELECT coalesce(json_agg(t), '[]') FROM ({q}) t;",
                            ruolo="service_role")) for q in letture]
    rest = "|".join(json.dumps(p[:1], sort_keys=True, default=str) for p in parti)
    risposta = json.loads(sql(f"SET TimeZone = '{fuso}'; SELECT public.nucleo_sentinella_cloud('{{}}'::text[], true);",
                              ruolo="service_role"))
    letto = K._dati_sentinella(risposta, [], True)
    assert letto is not None and letto[0] == rest
    assert "04:00:03.123456" in rest or "06:00:03.123456" in rest


def test_pg_il_finto_risponde_come_il_vero(dati) -> None:
    """Stessi dati nel PostgreSQL e nel finto; stessa sequenza di scritture: stessi [evento, fixture,
    presente] e gli STESSI eventi con la versione cambiata."""
    finto = CloudSentinella()
    finto.tabelle["live_follow"] = [{"event_id": e, "fixture_id": f if isinstance(f, int) else None}
                                    for e, f in LIVE_FOLLOW.items()]
    finto.tabelle["omega_events"] = [{"event_id": e, "fixture_id": f if isinstance(f, int) else None}
                                     for e, f in OMEGA_EVENTS.items()]
    finto.tabelle["fixture_predictions"] = []
    for riga in FIXTURE.values():
        finto.scrivi_previsione(dict(riga))
    eventi = sorted(set(LIVE_FOLLOW) | set(OMEGA_EVENTS) | {"ev10"})

    def risposte() -> Any:
        vero = rpc(eventi, omega=False)["eventi"]
        f = json.loads(finto._rpc("nucleo_sentinella_cloud", {"p_event_ids": eventi, "p_omega": False}).content)
        return vero, f["eventi"]

    def chiave(righe: Any) -> Any:
        return [r[:3] for r in righe]

    vero, f = risposte()
    assert chiave(vero) == chiave(f)
    for scrittura in ({"fixture_id": 101, "status": "ok"}, {**FIXTURE[101]},
                      {"fixture_id": 102, "tactical_engine_json": {"lambda_home": 1.0, "lambda_away": 1.0}},
                      {"fixture_id": 105, "league_id": 39, "tactical_engine_json": None}):
        scrivi_previsione(scrittura)
        finto.scrivi_previsione(dict(scrittura))
        nuovo_vero, nuovo_f = risposte()
        assert chiave(nuovo_vero) == chiave(nuovo_f), scrittura
        cambiati_vero = {a[0] for a, b in zip(vero, nuovo_vero) if a != b}
        cambiati_f = {a[0] for a, b in zip(f, nuovo_f) if a != b}
        assert cambiati_vero == cambiati_f, scrittura
        vero, f = nuovo_vero, nuovo_f


# ---------------------------------------------------------------------------
# 2. Un giro completo sul PostgreSQL vero (client supabase VERO -> MockTransport -> psql)
# ---------------------------------------------------------------------------
class PonteSql:
    """PostgREST minimo sopra psql: GET con select/eq/in/order/limit e le RPC di lettura usate qui."""

    def __init__(self) -> None:
        self.richieste: List[str] = []

    def gestisci(self, req: httpx.Request) -> httpx.Response:
        rotta = req.url.path.replace("/rest/v1", "").strip("/")
        self.richieste.append(f"{req.method} {rotta}")
        if req.method == "POST" and rotta == "rpc/nucleo_sentinella_cloud":
            a = json.loads(req.content or b"{}")
            eventi = "{" + ",".join(json.dumps(e) for e in a.get("p_event_ids") or []) + "}"
            r = psql(f"SELECT public.nucleo_sentinella_cloud({_q(eventi)}::text[], "
                     f"{'true' if a.get('p_omega', True) else 'false'});", ruolo="service_role")
            assert r.returncode == 0, r.stderr
            return httpx.Response(200, content=r.stdout.strip().encode(), headers={"content-type": "application/json"})
        if req.method == "POST":
            return httpx.Response(404, json={"code": "PGRST202", "details": None, "hint": None,
                                             "message": "Could not find the function"})
        return self._select(rotta, {k: v[0] for k, v in parse_qs(req.url.query.decode()).items()})

    def _select(self, tabella: str, q: Dict[str, str]) -> httpx.Response:
        assert ID.match(tabella), tabella
        colonne = q.get("select", "*")
        assert colonne == "*" or all(ID.match(c) for c in colonne.split(",")), colonne
        dove, ordine, limite = [], "", ""
        for col, cond in q.items():
            if col == "order":
                c, _, verso = cond.partition(".")
                assert ID.match(c)
                ordine = f" ORDER BY {c} {'DESC' if verso == 'desc' else 'ASC'}"
            elif col == "limit":
                limite = f" LIMIT {int(cond)}"
            elif col != "select":
                assert ID.match(col), col
                op, _, val = cond.partition(".")
                if op == "eq":
                    dove.append(f"{col}::text = {_q(val)}")
                elif op == "in":
                    valori = [v.strip('"') for v in val.strip("()").split(",") if v]
                    dove.append(f"{col}::text IN ({', '.join(_q(v) for v in valori) or 'NULL'})")
                else:
                    raise AssertionError(cond)
        where = (" WHERE " + " AND ".join(dove)) if dove else ""
        r = psql(f"SELECT coalesce(json_agg(t), '[]') FROM (SELECT {colonne} FROM public.{tabella}{where}"
                 f"{ordine}{limite}) t;", ruolo="service_role")
        assert r.returncode == 0, r.stderr
        return httpx.Response(200, content=r.stdout.strip().encode(), headers={"content-type": "application/json"})


@pytest.fixture
def vero(dati, monkeypatch):
    ponte = PonteSql()

    def crea(_url: str, _key: str, options: Any = None) -> Any:
        return supabase.create_client("https://abc.supabase.co", "x" * 40,
                                      options=ClientOptions(httpx_client=httpx.Client(
                                          transport=httpx.MockTransport(ponte.gestisci))))
    monkeypatch.setattr(db_client, "create_client", crea)
    monkeypatch.setattr(db_client._time, "sleep", lambda _s: None)
    db_client._TLS.client = None
    db_client._STATO_RETE.update({"guasti_di_fila": 0})
    yield ponte
    db_client._STATO_RETE.update({"guasti_di_fila": 0})


def test_pg_giro_completo_sorveglianza_dossier_mike(vero) -> None:
    adesso = [1_760_000_000.0]
    cliente = ClienteCloud("bot", dormi=lambda _s: None, casuale=lambda: 0.5)
    d = K.DossierPrematch(cliente, ripiego=mike_db, orologio=lambda: adesso[0])
    sorv = K.Sorveglianza(K.SentinellaCloud(cliente, orologio=lambda: adesso[0]), dossier=d,
                          orologio=lambda: adesso[0])
    eventi = ["ev1", "ev2", "ev3", "ev_tardo"]
    d.precarica(eventi)
    assert sorv.giro().cambiati == tuple(sorted(eventi))
    for ev in eventi:
        assert dossier.build_prematch(ev, d) == dossier.build_prematch(ev, mike_db), ev
    n = len(vero.richieste)
    adesso[0] += K.INTERVALLO_RAPIDO_S
    assert sorv.giro().cambiati == () and vero.richieste[n:] == ["POST rpc/nucleo_sentinella_cloud"]
    # il cloud ricalcola ev1 e abbina ev_tardo: al giro dopo SOLO quei due, gia' riletti
    scrivi_previsione({"fixture_id": 101, "tactical_engine_json": {"lambda_home": 2.4, "lambda_away": 0.6}})
    scrivi_previsione({**FIXTURE[101], "fixture_id": 777})
    sql("INSERT INTO public.live_follow (event_id, fixture_id) VALUES ('ev_tardo', 777);")
    adesso[0] += K.INTERVALLO_RAPIDO_S
    assert sorv.giro().cambiati == ("ev1", "ev_tardo")
    for ev in eventi:
        assert dossier.build_prematch(ev, d) == dossier.build_prematch(ev, mike_db), ev
    assert dossier.build_prematch("ev1", d)["lambda_home"] == 2.4
    assert dossier.build_prematch("ev_tardo", d)["lambda_home"] == FIXTURE[101]["tactical_engine_json"]["lambda_home"]
