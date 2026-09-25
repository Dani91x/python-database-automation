# -*- coding: utf-8 -*-
"""O6 - Omega, CALIBRAZIONE DELLA CODA. SOLO MISURA.

Domanda: sulle selezioni del Correct Score a cui il modello V3 da' P piccola
(dove Omega banca), quante ne ESCONO davvero rispetto a quante ne attende il
modello? Rapporto USCITI / ATTESI per fascia di P (<=1 %, 1-2 %, 2-5 %):
  * < 1  -> il modello sovrastima la coda (prudente: chiede prezzi migliori,
            perde occasioni);
  * > 1  -> la sottostima (pericoloso: banca a prezzi che non pagano il rischio).

Due P, entrambe con funzioni di PRODUZIONE importate:
  * P_modello = `omega_v3.probabilita_selezioni` (griglia V3, parametri del banco
    del 16/09), al minuto 0 con le lambda della CATENA ATTUALE (O1);
  * P_fusa    = `omega_v3.fondi_col_mercato(P_modello, p_mercato_devigata(CS))`,
    SOLO se il file di estrazione porta le quote Correct Score del giorno
    (`betfair_market_odds`, mercato "Correct Score"). Il veto empirico
    (Wilson sulle transizioni) NON e' riprodotto: alza soltanto la P, quindi
    P_nostra >= P_fusa (dichiarato).

IC: bootstrap a grappolo sulla PARTITA (2.000+ giri) del rapporto usciti/attesi.

LIMITE DICHIARATO: le quote di `betfair_market_odds` sono PRE-PARTITA; Omega
opera in gioco (gamba A 1'-44', gamba B 46'-85'). La coda misurata qui e' quella
del prior al calcio d'inizio, non quella del cancello in gioco.

Uso:
  python -m Betfair.stream.backtest.tools.misura_punto8.o6_coda \
      --o1 <o1_catena_lambda.json> [--estensione <o6_estrazione.json.gz>] --out <file.json>
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Betfair.stream.backtest.tools.misura_punto8 import comune as C
from Betfair.stream.backtest.tools.misura_punto8 import percorsi as P

C.blinda_db()

FASCE: Tuple[Tuple[str, float, float], ...] = (
    ("<=1%", 0.0, 0.01), ("1-2%", 0.01, 0.02), ("2-5%", 0.02, 0.05))

# il Correct Score FT standard di Betfair: 0-0 .. 3-3 + i tre aggregati
NOMI_CS_STANDARD: Tuple[str, ...] = tuple(
    f"{h} - {a}" for h in range(4) for a in range(4)) + (
    "Any Other Home Win", "Any Other Away Win", "Any Other Draw")


def fascia_di(p: float) -> Optional[str]:
    for nome, lo, hi in FASCE:
        if lo < float(p) <= hi:
            return nome
    return None


def esito_selezione(nome: str, gh: int, ga: int, quotate: set) -> Optional[int]:
    """1 se la selezione ``nome`` e' uscita col risultato finale (gh, ga)."""
    from Betfair.omega import omega_v3 as V3
    sc = V3.parse_scoreline(nome)
    if sc is not None:
        return int(sc == (gh, ga))
    if not V3.e_aggregato(nome):
        return None
    if (gh, ga) in quotate:
        return 0
    d = V3.direzione_aggregato(nome)
    if d == "home":
        return int(gh > ga)
    if d == "away":
        return int(ga > gh)
    if d == "draw":
        return int(gh == ga)
    return 1        # "Any Unquoted" senza direzione: tutto cio' che non e' quotato


def righe_partita(fid: Any, lam: Sequence[float], esito: dict, *, p3=None,
                  runners_cs: Optional[List[Any]] = None) -> List[dict]:
    """Una riga per selezione: P_modello, P_fusa (se ci sono le quote CS), esito."""
    from Betfair.omega import omega_v3 as V3
    if p3 is None:
        from Betfair.omega import omega_proposte as OP
        p3 = OP.parametri_modello()
    gh, ga = int(esito["goals_home"]), int(esito["goals_away"])
    nomi = [str(r.name) for r in runners_cs] if runners_cs else list(NOMI_CS_STANDARD)
    pm = V3.probabilita_selezioni(periodo=V3.PERIODO_FT, minuto=0.0, punteggio=(0, 0),
                                  nomi=nomi, p=p3, lambdas=(float(lam[0]), float(lam[1])))
    p_merc = V3.p_mercato_devigata(runners_cs) if runners_cs else None
    quotate = {sc for sc in (V3.parse_scoreline(n) for n in nomi) if sc is not None}
    out = []
    for nome, p in pm.items():
        y = esito_selezione(nome, gh, ga, quotate)
        if y is None:
            continue
        r = {"fixture_id": fid, "nome": nome, "p_modello": float(p), "y": int(y)}
        if p_merc is not None:
            r["p_fusa"] = float(V3.fondi_col_mercato(float(p), p_merc(nome), p3))
        out.append(r)
    return out


def tabella(righe: Sequence[dict], chiave_p: str, *, giri: int) -> Dict[str, dict]:
    out = {}
    for nome, lo, hi in FASCE:
        rr = [r for r in righe if chiave_p in r and lo < r[chiave_p] <= hi]
        if not rr:
            out[nome] = {"n_selezioni": 0}
            continue
        ic = C.bootstrap_rapporto([r["y"] for r in rr], [r[chiave_p] for r in rr],
                                  [r["fixture_id"] for r in rr], giri=giri)
        out[nome] = {"n_selezioni": len(rr), "n_partite": ic["n_unita"],
                     "usciti": ic["num"], "attesi": round(ic["den"], 3),
                     "rapporto": ic["rapporto"], "ic_lo": ic["lo"], "ic_hi": ic["hi"],
                     "verdetto": ("SOVRASTIMA la coda (prudente)" if ic["hi"] < 1.0 else
                                  "SOTTOSTIMA la coda (pericolo)" if ic["lo"] > 1.0 else
                                  "calibrata entro l'IC")}
    return out


def _runners_da_estrazione(righe_cs: Sequence[dict]) -> Dict[Tuple[int, str], List[Any]]:
    """{(fixture_id, run_date): [runner(name, back_price, lay_price)]} dalle righe
    di `betfair_market_odds` (colonne vere: selection, back/lay = [{price,size}])."""
    def best(liv):
        if isinstance(liv, str):
            try:
                liv = json.loads(liv)
            except ValueError:
                return None
        if isinstance(liv, list) and liv:
            try:
                v = float(liv[0].get("price"))
                return v if v > 1.0 else None
            except (TypeError, ValueError, AttributeError):
                return None
        return None
    out: Dict[Tuple[int, str], List[Any]] = {}
    for r in righe_cs:
        k = (int(r["fixture_id"]), str(r.get("run_date") or ""))
        out.setdefault(k, []).append(SimpleNamespace(
            name=str(r.get("selection") or ""), back_price=best(r.get("back")),
            lay_price=best(r.get("lay"))))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--o1", required=True, help="uscita di o1_catena_lambda (lambda attuali)")
    ap.add_argument("--campione", default=P.F_M2_CAMPIONE)
    ap.add_argument("--estensione", default=None,
                    help="estrai_db.py o6: quote 1X2 + Correct Score + esiti")
    ap.add_argument("--giri", type=int, default=C.GIRI_MIN)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    from Betfair.omega import omega_proposte as OP
    p3 = OP.parametri_modello()
    with open(a.o1, "r", encoding="utf-8") as fh:
        o1 = json.load(fh)
    lam = {int(x["fixture_id"]): x["lam_attuale"] for x in o1["per_partita"]}
    with gzip.open(a.campione, "rt", encoding="utf-8") as fh:
        camp = json.load(fh)
    esiti = {int(r["fixture_id"]): r for r in camp["esiti"]}
    run = {int(q["fixture_id"]): str(q.get("run_date") or "") for q in camp["quote"]}
    gruppi: Dict[str, List[dict]] = {"M2 tutte (24/06-11/09)": [], "run 09-11/09": [],
                                     "estrazione 25/09 (run 09,10,11,17,23/09; con quote CS)": []}
    for fid, l in lam.items():
        es = esiti.get(fid)
        if not es or es.get("goals_home") is None:
            continue
        rr = righe_partita(fid, l, es, p3=p3)
        gruppi["M2 tutte (24/06-11/09)"] += rr
        if run.get(fid, "") >= "2026-09-09":
            gruppi["run 09-11/09"] += rr
    if a.estensione:
        with gzip.open(a.estensione, "rt", encoding="utf-8") as fh:
            ext = json.load(fh)
        from Betfair.stream.backtest.tools.misura_punto8 import o1_catena_lambda as O1
        es_ext = {int(r["fixture_id"]): r for r in ext.get("esiti") or []}
        fps = {int(r["fixture_id"]): r for r in ext.get("fixture_predictions") or []}
        cs = _runners_da_estrazione(ext.get("quote_cs") or [])
        for q in ext.get("quote") or []:
            fid = int(q["fixture_id"])
            es = es_ext.get(fid)
            if not es or es.get("goals_home") is None:
                continue
            fp = O1.riga_fp_postgrest(fps[fid]) if fid in fps else None
            la = O1.lambda_attuale(fid, es.get("league_id"), fp, O1.pre_ko_da_quote(q))
            if la is None:
                continue
            runners = cs.get((fid, str(q.get("run_date") or "")))
            gruppi["estrazione 25/09 (run 09,10,11,17,23/09; con quote CS)"] += righe_partita(
                fid, la[:2], es, p3=p3, runners_cs=runners)
    ris = {}
    for g, rr in gruppi.items():
        ris[g] = {"p_modello": tabella(rr, "p_modello", giri=a.giri)}
        if any("p_fusa" in r for r in rr):
            ris[g]["p_fusa"] = tabella(rr, "p_fusa", giri=a.giri)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"risultati": ris, "meta": {"o1": a.o1, "estensione": a.estensione,
                                               "giri": a.giri}}, fh, indent=1)
    print(json.dumps(ris, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
