# -*- coding: utf-8 -*-
"""M1/M2 - Mike e le P CALIBRATE dell'Over 3.5 / 4.5. SOLO MISURA.

ATTUALE: `mike/dossier.build_prematch` calcola ``p_under35_cal`` =
1 - db_json_analisi.markets_calibrated.over_3_5["True"] e NESSUNO la legge;
``p_over45_cal`` non viene mai valorizzata.

Parte A (``affidabilita``): hit-rate REALE per DECILE di probabilita' di
`markets_calibrated.over_3_5` e `over_4_5` contro la frequenza osservata
(Wilson 95 %), Brier e log-loss della calibrata e della grezza
(`markets.over_x_5`) con differenza APPAIATA e IC bootstrap; separata PRIMA e
DOPO la data dell'ultima calibrazione Poisson (21/09: dopo = fuori campione).
La P dell'Under 3.5 si legge con la funzione di PRODUZIONE
(`dossier.build_prematch` su un DB finto con le chiavi vere).

Parte B (``conta``): sulle registrazioni del replay Mike (uscita JSON di
`certifica mike ... --json`), quante partite sono ENTRATE in HOLD o nell'ultimo
ingresso PERSIST (`PRE_LAST_ENTRY_PENDING`) e, fra queste, quante avrebbero
avuto ``p_under35_cal`` sotto soglia. La soglia NON e' a occhio: e' l'inversa
della curva di affidabilita' (isotonica sulla frequenza OSSERVATA dell'Under)
al pareggio del back Under alla quota q (1/q netto commissione), per q nella
banda d'ingresso di Mike (1,30-3,00, `mike/config.py`).

Uso:
  python -m ...misura_punto8.m1_mike affidabilita --estrazione estr_m1.json.gz --out m1.json
  python -m ...misura_punto8.m1_mike conta --referto certifica_mike.json \
      --estrazione estr_mike_ev.json.gz --curva m1.json --out m1_conta.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Betfair.stream.backtest.tools.misura_punto8 import comune as C

C.blinda_db()

DATA_CALIBRAZIONE_POISSON = "2026-09-21"
COMMISSIONE = 0.05
QUOTE_BANDA = (1.30, 1.50, 2.00, 2.50, 3.00)


def _json(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


class _DbMike:
    """Le tre letture di `build_prematch`, con le chiavi vere."""

    def __init__(self, fid: Optional[int], analisi: Optional[dict],
                 lam: Optional[tuple] = None) -> None:
        self._fid, self._an, self._lam = fid, analisi, lam

    def fixture_id_for_event(self, _eid: str) -> Optional[int]:
        return self._fid

    def fixture_lambdas(self, _fid: Any) -> Optional[tuple]:
        return self._lam

    def fixture_analysis(self, _fid: Any) -> Optional[dict]:
        return self._an


def p_under35_cal_produzione(db_json_analisi: Optional[dict], fid: Optional[int] = 1) -> Optional[float]:
    """``p_under35_cal`` calcolata dalla funzione VERA di Mike."""
    from Betfair.mike.dossier import build_prematch
    out = build_prematch("m8", _DbMike(fid, _json(db_json_analisi)))
    v = out.get("p_under35_cal")
    return None if v is None else float(v)


def p_true(nodo: Any) -> Optional[float]:
    """P("True") da un nodo {True: p, False: q} (formato letto da Mike)."""
    nodo = _json(nodo)
    if not isinstance(nodo, dict) or nodo.get("True") is None:
        return None
    try:
        p = float(nodo["True"])
    except (TypeError, ValueError):
        return None
    return p if 0.0 <= p <= 1.0 else None


def decili(righe: Sequence[dict], chiave: str) -> List[dict]:
    out = []
    for i in range(10):
        lo, hi = i / 10.0, (i + 1) / 10.0
        rr = [r for r in righe if r.get(chiave) is not None
              and (lo <= r[chiave] < hi or (i == 9 and r[chiave] == 1.0))]
        if not rr:
            continue
        k = sum(r["y"] for r in rr)
        w = C.wilson(k, len(rr))
        pm = sum(r[chiave] for r in rr) / len(rr)
        out.append({"decile": f"{lo:.1f}-{hi:.1f}", "n": len(rr), "p_media": round(pm, 4),
                    "freq_osservata": round(k / len(rr), 4), "wilson_lo": round(w[0], 4),
                    "wilson_hi": round(w[1], 4),
                    "dentro_IC": bool(w[0] <= pm <= w[1])})
    return out


def affidabilita(ext: dict, *, giri: int) -> dict:
    esiti = {int(r["fixture_id"]): r for r in ext.get("esiti") or []}
    righe: Dict[str, List[dict]] = {"over_3_5": [], "over_4_5": []}
    for fp in ext.get("fixture_predictions") or []:
        es = esiti.get(int(fp["fixture_id"]))
        if not es or es.get("goals_home") is None or \
                str(es.get("status_short") or "").upper() not in ("FT", "AET", "PEN"):
            continue
        tot = int(es["goals_home"]) + int(es["goals_away"])
        data = str(fp.get("fixture_date") or "")[:10]
        # Over 3.5: la calibrata letta DALLA FUNZIONE DI MIKE (1 - p_under35_cal)
        pu = p_under35_cal_produzione({"markets_calibrated": {"over_3_5": _json(fp.get("o35"))}})
        base = {"fixture_id": int(fp["fixture_id"]), "data": data}
        if pu is not None:
            righe["over_3_5"].append({**base, "p_cal": 1.0 - pu, "p_grezza": p_true(fp.get("r35")),
                                      "y": int(tot >= 4)})
        p45 = p_true(fp.get("o45"))
        if p45 is not None:
            righe["over_4_5"].append({**base, "p_cal": p45, "p_grezza": p_true(fp.get("r45")),
                                      "y": int(tot >= 5)})
    out: Dict[str, Any] = {}
    for mercato, rr in righe.items():
        blocco: Dict[str, Any] = {"n": len(rr)}
        for nome, sub in (("tutte", rr),
                          ("prima_del_21_09 (in campione per la calibrazione)",
                           [r for r in rr if r["data"] < DATA_CALIBRAZIONE_POISSON]),
                          ("dal_21_09 (FUORI CAMPIONE)",
                           [r for r in rr if r["data"] >= DATA_CALIBRAZIONE_POISSON])):
            if not sub:
                blocco[nome] = {"n": 0}
                continue
            b: Dict[str, Any] = {"n": len(sub), "freq": sum(r["y"] for r in sub) / len(sub),
                                 "decili_calibrata": decili(sub, "p_cal")}
            for metr, fn in (("brier", C.brier_binario), ("logloss", C.log_loss_binario)):
                b[f"{metr}_calibrata"] = sum(fn(r["p_cal"], r["y"]) for r in sub) / len(sub)
                cop = [r for r in sub if r.get("p_grezza") is not None]
                if cop:
                    d = [fn(r["p_cal"], r["y"]) - fn(r["p_grezza"], r["y"]) for r in cop]
                    ic = C.bootstrap_media(d, [r["fixture_id"] for r in cop], giri=giri)
                    b[f"{metr}_grezza"] = sum(fn(r["p_grezza"], r["y"]) for r in cop) / len(cop)
                    b[f"diff_{metr}_calibrata_meno_grezza"] = ic
                    b[f"verdetto_{metr}"] = C.verdetto(ic)
            blocco[nome] = b
        out[mercato] = blocco
    out["curva_under35"] = curva_under(righe["over_3_5"])
    return out


def curva_under(righe_o35: Sequence[dict]) -> dict:
    """Isotonica (PAV della produzione, `safe_strategy.calibration._pav`) della
    frequenza OSSERVATA dell'Under 3.5 contro la P dichiarata dell'Under, per
    decile. Da qui la soglia: la P dichiarata sotto la quale l'Under esce meno
    del pareggio del back alla quota q."""
    from Betfair.safe_strategy.calibration import _pav
    punti = []
    for i in range(10):
        lo, hi = i / 10.0, (i + 1) / 10.0
        rr = [r for r in righe_o35 if lo <= 1.0 - r["p_cal"] < hi or (i == 9 and r["p_cal"] == 0.0)]
        if rr:
            punti.append((sum(1.0 - r["p_cal"] for r in rr) / len(rr),
                          sum(1 - r["y"] for r in rr) / len(rr), float(len(rr))))
    if not punti:
        return {"nodi": [], "soglie": {}}
    iso = _pav([p[0] for p in punti], [p[1] for p in punti], [p[2] for p in punti])
    nodi = [[round(p[0], 4), round(y, 4), int(p[2])] for p, y in zip(punti, iso)]
    return {"nodi": nodi, "soglie": {f"{q:.2f}": soglia_da_curva(nodi, pareggio_back(q))
                                     for q in QUOTE_BANDA}}


def pareggio_back(q: float, c: float = COMMISSIONE) -> float:
    """P minima perche' un back a quota q abbia EV >= 0 netto commissione:
    p (q-1)(1-c) = 1-p  ->  p = 1 / (1 + (q-1)(1-c))."""
    return 1.0 / (1.0 + (float(q) - 1.0) * (1.0 - c))


def soglia_da_curva(nodi: Sequence[Sequence[float]], obiettivo: float) -> Optional[float]:
    """La P DICHIARATA x a cui la curva isotonica (x -> freq osservata) vale
    ``obiettivo`` (interpolazione lineare; None se la curva non ci arriva)."""
    if not nodi:
        return None
    for (x0, y0, _), (x1, y1, _) in zip(nodi, nodi[1:]):
        if y0 <= obiettivo <= y1 and y1 > y0:
            return round(x0 + (obiettivo - y0) * (x1 - x0) / (y1 - y0), 4)
    if nodi[0][1] >= obiettivo:
        return round(nodi[0][0], 4)
    return None


def conta(referto: Sequence[dict], ext: dict, soglie: Dict[str, Optional[float]]) -> dict:
    ponte = {str(p["event_id"]): p.get("fixture_id") for p in ext.get("ponte") or []}
    fps = {int(r["fixture_id"]): r for r in ext.get("fixture_predictions") or []}
    per = []
    for r in referto:
        eid = str(r.get("event_id"))
        stati = set(r.get("stati") or [])
        fid = ponte.get(eid)
        an = _json((fps.get(int(fid)) or {}).get("db_json_analisi")) if fid is not None else None
        pu = p_under35_cal_produzione(an, fid) if an else None
        per.append({"event_id": eid, "fixture_id": fid, "hold": "HOLD" in stati,
                    "persist": "PRE_LAST_ENTRY_PENDING" in stati, "p_under35_cal": pu})
    entrate = [x for x in per if x["hold"] or x["persist"]]
    out = {"registrazioni": len(per), "entrate_hold_o_persist": len(entrate),
           "di_cui_con_p_under35_cal": sum(1 for x in entrate if x["p_under35_cal"] is not None),
           "sotto_soglia": {}}
    for q, s in soglie.items():
        if s is None:
            out["sotto_soglia"][q] = None
            continue
        out["sotto_soglia"][q] = {"soglia": s, "n": sum(
            1 for x in entrate if x["p_under35_cal"] is not None and x["p_under35_cal"] < s)}
    out["per_evento"] = per
    return out


def _carica(path: str) -> Any:
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def referto_da_stdout(testo: str) -> List[dict]:
    """L'array JSON stampato da `certifica ... --json` in coda all'output."""
    i = testo.rfind("\n[")
    i = 0 if testo.startswith("[") and i < 0 else i + 1
    return json.loads(testo[i:])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cosa", choices=["affidabilita", "conta"])
    ap.add_argument("--estrazione", required=True)
    ap.add_argument("--referto", default=None, help="conta: stdout di certifica mike --json")
    ap.add_argument("--curva", default=None, help="conta: uscita di 'affidabilita'")
    ap.add_argument("--giri", type=int, default=C.GIRI_MIN)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ext = _carica(a.estrazione)
    if a.cosa == "affidabilita":
        ris = affidabilita(ext, giri=a.giri)
    else:
        with open(a.referto, "r", encoding="utf-8") as fh:
            ref = referto_da_stdout(fh.read())
        soglie = (_carica(a.curva).get("curva_under35") or {}).get("soglie") or {}
        ris = conta(ref, ext, soglie)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(ris, fh, indent=1, default=str)
    print(json.dumps(ris, indent=1, default=str)[:5000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
