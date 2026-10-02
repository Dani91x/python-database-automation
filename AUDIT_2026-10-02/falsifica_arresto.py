"""FALSIFICAZIONE di R1 (arresto ordinato di Safe e Omega, 02/10/2026).

Stesso meccanismo di ``falsifica_riconciliazione.py`` (mutazione nel file vero, rosso
preteso, ripristino byte per byte, verde finale). Esito in ``falsifica_arresto_out.txt``.
ASCII-only.
"""
from __future__ import annotations

import importlib.util
import os
import sys

_QUI = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "falsifica_base", os.path.join(_QUI, "falsifica_riconciliazione.py"))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

AB_ = "Betfair/safe_strategy/arresto_bot.py"
BS_ = "Betfair/safe_strategy/bot_service.py"
OS_ = "Betfair/omega/omega_service.py"
JS_ = "desktop/main.js"

F.OUT = os.path.join(_QUI, "falsifica_arresto_out.txt")
F.TEST = [
    "Betfair/safe_strategy/tests/test_arresto_bot_safe_omega_2026_10_02.py",
    "Betfair/stream/tests/test_sveglia_bot_f5_f6_2026_09_18.py",
]
F.MUTAZIONI = [
    ("A1", "nessun annullo davvero (solo contabile)", AB_,
     "            voce[\"esito\"] = annulla_riga(tr, market=market, db=db,",
     "            voce[\"esito\"] = (lambda *a, **k: \"annullato\")(tr, market=market, db=db,"),
    ("A2", "riga paper annullata col REST sul conto vero", AB_,
     "    if mode == \"paper\":\n        if canale:", "    if False:\n        if canale:"),
    ("A3", "nessun tetto di 10 s", AB_,
     "        if ora() >= scadenza:", "        if False:"),
    ("A4", "posizione lasciata senza CRITICAL", AB_,
     "    if esito[\"posizioni\"]:\n        problemi.append",
     "    if False:\n        problemi.append"),
    ("A5", "stop dall'app scambiato per segnale", AB_,
     "        causa = CAUSA_STOP_APP if stop_app() else CAUSA_SEGNALE",
     "        causa = CAUSA_SEGNALE"),
    ("A6", "arresto ordinato saltato all'uscita", AB_,
     "            chiudi(causa)\n", "            pass\n"),
    ("A7", "SIGTERM/SIGBREAK non intercettati", AB_,
     "            signal.signal(s, _segnale_in_interrupt)",
     "            signal.signal(s, signal.SIG_DFL)"),
    ("A8", "coda paper: annullo non accodato", AB_,
     "            return \"accodato\" if ok else \"ignoto\"", "            return \"nessun_ordine\""),
    ("A9", "canale ignorato: la riga del canale va al REST", AB_,
     "    canale = X.ha_marker_canale(tr) and bool(porta_kw)", "    canale = False"),
    ("A10", "Safe: la chiusura non usa il DB vero", BS_,
     "bot=\"safe\", db=_real_db,", "bot=\"safe\", db=None,"),
    ("A11", "Omega: la chiusura non usa il mercato vero", OS_,
     "bot=\"omega\", db=_real_db, market=_real_market,",
     "bot=\"omega\", db=_real_db, market=None,"),
    ("A12", "Omega: la dormita non vede l'arresto (60 s di fila)", OS_,
     "        _AB.dormi_finche_arresto(pausa, richiesto=_AO.richiesto, dormi=time.sleep)",
     "        time.sleep(pausa)"),
    ("A13", "main.js: grazia di Safe e Omega a 25 s", JS_,
     "if (label === 'omega-service' || label === 'safe-strategy-bot') return 45_000;",
     "if (label === 'omega-service' || label === 'safe-strategy-bot') return 25_000;"),
    ("A14", "Safe: main senza arresto ordinato", BS_,
     "        _AB.esegui_ciclo_con_arresto(\n            lambda: _ciclo_persistente(_un_giro, label=\"[safe.bot]\"),",
     "        (lambda *a, **k: None)(\n            lambda: _ciclo_persistente(_un_giro, label=\"[safe.bot]\"),"),
]

if __name__ == "__main__":
    sys.exit(F.main())
