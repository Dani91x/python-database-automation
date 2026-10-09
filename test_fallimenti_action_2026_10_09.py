"""09/10/2026 - Fallimenti delle action: rimedi definitivi (AUDIT_2026-10-09/fallimenti_action).

Run rosse vere riprodotte qui (righe dai log `gh run view <id> --log-failed`):
  - 37898960743 (09/10 07:28 UTC) Retrain, job rechain: `training_planner._all_pages` ->
    `ai_model_registry` -> APIError code 522 (pagina Cloudflare "522: Connection timed out"),
    traceback, run rossa con i 3 shard di training RIUSCITI;
  - 37277717856 (05/10 07:26) ML Post-Calibration: `_fetch_registry_cells` -> 521
    ("521: Web server is down"), traceback;
  - 37103519105 / 36976589187 (03/10, 02/10) Leagues Mapping: lettura api_coverage_by_season 522;
  - 37898960772 (09/10) Hazard Atlas: rpc/hazard_atlas_salva_versione 520 x5 -> exit 1.

I finti: client supabase/postgrest/httpx VERO del .venv con httpx.MockTransport al posto della
rete (stesso schema di test_catchup_rete_2026_10_08); pagine HTML con i titoli veri dei log;
corpi JSON veri di PostgREST. L'atlante usa il finto di urlopen del suo test del 28/09.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from typing import Any, Callable, Dict, List, Optional

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
import yaml  # noqa: E402
from postgrest.exceptions import APIError  # noqa: E402
from supabase import ClientOptions  # noqa: E402

import db_client  # noqa: E402
import training_planner as tp  # noqa: E402


def _pagina(codice: int, titolo: str) -> bytes:
    """Pagina Cloudflare: inizio e titolo VERI dai log (il resto e' grafica)."""
    return (b'<!DOCTYPE html>\n<!--[if lt IE 7]> <html class="no-js ie6 oldie" lang="en-US"> <![endif]-->\n'
            b'<head>\n\n<title>supabase.co | ' + f"{codice}: {titolo}".encode() + b'</title>\n'
            b'<meta charset="UTF-8" />\n</head>\n<body>\n</body>\n</html>')


PAGINE = {520: "Web server is returning an unknown error", 521: "Web server is down",
          522: "Connection timed out"}
CORPO_57014 = {"code": "57014", "details": None, "hint": None,
               "message": "canceling statement due to statement timeout"}
CORPO_42501 = {"code": "42501", "details": None, "hint": None, "message": "permission denied for table matches"}
CORPO_PGRST202 = {"code": "PGRST202", "details": None, "hint": None,
                  "message": "Could not find the function public.leagues_needing_retrain(p_min_new) in the schema cache"}


def cloudflare(codice: int) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _r: httpx.Response(codice, content=_pagina(codice, PAGINE[codice]),
                                     headers={"content-type": "text/html; charset=UTF-8"})


def json_errore(stato: int, corpo: Dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _r: httpx.Response(stato, json=corpo)


def eccezione(tipo: type, msg: str = "x") -> Callable[[httpx.Request], httpx.Response]:
    def _f(req: httpx.Request) -> httpx.Response:
        raise tipo(msg, request=req)
    return _f


class Server:
    """PostgREST finto: `copione[(metodo, rotta)]` = azioni nell'ordine (una per richiesta),
    poi la risposta normale (`righe[rotta]`, 200; POST -> 201)."""

    def __init__(self) -> None:
        self.richieste: List[tuple] = []
        self.copione: Dict[tuple, List[Optional[Callable[[httpx.Request], Any]]]] = {}
        self.righe: Dict[str, Any] = {}

    def gestisci(self, req: httpx.Request) -> httpx.Response:
        rotta = req.url.path.replace("/rest/v1", "")
        self.richieste.append((req.method, rotta))
        azioni = self.copione.get((req.method, rotta))
        if azioni:
            azione = azioni.pop(0)
            if azione is not None:
                return azione(req)
        if req.method == "POST" and not rotta.startswith("/rpc/"):
            corpo = json.loads(req.content or b"[]")
            return httpx.Response(201, json=corpo if isinstance(corpo, list) else [corpo])
        return httpx.Response(200, json=self.righe.get(rotta, []))

    def n(self, metodo: str, rotta: str) -> int:
        return sum(1 for r in self.richieste if r == (metodo, rotta))


@pytest.fixture
def server(monkeypatch):
    srv = Server()

    def crea(_url: str, _key: str, options: Any = None) -> Any:
        return supabase.create_client(
            "https://abc.supabase.co", "x" * 40,
            options=ClientOptions(httpx_client=httpx.Client(transport=httpx.MockTransport(srv.gestisci))))
    monkeypatch.setattr(db_client, "create_client", crea)
    monkeypatch.setattr(db_client._TLS, "client", None, raising=False)
    return srv


@pytest.fixture(autouse=True)
def stato_pulito(monkeypatch):
    sonni: List[float] = []
    monkeypatch.setattr(db_client._time, "sleep", sonni.append)
    monkeypatch.setattr(db_client._random, "random", lambda: 0.5)      # jitter neutro
    monkeypatch.delenv("DB_RESILIENZA_ACTION", raising=False)
    monkeypatch.delenv("DB_RESILIENZA_ATTESA_LUNGA_S", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0, "resilienza_action": False})
    db_client.STATISTICHE_RETE.update({"ritentativi": 0, "riusciti_dopo_ritentativo": 0,
                                       "guasti_persistenti": 0, "rinnovi_client": 0})
    db_client.STATISTICHE_RETE["per_classe"].clear()
    db_client._TLS.dentro_ritentativi = False
    yield sonni
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0, "resilienza_action": False})
    db_client._TLS.client = None
    db_client._TLS.dentro_ritentativi = False


def _sb() -> Any:
    db_client.attiva_resilienza_action()
    return db_client.get_supabase_client()


# ---------------------------------------------------------------------------
# 1. Le run vere: 522 / 521 su una lettura, poi il DB risponde
# ---------------------------------------------------------------------------
def test_rechain_run_37898960743_522_poi_200_il_planner_legge(server, stato_pulito):
    """La riga vera: training_planner._all_pages('ai_model_registry') -> 522."""
    server.copione[("GET", "/ai_model_registry")] = [cloudflare(522), cloudflare(522)]
    server.righe["/ai_model_registry"] = [{"league_id": 39, "trained_at": "2026-10-09T07:27:00+00:00"}]
    db_client.attiva_resilienza_action()
    righe = tp._all_pages("ai_model_registry", "league_id,trained_at")
    assert righe == [{"league_id": 39, "trained_at": "2026-10-09T07:27:00+00:00"}]
    assert server.n("GET", "/ai_model_registry") == 3
    assert stato_pulito == [2.0, 4.0]                                  # attese brevi, jitter neutro
    assert db_client.STATISTICHE_RETE["riusciti_dopo_ritentativo"] == 1


def test_postcal_run_37277717856_521_poi_200(server, stato_pulito):
    import compute_ml_post_calibration as cmp
    server.copione[("GET", "/ai_model_registry")] = [cloudflare(521)]
    server.righe["/ai_model_registry"] = [{"league_id": 1, "target": "x", "calibration_cells": {},
                                           "trained_at": None}]
    db_client.attiva_resilienza_action()
    assert len(cmp._fetch_registry_cells()) == 1
    assert server.n("GET", "/ai_model_registry") == 2


def test_senza_attivazione_nessun_ritentativo_profilo_bot_invariato(server, stato_pulito):
    """I bot non chiamano attiva_resilienza_action: un 522 resta un errore alla prima."""
    server.copione[("GET", "/ai_model_registry")] = [cloudflare(522)]
    with pytest.raises(APIError) as info:
        db_client.get_supabase_client().table("ai_model_registry").select("*").execute()
    assert str(info.value.code) == "522"
    assert server.n("GET", "/ai_model_registry") == 1 and stato_pulito == []


def test_attivazione_da_ambiente_per_i_passi_inline(server, monkeypatch, stato_pulito):
    monkeypatch.setenv("DB_RESILIENZA_ACTION", "1")
    server.copione[("GET", "/x")] = [cloudflare(522)]
    db_client.get_supabase_client().table("x").select("*").execute()
    assert server.n("GET", "/x") == 2


# ---------------------------------------------------------------------------
# 2. Regole di idempotenza (mai righe doppie, mai contatori raddoppiati)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("codice, attese", [(522, 2), (521, 2), (520, 1)])
def test_insert_puro_si_ritenta_solo_se_non_consegnato(server, codice, attese):
    server.copione[("POST", "/match_events")] = [cloudflare(codice)]
    sb = _sb()
    try:
        sb.table("match_events").insert({"fixture_id": 1}).execute()
    except APIError as e:
        assert codice == 520 and str(e.code) == "520"
    assert server.n("POST", "/match_events") == attese


def test_upsert_si_ritenta_anche_su_520(server):
    server.copione[("POST", "/fixture_predictions")] = [cloudflare(520)]
    _sb().table("fixture_predictions").upsert({"fixture_id": 1}, on_conflict="fixture_id").execute()
    assert server.n("POST", "/fixture_predictions") == 2


def test_patch_e_delete_si_ritentano_su_520(server):
    server.copione[("PATCH", "/matches")] = [cloudflare(520)]
    server.copione[("DELETE", "/match_lineups")] = [cloudflare(520)]
    sb = _sb()
    sb.table("matches").update({"x": 1}).eq("fixture_id", 1).execute()
    sb.table("match_lineups").delete().eq("fixture_id", 1).execute()
    assert server.n("PATCH", "/matches") == 2 and server.n("DELETE", "/match_lineups") == 2


def test_rpc_di_lettura_si_ritenta_rpc_che_scrive_no(server):
    server.copione[("POST", "/rpc/leagues_needing_retrain")] = [cloudflare(520)]
    server.copione[("POST", "/rpc/flush_analytics_snap_staging")] = [cloudflare(520)]
    server.copione[("POST", "/rpc/record_fixture_detail_checks")] = [cloudflare(522)]
    sb = _sb()
    sb.rpc("leagues_needing_retrain", {"p_min_new": 10}).execute()
    with pytest.raises(APIError):
        sb.rpc("flush_analytics_snap_staging", {"p_league_id": 1}).execute()
    sb.rpc("record_fixture_detail_checks", {"p_righe": []}).execute()     # 522: mai arrivata
    assert server.n("POST", "/rpc/leagues_needing_retrain") == 2
    assert server.n("POST", "/rpc/flush_analytics_snap_staging") == 1
    assert server.n("POST", "/rpc/record_fixture_detail_checks") == 2


@pytest.mark.parametrize("risposta, codice", [(json_errore(500, CORPO_57014), "57014"),
                                              (json_errore(403, CORPO_42501), "42501")])
def test_57014_e_4xx_mai_ritentati(server, stato_pulito, risposta, codice):
    server.copione[("GET", "/matches")] = [risposta]
    with pytest.raises(APIError) as info:
        _sb().table("matches").select("*").execute()
    assert info.value.code == codice
    assert server.n("GET", "/matches") == 1 and stato_pulito == []


def test_eccezioni_di_trasporto(server):
    server.copione[("GET", "/a")] = [eccezione(httpx.ReadTimeout, "The read operation timed out")]
    server.copione[("POST", "/b")] = [eccezione(httpx.ConnectError, "[Errno -3] Temporary failure")]
    server.copione[("POST", "/c")] = [eccezione(
        httpx.RemoteProtocolError, "<ConnectionTerminated error_code:0, last_stream_id:19999, additional_data:None>")]
    sb = _sb()
    sb.table("a").select("*").execute()                                 # lettura: ritentata
    sb.table("b").insert({"k": 1}).execute()                            # mai partita: ritentata
    with pytest.raises(httpx.RemoteProtocolError):
        sb.table("c").insert({"k": 1}).execute()                        # forse applicata: NO
    assert (server.n("GET", "/a"), server.n("POST", "/b"), server.n("POST", "/c")) == (2, 2, 1)


def test_fuori_da_rest_v1_passa_intatto(stato_pulito):
    visti: List[str] = []

    def interno(req: httpx.Request) -> httpx.Response:
        visti.append(req.url.path)
        return httpx.Response(522)
    t = db_client.TrasportoResiliente(httpx.MockTransport(interno))
    with httpx.Client(transport=t) as c:
        assert c.post("https://abc.supabase.co/storage/v1/object/models/x.pkl").status_code == 522
    assert visti == ["/storage/v1/object/models/x.pkl"] and stato_pulito == []


# ---------------------------------------------------------------------------
# 3. Persistente: attese brevi + una lunga, poi l'interruttore; niente doppio strato
# ---------------------------------------------------------------------------
def test_522_persistente_attese_brevi_poi_lunga_poi_interruttore(server, stato_pulito):
    server.copione[("GET", "/x")] = [cloudflare(522)] * 100
    sb = _sb()
    for _ in range(2):
        with pytest.raises(APIError):
            sb.table("x").select("*").execute()
    assert stato_pulito == [2.0, 4.0, 8.0, 16.0, 32.0, 120.0] * 2      # ~3 min per chiamata
    assert server.n("GET", "/x") == 14
    assert db_client.STATISTICHE_RETE["guasti_persistenti"] == 2
    with pytest.raises(APIError):                                       # interruttore aperto
        sb.table("x").select("*").execute()
    assert server.n("GET", "/x") == 15


def test_dentro_con_ritentativi_il_trasporto_non_raddoppia(server, stato_pulito):
    """Catchup (esegui_con_retry): 6 tentativi del livello di sopra, non 6 x 7."""
    server.copione[("GET", "/x")] = [cloudflare(522)] * 100
    sb = _sb()
    with pytest.raises(db_client.GuastoRete):
        db_client.esegui_con_retry(lambda c: c.table("x").select("*"), sb)
    assert server.n("GET", "/x") == 6
    assert db_client._TLS.dentro_ritentativi is False


# ---------------------------------------------------------------------------
# 4. Riga chiara al posto del traceback muto
# ---------------------------------------------------------------------------
def test_esegui_main_action_guasto_persistente_riga_chiara_exit_1(server, tmp_path, monkeypatch, capsys):
    riepilogo = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(riepilogo))
    db_client._STATO_RETE["guasti_di_fila"] = 5                         # un tentativo solo
    server.copione[("GET", "/ai_model_registry")] = [cloudflare(522)]

    def main() -> None:
        tp._all_pages("ai_model_registry", "league_id")
    with pytest.raises(SystemExit) as info:
        db_client.esegui_main_action(main, "training_planner")
    assert info.value.code == 1
    out = capsys.readouterr().out
    assert "::error::GUASTO DB PERSISTENTE (gateway) in training_planner" in out
    assert "522: Connection timed out" in out
    assert "GUASTO DB PERSISTENTE" in riepilogo.read_text(encoding="utf-8")


def test_esegui_main_action_errore_di_codice_risale_identico(server):
    def main() -> None:
        raise KeyError("fixture_id")
    with pytest.raises(KeyError):
        db_client.esegui_main_action(main, "x")
    assert db_client.resilienza_action_attiva()


def test_entrypoint_dei_workflow_passano_da_esegui_main_action():
    file = ["daily_yesterday_backfill.py", "Prediction/today_predictions_backfill.py",
            "Prediction/predictions_results_backfill.py", "build_analytics_signals.py",
            "merge_engine_signals.py", "enrich_analytics_snapshots.py", "refresh_analytics_bets.py",
            "build_direzione.py", "leagues_mapper.py", "compute_ml_post_calibration.py",
            "cloud_retrain_shard.py", "generate_dynamic_cal.py", "update_poisson_calibration.py",
            "seasons_catchup.py"]
    for f in file:
        testo = open(os.path.join(ROOT, f), encoding="utf-8").read()
        coda = testo.split('if __name__ == "__main__":', 1)[1]
        assert "esegui_main_action(" in coda, f


# ---------------------------------------------------------------------------
# 5. Planner: guasto non piu' inghiottito, attese lunghe
# ---------------------------------------------------------------------------
def test_incremental_todo_guasto_di_rete_risale_rpc_assente_resta_vuota(server):
    db_client._STATO_RETE["guasti_di_fila"] = 5
    server.copione[("POST", "/rpc/leagues_needing_retrain")] = [cloudflare(522), json_errore(404, CORPO_PGRST202)]
    db_client.attiva_resilienza_action()
    with pytest.raises(APIError):
        tp._incremental_todo(10, None)
    assert tp._incremental_todo(10, None) == []                         # RPC assente: come prima


def test_planner_con_attesa(monkeypatch):
    chiamate: List[int] = []
    err = APIError({"message": "JSON could not be generated", "code": 522, "hint": None,
                    "details": _pagina(522, PAGINE[522]).decode()})

    def finto(**_k: Any) -> Dict[str, Any]:
        chiamate.append(1)
        if len(chiamate) < 3:
            raise err
        return {"todo": [1]}
    monkeypatch.setattr(tp, "select_leagues_to_train", finto)
    attese: List[float] = []
    assert tp.select_leagues_to_train_con_attesa(dormi=attese.append) == {"todo": [1]}
    assert attese == [60.0, 120.0]
    chiamate.clear()
    monkeypatch.setattr(tp, "select_leagues_to_train", lambda **_k: (_ for _ in ()).throw(err))
    attese.clear()
    with pytest.raises(APIError):
        tp.select_leagues_to_train_con_attesa(dormi=attese.append)
    assert attese == [60.0, 120.0, 240.0]
    monkeypatch.setattr(tp, "select_leagues_to_train", lambda **_k: (_ for _ in ()).throw(KeyError("x")))
    attese.clear()
    with pytest.raises(KeyError):
        tp.select_leagues_to_train_con_attesa(dormi=attese.append)
    assert attese == []


# ---------------------------------------------------------------------------
# 6. Il passo rechain di retrain_models.yml, eseguito con bash e python/gh/sleep finti
# ---------------------------------------------------------------------------
def _passo(job: str, step_id: str) -> str:
    w = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "retrain_models.yml"), encoding="utf-8"))
    return [s for s in w["jobs"][job]["steps"] if s.get("id") == step_id][0]["run"]


BASH = shutil.which("bash")


@pytest.mark.skipif(BASH is None, reason="bash assente")
@pytest.mark.parametrize("caso", ["guasto_db", "errore_codice", "lancio_ok", "gh_ko_run_creata",
                                  "gh_ko_run_assente", "gh_ko_stato_illeggibile", "nessuna_rimasta"])
def test_rechain_bash(tmp_path, caso):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    rc_py = {"guasto_db": 3, "errore_codice": 1}.get(caso, 0)
    rimaste = 0 if caso == "nessuna_rimasta" else 5
    (bin_ / "python").write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        cat > /dev/null
        if [ {rc_py} -eq 0 ]; then printf '{rimaste}' > remaining_count.txt; fi
        exit {rc_py}
        """), newline="\n")
    gh_ko = caso.startswith("gh_ko")
    conta = {"gh_ko_run_creata": "1", "gh_ko_run_assente": "0"}.get(caso, "")
    (bin_ / "gh").write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        echo "$*" >> "{(tmp_path / 'gh.log').as_posix()}"
        if [ "$1" = "api" ]; then
          if [ -z "{conta}" ]; then exit 1; fi
          echo "{conta}"; exit 0
        fi
        if [ "{str(gh_ko).lower()}" = "true" ] && [ ! -f "{(tmp_path / 'primo').as_posix()}" ]; then
          touch "{(tmp_path / 'primo').as_posix()}"; exit 1
        fi
        exit 0
        """), newline="\n")
    (bin_ / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n", newline="\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    script = tmp_path / "passo.sh"
    script.write_text(_passo("rechain", "rilancio"), newline="\n")
    env = dict(os.environ, PATH=bin_.as_posix() + os.pathsep + os.environ.get("PATH", ""),
               GITHUB_OUTPUT=(tmp_path / "out").as_posix(), GITHUB_STEP_SUMMARY=(tmp_path / "sum").as_posix(),
               GITHUB_REPOSITORY="o/r", CHAIN_DEPTH="0", CATENA="true")
    r = subprocess.run([BASH, "-e", script.name], cwd=tmp_path, env=env, capture_output=True, text=True)
    gh = (tmp_path / "gh.log").read_text().splitlines() if (tmp_path / "gh.log").exists() else []
    lanci = [g for g in gh if g.startswith("workflow run")]
    out = (tmp_path / "out").read_text() if (tmp_path / "out").exists() else ""
    if caso == "guasto_db":
        assert r.returncode == 0 and "::warning::RECHAIN NON ESEGUITO" in r.stdout
        assert lanci == [] and "rilanciato=true" not in out
        assert "rechain rinviato" in (tmp_path / "sum").read_text()
    elif caso == "errore_codice":
        assert r.returncode == 1 and lanci == []
    elif caso == "nessuna_rimasta":
        assert r.returncode == 0 and lanci == []
    elif caso == "lancio_ok":
        assert r.returncode == 0 and len(lanci) == 1 and "rilanciato=true" in out
        assert "catena=true" in lanci[0] and "chain_depth=1" in lanci[0]
    elif caso == "gh_ko_run_creata":
        assert r.returncode == 0 and len(lanci) == 1
    elif caso == "gh_ko_run_assente":
        assert r.returncode == 0 and len(lanci) == 2
    elif caso == "gh_ko_stato_illeggibile":
        assert r.returncode == 1 and len(lanci) == 1 and "illeggibile" in r.stdout


def test_workflow_contratti():
    wf = os.path.join(ROOT, ".github", "workflows")

    def carica(n: str) -> Dict[str, Any]:
        return yaml.safe_load(open(os.path.join(wf, n), encoding="utf-8"))
    rt = carica("retrain_models.yml")
    assert rt["jobs"]["rechain"]["timeout-minutes"] >= 20
    gate = [s for s in rt["jobs"]["plan"]["steps"] if s.get("id") == "gate"][0]
    assert gate["env"]["DB_RESILIENZA_ACTION"] == "1"
    assert "select_leagues_to_train_con_attesa" in gate["run"] and "esegui_main_action" in gate["run"]
    reb = [s for s in rt["jobs"]["rechain"]["steps"] if s.get("id") == "rilancio"][0]
    assert reb["env"]["DB_RESILIENZA_ACTION"] == "1"
    for nome, job, tetto in [("daily_yesterday_backfill.yml", "run-backfill", 120),
                             ("today_predictions_backfill.yml", "run-predictions", 330),
                             ("predictions_results_backfill.yml", "run-results-backfill", 240),
                             ("weekly_poisson_calibration.yml", "calibrate", 90)]:
        assert carica(nome)["jobs"][job]["timeout-minutes"] == tetto, nome
    cal = carica("ml_calibration.yml")
    passi = " ".join(s.get("run", "") or "" for s in cal["jobs"]["assemble"]["steps"])
    assert "requirements-planner.txt" in passi and "install --upgrade pip supabase" not in passi


# ---------------------------------------------------------------------------
# 7. Atlante hazard (run 37898960772): niente doppioni, corpo compatto, pre-controllo
# ---------------------------------------------------------------------------
from Betfair.stream.scalper import genera_atlante as G  # noqa: E402
from Betfair.stream.tests import test_genera_atlante_scrittura_ritentativi_2026_09_28 as TA  # noqa: E402


def test_atlante_520_ma_riga_gia_scritta_nessun_ritentativo(monkeypatch):
    import urllib.request
    trovata = json.dumps([{"id": 9}]).encode()
    finto = TA.UrlopenFinto([TA._http_error(520, b"error code: 520"), trovata])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    sonno = TA._sonno_finto()
    s = G._Scrittore("http://finto", "k", attese=(5.0, 30.0), sleep=sonno)
    s._scrivi_riga("2026-10-09T08:51:48+00:00", 382, 460950, 10500510, TA._atlas(382))
    assert [c["metodo"] for c in finto.chiamate] == ["POST", "GET"]
    assert "generated_at=eq.2026-10-09T08:51:48%2B00:00" in finto.chiamate[1]["path"]
    assert sonno.attese == []


def test_atlante_520_riga_assente_ritenta_e_500_57014_non_controlla(monkeypatch):
    import urllib.request
    finto = TA.UrlopenFinto([TA._http_error(520, b"error code: 520"), b"[]", None])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    sonno = TA._sonno_finto()
    G._Scrittore("http://finto", "k", attese=(5.0,), sleep=sonno)._scrivi_riga("g", 1, 1, 1, TA._atlas())
    assert [c["metodo"] for c in finto.chiamate] == ["POST", "GET", "POST"] and sonno.attese == [5.0]
    finto2 = TA.UrlopenFinto([TA._http_error(500), None])
    monkeypatch.setattr(urllib.request, "urlopen", finto2)
    G._Scrittore("http://finto", "k", attese=(5.0,), sleep=lambda s: None)._scrivi_riga("g", 1, 1, 1, TA._atlas())
    assert [c["metodo"] for c in finto2.chiamate] == ["POST", "POST"]   # 57014: niente lettura


def test_atlante_corpo_compatto(monkeypatch):
    import urllib.request
    corpi: List[bytes] = []

    def urlopen(req: Any, timeout: float = 0.0) -> Any:
        corpi.append(req.data)
        return TA._RispostaFinta(b"")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    G._Scrittore("http://finto", "k", attese=()).\
        _req("POST", "hazard_atlas", {"a": [1, 2], "b": {"c": 3}}, "return=minimal")
    assert corpi == [b'{"a":[1,2],"b":{"c":3}}']


def test_atlante_pre_controllo_ritenta_sul_520(monkeypatch, capsys):
    import time
    import urllib.request
    w = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "hazard_atlas.yml"), encoding="utf-8"))
    run = [s for s in w["jobs"]["hazard-atlas"]["steps"] if s.get("name", "").startswith("Prerequisiti")][0]["run"]
    codice = re.search(r"python - <<'PY'\n(.*?)\nPY", run, re.S).group(1)
    finto = TA.UrlopenFinto([TA._http_error(520, b"error code: 520"), b"[]",
                             json.dumps([{"watermark_event_id": 10473273}]).encode()])
    monkeypatch.setattr(urllib.request, "urlopen", finto)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setenv("SUPABASE_URL", "http://finto")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    exec(compile(codice, "prerequisiti", "exec"), {"__name__": "__main__"})
    assert "filigrana=10473273: procedo" in capsys.readouterr().out
    assert len(finto.chiamate) == 3
    finto404 = TA.UrlopenFinto([TA._http_error(404, b"{}")])
    monkeypatch.setattr(urllib.request, "urlopen", finto404)
    with pytest.raises(SystemExit):
        exec(compile(codice, "prerequisiti", "exec"), {"__name__": "__main__"})
    assert len(finto404.chiamate) == 1                                   # 404: subito, come prima
