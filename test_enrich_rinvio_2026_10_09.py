"""09/10/2026 - Enrich freq/ritardi: RINVIO DICHIARATO invece della run rossa per un DB
sotto carico (AUDIT_2026-10-09/fallimenti_action/ENRICH_RINVIO.md).

Run vera riprodotta: 37927426667 (Predictions Results, passo `enrich`): dopo le leghe
334, 252, 287, 703 riuscite, la lega 850 scrive 808 righe e poi il flush va in
`ReadTimeout: The read operation timed out` (httpx); 5 tentativi a 0,5-4 s, lega
abbandonata con 3612 righe in "falliti" -> SystemExit -> exit 1 -> gate rosso. Nessuna
riga `[RETE]`: la RPC di flush e' un POST non idempotente per il TrasportoResiliente.

I finti: client supabase/postgrest/httpx VERO del .venv con httpx.MockTransport al posto
della rete (stesso schema di test_fallimenti_action_2026_10_09), TrasportoResiliente
montato come in produzione (esegui_main_action), ReadTimeout VERO di httpx, corpi JSON
veri di PostgREST, colonne vere di matches / analytics_signals / live_alerts.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import httpx  # noqa: E402
import pytest  # noqa: E402
import supabase  # noqa: E402
from supabase import ClientOptions  # noqa: E402

import db_client  # noqa: E402
import enrich_analytics_snapshots as en  # noqa: E402

MERCATI = [("over_2_5", "Over"), ("over_2_5", "Under"), ("btts", "Yes"), ("btts", "No")]
CORPO_22P02 = {"code": "22P02", "details": None, "hint": None,
               "message": 'invalid input syntax for type bigint: "x"'}


def read_timeout(req: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("The read operation timed out", request=req)


class PostgREST:
    """PostgREST finto per l'enrich. Dati per lega: `n_fix[lega]` partite settlate
    (matches) e le stesse fixture in analytics_signals x 4 mercati. Il flush risponde
    con il numero di righe in staging per la lega (come la RPC vera: int scalare).
    `copione[(metodo, rotta, lega|None)]` = azioni una per richiesta, poi il normale."""

    def __init__(self, n_fix: Dict[int, int]) -> None:
        self.n_fix = dict(n_fix)
        self.richieste: List[tuple] = []
        self.copione: Dict[tuple, List[Optional[Callable[[httpx.Request], Any]]]] = {}
        self.staging: Dict[tuple, dict] = {}
        self.scritte: Dict[int, int] = {}            # lega -> righe flushate
        self.allarmi_storia: List[dict] = []         # GET /live_alerts
        self.allarmi_scritti: List[dict] = []        # POST /live_alerts
        self.timeout_letti: List[tuple] = []         # (metodo, rotta, timeout read)

    @staticmethod
    def _fid(lega: int, i: int) -> int:
        return lega * 10000 + i

    def _lega_di(self, fid: int) -> int:
        return fid // 10000

    def _matches(self, lega: int) -> List[dict]:
        return [{"fixture_id": self._fid(lega, i), "fixture_date": f"2026-{1 + (i % 9):02d}-15T18:00:00+00:00",
                 "status_short": "FT", "season_year": 2026, "goals_home": i % 4, "goals_away": (i + 1) % 3,
                 "fulltime_home": i % 4, "fulltime_away": (i + 1) % 3, "halftime_home": 0, "halftime_away": 1}
                for i in range(self.n_fix[lega])]

    def _signals(self, lega: int) -> List[dict]:
        out, rid = [], lega * 100000
        for i in range(self.n_fix[lega]):
            for m, s in MERCATI:
                rid += 1
                out.append({"id": rid, "fixture_id": self._fid(lega, i), "market": m, "selection": s})
        return out

    def gestisci(self, req: httpx.Request) -> httpx.Response:
        rotta = req.url.path.replace("/rest/v1", "")
        p = req.url.params
        lega = None
        if rotta == "/rpc/flush_analytics_snap_staging":
            lega = int(json.loads(req.content)["p_league_id"])
        elif "league_id" in p:
            lega = int(p["league_id"].split(".", 1)[1])
        self.richieste.append((req.method, rotta, lega))
        self.timeout_letti.append((req.method, rotta, (req.extensions.get("timeout") or {}).get("read")))
        azioni = self.copione.get((req.method, rotta, lega))
        if azioni:
            azione = azioni.pop(0)
            if azione is not None:
                return azione(req)
        if rotta == "/live_alerts":
            if req.method == "GET":
                return httpx.Response(200, json=self.allarmi_storia)
            corpo = json.loads(req.content)
            self.allarmi_scritti.extend(corpo if isinstance(corpo, list) else [corpo])
            return httpx.Response(201, json=[])
        if rotta == "/analytics_signals":
            if "kickoff" in p:                                    # _recent_targets
                if "or" in p:
                    return httpx.Response(200, json=[])
                oggi = datetime.now(timezone.utc).strftime("%Y-%m-%dT18:00:00+00:00")
                righe, n = [], 0
                for lg in self.n_fix:
                    n += 1
                    righe.append({"league_id": lg, "fixture_id": self._fid(lg, 0), "kickoff": oggi, "id": n})
                return httpx.Response(200, json=righe)
            return httpx.Response(200, json=[] if "id" in p else self._signals(lega))
        if rotta == "/matches":
            return httpx.Response(200, json=[] if "or" in p else self._matches(lega))
        if rotta == "/analytics_snap_staging":
            if req.method == "DELETE":
                fids = {int(x) for x in p["fixture_id"][len("in.("):-1].split(",")}
                for k in [k for k in self.staging if k[0] in fids]:
                    del self.staging[k]
                return httpx.Response(200, json=[])
            for r in json.loads(req.content):
                self.staging[(r["fixture_id"], r["market"], r["selection"])] = r
            return httpx.Response(201, json=[])
        if rotta == "/rpc/flush_analytics_snap_staging":
            chiavi = [k for k in self.staging if self._lega_di(k[0]) == lega]
            for k in chiavi:
                del self.staging[k]
            self.scritte[lega] = self.scritte.get(lega, 0) + len(chiavi)
            return httpx.Response(200, json=len(chiavi))
        return httpx.Response(404, json={"code": "PGRST205", "message": f"rotta {rotta}", "details": None, "hint": None})

    def n(self, metodo: str, rotta: str, lega: Optional[int] = None) -> int:
        return sum(1 for r in self.richieste if r[0] == metodo and r[1] == rotta and (lega is None or r[2] == lega))


@pytest.fixture(autouse=True)
def stato_pulito(monkeypatch, tmp_path):
    # en.time e db_client._time sono LO STESSO modulo time: una sola lista di attese;
    # i ritentativi del trasporto si contano in STATISTICHE_RETE["ritentativi"]
    sonni: List[float] = []
    monkeypatch.setattr(en.time, "sleep", sonni.append)
    monkeypatch.setattr(en.random, "random", lambda: 0.5)             # jitter neutro
    for v in ("DB_RESILIENZA_ACTION", "ENRICH_SOGLIA_RINVII_PCT", "ENRICH_TIMEOUT_SCRITTURA_S"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output.txt"))
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0, "resilienza_action": False})
    db_client._TLS.dentro_ritentativi = False
    db_client._TLS.client = None
    db_client.STATISTICHE_RETE.update({"ritentativi": 0, "riusciti_dopo_ritentativo": 0,
                                       "guasti_persistenti": 0, "rinnovi_client": 0})
    db_client.STATISTICHE_RETE["per_classe"].clear()
    yield {"en": sonni, "tmp": tmp_path}
    db_client._STATO_RETE.update({"rinnovo_ogni": None, "guasti_di_fila": 0, "resilienza_action": False})
    db_client._TLS.client = None
    db_client._TLS.dentro_ritentativi = False


def _monta(monkeypatch, srv: PostgREST) -> None:
    def crea(_url: str, _key: str, options: Any = None) -> Any:
        return supabase.create_client(
            "https://abc.supabase.co", "x" * 40,
            options=ClientOptions(httpx_client=httpx.Client(transport=httpx.MockTransport(srv.gestisci))))
    monkeypatch.setattr(db_client, "create_client", crea)


def _lancia(monkeypatch, srv: PostgREST, *argv: str) -> None:
    """Come il __main__ dello script nel workflow: esegui_main_action(main)."""
    _monta(monkeypatch, srv)
    monkeypatch.setattr(sys, "argv", ["enrich_analytics_snapshots.py", "--days", "4", *argv])
    db_client.esegui_main_action(en.main, "enrich_analytics_snapshots.py")


def _leggi(p) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ---------------------------------------------------------------------------
# (a) ReadTimeout x2 poi 200: flush riuscito, 0 rinviate, attese 2 e 4 s
# ---------------------------------------------------------------------------
def test_a_read_timeout_due_volte_poi_flush_riuscito(monkeypatch, stato_pulito, capsys):
    srv = PostgREST({850: 12})
    srv.copione[("POST", "/rpc/flush_analytics_snap_staging", 850)] = [read_timeout, read_timeout]
    _lancia(monkeypatch, srv)
    assert srv.scritte == {850: 12 * len(MERCATI)}                    # tutte scritte
    assert srv.n("POST", "/rpc/flush_analytics_snap_staging", 850) == 3
    assert stato_pulito["en"] == [2.0, 4.0]
    assert db_client.STATISTICHE_RETE["ritentativi"] == 0              # un solo strato di ritentativi
    assert srv.allarmi_scritti == []
    assert "rinvii=0" in _leggi(stato_pulito["tmp"] / "output.txt")
    assert "RINVIATA" not in capsys.readouterr().out


def test_a_timeout_150s_solo_sulle_scritture(monkeypatch, stato_pulito):
    """Il client resta col suo timeout per le letture; 150 s solo su upsert/flush/delete."""
    srv = PostgREST({850: 3})
    _lancia(monkeypatch, srv)
    scritture = {t for (m, r, t) in srv.timeout_letti
                 if r in ("/rpc/flush_analytics_snap_staging", "/analytics_snap_staging")}
    letture = {t for (m, r, t) in srv.timeout_letti if m == "GET"}
    assert scritture == {150.0}
    assert 150.0 not in letture


# ---------------------------------------------------------------------------
# (b) ReadTimeout persistente: lega RINVIATA, exit 0, warning, live_alerts, riepilogo
# ---------------------------------------------------------------------------
def test_b_read_timeout_persistente_lega_rinviata_exit_0(monkeypatch, stato_pulito, capsys):
    srv = PostgREST({850: 12, 334: 5, 252: 5, 287: 5})
    srv.copione[("POST", "/rpc/flush_analytics_snap_staging", 850)] = [read_timeout] * 50
    _lancia(monkeypatch, srv)                                          # nessun SystemExit
    out = capsys.readouterr().out
    assert srv.n("POST", "/rpc/flush_analytics_snap_staging", 850) == 7
    assert stato_pulito["en"] == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0]
    assert f"RINVIATA lega 850: {12 * len(MERCATI)} righe, motivo: flush lega 850: ReadTimeout" in out
    assert "::warning::ENRICH: 1 leghe RINVIATE" in out
    assert [(a["level"], a["code"]) for a in srv.allarmi_scritti] == [("WARN", "ENRICH_RINVIO")]
    assert srv.allarmi_scritti[0]["message"].startswith("lega 850: 48 righe RINVIATE")
    riepilogo = _leggi(stato_pulito["tmp"] / "summary.md")
    assert "RINVIATE PER DB SOTTO CARICO (rinviato)" in riepilogo and "lega 850" in riepilogo
    uscita = _leggi(stato_pulito["tmp"] / "output.txt")
    assert "rinvii=1" in uscita and "esito=rinviato" in uscita
    assert srv.scritte.get(334) == 20 and srv.scritte.get(252) == 20 and srv.scritte.get(287) == 20
    # il trasporto resiliente e' davvero montato (come in produzione): non ha ritentato
    assert isinstance(db_client.get_supabase_client().postgrest.session._transport,
                      db_client.TrasportoResiliente)
    assert srv.staging == {}                                           # nessun residuo


def test_b_upsert_in_timeout_un_solo_strato_di_ritentativi(monkeypatch, stato_pulito):
    """L'upsert e' idempotente per il TrasportoResiliente: senza ritentativi_del_chiamante
    sarebbero 7 x 7 = 49 richieste. Ne partono 7."""
    srv = PostgREST({850: 3, 334: 3, 252: 3, 287: 3})
    srv.copione[("POST", "/analytics_snap_staging", None)] = [read_timeout] * 7
    _lancia(monkeypatch, srv)
    assert srv.n("POST", "/analytics_snap_staging") == 7 + 3          # 7 sulla prima lega, 1 per le altre 3
    assert db_client.STATISTICHE_RETE["ritentativi"] == 0
    assert [a["code"] for a in srv.allarmi_scritti] == ["ENRICH_RINVIO"]


# ---------------------------------------------------------------------------
# (c) errore logico 4xx: exit 1 subito, nessun ritentativo, nessuna lega dopo
# ---------------------------------------------------------------------------
def test_c_errore_logico_4xx_exit_1_subito(monkeypatch, stato_pulito):
    srv = PostgREST({850: 3, 334: 3})
    srv.copione[("POST", "/rpc/flush_analytics_snap_staging", 850)] = [
        lambda _r: httpx.Response(400, json=CORPO_22P02)]
    with pytest.raises(RuntimeError, match="errore LOGICO su flush lega 850"):
        _lancia(monkeypatch, srv)
    assert srv.n("POST", "/rpc/flush_analytics_snap_staging", 850) == 1
    assert srv.n("GET", "/analytics_signals", 334) == 0                # la lega dopo non parte
    assert stato_pulito["en"] == [] and srv.allarmi_scritti == []


# ---------------------------------------------------------------------------
# (d) rinvii oltre soglia: exit 1; soglia da ambiente
# ---------------------------------------------------------------------------
def test_d_rinvii_oltre_soglia_exit_1(monkeypatch, stato_pulito, capsys):
    srv = PostgREST({850: 3, 334: 3})
    srv.copione[("POST", "/rpc/flush_analytics_snap_staging", 850)] = [read_timeout] * 7
    with pytest.raises(SystemExit) as ex:
        _lancia(monkeypatch, srv)
    assert ex.value.code != 0 and "soglia (50.0% > 25%)" in str(ex.value.code)
    assert "::error::ENRICH: rinvii oltre la soglia" in capsys.readouterr().out
    assert "esito=guasto" in _leggi(stato_pulito["tmp"] / "output.txt")


def test_d_soglia_da_ambiente(monkeypatch, stato_pulito):
    monkeypatch.setenv("ENRICH_SOGLIA_RINVII_PCT", "60")
    srv = PostgREST({850: 3, 334: 3})
    srv.copione[("POST", "/rpc/flush_analytics_snap_staging", 850)] = [read_timeout] * 7
    _lancia(monkeypatch, srv)                                          # 50% <= 60%: exit 0
    assert "esito=rinviato" in _leggi(stato_pulito["tmp"] / "output.txt")


def test_d_stessa_lega_rinviata_3_run_di_fila_exit_1(monkeypatch, stato_pulito):
    adesso = datetime.now(timezone.utc)
    srv = PostgREST({850: 3, 334: 3, 252: 3, 287: 3, 703: 3})
    srv.allarmi_storia = [
        {"id": 2, "code": "ENRICH_RINVIO", "message": "lega 850: 12 righe RINVIATE ...",
         "created_at": (adesso - timedelta(days=1)).isoformat()},
        {"id": 1, "code": "ENRICH_RINVIO", "message": "lega 850: 12 righe RINVIATE ...",
         "created_at": (adesso - timedelta(days=2)).isoformat()}]
    srv.copione[("POST", "/rpc/flush_analytics_snap_staging", 850)] = [read_timeout] * 7
    with pytest.raises(SystemExit) as ex:
        _lancia(monkeypatch, srv)                                      # 20% <= 25% ma persistente
    assert "run consecutive" in str(ex.value.code)
    assert [(a["level"], a["code"]) for a in srv.allarmi_scritti] == [("CRITICAL", "ENRICH_RINVIO_PERSISTENTE")]


def test_d_ripresa_azzera_la_serie_e_la_lega_rinviata_si_rifa(monkeypatch, stato_pulito, capsys):
    """La 999 rinviata ieri e senza partite oggi nella finestra viene rifatta e
    riceve ENRICH_RIPRESA; la 850 ha una RIPRESA dopo due rinvii: serie azzerata."""
    adesso = datetime.now(timezone.utc)
    srv = PostgREST({850: 3, 334: 3, 252: 3, 287: 3, 703: 3})
    srv.allarmi_storia = [
        {"id": 4, "code": "ENRICH_RINVIO", "message": "lega 999: 8 righe RINVIATE ...",
         "created_at": (adesso - timedelta(hours=20)).isoformat()},
        {"id": 3, "code": "ENRICH_RIPRESA", "message": "lega 850: freq/ritardi RIPRESI",
         "created_at": (adesso - timedelta(hours=21)).isoformat()},
        {"id": 2, "code": "ENRICH_RINVIO", "message": "lega 850: x", "created_at": (adesso - timedelta(days=2)).isoformat()},
        {"id": 1, "code": "ENRICH_RINVIO", "message": "lega 850: x", "created_at": (adesso - timedelta(days=3)).isoformat()}]
    srv.n_fix[999] = 2                                                 # esiste, ma non nella finestra
    _orig = srv.gestisci

    def senza_999_nei_recenti(req: httpx.Request) -> httpx.Response:
        r = _orig(req)
        if req.url.path.endswith("/analytics_signals") and "kickoff" in req.url.params and r.status_code == 200:
            righe = [x for x in json.loads(r.content) if x["league_id"] != 999]
            return httpx.Response(200, json=righe)
        return r
    srv.gestisci = senza_999_nei_recenti                               # type: ignore[method-assign]
    srv.copione[("POST", "/rpc/flush_analytics_snap_staging", 850)] = [read_timeout] * 7
    _lancia(monkeypatch, srv)                                          # 1/6 rinviata, serie 1: exit 0
    assert srv.scritte.get(999) == 2 * len(MERCATI)
    assert "riprese in questo giro: [999]" in capsys.readouterr().out
    codici = sorted((a["code"], a["message"].split(":")[0]) for a in srv.allarmi_scritti)
    assert codici == [("ENRICH_RINVIO", "lega 850"), ("ENRICH_RIPRESA", "lega 999")]


# ---------------------------------------------------------------------------
# (e) riproduzione della run 37927426667
# ---------------------------------------------------------------------------
def test_e_run_37927426667_timeout_sulla_850_dopo_altre_riuscite(monkeypatch, stato_pulito, capsys):
    """Ordine vero delle prime leghe del log: 334, 252, 287, 703, 850 (808 righe scritte,
    poi ReadTimeout), 506, 776. Fette piccole perche' la 850 ne faccia piu' d'una."""
    monkeypatch.setattr(en, "_FLUSH_SLICE", 50)
    leghe = {334: 6, 252: 6, 287: 6, 703: 6, 850: 30, 506: 6, 776: 6}
    srv = PostgREST(leghe)
    srv.copione[("POST", "/rpc/flush_analytics_snap_staging", 850)] = [None] + [read_timeout] * 50
    _lancia(monkeypatch, srv)                                          # exit 0
    out = capsys.readouterr().out
    assert srv.scritte[850] == 50                                      # la prima fetta e' scritta
    assert f"RINVIATA lega 850: {30 * len(MERCATI) - 50} righe" in out
    for lg in (334, 252, 287, 703, 506, 776):
        assert srv.scritte[lg] == 6 * len(MERCATI), lg                 # anche le leghe DOPO la 850
    assert "1 leghe RINVIATE" in out and "::error::" not in out
    assert srv.staging == {}
    assert [a["code"] for a in srv.allarmi_scritti] == ["ENRICH_RINVIO"]


def test_e_tre_leghe_rinviate_di_fila_aprono_l_interruttore(monkeypatch, stato_pulito):
    srv = PostgREST({1: 2, 2: 2, 3: 2, 4: 2, 5: 2})
    for lg in (1, 2, 3, 4, 5):
        srv.copione[("POST", "/rpc/flush_analytics_snap_staging", lg)] = [read_timeout] * 7
    with pytest.raises(SystemExit):
        _lancia(monkeypatch, srv)
    assert srv.n("POST", "/rpc/flush_analytics_snap_staging") == 21      # 3 leghe x 7, poi stop
    assert srv.n("GET", "/analytics_signals", 4) == 0


# ---------------------------------------------------------------------------
# contratto del workflow: il gate legge l'esito dell'enrich (rinviato != failure)
# ---------------------------------------------------------------------------
def test_gate_del_workflow_distingue_rinviato_da_failure():
    import yaml
    wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "predictions_results_backfill.yml"),
                             encoding="utf-8"))
    passi = wf["jobs"]["run-results-backfill"]["steps"]
    enrich = next(p for p in passi if p.get("id") == "enrich")
    gate = next(p for p in passi if str(p.get("name", "")).startswith("Gate errori nascosti"))
    assert enrich.get("continue-on-error") is True
    assert gate["env"]["RINVII_ENRICH"] == "${{ steps.enrich.outputs.rinvii }}"
    assert gate["env"]["ESITO_ENRICH"] == "${{ steps.enrich.outputs.esito }}"
    assert '"$RINVII_ENRICH" != "0"' in gate["run"] and "::warning::" in gate["run"]
    assert 'if [ "$v" != "success" ]' in gate["run"]          # failure resta rosso
