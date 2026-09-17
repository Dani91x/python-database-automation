# -*- coding: utf-8 -*-
"""k_in_gioco — M6: IL MARGINE SUL BOOK IN GIOCO, per fascia, per minuto, per prezzo.

LA DOMANDA. `tools/misura_prezzo_appaiata.py` (M0) misura `k = p_implicita / p_reale`
su 48.280 selezioni **pre-match** e trova che al miglior back il margine c'e' nella
coda. Il referto M1 (`INGRESSO_PASSIVO_MISURA_2026-09-17.md` §6.1) avverte che il book
**in gioco** e' peggiore: `k` al tocco 0,49 contro 0,80 pre-match, ma su 293 celle e
12 uscite. M6 rifa' quella misura **su campione serio**: tutte le registrazioni, tutte
le celle candidate a ogni minuto, con l'esito AUTOREVOLE del `marketDefinition`.

QUESTO STRUMENTO NON DECIDE NIENTE, NON TOCCA LA STRATEGIA, NON SCRIVE SUL DATABASE.

---------------------------------------------------------------------------
METODO
---------------------------------------------------------------------------
* Osservazioni da `tools/superficie_liability.campiona_evento`: ladder dai `rc`
  NATIVI, minuto e punteggio dal sidecar (mai dall'orologio), nomi dalle formule
  dei gusci, mercato OPEN + in gioco + runner ACTIVE.
* **Esito**: il `WINNER` del `marketDefinition` finale (`vincitori()`). Il sidecar
  resta come controprova: le discordanze si contano e si dichiarano.
* **Tre prezzi**, gli stessi di M0 e di M1: `tocco` (best availableToLay),
  `mid` (mid dei due lati, al tick, dentro lo spread), `best_back`.
* **Secchi**: (mercato) x (fascia di `p_implicita` AL TOCCO) x (fascia di minuto,
  ampiezza `--minuto-passo`). La fascia si definisce UNA volta sola sul tocco: cosi'
  i tre prezzi si confrontano sulle STESSE celle (misura appaiata).
* **Intervalli**: bootstrap a grappolo sulle PARTITE. Le celle della stessa partita
  non sono indipendenti (ne esce una sola per mercato) e, qui, nemmeno quelle dello
  stesso minuto: si ricampionano le PARTITE con reimmissione.
* `k prudente` = `p_implicita media / estremo ALTO del bootstrap di p_reale`: il k
  che si puo' difendere.

---------------------------------------------------------------------------
LE DUE FALSIFICAZIONI
---------------------------------------------------------------------------
1. **placebo CALIBRATO** (`--placebo calibrato`): l'esito non e' quello vero, e' un
   vincitore ESTRATTO dalla distribuzione DEVIGATA del mercato in quel minuto. Sotto
   questa ipotesi il mercato e' perfettamente calibrato per costruzione, quindi
   `k` deve tornare `p_implicita(livello) / p_equa` — cioe' **~1 al livello devigato**,
   < 1 al tocco e > 1 al miglior back, PER SOLA GEOMETRIA DEL LIBRO. Se non torna,
   l'errore e' nello stimatore, non nel mercato.
2. **placebo PERMUTATO** (`--placebo permutato`): i vincitori veri vengono scambiati
   fra le partite (stesso mercato). L'informazione sparisce: la struttura per fascia
   deve appiattirsi. Se il `k` misurato sopravvive alla permutazione, non stava
   misurando il mercato.

---------------------------------------------------------------------------
LIMITI, dichiarati
---------------------------------------------------------------------------
* NON e' un replay del bot: niente flumine, niente scanner, niente ordini. E' una
  misura di PREZZO e di ESITO. La condotta si certifica solo dal banco comune.
* `k` al `mid` e al `best_back` suppone il FILL a quel prezzo: non contiene la
  selezione avversa (che M1 misura, e che va MOLTIPLICATA, non sommata).
* Una sola scoreline esce per mercato: le uscite restano poche anche con tutte le
  registrazioni. Le righe sotto `--n-min-uscite` sono `misurabile: false`.

Uso:
    python -m Betfair.omega.tools.k_in_gioco
    python -m Betfair.omega.tools.k_in_gioco --passo 1 --minuto-passo 10 --boot 2000
    python -m Betfair.omega.tools.k_in_gioco --placebo calibrato --seme 7
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Betfair.omega.tools.superficie_liability import (
    COMMISSIONE, MERCATI, campiona_evento,
)

LIVELLI: Tuple[str, ...] = ("tocco", "mid", "best_back")
CAMPO_P = {"tocco": "p_impl_tocco", "mid": "p_impl_mid", "best_back": "p_impl_back"}
N_MIN_USCITE = 5


def fascia_minuto(minuto: int, passo: int) -> str:
    lo = ((int(minuto) - 1) // int(passo)) * int(passo) + 1
    return f"{lo}-{lo + int(passo) - 1}"


def bootstrap_grappolo(per_partita: Dict[str, Tuple[int, int]], *, giri: int,
                       seme: int) -> Tuple[float, float]:
    """(2,5 %, 97,5 %) di p_reale ricampionando le PARTITE con reimmissione."""
    chiavi = list(per_partita)
    if not chiavi:
        return 0.0, 1.0
    rnd = random.Random(seme)
    campioni: List[float] = []
    for _ in range(int(giri)):
        u = d = 0
        for _ in range(len(chiavi)):
            a, b = per_partita[chiavi[rnd.randrange(len(chiavi))]]
            u += a
            d += b
        if d:
            campioni.append(u / d)
    if not campioni:
        return 0.0, 1.0
    campioni.sort()
    return (campioni[int(0.025 * (len(campioni) - 1))],
            campioni[int(0.975 * (len(campioni) - 1))])


# ---------------------------------------------------------------------------
# raccolta (una passata sui raw, riusabile da M4)
# ---------------------------------------------------------------------------
def eventi_disponibili(dati: str) -> List[str]:
    return sorted(n for n in os.listdir(dati)
                  if n.isdigit()
                  and os.path.exists(os.path.join(dati, n, f"{n}.raw.jsonl"))
                  and os.path.exists(os.path.join(dati, n, f"{n}.scores.jsonl")))


def raccogli(dati: str, eventi: Sequence[str], *, passo: int,
             cache: Optional[str] = None, verbose: bool = True) -> List[dict]:
    """Osservazioni per tutti gli eventi. Con `cache` si rilegge il file gia' scritto
    invece di riparsare 300 MB di raw: la misura resta identica, il tempo no."""
    if cache and os.path.exists(cache):
        with gzip.open(cache, "rt", encoding="utf-8") as fh:
            dati_cache = json.load(fh)
        if dati_cache.get("passo") == int(passo) and \
                dati_cache.get("eventi") == list(eventi):
            if verbose:
                print(f"  cache: {len(dati_cache['righe'])} osservazioni da {cache}",
                      flush=True)
            return dati_cache["righe"]
    minuti = list(range(1, 90, max(1, int(passo))))
    righe: List[dict] = []
    for ev in eventi:
        try:
            got = campiona_evento(os.path.join(dati, str(ev)), str(ev),
                                  minuti=minuti, commissione=COMMISSIONE)
        except Exception as exc:                       # pragma: no cover
            if verbose:
                print(f"  {ev}: SALTATO ({exc})", flush=True)
            continue
        righe.extend(got)
        if verbose:
            print(f"  {ev}: {len(got)} osservazioni", flush=True)
    if cache:
        os.makedirs(os.path.dirname(cache) or ".", exist_ok=True)
        with gzip.open(cache, "wt", encoding="utf-8") as fh:
            json.dump({"passo": int(passo), "eventi": list(eventi), "righe": righe}, fh)
    return righe


# ---------------------------------------------------------------------------
# esiti: veri, placebo calibrato, placebo permutato
# ---------------------------------------------------------------------------
def esito_vero(r: dict) -> Optional[int]:
    """Il `WINNER` del marketDefinition; il sidecar solo se il mercato non si e'
    mai visto risolto. Mai dedotto."""
    if r.get("esito_md") is not None:
        return int(r["esito_md"])
    return None if r.get("esito") is None else int(r["esito"])


def applica_placebo(righe: List[dict], modo: str, *, seme: int) -> List[dict]:
    """Ritorna una copia delle righe con `esito_placebo` al posto dell'esito vero."""
    rnd = random.Random(seme)
    fuori = [dict(r) for r in righe]
    if modo == "calibrato":
        # per ogni (evento, mercato, minuto) si estrae UN vincitore dalla
        # distribuzione devigata di quel minuto. Sotto questa ipotesi il mercato
        # e' calibrato per costruzione.
        gruppi: Dict[Tuple[str, str, int], List[int]] = defaultdict(list)
        for i, r in enumerate(fuori):
            gruppi[(r["event_id"], r["market_id"], r["minuto"])].append(i)
        for chiave, idx in gruppi.items():
            pesi = [(i, fuori[i].get("p_equa")) for i in idx]
            pesi = [(i, p) for i, p in pesi if p is not None and p > 0]
            for i in idx:
                fuori[i]["esito_placebo"] = None
            if not pesi:
                continue
            tot = sum(p for _, p in pesi)
            u = rnd.random() * max(tot, 1.0)     # resto = «vince una cella non quotata»
            acc = 0.0
            vinto = None
            for i, p in pesi:
                acc += p
                if u <= acc:
                    vinto = i
                    break
            for i, _p in pesi:
                fuori[i]["esito_placebo"] = 1 if i == vinto else 0
        return fuori
    if modo == "permutato":
        # i vincitori VERI si scambiano fra partite dello stesso tipo di mercato.
        vincitori: Dict[Tuple[str, str], Optional[int]] = {}
        for r in fuori:
            chiave = (r["event_id"], r["market_id"])
            if chiave not in vincitori:
                vincitori[chiave] = None
            if esito_vero(r) == 1:
                vincitori[chiave] = int(r["selection_id"])
        per_tipo: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for (ev, mk) in vincitori:
            tipo = next((r["mercato"] for r in fuori
                         if r["event_id"] == ev and r["market_id"] == mk), None)
            if tipo:
                per_tipo[tipo].append((ev, mk))
        rimescolato: Dict[Tuple[str, str], Optional[int]] = {}
        for tipo, chiavi in per_tipo.items():
            sorgenti = list(chiavi)
            rnd.shuffle(sorgenti)
            for dest, src in zip(chiavi, sorgenti):
                rimescolato[dest] = vincitori.get(src)
        for r in fuori:
            v = rimescolato.get((r["event_id"], r["market_id"]))
            r["esito_placebo"] = None if v is None else (1 if int(r["selection_id"]) == v else 0)
        return fuori
    raise ValueError(f"placebo sconosciuto: {modo!r}")


# ---------------------------------------------------------------------------
def aggrega(righe: List[dict], *, minuto_passo: int, giri_boot: int, seme: int,
            distanza_minima: int, n_min_uscite: int,
            campo_esito: str = "vero") -> dict:
    usabili = [r for r in righe
               if r.get("raggiungibile") and r.get("fascia")
               and (r.get("distanza_gol") is None
                    or r["distanza_gol"] >= int(distanza_minima))]

    def esito_di(r: dict) -> Optional[int]:
        if campo_esito == "vero":
            return esito_vero(r)
        v = r.get("esito_placebo")
        return None if v is None else int(v)

    gruppi: Dict[Tuple[str, str, str], List[dict]] = defaultdict(list)
    for r in usabili:
        gruppi[(r["mercato"], r["fascia"],
                fascia_minuto(r["minuto"], minuto_passo))].append(r)

    fuori: List[dict] = []
    for chiave in sorted(gruppi):
        g = gruppi[chiave]
        con_esito = [r for r in g if esito_di(r) is not None]
        if not con_esito:
            continue
        uscite = sum(esito_di(r) or 0 for r in con_esito)
        per_partita: Dict[str, Tuple[int, int]] = {}
        for r in con_esito:
            a, b = per_partita.get(r["event_id"], (0, 0))
            per_partita[r["event_id"]] = (a + (esito_di(r) or 0), b + 1)
        lo, hi = bootstrap_grappolo(per_partita, giri=giri_boot, seme=seme)
        p_reale = uscite / len(con_esito)
        equi = [r["p_equa"] for r in con_esito if r.get("p_equa")]
        p_equa_media = (sum(equi) / len(equi)) if equi else None
        riga: Dict[str, Any] = {
            "mercato": chiave[0], "fascia": chiave[1], "minuti": chiave[2],
            "n_celle": len(con_esito), "n_partite": len(per_partita),
            "uscite": uscite, "p_reale": round(p_reale, 6),
            "p_reale_boot_lo": round(lo, 6), "p_reale_boot_hi": round(hi, 6),
            "p_equa_media": None if p_equa_media is None else round(p_equa_media, 6),
            "n_con_devig": len(equi),
            "misurabile": bool(uscite >= int(n_min_uscite)),
            # IL BIAS AL NETTO DELLA GEOMETRIA DEL LIBRO. `k` al miglior back e'
            # > 1 anche su un mercato perfettamente calibrato, solo perche' quel
            # prezzo e' piu' basso del mid (lo dimostra il placebo calibrato).
            # Il bias vero e' `p_equa / p_reale`: la probabilita' DEVIGATA del
            # mercato contro la frequenza reale. E' il `k_equo` di K_MISURATO
            # §4, qui misurato IN GIOCO.
            "bias_equo": (round(p_equa_media / p_reale, 3)
                          if (p_equa_media and p_reale > 0) else None),
            "bias_equo_prudente": (round(p_equa_media / hi, 3)
                                   if (p_equa_media and hi > 0) else None),
        }
        for liv in LIVELLI:
            vals = [r.get(CAMPO_P[liv]) for r in con_esito]
            vals = [v for v in vals if v is not None]
            if not vals:
                riga[f"p_impl_{liv}"] = None
                riga[f"k_{liv}"] = riga[f"k_{liv}_prudente"] = None
                riga[f"k_{liv}_se_calibrato"] = None
                continue
            media = sum(vals) / len(vals)
            riga[f"p_impl_{liv}"] = round(media, 6)
            riga[f"n_{liv}"] = len(vals)
            riga[f"k_{liv}"] = round(media / p_reale, 3) if p_reale > 0 else None
            riga[f"k_{liv}_prudente"] = round(media / hi, 3) if hi > 0 else None
            riga[f"k_{liv}_se_calibrato"] = (round(media / p_equa_media, 3)
                                             if p_equa_media else None)
        fuori.append(riga)
    return {
        "generato_il": "2026-09-17",
        "misura": "M6 - k sul book IN GIOCO",
        "esito": ("WINNER del marketDefinition finale" if campo_esito == "vero"
                  else f"PLACEBO ({campo_esito})"),
        "commissione": COMMISSIONE,
        "minuto_passo": minuto_passo, "distanza_minima_gol": distanza_minima,
        "giri_bootstrap": giri_boot, "seme": seme,
        "n_osservazioni": len(righe), "n_usabili": len(usabili),
        "righe": fuori,
    }


def aggrega_placebo_ripetuto(righe: List[dict], modo: str, *, giri: int, seme: int,
                             minuto_passo: int, distanza_minima: int) -> dict:
    """Il placebo ripetuto `giri` volte e MEDIATO.

    Un solo sorteggio, nella coda, ha pochissime uscite e dice poco: la stima nulla
    si ottiene accumulando uscite e celle su piu' realizzazioni. Nessun bootstrap
    qui: del placebo interessa il PUNTO, non l'intervallo."""
    usabili = [r for r in righe
               if r.get("raggiungibile") and r.get("fascia")
               and (r.get("distanza_gol") is None
                    or r["distanza_gol"] >= int(distanza_minima))]
    acc: Dict[Tuple[str, str, str], Dict[str, float]] = defaultdict(
        lambda: {"celle": 0, "uscite": 0, "p_sum": defaultdict(float),
                 "p_n": defaultdict(int), "equa_sum": 0.0, "equa_n": 0})
    for giro in range(int(giri)):
        marcate = applica_placebo(usabili, modo, seme=seme + giro)
        for r in marcate:
            v = r.get("esito_placebo")
            if v is None:
                continue
            chiave = (r["mercato"], r["fascia"], fascia_minuto(r["minuto"], minuto_passo))
            a = acc[chiave]
            a["celle"] += 1
            a["uscite"] += int(v)
            if giro == 0:
                for liv in LIVELLI:
                    val = r.get(CAMPO_P[liv])
                    if val is not None:
                        a["p_sum"][liv] += float(val)
                        a["p_n"][liv] += 1
                if r.get("p_equa"):
                    a["equa_sum"] += float(r["p_equa"])
                    a["equa_n"] += 1
    fuori = []
    for chiave in sorted(acc):
        a = acc[chiave]
        if not a["celle"]:
            continue
        p_reale = a["uscite"] / a["celle"]
        riga: Dict[str, Any] = {
            "mercato": chiave[0], "fascia": chiave[1], "minuti": chiave[2],
            "celle_x_giri": a["celle"], "uscite_x_giri": a["uscite"],
            "p_reale": round(p_reale, 6),
            "p_equa_media": (round(a["equa_sum"] / a["equa_n"], 6)
                             if a["equa_n"] else None),
        }
        for liv in LIVELLI:
            if not a["p_n"][liv]:
                riga[f"k_{liv}"] = riga[f"k_{liv}_atteso"] = None
                continue
            media = a["p_sum"][liv] / a["p_n"][liv]
            riga[f"p_impl_{liv}"] = round(media, 6)
            riga[f"k_{liv}"] = round(media / p_reale, 3) if p_reale > 0 else None
            riga[f"k_{liv}_atteso"] = (round(media / (a["equa_sum"] / a["equa_n"]), 3)
                                       if a["equa_n"] else None)
        fuori.append(riga)
    return {"modo": modo, "giri": int(giri), "seme": seme, "righe": fuori}


def conta_discordanze(righe: List[dict]) -> Dict[str, int]:
    """Sidecar contro marketDefinition: quante volte non concordano."""
    confrontabili = [r for r in righe
                     if r.get("esito") is not None and r.get("esito_md") is not None]
    disc = [r for r in confrontabili if int(r["esito"]) != int(r["esito_md"])]
    return {"confrontabili": len(confrontabili), "discordanti": len(disc),
            "solo_sidecar": sum(1 for r in righe
                                if r.get("esito") is not None and r.get("esito_md") is None),
            "solo_market_definition": sum(1 for r in righe
                                          if r.get("esito_md") is not None
                                          and r.get("esito") is None)}


def stampa(dati: dict, *, solo_misurabili: bool = False) -> None:
    print("{:<16}{:<11}{:<9}{:>7}{:>7}{:>6}{:>9}".format(
        "mercato", "fascia", "minuti", "celle", "part.", "usc.", "p_reale")
        + "".join("{:>9}".format("k_" + l[:7]) for l in LIVELLI)
        + "".join("{:>10}".format("kpr_" + l[:6]) for l in LIVELLI)
        + "{:>10}{:>11}".format("bias_equo", "bias_prud"))
    for r in dati["righe"]:
        if solo_misurabili and not r["misurabile"]:
            continue
        base = "{:<16}{:<11}{:<9}{:>7}{:>7}{:>6}{:>9}".format(
            r["mercato"][:15], r["fascia"], r["minuti"], r["n_celle"],
            r["n_partite"], r["uscite"], f"{r['p_reale']:.4f}")
        ks = "".join("{:>9}".format(
            "-" if r.get(f"k_{l}") is None else f"{r[f'k_{l}']:.2f}") for l in LIVELLI)
        kp = "".join("{:>10}".format(
            "-" if r.get(f"k_{l}_prudente") is None else f"{r[f'k_{l}_prudente']:.2f}")
            for l in LIVELLI)
        be = "{:>10}{:>11}".format(
            "-" if r.get("bias_equo") is None else f"{r['bias_equo']:.2f}",
            "-" if r.get("bias_equo_prudente") is None else f"{r['bias_equo_prudente']:.2f}")
        print(base + ks + kp + be)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="M6 - k sul book in gioco")
    ap.add_argument("--dati", default="_live_raw")
    ap.add_argument("--eventi", nargs="*", default=None)
    ap.add_argument("--passo", type=int, default=1, help="passo del campionamento (minuti)")
    ap.add_argument("--minuto-passo", type=int, default=10, help="ampiezza della fascia di minuto")
    ap.add_argument("--distanza-minima", type=int, default=2)
    ap.add_argument("--n-min-uscite", type=int, default=N_MIN_USCITE)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seme", type=int, default=20260917)
    ap.add_argument("--placebo", default=None, choices=("calibrato", "permutato"))
    ap.add_argument("--placebo-giri", type=int, default=50,
                    help="ripetizioni del placebo: la stima nulla si media")
    ap.add_argument("--cache", default=os.path.join(
        "Betfair", "omega", "data", "campione_book_2026-09-17.json.gz"))
    ap.add_argument("--out", default=os.path.join(
        "Betfair", "omega", "data", "k_in_gioco_2026-09-17.json"))
    args = ap.parse_args(argv)

    eventi = args.eventi or eventi_disponibili(args.dati)
    righe = raccogli(args.dati, eventi, passo=args.passo, cache=args.cache)
    disc = conta_discordanze(righe)
    print(f"\nosservazioni: {len(righe)}  eventi: {len(eventi)}")
    print(f"esito sidecar vs marketDefinition: {disc['discordanti']} discordanti su "
          f"{disc['confrontabili']} confrontabili; solo sidecar {disc['solo_sidecar']}, "
          f"solo marketDefinition {disc['solo_market_definition']}\n")

    if args.placebo:
        dati = aggrega_placebo_ripetuto(
            righe, args.placebo, giri=args.placebo_giri, seme=args.seme,
            minuto_passo=args.minuto_passo, distanza_minima=args.distanza_minima)
        dati.update({"generato_il": "2026-09-17",
                     "misura": f"M6 - PLACEBO {args.placebo}",
                     "n_osservazioni": len(righe),
                     "eventi": [str(e) for e in eventi],
                     "discordanze_esito": disc})
        out = args.out.replace(".json", f"_placebo_{args.placebo}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"scritto {out}")
        print()
        print("{:<16}{:<11}{:<9}{:>12}{:>9}{:>9}".format(
            "mercato", "fascia", "minuti", "celle x giri", "p_reale", "k_back")
            + "{:>12}".format("k_back atteso"))
        for r in dati["righe"]:
            print("{:<16}{:<11}{:<9}{:>12}{:>9}{:>9}{:>12}".format(
                r["mercato"][:15], r["fascia"], r["minuti"], r["celle_x_giri"],
                f"{r['p_reale']:.4f}",
                "-" if r.get("k_best_back") is None else f"{r['k_best_back']:.2f}",
                "-" if r.get("k_best_back_atteso") is None else f"{r['k_best_back_atteso']:.2f}"))
        return 0
    dati = aggrega(righe, minuto_passo=args.minuto_passo, giri_boot=args.boot,
                   seme=args.seme, distanza_minima=args.distanza_minima,
                   n_min_uscite=args.n_min_uscite, campo_esito="vero")
    dati["eventi"] = [str(e) for e in eventi]
    dati["discordanze_esito"] = disc
    out = args.out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"scritto {out}\n")
    stampa(dati)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
