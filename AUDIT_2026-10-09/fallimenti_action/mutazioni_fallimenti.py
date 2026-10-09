"""Falsificazione dei test di test_fallimenti_action_2026_10_09.py (09/10/2026).

Ogni mutazione cambia UNA riga del codice corretto; i test devono diventare rossi.
Ripristino dai byte originali e controllo sha256 file per file. Uso (dalla radice del worktree):
    .venv/Scripts/python.exe AUDIT_2026-10-09/fallimenti_action/mutazioni_fallimenti.py
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys

WF = ".github/workflows/"
MUT = [
    ("M01 trasporto mai montato", "db_client.py",
     "    if resilienza_action_attiva():\r\n        # 09/10",
     "    if False and resilienza_action_attiva():\r\n        # 09/10"),
    ("M02 insert puro ritentato su esito ambiguo", "db_client.py",
     '    return "resolution=" in prefer', '    return True'),
    ("M03 RPC che scrive ritentata su esito ambiguo", "db_client.py",
     'return path.rsplit("/rpc/", 1)[1].strip("/") in RPC_LETTURA_ACTION', 'return True'),
    ("M04 522 trattato come ambiguo", "db_client.py",
     '        return "non_consegnata"\r\n    if status in STATUS_AMBIGUI:',
     '        return "ambigua"\r\n    if status in STATUS_AMBIGUI:'),
    ("M05 500 JSON (57014) ritentato", "db_client.py",
     'if status == 500 and "html" in (content_type or "").lower():',
     'if status == 500:'),
    ("M06 niente attesa lunga", "db_client.py",
     "    return tuple(ATTESE_RETE_S) + (lunga,)", "    return tuple(ATTESE_RETE_S)"),
    ("M07 interruttore ignorato dal trasporto", "db_client.py",
     "            attese = ()                                   # interruttore aperto: un tentativo solo\r\n        dormi = self._dormi",
     "            pass\r\n        dormi = self._dormi"),
    ("M08 il trasporto ritenta anche dentro con_ritentativi", "db_client.py",
     'if "/rest/v1/" not in path or getattr(_TLS, "dentro_ritentativi", False):',
     'if "/rest/v1/" not in path:'),
    ("M09 main: nessuna riga chiara (risale tutto)", "db_client.py",
     "        classe = classifica_guasto_rete(e)\r\n        if classe is None:\r\n            raise\r\n        import sys",
     "        classe = None\r\n        if classe is None:\r\n            raise\r\n        import sys"),
    ("M10 main: inghiotte anche gli errori di codice", "db_client.py",
     "        classe = classifica_guasto_rete(e)\r\n        if classe is None:\r\n            raise\r\n        import sys",
     "        classe = classifica_guasto_rete(e) or 'x'\r\n        if classe is None:\r\n            raise\r\n        import sys"),
    ("M11 variabile d'ambiente ignorata", "db_client.py",
     'return (os.environ.get(ENV_RESILIENZA_ACTION) or "").strip().lower() in ("1", "true", "si", "on")',
     'return False'),
    ("M12 ritenta anche fuori da /rest/v1/", "db_client.py",
     'if "/rest/v1/" not in path or getattr(', 'if False and "/rest/v1/" not in path or getattr('),
    ("M13 planner inghiotte di nuovo il guasto di rete", "training_planner.py",
     "        if classifica_guasto_rete(e) is not None:\r\n            raise\r\n",
     "        if False:\r\n            raise\r\n"),
    ("M14 planner senza attese lunghe", "training_planner.py",
     "ATTESE_LUNGHE_PLANNER_S = (60.0, 120.0, 240.0)", "ATTESE_LUNGHE_PLANNER_S = ()"),
    ("M15 rechain rosso sul guasto DB", WF + "retrain_models.yml",
     '            echo "$MSG" >> "$GITHUB_STEP_SUMMARY"\r\n            exit 0',
     '            echo "$MSG" >> "$GITHUB_STEP_SUMMARY"\r\n            exit 1'),
    ("M16 rechain rilancia senza controllo anti-doppio", WF + "retrain_models.yml",
     '          if [ "$CREATE" -gt 0 ]; then', '          if false; then'),
    ("M17 rechain rilancia con stato illeggibile", WF + "retrain_models.yml",
     '            echo "::error::[RECHAIN] stato delle run illeggibile: NON rilancio (evito un doppio)."\r\n            exit 1',
     '            echo "::error::[RECHAIN] stato delle run illeggibile: NON rilancio (evito un doppio)."\r\n            CREATE=0'),
    ("M18 atlante: gia_scritto ignorato", "Betfair/stream/scalper/genera_atlante.py",
     "if gia_scritto is not None and code != 500 and gia_scritto():",
     "if False and gia_scritto is not None and code != 500 and gia_scritto():"),
    ("M19 atlante: controllo anche dopo il 500 (57014)", "Betfair/stream/scalper/genera_atlante.py",
     "if gia_scritto is not None and code != 500 and gia_scritto():",
     "if gia_scritto is not None and gia_scritto():"),
    ("M20 atlante: JSON non compatto", "Betfair/stream/scalper/genera_atlante.py",
     'json.dumps(corpo, separators=(",", ":"))', "json.dumps(corpo)"),
    ("M21 pre-controllo atlante senza ritentativi", WF + "hazard_atlas.yml",
     "              attese = (5, 15, 45, 90)", "              attese = ()"),
    ("M22 Daily senza tetto di tempo", WF + "daily_yesterday_backfill.yml",
     "    timeout-minutes: 120\r\n", ""),
    ("M23 Post-Cal di nuovo senza versione fissa", WF + "ml_calibration.yml",
     "        run: python -m pip install -r requirements-planner.txt",
     "        run: python -m pip install --upgrade pip supabase python-dotenv"),
    ("M24 leagues_mapper non passa da esegui_main_action", "leagues_mapper.py",
     'esegui_main_action(run_full_leagues_backfill_mapping, "leagues_mapper.py")',
     "run_full_leagues_backfill_mapping()"),
    ("M25 timeout di lettura non ritentato", "db_client.py",
     "    if classifica_guasto_rete(exc) is not None:\r\n        return \"ambigua\"",
     "    if classifica_guasto_rete(exc) not in (None, 'timeout_rete'):\r\n        return \"ambigua\""),
    ("M26 rechain: piano gate senza resilienza d'ambiente", WF + "retrain_models.yml",
     '          DB_RESILIENZA_ACTION: "1"\r\n        run: |\r\n          python - <<\'PY\'\r\n          import os',
     '        run: |\r\n          python - <<\'PY\'\r\n          import os'),
]


def sha(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main() -> int:
    file = sorted({m[1] for m in MUT})
    prima = {f: sha(f) for f in file}
    esito = []
    for nome, f, vecchio, nuovo in MUT:
        orig = open(f, "rb").read()
        testo = orig.decode("utf-8")
        if testo.count(vecchio) != 1:
            esito.append((nome, f"NON APPLICABILE ({testo.count(vecchio)} occorrenze)"))
            continue
        open(f, "wb").write(testo.replace(vecchio, nuovo).encode("utf-8"))
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", "test_fallimenti_action_2026_10_09.py",
                                "-q", "-p", "no:cacheprovider"], capture_output=True, text=True)
        finally:
            open(f, "wb").write(orig)
        rossi = sorted(set(re.findall(r"FAILED \S+::(\S+)", r.stdout)))
        esito.append((nome, f"{len(rossi)} rossi: {', '.join(rossi)}" if rossi else "VERDE (test cieco!)"))
        print(esito[-1], flush=True)
    dopo = {f: sha(f) for f in file}
    print("\nRIPRISTINO:", "sha256 identico su tutti i file" if dopo == prima else f"DIVERSO: {dopo}")
    with open("AUDIT_2026-10-09/fallimenti_action/mutazioni_esito.txt", "w", encoding="utf-8") as fh:
        for n, e in esito:
            fh.write(f"{n}: {e}\n")
        fh.write("ripristino sha256: " + ("identico" if dopo == prima else "DIVERSO") + "\n")
    return 0 if dopo == prima else 1


if __name__ == "__main__":
    sys.exit(main())
