"""Stampa le righe citate (file:riga) per controllare a occhio le prove dell'inventario.

Uso:  python mostra_righe.py Betfair/stream/runner.py:2585 desktop/main.js:435 ...
      python mostra_righe.py --inventario ../INVENTARIO_ARCHITETTURA.md
Con --inventario estrae tutti i riferimenti `percorso:riga` del file e segnala quelli
che puntano a un file inesistente o a una riga oltre la fine. Solo libreria standard.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]
RX = re.compile(r"`?((?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]+\.(?:py|js|ts|tsx|sql|md|bat)):(\d+)(?:-(\d+))?")


def mostra(rif: str, file: str, riga: int) -> bool:
    p = RADICE / file
    if not p.is_file():
        print(f"MANCA FILE  {rif}")
        return False
    righe = p.read_text(encoding="utf-8", errors="replace").splitlines()
    if riga < 1 or riga > len(righe):
        print(f"RIGA FUORI  {rif} (il file ha {len(righe)} righe)")
        return False
    print(f"{rif:<62}| {righe[riga - 1].strip()[:110]}")
    return True


def main(argv: list[str]) -> int:
    rifs: list[tuple[str, str, int]] = []
    if argv[:1] == ["--inventario"]:
        testo = Path(argv[1]).read_text(encoding="utf-8")
        visti = set()
        for m in RX.finditer(testo):
            chiave = (m.group(1), int(m.group(2)))
            if chiave in visti:
                continue
            visti.add(chiave)
            rifs.append((f"{m.group(1)}:{m.group(2)}", m.group(1), int(m.group(2))))
    else:
        for a in argv:
            f, _, r = a.rpartition(":")
            rifs.append((a, f, int(r)))
    ko = sum(0 if mostra(*x) else 1 for x in rifs)
    print(f"\n{len(rifs)} riferimenti, {ko} non validi")
    return 1 if ko else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
