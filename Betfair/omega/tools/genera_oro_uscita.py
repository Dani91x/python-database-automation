# -*- coding: utf-8 -*-
"""Genera (o verifica) i VETTORI D'ORO dell'uscita di Omega al prezzo di adesso
(24/09/2026): lega ``omega_proposte.esito_uscita_al_prezzo`` (Python) alla porta
TypeScript ``esitoUscitaAlPrezzo`` di ``frontend/src/lib/omegaProposte.ts``.

    python -m Betfair.omega.tools.genera_oro_uscita           # verifica
    python -m Betfair.omega.tools.genera_oro_uscita --scrivi  # rigenera

Deterministico: i casi coprono ogni ramo della decisione (cap, rischio,
protezione, bloccabile non positivo, tenere, aspettare, blocca il profitto,
controparte, nessun prezzo) e i valori non validi. ASCII-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from Betfair.omega import omega_proposte as PR

ORO = Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "omegaUscita.golden.json"

_BASE = {"lay_price": 4.0, "size": 1.0, "back_price": 6.0, "back_size": 100.0,
         "ev_tenere": 0.10, "max_attesa": None, "p_evento": 0.20,
         "commissione": 0.05, "margine_attesa": 0.02, "cap_scattato": None,
         "p_lose_max": 0.0}


def casi() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def c(nome: str, **kw: Any) -> None:
        out.append({"nome": nome, "ingresso": {**_BASE, **kw}})

    c("blocca il profitto")
    c("tenere vale di piu", ev_tenere=0.5)
    c("aspettare vale di piu", max_attesa=0.6)
    c("aspettare entro il margine", max_attesa=0.33)
    c("controparte insufficiente", back_size=0.5)
    c("cap scattato in profitto", cap_scattato="v3_max_liability_per_leg")
    c("cap scattato in perdita", back_price=3.0, cap_scattato="max_open_liability")
    c("rischio oltre soglia", p_lose_max=0.15, p_evento=0.2)
    c("rischio sotto soglia", p_lose_max=0.25, p_evento=0.2)
    c("protezione", back_price=3.0, ev_tenere=-0.5)
    c("bloccabile non positivo", back_price=3.0, ev_tenere=0.0)
    c("pareggio esatto", back_price=4.0, ev_tenere=-0.1)
    c("nessun prezzo di back", back_price=None)
    c("back 1.0", back_price=1.0)
    c("commissione alta tagliata a 0.5", commissione=0.9)
    c("commissione zero", commissione=0.0, back_price=5.0)
    c("size grande", size=12.5, lay_price=2.3, back_price=2.9, back_size=500.0,
      ev_tenere=0.4)
    c("posizione senza numeri", lay_price=None)
    c("lay 1.0", lay_price=1.0)
    c("ev assente", ev_tenere=None)
    c("stringhe non numeri", back_price="6.0")
    return out


def calcola() -> list[dict[str, Any]]:
    return [{**caso, "uscita": PR.esito_uscita_al_prezzo(**caso["ingresso"])}
            for caso in casi()]


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
