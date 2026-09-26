# -*- coding: utf-8 -*-
"""Falsificazione F-11 (26/09): rimette il follow automatico all'apertura del
Tennis Terminal (e una variante: bottone che non segue); vitest DEVE tornare
rosso. Ripristino dal testo in memoria + sha256. Non interrompere.

Uso (dalla radice): .venv/Scripts/python.exe AUDIT_2026-09-26/falsifica_terminal_f11.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess

PAG = "frontend/src/pages/TennisTerminal.tsx"
MUT = [
    ("F1 follow automatico all'apertura (il bug)",
     "    const segui = async () => {",
     "    useEffect(() => {\n        if (!eventId || !marketId) return;\n"
     "        followTennisEvent(eventId, marketId).catch(() => {});\n"
     "    }, [eventId, marketId]);\n    const segui = async () => {"),
    ("F2 il bottone non chiama la rpc",
     "            await followTennisEvent(eventId, marketId);\n            setSeguita(true);",
     "            setSeguita(true);"),
    ("F3 nessun avviso a partita non seguita",
     "                            {seguita === false && !seguiError && (",
     "                            {false && ("),
]


def main() -> int:
    with open(PAG, encoding="utf-8", newline="") as fh:
        orig = fh.read()
    sha0 = hashlib.sha256(orig.encode("utf-8")).hexdigest()
    nl = "\r\n" if "\r\n" in orig else "\n"
    ok = True
    for nome, old, new in MUT:
        old, new = old.replace("\n", nl), new.replace("\n", nl)
        if orig.count(old) != 1:
            print(nome, "ANCORA NON TROVATA")
            ok = False
            continue
        try:
            with open(PAG, "w", encoding="utf-8", newline="") as fh:
                fh.write(orig.replace(old, new))
            r = subprocess.run("npx vitest run src/pages/TennisTerminal.test.tsx",
                               cwd="frontend", shell=True, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            righe = [x for x in r.stdout.splitlines() if "Tests" in x]
            esito = "ROSSO" if r.returncode != 0 else "VERDE(!)"
            ok = ok and r.returncode != 0
            print("%-44s %s %s" % (nome, esito, righe[-1].strip() if righe else ""))
        finally:
            with open(PAG, "w", encoding="utf-8", newline="") as fh:
                fh.write(orig)
            with open(PAG, encoding="utf-8", newline="") as fh:
                assert hashlib.sha256(fh.read().encode("utf-8")).hexdigest() == sha0
    return 0 if ok else 1


if __name__ == "__main__":
    os.environ.setdefault("FORCE_COLOR", "0")
    raise SystemExit(main())
