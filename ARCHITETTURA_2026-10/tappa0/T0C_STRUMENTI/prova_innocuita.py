"""T0C - PROVA DI INNOCUITA' della cassetta: il referto con la cassetta accesa e'
IDENTICO a quello senza, esclusi SOLO i tempi (``certifica.righe_senza_tempi``)
e il blocco che ``--cassetta`` aggiunge IN CODA (riga vuota + ``CASSETTA:`` e,
con ``--ombra``/``--congela``, le righe ``OMBRA``/``CONGELATO``).

Nessun'altra riga si toglie (nemmeno le vuote): e' piu' severo di
``Betfair/stream/backtest/tools/confronta_referti.py``.

Uso (dalla radice del repository):
    python ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/prova_innocuita.py SENZA.txt CON.txt
Exit code 0 = identici, 1 = diversi (diff stampato). ASCII-only.
"""
from __future__ import annotations

import difflib
import os
import sys

sys.path.insert(0, os.getcwd())

from Betfair.stream.backtest.certifica import righe_senza_tempi  # noqa: E402


def senza_blocco_cassetta(righe):
    """Toglie il blocco in coda di ``--cassetta`` (dalla riga vuota che precede
    ``CASSETTA:`` in poi). Un referto senza quel blocco resta com'e'."""
    for i, r in enumerate(righe):
        if r.startswith("CASSETTA: "):
            j = i - 1 if i > 0 and righe[i - 1] == "" else i
            return righe[:j]
    return righe


def main(argv):
    a, b = argv[1], argv[2]
    ra = senza_blocco_cassetta(righe_senza_tempi(open(a, encoding="utf-8").read()))
    rb = senza_blocco_cassetta(righe_senza_tempi(open(b, encoding="utf-8").read()))
    if ra == rb:
        print("IDENTICI esclusi i tempi: %d righe (%s / %s)" % (len(ra), os.path.basename(a),
                                                              os.path.basename(b)))
        return 0
    print("DIVERSI:")
    for r in difflib.unified_diff(ra, rb, a, b, lineterm=""):
        print(r)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
