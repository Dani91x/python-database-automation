# -*- coding: utf-8 -*-
"""Elenca ogni ``delenv(...)`` dei test su una variabile che sta nel ``.env`` vero.

Lancio: ``python AUDIT_2026-10-02/cerca_delenv_env.py <percorso del .env>``

Del ``.env`` legge SOLO i NOMI (la parte prima di ``=``): i valori non vengono
mai letti in una variabile, stampati o scritti. Stampa:
  ENV       delenv con nome letterale presente nel .env
  COSTANTE  delenv con argomento non letterale (da risolvere a mano)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
_NOME = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_DELENV = re.compile(r"delenv\(\s*([^,)]+)")


def nomi_env(percorso: Path) -> set[str]:
    out: set[str] = set()
    for riga in percorso.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _NOME.match(riga)
        if m:
            out.add(m.group(1))
    return out


_COSTANTE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*[A-Za-z]+\s*)?=\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")


def mappa_costanti() -> dict[str, set[str]]:
    """``NOME_COSTANTE -> {valori}`` per ogni ``NOME = "STRINGA"`` del repo."""
    out: dict[str, set[str]] = {}
    for p in RADICE.rglob("*.py"):
        rel = p.relative_to(RADICE).as_posix()
        if rel.startswith((".venv/", ".claude/", "frontend/")):
            continue
        try:
            testo = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for riga in testo.splitlines():
            m = _COSTANTE.match(riga)
            if m:
                out.setdefault(m.group(1), set()).add(m.group(2))
    return out


def main() -> None:
    nomi = nomi_env(Path(sys.argv[1]))
    costanti = mappa_costanti()
    print(f"nomi nel .env: {len(nomi)}")
    for p in sorted(RADICE.rglob("*.py")):
        rel = p.relative_to(RADICE).as_posix()
        if rel.startswith((".venv/", ".claude/", "frontend/")) or "/node_modules/" in rel:
            continue
        try:
            righe = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, r in enumerate(righe, 1):
            for m in _DELENV.finditer(r):
                arg = m.group(1).strip()
                if arg[:1] in "\"'":
                    if arg.strip("\"'") in nomi:
                        print(f"ENV\t{rel}:{i}\t{r.strip()[:150]}")
                elif rel != "AUDIT_2026-10-02/cerca_delenv_env.py":
                    valori = costanti.get(arg.split(".")[-1], set())
                    nel_env = sorted(v for v in valori if v in nomi)
                    if nel_env:
                        print(f"ENV(cost)\t{rel}:{i}\t{arg} -> {','.join(nel_env)}")
                    elif not valori:
                        print(f"IRRISOLTA\t{rel}:{i}\t{r.strip()[:150]}")


if __name__ == "__main__":
    main()
