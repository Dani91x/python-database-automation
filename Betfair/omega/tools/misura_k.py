# -*- coding: utf-8 -*-
"""misura_k — FAVOURITE-LONGSHOT BIAS MISURATO SUL NOSTRO BOOK (Omega V3, Fase K).

DOMANDA: quando Betfair offre un LAY a quota L su una scoreline (Correct Score o
Half Time Score), quante volte quella scoreline esce DAVVERO rispetto a quante
volte il prezzo dice che dovrebbe uscire?

Il numero che serve al motore e' ``k``:

    p_implicita = (1 - c) / (L - c)        # break-even del lay, commissione c
    k           = p_implicita / p_reale

``k > 1`` significa che il prezzo di lay sovrastima la probabilita' della coda:
e' il *favourite-longshot bias* (Thaler & Ziemba 1988; Cain-Law-Peel 2000 sul
calcio), e in un lay e' esattamente il margine che ci si porta a casa. Il
progetto (PROGETTO_OMEGA_V3 §3.3) impone un cancello ``P_nostra <= p_implicita/k``:
qui ``k`` viene MISURATO per secchi di ``p_implicita``, non deciso a tavolino.

FONTE: ``betfair_market_odds`` (quote Betfair PRE-MATCH complete, back+lay,
popolata da ``betfair_full_odds.py``) incrociata con l'esito vero di ``matches``
(``goals_home/away`` per il Correct Score, ``halftime_home/away`` per l'Half Time
Score). Un incrocio 1:1 su ``fixture_id``, gia' garantito dal matching di
``Betfair/betfair_match.py``.

LIMITE DICHIARATO, da leggere prima di usare il numero: queste quote sono
PRE-MATCH. Omega V3 entra al 25'-40' e al 55'-85', su un book LIVE condizionato
al punteggio. Il bias misurato qui e' quello della coda pre-match sullo stesso
mercato e sullo stesso book; non e' il bias live. Vale come *prior* del margine,
e come unica misura diretta disponibile finche' non esiste una serie di book
live registrati abbastanza lunga (v. §4.4 del progetto).

INTERVALLI: le selezioni della stessa partita NON sono indipendenti (esattamente
una scoreline esce per mercato). Un intervallo binomiale su n selezioni sarebbe
falsamente stretto. Qui l'intervallo e' un BOOTSTRAP A GRAPPOLO sulle partite
(si ricampionano le partite, non le righe): e' il conto onesto.

Uso:
    python -m Betfair.omega.tools.misura_k
    python -m Betfair.omega.tools.misura_k --commissione 0.05 --boot 2000

Scrive ``Betfair/omega/data/k_misurato_2026-09-16.json`` (dati versionati) e
stampa la tabella. Nessuna scrittura sul database: e' sola lettura.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

MERCATI = {"Correct Score": "ft", "Half Time Score": "ht"}
COMMISSIONE_DEFAULT = 0.05
# Secchi di p_implicita (estremo superiore incluso). Sotto lo 0,2 % il campione
# storico non puo' dire nulla (§4.4: servono migliaia di casi), sopra il 10 % non
# e' piu' coda e Omega non ci opera.
SECCHI: Tuple[Tuple[float, float, str], ...] = (
    (0.0000, 0.0020, "0-0,2%"),
    (0.0020, 0.0050, "0,2-0,5%"),
    (0.0050, 0.0100, "0,5-1%"),
    (0.0100, 0.0200, "1-2%"),
    (0.0200, 0.0500, "2-5%"),
    (0.0500, 0.1000, "5-10%"),
    (0.1000, 1.0001, ">10%"),
)
K_PRUDENTE = 2.0          # §3.3: k di default quando il secchio non e' misurabile
N_MIN_SECCHIO = 200       # sotto: "non lo so", non "k = 1"
SCORELINE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
ANY_RE = re.compile(r"any\s*(other|unquoted)", re.IGNORECASE)
HOME_RE = re.compile(r"home", re.IGNORECASE)
AWAY_RE = re.compile(r"away", re.IGNORECASE)
DRAW_RE = re.compile(r"draw", re.IGNORECASE)


def parse_scoreline(nome: str) -> Optional[Tuple[int, int]]:
    m = SCORELINE_RE.match(nome or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _prezzo(livelli: Any) -> Optional[float]:
    """Miglior prezzo dal blocco JSONB [{price,size}, ...]; None se assente."""
    if not isinstance(livelli, list) or not livelli:
        return None
    try:
        p = float(livelli[0].get("price"))
    except (TypeError, ValueError, AttributeError):
        return None
    return p if math.isfinite(p) and p > 1.0 else None


def p_implicita(prezzo_lay: float, commissione: float) -> Optional[float]:
    """Break-even del LAY a ``prezzo_lay``: (1-c)/(L-c). E' la STESSA formula del
    motore (``omega_model.select_by_model``), non una sua approssimazione."""
    c = max(0.0, min(0.5, float(commissione)))
    den = float(prezzo_lay) - c
    if den <= 0:
        return None
    p = (1.0 - c) / den
    return p if 0.0 < p <= 1.0 else None


def esito_selezione(nome: str, reale: Tuple[int, int], quotate: set) -> Optional[bool]:
    """La selezione si e' verificata? None = non interpretabile (va scartata,
    mai contata come "non uscita": gonfierebbe k dalla parte sbagliata)."""
    sc = parse_scoreline(nome)
    if sc is not None:
        return sc == reale
    if not ANY_RE.search(nome or ""):
        return None
    rh, ra = reale
    fuori = (rh, ra) not in quotate
    if DRAW_RE.search(nome):
        return fuori and rh == ra
    if HOME_RE.search(nome):
        return fuori and rh > ra
    if AWAY_RE.search(nome):
        return fuori and ra > rh
    # "Any Unquoted" senza direzione (tipico dell'Half Time Score)
    return fuori


def wilson(k: float, n: float, z: float = 1.96) -> Tuple[float, float]:
    """Intervallo di Wilson two-sided (riferimento, NON quello che si usa: la
    correlazione fra selezioni della stessa partita lo rende troppo stretto)."""
    n = float(n)
    if n <= 0:
        return 0.0, 1.0
    p = float(k) / n
    z2 = z * z
    centro = (p + z2 / (2 * n)) / (1 + z2 / n)
    semi = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, centro - semi), min(1.0, centro + semi)


def bootstrap_grappolo(per_partita: Dict[Any, Tuple[int, int]], *, giri: int,
                       seed: int = 20260916) -> Tuple[float, float]:
    """(p_reale al 2,5 %, al 97,5 %) ricampionando le PARTITE con reimmissione.

    ``per_partita``: fixture_id -> (uscite, righe). Ricampionare le partite tiene
    conto del fatto che in un mercato a risultato esatto esce una sola scoreline:
    le righe della stessa partita sono legate fra loro."""
    chiavi = list(per_partita.keys())
    if not chiavi:
        return 0.0, 1.0
    rng = random.Random(seed)
    m = len(chiavi)
    coppie = [per_partita[c] for c in chiavi]
    campioni: List[float] = []
    for _ in range(max(1, int(giri))):
        u = 0
        d = 0
        for _ in range(m):
            a, b = coppie[rng.randrange(m)]
            u += a
            d += b
        if d > 0:
            campioni.append(u / d)
    if not campioni:
        return 0.0, 1.0
    campioni.sort()
    lo = campioni[int(0.025 * (len(campioni) - 1))]
    hi = campioni[int(0.975 * (len(campioni) - 1))]
    return lo, hi


# ---------------------------------------------------------------------------
# Lettura dati (sola lettura, a pagine: il database respira — §18)
# ---------------------------------------------------------------------------
def leggi_quote(sb, pagina: int = 1000) -> List[dict]:
    fuori: List[dict] = []
    for mercato in MERCATI:
        off = 0
        while True:
            d = (sb.table("betfair_market_odds")
                 .select("fixture_id,market_name,selection,back,lay,run_date")
                 .eq("market_name", mercato)
                 .order("fixture_id").order("selection")
                 .range(off, off + pagina - 1).execute().data)
            if not d:
                break
            fuori.extend(d)
            if len(d) < pagina:
                break
            off += pagina
    return fuori


def leggi_esiti(sb, fixture_ids: List[int], blocco: int = 300) -> Dict[int, dict]:
    fuori: Dict[int, dict] = {}
    ids = sorted(set(int(x) for x in fixture_ids))
    for i in range(0, len(ids), blocco):
        chunk = ids[i:i + blocco]
        d = (sb.table("matches")
             .select("fixture_id,status_short,goals_home,goals_away,"
                     "halftime_home,halftime_away,league_id")
             .in_("fixture_id", chunk).execute().data)
        for r in d or ():
            fuori[int(r["fixture_id"])] = r
    return fuori


def _reale(riga: dict, periodo: str) -> Optional[Tuple[int, int]]:
    if str(riga.get("status_short") or "").upper() not in ("FT", "AET", "PEN"):
        return None
    if periodo == "ht":
        h, a = riga.get("halftime_home"), riga.get("halftime_away")
    else:
        h, a = riga.get("goals_home"), riga.get("goals_away")
    if h is None or a is None:
        return None
    try:
        return int(h), int(a)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
def misura(quote: List[dict], esiti: Dict[int, dict], *, commissione: float,
           giri_boot: int) -> dict:
    """Tabella di k per (mercato, secchio). Ritorna il dizionario versionabile."""
    # (mercato, fixture) -> scoreline quotate, per decidere gli aggregati
    quotate: Dict[Tuple[str, int], set] = {}
    for r in quote:
        sc = parse_scoreline(r.get("selection") or "")
        if sc is not None:
            quotate.setdefault((r["market_name"], int(r["fixture_id"])), set()).add(sc)

    agg: Dict[Tuple[str, str], dict] = {}
    scartate = {"no_lay": 0, "no_esito": 0, "nome_ignoto": 0, "p_fuori": 0}
    partite_viste: Dict[str, set] = {"ft": set(), "ht": set()}
    etichette = [s[2] for s in SECCHI]

    for r in quote:
        mercato = r["market_name"]
        periodo = MERCATI[mercato]
        fid = int(r["fixture_id"])
        riga_esito = esiti.get(fid)
        reale = _reale(riga_esito, periodo) if riga_esito else None
        if reale is None:
            scartate["no_esito"] += 1
            continue
        prezzo = _prezzo(r.get("lay"))
        if prezzo is None:
            scartate["no_lay"] += 1
            continue
        p_imp = p_implicita(prezzo, commissione)
        if p_imp is None:
            scartate["p_fuori"] += 1
            continue
        uscita = esito_selezione(r.get("selection") or "", reale,
                                 quotate.get((mercato, fid), set()))
        if uscita is None:
            scartate["nome_ignoto"] += 1
            continue
        partite_viste[periodo].add(fid)
        for lo, hi, etichetta in SECCHI:
            if lo < p_imp <= hi:
                nodo = agg.setdefault((mercato, etichetta), {
                    "per_partita": {}, "somma_p": 0.0, "n": 0, "uscite": 0,
                    "prezzo_min": prezzo, "prezzo_max": prezzo,
                })
                cella = nodo["per_partita"].setdefault(fid, [0, 0])
                cella[0] += 1 if uscita else 0
                cella[1] += 1
                nodo["somma_p"] += p_imp
                nodo["n"] += 1
                nodo["uscite"] += 1 if uscita else 0
                nodo["prezzo_min"] = min(nodo["prezzo_min"], prezzo)
                nodo["prezzo_max"] = max(nodo["prezzo_max"], prezzo)
                break

    righe: List[dict] = []
    for chiave in sorted(agg, key=lambda t: (t[0], etichette.index(t[1]))):
        mercato, etichetta = chiave
        nodo = agg[chiave]
        n = nodo["n"]
        uscite = nodo["uscite"]
        p_media = nodo["somma_p"] / n if n else 0.0
        p_reale = uscite / n if n else 0.0
        per_partita = {k: (v[0], v[1]) for k, v in nodo["per_partita"].items()}
        lo_b, hi_b = bootstrap_grappolo(per_partita, giri=giri_boot)
        w_lo, w_hi = wilson(uscite, n)

        def _k(p: float) -> Optional[float]:
            return (p_media / p) if p > 0 else None

        misurabile = n >= N_MIN_SECCHIO
        k_centro = _k(p_reale)
        k_prudente = _k(hi_b)                     # p_reale ALTO -> k BASSO
        k_ottimista = _k(lo_b) if lo_b > 0 else None
        operabile = bool(misurabile and k_prudente is not None and k_prudente > 1.0)
        righe.append({
            "mercato": mercato,
            "periodo": MERCATI[mercato],
            "secchio": etichetta,
            "n_selezioni": n,
            "n_partite": len(per_partita),
            "uscite": uscite,
            "p_implicita_media": round(p_media, 6),
            "prezzo_lay_min": nodo["prezzo_min"],
            "prezzo_lay_max": nodo["prezzo_max"],
            "p_reale": round(p_reale, 6),
            "p_reale_boot_lo": round(lo_b, 6),
            "p_reale_boot_hi": round(hi_b, 6),
            "p_reale_wilson_lo": round(w_lo, 6),
            "p_reale_wilson_hi": round(w_hi, 6),
            "k_centro": None if k_centro is None else round(k_centro, 3),
            "k_prudente": None if k_prudente is None else round(k_prudente, 3),
            "k_ottimista": None if k_ottimista is None else round(k_ottimista, 3),
            "misurabile": bool(misurabile),
            "operabile": operabile,
            # LA REGOLA DEL PROGETTO (§3.3): la soglia usata dal motore non
            # scende MAI sotto K_PRUDENTE, anche dove il bias misurato e' enorme.
            "k_soglia": round(max(K_PRUDENTE, float(k_prudente or 0.0)), 3) if operabile
                        else K_PRUDENTE,
            "motivo_soglia": ("misurato" if operabile else
                              ("campione_insufficiente" if not misurabile
                               else "bias_non_dimostrato")),
        })

    return {
        "generato_il": "2026-09-16",
        "fonte": "betfair_market_odds x matches (quote PRE-MATCH, fino all'11/09/2026)",
        "commissione": commissione,
        "k_prudente_default": K_PRUDENTE,
        "n_min_secchio": N_MIN_SECCHIO,
        "giri_bootstrap": giri_boot,
        "partite_ft": len(partite_viste["ft"]),
        "partite_ht": len(partite_viste["ht"]),
        "scartate": scartate,
        "secchi": etichette,
        "righe": righe,
    }


def misura_equa(quote: List[dict], esiti: Dict[int, dict], *, giri_boot: int) -> dict:
    """SECONDA MISURA: la FORMA del bias, separata dal COSTO dello spread.

    ``misura()`` confronta l'esito con la ``p_implicita`` del prezzo di LAY: e' il
    numero operativo (e' li' che si opererebbe), ma contiene anche lo spread —
    la somma delle 1/quota_lay di un mercato sta sotto 1, quindi OGNI selezione
    ha una p_implicita di lay piu' bassa del vero solo per come e' fatto il book.

    Qui invece la probabilita' di mercato e' DEVIGATA: mid di back/lay per
    selezione, normalizzato a 1 sul mercato. Se ``k_equo > 1`` nella coda, il
    favourite-longshot bias esiste ma se lo mangia lo spread (e la strada e'
    entrare con ordini passivi); se ``k_equo ~ 1``, il mercato e' calibrato e
    non c'e' nessun bias da raccogliere: l'unico edge possibile e' il modello.
    """
    per_mercato: Dict[Tuple[str, int], List[dict]] = {}
    for r in quote:
        per_mercato.setdefault((r["market_name"], int(r["fixture_id"])), []).append(r)

    etichette = [s[2] for s in SECCHI]
    agg: Dict[Tuple[str, str], dict] = {}
    for (mercato, fid), righe in per_mercato.items():
        periodo = MERCATI[mercato]
        riga_esito = esiti.get(fid)
        reale = _reale(riga_esito, periodo) if riga_esito else None
        if reale is None:
            continue
        quotate = {sc for sc in (parse_scoreline(x.get("selection") or "") for x in righe)
                   if sc is not None}
        pesi: List[Tuple[dict, float]] = []
        for x in righe:
            b, l = _prezzo(x.get("back")), _prezzo(x.get("lay"))
            if b is None and l is None:
                continue
            if b is None or l is None:
                w = 1.0 / float(b if b is not None else l)
            else:
                w = 0.5 * (1.0 / float(b) + 1.0 / float(l))
            pesi.append((x, w))
        tot = sum(w for _, w in pesi)
        # un mercato mezzo vuoto non si devigano: normalizzare su meta' book
        # produrrebbe probabilita' inventate
        if tot <= 0.5 or len(pesi) < 6:
            continue
        for x, w in pesi:
            p_eq = w / tot
            uscita = esito_selezione(x.get("selection") or "", reale, quotate)
            if uscita is None:
                continue
            for lo, hi, etichetta in SECCHI:
                if lo < p_eq <= hi:
                    nodo = agg.setdefault((mercato, etichetta),
                                          {"per_partita": {}, "somma_p": 0.0,
                                           "n": 0, "uscite": 0})
                    cella = nodo["per_partita"].setdefault(fid, [0, 0])
                    cella[0] += 1 if uscita else 0
                    cella[1] += 1
                    nodo["somma_p"] += p_eq
                    nodo["n"] += 1
                    nodo["uscite"] += 1 if uscita else 0
                    break

    righe_out: List[dict] = []
    for chiave in sorted(agg, key=lambda t: (t[0], etichette.index(t[1]))):
        mercato, etichetta = chiave
        nodo = agg[chiave]
        n, uscite = nodo["n"], nodo["uscite"]
        p_media = nodo["somma_p"] / n if n else 0.0
        p_reale = uscite / n if n else 0.0
        lo_b, hi_b = bootstrap_grappolo({k: (v[0], v[1]) for k, v in nodo["per_partita"].items()},
                                        giri=giri_boot)
        righe_out.append({
            "mercato": mercato, "periodo": MERCATI[mercato], "secchio": etichetta,
            "n_selezioni": n, "n_partite": len(nodo["per_partita"]), "uscite": uscite,
            "p_equa_media": round(p_media, 6), "p_reale": round(p_reale, 6),
            "p_reale_boot_lo": round(lo_b, 6), "p_reale_boot_hi": round(hi_b, 6),
            "k_equo": round(p_media / p_reale, 3) if p_reale > 0 else None,
            "k_equo_prudente": round(p_media / hi_b, 3) if hi_b > 0 else None,
        })
    return {"righe": righe_out}


def secchio_di(p_imp: float) -> str:
    """Etichetta del secchio di una p_implicita (stessa griglia della misura)."""
    for lo, hi, etichetta in SECCHI:
        if lo < float(p_imp) <= hi:
            return etichetta
    return SECCHI[-1][2]


def tabella_k(dati: dict) -> Dict[Tuple[str, str], float]:
    """(periodo, secchio) -> k da usare nel cancello. Dove il secchio non e'
    misurabile o non e' operabile si usa K_PRUDENTE, con il motivo dichiarato
    nella riga (``motivo_soglia``)."""
    fuori: Dict[Tuple[str, str], float] = {}
    for r in dati.get("righe", ()):
        fuori[(str(r["periodo"]), str(r["secchio"]))] = float(r.get("k_soglia") or K_PRUDENTE)
    return fuori


def carica_tabella_k(percorso: Optional[str] = None) -> Dict[Tuple[str, str], float]:
    """Tabella k dal file versionato; {} se manca (il motore usa K_PRUDENTE)."""
    p = percorso or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "data", "k_misurato_2026-09-16.json")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return tabella_k(json.load(fh))
    except (OSError, ValueError):
        return {}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Misura di k (favourite-longshot bias) su betfair_market_odds")
    ap.add_argument("--commissione", type=float, default=COMMISSIONE_DEFAULT)
    ap.add_argument("--boot", type=int, default=2000, help="giri di bootstrap a grappolo")
    ap.add_argument("--out", default=os.path.join("Betfair", "omega", "data",
                                                  "k_misurato_2026-09-16.json"))
    args = ap.parse_args(argv)

    sys.path.insert(0, os.getcwd())
    from db_client import get_supabase_client  # import tardivo: il modulo resta puro

    sb = get_supabase_client()
    print("lettura quote (Correct Score + Half Time Score)...", flush=True)
    quote = leggi_quote(sb)
    print(f"  righe quote: {len(quote)}", flush=True)
    fixture_ids = [int(r["fixture_id"]) for r in quote]
    print(f"  fixture distinte: {len(set(fixture_ids))}", flush=True)
    esiti = leggi_esiti(sb, fixture_ids)
    print(f"  esiti trovati: {len(esiti)}", flush=True)

    dati = misura(quote, esiti, commissione=args.commissione, giri_boot=args.boot)
    dati["equa"] = misura_equa(quote, esiti, giri_boot=args.boot)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"scritto {args.out}")
    print(f"partite FT {dati['partite_ft']} / HT {dati['partite_ht']}  scartate {dati['scartate']}")
    intest = ("mercato", "secchio", "n", "part.", "uscite", "p_impl", "p_reale",
              "k", "k_prud", "operabile")
    print("{:<16}{:<11}{:>7}{:>7}{:>8}{:>9}{:>9}{:>8}{:>8}{:>11}".format(*intest))
    for r in dati["righe"]:
        print("{:<16}{:<11}{:>7}{:>7}{:>8}{:>9.4f}{:>9.4f}{:>8}{:>8}{:>11}".format(
            r["mercato"][:15], r["secchio"], r["n_selezioni"], r["n_partite"],
            r["uscite"], r["p_implicita_media"], r["p_reale"],
            "-" if r["k_centro"] is None else f"{r['k_centro']:.2f}",
            "-" if r["k_prudente"] is None else f"{r['k_prudente']:.2f}",
            "SI" if r["operabile"] else "no"))
    print("\n-- probabilita' DEVIGATA (forma del bias, spread escluso) --")
    print("{:<16}{:<11}{:>7}{:>7}{:>8}{:>9}{:>9}{:>8}{:>8}".format(
        "mercato", "secchio", "n", "part.", "uscite", "p_equa", "p_reale", "k_eq", "k_eq_pr"))
    for r in dati["equa"]["righe"]:
        print("{:<16}{:<11}{:>7}{:>7}{:>8}{:>9.4f}{:>9.4f}{:>8}{:>8}".format(
            r["mercato"][:15], r["secchio"], r["n_selezioni"], r["n_partite"],
            r["uscite"], r["p_equa_media"], r["p_reale"],
            "-" if r["k_equo"] is None else f"{r['k_equo']:.2f}",
            "-" if r["k_equo_prudente"] is None else f"{r['k_equo_prudente']:.2f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
