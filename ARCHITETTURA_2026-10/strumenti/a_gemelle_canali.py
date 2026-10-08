"""Misura del codice GEMELLO fra i moduli dei canali locali (scheda A). Sola lettura.

Uso: python -I ARCHITETTURA_2026-10/strumenti/a_gemelle_canali.py
Per ogni coppia: righe di codice e percentuale di righe uguali (blocchi difflib sulle
righe normalizzate, stessa normalizzazione di e4_gemelli_tennis.py). ASCII-only.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from e4_gemelli_tennis import leggi, righe_di_codice, similitudine  # noqa: E402

FILES = [
    "Betfair/stream/canale_bot.py",
    "Betfair/stream/esiti_ordini_canale.py",
    "Betfair/stream/sveglia_canale.py",
    "Betfair/safe_strategy/canale_scan.py",
    "Betfair/stream/tennis_live/canale_bot_tennis.py",
]


def main() -> None:
    code = {f: righe_di_codice(leggi(f)) for f in FILES}
    for f in FILES:
        print("%-52s righe di codice %d" % (f, len(code[f])))
    for i, a in enumerate(FILES):
        for b in FILES[i + 1:]:
            n, pa, pb, rt = similitudine(code[a], code[b])
            print("%-40s <-> %-40s uguali %4d (%.1f%% / %.1f%%)"
                  % (a.split("/")[-1], b.split("/")[-1], n, 100 * pa, 100 * pb))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
