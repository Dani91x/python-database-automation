# -*- coding: utf-8 -*-
"""Bisezione dell'inquinatore minimo di un test che cade in ordine INVERSO.

    python AUDIT_2026-10-02/bisezione_inquinatore.py <cartella> <nodeid bersaglio>

Raccoglie i test della cartella, prende quelli che in ordine inverso girano
PRIMA del bersaglio, e dimezza finche' resta il singolo test che, eseguito
prima del bersaglio, lo rende rosso (plugin ``ordine_test_plugin``,
``ORDINE_TEST=elenco:<file>``). Assunzione: un inquinatore singolo basta.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
AUDIT = Path(__file__).resolve().parent


def corri(cartella: str, ordine: list[str]) -> bool:
    """True = bersaglio (ultimo) ROSSO."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(ordine))
        nome = fh.name
    env = dict(os.environ, ORDINE_TEST=f"elenco:{nome}",
               PYTHONPATH=str(AUDIT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    p = subprocess.run([sys.executable, "-m", "pytest", cartella, "-q", "-p", "no:cacheprovider",
                        "-p", "ordine_test_plugin"], cwd=RADICE, capture_output=True,
                       text=True, env=env, encoding="utf-8", errors="replace")
    os.unlink(nome)
    return any(r.startswith("FAILED") and ordine[-1] in r for r in p.stdout.splitlines())


def main() -> None:
    cartella, bersaglio = sys.argv[1], sys.argv[2]
    p = subprocess.run([sys.executable, "-m", "pytest", cartella, "--collect-only", "-q",
                        "-p", "no:cacheprovider"], cwd=RADICE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    ids = [r.strip() for r in p.stdout.splitlines() if "::" in r]
    i = ids.index(bersaglio)
    candidati = list(reversed(ids[i + 1:]))      # in inverso girano prima
    print(f"candidati: {len(candidati)}", flush=True)
    if not corri(cartella, candidati + [bersaglio]):
        print("NON riprodotto con tutti i candidati")
        return
    while len(candidati) > 1:
        meta = len(candidati) // 2
        a, b = candidati[:meta], candidati[meta:]
        if corri(cartella, a + [bersaglio]):
            candidati = a
        elif corri(cartella, b + [bersaglio]):
            candidati = b
        else:
            print(f"serve una COMBINAZIONE (nessuna meta' basta da sola): {len(candidati)} rimasti")
            break
        print(f"  rimasti {len(candidati)}", flush=True)
    print("INQUINATORE:", candidati if len(candidati) <= 5 else len(candidati))
    if len(candidati) == 1:
        print("conferma da solo:", "ROSSO" if corri(cartella, candidati + [bersaglio]) else "VERDE")


if __name__ == "__main__":
    main()
