"""Confronto dei referti del giro 4 (``AUDIT_2026-10-06/replay/giro4/``) con
quelli del giro 3 (``AUDIT_2026-10-06/replay/giro3/``).

Per i 15 scenari dello Scalper (A1..C): righe OK/KO/NE identiche. Per la
modalita': righe OK/KO/NE, righe dei cicli e riga NETTO; ogni differenza si
stampa (attese solo dove agiscono le decisioni del giro 4: P1, lo stop lascia
la banca; P13, la ripresa dal conto dopo il riavvio).

Uso: python AUDIT_2026-10-06/strumenti/confronta_giro4.py
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import os
import re
import sys

G2 = "AUDIT_2026-10-06/replay/giro3"
G3 = "AUDIT_2026-10-06/replay/giro4"
SCALPER = ("A1", "A2", "B1", "B2", "B3", "C")
MEDIA = ("media_35797769", "varianti_35797769", "guasti_35797769", "media_35760084",
         "liquidita_35797769", "liquidita_35760084")


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
        print("%-18s %3d righe giro 3, %3d giro 4: %s" % (nome, len(a), len(b),
                                                          "IDENTICHE" if uguali else "DIVERSE"))
        if not uguali:
            for x in a:
                if x not in b:
                    print("   - giro 3: " + x[:400])
            for y in b:
                if y not in a:
                    print("   + giro 4: " + y[:400])
    print("ESITO scalper: %s" % ("identico" if not diversi_scalper
                                 else "%d gruppi DIVERSI" % diversi_scalper))
    return 1 if diversi_scalper else 0


if __name__ == "__main__":
    sys.exit(main())
