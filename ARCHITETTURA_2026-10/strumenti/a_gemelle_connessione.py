"""Misura del codice GEMELLO nella scheda A (connessione Betfair): calcio vs tennis.

Uso (sola lettura, nessun import del codice di produzione):
    python ARCHITETTURA_2026-10/strumenti/a_gemelle_connessione.py

Per ogni coppia (calcio, tennis): righe, righe di codice (senza vuote/commenti/docstring),
percentuale uguale per blocchi difflib sulle righe normalizzate (strip) e, per ogni
funzione con LO STESSO NOME, le righe e il rapporto difflib con file:riga di entrambe.
Riusa la stessa normalizzazione di e4_gemelli_tennis.py. ASCII-only, stampa a video.
"""
from __future__ import annotations

import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from e4_gemelli_tennis import funzioni, leggi, righe_di_codice, similitudine  # noqa: E402

COPPIE = [
    ("Betfair/stream/runner.py", "Betfair/stream/tennis_live/tennis_runner.py"),
    ("Betfair/stream/raw_listener.py", "Betfair/stream/tennis_live/tennis_recorder.py"),
    ("Betfair/stream/canale_bot.py", "Betfair/stream/tennis_live/canale_bot_tennis.py"),
    ("Betfair/stream/sottoscrizione_a_caldo.py", "Betfair/stream/tennis_live/iscrizione_a_caldo.py"),
    ("Betfair/stream/watchlist.py", "Betfair/stream/tennis_live/mercati_registrati.py"),
]


def main() -> None:
    for pa, pb in COPPIE:
        ra, rb = leggi(pa), leggi(pb)
        ca, cb = righe_di_codice(ra), righe_di_codice(rb)
        n, pa_, pb_, rt = similitudine(ca, cb)
        print("=" * 100)
        print("A = %s : %d righe, %d di codice" % (pa, len(ra) - 1, len(ca)))
        print("B = %s : %d righe, %d di codice" % (pb, len(rb) - 1, len(cb)))
        print("righe uguali (blocchi difflib): %d -> %.1f%% di A, %.1f%% di B, ratio %.3f"
              % (n, 100 * pa_, 100 * pb_, rt))
        fa, fb = funzioni(pa), funzioni(pb)
        comuni = sorted(set(fa) & set(fb), key=lambda k: fa[k][0])
        print("funzioni omonime: %d (A ne ha %d, B ne ha %d)" % (len(comuni), len(fa), len(fb)))
        for k in comuni:
            a0, a1, c1 = fa[k]
            b0, b1, c2 = fb[k]
            r = difflib.SequenceMatcher(None, c1, c2, autojunk=False).ratio()
            print("  %-44s A %4d righe cod  B %4d righe cod  ratio %.2f  A:%d B:%d"
                  % (k[:44], len(c1), len(c2), r, a0, b0))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
