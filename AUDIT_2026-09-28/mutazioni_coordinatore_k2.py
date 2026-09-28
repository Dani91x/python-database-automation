"""Mutazioni INDIPENDENTI del coordinatore sulla consegna D2 (28/09/2026).

Si lancia dalla radice del worktree di verifica (origin/master + patch D2).
Per ogni mutazione: copia del file, sostituzione di UNA occorrenza (ancora a
riga singola, CRLF rispettato), test mirati, ripristino dalla copia, md5.
Non va MAI interrotto: il ripristino e' nel finally.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

PY = sys.executable
RADICE = Path.cwd()
COPIE = Path(__file__).resolve().parent / "copie_mutazioni"
COPIE.mkdir(exist_ok=True)

T_K = [
    "Betfair/stream/tests/test_arresto_ordinato_comportamento_2026_09_28.py",
    "Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py",
    "Betfair/stream/tests/test_arresto_ordinato_2026_09_28.py",
    "Betfair/stream/tests/test_avviatore_watchdog_2026_09_28.py",
]
A = "        if _AO.richiesto():"
MUTAZIONI: List[Tuple[str, str, str, str, int, List[str]]] = [
    ("K1 omega: il guscio non guarda l'arresto", "Betfair/omega/omega_service.py",
     A, "        if False and _AO.richiesto():  # MUTAZIONE", 0, T_K),
    ("K2 omega: main non usa il guscio (cablaggio)", "Betfair/omega/omega_service.py",
     "        _ciclo_persistente(_un_giro, label=\"[omega]\")",
     "        while _un_giro():  # MUTAZIONE\n            pass", 0, T_K),
    ("K3 mike: il guscio non guarda l'arresto", "Betfair/mike/service.py",
     "        if controlla_arresto and _AO.richiesto():",
     "        if False and controlla_arresto and _AO.richiesto():  # MUTAZIONE", 0, T_K),
    ("K4 mike: main spegne il controllo (cablaggio)", "Betfair/mike/service.py",
     "controlla_arresto=not args.once)", "controlla_arresto=False)  # MUTAZIONE", 0, T_K),
    ("K5 mike: l'arresto interrompe anche un --once", "Betfair/mike/service.py",
     "        if controlla_arresto and _AO.richiesto():",
     "        if _AO.richiesto():  # MUTAZIONE", 0, T_K),
    ("K6 scanner safe: il giro non guarda l'arresto", "Betfair/safe_strategy/service.py",
     "    if _AO.richiesto():", "    if False and _AO.richiesto():  # MUTAZIONE", 0, T_K),
    ("K7 scanner safe: main non usa il ciclo (cablaggio)", "Betfair/safe_strategy/service.py",
     "        _ciclo_persistente(scan)",
     "        while True:  # MUTAZIONE\n            scan.tick()\n            time.sleep(0.5)", 0, T_K),
    ("K8 bot safe: il guscio non guarda l'arresto", "Betfair/safe_strategy/bot_service.py",
     A, "        if False and _AO.richiesto():  # MUTAZIONE", 0, T_K),
    ("K9 sessione scalper: non vede l'arresto", "Betfair/stream/scalper/scalper_session.py",
     A, "        if False and _AO.richiesto():  # MUTAZIONE", 0, T_K),
    ("K10 supervisore scalper: solo il file, non l'arresto (cablaggio)",
     "Betfair/stream/scalper/scalper_service.py",
     "        return os.path.isfile(KILL_FILE) or _AO.richiesto()",
     "        return os.path.isfile(KILL_FILE)  # MUTAZIONE", 0, T_K),
    ("K11 supervisore scalper: chi resta non viene terminato",
     "Betfair/stream/scalper/scalper_service.py",
     "        p.terminate()", "        pass  # MUTAZIONE", 0, T_K),
    ("K12 supervisore scalper: il giro parte anche col freno",
     "Betfair/stream/scalper/scalper_service.py",
     "            ferma_per_kill_switch()\n            return",
     "            ferma_per_kill_switch()  # MUTAZIONE", 0, T_K),
    ("K13 servizio tennis: non vede l'arresto", "Betfair/stream/tennis_live/tennis_bot_service.py",
     A, "        if False and _AO.richiesto():  # MUTAZIONE", 0, T_K),
]


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def sostituisci(testo: bytes, vecchio: str, nuovo: str, quale: int) -> bytes:
    crlf = b"\r\n" in testo
    v = vecchio.encode("utf-8")
    n = nuovo.encode("utf-8")
    if crlf:
        v = v.replace(b"\n", b"\r\n")
        n = n.replace(b"\n", b"\r\n")
    pos = -1
    for _ in range(quale + 1):
        pos = testo.find(v, pos + 1)
        if pos < 0:
            raise LookupError("ancora non trovata")
    return testo[:pos] + n + testo[pos + len(v):]


def main() -> int:
    esiti = []
    for nome, rel, vecchio, nuovo, quale, test in MUTAZIONI:
        f = RADICE / rel
        copia = COPIE / (rel.replace("/", "__") + ".orig")
        shutil.copy2(f, copia)
        prima = md5(f)
        esito = "?"
        t0 = time.time()
        try:
            try:
                f.write_bytes(sostituisci(f.read_bytes(), vecchio, nuovo, quale))
            except LookupError:
                esito = "NON APPLICATA (ancora non trovata)"
                continue
            esistenti = [t for t in test if (RADICE / t).exists()]
            try:
                r = subprocess.run(
                    [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                     # rossi GIA' su master (Mike paper sul runner, cantiere D1-bis):
                     # senza toglierli ogni mutazione sembrerebbe rossa
                     "--deselect", "Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py::test_mike_paper_apertura_ferma_col_freno",
                     "--deselect", "Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py::test_mike_paper_chiusura_passa_col_freno",
                     "--deselect", "Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py::test_mike_paper_freno_rilasciato_parita",
                     *esistenti],
                    cwd=str(RADICE), capture_output=True, text=True, errors="replace",
                    timeout=240)
            except subprocess.TimeoutExpired:
                esito = "ROSSA PER BLOCCO (test appesi oltre 240 s: nessun test la ferma con un'asserzione)"
                continue
            coda = [x for x in r.stdout.strip().splitlines() if x.strip()][-1:] or [""]
            falliti = [x for x in r.stdout.splitlines() if x.startswith("FAILED") or x.startswith("ERROR")]
            if r.returncode == 0:
                esito = "SOPRAVVISSUTA (test verdi) | " + coda[0]
            else:
                esito = "ROSSA | " + (falliti[0][:150] if falliti else coda[0][:150])
        finally:
            shutil.copy2(copia, f)
            dopo = md5(f)
            ok = "ripristino OK" if dopo == prima else "!!! RIPRISTINO FALLITO !!!"
            esiti.append((nome, esito, ok, time.time() - t0))
            print("%-75s -> %s [%s, %.0f s]" % (nome[:75], esito, ok, time.time() - t0), flush=True)
    sopravvissute = [e for e in esiti if e[1].startswith("SOPRAVVISSUTA")]
    non_appl = [e for e in esiti if e[1].startswith("NON APPLICATA")]
    rotti = [e for e in esiti if "FALLITO" in e[2]]
    print("\nTOTALE %d | rosse %d | SOPRAVVISSUTE %d | non applicate %d | ripristini falliti %d" % (
        len(esiti), len(esiti) - len(sopravvissute) - len(non_appl), len(sopravvissute),
        len(non_appl), len(rotti)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
