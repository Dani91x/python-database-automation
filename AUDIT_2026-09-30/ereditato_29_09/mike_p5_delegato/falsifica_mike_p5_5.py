"""Falsificazione del blocco 5 di P5 (valore di serie e gemelli della forma
banca). Stessa macchina di falsifica_mike_p5_2.py (copia in memoria + hash)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import falsifica_mike_p5_2 as F  # noqa: E402

CFG = os.path.join(F.RADICE, "Betfair", "mike", "config.py")
ENG = F.ENG
F.TEST = ["Betfair/mike/tests/test_mike_p5_gemelli_banca_2026_09_29.py"]
F.MUTAZIONI = [
    ("V1 valore di serie ancora la punta", CFG,
     "    \"cover_form\": (\"lay_under45\", str,",
     "    \"cover_form\": (\"back_over45\", str,  # MUTAZIONE\n    "),
    ("V2 freno della copertura spento", ENG,
     "    bloccata = copertura_bloccata(ctx)\n    manca = None if bloccata else attesa_ritento_copertura(ctx, snap, params)",
     "    bloccata = None  # MUTAZIONE\n    manca = None if bloccata else attesa_ritento_copertura(ctx, snap, params)"),
    ("V3 ritmo minimo spento", ENG,
     "    manca = None if bloccata else attesa_ritento_copertura(ctx, snap, params)",
     "    manca = None  # MUTAZIONE"),
    ("V4 la copertura ordinata aspetta anche nella banca", ENG,
     "    if timing == \"wait\" and ctx.cover_forced and not dopo_gol and snap.goals is not None:\n        timing = \"cover\"\n    x_pieno = cover_residual_lay(",
     "    if False:  # MUTAZIONE\n        timing = \"cover\"\n    x_pieno = cover_residual_lay("),
]

if __name__ == "__main__":
    F.main()
