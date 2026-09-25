# -*- coding: utf-8 -*-
"""O1 - Omega, ORDINE DELLA CATENA DELLE LAMBDA pre-partita. SOLO MISURA.

ATTUALE (codice di produzione, `omega_service._prematch_lambdas`):
    1. fixture abbinata (`stream.db.get_fixture_prematch_lambdas`:
       tactical_engine_json, poi db_json_analisi.inputs)
    2. lambda salvate sull'evento  3. quote 1X2 pre_ko  4. ... ripieghi live
VARIANTE (proposta O1 dell'audit del 24/09):
    quote pre_ko devigate PRIMA (`omega_model.lambdas_from_pre_ko`); la fixture
    solo se le quote mancano (poi il resto della catena, identica).

Le due braccia si calcolano con le FUNZIONI VERE (importate, non ricopiate):
il braccio attuale chiama proprio `omega_service._prematch_lambdas` con un DB
finto che ha le chiavi del vero (`get_event` -> fixture_id/league_id;
`fixture_predictions` -> tactical_engine_json / db_json_analisi.inputs).

Metrica: log-loss e Brier del RISULTATO ESATTO finale (FT) e del primo tempo (HT)
con il modello V3 di produzione (`omega_v3.griglia_finale`, parametri del banco
del 16/09 letti da `omega_proposte.parametri_modello`) al minuto 0, e per
confronto con M2 anche con la griglia v2 (`omega_model.residual_grid`, cv 0,30).
IC: bootstrap a grappolo 2.000+ giri sulla PARTITA e, a parte, sulla LEGA.

Dati (sola lettura):
  * il campione M2 (`Betfair/omega/data/m2_campione_2026-09-17.json.gz`: quote
    Betfair Match Odds pre-match 24/06-11/09, esiti, fixture_predictions);
  * l'ESTENSIONE 17/09 -> oggi, se il coordinatore ha lanciato
    `estrai_db.py o1` (stesso formato: chiavi `quote`, `esiti`, `fixture_predictions`).

Uso:
  python -m Betfair.stream.backtest.tools.misura_punto8.o1_catena_lambda \
      [--estensione <file.json.gz>] [--live-raw <dir>] [--giri 2000] --out <file.json>
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from Betfair.stream.backtest.tools.misura_punto8 import comune as C
from Betfair.stream.backtest.tools.misura_punto8 import percorsi as P

C.blinda_db()

SPLIT_M2 = "2026-07-25"          # lo split temporale di M2 (stima prima / prova dopo)
INIZIO_ESTENSIONE = "2026-09-17"
CV_V2 = 0.30                     # `model_lambda_cv` di produzione (omega_config)


# ---------------------------------------------------------------------------
# il DB finto con le CHIAVI DEL VERO
# ---------------------------------------------------------------------------
class _Risposta:
    def __init__(self, data: List[dict]) -> None:
        self.data = data


class _Query:
    """Imita la catena PostgREST usata da `get_fixture_prematch_lambdas`:
    table(...).select(...).eq("fixture_id", x).limit(1).execute()."""

    def __init__(self, righe: Dict[int, dict]) -> None:
        self._righe = righe
        self._fid: Optional[int] = None

    def select(self, *_a: Any, **_k: Any) -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        if col != "fixture_id":
            raise AssertionError(f"filtro inatteso {col}")
        self._fid = int(val)
        return self

    def limit(self, _n: int) -> "_Query":
        return self

    def execute(self) -> _Risposta:
        r = self._righe.get(int(self._fid)) if self._fid is not None else None
        return _Risposta([r] if r else [])


class SupabaseFinto:
    def __init__(self, righe_fp: Dict[int, dict]) -> None:
        self._righe = righe_fp

    def table(self, nome: str) -> _Query:
        if nome != "fixture_predictions":
            raise AssertionError(f"tabella inattesa {nome}")
        return _Query(self._righe)


class OmegaDbFinto:
    """Il minimo del `OmegaDb` che `_prematch_lambdas` tocca in pre-partita.
    `get_event` porta le colonne vere di `omega_events` (fixture_id, league_id,
    model); nessuna lambda salvata (partita mai vista dal bot)."""

    def __init__(self, eventi: Dict[str, dict]) -> None:
        self._eventi = eventi
        self.salvati: List[Tuple[str, dict]] = []

    def get_event(self, event_id: str) -> Optional[dict]:
        return self._eventi.get(str(event_id))

    def save_event_model(self, event_id: str, model: dict) -> None:
        self.salvati.append((event_id, model))

    def log(self, *_a: Any, **_k: Any) -> None:
        return None


def riga_fp_postgrest(fp: dict) -> dict:
    """Dalla riga APPIATTITA del campione M2 (select con alias lh/la/tlh/tla,
    `m2_pesi.SEL_FP`) alla riga come la restituisce PostgREST alla produzione
    (`tactical_engine_json` e `db_json_analisi` sono JSONB -> dict)."""
    out: Dict[str, Any] = {"league_id": fp.get("league_id")}
    if fp.get("tlh") is not None or fp.get("tla") is not None:
        out["tactical_engine_json"] = {"lambda_home": fp.get("tlh"), "lambda_away": fp.get("tla")}
    else:
        out["tactical_engine_json"] = None
    if fp.get("lh") is not None or fp.get("la") is not None:
        out["db_json_analisi"] = {"inputs": {"lambda_home": fp.get("lh"), "lambda_away": fp.get("la")}}
    else:
        out["db_json_analisi"] = None
    return out


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 1.0 else None


def pre_ko_da_quote(q: dict) -> Optional[dict]:
    """Il `pre_ko` come lo congela lo scanner: prezzi BACK 1X2 (home/draw/away)."""
    pre = {"home": _f(q.get("back_home")), "draw": _f(q.get("back_draw")),
           "away": _f(q.get("back_away"))}
    return pre if all(v is not None for v in pre.values()) else None


# ---------------------------------------------------------------------------
# le due braccia, con le funzioni di PRODUZIONE
# ---------------------------------------------------------------------------
def _moduli():
    import Betfair.stream.db as SDB
    from Betfair.omega import omega_model as M
    from Betfair.omega import omega_service as OS
    return SDB, M, OS


def lambda_attuale(fid: int, league_id: Any, fp_postgrest: Optional[dict],
                   pre_ko: Optional[dict]) -> Optional[Tuple[float, float, str]]:
    """La catena di PRODUZIONE, chiamata davvero (`omega_service._prematch_lambdas`)."""
    SDB, _M, OS = _moduli()
    righe = {int(fid): fp_postgrest} if fp_postgrest else {}
    vecchio = SDB.get_supabase_client
    SDB.get_supabase_client = lambda: SupabaseFinto(righe)   # type: ignore[assignment]
    try:
        eid = f"m8-{fid}"
        OS._LAMBDA_CACHE.pop(eid, None)
        db = OmegaDbFinto({eid: {"event_id": eid, "fixture_id": int(fid),
                                 "league_id": league_id, "model": None}})
        # 25/09 sera: in produzione O1 e' ACCESO di default (ordine dell'utente);
        # il braccio ATTUALE della misura resta la catena di PRIMA (fixture in
        # testa), dichiarata esplicitamente, cosi' la misura e' riproducibile
        out = OS._prematch_lambdas(db, eid, {"pre_ko": pre_ko} if pre_ko else {},
                                   params={"lambda_quote_prima": False})
        OS._LAMBDA_CACHE.pop(eid, None)
    finally:
        SDB.get_supabase_client = vecchio   # type: ignore[assignment]
    if out is None:
        return None
    return float(out[0]), float(out[1]), str(out[3])


def lambda_variante(fid: int, league_id: Any, fp_postgrest: Optional[dict],
                    pre_ko: Optional[dict]) -> Optional[Tuple[float, float, str]]:
    """VARIANTE O1: quote pre_ko devigate PRIMA; se mancano, la catena attuale."""
    _SDB, M, _OS = _moduli()
    lam = M.lambdas_from_pre_ko(pre_ko) if pre_ko else None
    if lam:
        return float(lam[0]), float(lam[1]), "pre_ko_odds"
    return lambda_attuale(fid, league_id, fp_postgrest, None)


# ---------------------------------------------------------------------------
# metriche per partita
# ---------------------------------------------------------------------------
def _parametri_v3():
    from Betfair.omega import omega_proposte as OP
    return OP.parametri_modello()


def valuta_v3(lh: float, la: float, esito: dict, p=None) -> Optional[dict]:
    """log-loss/Brier CS finale e HT col modello V3 di produzione al minuto 0."""
    from Betfair.omega import omega_v3 as V3
    p = p or _parametri_v3()
    gh, ga = esito.get("goals_home"), esito.get("goals_away")
    if gh is None or ga is None:
        return None
    ft = V3.griglia_finale(minuto=0.0, punteggio=(0, 0), periodo=V3.PERIODO_FT, p=p,
                           lambdas=(lh, la))
    if not ft:
        return None
    cella = (int(gh), int(ga))
    out = {"ll_ft": C.log_loss(ft.get(cella, 0.0)), "brier_ft": C.brier_multiclasse(ft, cella),
           "p_ft": ft.get(cella, 0.0)}
    hh, ha = esito.get("halftime_home"), esito.get("halftime_away")
    if hh is not None and ha is not None:
        ht = V3.griglia_finale(minuto=0.0, punteggio=(0, 0), periodo=V3.PERIODO_HT, p=p,
                               lambdas=(lh, la))
        if ht:
            c2 = (int(hh), int(ha))
            out["ll_ht"] = C.log_loss(ht.get(c2, 0.0))
            out["brier_ht"] = C.brier_multiclasse(ht, c2)
    return out


def valuta_v2(lh: float, la: float, esito: dict) -> Optional[dict]:
    """La stessa misura con la griglia v2 (`omega_model.residual_grid`, cv 0,30):
    e' la metrica di M2, per confrontare i numeri di oggi con quelli del 17/09."""
    from Betfair.omega import omega_model as M
    gh, ga = esito.get("goals_home"), esito.get("goals_away")
    if gh is None or ga is None:
        return None
    ft = M.residual_grid(lh, la, M.DEFAULT_RHO, 8, dixon_coles=True, cv=CV_V2)
    cella = (min(8, int(gh)), min(8, int(ga)))
    out = {"ll_ft_v2": C.log_loss(ft.get(cella, 0.0))}
    hh, ha = esito.get("halftime_home"), esito.get("halftime_away")
    if hh is not None and ha is not None:
        q = M.ht_residual_share(0)
        ht = M.residual_grid(lh * q, la * q, M.DEFAULT_RHO, 6, dixon_coles=True, cv=CV_V2)
        out["ll_ht_v2"] = C.log_loss(ht.get((min(6, int(hh)), min(6, int(ha))), 0.0))
    return out


# ---------------------------------------------------------------------------
# campione
# ---------------------------------------------------------------------------
def _carica(path: str) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def righe_da_campione(camp: dict, *, etichetta_fn) -> List[dict]:
    quote = {int(q["fixture_id"]): q for q in camp.get("quote") or []}
    esiti = {int(r["fixture_id"]): r for r in camp.get("esiti") or []}
    fps = {int(r["fixture_id"]): r for r in camp.get("fixture_predictions") or []}
    out = []
    for fid, q in sorted(quote.items()):
        es = esiti.get(fid)
        if not es or str(es.get("status_short") or "").upper() not in ("FT", "AET", "PEN"):
            continue
        if es.get("goals_home") is None or es.get("goals_away") is None:
            continue
        out.append({"fixture_id": fid, "run_date": str(q.get("run_date") or ""),
                    "league_id": es.get("league_id"), "esito": es,
                    "pre_ko": pre_ko_da_quote(q),
                    "fp": riga_fp_postgrest(fps[fid]) if fid in fps else None,
                    "insieme": etichetta_fn(str(q.get("run_date") or ""))})
    return out


def misura(righe: Sequence[dict], *, giri: int = C.GIRI_MIN, log=print) -> dict:
    p3 = _parametri_v3()
    per: List[dict] = []
    t0 = time.time()
    for i, r in enumerate(righe):
        a = lambda_attuale(r["fixture_id"], r["league_id"], r["fp"], r["pre_ko"])
        v = lambda_variante(r["fixture_id"], r["league_id"], r["fp"], r["pre_ko"])
        if a is None or v is None:
            continue
        ma, mv = valuta_v3(a[0], a[1], r["esito"], p3), valuta_v3(v[0], v[1], r["esito"], p3)
        if ma is None or mv is None:
            continue
        ma.update(valuta_v2(a[0], a[1], r["esito"]) or {})
        mv.update(valuta_v2(v[0], v[1], r["esito"]) or {})
        per.append({"fixture_id": r["fixture_id"], "league_id": r["league_id"],
                    "insieme": r["insieme"], "fonte_attuale": a[2], "fonte_variante": v[2],
                    "lam_attuale": [round(a[0], 4), round(a[1], 4)],
                    "lam_variante": [round(v[0], 4), round(v[1], 4)],
                    "attuale": ma, "variante": mv})
        if log and (i + 1) % 200 == 0:
            log(f"   {i + 1}/{len(righe)} partite ({time.time() - t0:.0f} s)")
    return {"per_partita": per, "sintesi": sintesi(per, giri=giri)}


METRICHE = ("ll_ft", "brier_ft", "ll_ht", "brier_ht", "ll_ft_v2", "ll_ht_v2")


def sintesi(per: Sequence[dict], *, giri: int = C.GIRI_MIN) -> dict:
    gruppi = {
        "m2_stima (<25/07, in campione per M2)": [x for x in per if x["insieme"] == "m2_stima"],
        "m2_prova (25/07-11/09)": [x for x in per if x["insieme"] == "m2_prova"],
        "estensione (>=17/09)": [x for x in per if x["insieme"] == "estensione"],
        "FUORI CAMPIONE (m2_prova + estensione)": [x for x in per if x["insieme"] in ("m2_prova", "estensione")],
        # la variante NON ha parametri stimati sui dati (e' un riordino della
        # catena): per lei nessuna partita e' "in campione". L'unico parametro
        # comune alle due braccia (il V3 del 16/09) e' stimato su transizioni
        # aggregate che coprono tutto il periodo allo stesso modo.
        "TUTTE (la variante non stima parametri)": list(per),
        "SOLO partite in cui la catena cambia": [x for x in per if x["lam_attuale"] != x["lam_variante"]],
    }
    out: Dict[str, Any] = {}
    for nome, g in gruppi.items():
        diversi = [x for x in g if x["lam_attuale"] != x["lam_variante"]]
        blocco: Dict[str, Any] = {"n": len(g), "n_catena_diversa": len(diversi),
                                  "fonti_attuale": _conta(x["fonte_attuale"] for x in g)}
        for k in METRICHE:
            coppie = [(x["variante"][k] - x["attuale"][k], x["fixture_id"], x["league_id"])
                      for x in g if k in x["variante"] and k in x["attuale"]]
            if not coppie:
                continue
            d = [c[0] for c in coppie]
            ic_p = C.bootstrap_media(d, [c[1] for c in coppie], giri=giri)
            ic_l = C.bootstrap_media(d, [c[2] for c in coppie], giri=giri, seme=C.SEME + 1)
            blocco[k] = {
                "attuale": _media(x["attuale"][k] for x in g if k in x["attuale"]),
                "variante": _media(x["variante"][k] for x in g if k in x["variante"]),
                "diff_ic_partita": ic_p, "diff_ic_lega": ic_l,
                "verdetto": C.verdetto(ic_p),
                "verdetto_lega": C.verdetto(ic_l)}
        out[nome] = blocco
    out["per_lega (partite in cui la catena cambia, n >= 20)"] = per_lega(per, giri=giri)
    return out


def per_lega(per: Sequence[dict], *, giri: int, n_min: int = 20) -> Dict[str, dict]:
    """Differenza log-loss FT per lega, solo dove la catena cambia davvero."""
    gr: Dict[Any, List[dict]] = {}
    for x in per:
        if x["lam_attuale"] != x["lam_variante"]:
            gr.setdefault(x["league_id"], []).append(x)
    out = {}
    for lega, g in sorted(gr.items(), key=lambda kv: -len(kv[1])):
        if len(g) < n_min:
            continue
        d = [x["variante"]["ll_ft"] - x["attuale"]["ll_ft"] for x in g]
        ic = C.bootstrap_media(d, [x["fixture_id"] for x in g], giri=giri)
        out[str(lega)] = {"n": len(g), "diff_ll_ft": ic, "verdetto": C.verdetto(ic)}
    return out


def _media(xs: Iterable[float]) -> Optional[float]:
    v = list(xs)
    return sum(v) / len(v) if v else None


def _conta(xs: Iterable[str]) -> Dict[str, int]:
    d: Dict[str, int] = {}
    for x in xs:
        d[x] = d.get(x, 0) + 1
    return d


def distribuzione_lambda_source(righe_ev: Sequence[dict]) -> dict:
    """Da dove sono venute DAVVERO le lambda di Omega in produzione: le righe di
    `omega_events` (colonna `model->>lambda_source`, alias `src` nell'estrazione).
    None = evento senza modello salvato (la fixture non si persiste: vedi
    `_prematch_lambdas`, persist solo per i ripieghi)."""
    conta: Dict[str, int] = {}
    for r in righe_ev:
        k = str(r.get("src")) if r.get("src") is not None else "nessun_modello_salvato"
        conta[k] = conta.get(k, 0) + 1
    tot = sum(conta.values())
    return {"eventi": tot, "per_fonte": dict(sorted(conta.items(), key=lambda kv: -kv[1])),
            "quote": {k: round(v / tot, 4) for k, v in conta.items()} if tot else {}}


def stato_iniziale_match_odds(path_raw: str, max_righe: int = 50_000) -> Optional[bool]:
    """``inPlay`` della PRIMA definizione MATCH_ODDS della registrazione: True
    vuol dire che il registratore e' partito a partita gia' iniziata (il pre-KO
    NON e' mai stato registrato, il che non dice nulla su cosa avesse lo scanner
    in produzione). None se il MATCH_ODDS non compare."""
    with open(path_raw, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh):
            if n >= max_righe:
                break
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            for mc in rec.get("mc") or []:
                md = mc.get("marketDefinition")
                if md is not None and str(md.get("marketType") or "") == "MATCH_ODDS":
                    return bool(md.get("inPlay"))
    return None


def quota_senza_pre_ko(live_raw: Optional[str]) -> dict:
    """Sulle registrazioni `_live_raw/`: quante NON hanno un Match Odds pre-KO
    leggibile (stessa lettura di `validate_opportunity.prematch_1x2`, che
    ricostruisce la ladder fino al primo tick in gioco come lo scanner), e fra
    queste quante sono semplicemente INIZIATE A PARTITA IN CORSO (difetto del
    registratore, non del mercato)."""
    if not live_raw or not os.path.isdir(live_raw):
        return {"errore": "cartella _live_raw non trovata"}
    from Betfair.safe_strategy.tools.validate_opportunity import prematch_1x2
    tot, senza, senza_raw, elenco, iniziate_in_gioco = 0, 0, 0, [], []
    for d in sorted(os.listdir(live_raw)):
        if d.startswith("_") or not d.isdigit():
            continue
        tot += 1
        raw = os.path.join(live_raw, d, f"{d}.raw.jsonl")
        if not os.path.isfile(raw):
            senza_raw += 1
            continue
        if prematch_1x2(live_raw, d) is None:
            senza += 1
            elenco.append(d)
            if stato_iniziale_match_odds(raw) is not False:
                iniziate_in_gioco.append(d)
    con_raw = tot - senza_raw
    vere = senza - len(iniziate_in_gioco)
    return {"registrazioni": tot, "senza_raw": senza_raw, "con_raw": con_raw,
            "senza_pre_ko": senza,
            "di_cui_registrazione_iniziata_in_gioco_o_senza_MO": len(iniziate_in_gioco),
            "senza_pre_ko_con_registrazione_pre_ko": vere,
            "quota_senza_pre_ko_su_con_raw": (senza / con_raw) if con_raw else None,
            "eventi_senza_pre_ko": elenco, "eventi_iniziati_in_gioco": iniziate_in_gioco}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--campione", default=P.F_M2_CAMPIONE)
    ap.add_argument("--estensione", default=None, help="file di estrai_db.py o1 (json.gz)")
    ap.add_argument("--live-raw", default=None)
    ap.add_argument("--giri", type=int, default=C.GIRI_MIN)
    ap.add_argument("--limite", type=int, default=0, help="solo le prime N partite (prova)")
    ap.add_argument("--solo-lambda-source", default=None,
                    help="scrive solo la distribuzione di omega_events.lambda_source dell'estrazione")
    ap.add_argument("--rifai-sintesi", default=None,
                    help="ricalcola SOLO la sintesi da un'uscita precedente (per_partita)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.solo_lambda_source:
        d = distribuzione_lambda_source(_carica(a.solo_lambda_source).get(
            "omega_events_lambda_source") or [])
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
        print(json.dumps(d, indent=1))
        return 0
    if a.rifai_sintesi:
        with open(a.rifai_sintesi, "r", encoding="utf-8") as fh:
            res = json.load(fh)
        res["sintesi"] = sintesi(res["per_partita"], giri=a.giri)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, default=str)
        print(json.dumps(res["sintesi"], indent=1, default=str)[:3000])
        return 0

    def etichetta_m2(rd: str) -> str:
        return "m2_stima" if rd < SPLIT_M2 else "m2_prova"

    righe = righe_da_campione(_carica(a.campione), etichetta_fn=etichetta_m2)
    if a.estensione:
        ext = righe_da_campione(_carica(a.estensione), etichetta_fn=lambda rd: "estensione")
        ext = [r for r in ext if r["run_date"] >= INIZIO_ESTENSIONE]
        viste = {r["fixture_id"] for r in righe}
        righe += [r for r in ext if r["fixture_id"] not in viste]
    if a.limite:
        righe = righe[: a.limite]
    print(f"O1: {len(righe)} partite con esito ({sum(1 for r in righe if r['pre_ko'])} con pre_ko)")
    res = misura(righe, giri=a.giri)
    res["senza_pre_ko"] = quota_senza_pre_ko(P.live_raw(a.live_raw))
    res["meta"] = {"campione": a.campione, "estensione": a.estensione, "giri": a.giri,
                   "split_m2": SPLIT_M2, "inizio_estensione": INIZIO_ESTENSIONE,
                   "parametri_v3": P.F_PARAMETRI_V3}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(json.dumps(res["sintesi"], indent=1, default=str)[:6000])
    print(json.dumps(res["senza_pre_ko"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
