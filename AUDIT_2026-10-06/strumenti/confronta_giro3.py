"""Confronto dei referti del giro 3 (``AUDIT_2026-10-06/replay/giro3/``) con
quelli verificati dal coordinatore nel giro 2 (``AUDIT_2026-10-05/replay/giro2_coord/``).

Per i 15 scenari dello Scalper (A1..C): righe OK/KO/NE identiche. Per la
modalita': righe OK/KO/NE, righe dei cicli e riga NETTO; ogni differenza si
stampa (attese solo dove la regola nuova della banca ha effetto).

Uso: python AUDIT_2026-10-06/strumenti/confronta_giro3.py
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import os
import re
import sys

G2 = "AUDIT_2026-10-05/replay/giro2_coord"
G3 = "AUDIT_2026-10-06/replay/giro3"
SCALPER = ("A1", "A2", "B1", "B2", "B3", "C")
MEDIA = ("media_35797769", "varianti_35797769", "guasti_35797769", "media_35760084")


def righe(path: str, media: bool) -> list:
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for r in fh:
            r = r.rstrip()
            if re.match(r"^(OK|KO|NE) ", r):
                out.append(r)
            elif media and re.search(r"MEDIA UNDER (ciclo \d+:|P&L del replay)", r):
                out.append(r.strip())
    return out


def main() -> int:
    diversi_scalper = 0
    for nome in SCALPER + MEDIA:
        media = nome in MEDIA
        a = righe(os.path.join(G2, nome + ".txt"), media)
        b = righe(os.path.join(G3, nome + ".txt"), media)
        uguali = a == b
        if not uguali and not media:
            diversi_scalper += 1
        print("%-18s %3d righe giro 2, %3d giro 3: %s" % (nome, len(a), len(b),
                                                          "IDENTICHE" if uguali else "DIVERSE"))
        if not uguali:
            for x in a:
                if x not in b:
                    print("   - giro 2: " + x[:400])
            for y in b:
                if y not in a:
                    print("   + giro 3: " + y[:400])
    print("ESITO scalper: %s" % ("identico" if not diversi_scalper
                                 else "%d gruppi DIVERSI" % diversi_scalper))
    return 1 if diversi_scalper else 0


if __name__ == "__main__":
    sys.exit(main())
