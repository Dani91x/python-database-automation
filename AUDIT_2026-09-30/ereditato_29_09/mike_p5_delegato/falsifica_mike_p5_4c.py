"""Falsificazione del blocco 4C di P5 (chiusura manuale e stato del mercato).
Stessa macchina di falsifica_mike_p5_2.py (copia in memoria + hash)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import falsifica_mike_p5_2 as F  # noqa: E402

ENG = F.ENG
F.TEST = ["Betfair/mike/tests/test_mike_p5_4c_2026_09_29.py"]
F.MUTAZIONI = [
    ("D1 un mercato chiuso ferma tutto (la prima versione)", ENG,
     "    ferme = [c for c in closes if not operabile(snap.book(c.market, c.selection))\n             and riaprira(snap.book(c.market, c.selection))]",
     "    ferme = [c for c in closes if not operabile(snap.book(c.market, c.selection))]  # MUTAZIONE"),
    ("D2 la chiusura sul mercato chiuso parte lo stesso", ENG,
     "        closes = [c for c in closes if c not in su_chiusi]",
     "        closes = list(closes)  # MUTAZIONE"),
    ("D3 nessuna attesa a mercato sospeso", ENG,
     "    ferme = [c for c in closes if not operabile(snap.book(c.market, c.selection))\n             and riaprira(snap.book(c.market, c.selection))]",
     "    ferme = []  # MUTAZIONE"),
    ("D4 la selezione decisa finisce fra le chiusure", ENG,
     "        if won is not None:\n            locked = float(w if won else l)\n            decided.append(key)",
     "        if False:  # MUTAZIONE\n            locked = float(w if won else l)\n            decided.append(key)"),
]

if __name__ == "__main__":
    F.main()
