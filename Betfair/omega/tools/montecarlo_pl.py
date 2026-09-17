# -*- coding: utf-8 -*-
"""montecarlo_pl — M5: P&L, CODA E DRAWDOWN di Omega V4, con le correlazioni vere.

LA DOMANDA. `PROGETTO_OMEGA_V4_2026-09-17.md` §5.4 stima il P&L con conti ANALITICI
su gambe indipendenti. Ma le gambe non sono indipendenti:

 * dentro un mercato le scoreline sono **mutuamente esclusive** — ne esce UNA sola,
   quindi un paniere di celle non perde tutto insieme, e non vince tutto insieme;
 * dentro una partita le due gambe (HT e FT) condividono lo stesso flusso di gol:
   una partita che segna molto le colpisce ENTRAMBE;
 * un gol uccide piu' quotazioni della stessa partita nello stesso istante.

M5 simula queste tre cose e riporta distribuzione mensile, drawdown massimo e
probabilita' di mese negativo.

QUESTO STRUMENTO NON DECIDE NIENTE, NON TOCCA LA STRATEGIA, NON SCRIVE SUL DATABASE.

---------------------------------------------------------------------------
DA DOVE VENGONO GLI INGREDIENTI (nessuno inventato)
---------------------------------------------------------------------------
| ingrediente | fonte |
|---|---|
| fasce operative, quota mediana al prezzo d'ingresso | `data/superficie_liability_*.json` (M3, book LIVE) |
| `k` per fascia (centrale e prudente) | `data/k_in_gioco_aggregato_*.json` (M6) oppure `data/prezzo_appaiato_*.json` (M0) |
| quante celle per partita in quella fascia | M3, conteggio delle celle ammissibili |
| `phi`, quota di fill di una quotazione | **NON MISURATO**: scenari 0,05/0,10/0,20/0,30, da sostituire coi numeri di M1-bis |
| selezione avversa | M1 misura 2,5x sulle celle abbinate: e' uno SCENARIO, non un default |
| dispersione fra partite (correlazione HT-FT) | `forma_gamma` 13,34 dei parametri vincenti -> cv = 1/sqrt(a) = 0,27 |

`p_vera` di una cella = `p_implicita(prezzo d'ingresso) / k`, moltiplicata per il
fattore di partita e per la selezione avversa. Con `k` prudente la simulazione e'
pessimista per costruzione: e' quella che conta.

---------------------------------------------------------------------------
LIMITI, dichiarati
---------------------------------------------------------------------------
* `phi` e' l'ipotesi, non una misura: ogni riga di risultato la porta scritta.
* La correlazione fra partite diverse (lo stesso turno di campionato) NON e'
  modellata: le partite sono indipendenti fra loro.
* Non c'e' green-up ne' chiusura anticipata: V4 tiene fino al regolamento (§4).
* Non e' un replay: e' una simulazione di P&L su probabilita' misurate altrove.

Uso:
    python -m Betfair.omega.tools.montecarlo_pl
    python -m Betfair.omega.tools.montecarlo_pl --celle 5 --selezione-avversa 2.5
    python -m Betfair.omega.tools.montecarlo_pl --seme 99   (stabilita' del seme)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics as st
from typing import Any, Dict, List, Optional, Sequence, Tuple

COMMISSIONE = 0.05
PARTITE_GIORNO = 113          # ultimo giorno Betfair misurato (11/09)
GIORNI_MESE = 30
PHI_SCENARI = (0.05, 0.10, 0.20, 0.30)
# cv della forza residua fra partite: 1/sqrt(forma_gamma), forma_gamma 13,34
CV_PARTITA = 0.27
EQUIV = {"Correct Score": "CORRECT_SCORE", "Half Time Score": "HALF_TIME_SCORE"}


class Fascia:
    """Una fascia operativa: mercato, quota d'ingresso, p implicita, k, peso."""

    __slots__ = ("mercato", "nome", "quota", "p_impl", "k", "peso", "quota_misurata")

    def __init__(self, mercato: str, nome: str, quota: float, p_impl: float,
                 k: float, peso: float) -> None:
        self.mercato = mercato
        self.nome = nome
        self.quota = float(quota)
        self.p_impl = float(p_impl)
        self.k = float(k)
        self.peso = float(peso)
        self.quota_misurata: Optional[float] = None

    def p_vera(self) -> float:
        return self.p_impl / max(1e-9, self.k)

    def come_dict(self) -> Dict[str, Any]:
        return {"mercato": self.mercato, "fascia": self.nome,
                "quota": round(self.quota, 2),
                "quota_mediana_misurata": (None if self.quota_misurata is None
                                           else round(self.quota_misurata, 2)),
                "p_impl": round(self.p_impl, 6),
                "k": round(self.k, 3), "p_vera": round(self.p_vera(), 6),
                "peso": round(self.peso, 4)}


def fasce_da_misure(*, k_json: str, superficie_json: str, livello: str,
                    k_campo: str, soglia_k: float) -> List[Fascia]:
    """Le fasce con `k` sopra soglia, con la quota mediana misurata sul book vivo."""
    kd = json.load(open(k_json, encoding="utf-8"))
    sd = json.load(open(superficie_json, encoding="utf-8"))
    quote: Dict[Tuple[str, str], List[Tuple[float, int]]] = {}
    celle: Dict[Tuple[str, str], int] = {}
    colonna = "quota_back_mediana" if livello == "best_back" else "quota_tocco_mediana"
    for r in sd["righe"]:
        v = r.get(colonna)
        chiave = (r["mercato"], r["fascia"])
        celle[chiave] = celle.get(chiave, 0) + int(r["n_celle"])
        if v is not None:
            quote.setdefault(chiave, []).append((float(v), int(r["n_celle"])))

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

    fuori: List[Fascia] = []
    for r in kd["righe"]:
        mercato = EQUIV.get(r["mercato"], r["mercato"])
        nome = r.get("fascia") or r.get("secchio")
        k = r.get(k_campo)
        if k is None or float(k) < float(soglia_k):
            continue
        chiave = (mercato, nome)
        misurata = mediana_pesata(quote.get(chiave, []))
        p_impl = r.get(f"p_impl_{livello}")
        if p_impl is None or float(p_impl) <= 0:
            continue
        # LA QUOTA SI DERIVA DALLA STESSA `p_impl` con cui si calcola `p_vera`.
        # Mescolare la quota MEDIANA misurata con la `p_impl` MEDIA e' un errore:
        # le due non descrivono la stessa cella, e il P&L simulato esce sbagliato
        # (misurato: quota mediana 46 contro quota implicita 34,4 sul CS 1-2 %).
        # La quota misurata resta nel referto come controllo.
        L = (1.0 - COMMISSIONE) / float(p_impl) + COMMISSIONE
        f = Fascia(mercato, nome, L, float(p_impl), float(k),
                   float(celle.get(chiave, 0)))
        f.quota_misurata = misurata
        fuori.append(f)
    tot = sum(f.peso for f in fuori)
    for f in fuori:
        f.peso = (f.peso / tot) if tot > 0 else (1.0 / max(1, len(fuori)))
    return fuori


def _scegli(fasce: Sequence[Fascia], u: float) -> Fascia:
    acc = 0.0
    for f in fasce:
        acc += f.peso
        if u <= acc:
            return f
    return fasce[-1]


def simula_giorno(fasce_per_mercato: Dict[str, List[Fascia]], *, partite: int,
                  celle: int, phi: float, liability: float, commissione: float,
                  selezione_avversa: float, cv_partita: float,
                  rnd: random.Random) -> Tuple[float, int, int, float]:
    """(P&L del giorno, gambe abbinate, perdite, liability massima simultanea)."""
    pnl = 0.0
    abbinate = 0
    perdite = 0
    liab_max = 0.0
    for _ in range(partite):
        # fattore di PARTITA: una partita che segna molto alza la probabilita' di
        # OGNI cella di coda, su tutt'e due le gambe. E' la correlazione vera.
        fattore = math.exp(rnd.gauss(0.0, cv_partita) - 0.5 * cv_partita ** 2)
        liab_partita = 0.0
        for mercato, fasce in fasce_per_mercato.items():
            if not fasce:
                continue
            scelte: List[Fascia] = []
            for _c in range(celle):
                scelte.append(_scegli(fasce, rnd.random()))
            riempite = [f for f in scelte if rnd.random() < phi]
            if not riempite:
                continue
            abbinate += len(riempite)
            liab_partita += liability * len(riempite)
            # UNA sola scoreline esce: si estrae una volta sola per mercato
            probabilita = [min(0.95, f.p_vera() * fattore * selezione_avversa)
                           for f in riempite]
            u = rnd.random()
            acc = 0.0
            vincente = -1
            for i, p in enumerate(probabilita):
                acc += p
                if u <= acc:
                    vincente = i
                    break
            for i, f in enumerate(riempite):
                stake = liability / max(1e-9, f.quota - 1.0)
                if i == vincente:
                    pnl -= liability
                    perdite += 1
                else:
                    pnl += stake * (1.0 - commissione)
        liab_max = max(liab_max, liab_partita)
    return pnl, abbinate, perdite, liab_max


def simula(fasce: Sequence[Fascia], *, mesi: int, giorni: int, partite: int,
           celle: int, phi: float, liability: float, commissione: float,
           selezione_avversa: float, cv_partita: float, seme: int) -> Dict[str, Any]:
    per_mercato: Dict[str, List[Fascia]] = {}
    for f in fasce:
        per_mercato.setdefault(f.mercato, []).append(f)
    for mercato, lista in per_mercato.items():
        tot = sum(x.peso for x in lista)
        for x in lista:
            x.peso = (x.peso / tot) if tot > 0 else 1.0 / len(lista)

    rnd = random.Random(seme)
    mensili: List[float] = []
    drawdown: List[float] = []
    gambe: List[int] = []
    perdite_mese: List[int] = []
    picco_liab: List[float] = []
    for _ in range(int(mesi)):
        cumulato = 0.0
        massimo = 0.0
        dd = 0.0
        g = 0
        pr = 0
        pl = 0.0
        for _giorno in range(int(giorni)):
            pnl, ab, pe, lm = simula_giorno(
                per_mercato, partite=partite, celle=celle, phi=phi,
                liability=liability, commissione=commissione,
                selezione_avversa=selezione_avversa, cv_partita=cv_partita, rnd=rnd)
            cumulato += pnl
            g += ab
            pr += pe
            pl = max(pl, lm)
            massimo = max(massimo, cumulato)
            dd = max(dd, massimo - cumulato)
        mensili.append(cumulato)
        drawdown.append(dd)
        gambe.append(g)
        perdite_mese.append(pr)
        picco_liab.append(pl)

    mensili_ord = sorted(mensili)
    dd_ord = sorted(drawdown)

    def q(v: List[float], p: float) -> float:
        return round(v[min(len(v) - 1, max(0, int(p * (len(v) - 1))))], 2)

    return {
        "phi": phi, "celle_per_gamba": celle, "liability_per_gamba": liability,
        "selezione_avversa": selezione_avversa, "mesi_simulati": int(mesi),
        "giorni_per_mese": int(giorni), "partite_giorno": partite, "seme": seme,
        "gambe_abbinate_per_mese_media": round(st.mean(gambe), 1),
        "gambe_abbinate_per_giorno_media": round(st.mean(gambe) / giorni, 2),
        "perdite_per_mese_media": round(st.mean(perdite_mese), 2),
        "pnl_mensile_medio": round(st.mean(mensili), 2),
        "pnl_mensile_mediano": round(st.median(mensili), 2),
        "pnl_mensile_ds": round(st.pstdev(mensili), 2),
        "pnl_mensile_p05": q(mensili_ord, 0.05),
        "pnl_mensile_p25": q(mensili_ord, 0.25),
        "pnl_mensile_p75": q(mensili_ord, 0.75),
        "pnl_mensile_p95": q(mensili_ord, 0.95),
        "prob_mese_negativo": round(sum(1 for x in mensili if x < 0) / len(mensili), 4),
        "drawdown_medio": round(st.mean(drawdown), 2),
        "drawdown_mediano": round(st.median(drawdown), 2),
        "drawdown_p95": q(dd_ord, 0.95),
        "drawdown_massimo": round(max(drawdown), 2),
        "liability_di_partita_picco_medio": round(st.mean(picco_liab), 2),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="M5 - Monte Carlo di P&L e drawdown")
    ap.add_argument("--k-json", default=os.path.join(
        "Betfair", "omega", "data", "k_in_gioco_aggregato_2026-09-17.json"))
    ap.add_argument("--superficie", default=os.path.join(
        "Betfair", "omega", "data", "superficie_liability_2026-09-17.json"))
    ap.add_argument("--livello", default="best_back", choices=("best_back", "mid", "tocco"))
    ap.add_argument("--k-campo", default="k_best_back_prudente")
    ap.add_argument("--soglia-k", type=float, default=1.0)
    ap.add_argument("--partite", type=int, default=PARTITE_GIORNO)
    ap.add_argument("--celle", type=int, default=1, help="celle quotate per gamba (paniere)")
    ap.add_argument("--liability", type=float, default=30.0)
    ap.add_argument("--commissione", type=float, default=COMMISSIONE)
    ap.add_argument("--selezione-avversa", type=float, default=1.0)
    ap.add_argument("--cv-partita", type=float, default=CV_PARTITA)
    ap.add_argument("--mesi", type=int, default=2000)
    ap.add_argument("--giorni", type=int, default=GIORNI_MESE)
    ap.add_argument("--seme", type=int, default=20260917)
    ap.add_argument("--phi", type=float, nargs="*", default=list(PHI_SCENARI))
    ap.add_argument("--out", default=os.path.join(
        "Betfair", "omega", "data", "montecarlo_pl_2026-09-17.json"))
    args = ap.parse_args(argv)

    fasce = fasce_da_misure(k_json=args.k_json, superficie_json=args.superficie,
                            livello=args.livello, k_campo=args.k_campo,
                            soglia_k=args.soglia_k)
    if not fasce:
        print("nessuna fascia sopra la soglia di k: non c'e' niente da simulare.")
        return 1
    print(f"fasce operative ({args.k_campo} >= {args.soglia_k}, livello {args.livello}):")
    for f in fasce:
        misurata = "-" if f.quota_misurata is None else f"{f.quota_misurata:.0f}"
        print(f"  {f.mercato:<16} {f.nome:<10} quota {f.quota:>6.1f} "
              f"(mediana misurata {misurata:>4})  "
              f"p_impl {f.p_impl * 100:>6.3f}%  k {f.k:>5.2f}  "
              f"p_vera {f.p_vera() * 100:>6.3f}%  peso {f.peso:.3f}")
    print()

    risultati = []
    for phi in args.phi:
        r = simula(fasce, mesi=args.mesi, giorni=args.giorni, partite=args.partite,
                   celle=args.celle, phi=float(phi), liability=args.liability,
                   commissione=args.commissione,
                   selezione_avversa=args.selezione_avversa,
                   cv_partita=args.cv_partita, seme=args.seme)
        risultati.append(r)

    dati = {
        "generato_il": "2026-09-17", "misura": "M5 - Monte Carlo di P&L e drawdown",
        "fonte_k": args.k_json, "fonte_quote": args.superficie,
        "livello_ingresso": args.livello, "k_campo": args.k_campo,
        "fasce": [f.come_dict() for f in fasce],
        "risultati": risultati,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"scritto {args.out}\n")

    print("{:>6}{:>8}{:>10}{:>11}{:>11}{:>10}{:>10}{:>11}{:>10}{:>11}".format(
        "phi", "gambe/g", "perdite/m", "P&L medio", "mediano", "p05", "p95",
        "mese neg.", "DD med.", "DD p95"))
    for r in risultati:
        print("{:>6}{:>8}{:>10}{:>11}{:>11}{:>10}{:>10}{:>11}{:>10}{:>11}".format(
            f"{r['phi']:.2f}", f"{r['gambe_abbinate_per_giorno_media']:.1f}",
            f"{r['perdite_per_mese_media']:.1f}", f"{r['pnl_mensile_medio']:+.0f}",
            f"{r['pnl_mensile_mediano']:+.0f}", f"{r['pnl_mensile_p05']:+.0f}",
            f"{r['pnl_mensile_p95']:+.0f}",
            f"{r['prob_mese_negativo'] * 100:.1f}%",
            f"{r['drawdown_medio']:.0f}", f"{r['drawdown_p95']:.0f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
