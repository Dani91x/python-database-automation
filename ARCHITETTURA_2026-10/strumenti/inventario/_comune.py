"""Funzioni comuni agli script dell'inventario (solo libreria standard, sola lettura).

Nessuno script importa codice di produzione: leggono solo i file tracciati da git
(`git ls-files`) e scrivono SOLO dentro ARCHITETTURA_2026-10/strumenti/inventario/uscite/.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Radice del repo: .../ARCHITETTURA_2026-10/strumenti/inventario/_comune.py -> 3 livelli su
RADICE = Path(__file__).resolve().parents[3]
USCITE = Path(__file__).resolve().parent / "uscite"
USCITE.mkdir(parents=True, exist_ok=True)


def git(*args: str) -> str:
    """Esegue git nella radice e ritorna lo stdout (utf-8)."""
    r = subprocess.run(["git", *args], cwd=RADICE, capture_output=True, check=True)
    return r.stdout.decode("utf-8", errors="replace")


def file_tracciati() -> list[str]:
    """Elenco dei file tracciati (percorsi con / relativi alla radice)."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=RADICE, capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8", errors="replace").split("\0") if p]


def leggi_bytes(rel: str) -> bytes | None:
    p = RADICE / rel
    try:
        return p.read_bytes()
    except OSError:
        return None


def righe_wc(dati: bytes) -> int:
    """Come `wc -l`: numero di caratteri di nuova riga."""
    return dati.count(b"\n")


def e_binario(dati: bytes) -> bool:
    return b"\0" in dati[:8192]


def leggi_testo(rel: str) -> str | None:
    d = leggi_bytes(rel)
    if d is None or e_binario(d):
        return None
    return d.decode("utf-8-sig", errors="replace")


def e_test_py(rel: str) -> bool:
    nome = rel.rsplit("/", 1)[-1]
    parti = rel.split("/")
    return (
        nome.startswith("test_")
        or nome.endswith("_test.py")
        or nome == "conftest.py"
        or "tests" in parti[:-1]
        or "test" in parti[:-1]
    )


def e_strumento(rel: str) -> bool:
    parti = rel.split("/")
    return "tools" in parti[:-1]


def scrivi(nome: str, testo: str) -> Path:
    p = USCITE / nome
    p.write_text(testo, encoding="utf-8", newline="\n")
    if p.stat().st_size > 1_000_000:
        print(f"ATTENZIONE: {nome} supera 1 MB", file=sys.stderr)
    return p
