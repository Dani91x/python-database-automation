"""FALSIFICAZIONE del reperto 1 (Safe: adozione per mercato dell'ordine del canale senza
eventi) e del rispetto di ``ATTORI_CON_TRADUZIONE`` su coda, REST e finto del motore
(02/10/2026). Stesso meccanismo di ``falsifica_riconciliazione.py``. ASCII-only."""
from __future__ import annotations

import importlib.util
import os
import sys

_QUI = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "falsifica_base", os.path.join(_QUI, "falsifica_riconciliazione.py"))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

BS_ = "Betfair/safe_strategy/bot_service.py"
EX_ = "Betfair/safe_strategy/execution.py"
LOW_ = "Betfair/stream/live_order_worker.py"
OT_ = "Betfair/omega/tests/test_riconciliazione_tradotti_omega_2026_10_02.py"

F.OUT = os.path.join(_QUI, "falsifica_reperto1_out.txt")
F.TEST = [
    "Betfair/safe_strategy/tests/test_reperto1_adozione_canale_safe_2026_10_02.py",
    "Betfair/safe_strategy/tests/test_riconciliazione_tradotti_safe_2026_10_02.py",
    "Betfair/omega/tests/test_riconciliazione_tradotti_omega_2026_10_02.py",
    "Betfair/stream/tests/test_riconciliazione_tradotti_2026_10_02.py",
]
F.MUTAZIONI = [
    ("P1-a", "nessuna adozione per mercato (il difetto del reperto 1)", BS_,
     "                if _adotta_per_mercato(market, tr, db=db) is None:",
     "                if False:"),
    ("P1-b", "adozione senza la finestra dell'invio", BS_,
     "            and str(o.get(\"bet_id\")) not in noti and _nella_finestra(o, quando)",
     "            and str(o.get(\"bet_id\")) not in noti"),
    ("P1-c", "adozione senza la size esatta", BS_,
     "                    and abs(float(o.get(\"size_requested\")) - size) <= 0.005)",
     "                    and True)"),
    ("P1-d", "adozione senza la quota esatta", BS_,
     "                    and abs(float(o.get(\"price_requested\")) - prezzo) <= 1e-9",
     "                    and True"),
    ("P1-e", "adozione di un bet_id gia' di un'altra riga", BS_,
     "            and str(o.get(\"bet_id\")) not in noti and _nella_finestra(o, quando)",
     "            and _nella_finestra(o, quando)"),
    ("P1-f", "piu' candidati: se ne adotta uno a caso", BS_,
     "    if len(cand) > 1:\n        return None\n    bet_id, o = next(iter(cand.items()))",
     "    bet_id, o = next(iter(cand.items()))"),
    ("P1-g", "indecisa senza avviso", BS_,
     "                        _log(db, \"canale_orfano\", {",
     "                        (lambda *a, **k: None)(db, \"canale_orfano\", {"),
    ("P1-h", "lettura del conto intero invece della strategia safe", BS_,
     "        ordini = list(leggi(SAFE_STRATEGY_REF) or [])",
     "        ordini = list(leggi() or [])"),
    ("P1-i", "il canale non scrive l'ordine mandato prima dell'invio", EX_,
     "                \"canale_inviato\": {\"selection_id\": int(selection_id),",
     "                \"canale_inviato_no\": {\"selection_id\": int(selection_id),"),
    ("P11-a", "coda e REST di Safe ignorano ATTORI_CON_TRADUZIONE", EX_,
     "                               and _ATTORE_SAFE in _MI.ATTORI_CON_TRADUZIONE)",
     "                               and True)"),
    ("P11-b", "il worker ignora ATTORI_CON_TRADUZIONE", LOW_,
     "    if str(params.get(\"source\") or \"\") not in MI.ATTORI_CON_TRADUZIONE:\n        return None",
     "    if False:\n        return None"),
    ("P11-c", "il finto del motore traduce per ogni attore", OT_,
     "                and d.get(\"attore\") not in MI.ATTORI_CON_TRADUZIONE):",
     "                and False):"),
]

if __name__ == "__main__":
    sys.exit(F.main())
