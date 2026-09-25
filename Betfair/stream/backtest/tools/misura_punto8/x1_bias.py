# -*- coding: utf-8 -*-
"""X1 - scalper calcio, BIAS del maker su P calibrate. SOLO MISURA.

ATTUALE (`stream/scalper/bias_resolver.resolve_bias`): consenso sull'argmax 1X2
di ML (`model_predictions_json.targets.target_1x2`) e Poisson
(`db_json_analisi.markets.1x2`), P GREZZE; edge = media delle due / p_mid - 1
in [2 %, 20 %].
VARIANTE: le stesse regole su P CALIBRATE con la pagella (`direction_pagella`,
globale): p -> hit_rate reale della fascia di probabilita' di quel motore x
selezione.

Tre misure:
  A. PAGELLA: hit-rate per motore x selezione 1X2 x fascia (Q9) con Wilson 95 %
     e lo scarto dalla fascia dichiarata (sovra/sotto-fiducia).
  B. CONCORDANZA ML/Poisson partita per partita (finestra dell'estrazione):
     quanto spesso concordano, e l'hit-rate dell'argmax quando concordano e
     quando no (Wilson), per fascia della P media di consenso.
  C. Sulle due registrazioni dove lo scalper entra (35797769, 35777617): il bias
     che `resolve_bias` (funzione VERA) avrebbe dato con le P grezze e con le P
     calibrate, al prezzo MID dell'ultimo book pre-KO della registrazione.

Uso:
  python -m ...misura_punto8.x1_bias --estrazione estr_x1.json.gz [--live-raw auto] --out x1.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Betfair.stream.backtest.tools.misura_punto8 import comune as C
from Betfair.stream.backtest.tools.misura_punto8 import percorsi as P

C.blinda_db()

EVENTI_SCALPER = ("35797769", "35777617")
# fasce della pagella (`build_direzione.py:21-22`): [lo, hi)
FASCE = ((0.0, 0.30, "<.30"), (0.30, 0.40, ".30-.40"), (0.40, 0.50, ".40-.50"),
         (0.50, 0.60, ".50-.60"), (0.60, 0.70, ".60-.70"), (0.70, 1.01, ">.70"))
_SEL = {"H": "H", "D": "D", "A": "A", "1": "H", "X": "D", "2": "A",
        "HOME": "H", "DRAW": "D", "AWAY": "A"}


def fascia_di(p: float) -> str:
    for lo, hi, et in FASCE:
        if lo <= float(p) < hi:
            return et
    return FASCE[-1][2]


def _json(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


def mappa_pagella(righe: Sequence[dict]) -> Dict[Tuple[str, str, str], dict]:
    """(engine, selezione H/D/A, fascia) -> riga della pagella 1X2 globale."""
    out = {}
    for r in righe:
        if str(r.get("market")) != "1x2" or int(r.get("league_id") or 0) != 0:
            continue
        sel = _SEL.get(str(r.get("selection") or "").upper())
        if sel is None:
            continue
        out[(str(r["engine"]), sel, str(r["prob_bucket"]))] = r
    return out


def tabella_pagella(righe: Sequence[dict]) -> List[dict]:
    out = []
    lim = {et: (lo, hi) for lo, hi, et in FASCE}
    for (eng, sel, fa), r in sorted(mappa_pagella(righe).items()):
        n, k = int(r["n"]), int(r["hits"])
        w = C.wilson(k, n)
        lo, hi = lim.get(fa, (0.0, 1.0))
        stato = ("SOVRA-fiducia (esce meno della fascia)" if w[1] < lo else
                 "SOTTO-fiducia (esce piu' della fascia)" if w[0] > min(hi, 1.0) else
                 "coerente con la fascia")
        out.append({"engine": eng, "sel": sel, "fascia": fa, "n": n, "hit_rate": k / n if n else None,
                    "wilson": [round(w[0], 4), round(w[1], 4)], "stato": stato})
    return out


def calibra(probs: Optional[Dict[str, Any]], engine: str,
            pag: Dict[Tuple[str, str, str], dict]) -> Optional[Dict[str, float]]:
    """P -> hit_rate della fascia (pagella globale). Se la fascia manca, resta
    la P grezza (non si inventa)."""
    if not isinstance(probs, dict):
        return None
    out = {}
    for s in ("H", "D", "A"):
        v = probs.get(s)
        if v is None:
            return None
        r = pag.get((engine, s, fascia_di(float(v))))
        out[s] = float(r["hit_rate"]) if r else float(v)
    return out


def riga_calibrata(pred: dict, pag: Dict[Tuple[str, str, str], dict]) -> dict:
    """La riga `fixture_predictions` con le mappe 1X2 sostituite dalle calibrate,
    NELLE STESSE CHIAVI che legge `bias_resolver.extract_1x2`."""
    from Betfair.stream.scalper.bias_resolver import extract_1x2
    p = extract_1x2(pred)
    ml_c, po_c = calibra(p["ml"], "ml", pag), calibra(p["poisson"], "poisson", pag)
    nuova = json.loads(json.dumps(pred))
    if ml_c is not None:
        nuova.setdefault("model_predictions_json", {}).setdefault("targets", {})["target_1x2"] = ml_c
        nuova["model_predictions_json"]["targets"].pop("target_ft_1x2", None)
    if po_c is not None:
        nuova.setdefault("db_json_analisi", {}).setdefault("markets", {})["1x2"] = po_c
    return nuova


def concordanza(ext: dict) -> dict:
    """ML e Poisson partita per partita: accordo e hit-rate dell'argmax."""
    esiti = {int(r["fixture_id"]): r for r in ext.get("esiti") or []}
    from Betfair.stream.scalper.bias_resolver import _argmax_1x2
    conta = {"n": 0, "concordi": 0, "concordi_hit": 0, "discordi": 0,
             "discordi_ml_hit": 0, "discordi_po_hit": 0}
    per_fascia: Dict[str, List[int]] = {}
    for r in ext.get("finestra_1x2") or []:
        es = esiti.get(int(r["fixture_id"]))
        if not es or es.get("goals_home") is None or \
                str(es.get("status_short") or "").upper() not in ("FT", "AET", "PEN"):
            continue
        ml_raw = _json(r.get("ml")) or _json(r.get("ml_ft"))
        ml = _argmax_1x2({k: (ml_raw or {}).get(k) for k in ("H", "D", "A")} if ml_raw else None)
        po = _argmax_1x2(_json(r.get("po")))
        if ml is None or po is None:
            continue
        gh, ga = int(es["goals_home"]), int(es["goals_away"])
        vero = "H" if gh > ga else "A" if ga > gh else "D"
        conta["n"] += 1
        if ml[0] == po[0]:
            conta["concordi"] += 1
            hit = int(ml[0] == vero)
            conta["concordi_hit"] += hit
            per_fascia.setdefault(fascia_di((ml[1] + po[1]) / 2.0), []).append(hit)
        else:
            conta["discordi"] += 1
            conta["discordi_ml_hit"] += int(ml[0] == vero)
            conta["discordi_po_hit"] += int(po[0] == vero)
    out: Dict[str, Any] = dict(conta)
    if conta["concordi"]:
        out["hit_concordi"] = conta["concordi_hit"] / conta["concordi"]
        out["wilson_concordi"] = C.wilson(conta["concordi_hit"], conta["concordi"])
    if conta["discordi"]:
        out["hit_discordi_ml"] = conta["discordi_ml_hit"] / conta["discordi"]
        out["hit_discordi_poisson"] = conta["discordi_po_hit"] / conta["discordi"]
    out["concordi_per_fascia_p_media"] = {
        f: {"n": len(v), "hit": sum(v) / len(v), "wilson": C.wilson(sum(v), len(v))}
        for f, v in sorted(per_fascia.items())}
    return out


def _normalizza(p: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
    if not p:
        return None
    tot = sum(float(v) for v in p.values())
    return {k: float(v) / tot for k, v in p.items()} if tot > 0 else None


def brier_calibrazione(ext: dict, pag: Dict[Tuple[str, str, str], dict], *,
                       giri: int = C.GIRI_MIN) -> dict:
    """Brier 1X2 (3 classi) e log-loss della P GREZZA contro la P CALIBRATA con
    la pagella (normalizzata a somma 1), per motore, partita per partita sulla
    finestra; differenza appaiata con IC bootstrap sulla partita. Poi la P
    media di CONSENSO dichiarata contro la frequenza osservata per fascia.

    ATTENZIONE: la pagella e' costruita sullo storico settled (generated_at nel
    file): le partite della finestra gia' giocate a quella data sono IN CAMPIONE
    per la calibrata. Il confronto e' ottimista per la variante."""
    from Betfair.stream.scalper.bias_resolver import _argmax_1x2
    esiti = {int(r["fixture_id"]): r for r in ext.get("esiti") or []}
    per_motore: Dict[str, List[Tuple[int, float, float, float, float]]] = {"ml": [], "poisson": []}
    consenso: Dict[str, List[Tuple[float, int]]] = {}
    for r in ext.get("finestra_1x2") or []:
        es = esiti.get(int(r["fixture_id"]))
        if not es or es.get("goals_home") is None or \
                str(es.get("status_short") or "").upper() not in ("FT", "AET", "PEN"):
            continue
        gh, ga = int(es["goals_home"]), int(es["goals_away"])
        vero = "H" if gh > ga else "A" if ga > gh else "D"
        ml_raw = _json(r.get("ml")) or _json(r.get("ml_ft"))
        mappe = {"ml": {k: (ml_raw or {}).get(k) for k in ("H", "D", "A")} if ml_raw else None,
                 "poisson": _json(r.get("po"))}
        argm = {}
        for eng, m in mappe.items():
            if not isinstance(m, dict) or any(m.get(k) is None for k in ("H", "D", "A")):
                continue
            g = _normalizza({k: float(m[k]) for k in ("H", "D", "A")})
            c = _normalizza(calibra(m, eng, pag))
            if g is None or c is None:
                continue
            bg = C.brier_multiclasse(g, vero)
            bc = C.brier_multiclasse(c, vero)
            per_motore[eng].append((int(r["fixture_id"]), bg, bc, C.log_loss(g[vero]),
                                    C.log_loss(c[vero])))
            argm[eng] = _argmax_1x2(m)
        if argm.get("ml") and argm.get("poisson") and argm["ml"][0] == argm["poisson"][0]:
            pm = (argm["ml"][1] + argm["poisson"][1]) / 2.0
            consenso.setdefault(fascia_di(pm), []).append((pm, int(argm["ml"][0] == vero)))
    out: Dict[str, Any] = {"pagella_generata": sorted({str(x.get("generated_at"))[:10]
                                                       for x in ext.get("direction_pagella") or []})}
    for eng, rr in per_motore.items():
        if not rr:
            out[eng] = {"n": 0}
            continue
        ib = C.bootstrap_media([x[2] - x[1] for x in rr], [x[0] for x in rr], giri=giri)
        il = C.bootstrap_media([x[4] - x[3] for x in rr], [x[0] for x in rr], giri=giri,
                               seme=C.SEME + 7)
        out[eng] = {"n": len(rr), "brier_grezza": sum(x[1] for x in rr) / len(rr),
                    "brier_calibrata": sum(x[2] for x in rr) / len(rr), "diff_brier": ib,
                    "verdetto_brier": C.verdetto(ib),
                    "logloss_grezza": sum(x[3] for x in rr) / len(rr),
                    "logloss_calibrata": sum(x[4] for x in rr) / len(rr), "diff_logloss": il,
                    "verdetto_logloss": C.verdetto(il)}
    out["consenso_dichiarata_vs_osservata"] = {
        f: {"n": len(v), "p_media_dichiarata": sum(p for p, _ in v) / len(v),
            "freq_osservata": sum(y for _, y in v) / len(v),
            "wilson": C.wilson(sum(y for _, y in v), len(v))}
        for f, v in sorted(consenso.items())}
    return out


def mid_pre_ko(live_raw: str, eid: str, max_righe: int = 400_000) -> Optional[Dict[int, float]]:
    """{selection_id: 1/mid} dell'ULTIMO book Match Odds prima del primo tick in
    gioco (ladder atb/atl ricostruita dai delta: size 0 = livello tolto), e
    {selection_id: sortPriority}."""
    path = os.path.join(live_raw, eid, f"{eid}.raw.jsonl")
    if not os.path.isfile(path):
        return None
    mo, sorts = None, {}
    atb: Dict[int, Dict[float, float]] = {}
    atl: Dict[int, Dict[float, float]] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh):
            if n >= max_righe:
                break
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            fine = False
            for mc in rec.get("mc") or []:
                md = mc.get("marketDefinition")
                if md is not None and str(md.get("marketType") or "") == "MATCH_ODDS":
                    mo = mc.get("id")
                    s = {int(r["id"]): int(r.get("sortPriority") or 0)
                         for r in md.get("runners") or [] if r.get("id") is not None}
                    sorts = s or sorts
                    if md.get("inPlay"):
                        fine = True
                if mo is None or mc.get("id") != mo or fine:
                    continue
                for rc in mc.get("rc") or []:
                    sid = int(rc["id"])
                    for chiave, lad in (("atb", atb), ("atl", atl)):
                        for pr, sz in rc.get(chiave) or []:
                            l = lad.setdefault(sid, {})
                            if float(sz) <= 0:
                                l.pop(float(pr), None)
                            else:
                                l[float(pr)] = float(sz)
            if fine:
                break
    probs = {}
    for sid in sorts:
        b = max(atb.get(sid, {}) or [0.0])
        l = min(atl.get(sid, {}) or [0.0]) if atl.get(sid) else 0.0
        if b > 1.0 and l > 1.0:
            probs[sid] = 1.0 / ((b + l) / 2.0)
    return {"probs": probs, "sorts": sorts} if probs else None


def bias_registrazioni(ext: dict, live_raw: Optional[str],
                       pag: Dict[Tuple[str, str, str], dict]) -> List[dict]:
    from Betfair.stream.scalper.bias_resolver import resolve_bias
    from Betfair.safe_strategy.tools.validate_opportunity import load_score_rows
    ponte = {str(p["event_id"]): p.get("fixture_id") for p in ext.get("ponte") or []}
    fps = {int(r["fixture_id"]): r for r in ext.get("fixture_predictions") or []}
    out = []
    for eid in EVENTI_SCALPER:
        fid = ponte.get(eid)
        pred = fps.get(int(fid)) if fid is not None else None
        riga = {"event_id": eid, "fixture_id": fid}
        if pred is None:
            riga["esito"] = "nessuna fixture_predictions nell'estrazione"
            out.append(riga)
            continue
        pred = {**pred, "model_predictions_json": _json(pred.get("model_predictions_json")),
                "db_json_analisi": _json(pred.get("db_json_analisi"))}
        rows = load_score_rows(live_raw, eid) if live_raw else []
        home = next((r["home"] for r in rows if r.get("home")), "") or "Home"
        away = next((r["away"] for r in rows if r.get("away")), "") or "Away"
        book = mid_pre_ko(live_raw, eid) if live_raw else None
        # nomi dei runner come il catalogo: sortPriority 1=casa, 2=trasferta, 3=pareggio
        nomi = {}
        mid = None
        if book:
            per_sort = {v: k for k, v in book["sorts"].items()}
            nomi = {per_sort[1]: home, per_sort[2]: away, per_sort[3]: "The Draw"} \
                if all(s in per_sort for s in (1, 2, 3)) else {}
            if nomi:
                mid = {"H": book["probs"].get(per_sort[1]), "A": book["probs"].get(per_sort[2]),
                       "D": book["probs"].get(per_sort[3])}
        d0 = resolve_bias(pred, nomi, home, away, mid)
        d1 = resolve_bias(riga_calibrata(pred, pag), nomi, home, away, mid)
        riga.update({"grezza": d0.to_meta(), "calibrata": d1.to_meta(),
                     "bias_cambiato": d0.bias != d1.bias})
        out.append(riga)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--estrazione", required=True)
    ap.add_argument("--live-raw", default="auto")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with gzip.open(a.estrazione, "rt", encoding="utf-8") as fh:
        ext = json.load(fh)
    pag = mappa_pagella(ext.get("direction_pagella") or [])
    live = P.live_raw(None if a.live_raw == "auto" else a.live_raw)
    ris = {"pagella_1x2": tabella_pagella(ext.get("direction_pagella") or []),
           "concordanza": concordanza(ext),
           "brier_grezza_vs_calibrata": brier_calibrazione(ext, pag),
           "registrazioni": bias_registrazioni(ext, live, pag)}
    ris["bias_cambiati"] = sum(1 for r in ris["registrazioni"] if r.get("bias_cambiato"))
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(ris, fh, indent=1, default=str)
    print(json.dumps(ris, indent=1, default=str)[:5000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
