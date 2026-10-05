"""Confronto riga per riga (righe OK/KO/NE degli scenari) fra i referti del
revisore (``AUDIT_2026-10-05/replay/scalper_15_con_media_spenta/``) e quelli del
giro 2 (``AUDIT_2026-10-05/replay/giro2/nr_*.txt``).

Uso: python AUDIT_2026-10-05/strumenti/confronta_non_regressione.py [cartella_giro2]
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import os
import re
import sys

RIF = "AUDIT_2026-10-05/replay/scalper_15_con_media_spenta"
COPPIE = {"A1": "nr_A1", "A2": "nr_A2", "B1": "nr_B1", "B2": "nr_B2", "B3": "nr_B3",
          "C": "nr_C"}


def righe(path: str) -> list:
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for r in fh:
            if re.match(r"^(OK|KO|NE) ", r):
                out.append(r.rstrip())
    return out


def main(cartella: str) -> int:
    diversi = 0
    for rif, nostro in COPPIE.items():
        a = righe(os.path.join(RIF, rif + ".txt"))
        b = righe(os.path.join(cartella, nostro + ".txt"))
        uguali = a == b
        diversi += 0 if uguali else 1
        print("%-3s %d righe revisore, %d giro 2: %s" % (rif, len(a), len(b),
                                                          "IDENTICHE" if uguali else "DIVERSE"))
        if not uguali:
            for x, y in zip(a, b):
                if x != y:
                    print("   revisore: " + x)
                    print("   giro 2  : " + y)
    print("ESITO: %s" % ("tutte identiche" if not diversi else "%d gruppi diversi" % diversi))
    return 1 if diversi else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "AUDIT_2026-10-05/replay/giro2"))
