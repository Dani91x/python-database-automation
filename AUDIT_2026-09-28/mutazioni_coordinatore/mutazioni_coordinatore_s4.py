"""Mutazioni del COORDINATORE sul cantiere S4 (scratch firmato esatto: la pausa
anti-cascata e la regola della sequenza equivalente valgono solo nel flatten).

Due direzioni: la correzione tolta (il difetto torna) e la correzione
allargata troppo (l'anti-cascata del flatten sparisce). Ripristino da copia
in memoria con controllo dell'hash. Si lancia dalla radice del worktree.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PY = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.venv\Scripts\python.exe"
F = "Betfair/stream/scalper/scalper_bot.py"
TEST = ["Betfair/stream/tests", "-k", "scalper or cantiere_s"]

MUT: List[Tuple[str, bytes, bytes]] = [
    ("D1 la pausa di 30 s torna a valere anche fuori dal flatten",
     b"        rate_ok = (slot.status != FLATTENING\n",
     b"        rate_ok = (False\n"),
    ("D2 la sequenza di un'altra chiusura presa per propria",
     b"                    slot.status == FLATTENING\n                    and st_old is not None",
     b"                    True\n                    and st_old is not None"),
    ("D3 ALLARGATA: nessuna pausa nemmeno nel flatten",
     b"        rate_ok = (slot.status != FLATTENING\n",
     b"        rate_ok = (True\n"),
    ("D4 ALLARGATA: nel flatten la sequenza equivalente si ricrea",
     b"                    slot.status == FLATTENING\n                    and st_old is not None",
     b"                    False\n                    and st_old is not None"),
]


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def suite() -> Tuple[bool, str]:
    r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider", "-x"],
                       capture_output=True, text=True, timeout=900)
    coda = [x for x in (r.stdout or "").splitlines() if x.strip()][-1:]
    return r.returncode == 0, (coda[0] if coda else "?")


def main() -> int:
    ok, coda = suite()
    print("BASE (senza mutazioni): %s  %s" % ("VERDE" if ok else "ROSSA", coda), flush=True)
    if not ok:
        return 2
    p = Path(F)
    orig = p.read_bytes()
    crlf = b"\r\n" in orig
    vive = 0
    for nome, prima, dopo in MUT:
        a = prima.replace(b"\n", b"\r\n") if crlf else prima
        d = dopo.replace(b"\n", b"\r\n") if crlf else dopo
        n = orig.count(a)
        if n != 1:
            print("%-62s ANCORA NON UNICA (%d)" % (nome, n), flush=True)
            vive += 1
            continue
        try:
            p.write_bytes(orig.replace(a, d))
            verde, coda = suite()
        finally:
            p.write_bytes(orig)
        assert md5(p.read_bytes()) == md5(orig)
        errore = "error" in coda and "failed" not in coda
        print("%-62s %s  %s" % (nome, "SOPRAVVISSUTA" if verde else
                                ("ERRORE DI RACCOLTA" if errore else "rossa"), coda), flush=True)
        vive += 1 if (verde or errore) else 0
    print("mutazioni sopravvissute o non valide: %d su %d" % (vive, len(MUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
