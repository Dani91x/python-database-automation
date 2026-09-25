# -*- coding: utf-8 -*-
"""S2 - Safe, CALIBRAZIONE DELLE P D'USCITA. SOLO MISURA.

ATTUALE: l'uscita a modello di Safe (`bot_service._p_calcio`) decide con la P
GREZZA del book Poisson residuo (`OpportunityModel(params).book(...)`, nessuna
calibrazione applicata: `calibrate` si usa solo sulle opportunita').
VARIANTE: la stessa P passata per una isotonica (`calibration.fit_calibration`,
shrinkage + PAV) rifatta su TUTTE le registrazioni `_live_raw/` disponibili.

Metodo (funzioni di produzione importate, nessuna copia):
  * campioni = `validate_opportunity.calibration_samples` (un campione per minuto
    per ogni runner prezzabile di ogni mercato REGOLATO, esito dal WINNER dello
    stream), book = `OpportunityModel(calibration="off").book`, lambda =
    `validate_opportunity.event_lambdas` (pre_ko, altrimenti i default del bot);
  * SPLIT PER DATA: le registrazioni si ordinano per data del calcio d'inizio;
    la tabella si stima sulle prime (STIMA) e si misura sulle ultime (PROVA);
  * metrica: Brier e log-loss binari per famiglia di mercato e fascia di minuto;
    differenza APPAIATA (calibrata - grezza) con bootstrap a grappolo sulla
    PARTITA (i campioni della stessa partita sono correlati), 2.000+ giri.
  * a confronto anche la tabella IN PRODUZIONE (`opp_calibration.json`, 10/09):
    e' stata stimata su 32 partite che COMPRENDONO quelle di prova, quindi il suo
    numero e' ottimista (in campione) e lo si dichiara.

Le cache mancanti si costruiscono con `validate_opportunity.build_event_cache`
in una cartella LOCALE (``--cache-out``): la cartella delle cache del checkout
principale si legge soltanto.

Uso:
  python -m Betfair.stream.backtest.tools.misura_punto8.s2_calibrazione_uscita \
      --out <file.json> [--cache-out <dir>] [--quota-stima 0.6] [--giri 2000]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from Betfair.stream.backtest.tools.misura_punto8 import comune as C
from Betfair.stream.backtest.tools.misura_punto8 import percorsi as P

C.blinda_db()


def _vo():
    from Betfair.safe_strategy.tools import validate_opportunity as VO
    return VO


def raccogli_cache(live_raw: str, cache_letta: Optional[str], cache_out: str,
                   log=print) -> List[str]:
    """Il percorso di una cache per ogni registrazione utilizzabile: quella del
    checkout principale se esiste (sola lettura), altrimenti una costruita qui."""
    VO = _vo()
    out: List[str] = []
    for eid in VO.available_events(live_raw):
        if not str(eid).isdigit():
            continue            # `_synth_*`: le sintetiche non si contano MAI come reali (par. 6.1)
        if cache_letta:
            p = VO.cache_path(cache_letta, eid)
            if os.path.isfile(p):
                out.append(p)
                continue
        p = VO.build_event_cache(live_raw, eid, cache_dir=cache_out)
        if p:
            log(f"   cache costruita: {eid}")
            out.append(p)
    return out


def data_evento(cache: Dict[str, Any]) -> Optional[str]:
    snaps = cache.get("snapshots") or []
    if not snaps:
        return None
    ts = int(snaps[0]["ts"]) / 1000.0
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def campioni_per_evento(paths: Sequence[str]) -> List[dict]:
    """[{event_id, data, fonte_lambda, campioni}] con le funzioni di produzione."""
    VO = _vo()
    from Betfair.safe_strategy.opportunity import OpportunityModel
    model = OpportunityModel(calibration="off")
    ev: List[dict] = []
    for p in paths:
        cache = VO.load_event_cache(p)
        lam, src = VO.event_lambdas(cache)
        cs = VO.calibration_samples(cache, model=model, lambdas=lam)
        if not cs:
            continue
        ev.append({"event_id": str(cache.get("event_id")), "data": data_evento(cache),
                   "fonte_lambda": src, "campioni": cs})
    ev.sort(key=lambda e: (e["data"] or "", e["event_id"]))
    return ev


def dividi_per_data(eventi: Sequence[dict], quota_stima: float) -> Tuple[List[dict], List[dict], str]:
    """STIMA = le prime ``quota_stima`` registrazioni in ordine di data, PROVA il
    resto. Il taglio cade fra due GIORNI diversi (mai la stessa giornata nei due
    insiemi): si sposta in avanti finche' il giorno cambia."""
    n = len(eventi)
    k = max(1, min(n - 1, int(round(n * float(quota_stima)))))
    giorno = lambda e: (e["data"] or "")[:10]
    while k < n - 1 and giorno(eventi[k]) == giorno(eventi[k - 1]):
        k += 1
    return list(eventi[:k]), list(eventi[k:]), giorno(eventi[k]) if k < n else ""


def righe_valutate(prova: Sequence[dict], calibratori: Dict[str, Any]) -> List[dict]:
    from Betfair.safe_strategy.calibration import bucket_of
    righe = []
    for e in prova:
        for s in e["campioni"]:
            r = {"ev": e["event_id"], "fam": s.family, "fascia": bucket_of(s.minute),
                 "y": int(s.outcome), "p": {"grezza": float(s.p_model)}}
            for nome, cal in calibratori.items():
                r["p"][nome] = float(cal.apply(float(s.p_model), s.family, s.minute))
            righe.append(r)
    return righe


def origine_mobile(eventi: Sequence[dict], *, quota_minima: float = 0.4) -> List[dict]:
    """Validazione a ORIGINE MOBILE (forward chaining): per ogni giorno dopo il
    primo ``quota_minima`` di registrazioni, la tabella si stima su TUTTI i
    giorni precedenti e si prova su quel giorno. Ogni partita di prova e' vista
    da una tabella che non l'ha mai incontrata, e le partite di prova sono molte
    di piu' che con un taglio unico. Ritorna le righe gia' valutate."""
    from Betfair.safe_strategy.calibration import Calibrator, fit_calibration
    giorni = sorted({(e["data"] or "")[:10] for e in eventi})
    n_min = max(1, int(round(len(eventi) * quota_minima)))
    righe: List[dict] = []
    for g in giorni:
        prima = [e for e in eventi if (e["data"] or "")[:10] < g]
        oggi = [e for e in eventi if (e["data"] or "")[:10] == g]
        if len(prima) < n_min or not oggi:
            continue
        cal = Calibrator.from_dict(fit_calibration([s for e in prima for s in e["campioni"]],
                                                   n_events=len(prima)))
        for r in righe_valutate(oggi, {"isotonica_origine_mobile": cal}):
            r["giorno"] = g
            righe.append(r)
    return righe


def valuta(prova: Sequence[dict], calibratori: Dict[str, Any], *, giri: int,
           righe: Optional[List[dict]] = None) -> dict:
    """Per famiglia x fascia e in totale: Brier e log-loss della P grezza e di
    ogni calibratore, differenza appaiata con IC a grappolo sulla partita."""
    if righe is None:
        righe = righe_valutate(prova, calibratori)
    else:
        calibratori = {k: None for k in righe[0]["p"] if k != "grezza"} if righe else {}
    gruppi: Dict[str, List[dict]] = defaultdict(list)
    for r in righe:
        gruppi["TUTTE"].append(r)
        gruppi[f"{r['fam']}"].append(r)
        gruppi[f"{r['fam']}|{r['fascia']}"].append(r)
    out: Dict[str, Any] = {}
    for g, rr in sorted(gruppi.items()):
        blocco: Dict[str, Any] = {"n": len(rr), "n_partite": len({r["ev"] for r in rr}),
                                  "freq_reale": sum(r["y"] for r in rr) / len(rr)}
        for metr, fn in (("brier", C.brier_binario), ("logloss", C.log_loss_binario)):
            base = [fn(r["p"]["grezza"], r["y"]) for r in rr]
            blocco[f"{metr}_grezza"] = sum(base) / len(base)
            for nome in calibratori:
                val = [fn(r["p"][nome], r["y"]) for r in rr]
                d = [v - b for v, b in zip(val, base)]
                ic = C.bootstrap_media(d, [r["ev"] for r in rr], giri=giri)
                blocco[f"{metr}_{nome}"] = sum(val) / len(val)
                blocco[f"diff_{metr}_{nome}"] = ic
                blocco[f"verdetto_{metr}_{nome}"] = C.verdetto(ic)
        out[g] = blocco
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--live-raw", default=None)
    ap.add_argument("--cache", default=None, help="cache esistenti (sola lettura)")
    ap.add_argument("--cache-out", default=os.path.join("AUDIT_2026-09-25", "misura_punto8_dati", "cache_s2"))
    ap.add_argument("--quota-stima", type=float, default=0.6)
    ap.add_argument("--solo-pre-ko", action="store_true",
                    help="solo le registrazioni con lambda da pre_ko (niente default)")
    ap.add_argument("--giri", type=int, default=C.GIRI_MIN)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    from Betfair.safe_strategy.calibration import Calibrator, fit_calibration

    live = P.live_raw(a.live_raw)
    paths = raccogli_cache(live, P.cache_opportunita(a.cache), a.cache_out)
    eventi = campioni_per_evento(paths)
    if a.solo_pre_ko:
        eventi = [e for e in eventi if e["fonte_lambda"] == "pre_ko"]
    stima, prova, taglio = dividi_per_data(eventi, a.quota_stima)
    camp_stima = [s for e in stima for s in e["campioni"]]
    nuova = Calibrator.from_dict(fit_calibration(camp_stima, n_events=len(stima)))
    calibratori = {"isotonica_stima": nuova}
    if os.path.isfile(P.F_OPP_CAL):
        calibratori["produzione_10_09_IN_CAMPIONE"] = Calibrator.load(P.F_OPP_CAL)
    ris = valuta(prova, calibratori, giri=a.giri)
    righe_om = origine_mobile(eventi)
    ris_om = valuta([], {}, giri=a.giri, righe=righe_om) if righe_om else {}
    meta = {
        "origine_mobile_partite_di_prova": len({r["ev"] for r in righe_om}),
        "origine_mobile_giorni": sorted({r["giorno"] for r in righe_om}),
        "registrazioni_con_campioni": len(eventi),
        "stima": [(e["event_id"], e["data"], e["fonte_lambda"]) for e in stima],
        "prova": [(e["event_id"], e["data"], e["fonte_lambda"]) for e in prova],
        "taglio_prima_data_di_prova": taglio,
        "campioni_stima": len(camp_stima),
        "campioni_prova": sum(len(e["campioni"]) for e in prova),
        "fonti_lambda": {k: sum(1 for e in eventi if e["fonte_lambda"] == k)
                         for k in ("pre_ko", "default")},
        "solo_pre_ko": bool(a.solo_pre_ko), "giri": a.giri,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "risultati_taglio_unico": ris,
                   "risultati_origine_mobile": ris_om}, fh, indent=1, default=str)
    print(json.dumps({k: v for k, v in meta.items() if k not in ("stima", "prova")},
                     indent=1, default=str))
    print("TAGLIO UNICO:", json.dumps(ris.get("TUTTE", {}), indent=1, default=str))
    print("ORIGINE MOBILE:", json.dumps(ris_om.get("TUTTE", {}), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
