"""Falsificazione del blocco 2B di P5 (stessa macchina di falsifica_mike_p5_2.py:
copia in memoria + hash, mai git checkout).
Uso: python AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_2b.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import falsifica_mike_p5_2 as F  # noqa: E402

F.TEST = ["Betfair/mike/tests/test_mike_p5_2b_2026_09_29.py",
          "Betfair/mike/tests/test_mike_p5_copertura_banca_2026_09_29.py",
          "Betfair/mike/tests/test_mike_p5_compensazione_mercato_2026_09_29.py"]
ENG = F.ENG
F.MUTAZIONI = [
    ("G1 guardia del punteggio assente tolta nel ramo banca", ENG,
     "    if timing == \"wait\" and ctx.cover_forced and not dopo_gol and snap.goals is not None:\n"
     "        timing = \"cover\"\n    x_pieno = cover_residual_lay(",
     "    if timing == \"wait\" and ctx.cover_forced and not dopo_gol:  # MUTAZIONE\n"
     "        timing = \"cover\"\n    x_pieno = cover_residual_lay("),
    ("Q19 abbinato della riga per selezione", ENG,
     "                             if x.market == market\n                             and not x.archived",
     "                             if x.market == market and x.selection == selection  # MUTAZIONE\n"
     "                             and not x.archived"),
    ("T1 tolleranza sulla PRIMA chiusura del mercato", ENG,
     "    return max(_FLAT_EPS, 0.005 * float(chiusure[-1].fill_price))",
     "    return max(_FLAT_EPS, 0.005 * float(chiusure[0].fill_price))  # MUTAZIONE"),
    ("T2 tolleranza sulla chiusura a prezzo piu' alto", ENG,
     "    return max(_FLAT_EPS, 0.005 * float(chiusure[-1].fill_price))",
     "    return max(_FLAT_EPS, 0.005 * max(float(c.fill_price) for c in chiusure))  # MUTAZIONE"),
    ("A1 gia' coperto senza le banche", ENG,
     "    gross = _market_pnl_by_total(active_legs(legs), MARKET_OU45, 5)",
     "    gross = _market_pnl_by_total([l for l in active_legs(legs) if l.side == \"back\"], "
     "MARKET_OU45, 5)  # MUTAZIONE"),
]

if __name__ == "__main__":
    F.main()
