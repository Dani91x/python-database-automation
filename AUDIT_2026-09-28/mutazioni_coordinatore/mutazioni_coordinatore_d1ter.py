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

T_D = [
    "Betfair/mike/tests/test_mike_d1ter_esito_ignoto_runner_2026_09_28.py",
    "Betfair/mike/tests/test_mike_d1ter_submin_fok_parita_2026_09_28.py",
    "Betfair/mike/tests/test_mike_d1bis_freno_coperture_runner_2026_09_28.py",
    "Betfair/stream/tests/test_motore_ritiro_pendente_d1ter_2026_09_28.py",
    "Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py",
    "Betfair/mike/tests",
]
MO = "Betfair/stream/motore_ordini.py"
MS = "Betfair/mike/service.py"
MUTAZIONI: List[Tuple[str, str, str, str, int, List[str]]] = [
    ("T1 motore: terminale emesso anche a ordine vivo", MO,
     "        if not morto:", "        if False and not morto:  # MUTAZIONE", 0, T_D),
    ("T2 motore: il ritiro pendente non si ritenta", MO,
     "            if s.get(\"ritiro_pendente\"):",
     "            if False and s.get(\"ritiro_pendente\"):  # MUTAZIONE", 0, T_D),
    ("T3 motore: ordine senza bet_id dato per morto", MO,
     "            elif _ordine_terminale(ordine):",
     "            elif True or _ordine_terminale(ordine):  # MUTAZIONE", 0, T_D),
    ("T4 mike: fase errore torna 'annullata' (esito ignoto dato per morto)", MS,
     "        if fase == \"errore\":\n", "        if False and fase == \"errore\":  # MUTAZIONE\n", 0, T_D),
    ("T5 mike: la lay appoggiata scaduta fa avanzare il freno", MS,
     "            no_definitivo = (not appoggiata and not ignoto_prima",
     "            no_definitivo = (not ignoto_prima  # MUTAZIONE", 0, T_D),
    ("T6 mike: un esito ignoto poi morto fa avanzare il freno", MS,
     "            no_definitivo = (not appoggiata and not ignoto_prima",
     "            no_definitivo = (not appoggiata  # MUTAZIONE", 0, T_D),
    ("T7 porta di Mike: il taker non dichiara il FOK sotto il minimo",
     "Betfair/mike/porta_ordini.py",
     "        self.submin_fill_or_kill = not self.appoggiata",
     "        self.submin_fill_or_kill = False  # MUTAZIONE", 0, T_D),
    ("T8 esecuzione: il piano del live non viene mai consultato in paper",
     "Betfair/safe_strategy/execution.py",
     "    if not getattr(porta, \"submin_fill_or_kill\", False):",
     "    if True:  # MUTAZIONE", 0, T_D + ["Betfair/safe_strategy/tests/test_execution.py"]),
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
