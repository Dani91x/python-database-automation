"""Falsificazione dei fix del cantiere dati/action/atlante (26/09/2026).

Per ogni mutazione: legge i byte originali, rimette il bug (o una variante),
lancia i test nuovi (devono diventare ROSSI), ripristina i byte e verifica
l'uguaglianza byte per byte (come cmp). Non interrompere: il ripristino e' nel
``finally`` di ogni mutazione.

Uso (dalla radice del worktree/checkout):
    .venv\\Scripts\\python.exe AUDIT_2026-09-26\\falsifica_fix_dati_action_atlante.py
"""
import os
import subprocess
import sys

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
ENV = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x", SUPABASE_KEY="x")

T_CATCHUP = ["test_catchup_attesa_concorrenti_2026_09_26.py"]
T_CODA = ["Betfair/stream/tests/test_atlante_a_domanda_coda_scrittura_2026_09_26.py"]
T_RIF = ["Betfair/stream/tests/test_atlante_v4_stagione_rif_per_lega_2026_09_26.py"]
T_MIKE = ["Betfair/mike/tests/test_mike_atlante_frame_dossier_2026_09_26.py"]

MUT = [
    ("M1a main non aspetta", "seasons_catchup.py",
     "    attendi_action_concorrenti(concorrenza, _env_int(",
     "    (lambda *a, **k: None)(concorrenza, _env_int(", T_CATCHUP),
    ("M1b attesa che non aspetta", "seasons_catchup.py",
     "        if minuti >= attesa_max_min:", "        if True:", T_CATCHUP),
    ("M2 coda per primo ko (bug O-1)", "Betfair/stream/scalper/atlante_a_domanda.py",
     "nuove.sort(key=lambda l: (fascia.get(l, 2), primo_ko.get(l, adesso)))",
     "nuove.sort(key=lambda l: primo_ko.get(l, adesso))", T_CODA),
    ("M2b fascia senza in-play", "Betfair/stream/scalper/atlante_a_domanda.py",
     "    if ko <= adesso < ko + fine_s:", "    if False:", T_CODA),
    ("M3 doppia scrittura (bug O-3)", "Betfair/stream/scalper/atlante_a_domanda.py",
     "        prep_prima = list(self.in_preparazione)",
     "        prep_prima = list(self.in_preparazione)\r\n        if nuove[:1]:\r\n            self._scrivi_live(adesso)",
     T_CODA),
    ("M3b niente scrittura se cambia solo in_preparazione", "Betfair/stream/scalper/atlante_a_domanda.py",
     "riscrivi = (cambiato or self.in_preparazione != prep_prima", "riscrivi = (cambiato", T_CODA),
    ("M4 riferimento globale (bug O-4)", "Betfair/stream/scalper/genera_atlante.py",
     "rif = {lid: max(int(x) for x in v[\"stagioni\"]) + 1 for lid, v in vista.items()}",
     "rif = max(int(x) for v in vista.values() for x in v[\"stagioni\"]) + 1", T_RIF),
    ("M4b assembla ignora il dict", "Betfair/stream/scalper/atlante_v4.py",
     "w = _peso(int(st), rif_per_lega[str(lid)], emivita)",
     "w = _peso(int(st), max(rif_per_lega.values()), emivita)", T_RIF),
    ("M5 frame senza chiavi v4 (bug R-FA-2)", "Betfair/mike/service.py",
     "\"hazard_versione\": live.get(\"hazard_versione\"), \"hazard_fase\": live.get(\"hazard_fase\"),",
     "", T_MIKE),
    ("M5b frame senza nota/recupero", "Betfair/mike/service.py",
     "                  \"hazard_nota\": live.get(\"hazard_nota\"),", "", T_MIKE),
    ("M6 dossier: lega solo coi lambda (bug R-FA-3)", "Betfair/mike/dossier.py",
     "        if lam:\r\n            # R-FA-3", "        if lam and lam[0] is not None:\r\n            # R-FA-3", T_MIKE),
    ("M6b produttore: None senza lambda", "Betfair/stream/db.py",
     "    if con_squadre:\r\n        # R-FA-3", "    if False:\r\n        # R-FA-3", T_MIKE),
]


def main() -> int:
    esiti = []
    for nome, rel, vecchio, nuovo, test in MUT:
        path = os.path.join(WT, rel)
        with open(path, "rb") as f:
            orig = f.read()
        testo = orig.decode("utf-8")
        n = testo.count(vecchio)
        if n != 1:
            esiti.append((nome, "MUTAZIONE NON APPLICABILE (occorrenze %d)" % n))
            continue
        try:
            with open(path, "wb") as f:
                f.write(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", *test], cwd=WT, env=ENV,
                               capture_output=True, text=True)
            righe = [x for x in r.stdout.splitlines() if x.strip()]
            fondo = righe[-1] if righe else r.stderr[-200:]
            rossi = [x.split("::")[-1].split(" ")[0] for x in r.stdout.splitlines() if x.startswith("FAILED")]
            esiti.append((nome, ("ROSSO " if r.returncode else "VERDE (falsificazione FALLITA) ") + fondo
                          + " | " + ", ".join(rossi)))
        finally:
            with open(path, "wb") as f:
                f.write(orig)
            with open(path, "rb") as f:
                assert f.read() == orig, "RIPRISTINO FALLITO " + rel
    for nome, e in esiti:
        print("%s: %s" % (nome, e))
    print("ripristino verificato byte per byte su tutti i file mutati")
    return 0 if all(e.startswith("ROSSO") for _, e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
