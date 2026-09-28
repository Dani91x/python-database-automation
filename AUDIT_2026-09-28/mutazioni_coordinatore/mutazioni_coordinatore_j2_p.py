"""Mutazioni INDIPENDENTI del coordinatore sulla consegna N (28/09/2026).

Si lancia dalla radice del worktree di verifica (origin/master + patch N).
Per ogni mutazione: copia del file, sostituzione di UNA occorrenza (ancora a
riga singola o doppia, CRLF rispettato), test mirati, ripristino dalla copia,
md5. Non va MAI interrotto: il ripristino e' nel finally.
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

T_J = [
    "Betfair/mike/tests/test_mike_flusso_cantiere_j2_2026_09_28.py",
    "Betfair/safe_strategy/tests/test_flusso_interrotto_cantiere_j_2026_09_28.py",
    "Betfair/safe_strategy/tests/test_flusso_interrotto_cantiere_j_bis_2026_09_28.py",
    "Betfair/safe_strategy/tests/test_flusso_su_master_cantiere_j2_2026_09_28.py",
    "Betfair/mike/tests",
]
T_P = [
    "Betfair/safe_strategy/tests/test_p_nessun_fill_di_casa_2026_09_28.py",
    "Betfair/safe_strategy/tests/test_p_blocco3_2026_09_28.py",
    "Betfair/safe_strategy/tests/test_execution.py",
    "Betfair/safe_strategy/tests/test_bot_service.py",
    "Betfair/safe_strategy/tests",
]
T_PO = ["Betfair/omega"]
MS = "Betfair/mike/service.py"
SB = "Betfair/safe_strategy/bot_service.py"
SX = "Betfair/safe_strategy/execution.py"
FP = "Betfair/stream/flusso_prezzi.py"
MUTAZIONI: List[Tuple[str, str, str, str, int, List[str]]] = [
    ("J1 mike: col flusso fermo una APERTURA parte coi prezzi del ripiego REST", MS,
     "    if fonte_prezzi == F._flusso.FONTE_RIPIEGO_REST and leg.role in APERTURE_MIKE:",
     "    if False and fonte_prezzi == F._flusso.FONTE_RIPIEGO_REST and leg.role in APERTURE_MIKE:  # MUTAZIONE", 0, T_J),
    ("J2 flusso: il giro dello scanner bloccato non conta (stato vecchio = vivo)", FP,
     "        if eta > STATO_CALCOLO_MAX_S:",
     "        if False and eta > STATO_CALCOLO_MAX_S:  # MUTAZIONE", 0, T_J),
    ("J3 flusso: riga senza il blocco dichiarato data per viva anche con lo scanner nuovo", FP,
     "        if blocco_riga(payload) is None and stato_dichiara_flusso(stato):",
     "        if False and blocco_riga(payload) is None and stato_dichiara_flusso(stato):  # MUTAZIONE", 0, T_J),
    ("J4 flusso: un mercato fermo della decisione non ferma niente", FP,
     "    fermi_usati = [m for m in usati if m in fermi]",
     "    fermi_usati = []  # MUTAZIONE", 0, T_J),
    ("J5 safe: combo approvata con una gamba su mercato fermo accettata", SB,
     "        if isinstance(row_feed, dict) and not XE.flusso_esito(",
     "        if False and isinstance(row_feed, dict) and not XE.flusso_esito(  # MUTAZIONE", 0, T_J),
    ("P1 safe: il runner spento consuma i tentativi della partita", SB,
     "    if X.e_senza_runner(err):",
     "    if False and X.e_senza_runner(err):  # MUTAZIONE", 0, T_P),
    ("P2 safe: runner spento, il segnale diventa definitivo", SB,
     "                  \"last_ts\": now.isoformat(), \"final\": False, \"senza_runner\": True,",
     "                  \"last_ts\": now.isoformat(), \"final\": True, \"senza_runner\": True,  # MUTAZIONE", 0, T_P),
    ("P3 esecuzione: la riconciliazione ignora il riferimento del canale", SX,
     "    if not cor:",
     "    if True:  # MUTAZIONE", 0, T_P),
    ("P4 esecuzione: una chiusura paper con execution_mode rest non va al runner", SX,
     "    if mode == \"paper\" and str(params.get(\"execution_mode\") or \"auto\") != \"auto\":",
     "    if False and mode == \"paper\":  # MUTAZIONE", 0, T_P),
    ("P5 omega: il green-up confermato non porta lo stato a done", "Betfair/omega/omega_service.py",
     "                _greenup_fill_confermato(db, tr, now)",
     "                pass  # MUTAZIONE", 0, T_PO),
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
                    [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *esistenti],
                    cwd=str(RADICE), capture_output=True, text=True, errors="replace",
                    timeout=420)
            except subprocess.TimeoutExpired:
                esito = "ROSSA PER BLOCCO (test appesi oltre 420 s)"
                continue
            coda = [x for x in r.stdout.strip().splitlines() if x.strip()][-1:] or [""]
            falliti = [x for x in r.stdout.splitlines()
                       if x.startswith("FAILED") or x.startswith("ERROR")]
            if r.returncode == 0:
                esito = "SOPRAVVISSUTA (test verdi) | " + coda[0]
            else:
                esito = "ROSSA | " + (falliti[0][:150] if falliti else coda[0][:150])
        finally:
            shutil.copy2(copia, f)
            dopo = md5(f)
            ok = "ripristino OK" if dopo == prima else "!!! RIPRISTINO FALLITO !!!"
            esiti.append((nome, esito, ok, time.time() - t0))
            print("%-72s -> %s [%s, %.0f s]" % (nome[:72], esito, ok, time.time() - t0),
                  flush=True)
    sopravvissute = [e for e in esiti if e[1].startswith("SOPRAVVISSUTA")]
    non_appl = [e for e in esiti if e[1].startswith("NON APPLICATA")]
    rotti = [e for e in esiti if "FALLITO" in e[2]]
    print("\nTOTALE %d | rosse %d | SOPRAVVISSUTE %d | non applicate %d | ripristini falliti %d" % (
        len(esiti), len(esiti) - len(sopravvissute) - len(non_appl), len(sopravvissute),
        len(non_appl), len(rotti)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
