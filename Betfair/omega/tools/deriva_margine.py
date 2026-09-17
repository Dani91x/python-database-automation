# -*- coding: utf-8 -*-
"""deriva_margine — M4: IL TEMPO E' DALLA NOSTRA PARTE? La misura APPAIATA.

LA DOMANDA. `PROGETTO_OMEGA_V4_2026-09-17.md` §1.3-bis confronta due derive misurate
SEPARATAMENTE — quella della quota di mercato (sulle registrazioni) e quella della P
del modello (su celle rappresentative con punteggio fisso) — e ne deduce che sul
Correct Score il margine migliora di ~+14 % ogni 5 minuti senza gol. Quel confronto e'
dichiarato «indizio forte, non misura», perche' le due derive non sono appaiate.

M4 le appaia: **stessa cella, stessa partita, stesso intervallo di tempo**. Per ogni
cella presente al minuto `m` e al minuto `m + delta` SENZA gol in mezzo:

    deriva_mercato = p_implicita(prezzo a m+delta) / p_implicita(prezzo a m)
    deriva_modello = p_modello(m+delta) / p_modello(m)
    deriva_margine = deriva_mercato / deriva_modello

`> 1` significa che il margine al nostro favore MIGLIORA restando fermi.

QUESTO STRUMENTO NON DECIDE NIENTE, NON TOCCA LA STRATEGIA, NON SCRIVE SUL DATABASE.

---------------------------------------------------------------------------
DA DOVE VIENE IL MODELLO, E DA DOVE VENGONO I LAMBDA (dichiarato)
---------------------------------------------------------------------------
Il modello e' `omega_v3.griglia_finale` — la funzione PURA che il banco ha eletto
vincitrice (Gamma-Poisson, `data/parametri_vincenti_2026-09-16.json`): quella che
verrebbe certificata e' quella che qui si misura.

I lambda NON vengono dalla catena di produzione (`omega_service._prematch_lambdas`
legge il DB e qui non lo si tocca) e non vengono dalle quote pre-KO (le registrazioni
partono in gioco). Vengono **fittati sul MERCATO STESSO**, una volta sola, al minuto
di ancoraggio di ogni partita: si cercano i due lambda pre-partita che riproducono al
meglio la distribuzione DEVIGATA delle scoreline quotate in quel momento. Poi si
CONGELANO. E' la fonte `market_grid` gia' prevista dalla catena di produzione
(`omega_model.lambdas_from_market_grid`), qui rifatta in forma pura.

CONSEGUENZA, e va letta: all'ancoraggio il margine e' ~1 per costruzione. M4 NON
misura il LIVELLO del margine (quello e' M0/M6): misura la sua DERIVATA nel tempo,
che e' esattamente la domanda «aspettare paga?».

---------------------------------------------------------------------------
LE DUE FALSIFICAZIONI
---------------------------------------------------------------------------
1. **cella a caso** (`--placebo cella`): la deriva del mercato di una cella viene
   appaiata con la deriva del MODELLO di un'altra cella a caso dello stesso mercato e
   dello stesso intervallo. Se l'effetto e' una proprieta' della singola cella, sparisce.
   Se resta, l'effetto e' AGGREGATO (il modello decade piu' in fretta del mercato in
   media) — vero lo stesso, ma diverso, e va detto quale dei due e'.
2. **permutazione** (`--permutazioni N`): la stessa cosa fatta N volte, per ricavare la
   distribuzione nulla della mediana e collocarci quella osservata.

LIMITI, dichiarati:
 * solo scoreline numeriche (gli aggregati «Any Unquoted» hanno una P che dipende
   dall'elenco dei quotati: la deriva non e' confrontabile cella per cella);
 * i lambda sono fittati sul mercato: il modello parte d'accordo col mercato;
 * niente flumine, niente scanner, niente ordini: e' una misura di prezzo e di modello.

Uso:
    python -m Betfair.omega.tools.deriva_margine
    python -m Betfair.omega.tools.deriva_margine --delta 5 --permutazioni 1000
    python -m Betfair.omega.tools.deriva_margine --placebo cella
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics as st
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Betfair.omega import omega_v3 as V
from Betfair.omega.tools.k_in_gioco import (
    eventi_disponibili, fascia_minuto, raccogli,
)
from Betfair.omega.tools.superficie_liability import COMMISSIONE, fascia_di

PERIODO = {"HALF_TIME_SCORE": V.PERIODO_HT, "CORRECT_SCORE": V.PERIODO_FT}
PERCORSO_PARAMETRI = os.path.join("Betfair", "omega", "data",
                                  "parametri_vincenti_2026-09-16.json")
# fit dei lambda: griglia grossa poi raffinamento locale
LAMBDA_MIN, LAMBDA_MAX = 0.25, 4.0
FIT_PASSI = 16
FIT_RAFFINAMENTI = 3
# oltre questa divergenza il fit NON riproduce il mercato: la partita si scarta
# (stessa regola di `omega_model.MARKET_FIT_MAX_LOSS`, qui su una KL)
FIT_KL_MAX = 0.35
N_MIN_COPPIE = 30


def carica_parametri(percorso: str = PERCORSO_PARAMETRI) -> V.Parametri:
    with open(percorso, encoding="utf-8") as fh:
        crudo = json.load(fh)
    pf = tuple(tuple(x) for x in (crudo.pop("peso_per_fascia", ()) or ()))
    return V.Parametri(**crudo, peso_per_fascia=pf)


def _kl(mercato: Dict[Tuple[int, int], float],
        modello: Dict[Tuple[int, int], float]) -> float:
    """KL(mercato || modello) sulle sole celle quotate, entrambe rinormalizzate."""
    som_m = sum(mercato.values())
    som_g = sum(modello.get(c, 0.0) for c in mercato)
    if som_m <= 0 or som_g <= 0:
        return float("inf")
    tot = 0.0
    for cella, pm in mercato.items():
        q = modello.get(cella, 0.0) / som_g
        p = pm / som_m
        if p <= 0:
            continue
        if q <= 1e-12:
            return float("inf")
        tot += p * math.log(p / q)
    return tot


def fitta_lambdas(*, mercato: Dict[Tuple[int, int], float], minuto: float,
                  punteggio: Tuple[int, int], periodo: str, p: V.Parametri
                  ) -> Optional[Tuple[float, float, float]]:
    """(lambda casa, lambda ospite, KL) che meglio riproducono il book devigato.

    Griglia grossa + raffinamenti locali: nessuna libreria, nessuna dipendenza."""
    if len(mercato) < 6:
        return None
    lo_h = lo_a = LAMBDA_MIN
    hi_h = hi_a = LAMBDA_MAX
    migliore: Optional[Tuple[float, float, float]] = None
    for giro in range(FIT_RAFFINAMENTI + 1):
        passi = FIT_PASSI if giro == 0 else 8
        for i in range(passi + 1):
            lh = lo_h + (hi_h - lo_h) * i / passi
            for j in range(passi + 1):
                la = lo_a + (hi_a - lo_a) * j / passi
                griglia = V.griglia_finale(minuto=minuto, punteggio=punteggio,
                                           periodo=periodo, p=p, lambdas=(lh, la))
                d = _kl(mercato, griglia)
                if migliore is None or d < migliore[2]:
                    migliore = (lh, la, d)
        if migliore is None:
            return None
        larghezza_h = (hi_h - lo_h) / passi
        larghezza_a = (hi_a - lo_a) / passi
        lo_h, hi_h = max(LAMBDA_MIN, migliore[0] - larghezza_h), min(LAMBDA_MAX, migliore[0] + larghezza_h)
        lo_a, hi_a = max(LAMBDA_MIN, migliore[1] - larghezza_a), min(LAMBDA_MAX, migliore[1] + larghezza_a)
    return migliore


def ancoraggi(righe: List[dict], p: V.Parametri) -> Dict[Tuple[str, str], dict]:
    """Per ogni (evento, mercato): lambda congelati, minuto d'ancoraggio, KL del fit."""
    per_mercato: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for r in righe:
        per_mercato[(r["event_id"], r["market_id"])].append(r)
    fuori: Dict[Tuple[str, str], dict] = {}
    for chiave, gruppo in per_mercato.items():
        tipo = gruppo[0]["mercato"]
        periodo = PERIODO.get(tipo)
        if periodo is None:
            continue
        per_minuto: Dict[int, List[dict]] = defaultdict(list)
        for r in gruppo:
            per_minuto[r["minuto"]].append(r)
        for minuto in sorted(per_minuto):
            righe_m = per_minuto[minuto]
            mercato: Dict[Tuple[int, int], float] = {}
            punteggio = None
            for r in righe_m:
                if r.get("aggregato") or r.get("p_equa") is None:
                    continue
                sc = V.parse_scoreline(r["nome"])
                if sc is None:
                    continue
                mercato[sc] = float(r["p_equa"])
                punteggio = r["punteggio"]
            if len(mercato) < 6 or punteggio is None:
                continue
            casa, osp = (int(x) for x in punteggio.split("-"))
            fit = fitta_lambdas(mercato=mercato, minuto=float(minuto),
                                punteggio=(casa, osp), periodo=periodo, p=p)
            if fit is None or not math.isfinite(fit[2]) or fit[2] > FIT_KL_MAX:
                continue
            fuori[chiave] = {"lambdas": (fit[0], fit[1]), "kl": fit[2],
                             "minuto": minuto, "periodo": periodo,
                             "punteggio": (casa, osp), "mercato": tipo,
                             "n_celle_fit": len(mercato)}
            break
    return fuori


def coppie(righe: List[dict], anc: Dict[Tuple[str, str], dict], p: V.Parametri, *,
           delta: int, distanza_minima: int) -> List[dict]:
    """Una riga per (cella, minuto -> minuto+delta) senza gol in mezzo."""
    indice: Dict[Tuple[str, str, int, int], dict] = {}
    for r in righe:
        indice[(r["event_id"], r["market_id"], int(r["selection_id"]),
                int(r["minuto"]))] = r
    cache_griglia: Dict[Tuple[str, str, int, str], Dict[Tuple[int, int], float]] = {}

    def griglia_di(chiave_mercato, minuto: int, punteggio: str):
        ck = (chiave_mercato[0], chiave_mercato[1], minuto, punteggio)
        got = cache_griglia.get(ck)
        if got is None:
            info = anc[chiave_mercato]
            casa, osp = (int(x) for x in punteggio.split("-"))
            got = V.griglia_finale(minuto=float(minuto), punteggio=(casa, osp),
                                   periodo=info["periodo"], p=p,
                                   lambdas=info["lambdas"])
            cache_griglia[ck] = got
        return got

    fuori: List[dict] = []
    for chiave, r in indice.items():
        ev, mk, sid, minuto = chiave
        info = anc.get((ev, mk))
        if info is None or minuto < info["minuto"]:
            continue
        dopo = indice.get((ev, mk, sid, minuto + int(delta)))
        if dopo is None:
            continue
        if r["punteggio"] != dopo["punteggio"]:
            continue                        # c'e' stato un gol: non e' «restare fermi»
        if r.get("aggregato") or not r.get("raggiungibile") or not dopo.get("raggiungibile"):
            continue
        if r.get("distanza_gol") is None or r["distanza_gol"] < int(distanza_minima):
            continue
        sc = V.parse_scoreline(r["nome"])
        if sc is None:
            continue
        pa = r.get("p_impl_tocco")
        pb = dopo.get("p_impl_tocco")
        if not pa or not pb:
            continue
        g1 = griglia_di((ev, mk), minuto, r["punteggio"])
        g2 = griglia_di((ev, mk), minuto + int(delta), dopo["punteggio"])
        m1, m2 = g1.get(sc, 0.0), g2.get(sc, 0.0)
        if m1 <= 0 or m2 <= 0:
            continue
        fuori.append({
            "event_id": ev, "market_id": mk, "mercato": r["mercato"],
            "selection_id": sid, "nome": r["nome"], "minuto": minuto,
            "punteggio": r["punteggio"], "fascia": r.get("fascia"),
            "minuti": fascia_minuto(minuto, 15),
            "deriva_mercato": pb / pa,
            "deriva_modello": m2 / m1,
            "deriva_margine": (pb / pa) / (m2 / m1),
            "kl_fit": info["kl"],
        })
    return fuori


def _mediana(v: Sequence[float]) -> Optional[float]:
    return round(st.median(v), 4) if v else None


def aggrega(cp: List[dict], *, n_min: int) -> dict:
    gruppi: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for c in cp:
        if c["fascia"]:
            gruppi[(c["mercato"], c["fascia"])].append(c)
    righe = []
    for chiave in sorted(gruppi):
        g = gruppi[chiave]
        dm = sorted(c["deriva_margine"] for c in g)
        righe.append({
            "mercato": chiave[0], "fascia": chiave[1],
            "n_coppie": len(g), "n_partite": len({c["event_id"] for c in g}),
            "deriva_mercato_mediana": _mediana([c["deriva_mercato"] for c in g]),
            "deriva_modello_mediana": _mediana([c["deriva_modello"] for c in g]),
            "deriva_margine_mediana": _mediana(dm),
            "deriva_margine_p25": round(dm[len(dm) // 4], 4) if dm else None,
            "deriva_margine_p75": round(dm[3 * len(dm) // 4], 4) if dm else None,
            "quota_sopra_1": round(sum(1 for x in dm if x > 1.0) / len(dm), 4) if dm else None,
            "misurabile": bool(len(g) >= int(n_min)),
        })
    return {"righe": righe}


def permutazione(cp: List[dict], *, giri: int, seme: int,
                 per_fascia: bool = False) -> dict:
    """Distribuzione nulla della mediana di `deriva_margine` quando la deriva del
    MODELLO viene appaiata con una cella A CASO dello stesso (partita, mercato,
    minuto). Se l'effetto e' una proprieta' della SINGOLA cella, la permutazione
    lo distrugge; se sopravvive, l'effetto e' aggregato — vero lo stesso, ma
    diverso, e va detto quale dei due e'.

    Con `per_fascia` la chiave di rendiconto e' (mercato, fascia): serve perche'
    l'effetto puo' esistere SOLO nella coda e sparire nella media di tutte le
    fasce."""
    rnd = random.Random(seme)
    gruppi: Dict[Tuple[str, str, int], List[dict]] = defaultdict(list)
    for c in cp:
        gruppi[(c["event_id"], c["market_id"], c["minuto"])].append(c)

    def etichetta(c: dict) -> str:
        return f"{c['mercato']} | {c['fascia']}" if per_fascia else c["mercato"]

    osservata: Dict[str, List[float]] = defaultdict(list)
    for c in cp:
        osservata[etichetta(c)].append(c["deriva_margine"])
    nulle: Dict[str, List[float]] = defaultdict(list)
    for _ in range(int(giri)):
        campione: Dict[str, List[float]] = defaultdict(list)
        for g in gruppi.values():
            if len(g) < 2:
                continue
            modelli = [c["deriva_modello"] for c in g]
            rnd.shuffle(modelli)
            for c, dmod in zip(g, modelli):
                campione[etichetta(c)].append(c["deriva_mercato"] / dmod)
        for mer, v in campione.items():
            if v:
                nulle[mer].append(st.median(v))
    fuori = {}
    for mer, v in nulle.items():
        v = sorted(v)
        oss = st.median(osservata[mer])
        piu_estremi = sum(1 for x in v if x >= oss)
        fuori[mer] = {
            "osservata": round(oss, 4),
            "n_coppie": len(osservata[mer]),
            "nulla_mediana": round(st.median(v), 4) if v else None,
            "nulla_2_5": round(v[int(0.025 * (len(v) - 1))], 4) if v else None,
            "nulla_97_5": round(v[int(0.975 * (len(v) - 1))], 4) if v else None,
            "p_valore_una_coda": round((piu_estremi + 1) / (len(v) + 1), 4) if v else None,
            "giri": len(v),
        }
    return fuori


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="M4 - deriva appaiata del margine")
    ap.add_argument("--dati", default="_live_raw")
    ap.add_argument("--eventi", nargs="*", default=None)
    ap.add_argument("--passo", type=int, default=1)
    ap.add_argument("--delta", type=int, default=5, help="minuti fra i due campioni")
    ap.add_argument("--distanza-minima", type=int, default=2)
    ap.add_argument("--n-min", type=int, default=N_MIN_COPPIE)
    ap.add_argument("--permutazioni", type=int, default=1000)
    ap.add_argument("--seme", type=int, default=20260917)
    ap.add_argument("--parametri", default=PERCORSO_PARAMETRI)
    ap.add_argument("--cache", default=os.path.join(
        "Betfair", "omega", "data", "campione_book_2026-09-17.json.gz"))
    ap.add_argument("--out", default=os.path.join(
        "Betfair", "omega", "data", "deriva_margine_2026-09-17.json"))
    args = ap.parse_args(argv)

    p = carica_parametri(args.parametri)
    eventi = args.eventi or eventi_disponibili(args.dati)
    righe = raccogli(args.dati, eventi, passo=args.passo, cache=args.cache)
    print(f"osservazioni: {len(righe)}", flush=True)
    anc = ancoraggi(righe, p)
    print(f"mercati con lambda fittati: {len(anc)} "
          f"(KL mediana {_mediana([a['kl'] for a in anc.values()])})", flush=True)
    cp = coppie(righe, anc, p, delta=args.delta,
                distanza_minima=args.distanza_minima)
    print(f"coppie (stessa cella, stesso punteggio, {args.delta}'): {len(cp)}", flush=True)
    dati = aggrega(cp, n_min=args.n_min)
    dati.update({
        "generato_il": "2026-09-17", "misura": "M4 - deriva appaiata del margine",
        "delta_minuti": args.delta, "distanza_minima_gol": args.distanza_minima,
        "parametri_modello": args.parametri, "commissione": COMMISSIONE,
        "n_osservazioni": len(righe), "n_coppie": len(cp),
        "n_mercati_ancorati": len(anc),
        "kl_fit_mediana": _mediana([a["kl"] for a in anc.values()]),
        "eventi": [str(e) for e in eventi],
    })
    if args.permutazioni:
        dati["permutazione_cella_a_caso"] = permutazione(
            cp, giri=args.permutazioni, seme=args.seme)
        dati["permutazione_per_fascia"] = permutazione(
            cp, giri=args.permutazioni, seme=args.seme, per_fascia=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"scritto {args.out}\n")

    print("{:<16}{:<11}{:>8}{:>7}{:>12}{:>12}{:>13}{:>9}{:>9}{:>10}".format(
        "mercato", "fascia", "coppie", "part.", "der.mercato", "der.modello",
        "DER.MARGINE", "p25", "p75", ">1"))
    for r in dati["righe"]:
        print("{:<16}{:<11}{:>8}{:>7}{:>12}{:>12}{:>13}{:>9}{:>9}{:>10}".format(
            r["mercato"][:15], r["fascia"], r["n_coppie"], r["n_partite"],
            f"{r['deriva_mercato_mediana']:.3f}", f"{r['deriva_modello_mediana']:.3f}",
            f"{r['deriva_margine_mediana']:.3f}", f"{r['deriva_margine_p25']:.3f}",
            f"{r['deriva_margine_p75']:.3f}",
            f"{r['quota_sopra_1'] * 100:.0f}%"))
    if args.permutazioni:
        print("\nPLACEBO «cella a caso» (permutazione della deriva del modello):")
        for mer, v in sorted(dati["permutazione_cella_a_caso"].items()):
            print(f"  {mer:<16} osservata {v['osservata']:.3f}  "
                  f"nulla {v['nulla_mediana']:.3f} "
                  f"[{v['nulla_2_5']:.3f}, {v['nulla_97_5']:.3f}]  "
                  f"p = {v['p_valore_una_coda']}")
        print()
        print("  per FASCIA (l'effetto puo' vivere solo nella coda):")
        for mer, v in sorted(dati["permutazione_per_fascia"].items()):
            print(f"  {mer:<28} n {v['n_coppie']:>5}  osservata {v['osservata']:.3f}  "
                  f"nulla {v['nulla_mediana']:.3f} "
                  f"[{v['nulla_2_5']:.3f}, {v['nulla_97_5']:.3f}]  "
                  f"p = {v['p_valore_una_coda']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
