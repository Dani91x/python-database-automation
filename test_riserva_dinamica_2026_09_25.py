"""Riserva dinamica della quota API (25/09/2026).

Ordine dell'utente: usare il ~40 % di quota che a fine giornata avanzava (la riserva di 3.000
chiamate per le action). La riserva vale API_FOOTBALL_RISERVA_GIORNALIERA (3000) finche' le 3
action giornaliere del giorno UTC (Daily Yesterday, Today Predictions, Predictions Results) non
hanno TUTTE finito con successo (stato letto da GitHub), poi scende ad API_FOOTBALL_RISERVA_RESIDUA
(300). Dalle 23 UTC il recupero non parte con lega-stagioni nuove (reset del contatore alle 00:00).

Finto GitHub: GET /repos/{repo}/actions/workflows/{file}/runs con i parametri veri (`status` =
in_progress | queued | success | completed, `created` = ">=YYYY-MM-DDTHH:MM:SSZ", `per_page`) e la
risposta vera {"total_count": n, "workflow_runs": [{id, name, status, conclusion, created_at,
event}]}.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"
os.environ["API_FOOTBALL_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api_quota  # noqa: E402
import seasons_catchup as sc  # noqa: E402
from test_backfill_automatico_2026_09_25 import (  # noqa: E402,F401  (mondo e' una fixture)
    OGGI, FintoClient, FintoDB, FintoServer, coverage, mondo, quota_per,
)

GIORNO = datetime(2026, 9, 25, tzinfo=timezone.utc)
DAILY, TODAY, RESULTS = sc.ACTION_GIORNALIERE
NOMI = {DAILY: "Daily Yesterday Backfill", TODAY: "Today Predictions Backfill",
        RESULTS: "Predictions Results Backfill"}
ENV_GH = {"GITHUB_TOKEN": "ghs_x", "GITHUB_REPOSITORY": "utente/python-database-automation"}


class RispostaGH:
    def __init__(self, status_code: int, corpo: Dict[str, Any]) -> None:
        self.status_code = status_code
        self._corpo = corpo

    def json(self) -> Dict[str, Any]:
        return self._corpo


class FintoGitHub:
    """Le run dei workflow, filtrate come l'API REST di GitHub."""

    def __init__(self) -> None:
        self.runs: List[Dict[str, Any]] = []
        self.richieste: List[Dict[str, Any]] = []
        self.errore_http: Optional[int] = None

    def run(self, wf: str, quando: datetime, status: str = "completed", conclusion: Optional[str] = "success") -> None:
        self.runs.append({"id": 36100000000 + len(self.runs), "name": NOMI[wf], "path": f".github/workflows/{wf}",
                          "_wf": wf, "status": status, "conclusion": conclusion if status == "completed" else None,
                          "event": "schedule", "created_at": quando.strftime("%Y-%m-%dT%H:%M:%SZ")})

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None,
            timeout: int = 15) -> RispostaGH:
        params = dict(params or {})
        self.richieste.append({"url": url, **params})
        assert headers and headers["Authorization"] == "Bearer ghs_x"
        if self.errore_http:
            return RispostaGH(self.errore_http, {"message": "Server Error"})
        wf = url.rsplit("/workflows/", 1)[1].split("/")[0]
        sel = [r for r in self.runs if r["_wf"] == wf]
        st = params.get("status")
        if st in ("in_progress", "queued", "completed"):
            sel = [r for r in sel if r["status"] == st]
        elif st:                                              # una conclusione: success, failure, ...
            sel = [r for r in sel if r["conclusion"] == st]
        if params.get("created"):
            dal = params["created"][2:]
            assert params["created"].startswith(">=")
            sel = [r for r in sel if r["created_at"] >= dal]
        runs = [{k: v for k, v in r.items() if k != "_wf"} for r in sel]
        return RispostaGH(200, {"total_count": len(runs), "workflow_runs": runs[:int(params.get("per_page") or 30)]})


def _controllo(gh: FintoGitHub, env: Optional[Dict[str, str]] = None) -> sc.ControlloConcorrenza:
    return sc.ControlloConcorrenza(env=ENV_GH if env is None else env, http_get=gh.get)


def _tutte_fatte(gh: FintoGitHub) -> None:
    # orari reali: cron 01:12 / 02:18 / 03:23 UTC con ~5 h di ritardo
    gh.run(DAILY, GIORNO.replace(hour=6, minute=2))
    gh.run(TODAY, GIORNO.replace(hour=7, minute=35))
    gh.run(RESULTS, GIORNO.replace(hour=8, minute=27))


def _quota(gh: FintoGitHub, adesso: datetime, env: Optional[Dict[str, str]] = None, current: int = 5000):
    db, server = FintoDB(), FintoServer(current=current)
    avvisi: List[str] = []
    c = _controllo(gh, env)
    q = api_quota.GestoreQuota(sb=db, api_key="x", http_get=server.http_get_status, env={}, stampa=avvisi.append,
                               action_completate=lambda: c.action_completate_oggi(adesso))
    return q, avvisi, c


# ===========================================================================
# 1. Le 3 verifiche del giorno e la riserva
# ===========================================================================
def test_cron_letti_dai_workflow_veri():
    c = _controllo(FintoGitHub())
    assert [c.orario_cron(w) for w in sc.ACTION_GIORNALIERE] == [(1, 12), (2, 18), (3, 23)]


def test_prima_del_completamento_riserva_piena_3000():
    gh = FintoGitHub()
    gh.run(DAILY, GIORNO.replace(hour=6, minute=2))
    gh.run(TODAY, GIORNO.replace(hour=7, minute=35))           # Results non ancora partita
    q, avvisi, _ = _quota(gh, GIORNO.replace(hour=8))
    st = q.aggiorna()
    assert st.riserva == 3000 and st.margine == 7500 - 5000 - 3000
    assert q.capacita_giornaliera() == 4500


def test_dopo_il_completamento_riserva_residua_300_e_nota_una_volta():
    gh = FintoGitHub()
    _tutte_fatte(gh)
    q, avvisi, _ = _quota(gh, GIORNO.replace(hour=19))
    st = q.aggiorna()
    assert st.riserva == 300 and st.margine == 7500 - 5000 - 300 and q.margine() == 2200
    assert q.capacita_giornaliera() == 7200
    assert "contatore API 5000/7500 (fonte /status), riserva action 300, margine 2200" == st.riga()
    assert any("action del giorno UTC completate: riserva 3000 -> 300" in a for a in avvisi)
    q.aggiorna()
    assert sum("riserva 3000 -> 300" in a for a in avvisi) == 1       # nota solo quando cambia


def test_residua_da_env_e_mai_sopra_la_piena():
    assert api_quota.leggi_riserva_residua({}) == 300
    assert api_quota.leggi_riserva_residua({"API_FOOTBALL_RISERVA_RESIDUA": "800"}) == 800
    assert api_quota.leggi_riserva_residua({"API_FOOTBALL_RISERVA_RESIDUA": "5000"}, 3000) == 3000


def test_token_assente_riserva_piena_con_avviso():
    gh = FintoGitHub()
    _tutte_fatte(gh)
    q, avvisi, c = _quota(gh, GIORNO.replace(hour=19), env={})
    assert c.action_completate_oggi(GIORNO.replace(hour=19)) is None
    assert q.aggiorna().riserva == 3000
    assert any("stato delle action del giorno non leggibile" in a and "riserva piena 3000" in a for a in avvisi)
    assert gh.richieste == []


def test_run_di_ieri_in_ritardo_dopo_mezzanotte_non_conta():
    gh = FintoGitHub()
    gh.run(DAILY, GIORNO.replace(hour=0, minute=40))            # Daily di IERI partita in ritardo
    gh.run(TODAY, GIORNO.replace(hour=0, minute=55))
    gh.run(RESULTS, GIORNO.replace(hour=1, minute=5))
    c = _controllo(gh)
    assert c.action_completate_oggi(GIORNO.replace(hour=2)) is False
    creati = [r["created"] for r in gh.richieste if r.get("status") == "success"]
    assert creati == [">=2026-09-25T01:12:00Z"]                # dal cron di OGGI della Daily


def test_action_fallita_oggi_riserva_piena():
    gh = FintoGitHub()
    _tutte_fatte(gh)
    gh.runs[-1]["conclusion"] = "failure"                        # Results fallita: si rilancia a mano
    q, _, _ = _quota(gh, GIORNO.replace(hour=19))
    assert q.aggiorna().riserva == 3000


def test_action_in_corso_riserva_piena_anche_se_una_run_e_riuscita():
    gh = FintoGitHub()
    _tutte_fatte(gh)
    gh.run(TODAY, GIORNO.replace(hour=18), status="in_progress")   # rilancio a mano in corso
    q, _, _ = _quota(gh, GIORNO.replace(hour=19))
    assert q.aggiorna().riserva == 3000


def test_github_in_errore_non_leggibile():
    gh = FintoGitHub()
    _tutte_fatte(gh)
    gh.errore_http = 500
    assert _controllo(gh).action_completate_oggi(GIORNO.replace(hour=19)) is None


def test_github_in_errore_solo_sulle_run_riuscite_non_leggibile():
    gh = FintoGitHub()
    _tutte_fatte(gh)
    vero = gh.get

    def get(url, params=None, headers=None, timeout=15):
        if (params or {}).get("status") == "success":
            return RispostaGH(502, {"message": "Bad Gateway"})
        return vero(url, params, headers, timeout)
    c = sc.ControlloConcorrenza(env=ENV_GH, http_get=get)
    assert c.action_completate_oggi(GIORNO.replace(hour=19)) is None


def test_completate_resta_vero_nel_giorno_e_si_rilegge_il_giorno_dopo():
    gh = FintoGitHub()
    _tutte_fatte(gh)
    c = _controllo(gh)
    assert c.action_completate_oggi(GIORNO.replace(hour=19)) is True
    n = len(gh.richieste)
    assert c.action_completate_oggi(GIORNO.replace(hour=21)) is True and len(gh.richieste) == n
    c._completate_cache = None
    assert c.action_completate_oggi(GIORNO.replace(hour=22)) is True and len(gh.richieste) == n
    assert c.action_completate_oggi(GIORNO + timedelta(days=1, hours=9)) is False   # nuovo giorno UTC


# ===========================================================================
# 2. Fine giornata UTC: niente lega-stagioni nuove a cavallo del reset
# ===========================================================================
def _catchup(db, server, adesso_utc, env=None):
    client = FintoClient(server)
    q = quota_per(db, server, client)
    righe: List[str] = []
    ris = sc.esegui_catchup(db, client, q, None, env={"CATCHUP_LEGHE_PRIORITARIE": "135", **(env or {})},
                            oggi=OGGI, stampa=righe.append, adesso_utc=adesso_utc)
    return ris, righe


def test_dalle_23_utc_non_parte_nessuna_lega_stagione(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(135, 2026))
    db.partita(1, 135, 2026)
    ris, righe = _catchup(db, server, lambda: GIORNO.replace(hour=23, minute=5))
    assert server.chiamate == [] and ris.codice == 0
    assert ris.fermato_per.startswith("fine giornata UTC (ore 23 >= 23")
    ris, righe = _catchup(db, server, lambda: GIORNO.replace(hour=22, minute=59))
    assert len(server.chiamate) == 5 and ris.fatte == [(135, 2026)]


def test_ora_di_stop_da_env(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(135, 2026))
    db.partita(1, 135, 2026)
    ris, _ = _catchup(db, server, lambda: GIORNO.replace(hour=22), env={"CATCHUP_ORA_STOP_UTC": "22"})
    assert server.chiamate == [] and "fine giornata UTC" in ris.fermato_per


def test_lega_stagione_in_corso_si_ferma_a_fine_partita_alle_23(mondo):
    db, server = mondo
    db.t["api_coverage_by_season"].append(coverage(135, 2026))
    for fid in range(1, 31):
        db.partita(fid, 135, 2026)

    def orologio() -> datetime:                                   # scatta le 23 durante il lavoro
        return GIORNO.replace(hour=22, minute=59) if len(server.chiamate) < 10 else GIORNO.replace(hour=23)
    ris, _ = _catchup(db, server, orologio)
    fatte = {p["fixture"] for e, p in server.chiamate}
    assert len(fatte) == 25 and len(server.chiamate) == 125      # controllo ogni 25 partite, a fine partita
    assert "fine giornata UTC" in ris.fermato_per and ris.codice == 0


def test_p4_non_parte_dalle_23(mondo, monkeypatch):
    db, server = mondo
    monkeypatch.setattr(sc, "leghe_modelli_ml", lambda: set())
    db.t["api_coverage_by_season"].append(coverage(777, 2023, current=False, fine="2024-05-30", inizio="2023-08-20"))
    ris, righe = _catchup(db, server, lambda: GIORNO.replace(hour=23, minute=30))
    assert server.chiamate == [] and ris.p4_non_partita.startswith("fine giornata UTC")
