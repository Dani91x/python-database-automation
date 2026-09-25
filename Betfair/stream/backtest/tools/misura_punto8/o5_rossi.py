# -*- coding: utf-8 -*-
"""O5 - Omega V3 e i CARTELLINI ROSSI. SOLO MISURA.

ATTUALE: `omega_v3.griglia_finale` ignora i rossi (il feed li porta, il modello
no). VARIANTE: stessa griglia, con le intensita' RESIDUE moltiplicate per i
coefficienti GLOBALI (mai per lega: campione piccolo, rischio di overfitting)
di `inplay_intensity_by_league.json`, letti con la funzione di produzione
`stream.engine.live_engine.red_card_multipliers(rh, ra, league_id=None)`.

Come si innesta il moltiplicatore nel V3 (gamma-Poisson): la predittiva dei gol
residui e' una NegBin con forma a+gol_visti e scala beta = (a/lambda0 +
esposizione_consumata) / esposizione_residua. Moltiplicare l'INTENSITA' residua
per m equivale a moltiplicare l'esposizione residua per m, cioe' beta -> beta/m.
`griglia_con_rossi` fa esattamente questo usando le funzioni interne del V3
(`_negbin_pmf`, `esposizione`, `intensita_residue`, `_tau_dc`, importate), e con
m = (1, 1) RESTITUISCE LA GRIGLIA DI PRODUZIONE AL BIT (test di equivalenza).

Metrica: log-loss e Brier del risultato ESATTO FINALE, valutati al minuto del
primo rosso (con il punteggio di quel minuto) e, come seconda lettura, ogni 10'
fino all'85' (piu' punti per partita: IC a grappolo sulla partita). Campione
piccolo per costruzione: n e IC sempre dichiarati.

Fonti (in ordine di forza):
  * ``--estrazione`` (estrai_db.py o5): partite con rosso da `match_events`
    (event_type 'Card', detail con 'Red'), gol col minuto, esito, quote 1X2;
  * ``--live-raw``: le registrazioni `_live_raw/` (rossi e punteggi dall'IPS,
    lambda dal pre_ko): poche partite, ma senza bisogno del DB.

Uso:
  python -m Betfair.stream.backtest.tools.misura_punto8.o5_rossi --live-raw auto --out <f.json>
  python -m Betfair.stream.backtest.tools.misura_punto8.o5_rossi --estrazione <o5.json.gz> --out <f.json>
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
from Betfair.stream.backtest.tools.misura_punto8 import percorsi as P

C.blinda_db()


def griglia_con_rossi(*, minuto: float, punteggio: Tuple[int, int], p: Any,
                      lambdas: Tuple[float, float],
                      mult: Tuple[float, float]) -> Dict[Tuple[int, int], float]:
    """Griglia del PUNTEGGIO FINALE (periodo FT) con le intensita' residue
    moltiplicate per ``mult`` = (casa, trasferta). Solo il ramo gamma_poisson
    (quello di produzione, `v3_modello`): per gli altri rami si alza un errore
    invece di inventare un'equivalenza."""
    from Betfair.omega import omega_v3 as V3
    if not (p.modello == "gamma_poisson" and p.forma_gamma > 0):
        raise ValueError("griglia_con_rossi vale solo per il modello gamma_poisson di produzione")
    periodo = V3.PERIODO_FT
    sh, sa = int(punteggio[0]), int(punteggio[1])
    mg = int(V3.MAX_GOL_RESIDUI[periodo])
    mh, ma = float(mult[0]), float(mult[1])
    lh_r, la_r = V3.intensita_residue(minuto=minuto, punteggio=(sh, sa), periodo=periodo,
                                      p=p, lambdas=lambdas)
    lh_r, la_r = lh_r * mh, la_r * ma
    applica_tau = p.dc_sempre or (sh == 0 and sa == 0)
    consumata, residua = V3.esposizione(minuto, periodo, p)
    a = float(p.forma_gamma)
    lh0, la0 = max(1e-6, float(lambdas[0])), max(1e-6, float(lambdas[1]))
    d = sh - sa
    rh = max(1e-12, residua * math.exp(-p.beta_squilibrio * d)) * mh
    ra = max(1e-12, residua * math.exp(+p.beta_squilibrio * d)) * ma
    bh = (a / lh0 + consumata) / rh
    ba = (a / la0 + consumata) / ra
    ph = [V3._negbin_pmf(k, a + sh, bh) for k in range(mg + 1)]
    pa = [V3._negbin_pmf(k, a + sa, ba) for k in range(mg + 1)]
    g: Dict[Tuple[int, int], float] = {}
    for h in range(mg + 1):
        for x in range(mg + 1):
            v = ph[h] * pa[x]
            if applica_tau:
                v *= V3._tau_dc(h, x, lh_r, la_r, p.rho)
            g[(h, x)] = v
    tot = sum(g.values())
    if tot <= 0 or not math.isfinite(tot):
        return {}
    return {(sh + h, sa + x): v / tot for (h, x), v in g.items()}


def moltiplicatori_globali(rh: int, ra: int) -> Tuple[float, float]:
    from Betfair.stream.engine.live_engine import red_card_multipliers
    return red_card_multipliers(int(rh), int(ra), None)


def valuta_punto(*, minuto: float, punteggio: Tuple[int, int], rossi: Tuple[int, int],
                 lambdas: Tuple[float, float], finale: Tuple[int, int], p: Any) -> Optional[dict]:
    from Betfair.omega import omega_v3 as V3
    att = V3.griglia_finale(minuto=minuto, punteggio=punteggio, periodo=V3.PERIODO_FT,
                            p=p, lambdas=lambdas)
    var = griglia_con_rossi(minuto=minuto, punteggio=punteggio, p=p, lambdas=lambdas,
                            mult=moltiplicatori_globali(*rossi))
    if not att or not var:
        return None
    return {"ll_att": C.log_loss(att.get(finale, 0.0)), "ll_var": C.log_loss(var.get(finale, 0.0)),
            "br_att": C.brier_multiclasse(att, finale), "br_var": C.brier_multiclasse(var, finale)}


def punti_di_valutazione(eventi: Sequence[dict], primo_rosso: int) -> List[int]:
    """Il minuto del primo rosso e poi ogni 10' fino all'85'."""
    out = [int(primo_rosso)]
    m = (int(primo_rosso) // 10 + 1) * 10
    while m <= 85:
        out.append(m)
        m += 10
    return [x for x in out if x < 90]


def stato_al(eventi: Sequence[dict], minuto: int) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """(punteggio, rossi) con gli eventi fino al ``minuto`` compreso. Eventi:
    {minute, tipo: 'gol'|'rosso', lato: 'home'|'away'}."""
    sh = sa = rh = ra = 0
    for e in eventi:
        if int(e["minute"]) > int(minuto):
            continue
        if e["tipo"] == "gol":
            sh += e["lato"] == "home"
            sa += e["lato"] == "away"
        elif e["tipo"] == "rosso":
            rh += e["lato"] == "home"
            ra += e["lato"] == "away"
    return (sh, sa), (rh, ra)


def misura_partite(partite: Sequence[dict], *, giri: int, p=None) -> dict:
    """partite: [{id, league_id, lambdas, finale, eventi}] (solo quelle con rosso)."""
    if p is None:
        from Betfair.omega import omega_proposte as OP
        p = OP.parametri_modello()
    primo, tutti = [], []
    for pt in partite:
        rossi = [e for e in pt["eventi"] if e["tipo"] == "rosso" and int(e["minute"]) < 90]
        if not rossi:
            continue
        m0 = min(int(e["minute"]) for e in rossi)
        for j, m in enumerate(punti_di_valutazione(pt["eventi"], m0)):
            sc, rs = stato_al(pt["eventi"], m)
            if sc[0] > pt["finale"][0] or sc[1] > pt["finale"][1]:
                continue            # eventi incoerenti col finale: si salta il punto
            v = valuta_punto(minuto=float(m), punteggio=sc, rossi=rs,
                             lambdas=tuple(pt["lambdas"]), finale=tuple(pt["finale"]), p=p)
            if v is None:
                continue
            v.update({"id": pt["id"], "minuto": m, "rossi": rs})
            tutti.append(v)
            if j == 0:
                primo.append(v)
    out = {}
    for nome, rr in (("al_primo_rosso", primo), ("ogni_10_minuti", tutti)):
        if not rr:
            out[nome] = {"n_punti": 0, "n_partite": 0, "verdetto": C.NON_MISURABILE}
            continue
        blocco = {"n_punti": len(rr), "n_partite": len({r["id"] for r in rr})}
        for k in ("ll", "br"):
            d = [r[f"{k}_var"] - r[f"{k}_att"] for r in rr]
            ic = C.bootstrap_media(d, [r["id"] for r in rr], giri=giri)
            blocco[k] = {"attuale": sum(r[f"{k}_att"] for r in rr) / len(rr),
                         "variante": sum(r[f"{k}_var"] for r in rr) / len(rr),
                         "diff": ic, "verdetto": C.verdetto(ic)}
        out[nome] = blocco
    return out


# ---------------------------------------------------------------------------
# sorgenti
# ---------------------------------------------------------------------------
def partite_da_live_raw(live_raw: str) -> Tuple[List[dict], dict]:
    """Registrazioni con rosso: rossi/punteggi dall'IPS (`load_score_rows`),
    lambda dal pre_ko (`omega_model.lambdas_from_pre_ko`)."""
    from Betfair.omega import omega_model as M
    from Betfair.safe_strategy.tools import validate_opportunity as VO
    out, conta = [], {"registrazioni": 0, "con_rosso": 0, "con_rosso_e_pre_ko": 0}
    for eid in VO.available_events(live_raw):
        if not str(eid).isdigit():
            continue            # `_synth_*`: le sintetiche non si contano MAI come reali (par. 6.1)
        rows = VO.load_score_rows(live_raw, eid)
        if not rows:
            continue
        conta["registrazioni"] += 1
        ev: List[dict] = []
        prev = (0, 0, 0, 0)
        for r in rows:
            m = r.get("minute")
            if m is None:
                continue
            cur = (int(r["sh"]), int(r["sa"]), int(r.get("rh") or 0), int(r.get("ra") or 0))
            for i, (tipo, lato) in enumerate((("gol", "home"), ("gol", "away"),
                                              ("rosso", "home"), ("rosso", "away"))):
                for _ in range(max(0, cur[i] - prev[i])):
                    ev.append({"minute": int(m), "tipo": tipo, "lato": lato})
            prev = (max(prev[0], cur[0]), max(prev[1], cur[1]),
                    max(prev[2], cur[2]), max(prev[3], cur[3]))
        if not any(e["tipo"] == "rosso" for e in ev):
            continue
        conta["con_rosso"] += 1
        pre = VO.prematch_1x2(live_raw, eid)
        lam = M.lambdas_from_pre_ko(pre) if pre else None
        if not lam:
            continue
        conta["con_rosso_e_pre_ko"] += 1
        last = rows[-1]
        out.append({"id": eid, "league_id": None, "lambdas": [float(lam[0]), float(lam[1])],
                    "finale": [int(last["sh"]), int(last["sa"])], "eventi": ev})
    return out, conta


def _minuto_evento(e: dict) -> Optional[int]:
    try:
        m = int(e.get("minute"))
    except (TypeError, ValueError):
        return None
    return m


def partite_da_estrazione(ext: dict) -> Tuple[List[dict], dict]:
    """Dal file di `estrai_db.py o5` (chiavi vere: `matches`, `match_events`,
    `betfair_market_odds` Match Odds come nel campione M2)."""
    from Betfair.stream.backtest.tools.misura_punto8 import o1_catena_lambda as O1
    partite = {int(r["fixture_id"]): r for r in ext.get("esiti") or []}
    quote = {int(q["fixture_id"]): q for q in ext.get("quote") or []}
    fps = {int(r["fixture_id"]): r for r in ext.get("fixture_predictions") or []}
    per_fix: Dict[int, List[dict]] = {}
    for e in ext.get("eventi") or []:
        per_fix.setdefault(int(e["fixture_id"]), []).append(e)
    out, conta = [], {"partite_con_rosso": 0, "scartate_gol_incoerenti": 0,
                      "scartate_senza_lambda": 0}
    for fid, evs in per_fix.items():
        m = partite.get(fid)
        if not m or m.get("goals_home") is None:
            continue
        home, away = m.get("home_team_id"), m.get("away_team_id")
        ev = []
        for e in evs:
            mm = _minuto_evento(e)
            if mm is None:
                continue
            det = str(e.get("detail") or "")
            tipo = str(e.get("event_type") or "")
            lato = "home" if e.get("team_id") == home else "away" if e.get("team_id") == away else None
            if lato is None:
                continue
            if tipo == "Goal" and "missed" not in det.lower():
                if "own" in det.lower():
                    # API-Football: l'autogol porta il team_id di chi lo SUBISCE?
                    # Non lo assumiamo: la coerenza col finale lo decide sotto.
                    pass
                ev.append({"minute": mm, "tipo": "gol", "lato": lato, "det": det})
            elif tipo == "Card" and "red" in det.lower():
                ev.append({"minute": mm, "tipo": "rosso", "lato": lato})
        if not any(x["tipo"] == "rosso" for x in ev):
            continue
        conta["partite_con_rosso"] += 1
        gh = sum(1 for x in ev if x["tipo"] == "gol" and x["lato"] == "home")
        ga = sum(1 for x in ev if x["tipo"] == "gol" and x["lato"] == "away")
        if (gh, ga) != (int(m["goals_home"]), int(m["goals_away"])):
            conta["scartate_gol_incoerenti"] += 1
            continue
        q = quote.get(fid)
        fp = O1.riga_fp_postgrest(fps[fid]) if fid in fps else None
        la = O1.lambda_attuale(fid, m.get("league_id"), fp, O1.pre_ko_da_quote(q) if q else None)
        if la is None:
            conta["scartate_senza_lambda"] += 1
            continue
        out.append({"id": fid, "league_id": m.get("league_id"), "lambdas": [la[0], la[1]],
                    "finale": [int(m["goals_home"]), int(m["goals_away"])],
                    "eventi": sorted(ev, key=lambda x: x["minute"]),
                    "data": m.get("fixture_date")})
    return out, conta


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--live-raw", default=None, help="'auto' o una cartella")
    ap.add_argument("--estrazione", default=None, help="estrai_db.py o5 (match_events)")
    ap.add_argument("--campioni", nargs="*", default=[P.F_M2_CAMPIONE],
                    help="file con quote/esiti/fixture_predictions (M2 + estr_o1o6)")
    ap.add_argument("--giri", type=int, default=C.GIRI_MIN)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ris: Dict[str, Any] = {}
    if a.live_raw:
        live = P.live_raw(None if a.live_raw == "auto" else a.live_raw)
        partite, conta = partite_da_live_raw(live)
        ris["live_raw"] = {"conteggi": conta, "misura": misura_partite(partite, giri=a.giri),
                           "partite": [{"id": x["id"], "finale": x["finale"],
                                        "rossi": [e for e in x["eventi"] if e["tipo"] == "rosso"]}
                                       for x in partite]}
    if a.estrazione:
        with gzip.open(a.estrazione, "rt", encoding="utf-8") as fh:
            ext = {"eventi": json.load(fh).get("eventi") or []}
        for f in a.campioni:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                c = json.load(fh)
            for k in ("quote", "esiti", "fixture_predictions"):
                ext[k] = (ext.get(k) or []) + list(c.get(k) or [])
        partite, conta = partite_da_estrazione(ext)
        dopo = [x for x in partite if str(x.get("data") or "") >= "2026-06-30"]
        ris["estrazione"] = {"conteggi": conta,
                             "misura_tutte": misura_partite(partite, giri=a.giri),
                             "misura_dopo_29_06_fuori_dal_fit_dei_coefficienti":
                                 misura_partite(dopo, giri=a.giri)}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(ris, fh, indent=1, default=str)
    print(json.dumps(ris, indent=1, default=str)[:5000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
