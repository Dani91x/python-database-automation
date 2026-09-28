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

T_M = [
    "Betfair/mike/tests/test_mike_d1bis_freno_coperture_runner_2026_09_28.py",
    "Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py",
    "Betfair/mike/tests",
]
MUTAZIONI: List[Tuple[str, str, str, str, int, List[str]]] = [
    ("F1 lo stesso evento terminale riletto si conta due volte", "Betfair/mike/service.py",
     "            if no_definitivo and seq > gia:",
     "            if no_definitivo:  # MUTAZIONE", 0, T_M),
    ("F2 il ramo del runner conta solo 'rifiutato' (FOK ucciso non contato)", "Betfair/mike/service.py",
     "            no_definitivo = not appoggiata and fase in (\"rifiutato\", \"annullato\", \"scaduto\")",
     "            no_definitivo = not appoggiata and fase in (\"rifiutato\",)  # MUTAZIONE", 0, T_M),
    ("F3 il ramo del runner conta anche l'esito IGNOTO (fase errore)", "Betfair/mike/service.py",
     "            no_definitivo = not appoggiata and fase in (\"rifiutato\", \"annullato\", \"scaduto\")",
     "            no_definitivo = not appoggiata  # MUTAZIONE", 0, T_M),
    ("F4 il ramo del runner conta anche la lay appoggiata scaduta", "Betfair/mike/service.py",
     "            no_definitivo = not appoggiata and fase in (\"rifiutato\", \"annullato\", \"scaduto\")",
     "            no_definitivo = fase in (\"rifiutato\", \"annullato\", \"scaduto\")  # MUTAZIONE", 0, T_M),
    ("F5 freno unico: in paper sul runner le aperture passano a freno tirato", "Betfair/mike/service.py",
     "    if blocco_paper:",
     "    if False and blocco_paper:  # MUTAZIONE", 0, T_M),
    ("F6 freno unico: a freno tirato si ferma anche la CHIUSURA", "Betfair/mike/service.py",
     "                    if porta_paper is not None and not chiude_exec else None)",
     "                    if porta_paper is not None else None)  # MUTAZIONE", 0, T_M),
    ("F7 il conteggio non arriva al motore (funzione comune senza registrazione)", "Betfair/mike/service.py",
     "    if leg.role == \"over_cover\" and ctx is not None:",
     "    if False and leg.role == \"over_cover\" and ctx is not None:  # MUTAZIONE", 0, T_M),
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
            r = subprocess.run(
                [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *esistenti],
                cwd=str(RADICE), capture_output=True, text=True, errors="replace")
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
