# -*- coding: utf-8 -*-
"""Genera (o verifica) i VETTORI D'ORO che legano la rivalutazione al prezzo
di una proposta fra Python e TypeScript (24/09/2026).

    python -m Betfair.safe_strategy.tools.genera_oro_valuta_proposta          # verifica
    python -m Betfair.safe_strategy.tools.genera_oro_valuta_proposta --scrivi # rigenera

Il file ``frontend/src/lib/valutaProposta.golden.json`` contiene INGRESSI e
USCITE di ``proposte_opportunita.valuta_al_prezzo``. Il test Python
(``tests/test_scheda_al_ms_2026_09_24.py``) pretende che il Python di oggi
riproduca le uscite; il test TypeScript (``valutaProposta.test.ts``) pretende
lo stesso dalla porta TS. Se una delle due funzioni cambia da sola, un test
diventa rosso: mai una copia divergente.

Deterministico (nessun caso casuale): i casi coprono ogni criterio, i due lati,
i confini (== soglia) e i valori non validi. ASCII-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from Betfair.safe_strategy import proposte_opportunita as PO

ORO = Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "valutaProposta.golden.json"

# criteri tipici di ciascun motore (valori dei default di oggi, qui SOLO come
# ingressi di prova: il servizio li legge sempre dai parametri effettivi)
_MODELLO = {"min_edge": 0.03, "min_size": 20.0, "max_lay_price": 5.0,
            "commission": 0.05, "min_prob_back": 0.95, "max_prob_lay": 0.0,
            "opps_min_edge": 0.03, "max_liability_per_trade": 0.0, "stake": 5.0}
_TENNIS = {"min_edge": 0.015, "min_size": 20.0, "max_lay_price": 8.0,
           "min_back_price": 1.02, "commission": 0.05, "min_prob_back": 0.90,
           "max_prob_lay": 0.10, "opps_min_edge": 0.03,
           "max_liability_per_trade": 20.0, "stake": 5.0}
_ANOMALIA = {"min_edge": 0.005, "min_size": 10.0, "max_lay_price": 5.0,
             "commission": 0.05, "opps_min_edge": 0.0,
             "max_liability_per_trade": 0.0, "stake": 2.0}


def casi() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def c(nome: str, side: Any, prezzo: Any, abbinabile: Any, p_model: Any,
          criteri: Any) -> None:
        out.append({"nome": nome, "ingresso": {"side": side, "prezzo": prezzo,
                                               "abbinabile": abbinabile,
                                               "p_model": p_model, "criteri": criteri}})

    # modello calcio, back
    c("modello back valido", "back", 1.10, 300.0, 0.999, _MODELLO)
    c("modello back edge sotto soglia", "back", 1.04, 300.0, 0.985, _MODELLO)
    c("modello back p sotto minimo", "back", 1.02, 300.0, 0.90, _MODELLO)
    c("modello back abbinabile scarso", "back", 1.10, 10.0, 0.999, _MODELLO)
    c("modello back abbinabile ignoto", "back", 1.10, None, 0.999, _MODELLO)
    c("modello back ev negativo", "back", 1.03, 300.0, 0.96, _MODELLO)
    c("modello back quota al tick contro", "back", 1.03, 300.0, 0.995, _MODELLO)
    c("modello lay spento (max_prob_lay 0)", "lay", 1.5, 300.0, 0.10, _MODELLO)
    c("modello lay p zero", "lay", 1.5, 300.0, 0.0, _MODELLO)
    c("modello lay oltre quota massima", "lay", 6.0, 300.0, 0.0, _MODELLO)
    # tennis
    c("tennis back valido", "back", 1.05, 50.0, 0.99, _TENNIS)
    c("tennis back quota sotto minimo", "back", 1.01, 50.0, 0.999, _TENNIS)
    c("tennis lay valido", "lay", 5.0, 50.0, 0.01, _TENNIS)
    c("tennis lay oltre quota (20)", "lay", 20.0, 50.0, 0.01, _TENNIS)
    c("tennis lay oltre quota e tetto", "lay", 9.0, 50.0, 0.01, _TENNIS)
    c("tennis lay entro quota, tetto superato", "lay", 5.5, 50.0, 0.01, _TENNIS)
    c("tennis lay p sopra massimo", "lay", 3.0, 50.0, 0.2, _TENNIS)
    # anomalie (niente min_prob_*)
    c("anomalia back decided valida", "back", 1.08, 40.0, 1.0, _ANOMALIA)
    c("anomalia back edge sotto", "back", 1.9, 40.0, 0.52, _ANOMALIA)
    c("anomalia lay valida", "lay", 1.2, 40.0, 0.0, _ANOMALIA)
    c("anomalia lay oltre quota", "lay", 5.5, 40.0, 0.0, _ANOMALIA)
    # confini esatti
    c("confine min_size uguale", "back", 1.10, 20.0, 0.999, _MODELLO)
    c("confine max_lay_price uguale", "lay", 5.0, 300.0, 0.0, _MODELLO)
    c("confine tetto uguale", "lay", 5.0, 50.0, 0.0, {**_TENNIS, "stake": 5.0,
                                                    "max_liability_per_trade": 20.0})
    # valori non validi (fail-closed)
    c("prezzo assente", "back", None, 300.0, 0.995, _MODELLO)
    c("prezzo 1.0", "back", 1.0, 300.0, 0.995, _MODELLO)
    c("prezzo stringa", "back", "2.0", 300.0, 0.995, _MODELLO)
    c("p assente", "back", 1.02, 300.0, None, _MODELLO)
    c("p oltre 1", "back", 1.02, 300.0, 1.5, _MODELLO)
    c("lato sbagliato", "punta", 1.02, 300.0, 0.995, _MODELLO)
    c("criteri assenti", "back", 1.5, 300.0, 0.8, None)
    c("criteri vuoti lay", "lay", 1.5, 300.0, 0.2, {})
    c("commissione zero", "back", 1.5, 300.0, 0.8, {"commission": 0.0, "stake": 3.0})
    c("bool come prezzo", "back", True, 300.0, 0.8, _MODELLO)
    return out


def calcola() -> list[dict[str, Any]]:
    fuori = []
    for caso in casi():
        ing = caso["ingresso"]
        fuori.append({**caso, "uscita": PO.valuta_al_prezzo(**ing)})
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
