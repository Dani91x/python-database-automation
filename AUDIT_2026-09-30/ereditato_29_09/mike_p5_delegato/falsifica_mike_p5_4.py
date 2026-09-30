"""Falsificazione del blocco 4 di P5 (controlli del banco E2, J6, S2, J5B),
stessa macchina di falsifica_mike_p5_2.py (copia in memoria + hash).
Uso: python AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_4.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import falsifica_mike_p5_2 as F  # noqa: E402

CRT = os.path.join(F.RADICE, "Betfair", "mike", "certificazione.py")
F.TEST = ["Betfair/mike/tests/test_mike_p5_banco_2026_09_29.py"]
F.MUTAZIONI = [
    ("C1 E2 muto sulla banca", CRT,
     "        if a.side == \"lay\":\n            # 29/09 (P5, M3.1): copertura come BANCA",
     "        if a.side == \"lay\":\n            continue  # MUTAZIONE\n            # 29/09 (P5, M3.1): copertura come BANCA"),
    ("C2 E2 accetta una banca ridotta anche se il tetto non la tiene fuori", CRT,
     "                    and x * (float(a.price) - 1.0) > spazio + 0.011 \\",
     "                    and True \\"),
    ("C3 J6 giudica la banca col residuo della punta", CRT,
     "    if all(str(a.side) == \"lay\" for a in nuove):",
     "    if False:  # MUTAZIONE"),
    ("C4 S2 sempre sul libro Over", CRT,
     "    return E.SEL_UNDER if E.cover_form(params or {}) == E.COVER_LAY_U45 else E.SEL_OVER",
     "    return E.SEL_OVER  # MUTAZIONE"),
    ("C5 S2 ignora l'ordine proposto", CRT,
     "        if a.role == \"over_cover\" and a.selection:\n            return str(a.selection)",
     "        if False:  # MUTAZIONE\n            return str(a.selection)"),
    ("C6 J5B muto", CRT,
     "    if len(in_volo) > 1:\n        return (f\"due lay in volo sul mercato 4,5:",
     "    return None  # MUTAZIONE\n    if len(in_volo) > 1:\n        return (f\"due lay in volo sul mercato 4,5:"),
    ("C7 chiusura manuale anche a mercato sospeso", F.ENG,
     "    ferme = [c for c in closes if not operabile(snap.book(c.market, c.selection))]",
     "    ferme = []  # MUTAZIONE"),
]

if __name__ == "__main__":
    F.main()
