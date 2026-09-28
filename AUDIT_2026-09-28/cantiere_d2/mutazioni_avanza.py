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

T_CONDOTTA = [
    "Betfair/stream/tennis_live/tests/test_cantiere_d2_chiusure_via_bot_2026_09_28.py",
    "Betfair/stream/tennis_scalper/tests/test_condotta_ordini_2026_09_17.py",
    "Betfair/stream/tennis_live/tests/test_cantiere_d2_chiusure_esatte_2026_09_28.py",
    "Betfair/stream/tennis_live/tests/test_cantiere_d2_minimo_e_specchio_2026_09_28.py",
]
T_BOT = T_CONDOTTA + [
    "Betfair/stream/tennis_scalper/tests/test_tennis_pro.py",
    "Betfair/stream/tennis_scalper/tests/test_tennis_flb.py",
    "Betfair/stream/tennis_scalper/tests/test_tennis_swing.py",
    "Betfair/stream/tennis_scalper/tests/test_reperti_money_critical_2026_09_17.py",
]
T_MOTORE = T_CONDOTTA + [
    "Betfair/stream/tennis_live/tests/test_motore_ordini_tennis_2026_09_25.py",
    "Betfair/stream/tests/test_motore_ordini_2026_09_24.py",
]
T_RUNNER = T_CONDOTTA + [
    "Betfair/stream/tennis_live/tests/test_tennis_audit_runner.py",
    "Betfair/stream/tennis_live/tests/test_tennis_bot_params.py",
    "Betfair/stream/tennis_live/tests/test_paper_execution_gap5.py",
    "Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py",
]

# (nome, file, vecchio, nuovo, quale occorrenza (0 = prima), test)
MUTAZIONI: List[Tuple[str, str, str, str, int, List[str]]] = [
    ("P4 bot pro: le chiusure esatte non avanzano a ogni book",
     "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
     "        self._esatte.avanza(market)",
     "        pass  # MUTAZIONE",
     0, T_BOT),
    ("P5 bot flb: le chiusure esatte non avanzano a ogni book",
     "Betfair/stream/tennis_scalper/tennis_flb_bot.py",
     "        self._esatte.avanza(market)",
     "        pass  # MUTAZIONE",
     0, T_BOT),
    ("P2 bot swing: le chiusure esatte non avanzano a ogni book",
     "Betfair/stream/tennis_scalper/tennis_swing_bot.py",
     "        self._esatte.avanza(market)",
     "        pass  # MUTAZIONE",
     0, T_BOT),
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
