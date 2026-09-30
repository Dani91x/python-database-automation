"""Falsificazione del blocco 4B di P5: le sei mutazioni sopravvissute del
coordinatore (N3, N13, N14, N15, N17, N21) e il contratto dell'impronta.
Stessa macchina di falsifica_mike_p5_2.py (copia in memoria + hash).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import falsifica_mike_p5_2 as F  # noqa: E402

ENG = F.ENG
REG = os.path.join(F.RADICE, "Betfair", "stream", "backtest", "registro_bot.py")
F.TEST = ["Betfair/mike/tests/test_mike_p5_4b_2026_09_29.py"]
F.MUTAZIONI = [
    ("N3 forma ignota = banca", ENG,
     "    return v if v in (COVER_LAY_U45, COVER_BACK_O45) else COVER_BACK_O45",
     "    return v if v in (COVER_LAY_U45, COVER_BACK_O45) else COVER_LAY_U45  # MUTAZIONE"),
    ("N13 banca a mercato Under non aperto", ENG,
     "    if not operabile(bk):\n        return Decision(\"LIVE_UNCOVERED\", acts,\n                        \"copertura: mercato Under 4.5 %s",
     "    if False:  # MUTAZIONE\n        return Decision(\"LIVE_UNCOVERED\", acts,\n                        \"copertura: mercato Under 4.5 %s"),
    ("N14 troppi gol ignorati nella banca", ENG,
     "    if timing == \"skip\":\n        return Decision(\"LIVE_COVERED\", acts, \"copertura saltata: troppi gol\",\n                        updates={\"cover_skipped\": True, \"cover_stage\": 0, \"cover_forced\": False})\n    if liab <= 0.0:\n        return Decision(\"LIVE_COVERED\", acts, \"nessuna liability Under da coprire\",\n                        updates={\"cover_skipped\": True, \"cover_stage\": 0, \"cover_forced\": False})\n    if bk is None:",
     "    if False:  # MUTAZIONE\n        return Decision(\"LIVE_COVERED\", acts, \"copertura saltata: troppi gol\",\n                        updates={\"cover_skipped\": True, \"cover_stage\": 0, \"cover_forced\": False})\n    if liab <= 0.0:\n        return Decision(\"LIVE_COVERED\", acts, \"nessuna liability Under da coprire\",\n                        updates={\"cover_skipped\": True, \"cover_stage\": 0, \"cover_forced\": False})\n    if bk is None:"),
    ("N15 tranche della banca col minimo della puntata", ENG,
     "        piu_piccola_piazzabile = IT_LAY_MIN",
     "        pass  # MUTAZIONE"),
    ("N17 riprezzo a mercato Under sospeso", ENG,
     "    if bk is not None and not operabile(bk):\n        return Decision(\"LIVE_COVER_PENDING\", [],\n                        \"copertura: mercato Under 4.5 %s, nessun riprezzo\"",
     "    if False:  # MUTAZIONE\n        return Decision(\"LIVE_COVER_PENDING\", [],\n                        \"copertura: mercato Under 4.5 %s, nessun riprezzo\""),
    ("N21 ripiego anche nella forma di prima", ENG,
     "    if float(plan.size) >= IT_LAY_MIN - _EPS or not _banca_di_apertura(legs, key[0]):",
     "    if float(plan.size) >= IT_LAY_MIN - _EPS:  # MUTAZIONE"),
    ("I1 motore fuori dall'impronta", REG,
     "        moduli_produzione=(\"Betfair.mike.service\", \"Betfair.mike.engine\",",
     "        moduli_produzione=(\"Betfair.mike.service\",  # MUTAZIONE"),
]

if __name__ == "__main__":
    F.main()
