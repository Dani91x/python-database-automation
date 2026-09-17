# -*- coding: utf-8 -*-
"""misura_prezzo_appaiata — QUANTO VALE ENTRARE DENTRO LO SPREAD, sulle STESSE celle.

DOMANDA (progetto Omega V4, 17/09): `K_MISURATO_2026-09-16.md` mette a confronto
`k` al prezzo di lay (tabella a: <= 1 ovunque) e `k` alla probabilita' DEVIGATA
(tabella b: 1,53 sul CS 0,5-1 %) e ne deduce che «lo spread se lo mangia tutto».
Ma le due tabelle NON sono appaiate: i secchi della (b) sono ricostruiti sulla
p_equa, quindi contengono celle diverse da quelli della (a). Un confronto fra
due raggruppamenti diversi non misura il guadagno del prezzo: lo mescola con un
riclassamento.

Qui il confronto e' APPAIATO: stessi secchi (definiti UNA VOLTA sulla
p_implicita al prezzo di lay al tocco), stesse celle, stessi esiti; cambia solo
il PREZZO al quale si suppone di aver bancato:

  tocco      L = miglior availableToLay                (quello che Omega fa oggi)
  1tick      L = un tick sotto il tocco                (livello 'a' di M1)
  mid        L = mid fra best back e best lay, al tick (livello 'b' di M1)
  best_back  L = miglior availableToBack               (livello 'c' di M1)
  equo       p = mid devigato, normalizzato sul mercato (il tetto teorico)

Per ogni livello: `k = p_implicita(L) / p_reale` sul secchio, con bootstrap a
grappolo sulle PARTITE (una sola scoreline esce per mercato: le selezioni della
stessa partita non sono indipendenti).

LIMITE DICHIARATO, da leggere prima di usare il numero:
1. quote PRE-MATCH (`betfair_market_odds`): e' un prior del bias, non il bias live;
2. questa misura suppone il fill AL prezzo passivo. Il fill passivo NON e' certo e
   NON e' casuale: si ottiene piu' spesso quando il mercato viene verso di noi
   (selezione avversa). La quota di fill, l'attesa e la selezione avversa le
   misura `tools/misura_ingresso_passivo.py` sulle registrazioni (M1). I due
   numeri vanno moltiplicati, non sommati: questa e' la LEVA DI PREZZO, M1 e' la
   LEVA DI FILL.

Uso:
    python -m Betfair.omega.tools.misura_prezzo_appaiata
    python -m Betfair.omega.tools.misura_prezzo_appaiata --boot 2000 --commissione 0.05

Nessuna scrittura sul database: e' sola lettura. Scrive un JSON in
`Betfair/omega/data/`.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from typing import Any, Dict, List, Optional, Tuple

from Betfair.omega.tools.misura_k import (
    MERCATI, SECCHI, COMMISSIONE_DEFAULT, N_MIN_SECCHIO,
    _prezzo, p_implicita, esito_selezione, parse_scoreline,
    leggi_quote, leggi_esiti, _reale,
)
from Betfair.omega.omega_engine import _tick_bounds, round_to_tick

LIVELLI = ("tocco", "1tick", "mid", "best_back", "equo")


def tick_giu(prezzo: float, passi: int = 1) -> Optional[float]:
    """`passi` tick SOTTO `prezzo` sulla scala Betfair. None se si esce dalla scala."""
    p = float(prezzo)
    for _ in range(int(passi)):
        # `_tick_bounds` ha una tolleranza interna di 1e-9: per scendere DAVVERO
        # di un tick serve uno scostamento relativo piu' grande, altrimenti torna
        # lo stesso prezzo e il "tick sotto" non esiste (misurato: 75 -> 75).
        basso, _alto = _tick_bounds(p * (1.0 - 1e-6))
        if basso is None or basso >= p or basso <= 1.0:
            return None
        p = basso
    return p


def secchio_di(p_imp: float) -> Optional[str]:
    for lo, hi, etichetta in SECCHI:
        if lo < p_imp <= hi:
            return etichetta
    return None


def _boot(per_partita: Dict[Any, Tuple[int, int]], *, giri: int, seed: int
          ) -> Tuple[float, float]:
    """(2,5 %, 97,5 %) di p_reale ricampionando le PARTITE con reimmissione."""
    chiavi = list(per_partita)
    if not chiavi:
        return 0.0, 1.0
    rnd = random.Random(seed)
    campioni: List[float] = []
    for _ in range(int(giri)):
        u = d = 0
        for _ in range(len(chiavi)):
            k = chiavi[rnd.randrange(len(chiavi))]
            a, b = per_partita[k]
            u += a
            d += b
        if d:
            campioni.append(u / d)
    if not campioni:
        return 0.0, 1.0
    campioni.sort()
    return (campioni[int(0.025 * (len(campioni) - 1))],
            campioni[int(0.975 * (len(campioni) - 1))])


def prepara(quote: List[dict], esiti: Dict[int, dict], *, commissione: float
            ) -> List[dict]:
    """Una riga per selezione utile, con il prezzo di OGNI livello e l'esito vero.

    Il secchio e' calcolato UNA volta sola, sulla p_implicita al TOCCO: e' cio'
    che rende il confronto appaiato."""
    quotate: Dict[Tuple[str, int], set] = {}
    for r in quote:
        sc = parse_scoreline(r.get("selection") or "")
        if sc is not None:
            quotate.setdefault((r["market_name"], int(r["fixture_id"])), set()).add(sc)

    # somma dei pesi per mercato (per il devig): mid di back/lay, 1/L
    pesi: Dict[Tuple[str, int], float] = {}
    conta: Dict[Tuple[str, int], int] = {}
    for r in quote:
        b, l = _prezzo(r.get("back")), _prezzo(r.get("lay"))
        if b is None or l is None:
            continue
        chiave = (r["market_name"], int(r["fixture_id"]))
        mid = 2.0 / (1.0 / b + 1.0 / l)          # mid in PROBABILITA', non in quota
        pesi[chiave] = pesi.get(chiave, 0.0) + 1.0 / mid
        conta[chiave] = conta.get(chiave, 0) + 1

    fuori: List[dict] = []
    for r in quote:
        mercato = r["market_name"]
        periodo = MERCATI[mercato]
        fid = int(r["fixture_id"])
        riga_esito = esiti.get(fid)
        if not riga_esito:
            continue
        reale = _reale(riga_esito, periodo)
        if reale is None:
            continue
        b, l = _prezzo(r.get("back")), _prezzo(r.get("lay"))
        if b is None or l is None or b >= l:
            continue                 # senza i due lati non esiste uno spread
        uscita = esito_selezione(r.get("selection") or "", reale,
                                 quotate.get((mercato, fid)) or set())
        if uscita is None:
            continue
        p_tocco = p_implicita(l, commissione)
        if p_tocco is None:
            continue
        sec = secchio_di(p_tocco)
        if sec is None:
            continue
        un_tick = tick_giu(l, 1)
        mid_q = round_to_tick(2.0 / (1.0 / b + 1.0 / l))
        mid_q = min(max(mid_q, b), l)
        chiave = (mercato, fid)
        peso = pesi.get(chiave, 0.0)
        n_sel = conta.get(chiave, 0)
        p_equa = None
        if n_sel >= 6 and peso > 0.5:
            mid_prob = 2.0 / (1.0 / b + 1.0 / l)
            p_equa = (1.0 / mid_prob) / peso
        fuori.append({
            "mercato": mercato, "fixture_id": fid, "secchio": sec,
            "uscita": 1 if uscita else 0,
            "p": {
                "tocco": p_tocco,
                "1tick": p_implicita(un_tick, commissione) if un_tick else None,
                "mid": p_implicita(mid_q, commissione),
                "best_back": p_implicita(b, commissione),
                "equo": p_equa,
            },
            "prezzi": {"tocco": l, "1tick": un_tick, "mid": mid_q, "best_back": b},
        })
    return fuori


def misura(righe: List[dict], *, giri_boot: int, commissione: float) -> dict:
    gruppi: Dict[Tuple[str, str], List[dict]] = {}
    for r in righe:
        gruppi.setdefault((r["mercato"], r["secchio"]), []).append(r)

    fuori: List[dict] = []
    for (mercato, sec) in sorted(gruppi):
        g = gruppi[(mercato, sec)]
        n = len(g)
        uscite = sum(r["uscita"] for r in g)
        partite = {r["fixture_id"] for r in g}
        per_partita: Dict[int, Tuple[int, int]] = {}
        for r in g:
            a, b = per_partita.get(r["fixture_id"], (0, 0))
            per_partita[r["fixture_id"]] = (a + r["uscita"], b + 1)
        lo, hi = _boot(per_partita, giri=giri_boot, seed=20260917)
        p_reale = uscite / n if n else None
        riga: Dict[str, Any] = {
            "mercato": mercato, "secchio": sec, "n_selezioni": n,
            "n_partite": len(partite), "uscite": uscite,
            "p_reale": round(p_reale, 6) if p_reale is not None else None,
            "p_reale_boot_lo": round(lo, 6), "p_reale_boot_hi": round(hi, 6),
            "misurabile": bool(n >= N_MIN_SECCHIO and uscite > 0),
        }
        for liv in LIVELLI:
            valori = [r["p"][liv] for r in g if r["p"].get(liv) is not None]
            if not valori:
                riga[f"p_impl_{liv}"] = None
                riga[f"k_{liv}"] = None
                riga[f"k_{liv}_prudente"] = None
                continue
            p_med = sum(valori) / len(valori)
            riga[f"p_impl_{liv}"] = round(p_med, 6)
            riga[f"n_{liv}"] = len(valori)
            if p_reale and p_reale > 0:
                riga[f"k_{liv}"] = round(p_med / p_reale, 3)
                riga[f"k_{liv}_prudente"] = round(p_med / hi, 3) if hi > 0 else None
            else:
                riga[f"k_{liv}"] = None
                riga[f"k_{liv}_prudente"] = None
        # il GUADAGNO del prezzo: rapporto fra p_implicita del livello e del tocco,
        # sulle stesse celle. Non dipende da p_reale, quindi si misura sempre.
        base = riga.get("p_impl_tocco")
        for liv in LIVELLI:
            v = riga.get(f"p_impl_{liv}")
            riga[f"guadagno_{liv}"] = (round(v / base, 4)
                                       if (v and base and base > 0) else None)
        fuori.append(riga)
    return {
        "generato_il": "2026-09-17",
        "fonte": "betfair_market_odds (PRE-MATCH) x matches",
        "commissione": commissione,
        "secchi_definiti_su": "p_implicita al miglior availableToLay (tocco)",
        "livelli": list(LIVELLI),
        "n_selezioni": len(righe),
        "righe": fuori,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Guadagno APPAIATO del prezzo passivo su betfair_market_odds")
    ap.add_argument("--commissione", type=float, default=COMMISSIONE_DEFAULT)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--out", default=os.path.join(
        "Betfair", "omega", "data", "prezzo_appaiato_2026-09-17.json"))
    args = ap.parse_args(argv)

    sys.path.insert(0, os.getcwd())
    from db_client import get_supabase_client

    sb = get_supabase_client()
    print("lettura quote (Correct Score + Half Time Score)...", flush=True)
    quote = leggi_quote(sb)
    print(f"  righe quote: {len(quote)}", flush=True)
    esiti = leggi_esiti(sb, [int(r["fixture_id"]) for r in quote])
    print(f"  esiti trovati: {len(esiti)}", flush=True)

    righe = prepara(quote, esiti, commissione=args.commissione)
    print(f"  selezioni utili (con back E lay e esito): {len(righe)}", flush=True)
    dati = misura(righe, giri_boot=args.boot, commissione=args.commissione)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"scritto {args.out}\n")

    def _f(v: Optional[float], nd: int = 2) -> str:
        return "-" if v is None else f"{float(v):.{nd}f}"

    print("{:<16}{:<11}{:>7}{:>7}{:>6}{:>9}".format(
        "mercato", "secchio", "n", "part.", "usc.", "p_reale")
        + "".join("{:>10}".format("k_" + liv[:8]) for liv in LIVELLI)
        + "".join("{:>9}".format("g_" + liv[:7]) for liv in LIVELLI))
    for r in dati["righe"]:
        base = "{:<16}{:<11}{:>7}{:>7}{:>6}{:>9}".format(
            r["mercato"][:15], r["secchio"], r["n_selezioni"], r["n_partite"],
            r["uscite"], _f(r["p_reale"], 4))
        ks = "".join("{:>10}".format(_f(r.get(f"k_{liv}"))) for liv in LIVELLI)
        gs = "".join("{:>9}".format(_f(r.get(f"guadagno_{liv}"), 3)) for liv in LIVELLI)
        print(base + ks + gs)
    print("\nguadagno = p_implicita(livello) / p_implicita(tocco) sulle STESSE celle:")
    print("e' la LEVA DI PREZZO. La leva di FILL (quota di abbinamento, attesa,")
    print("selezione avversa) la misura tools/misura_ingresso_passivo.py (M1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
