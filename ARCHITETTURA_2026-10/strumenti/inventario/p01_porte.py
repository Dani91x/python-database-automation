"""Sezione 5 - porte locali 47xxx: dove sono definite e dove sono citate (file:riga), solo codice di produzione,
desktop/, *.bat, *.ps1 e frontend/src (non test). Sola lettura dei file tracciati.
Una 'definizione' e' una riga con assegnazione di costante o getenv con default = porta; le altre sono 'citazioni'
(commenti, docstring, client). Uscite: uscite/p01_porte.tsv, uscite/p01_porte_riepilogo.txt
Uso: python p01_porte.py
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402
from s01_righe import categoria  # noqa: E402

RE_PORTA = re.compile(r"(?<![\d.])47[0-9]{3}(?![\d])")
RE_DEF = re.compile(r"(PORT|PORTA|port|porta|lock)\w*\s*[:=].*47\d{3}|getenv\([^)]*47\d{3}|environ\.get\([^)]*47\d{3}|,\s*\"47\d{3}\"\s*\)|=\s*47\d{3}\b|\b47\d{3}\s*\)\s*$")


def main() -> int:
    righe_out = ["porta\ttipo\tfile\triga\ttesto"]
    per_porta: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: {"def": [], "cit": []})
    for rel in c.file_tracciati():
        cat = categoria(rel)
        ok = cat in ("py_codice_Betfair", "py_codice_radice", "py_codice_cartelle_radice", "desktop_codice", "frontend_codice") or \
            rel.endswith((".bat", ".ps1")) and "/" not in rel
        if not ok:
            continue
        t = c.leggi_testo(rel)
        if t is None:
            continue
        for i, riga in enumerate(t.splitlines(), 1):
            for m in RE_PORTA.finditer(riga):
                p = m.group(0)
                s = riga.strip()
                commento = s.startswith(("#", "//", "*", "/*", '"""'))
                tipo = "def" if (RE_DEF.search(s) and not commento) else "cit"
                righe_out.append(f"{p}\t{tipo}\t{rel}\t{i}\t{s[:150]}")
                per_porta[p][tipo].append(f"{rel}:{i}")
    c.scrivi("p01_porte.tsv", "\n".join(righe_out) + "\n")
    r = ["porta  n_def  n_cit  definizioni (file:riga)"]
    for p in sorted(per_porta):
        d = per_porta[p]["def"]
        r.append(f"{p}  {len(d):>3}  {len(per_porta[p]['cit']):>4}  " + "; ".join(d[:6]) + (" ..." if len(d) > 6 else ""))
    c.scrivi("p01_porte_riepilogo.txt", "\n".join(r) + "\n")
    print("\n".join(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
