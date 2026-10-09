"""Misura del ladder (W1-A2): nuovo a ogni cambio (minimo 20 ms) contro il worker di oggi a 200 ms.

Rieseguibile, sola lettura, nessuna rete: dalla radice del repository

    python ARCHITETTURA_2026-10/ondata1/W1-A2/misura_ladder.py [evento ...]

Per ogni registrazione (di serie 35760084 e 35797769) e sport, fa girare INSIEME
il ``ladder_worker`` vero di oggi (``runner.py`` / ``tennis_runner.py``, cadenza
del canale 200 ms, recorder/capture veri) e ``LadderEvento`` (20 ms) sugli stessi
``MarketBook`` (listener vero di betfairlightweight), col tempo della
registrazione (``pt``). Stampa una riga JSON per caso: pubblicazioni, attesa
"arrivo del book -> pubblicazione" (p50, p95, max, media in ms), righe nuove
diverse da quelle di oggi per lo stesso stato (deve essere 0), pubblicazioni
dello stesso mercato a meno di 20 ms (deve essere 0).

Limite dichiarato: il tempo e' quello della registrazione (``pt``), non l'orologio
del PC: misura la CADENZA (quanto aspetta un book prima di uscire), non i costi di
CPU ne' la rete fino alla UI. La misura dal vivo e' la sonda ``ladder_pub_pt_ms``
della Salute (T0A) in ombra.
"""
from __future__ import annotations

import json
import os
import sys
import time

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, RADICE)


def main(eventi: list) -> None:
    import pytest

    from Betfair.nucleo.betfair.tests.test_a2_ladder_parita import misura_cadenza

    for ev in eventi:
        for sport in ("calcio", "tennis"):
            inizio = time.perf_counter()
            with pytest.MonkeyPatch.context() as mp:
                m = misura_cadenza(ev, sport, mp)
            m["secondi_di_calcolo"] = round(time.perf_counter() - inizio, 1)
            print(json.dumps(m, sort_keys=True), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["35760084", "35797769"])
