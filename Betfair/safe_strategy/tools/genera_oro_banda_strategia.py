# -*- coding: utf-8 -*-
"""Genera (o verifica) i VETTORI D'ORO della BANDA DELLA STRATEGIA fra Python e
TypeScript (D7, 25/09/2026).

    python -m Betfair.safe_strategy.tools.genera_oro_banda_strategia          # verifica
    python -m Betfair.safe_strategy.tools.genera_oro_banda_strategia --scrivi # rigenera

Il file ``frontend/src/lib/bandaStrategia.golden.json`` contiene INGRESSI e
USCITE di ``proposte_opportunita.banda_della_strategia`` e ``in_banda``. Il
test Python (``tests/test_esecuzione_a_mercato_d7_2026_09_25.py``) pretende che
il Python di oggi riproduca le uscite; il test TypeScript
(``valutaProposta.banda.test.ts``) pretende lo stesso da ``bandaDellaStrategia``
/ ``inBanda``. Se una delle due cambia da sola, un test diventa rosso.

Deterministico; i criteri sono quelli di ``genera_oro_valuta_proposta`` (gli
stessi ingressi di prova). ASCII-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from Betfair.safe_strategy import proposte_opportunita as PO
from Betfair.safe_strategy.tools.genera_oro_valuta_proposta import _ANOMALIA, _MODELLO, _TENNIS

ORO = Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "bandaStrategia.golden.json"

# prezzi su cui si verifica ``in_banda`` (bordi compresi)
_PREZZI = (1.01, 1.02, 1.04, 1.05, 1.3, 1.31, 1.32, 1.4, 1.44, 1.46, 2.14, 2.5, 4.3, 4.4,
           4.8, 5.0, 5.1, 20.0, 1000.0)


def casi() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def c(nome: str, side: Any, p_model: Any, criteri: Any) -> None:
        out.append({"nome": nome, "ingresso": {"side": side, "p_model": p_model,
                                               "criteri": criteri}})

    c("tennis back p 0.99", "back", 0.99, _TENNIS)
    c("tennis back p 0.77", "back", 0.77, _TENNIS)
    c("tennis lay p 0.01", "lay", 0.01, _TENNIS)
    c("tennis lay p 0.2 (probabilita' fuori: non e' prezzo)", "lay", 0.2, _TENNIS)
    c("modello back p 0.999", "back", 0.999, _MODELLO)
    c("modello back p 0.5", "back", 0.5, _MODELLO)
    c("modello lay p 0.1", "lay", 0.1, _MODELLO)
    c("anomalia back p 0.7", "back", 0.7, _ANOMALIA)
    c("anomalia lay p 0.2", "lay", 0.2, _ANOMALIA)
    c("anomalia lay p 0.7 (banda sotto 1.42)", "lay", 0.7, _ANOMALIA)
    c("banda vuota (lay p 1.0)", "lay", 1.0, _ANOMALIA)
    c("senza criteri", "back", 0.8, None)
    c("p assente", "back", None, _MODELLO)
    c("p oltre 1", "back", 1.5, _MODELLO)
    c("lato sbagliato", "punta", 0.8, _MODELLO)
    c("criteri vuoti back", "back", 0.8, {})
    # l'edge minimo del MOTORE e' quello che morde (non l'EV ne' il servizio)
    c("edge del motore stringente back", "back", 0.99,
      {"min_edge": 0.1, "commission": 0.05, "stake": 5.0})
    c("edge del motore stringente lay", "lay", 0.2,
      {"min_edge": 0.2, "commission": 0.05, "stake": 5.0})
    return out


def calcola() -> list[dict[str, Any]]:
    fuori = []
    for caso in casi():
        ing = caso["ingresso"]
        banda = PO.banda_della_strategia(**ing)
        dentro = {f"{p:g}": PO.in_banda(prezzo=p, **ing) for p in _PREZZI}
        fuori.append({**caso, "uscita": {"banda": banda, "in_banda": dentro}})
    return fuori


def main(argv: list[str]) -> int:
    dati = calcola()
    testo = json.dumps(dati, indent=1, sort_keys=True, ensure_ascii=True) + "\n"
    if "--scrivi" in argv:
        ORO.write_text(testo, encoding="utf-8", newline="\n")
        print(f"scritto {ORO} ({len(dati)} casi)")
        return 0
    attuale = ORO.read_text(encoding="utf-8") if ORO.exists() else ""
    if json.loads(attuale or "[]") != json.loads(testo):
        print("il file d'oro NON corrisponde al Python di oggi")
        return 1
    print(f"file d'oro coerente ({len(dati)} casi)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
