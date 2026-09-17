# -*- coding: utf-8 -*-
"""ev_per_liability — DOVE CONVIENE QUOTARE: EV per euro di liability, per fascia.

Non misura niente di nuovo: COMPONE due misure gia' fatte e versionate, e scrive
la tabella che decide dove Omega V4 deve stare.

  (1) `data/prezzo_appaiato_2026-09-17.json` — il margine k PRUDENTE per fascia e
      per prezzo d'ingresso (tocco / 1 tick / mid / best back), misurato su 48.280
      selezioni pre-match con bootstrap a grappolo sulle partite
      (`tools/misura_prezzo_appaiata.py`).
  (2) `data/superficie_liability_2026-09-17.json` — la quota mediana a cui si entra
      in quella fascia, quindi la LIABILITY per euro di stake, misurata sul book
      LIVE registrato (`tools/superficie_liability.py`).

La formula e' quella della tesi (VISIONE_OMEGA_V4 §9):

    EV / euro di liability = (1 - c) * (1 - 1/k) / (L - 1)
    EV per gamba           = liability_gamba * (EV / euro di liability)

k <= 1 => EV negativo: la riga si stampa, ma con il segno che ha.

LIMITI, dichiarati (nessuno dei due e' aggirabile leggendo la tabella piu' forte):
 * k viene da quote PRE-MATCH: e' un prior del bias, non il bias live;
 * k suppone il FILL a quel prezzo. La quota di fill e la selezione avversa le
   misura `tools/misura_ingresso_passivo.py` (M1) ed entrano MOLTIPLICANDO, non
   sommando: una riga con EV alto e fill 1,7 % vale 1,7 % di quell'EV.

Uso:
    python -m Betfair.omega.tools.ev_per_liability
    python -m Betfair.omega.tools.ev_per_liability --livello mid --liability 30
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple

COMMISSIONE = 0.05
# nomi dei mercati: le due misure li scrivono in modo diverso (la prima viene da
# `betfair_market_odds.market_name`, la seconda dal `marketType` dello stream).
EQUIVALENTI = {"Correct Score": "CORRECT_SCORE", "Half Time Score": "HALF_TIME_SCORE"}


def ev_per_euro(k: Optional[float], L: Optional[float], c: float) -> Optional[float]:
    if k is None or L is None or L <= 1.0:
        return None
    return (1.0 - c) * (1.0 - 1.0 / float(k)) / (float(L) - 1.0)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="EV per euro di liability, per fascia")
    ap.add_argument("--k", default=os.path.join("Betfair", "omega", "data",
                                                "prezzo_appaiato_2026-09-17.json"))
    ap.add_argument("--superficie", default=os.path.join(
        "Betfair", "omega", "data", "superficie_liability_2026-09-17.json"))
    ap.add_argument("--livello", default="best_back",
                    choices=("tocco", "1tick", "mid", "best_back"))
    ap.add_argument("--liability", type=float, default=30.0,
                    help="liability per gamba, in EUR (dimensionamento a liability fissa)")
    ap.add_argument("--commissione", type=float, default=COMMISSIONE)
    ap.add_argument("--prudente", action="store_true", default=True)
    args = ap.parse_args(argv)

    kd = json.load(open(args.k, encoding="utf-8"))
    sd = json.load(open(args.superficie, encoding="utf-8"))

    # k prudente per (mercato normalizzato, fascia)
    ktab: Dict[Tuple[str, str], Optional[float]] = {}
    for r in kd["righe"]:
        mer = EQUIVALENTI.get(r["mercato"], r["mercato"])
        ktab[(mer, r["secchio"])] = r.get(f"k_{args.livello}_prudente")

    # quota mediana per (mercato, fascia), pesata sulle celle, dal book LIVE
    campioni: Dict[Tuple[str, str], List[Tuple[float, int]]] = {}
    for r in sd["righe"]:
        tocco, back = r.get("quota_tocco_mediana"), r.get("quota_back_mediana")
        if args.livello == "best_back":
            v = back
        elif args.livello == "mid" and tocco and back:
            # mid in PROBABILITA' (la stessa convenzione di misura_prezzo_appaiata)
            v = 2.0 / (1.0 / float(tocco) + 1.0 / float(back))
        else:
            v = tocco
        if v is None:
            continue
        campioni.setdefault((r["mercato"], r["fascia"]), []).append((float(v), r["n_celle"]))

    def mediana_pesata(v: List[Tuple[float, int]]) -> Optional[float]:
        if not v:
            return None
        tot = sum(w for _, w in v)
        acc = 0
        for x, w in sorted(v):
            acc += w
            if acc >= tot / 2:
                return x
        return v[-1][0]

    print(f"livello d'ingresso: {args.livello}   commissione {args.commissione}   "
          f"liability per gamba {args.liability:.2f} EUR\n")
    print("{:<16}{:<11}{:>9}{:>10}{:>12}{:>14}{:>13}".format(
        "mercato", "fascia", "k prud.", "quota", "liab/EUR di", "EV per EUR", "EV per gamba"))
    print("{:<16}{:<11}{:>9}{:>10}{:>12}{:>14}{:>13}".format(
        "", "", "", "mediana", "stake", "di liability", "(EUR)"))
    righe_out = []
    for chiave in sorted(campioni):
        L = mediana_pesata(campioni[chiave])
        k = ktab.get(chiave)
        ev = ev_per_euro(k, L, args.commissione)
        righe_out.append({"mercato": chiave[0], "fascia": chiave[1],
                          "k_prudente": k, "quota_mediana": L,
                          "ev_per_euro_liability": ev,
                          "ev_per_gamba": None if ev is None else round(ev * args.liability, 4)})
        print("{:<16}{:<11}{:>9}{:>10}{:>12}{:>14}{:>13}".format(
            chiave[0][:15], chiave[1],
            "-" if k is None else f"{k:.2f}",
            "-" if L is None else f"{L:.0f}",
            "-" if L is None else f"{L - 1:.0f}",
            "-" if ev is None else f"{ev * 100:.3f}%",
            "-" if ev is None else f"{ev * args.liability:+.3f}"))
    print("\nEV per EUR di liability = (1-c)(1-1/k)/(L-1). k <= 1 => segno negativo.")
    print("Va MOLTIPLICATO per la quota di fill del livello scelto (M1: best back 1,7 %,")
    print("mid 10,2 %, 1 tick 11,3 % per PIAZZAMENTO singolo di ~2-3 minuti).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
