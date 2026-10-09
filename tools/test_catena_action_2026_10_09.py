"""Catena notturna delle action (09/10/2026, cantiere orologio notturno).

Ordine dell'utente: le action girano di notte (app spenta), IN FILA, senza
sovrapposizioni con i cron e MAI due volte. Progetto:
- nessun cron GitHub (schedule:) nel repo;
- pg_cron (migrations/orologio_action_notturne_2026-10-09.sql) lancia SOLO il
  primo anello alle 00:12 UTC, una volta al giorno (guardia public.lanci_action);
- ogni anello lancia il successivo con il job `passa-testimone`
  (.github/scripts/passa_testimone.sh, workflow_dispatch con GITHUB_TOKEN):
  NON con workflow_run, perche' GitHub non esegue piu' di tre livelli di
  workflow_run in fila e la catena ne ha nove.

Questi test leggono i file VERI del repo (YAML con `yaml`, SQL come testo) e
provano lo script della staffetta con un `gh` finto che stampa gli stessi
valori del vero (`gh api ... --jq .total_count` -> un intero).

Uso: python -m pytest tools/test_catena_action_2026_10_09.py -q -p no:cacheprovider
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF_DIR = os.path.join(ROOT, ".github", "workflows")
SCRIPT = os.path.join(ROOT, ".github", "scripts", "passa_testimone.sh")
MIGRAZIONE = os.path.join(ROOT, "migrations", "orologio_action_notturne_2026-10-09.sql")

# ordine della catena (decisione dell'utente del 09/10/2026: Today Predictions
# subito dopo la Post-Calibration, pronta per le 09:00 italiane)
CATENA = [
    "daily_yesterday_backfill.yml",
    "retrain_models.yml",
    "ml_calibration.yml",
    "today_predictions_backfill.yml",
    "hazard_atlas.yml",
    "leagues_mapper.yml",
    "seasons_catchup.yml",
    "predictions_results_backfill.yml",
    "weekly_poisson_calibration.yml",
]
LAVORO_STAFFETTA = "passa-testimone"


# ---------------------------------------------------------------------------
# lettura
# ---------------------------------------------------------------------------
def _carica(nome: str) -> Dict[str, Any]:
    with open(os.path.join(WF_DIR, nome), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _tutti() -> Dict[str, Dict[str, Any]]:
    return {n: _carica(n) for n in sorted(os.listdir(WF_DIR)) if n.endswith((".yml", ".yaml"))}


def _on(d: Dict[str, Any]) -> Dict[str, Any]:
    # PyYAML (YAML 1.1) legge la chiave `on` come True
    on = d.get(True, d.get("on"))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on or {}


def _prossimo(d: Dict[str, Any]) -> Optional[str]:
    job = (d.get("jobs") or {}).get(LAVORO_STAFFETTA)
    if not job:
        return None
    trovati = [((s.get("env") or {}).get("PROSSIMO_ANELLO")) for s in job.get("steps", [])]
    trovati = [t for t in trovati if t]
    assert len(trovati) == 1, f"{LAVORO_STAFFETTA}: attesa UNA sola PROSSIMO_ANELLO, trovate {trovati}"
    return trovati[0]


def _testo_file(nome: str) -> str:
    with open(os.path.join(WF_DIR, nome), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# (1) nessun cron GitHub
# ---------------------------------------------------------------------------
def test_nessun_schedule_in_nessun_workflow() -> None:
    for nome, d in _tutti().items():
        assert "schedule" not in _on(d), f"{nome}: ha ancora un trigger schedule"
        # anche nel testo: una riga `- cron:` non commentata e' un cron vivo
        for riga in _testo_file(nome).splitlines():
            s = riga.strip()
            if s.startswith("#"):
                continue
            assert not re.match(r"^-?\s*cron\s*:", s), f"{nome}: riga cron viva: {riga!r}"


# ---------------------------------------------------------------------------
# (2) la catena e' UNA linea, nell'ordine deciso, senza cicli
# ---------------------------------------------------------------------------
def test_catena_una_linea_nell_ordine() -> None:
    tutti = _tutti()
    succ = {n: _prossimo(d) for n, d in tutti.items()}
    succ = {n: p for n, p in succ.items() if p}
    # ogni anello ha al piu' un successore (dict) e al piu' un predecessore
    pred: Dict[str, List[str]] = {}
    for a, b in succ.items():
        pred.setdefault(b, []).append(a)
    for b, aa in pred.items():
        assert len(aa) == 1, f"{b} ha piu' di un anello a monte: {aa}"
    # testa: nessun predecessore; percorso dalla testa
    teste = [n for n in succ if n not in pred]
    assert teste == ["daily_yesterday_backfill.yml"], f"testa della catena attesa il Daily, trovate {teste}"
    percorso = [teste[0]]
    while percorso[-1] in succ:
        nxt = succ[percorso[-1]]
        assert nxt not in percorso, f"ciclo nella catena: {percorso + [nxt]}"
        percorso.append(nxt)
    assert percorso == CATENA, f"ordine della catena diverso da quello deciso:\n{percorso}"
    # nessun anello fuori dalla linea
    assert set(succ) | set(pred) == set(CATENA)


def test_nessun_workflow_run_nella_catena() -> None:
    """La staffetta e' SOLO via workflow_dispatch: un workflow_run rimasto farebbe
    partire un anello DUE volte (staffetta + evento) o lo perderebbe oltre il
    terzo livello."""
    for nome, d in _tutti().items():
        assert "workflow_run" not in _on(d), f"{nome}: ha ancora un trigger workflow_run"


# ---------------------------------------------------------------------------
# (3) ogni anello ha workflow_dispatch con l'input catena (default false)
# ---------------------------------------------------------------------------
def test_ogni_anello_ha_dispatch_e_input_catena() -> None:
    for nome in CATENA:
        on = _on(_carica(nome))
        assert "workflow_dispatch" in on, f"{nome}: manca workflow_dispatch"
        inputs = (on["workflow_dispatch"] or {}).get("inputs") or {}
        assert "catena" in inputs, f"{nome}: manca l'input catena"
        c = inputs["catena"]
        assert str(c.get("default")) == "false", f"{nome}: catena deve valere 'false' a mano"
        assert "true" in [str(o) for o in c.get("options", [])], f"{nome}: catena senza opzione 'true'"
        assert len(inputs) <= 10, f"{nome}: troppi input (limite workflow_dispatch)"


# ---------------------------------------------------------------------------
# (4) i nomi: il prossimo anello esiste, ha workflow_dispatch e la staffetta
#     usa proprio PROSSIMO_ANELLO; l'elenco SQL coincide con la catena
# ---------------------------------------------------------------------------
def test_prossimo_anello_esiste_e_staffetta_coerente() -> None:
    tutti = _tutti()
    for nome in CATENA[:-1]:
        d = tutti[nome]
        p = _prossimo(d)
        assert p in tutti, f"{nome}: il prossimo anello {p!r} non esiste in .github/workflows"
        job = d["jobs"][LAVORO_STAFFETTA]
        cond = str(job.get("if", ""))
        assert "!cancelled()" in cond, f"{nome}: la staffetta deve partire solo se NON annullato"
        assert "inputs.catena == 'true'" in cond, f"{nome}: la staffetta deve partire solo con catena=true"
        altri = [j for j in d["jobs"] if j != LAVORO_STAFFETTA]
        needs = job.get("needs")
        needs = [needs] if isinstance(needs, str) else list(needs or [])
        assert sorted(needs) == sorted(altri), f"{nome}: la staffetta deve aspettare TUTTI i job ({altri}), needs={needs}"
        perm = job.get("permissions") or {}
        assert perm.get("actions") == "write", f"{nome}: la staffetta deve avere actions: write"
        passi = " ".join(str(s.get("run", "")) for s in job["steps"])
        assert 'passa_testimone.sh "$PROSSIMO_ANELLO"' in passi, f"{nome}: la staffetta non usa PROSSIMO_ANELLO"
    # l'ultimo anello non passa il testimone
    assert _prossimo(tutti[CATENA[-1]]) is None


def test_workflow_run_eventuali_citano_nomi_veri() -> None:
    """Rete per il futuro: un workflow_run con un nome sbagliato spezza la
    catena in silenzio."""
    nomi = {d.get("name") for d in _tutti().values()}
    for nome, d in _tutti().items():
        wr = _on(d).get("workflow_run")
        if wr:
            for w in wr.get("workflows", []):
                assert w in nomi, f"{nome}: workflow_run cita {w!r} che non esiste"


def test_elenco_sql_uguale_alla_catena() -> None:
    sql = open(MIGRAZIONE, encoding="utf-8").read()
    m = re.search(r"_orologio_catena\(\)\s*RETURNS text\[\].*?ARRAY\[(.*?)\]::text\[\]", sql, re.S)
    assert m, "funzione _orologio_catena non trovata"
    elenco = re.findall(r"'([a-z0-9_]+\.yml)'", m.group(1))
    assert elenco == CATENA, f"elenco SQL diverso dalla catena: {elenco}"


# ---------------------------------------------------------------------------
# regole dei singoli anelli
# ---------------------------------------------------------------------------
def test_concurrency_per_workflow_mai_cancellata() -> None:
    gruppi = []
    for nome in CATENA:
        c = _carica(nome).get("concurrency")
        assert c, f"{nome}: manca concurrency"
        assert c.get("cancel-in-progress") is False, f"{nome}: cancel-in-progress deve essere false"
        gruppi.append(c["group"])
    assert len(set(gruppi)) == len(gruppi), f"gruppo di concurrency condiviso: {gruppi}"


def test_retrain_regola_daily_success_e_auto_rilancio() -> None:
    daily = _carica("daily_yesterday_backfill.yml")
    st = daily["jobs"][LAVORO_STAFFETTA]["steps"][-1]
    assert st["env"]["MONTE_OK"] == "${{ needs.run-backfill.result == 'success' }}"
    assert 'monte_ok="$MONTE_OK"' in st["run"]

    r = _carica("retrain_models.yml")
    assert r["jobs"]["plan"]["if"] == "${{ inputs.monte_ok != 'false' }}"
    cond = r["jobs"][LAVORO_STAFFETTA]["if"]
    assert "needs.rechain.outputs.rilanciato != 'true'" in cond, "il retrain rilanciato non deve passare il testimone"
    assert r["jobs"]["rechain"]["outputs"]["rilanciato"] == "${{ steps.rilancio.outputs.rilanciato }}"
    passo = [s for s in r["jobs"]["rechain"]["steps"] if s.get("id") == "rilancio"][0]
    testo = passo["run"]
    i_out = testo.index('echo "rilanciato=true" >> "$GITHUB_OUTPUT"')
    i_gh = testo.index("gh workflow run retrain_models.yml")
    assert i_out < i_gh, "rilanciato=true va scritto PRIMA del lancio (mai due catene)"
    assert '-f catena="$CATENA"' in testo[i_gh:], "la run rilanciata deve ereditare catena"


def test_post_calibration_salta_se_retrain_saltato() -> None:
    r = _carica("retrain_models.yml")
    st = r["jobs"][LAVORO_STAFFETTA]["steps"][-1]
    assert st["env"]["RETRAIN_ESEGUITO"] == "${{ needs.plan.result == 'skipped' && 'false' || 'true' }}"
    c = _carica("ml_calibration.yml")
    # salta se il retrain e' stato saltato, TRANNE il lunedi' nella catena (FULL settimanale)
    assert c["jobs"]["assemble"]["if"] == (
        "${{ inputs.retrain_eseguito != 'false' || "
        "(inputs.catena == 'true' && needs.giorno.outputs.lunedi == 'true') }}")


def test_post_calibration_full_il_lunedi_nella_catena() -> None:
    """D3 (09/10/2026): FULL una volta a settimana dentro la catena (lunedi' UTC), altrimenti
    incrementale; a mano FULL solo con completa=true."""
    c = _carica("ml_calibration.yml")
    g = c["jobs"]["giorno"]
    assert "date -u +%u" in g["steps"][0]["run"] and '"$D" = "1"' in g["steps"][0]["run"]
    a = c["jobs"]["assemble"]
    assert a["needs"] == "giorno"
    passo = a["steps"][-1]
    assert passo["env"]["FULL_SETTIMANALE"] == "${{ inputs.catena == 'true' && needs.giorno.outputs.lunedi == 'true' }}"
    assert passo["env"]["COMPLETA"] == "${{ inputs.completa || 'false' }}"
    assert '[ "$COMPLETA" = "true" ] || [ "$FULL_SETTIMANALE" = "true" ]; then FULL="--full"' in passo["run"]
    assert 'compute_ml_post_calibration.py --min-n "$MIN_N" $FULL' in passo["run"]


def test_catchup_riserva_solo_per_results_nella_catena() -> None:
    """D1 (09/10/2026): nella catena il catchup tiene la quota solo per Predictions Results
    (che gira dopo); a mano la variabile e' vuota = riserva piena."""
    d = _carica("seasons_catchup.yml")
    env = d["jobs"]["catchup"]["steps"][-1]["env"]
    assert env["CATCHUP_RISERVA_PER"] == (
        "${{ inputs.catena == 'true' && 'predictions_results_backfill.yml' || '' }}")
    # cio' che resta da riservare e' davvero cio' che viene DOPO il catchup nella catena
    i = CATENA.index("seasons_catchup.yml")
    assert CATENA[i + 1:] == ["predictions_results_backfill.yml", "weekly_poisson_calibration.yml"]


def test_weekly_poisson_solo_lunedi_in_catena() -> None:
    d = _carica("weekly_poisson_calibration.yml")
    g = d["jobs"]["giorno"]
    assert "date -u +%u" in g["steps"][0]["run"]
    cal = d["jobs"]["calibrate"]
    assert cal["needs"] == "giorno"
    assert cal["if"] == "${{ inputs.catena != 'true' || needs.giorno.outputs.lunedi == 'true' }}"


def test_nessun_if_cita_ancora_schedule_o_workflow_run() -> None:
    for nome in CATENA:
        for j, job in _carica(nome)["jobs"].items():
            cond = str(job.get("if", ""))
            assert "'schedule'" not in cond and "workflow_run" not in cond, f"{nome}/{j}: if vecchio: {cond}"


# ---------------------------------------------------------------------------
# (5) la migrazione: pg_cron lancia SOLO il Daily, niente segreti
# ---------------------------------------------------------------------------
def _sql_senza_commenti() -> str:
    sql = open(MIGRAZIONE, encoding="utf-8").read()
    return "\n".join(r for r in sql.splitlines() if not r.lstrip().startswith("--"))


def test_migrazione_pg_cron_solo_daily_e_verifiche() -> None:
    sql = _sql_senza_commenti()
    job = re.findall(r"cron\.schedule\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*\$cmd\$(.*?)\$cmd\$\s*\)", sql, re.S)
    attesi = {
        "orologio_daily": ("12 0 * * *", "SELECT public.lancia_action('daily_yesterday_backfill.yml');"),
        "orologio_verifica_lancio": ("15 0 * * *", "SELECT public.verifica_lancio_action();"),
        "orologio_verifica_catena": ("30 7 * * *", "SELECT public.verifica_catena_notturna();"),
        "orologio_leggi_catena": ("33 7 * * *", "SELECT public.leggi_verifica_catena();"),
    }
    trovati = {n: (s, c.strip()) for n, s, c in job}
    assert trovati == attesi, f"job pg_cron diversi dal progetto: {trovati}"
    assert len(job) == len(attesi), "un job pg_cron schedulato due volte"
    assert sql.count("cron.schedule(") == len(attesi), "cron.schedule fuori dal blocco atteso"
    # lancia_action chiamata SOLO per il Daily (nessun altro lancio da pg_cron)
    chiamate = re.findall(r"lancia_action\('([^']+)'\)", sql)
    assert chiamate == ["daily_yesterday_backfill.yml"], f"lanci da pg_cron: {chiamate}"
    # ogni job tolto prima di essere rimesso (idempotenza)
    for n in attesi:
        assert f"'{n}'" in sql.split("PERFORM cron.schedule")[0], f"{n}: manca l'unschedule idempotente"


def test_migrazione_guardia_e_dispatch() -> None:
    sql = _sql_senza_commenti()
    assert "PRIMARY KEY (giorno, workflow_file)" in sql
    assert sql.count("ON CONFLICT") >= 2 and "DO NOTHING" in sql
    assert "vault.decrypted_secrets" in sql and "'github_actions_dispatch'" in sql
    assert "/actions/workflows/%s/dispatches" in sql
    assert "'X-GitHub-Api-Version', '2022-11-28'" in sql
    assert "'ref', 'master'" in sql
    assert "'{\"catena\": \"true\"}'" in sql, "il Daily deve partire con catena=true"
    assert "'ACTION_NON_PARTITA'" in sql and "'CATENA_NOTTURNA_INCOMPLETA'" in sql
    assert "IN (200, 204)" in sql


def test_nessun_segreto_nei_file_del_cantiere() -> None:
    sospetti = re.compile(r"(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{10,}")
    file = [MIGRAZIONE, SCRIPT] + [os.path.join(WF_DIR, n) for n in CATENA]
    for p in file:
        testo = open(p, encoding="utf-8").read()
        assert not sospetti.search(testo), f"{p}: stringa che sembra un token"
    sql = open(MIGRAZIONE, encoding="utf-8").read()
    assert "github_pat_" not in sql and "ghp_" not in sql


def test_file_nuovi_ascii() -> None:
    for p in (MIGRAZIONE, SCRIPT, os.path.abspath(__file__)):
        assert all(ord(c) < 128 for c in open(p, encoding="utf-8").read()), f"{p}: non ASCII"


# ---------------------------------------------------------------------------
# lo script della staffetta, con un gh finto
# ---------------------------------------------------------------------------
def _bash() -> Optional[str]:
    for c in (r"C:\Program Files\Git\bin\bash.exe", "/bin/bash", "/usr/bin/bash"):
        if os.path.exists(c):
            return c
    return None


GH_FINTO = r"""#!/usr/bin/env bash
# gh finto: registra la chiamata; `workflow run` riesce o fallisce secondo
# FINTO_ESITI (es. "1,0": primo fallisce, secondo riesce); `api ... --jq
# .total_count` stampa FINTO_CONTEGGIO (un intero come il vero) o fallisce.
echo "$*" >> "$FINTO_LOG"
if [ "$1" = "workflow" ] && [ "$2" = "run" ]; then
  N=$(grep -c "^workflow run" "$FINTO_LOG")
  E=$(echo "$FINTO_ESITI" | cut -d, -f"$N")
  [ -z "$E" ] && E=0
  exit "$E"
fi
if [ "$1" = "api" ]; then
  if [ "$FINTO_CONTEGGIO" = "errore" ]; then echo "HTTP 502" >&2; exit 1; fi
  echo "$FINTO_CONTEGGIO"
  exit 0
fi
exit 2
"""


def _staffetta(esiti: str, conteggio: str) -> tuple:
    bash = _bash()
    if not bash:
        pytest.skip("bash non disponibile")
    d = tempfile.mkdtemp(prefix="staffetta_")
    try:
        gh = os.path.join(d, "gh")
        with open(gh, "w", encoding="utf-8", newline="\n") as f:
            f.write(GH_FINTO)
        log = os.path.join(d, "log.txt")
        open(log, "w").close()
        env = dict(os.environ)
        env.update({
            "FINTO_LOG": log.replace("\\", "/"), "FINTO_ESITI": esiti, "FINTO_CONTEGGIO": conteggio,
            "PASSA_TESTIMONE_ATTESA_S": "0", "GITHUB_REF_NAME": "master",
            "GITHUB_REPOSITORY": "Dani91x/python-database-automation",
            "GITHUB_WORKFLOW": "Prova", "GITHUB_RUN_ID": "1",
        })
        dd = d.replace("\\", "/")
        if re.match(r"^[A-Za-z]:/", dd):        # Git Bash: C:/x -> /c/x
            dd = "/" + dd[0].lower() + dd[2:]
        cmd = f'export PATH="{dd}:$PATH"; chmod +x "{dd}/gh"; bash "{SCRIPT.replace(chr(92), "/")}" hazard_atlas.yml'
        p = subprocess.run([bash, "-c", cmd], env=env, capture_output=True, text=True, timeout=60)
        righe = open(log, encoding="utf-8").read().splitlines()
        return p.returncode, righe, p.stdout + p.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_staffetta_lancio_riuscito_una_chiamata() -> None:
    rc, righe, out = _staffetta("0", "0")
    assert rc == 0, out
    assert righe == ["workflow run hazard_atlas.yml --ref master -f catena=true"], righe


def test_staffetta_fallita_ma_run_creata_niente_secondo_lancio() -> None:
    rc, righe, out = _staffetta("1,0", "1")
    assert rc == 0, out
    assert sum(r.startswith("workflow run") for r in righe) == 1, righe
    assert any(r.startswith("api -X GET repos/Dani91x/python-database-automation/actions/workflows/hazard_atlas.yml/runs") for r in righe), righe


def test_staffetta_fallita_e_run_assente_un_solo_ritentativo() -> None:
    rc, righe, out = _staffetta("1,0", "0")
    assert rc == 0, out
    assert sum(r.startswith("workflow run") for r in righe) == 2, righe
    rc, righe, out = _staffetta("1,1,0", "0")
    assert rc == 1, out
    assert sum(r.startswith("workflow run") for r in righe) == 2, "mai piu' di due tentativi"


def test_staffetta_stato_illeggibile_non_rilancia() -> None:
    rc, righe, out = _staffetta("1,0", "errore")
    assert rc == 1, out
    assert sum(r.startswith("workflow run") for r in righe) == 1, righe
