# -*- coding: utf-8 -*-
"""banco_modelli — IL CONFRONTO FRA I MODELLI, sui nostri dati, fuori campione.

Ordine del coordinatore (16/09): il motore di V3 non e' «il Poisson residuo e basta».
Si costruiscono i candidati, si stimano i loro parametri sui NOSTRI dati e si
confrontano con **log-loss e Brier fuori campione**, per periodo (HT / FT) e per fascia
di minuto, con la calibrazione per decile stampata. Vince chi vince, non chi piace.

I candidati sono in `Betfair/omega/omega_v3.py` — lo stesso modulo che poi opera: cio'
che si certifica e' cio' che gira (PROCESSO_STANDARD_BOT §1).

DATI: `omega_minute_transitions` (`tools/estrai_transizioni.py`), 1,07 M righe costruite
dai gol con minuto di ~1,4 M partite: «dal punteggio S al bucket di minuto B, quante
volte si e' finiti a R» per il 90' (`ft`) e per il 45' (`ht`). E' la fonte piu' grande
che abbiamo sulla domanda esatta che V3 pone. **Ferma all'11/09/2026: dichiarato.**

PERCHE' QUESTI DATI SONO LA PROVA GIUSTA. I conteggi sono aggregati su tutte le partite
che sono passate da quello stato: la loro distribuzione e' quindi la MARGINALE sui
lambda, non la condizionale di una partita. Un modello che ignora l'eterogeneita' dei
lambda fra partite (Poisson puro) DEVE perdere qui, e perdere nel modo che conta per
Omega: sottostimando la coda. E' esattamente l'errore che si paga con la liability.

FUORI CAMPIONE, due split indipendenti:
  · `stati` — meta' degli stati (bucket, punteggio) a caso in addestramento, meta' in
    prova: prova la FORMA FUNZIONALE (il modello generalizza a stati mai visti?);
  · `leghe` — 30 leghe in addestramento, 30 in prova: prova la generalizzazione a
    campionati mai visti.

Uso:
    python -m Betfair.omega.tools.banco_modelli
    python -m Betfair.omega.tools.banco_modelli --split leghe --n-min 100
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import random
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.getcwd())

from Betfair.omega import omega_v3 as V3  # noqa: E402

SORGENTE = os.path.join("Betfair", "omega", "data", "transizioni_minuto_2026-09-16.json.gz")
DEST = os.path.join("Betfair", "omega", "data", "banco_modelli_2026-09-16.json")

# Stato = (target, bucket, punteggio); conteggi sui GOL RESIDUI
Stato = Tuple[str, int, Tuple[int, int]]


def _score(s: str) -> Optional[Tuple[int, int]]:
    try:
        h, a = str(s).split("-")
        return int(h), int(a)
    except (ValueError, AttributeError):
        return None


def costruisci_stati(righe: Sequence[dict]) -> Dict[Stato, Dict[Tuple[int, int], int]]:
    """Da righe `(bucket, score, target, result, n)` a conteggi di gol RESIDUI."""
    fuori: Dict[Stato, Dict[Tuple[int, int], int]] = {}
    for r in righe:
        sc = _score(r.get("score"))
        res = _score(r.get("result"))
        if sc is None or res is None:
            continue
        dh, da = res[0] - sc[0], res[1] - sc[1]
        if dh < 0 or da < 0:
            continue                      # un risultato non puo' togliere gol
        n = int(r.get("n") or 0)
        if n <= 0:
            continue
        chiave: Stato = (str(r["target"]), int(r["bucket"]), sc)
        cella = fuori.setdefault(chiave, {})
        cella[(dh, da)] = cella.get((dh, da), 0) + n
    return fuori


def somma_stati(a: Dict[Stato, Dict[Tuple[int, int], int]],
                b: Dict[Stato, Dict[Tuple[int, int], int]]) -> None:
    for k, cella in b.items():
        dest = a.setdefault(k, {})
        for c, n in cella.items():
            dest[c] = dest.get(c, 0) + n


def minuto_rappresentativo(bucket: int, target: str) -> float:
    """Il bucket e' un intervallo di 5': il minuto che lo rappresenta e' il suo
    centro. L'ultimo bucket e' aperto (85+ per il ft, 40+ per l'ht) e si accorcia."""
    b = int(bucket)
    if target == "ht":
        return b + 2.5 if b < 40 else 42.0
    return b + 2.5 if b < 85 else 86.5


# --------------------------------------------------------------------------
# I candidati: nome -> (parametri iniziali, chiavi libere, limiti)
# --------------------------------------------------------------------------
LIMITI = {
    "gol_totali": (1.2, 5.0),
    "quota_casa": (0.35, 0.70),
    "profilo_c1": (-2.0, 2.0),
    "profilo_c2": (-2.0, 2.0),
    "rho": (-0.6, 0.6),
    "beta_squilibrio": (-0.8, 0.8),
    "eta_gol_visti": (-0.5, 0.5),
    "lambda3": (0.0, 1.0),
    "forma_gamma": (0.3, 60.0),
    "cv_lambda": (0.0, 0.95),
}

CANDIDATI: Dict[str, Tuple[str, List[str], Dict[str, float]]] = {
    # nome -> (modello di omega_v3, parametri liberi, valori iniziali)
    "1_poisson": ("poisson", ["gol_totali", "quota_casa"],
                  {"gol_totali": 2.6, "quota_casa": 0.54}),
    "2_dixon_coles": ("dixon_coles", ["gol_totali", "quota_casa", "rho"],
                      {"gol_totali": 2.6, "quota_casa": 0.54, "rho": -0.13}),
    "3_dixon_robinson": ("dixon_robinson",
                         ["gol_totali", "quota_casa", "rho", "profilo_c1", "profilo_c2",
                          "beta_squilibrio", "eta_gol_visti"],
                         {"gol_totali": 2.6, "quota_casa": 0.54, "rho": -0.13,
                          "profilo_c1": 0.3, "profilo_c2": 0.0,
                          "beta_squilibrio": 0.05, "eta_gol_visti": 0.05}),
    "4_bivariato_KN": ("bivariato",
                       ["gol_totali", "quota_casa", "profilo_c1", "profilo_c2",
                        "beta_squilibrio", "eta_gol_visti", "lambda3"],
                       {"gol_totali": 2.6, "quota_casa": 0.54, "profilo_c1": 0.3,
                        "profilo_c2": 0.0, "beta_squilibrio": 0.05,
                        "eta_gol_visti": 0.05, "lambda3": 0.05}),
    "5_gamma_poisson": ("gamma_poisson",
                        ["gol_totali", "quota_casa", "rho", "profilo_c1", "profilo_c2",
                         "beta_squilibrio", "forma_gamma"],
                        {"gol_totali": 2.6, "quota_casa": 0.54, "rho": -0.13,
                         "profilo_c1": 0.3, "profilo_c2": 0.0,
                         "beta_squilibrio": 0.05, "forma_gamma": 6.0}),
    # il modello di PRODUZIONE di oggi (v2): Poisson-DC + mistura log-normale cv 0,30
    "0_v2_lognormale": ("dixon_coles",
                        ["gol_totali", "quota_casa", "rho", "cv_lambda"],
                        {"gol_totali": 2.6, "quota_casa": 0.54, "rho": -0.13,
                         "cv_lambda": 0.30}),
}


def parametri_da(modello: str, valori: Dict[str, float]) -> V3.Parametri:
    return V3.Parametri(modello=modello, **{k: float(v) for k, v in valori.items()})


# --------------------------------------------------------------------------
# Metriche
# --------------------------------------------------------------------------
def valuta(stati: Dict[Stato, Dict[Tuple[int, int], int]], p: V3.Parametri,
           *, solo_coda: float = 0.0) -> Dict[str, Any]:
    """log-loss multinomiale e Brier multiclasse, pesati sui conteggi.

    `solo_coda` > 0: si contano solo le celle che il modello mette sotto quella
    probabilita' — la parte del mondo dove Omega opera davvero."""
    ll = 0.0
    brier = 0.0
    n_tot = 0
    fuori_griglia = 0
    # calibrazione: (predetta) -> [somma p, uscite, n]
    decili: List[List[float]] = [[0.0, 0.0, 0.0] for _ in range(10)]
    for (target, bucket, sc), celle in stati.items():
        m = minuto_rappresentativo(bucket, target)
        griglia = V3.griglia_residua(minuto=m, punteggio=sc, periodo=target, p=p)
        if not griglia:
            continue
        n_stato = sum(celle.values())
        if n_stato <= 0:
            continue
        # somma dei quadrati: serve al Brier multiclasse
        if solo_coda > 0:
            chiavi = [c for c, v in griglia.items() if v <= solo_coda]
        else:
            chiavi = list(griglia.keys())
        somma_q = sum(griglia[c] ** 2 for c in chiavi)
        insieme = set(chiavi)
        for cella, n in celle.items():
            if cella not in griglia:
                fuori_griglia += n
                continue
            if solo_coda > 0 and cella not in insieme:
                continue
            pr = max(1e-12, griglia[cella])
            ll += -n * math.log(pr)
            brier += n * (somma_q - 2.0 * pr + 1.0)
            n_tot += n
        # calibrazione su TUTTE le celle dello stato (non solo le osservate)
        for cella in chiavi:
            pr = griglia[cella]
            idx = min(9, int(pr * 10))
            decili[idx][0] += pr * n_stato
            decili[idx][1] += celle.get(cella, 0)
            decili[idx][2] += n_stato
    if n_tot <= 0:
        return {"logloss": float("inf"), "brier": float("inf"), "n": 0}
    return {
        "logloss": ll / n_tot,
        "brier": brier / n_tot,
        "n": n_tot,
        "fuori_griglia": fuori_griglia,
        "calibrazione": [
            {"decile": i, "p_media": (d[0] / d[2] if d[2] else 0.0),
             "p_osservata": (d[1] / d[2] if d[2] else 0.0), "peso": d[2]}
            for i, d in enumerate(decili) if d[2] > 0],
    }


# Secchi della CODA, a risoluzione fine: il decile 0-10 % contiene tutta
# l'attivita' di Omega e non dice niente. Sono gli stessi tagli della misura di k.
SECCHI_CODA = ((0.0, 0.001, "<0,1%"), (0.001, 0.002, "0,1-0,2%"),
               (0.002, 0.005, "0,2-0,5%"), (0.005, 0.010, "0,5-1%"),
               (0.010, 0.020, "1-2%"), (0.020, 0.050, "2-5%"),
               (0.050, 0.100, "5-10%"))


def calibrazione_coda(stati: Dict[Stato, Dict[Tuple[int, int], int]], p: V3.Parametri
                      ) -> List[dict]:
    """Affidabilita' sulla CODA: per ogni secchio di probabilita' PREVISTA, la
    frequenza REALMENTE osservata. E' la tabella che dice se ci si puo' fidare
    del numero con cui si decide un lay a quota 80.

    Il peso di un secchio e' il numero di partite-stato che ci sono passate: se il
    modello dice 0,5 % su 100.000 stati, ci si aspettano ~500 uscite."""
    agg: Dict[str, List[float]] = {e: [0.0, 0.0, 0.0] for _, _, e in SECCHI_CODA}
    for (target, bucket, sc), celle in stati.items():
        m = minuto_rappresentativo(bucket, target)
        griglia = V3.griglia_residua(minuto=m, punteggio=sc, periodo=target, p=p)
        if not griglia:
            continue
        n_stato = sum(celle.values())
        for cella, pr in griglia.items():
            for lo, hi, etichetta in SECCHI_CODA:
                if lo < pr <= hi:
                    nodo = agg[etichetta]
                    nodo[0] += pr * n_stato          # uscite ATTESE
                    nodo[1] += celle.get(cella, 0)   # uscite VERE
                    nodo[2] += n_stato               # esposizione
                    break
    fuori = []
    for _, _, etichetta in SECCHI_CODA:
        att, vere, peso = agg[etichetta]
        if peso <= 0:
            continue
        p_prev = att / peso
        p_oss = vere / peso
        fuori.append({
            "secchio": etichetta, "esposizione": int(peso),
            "uscite_attese": round(att, 1), "uscite_vere": int(vere),
            "p_prevista": p_prev, "p_osservata": p_oss,
            # >1 = il modello SOVRASTIMA la coda (prudente per un layer);
            # <1 = la SOTTOSTIMA, ed e' l'errore che costa la liability
            "rapporto_prevista_su_vera": (p_prev / p_oss) if p_oss > 0 else None,
        })
    return fuori


def negll(stati: Dict[Stato, Dict[Tuple[int, int], int]], p: V3.Parametri) -> float:
    ll = 0.0
    n_tot = 0
    for (target, bucket, sc), celle in stati.items():
        m = minuto_rappresentativo(bucket, target)
        griglia = V3.griglia_residua(minuto=m, punteggio=sc, periodo=target, p=p)
        if not griglia:
            return 1e18
        for cella, n in celle.items():
            pr = griglia.get(cella)
            if pr is None:
                continue
            ll += -n * math.log(max(1e-12, pr))
            n_tot += n
    return ll / n_tot if n_tot else 1e18


def stima(stati: Dict[Stato, Dict[Tuple[int, int], int]], modello: str,
          liberi: List[str], iniziali: Dict[str, float], *, max_iter: int) -> Dict[str, float]:
    """MLE sui conteggi di addestramento (Nelder-Mead, limiti per riflessione)."""
    from scipy.optimize import minimize

    ordine = list(liberi)
    x0 = [float(iniziali[k]) for k in ordine]

    def clamp(x: Sequence[float]) -> Dict[str, float]:
        fuori = dict(iniziali)
        for k, v in zip(ordine, x):
            lo, hi = LIMITI[k]
            fuori[k] = min(hi, max(lo, float(v)))
        return fuori

    def obiettivo(x: Sequence[float]) -> float:
        val = clamp(x)
        try:
            return negll(stati, parametri_da(modello, val))
        except (ValueError, OverflowError):
            return 1e18

    res = minimize(obiettivo, x0, method="Nelder-Mead",
                   options={"maxiter": max_iter, "xatol": 1e-3, "fatol": 1e-5})
    return clamp(res.x)


# --------------------------------------------------------------------------
def dividi_stati(stati: Dict[Stato, Dict[Tuple[int, int], int]], *, seed: int = 20260916
                 ) -> Tuple[Dict[Stato, Dict], Dict[Stato, Dict]]:
    chiavi = sorted(stati.keys())
    rng = random.Random(seed)
    rng.shuffle(chiavi)
    meta = len(chiavi) // 2
    a = {k: stati[k] for k in chiavi[:meta]}
    b = {k: stati[k] for k in chiavi[meta:]}
    return a, b


def per_fascia_minuto(stati: Dict[Stato, Dict[Tuple[int, int], int]]
                      ) -> Dict[str, Dict[Stato, Dict]]:
    """Fasce di minuto che corrispondono alle finestre d'ingresso di V3."""
    fasce: Dict[str, Dict[Stato, Dict]] = {}
    for k, v in stati.items():
        target, bucket, _ = k
        if target == "ht":
            nome = "HT 0-19'" if bucket < 20 else ("HT 20-34'" if bucket < 35 else "HT 35-45'")
        else:
            nome = ("FT 0-44'" if bucket < 45 else
                    ("FT 45-64'" if bucket < 65 else "FT 65-90'"))
        fasce.setdefault(nome, {})[k] = v
    return fasce


def filtra(stati: Dict[Stato, Dict[Tuple[int, int], int]], *, n_min: int,
           target: Optional[str] = None) -> Dict[Stato, Dict]:
    return {k: v for k, v in stati.items()
            if sum(v.values()) >= n_min and (target is None or k[0] == target)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sorgente", default=SORGENTE)
    ap.add_argument("--out", default=DEST)
    ap.add_argument("--n-min", type=int, default=200,
                    help="stati con meno di questi casi: fuori (MIN_GLOBAL_N)")
    ap.add_argument("--max-iter", type=int, default=400)
    ap.add_argument("--split", choices=("stati", "leghe", "entrambi"), default="entrambi")
    args = ap.parse_args(argv)

    with gzip.open(args.sorgente, "rt", encoding="utf-8") as fh:
        grezzi = json.load(fh)
    globali = costruisci_stati(grezzi["globale"])
    print(f"stati globali: {len(globali)}  (con n >= {args.n_min}: "
          f"{len(filtra(globali, n_min=args.n_min))})", flush=True)

    split: Dict[str, Tuple[Dict, Dict]] = {}
    if args.split in ("stati", "entrambi"):
        tr, te = dividi_stati(filtra(globali, n_min=args.n_min))
        split["stati"] = (tr, te)
        print(f"split 'stati': {len(tr)} addestramento / {len(te)} prova", flush=True)
    if args.split in ("leghe", "entrambi"):
        leghe = sorted(grezzi.get("per_lega", {}).keys())
        rng = random.Random(20260916)
        rng.shuffle(leghe)
        meta = len(leghe) // 2
        a: Dict[Stato, Dict] = {}
        b: Dict[Stato, Dict] = {}
        for lid in leghe[:meta]:
            somma_stati(a, costruisci_stati(grezzi["per_lega"][lid]))
        for lid in leghe[meta:]:
            somma_stati(b, costruisci_stati(grezzi["per_lega"][lid]))
        split["leghe"] = (filtra(a, n_min=args.n_min), filtra(b, n_min=args.n_min))
        print(f"split 'leghe': {meta} leghe ({len(split['leghe'][0])} stati) / "
              f"{len(leghe) - meta} leghe ({len(split['leghe'][1])} stati)", flush=True)

    risultati: Dict[str, Any] = {"generato_il": "2026-09-16", "n_min": args.n_min,
                                 "split": {}}

    for nome_split, (tr, te) in split.items():
        print(f"\n===== SPLIT '{nome_split}' =====", flush=True)
        blocco: Dict[str, Any] = {"modelli": {}}
        for nome in sorted(CANDIDATI):
            modello, liberi, iniziali = CANDIDATI[nome]
            print(f"  fit {nome} ...", end="", flush=True)
            fit = stima(tr, modello, liberi, iniziali, max_iter=args.max_iter)
            p = parametri_da(modello, fit)
            dentro = valuta(tr, p)
            fuori = valuta(te, p)
            coda = valuta(te, p, solo_coda=0.02)
            per_periodo = {
                t: valuta(filtra(te, n_min=1, target=t), p) for t in ("ht", "ft")
            }
            per_fascia = {k: valuta(v, p) for k, v in per_fascia_minuto(te).items()}
            blocco["modelli"][nome] = {
                "modello_v3": modello,
                "parametri": {k: round(float(v), 5) for k, v in fit.items()},
                "dentro_campione": {"logloss": dentro["logloss"], "brier": dentro["brier"],
                                    "n": dentro["n"]},
                "fuori_campione": {"logloss": fuori["logloss"], "brier": fuori["brier"],
                                   "n": fuori["n"], "fuori_griglia": fuori.get("fuori_griglia")},
                "coda_p_sotto_2pct": {"logloss": coda["logloss"], "brier": coda["brier"],
                                      "n": coda["n"]},
                "per_periodo": {t: {"logloss": v["logloss"], "brier": v["brier"], "n": v["n"]}
                                for t, v in per_periodo.items()},
                "per_fascia_minuto": {k: {"logloss": v["logloss"], "brier": v["brier"],
                                          "n": v["n"]} for k, v in per_fascia.items()},
                "calibrazione_fuori_campione": fuori.get("calibrazione"),
            }
            print(f" logloss OOS {fuori['logloss']:.5f}  brier {fuori['brier']:.5f}"
                  f"  coda {coda['logloss']:.5f}", flush=True)
        risultati["split"][nome_split] = blocco

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(risultati, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"\nscritto {args.out}")

    for nome_split, blocco in risultati["split"].items():
        print(f"\n== {nome_split}: classifica fuori campione ==")
        print("{:<20}{:>11}{:>10}{:>11}{:>11}{:>11}".format(
            "modello", "logloss", "brier", "coda<2%", "HT", "FT"))
        ordinati = sorted(blocco["modelli"].items(),
                          key=lambda t: t[1]["fuori_campione"]["logloss"])
        for nome, d in ordinati:
            print("{:<20}{:>11.5f}{:>10.5f}{:>11.5f}{:>11.5f}{:>11.5f}".format(
                nome, d["fuori_campione"]["logloss"], d["fuori_campione"]["brier"],
                d["coda_p_sotto_2pct"]["logloss"],
                d["per_periodo"]["ht"]["logloss"], d["per_periodo"]["ft"]["logloss"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
