"""Confronto di due referti di `certifica` (cantiere 11, 08/10/2026).

E' la prova di non regressione «prima e dopo» e la prova che `--worker N` da' lo
STESSO referto di `--worker 1`. Si tolgono SOLO le righe che cambiano da un
giro all'altro senza dire niente sul bot:

* le righe dei tempi (`certifica.righe_senza_tempi`: ``tempo:``, ``TEMPO
  TOTALE:``, ``LENTO:``);
* le righe diagnostiche dei worker (``worker: ...``, ``MEMORIA: ...``), che
  esistono solo con `--worker N`;
* le righe del LOG (``LIVELLO:modulo:...``, lo stderr dei processi): con piu'
  processi arrivano intercalate in un altro ordine;
* le righe vuote (con `--worker N` il blocco diagnostico ne aggiunge due).

Tutto il resto deve essere identico, riga per riga e nello stesso ordine.

Uso:
    python -m Betfair.stream.backtest.tools.confronta_referti PRIMA.txt DOPO.txt
Exit code 0 = identici, 1 = diversi (le righe diverse sono stampate).
"""
from __future__ import annotations

import argparse
import difflib
import io
import re
import sys
from typing import List, Optional

from ..certifica import righe_senza_tempi

#: una riga di log del modulo `logging` (formato di default `LIVELLO:nome:testo`)
RIGA_DI_LOG = re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):[\w.]+:")
#: le righe diagnostiche che esistono solo con `--worker N`
PREFISSI_DIAGNOSTICA_WORKER = ("worker: ", "MEMORIA: ")


def righe_confrontabili(testo: str) -> List[str]:
    """Il referto senza tempi, log, diagnostica dei worker e righe vuote."""
    fuori: List[str] = []
    for r in righe_senza_tempi(testo):
        if not r.strip():
            continue
        if RIGA_DI_LOG.match(r) or r.startswith(PREFISSI_DIAGNOSTICA_WORKER):
            continue
        fuori.append(r)
    return fuori


def differenze(prima: str, dopo: str) -> List[str]:
    """Le righe diverse (formato `unified_diff`, senza intestazioni)."""
    a, b = righe_confrontabili(prima), righe_confrontabili(dopo)
    return [r for r in difflib.unified_diff(a, b, lineterm="", n=0)
            if not r.startswith(("---", "+++"))]


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="confronto di due referti di certifica")
    p.add_argument("prima")
    p.add_argument("dopo")
    a = p.parse_args(argv)
    with io.open(a.prima, encoding="utf-8", errors="replace") as f:
        prima = f.read()
    with io.open(a.dopo, encoding="utf-8", errors="replace") as f:
        dopo = f.read()
    diff = differenze(prima, dopo)
    n = sum(1 for r in diff if r[:1] in "+-")
    print(f"{a.prima}: {len(righe_confrontabili(prima))} righe | {a.dopo}: "
          f"{len(righe_confrontabili(dopo))} righe | righe diverse: {n}")
    for r in diff:
        print(r)
    return 0 if n == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
