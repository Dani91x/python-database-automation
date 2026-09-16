# -*- coding: utf-8 -*-
"""banco_fusione — QUANTO PESA IL MODELLO E QUANTO PESA IL MERCATO (candidato 6).

Il book incorpora informazione che noi non abbiamo (formazioni, infortuni, soldi veri).
La domanda non e' «chi ha ragione», ma **con che peso combinarli**. La forma usata e' il
pool logaritmico in logit — `logit(p) = w*logit(modello) + (1-w)*logit(mercato)` — che e'
la combinazione giusta quando le fonti sono calibrate ma correlate (Satopaa, Baron,
Foster, Mellers, Tetlock & Ungar 2014, *International Journal of Forecasting* 30(2)
344-356; per la teoria del pool logaritmico, Genest & Zidek 1986, *Statistical Science*
1(1) 114-135).

`w` non si sceglie: si stima per FASCIA DI PROBABILITA' DI MERCATO, minimizzando la
log-loss su un insieme di addestramento e misurandola su uno di prova.

DATI: `betfair_market_odds` (quote PRE-MATCH complete: Match Odds + Correct Score +
Half Time Score) x l'esito vero di `matches`. I lambda del modello vengono dalle quote
1X2 con la STESSA funzione della produzione (`omega_model.lambdas_from_pre_ko`): niente
scorciatoie di laboratorio.

LIMITE DICHIARATO: pre-match. In gioco il mercato e' piu' sottile e il modello ha in
mano il punteggio: il peso live sara' diverso, e va rimisurato quando ci saranno
abbastanza book live registrati. Questa e' la misura che i dati di oggi permettono.

Uso:  python -m Betfair.omega.tools.banco_fusione
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.getcwd())

from Betfair.omega import omega_model as M   # noqa: E402  (produzione: lambdas_from_pre_ko)
from Betfair.omega import omega_v3 as V3     # noqa: E402
from Betfair.omega.tools import misura_k as K  # noqa: E402

DEST = os.path.join("Betfair", "omega", "data", "banco_fusione_2026-09-16.json")
# fasce di probabilita' di MERCATO su cui si stima un peso distinto
FASCE = ((0.01, "<=1%"), (0.02, "1-2%"), (0.05, "2-5%"), (0.10, "5-10%"), (1.01, ">10%"))


def fascia_di(p: float) -> str:
    for soglia, nome in FASCE:
        if float(p) <= soglia:
            return nome
    return FASCE[-1][1]


def _mid(back: Any, lay: Any) -> Optional[float]:
    b, l = K._prezzo(back), K._prezzo(lay)
    if b is None and l is None:
        return None
    if b is None or l is None:
        return 1.0 / float(b if b is not None else l)
    return 0.5 * (1.0 / float(b) + 1.0 / float(l))


def costruisci_casi(quote: List[dict], esiti: Dict[int, dict]) -> List[dict]:
    """Un caso per (fixture, mercato): probabilita' di mercato devigate, lambda dal
    1X2 e il risultato vero."""
    per_fixture: Dict[int, Dict[str, List[dict]]] = {}
    for r in quote:
        per_fixture.setdefault(int(r["fixture_id"]), {}).setdefault(r["market_name"], []).append(r)

    casi: List[dict] = []
    for fid, mercati in per_fixture.items():
        mo = mercati.get("Match Odds") or []
        if len(mo) < 3:
            continue
        # sort_priority Betfair: 1 = casa, 2 = trasferta, 3 = pareggio
        per_prio = {int(x.get("sort_priority") or 0): x for x in mo}
        try:
            casa = K._prezzo(per_prio[1].get("back"))
            via = K._prezzo(per_prio[2].get("back"))
            pari = K._prezzo(per_prio[3].get("back"))
        except KeyError:
            continue
        if not (casa and via and pari):
            continue
        lam = M.lambdas_from_pre_ko({"home": casa, "draw": pari, "away": via})
        if lam is None:
            continue
        riga_esito = esiti.get(fid)
        if not riga_esito:
            continue
        for nome_mercato, periodo in (("Correct Score", "ft"), ("Half Time Score", "ht")):
            righe = mercati.get(nome_mercato) or []
            if len(righe) < 6:
                continue
            reale = K._reale(riga_esito, periodo)
            if reale is None:
                continue
            pesi: List[Tuple[str, float]] = []
            for x in righe:
                w = _mid(x.get("back"), x.get("lay"))
                if w is not None and w > 0:
                    pesi.append((str(x["selection"]), w))
            tot = sum(w for _, w in pesi)
            if tot <= 0.5 or len(pesi) < 6:
                continue
            quotate = {sc for sc in (K.parse_scoreline(n) for n, _ in pesi) if sc is not None}
            selezioni = []
            for nome, w in pesi:
                uscita = K.esito_selezione(nome, reale, quotate)
                if uscita is None:
                    continue
                selezioni.append({"nome": nome, "p_mercato": w / tot, "uscita": bool(uscita)})
            if not selezioni:
                continue
            casi.append({"fixture_id": fid, "periodo": periodo, "lambdas": list(lam),
                         "selezioni": selezioni,
                         "nomi": [s["nome"] for s in selezioni],
                         "run_date": righe[0].get("run_date")})
    return casi


def p_modello(caso: dict, p: V3.Parametri) -> Dict[str, float]:
    return V3.probabilita_selezioni(periodo=caso["periodo"], minuto=0.0, punteggio=(0, 0),
                                    nomi=caso["nomi"], p=p,
                                    lambdas=(caso["lambdas"][0], caso["lambdas"][1]))


def metriche(casi: Sequence[dict], p: V3.Parametri, pesi: Dict[str, float]
             ) -> Dict[str, Any]:
    """log-loss e Brier BINARI per selezione (ogni selezione e' un si'/no), con
    la fusione al peso indicato per fascia. Riporta anche modello e mercato puri."""
    somme = {"fusa": [0.0, 0.0], "modello": [0.0, 0.0], "mercato": [0.0, 0.0]}
    n = 0
    per_fascia: Dict[str, Dict[str, Any]] = {}
    calib: List[List[float]] = [[0.0, 0.0, 0.0] for _ in range(20)]
    for caso in casi:
        pm = p_modello(caso, p)
        if not pm:
            continue
        for s in caso["selezioni"]:
            nome = s["nome"]
            p_mod = pm.get(nome)
            if p_mod is None:
                continue
            p_mkt = float(s["p_mercato"])
            f = fascia_di(p_mkt)
            w = max(0.0, min(1.0, float(pesi.get(f, 1.0))))
            p_fus = V3._inv_logit(w * V3._logit(p_mod) + (1.0 - w) * V3._logit(p_mkt))
            y = 1.0 if s["uscita"] else 0.0
            for chiave, pr in (("fusa", p_fus), ("modello", p_mod), ("mercato", p_mkt)):
                q = min(1.0 - 1e-9, max(1e-9, pr))
                somme[chiave][0] += -(y * math.log(q) + (1 - y) * math.log(1 - q))
                somme[chiave][1] += (q - y) ** 2
            n += 1
            nodo = per_fascia.setdefault(f, {"n": 0, "ll_fusa": 0.0, "ll_mod": 0.0,
                                             "ll_mkt": 0.0, "uscite": 0,
                                             "somma_mkt": 0.0, "somma_mod": 0.0})
            nodo["n"] += 1
            nodo["uscite"] += int(y)
            nodo["somma_mkt"] += p_mkt
            nodo["somma_mod"] += p_mod
            for chiave, pr in (("ll_fusa", p_fus), ("ll_mod", p_mod), ("ll_mkt", p_mkt)):
                q = min(1.0 - 1e-9, max(1e-9, pr))
                nodo[chiave] += -(y * math.log(q) + (1 - y) * math.log(1 - q))
            idx = min(19, int(p_fus * 20))
            calib[idx][0] += p_fus
            calib[idx][1] += y
            calib[idx][2] += 1
    if n == 0:
        return {"n": 0}
    fuori = {"n": n}
    for chiave, (ll, br) in somme.items():
        fuori[chiave] = {"logloss": ll / n, "brier": br / n}
    fuori["per_fascia"] = {
        k: {"n": v["n"], "uscite": v["uscite"],
            "p_mercato_media": v["somma_mkt"] / v["n"],
            "p_modello_media": v["somma_mod"] / v["n"],
            "p_reale": v["uscite"] / v["n"],
            "logloss_fusa": v["ll_fusa"] / v["n"],
            "logloss_modello": v["ll_mod"] / v["n"],
            "logloss_mercato": v["ll_mkt"] / v["n"]}
        for k, v in sorted(per_fascia.items())}
    fuori["calibrazione"] = [
        {"bin": i, "p_media": c[0] / c[2], "p_osservata": c[1] / c[2], "n": int(c[2])}
        for i, c in enumerate(calib) if c[2] >= 30]
    return fuori


def stima_pesi(casi: Sequence[dict], p: V3.Parametri) -> Dict[str, float]:
    """Peso del modello per fascia, a griglia fine: ogni fascia e' indipendente
    dalle altre nella log-loss, quindi si ottimizza una fascia per volta."""
    griglia = [i / 20.0 for i in range(21)]
    pesi = {nome: 1.0 for _, nome in FASCE}
    # precalcolo: (fascia, p_mod, p_mkt, y)
    punti: Dict[str, List[Tuple[float, float, float]]] = {}
    for caso in casi:
        pm = p_modello(caso, p)
        if not pm:
            continue
        for s in caso["selezioni"]:
            p_mod = pm.get(s["nome"])
            if p_mod is None:
                continue
            p_mkt = float(s["p_mercato"])
            punti.setdefault(fascia_di(p_mkt), []).append(
                (float(p_mod), p_mkt, 1.0 if s["uscita"] else 0.0))
    for fascia, dati in punti.items():
        migliore, best_ll = 1.0, float("inf")
        for w in griglia:
            ll = 0.0
            for p_mod, p_mkt, y in dati:
                q = V3._inv_logit(w * V3._logit(p_mod) + (1.0 - w) * V3._logit(p_mkt))
                q = min(1.0 - 1e-9, max(1e-9, q))
                ll += -(y * math.log(q) + (1 - y) * math.log(1 - q))
            if ll < best_ll:
                best_ll, migliore = ll, w
        pesi[fascia] = migliore
    return pesi


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEST)
    ap.add_argument("--parametri", default="",
                    help="JSON con i parametri vincenti del banco modelli")
    args = ap.parse_args(argv)

    from db_client import get_supabase_client
    sb = get_supabase_client()
    print("lettura quote...", flush=True)
    quote = K.leggi_quote(sb)
    # servono anche i Match Odds per i lambda
    off = 0
    mo: List[dict] = []
    while True:
        d = (sb.table("betfair_market_odds")
             .select("fixture_id,market_name,selection,back,lay,sort_priority,run_date")
             .eq("market_name", "Match Odds").order("fixture_id")
             .range(off, off + 999).execute().data)
        if not d:
            break
        mo.extend(d)
        if len(d) < 1000:
            break
        off += 1000
    print(f"  CS+HTS {len(quote)}  Match Odds {len(mo)}", flush=True)
    esiti = K.leggi_esiti(sb, [int(r["fixture_id"]) for r in quote])
    casi = costruisci_casi(quote + mo, esiti)
    print(f"  casi (fixture x mercato): {len(casi)}", flush=True)

    # split temporale: le date piu' vecchie addestrano, le piu' recenti provano
    casi.sort(key=lambda c: str(c.get("run_date") or ""))
    taglio = int(len(casi) * 0.6)
    tr, te = casi[:taglio], casi[taglio:]
    print(f"  addestramento {len(tr)} (fino a {tr[-1]['run_date'] if tr else '-'}) / "
          f"prova {len(te)} (da {te[0]['run_date'] if te else '-'})", flush=True)

    valori = {}
    if args.parametri and os.path.exists(args.parametri):
        with open(args.parametri, "r", encoding="utf-8") as fh:
            valori = json.load(fh)
    p = V3.Parametri(**valori) if valori else V3.Parametri(modello="dixon_coles")
    print(f"  modello di base: {p.modello}", flush=True)

    pesi = stima_pesi(tr, p)
    print("  pesi stimati (peso del MODELLO):", pesi, flush=True)
    senza = {nome: 1.0 for _, nome in FASCE}
    solo_mkt = {nome: 0.0 for _, nome in FASCE}
    risultato = {
        "generato_il": "2026-09-16",
        "fonte": "betfair_market_odds (PRE-MATCH) x matches",
        "modello_base": p.modello,
        "parametri_modello": {k: getattr(p, k) for k in
                              ("gol_totali", "quota_casa", "rho", "profilo_c1",
                               "profilo_c2", "beta_squilibrio", "forma_gamma", "cv_lambda")},
        "pesi_stimati": pesi,
        "prova_fusa": metriche(te, p, pesi),
        "prova_solo_modello": metriche(te, p, senza),
        "prova_solo_mercato": metriche(te, p, solo_mkt),
        "addestramento_fusa": metriche(tr, p, pesi),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(risultato, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"scritto {args.out}")

    pr = risultato["prova_fusa"]
    print("\n-- fuori campione (n = {}) --".format(pr["n"]))
    for chiave in ("modello", "mercato", "fusa"):
        print(f"  {chiave:<9} logloss {pr[chiave]['logloss']:.5f}  brier {pr[chiave]['brier']:.6f}")
    print("\n-- per fascia di p_mercato --")
    print("{:<8}{:>8}{:>10}{:>10}{:>10}{:>11}{:>11}{:>11}".format(
        "fascia", "n", "p_mkt", "p_mod", "p_reale", "ll_mkt", "ll_mod", "ll_fusa"))
    for f, v in pr["per_fascia"].items():
        print("{:<8}{:>8}{:>10.4f}{:>10.4f}{:>10.4f}{:>11.5f}{:>11.5f}{:>11.5f}".format(
            f, v["n"], v["p_mercato_media"], v["p_modello_media"], v["p_reale"],
            v["logloss_mercato"], v["logloss_modello"], v["logloss_fusa"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
