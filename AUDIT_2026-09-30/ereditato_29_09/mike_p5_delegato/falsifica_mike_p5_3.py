"""Falsificazione del blocco 3 di P5 (servizio e motore ordini), con la stessa
macchina di falsifica_mike_p5_2.py (copia in memoria + hash, mai git checkout).
Uso: python AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_3.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import falsifica_mike_p5_2 as F  # noqa: E402

SRV = os.path.join(F.RADICE, "Betfair", "mike", "service.py")
MOT = os.path.join(F.RADICE, "Betfair", "stream", "motore_ordini.py")
F.TEST = ["Betfair/mike/tests/test_mike_p5_servizio_copertura_2026_09_29.py",
          "Betfair/stream/tests/test_motore_ordini_mercato_due_esiti_2026_09_29.py"]
F.MUTAZIONI = [
    ("S1 sorveglianza sempre sul libro Over", SRV,
     "    sel = _selezione_copertura(ctx, params)\n",
     "    sel = E.SEL_OVER  # MUTAZIONE\n"),
    ("S2 la copertura gia' sul book non decide il libro", SRV,
     "        if l.role == \"over_cover\" and (l.is_live or l.needs_reconcile):\n            return l.selection",
     "        if False:  # MUTAZIONE\n            return l.selection"),
    ("S3 meta.cover_form non scritto", SRV,
     "    if leg.role == \"over_cover\":\n        # 29/09 (P5, M3.1): la FORMA",
     "    if False:  # MUTAZIONE\n        # 29/09 (P5, M3.1): la FORMA"),
    ("M1 riduzione solo per selezione (come prima)", MOT,
     "            altro = altro_runner_due_esiti(market, int(riga[\"selection_id\"]))\n            if altro is None:",
     "            altro = None  # MUTAZIONE\n            if altro is None:"),
    ("M2 somma anche con tre esiti", MOT,
     "    if len(runners) != 2:\n        return None",
     "    if len(runners) < 2:  # MUTAZIONE\n        return None"),
    ("M3 altra selezione non rovesciata", MOT,
     "            return riduce_esposizione(float(win) + float(l2), float(lose) + float(w2),",
     "            return riduce_esposizione(float(win) + float(w2), float(lose) + float(l2),  # MUTAZIONE"),
]

if __name__ == "__main__":
    F.main()
