"""banco.py - CLI del banco di validazione fuori campione dell'Atlante Hazard.

    python -m Betfair.stream.scalper.validazione_hazard.banco --da-cache [--fase validazione|test|tutto]

Walk-forward (nessuna scelta sul test):
  VALIDAZIONE  addestra <= 2023, valuta 2024: si scelgono le varianti A (catena
               greedy: una variante entra SOLO se migliora la log-loss con IC 95%
               per partita che esclude lo zero), i parametri della forza
               pre-partita e il numero di giri di B1 (arresto anticipato).
  TEST         addestra <= 2024 con le scelte congelate, valuta 2025 UNA volta.
Legge SOLO la cache (``raccogli``); nessuna rete, nessuna scrittura sul DB.
Scrive ``risultati_<fase>.json`` e ``tabelle_<fase>.md`` nella cartella del referto.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# SANDBOX: questo processo non deve MAI poter parlare col DB vero (i moduli
# del motore live importano configurazioni che potrebbero leggere l'env)
os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"

import numpy as np  # noqa: E402

from Betfair.stream.scalper.validazione_hazard import candidati as CA  # noqa: E402
from Betfair.stream.scalper.validazione_hazard import metriche as ME  # noqa: E402
from Betfair.stream.scalper.validazione_hazard.dati import (costruisci_partite, recupero_registrato,  # noqa: E402
                                                            stagioni_valide)
from Betfair.stream.scalper.validazione_hazard.forza import lambda_prepartita  # noqa: E402
from Betfair.stream.scalper.validazione_hazard.produzione import LettoreCache, atlante_a0, predici_a0  # noqa: E402
from Betfair.stream.scalper.validazione_hazard.raccogli import CACHE_DEFAULT, carica  # noqa: E402
from Betfair.stream.scalper.validazione_hazard.stati import tabella_stati  # noqa: E402

OUT_DEFAULT = os.path.join("AUDIT_2026-09-25", "validazione_hazard")
SEGMENTI = ("tutti", "regolare_0_74", "tardo_75_89", "recupero_2T", "recupero_1T")


def log(*a: Any) -> None:
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# dati
# ---------------------------------------------------------------------------
FUMO = {"attivo": False}      # --fumo: prova veloce di tutto il percorso (1 partita su 10, B1 minimo)


def carica_tutto(cache: str) -> Dict[str, Any]:
    matches, eventi, cov, pred = [], [], [], []
    for suff in ("", "_supp"):
        if not os.path.exists(os.path.join(cache, f"matches{suff}.json.gz")):
            continue
        matches += carica(os.path.join(cache, f"matches{suff}.json.gz"))
        eventi += carica(os.path.join(cache, f"eventi{suff}.json.gz"))
        cov += carica(os.path.join(cache, f"coverage{suff}.json.gz"))
        pred += carica(os.path.join(cache, f"predizioni{suff}.json.gz"))
    partite, res = costruisci_partite(matches, eventi, cov)
    if FUMO["attivo"]:
        partite = [p for p in partite if p.fixture_id % 10 == 0]
    S = tabella_stati(partite)
    lam_real = {}
    for r in pred:
        try:
            lh, la = float(r["lh"]), float(r["la"])
        except (TypeError, ValueError, KeyError):
            continue
        if lh > 0 and la > 0:
            lam_real[int(r["fixture_id"])] = (lh, la)
    return {"matches": matches, "eventi": eventi, "coverage": cov, "partite": partite,
            "resoconto": res, "S": S, "lam_real": lam_real}


def scegli_forza(partite: List[Any], ultima_stagione: int) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
    """eta e rientro del Poisson-Elo: log-verosimiglianza media delle partite
    2018..ultima_stagione (le prime due stagioni sono rodaggio)."""
    griglia = []
    for eta in (0.005, 0.01, 0.015, 0.02, 0.035, 0.05):
        for rientro in (0.7, 0.8, 0.9, 1.0):
            lam = lambda_prepartita(partite, eta=eta, rientro=rientro)
            ll = [lam[p.fixture_id][2] for p in partite if 2018 <= p.season <= ultima_stagione]
            griglia.append({"eta": eta, "rientro": rientro, "ll_media": float(np.mean(ll))})
    best = max(griglia, key=lambda g: g["ll_media"])
    return {"eta": best["eta"], "rientro": best["rientro"]}, griglia


def vettori_lambda(partite: List[Any], S: Dict[str, np.ndarray], lam: Dict[int, Tuple[float, ...]]
                   ) -> Tuple[np.ndarray, np.ndarray]:
    lh = np.array([lam[p.fixture_id][0] for p in partite])
    la = np.array([lam[p.fixture_id][1] for p in partite])
    return lh[S["mi"]], la[S["mi"]]


def segmenti(S: Dict[str, np.ndarray], idx: np.ndarray) -> Dict[str, np.ndarray]:
    stop, tempo, m = S["stop"][idx], S["tempo"][idx], S["m_live"][idx]
    return {"tutti": np.ones(idx.size, dtype=bool),
            "regolare_0_74": (stop == 0) & (m < 75),
            "tardo_75_89": (stop == 0) & (m >= 75),
            "recupero_2T": (stop == 1) & (tempo == 2),
            "recupero_1T": (stop == 1) & (tempo == 1)}


# ---------------------------------------------------------------------------
# valutazione
# ---------------------------------------------------------------------------
def valuta(pred: Dict[str, Dict[str, np.ndarray]], S: Dict[str, np.ndarray], idx: np.ndarray,
           rif: str, b_boot: int = 1000, b_auc: int = 200, con_auc: bool = True,
           auc_ic_per: Optional[set] = None) -> Dict[str, Any]:
    """Metriche per candidato e segmento + differenze contro ``rif`` con IC per partita."""
    mi_g = S["mi"][idx]
    u, mi = np.unique(mi_g, return_inverse=True)
    n_p = u.size
    seg = segmenti(S, idx)
    pesi = ME.ricampioni(n_p, b_boot)
    out: Dict[str, Any] = {"n_partite": int(n_p), "n_stati": int(idx.size), "candidati": {}, "differenze": {}}
    for nome, pr in pred.items():
        riga: Dict[str, Any] = {}
        for k in (2, 3):
            y = S[f"y{k}"][idx]
            p = pr[f"p{k}"]
            ll = ME.logloss_vett(p, y)
            br = ME.brier_vett(p, y)
            for sn, sm in seg.items():
                if not sm.any():
                    continue
                cnt = ME.per_partita(sm.astype(float), mi, n_p)
                l_s = ME.ic_media(ME.per_partita(ll * sm, mi, n_p), cnt, pesi)
                b_s = ME.ic_media(ME.per_partita(br * sm, mi, n_p), cnt, pesi)
                tab = ME.calibrazione(p[sm], y[sm])
                r = {"n": int(sm.sum()), "freq": float(y[sm].mean()), "p_media": float(np.mean(p[sm])),
                     "logloss": l_s, "brier": b_s, "ece": ME.errore_calibrazione(tab)}
                if con_auc and sn in ("tutti", "tardo_75_89", "recupero_2T"):
                    usa_ic = b_auc and (auc_ic_per is None or nome in auc_ic_per)
                    r["auc"] = (ME.ic_auc(p[sm], y[sm], mi[sm], n_p, b=b_auc) if usa_ic
                                else ME.auc(p[sm], y[sm]))
                riga[f"{sn}|{k}"] = r
        out["candidati"][nome] = riga
    # differenze contro il riferimento (log-loss e Brier; negativo = meglio del riferimento)
    for nome, pr in pred.items():
        if nome == rif:
            continue
        d: Dict[str, Any] = {}
        for k in (2, 3):
            y = S[f"y{k}"][idx]
            dl = ME.logloss_vett(pr[f"p{k}"], y) - ME.logloss_vett(pred[rif][f"p{k}"], y)
            db = ME.brier_vett(pr[f"p{k}"], y) - ME.brier_vett(pred[rif][f"p{k}"], y)
            for sn, sm in seg.items():
                if not sm.any():
                    continue
                cnt = ME.per_partita(sm.astype(float), mi, n_p)
                est_l = ME.ic_media(ME.per_partita(dl * sm, mi, n_p), cnt, pesi)
                est_b = ME.ic_media(ME.per_partita(db * sm, mi, n_p), cnt, pesi)
                d[f"{sn}|{k}"] = {"d_logloss": est_l, "d_brier": est_b,
                                  "vince_logloss": est_l[2] < 0, "perde_logloss": est_l[1] > 0}
        out["differenze"][f"{nome}-vs-{rif}"] = d
    return out


def differenze_auc(pred, S, idx, coppie, b: int = 100) -> Dict[str, Any]:
    """AUC(a) - AUC(b) con IC per partita, 3' e 2', segmenti tutti / tardo / recupero 2T."""
    u, mi = np.unique(S["mi"][idx], return_inverse=True)
    seg = segmenti(S, idx)
    out: Dict[str, Any] = {}
    for a, bb in coppie:
        for k in (2, 3):
            for sn in ("tutti", "tardo_75_89", "recupero_2T"):
                sm = seg[sn]
                out[f"{a}-vs-{bb}|{sn}|{k}"] = ME.ic_differenza_auc(
                    pred[a][f"p{k}"][sm], pred[bb][f"p{k}"][sm], S[f"y{k}"][idx][sm], mi[sm], u.size, b=b)
    return out


def ll_totale(pr: Dict[str, np.ndarray], S: Dict[str, np.ndarray], idx: np.ndarray,
              maschera: Optional[np.ndarray] = None) -> float:
    m = np.ones(idx.size, dtype=bool) if maschera is None else maschera
    return float(sum(ME.logloss_vett(pr[f"p{k}"][m], S[f"y{k}"][idx][m]).mean() for k in (2, 3)))


def delta_ic(pa: Dict[str, np.ndarray], pb: Dict[str, np.ndarray], S: Dict[str, np.ndarray],
             idx: np.ndarray, maschera: np.ndarray, b: int = 1000) -> Tuple[float, float, float]:
    """(log-loss 2'+3' di a) - (di b) per stato, IC per partita."""
    mi_g = S["mi"][idx]
    u, mi = np.unique(mi_g, return_inverse=True)
    d = np.zeros(idx.size)
    for k in (2, 3):
        y = S[f"y{k}"][idx]
        d += ME.logloss_vett(pa[f"p{k}"], y) - ME.logloss_vett(pb[f"p{k}"], y)
    d = d * maschera
    cnt = ME.per_partita(maschera.astype(float), mi, u.size)
    return ME.ic_media(ME.per_partita(d, mi, u.size), cnt, ME.ricampioni(u.size, b))


# ---------------------------------------------------------------------------
# fasi
# ---------------------------------------------------------------------------
def indici(S: Dict[str, np.ndarray], train_max: int, eval_season: int) -> Tuple[np.ndarray, np.ndarray]:
    return (np.flatnonzero(S["stagione"] <= train_max), np.flatnonzero(S["stagione"] == eval_season))


def prepara_a0(D: Dict[str, Any], train_max: int) -> Dict[str, Any]:
    val = stagioni_valide(D["coverage"])
    leghe = sorted({p.league_id for p in D["partite"]})
    lettore = LettoreCache(D["matches"], D["eventi"])
    spl = {l: [s for s in val.get(l, []) if 2016 <= s <= train_max] for l in leghe}
    spl = {l: s for l, s in spl.items() if s}
    atlas, stati = atlante_a0(lettore, spl)
    return atlas


def fase_validazione(D: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    S, partite = D["S"], D["partite"]
    tr, ev = indici(S, 2023, 2024)
    leghe = np.array(sorted({p.league_id for p in partite}))
    ris: Dict[str, Any] = {"fase": "validazione", "addestramento": "<=2023", "valutazione": 2024}
    t0 = time.time()
    forza_par, griglia = scegli_forza(partite, 2023)
    ris["forza"] = {"scelta": forza_par, "griglia": griglia}
    lam = lambda_prepartita(partite, **forza_par)
    lam_h, lam_a = vettori_lambda(partite, S, lam)
    lam_tot = lam_h + lam_a
    gol_tot = np.array([float(sum(p.ft)) for p in partite])[S["mi"]]
    log("forza scelta", forza_par, round(time.time() - t0, 1), "s")
    pred: Dict[str, Dict[str, np.ndarray]] = {}
    atlas = prepara_a0(D, 2023)
    pred["A0"] = predici_a0(atlas, S, ev, partite)
    log("A0 fatto")
    reg = S["stop"][ev] == 0
    # catena greedy
    passi: List[Dict[str, Any]] = []
    corrente = CA.ConfA(nome="A1")
    mod = CA.addestra_a(corrente, S, tr, leghe, lam_tot, 2024, gol_tot)
    pred["A1"] = CA.prevedi_a(mod, S, ev, lam_tot)
    pred[_nome_pred(corrente)] = pred["A1"]
    ris["A1_info"] = _info(mod)
    passi.append({"passo": "A0->A1", "delta_tutti": delta_ic(pred["A1"], pred["A0"], S, ev, np.ones(ev.size, bool)),
                  "delta_regolari": delta_ic(pred["A1"], pred["A0"], S, ev, reg)})
    prove = [("A2", [dict(emivita=h) for h in (2.0, 3.0, 5.0)]),
             ("A3", [dict(stato=True)]),
             ("A4", [dict(rossi=True)]),
             ("A5", [dict(forza=True)]),
             ("A6", [dict(k="mdm")])]
    for tag, opzioni in prove:
        migliore = None
        esiti = []
        for opz in opzioni:
            conf = CA.variante(corrente, nome=f"{corrente.nome}+{tag}{opz}", **opz)
            m2 = CA.addestra_a(conf, S, tr, leghe, lam_tot, 2024, gol_tot)
            p2 = CA.prevedi_a(m2, S, ev, lam_tot)
            dl = delta_ic(p2, pred[_nome_pred(corrente)], S, ev, np.ones(ev.size, bool))
            esiti.append({"opzione": opz, "delta_ll_vs_corrente": dl, "info": _info(m2)})
            pred[f"{tag}{_etichetta(opz)}"] = p2
            if dl[2] < 0 and (migliore is None or dl[0] < migliore[1][0]):
                migliore = (conf, dl, opz)
        entra = migliore is not None
        passi.append({"passo": tag, "esiti": esiti, "entra": entra,
                      "scelta": migliore[2] if entra else None})
        if entra:
            corrente = migliore[0]
            pred[_nome_pred(corrente)] = pred[f"{tag}{_etichetta(migliore[2])}"]
        log(tag, "entra" if entra else "resta fuori", [e["delta_ll_vs_corrente"] for e in esiti])
    ris["catena"] = passi
    ris["A_star"] = {k: v for k, v in corrente.__dict__.items()}
    pred["A*"] = pred[_nome_pred(corrente)]
    # B1: arresto anticipato sulla validazione (sceglie il numero di giri)
    from Betfair.stream.scalper.validazione_hazard.modello_b1 import addestra_b1, importanza, prevedi_b1
    t0 = time.time()
    par_b1, zero_st = {}, False
    tar_path = os.path.join(out_dir, "taratura_b1.json")
    if os.path.exists(tar_path):          # taratura fatta in validazione (taratura_b1.py)
        with open(tar_path, encoding="utf-8") as fh:
            tar = json.load(fh)
        par_b1 = dict(tar[tar["scelta"]]["parametri"])
        zero_st = tar[tar["scelta"]].get("senza") == "stagione"
    b1 = addestra_b1(S, tr, lam_h, lam_a, n_round=(10 if FUMO["attivo"] else 3000), idx_val=ev, parametri=par_b1,
                     zero_stagione=zero_st)
    pred["B1"] = prevedi_b1(b1, S, ev, lam_h, lam_a)
    ris["B1"] = {"giri": b1["giri"], "secondi": round(time.time() - t0, 1), "importanza": importanza(b1),
                 "parametri": par_b1, "senza_stagione": zero_st}
    log("B1 fatto", b1["giri"], round(time.time() - t0, 1), "s")
    scelti = ["A0", "A1", "A*", "B1"] + [k for k in pred if k not in ("A0", "A1", "A*", "B1")
                                          and not k.startswith("catena:")]
    pred = {k: pred[k] for k in scelti if k in pred}
    ris["metriche"] = valuta(pred, S, ev, "A0", b_auc=0, con_auc=True)
    ris["ll_regolari"] = {k: ll_totale(v, S, ev, reg) for k, v in pred.items()}
    _scrivi(out_dir, "validazione", ris)
    return ris


def _etichetta(opz: Dict[str, Any]) -> str:
    return "".join(f"[{k}={v}]" for k, v in opz.items())


def _nome_pred(conf: CA.ConfA) -> str:
    return "catena:" + conf.nome


def _info(mod: CA.ModelloA) -> Dict[str, Any]:
    out = {}
    for k, v in mod.info.items():
        if isinstance(v, np.ndarray):
            continue
        out[k] = v
    if mod.beta:
        out["beta"] = mod.beta
    if mod.mult_rossi:
        out["mult_rossi"] = {k: v.tolist() for k, v in mod.mult_rossi.items()}
    return out


def fase_test(D: Dict[str, Any], out_dir: str, val: Dict[str, Any]) -> Dict[str, Any]:
    S, partite = D["S"], D["partite"]
    tr, ev = indici(S, 2024, 2025)
    leghe = np.array(sorted({p.league_id for p in partite}))
    ris: Dict[str, Any] = {"fase": "test", "addestramento": "<=2024", "valutazione": 2025}
    forza_par = val["forza"]["scelta"]
    lam = lambda_prepartita(partite, **forza_par)
    lam_h, lam_a = vettori_lambda(partite, S, lam)
    lam_tot = lam_h + lam_a
    gol_tot = np.array([float(sum(p.ft)) for p in partite])[S["mi"]]
    pred: Dict[str, Dict[str, np.ndarray]] = {}
    atlas = prepara_a0(D, 2024)
    pred["A0"] = predici_a0(atlas, S, ev, partite)
    pred["A0_squadre"] = predici_a0(atlas, S, ev, partite, squadre=True)
    pred["A0_1T_cumulato"] = predici_a0(atlas, S, ev, partite, convenzione_1t="cumulato")
    log("A0 fatto")
    base = CA.ConfA(nome="A1")
    confs = {"A1": base,
             "A1+A2": CA.variante(base, emivita=_emivita_scelta(val)),
             "A1+A3": CA.variante(base, stato=True),
             "A1+A4": CA.variante(base, rossi=True),
             "A1+A5": CA.variante(base, forza=True),
             "A1+A6": CA.variante(base, k="mdm")}
    stella = CA.ConfA(**val["A_star"])
    confs["A*"] = stella
    modelli = {}
    for nome, conf in confs.items():
        modelli[nome] = CA.addestra_a(conf, S, tr, leghe, lam_tot, 2025, gol_tot)
        pred[nome] = CA.prevedi_a(modelli[nome], S, ev, lam_tot)
        log(nome, "fatto")
    ris["info_A"] = {n: _info(m) for n, m in modelli.items()}
    # IL MODULO DI PRODUZIONE (atlante_v4, non collegato): stato grezzo per
    # stagione -> assembla_v4 -> consulta_atlante_v4 stato per stato. Deve dare
    # gli STESSI numeri di A* (parita' del modulo col candidato validato).
    t0 = time.time()
    pred["V4_modulo"], ris["V4_modulo"] = valuta_modulo_v4(partite, S, ev, lam_h, lam_a, modelli["A*"], 2024)
    for k in (2, 3):
        dmax = float(np.nanmax(np.abs(pred["V4_modulo"][f"p{k}"] - pred["A*"][f"p{k}"])))
        ris["V4_modulo"][f"max_diff_vs_A*_{k}"] = dmax
    log("V4 modulo fatto", ris["V4_modulo"], round(time.time() - t0, 1), "s")
    # DECISIONE DELL'UTENTE (25/09): in live il recupero e' la stima PER LEGA.
    # Prezzo del dato mancante: stessa previsione col recupero VERO (a posteriori)
    # e con la sola media condizionata per lega invece della distribuzione.
    d_vero = np.array([p.d2 if p.d2 is not None else 0 for p in partite])[S["mi"]]
    for nome in ("A1", "A*"):
        for modo in ("media", "oracolo"):
            pred[f"{nome}_recupero_{modo}"] = CA.prevedi_a(modelli[nome], S, ev, lam_tot, modo, d_vero)
    from Betfair.stream.scalper.validazione_hazard.modello_b1 import addestra_b1, importanza, prevedi_b1
    giri = val["B1"]["giri"]
    par_b1: Dict[str, Any] = {}
    zero_st = False
    tar_path = os.path.join(out_dir, "taratura_b1.json")
    if os.path.exists(tar_path):
        # iperparametri scelti in VALIDAZIONE (taratura_b1.py): giri e parametri
        with open(tar_path, encoding="utf-8") as fh:
            tar = json.load(fh)
        sc = tar[tar["scelta"]]
        par_b1 = dict(sc["parametri"])
        zero_st = sc.get("senza") == "stagione"
        giri = {str(k): v for k, v in sc["giri"].items()}
        ris["B1_taratura"] = {"scelta": tar["scelta"], "parametri": par_b1, "senza_stagione": zero_st}
    t0 = time.time()
    # giri scelti in validazione, riscalati sulla quantita' di dati (<=2024 vs <=2023)
    fatt = float(tr.size) / float(np.sum(S["stagione"] <= 2023))
    b1 = carica_o_addestra_b1(S, tr, lam_h, lam_a, giri, fatt, par_b1, zero_st, out_dir, ris)
    pred["B1"] = prevedi_b1(b1, S, ev, lam_h, lam_a)
    ris["B1"] = {"giri": {k: int(round(giri[str(k)] * fatt)) for k in (2, 3)}, "bag": 3,
                 "secondi_addestramento": round(time.time() - t0, 1), "importanza": importanza(b1),
                 "sd_media": {k: float(np.mean(pred["B1"][f"sd{k}"])) for k in (2, 3)}}
    log("B1 fatto", round(time.time() - t0, 1), "s")
    # --- INSIEMI DI VALUTAZIONE (25/09, reperto sui dati): nella stagione 2025
    # delle leghe europee i gol del recupero sono registrati SENZA minute_extra
    # (al 90'/45' regolare): la verita' vicino alla fine dei tempi e' falsata.
    #   pulito          blocchi (lega, mese) che registrano il recupero (>= 60%
    #                   dei gol di fine tempo con extra): insieme PRIMARIO;
    #   regolari_sicuri tutte le partite 2025, solo stati le cui finestre non
    #                   toccano la fine del tempo (t <= 41 in ogni tempo);
    #   intero          tutto il 2025 (tenuto per trasparenza: verita' falsata).
    reg_ok = recupero_registrato(D["matches"], D["eventi"])
    fx = np.array([p.fixture_id for p in partite])
    pulito = np.array([reg_ok.get(int(f), True) for f in fx])[S["mi"][ev]]
    sicuri = (S["stop"][ev] == 0) & (S["t"][ev] <= 41)
    ris["insiemi"] = {"pulito": {"stati": int(pulito.sum()),
                                 "partite": int(np.unique(S["mi"][ev][pulito]).size)},
                      "regolari_sicuri": {"stati": int(sicuri.sum())},
                      "intero": {"stati": int(ev.size), "partite": int(np.unique(S["mi"][ev]).size)}}
    salva_predizioni(out_dir, ev, pred)
    pp = _sotto(pred, pulito)
    evp = ev[pulito]
    ris["metriche"] = valuta(pp, S, evp, "A0", b_auc=100, auc_ic_per={"A0", "A*", "B1"})
    ris["auc_differenze"] = differenze_auc(pp, S, evp, [("A*", "A0"), ("B1", "A0"), ("B1", "A*")])
    ris["metriche_vs_Astar"] = {k: v for k, v in valuta({"A*": pp["A*"], "B1": pp["B1"]}, S, evp, "A*",
                                                          con_auc=False).items() if k == "differenze"}
    ris["calibrazione"] = calibrazioni(pp, S, evp, ["A0", "A1", "A*", "B1"])
    ris["metriche_regolari_sicuri"] = valuta(_sotto(pred, sicuri), S, ev[sicuri], "A0", con_auc=True, b_auc=0)
    ris["metriche_intero_verita_falsata"] = valuta(pred, S, ev, "A0", con_auc=False)
    ris["calibrazione_intero_verita_falsata"] = calibrazioni(pred, S, ev, ["A0", "A*"])
    # sottoinsieme con i lambda VERI del motore Poisson (quelli che Safe usa in live)
    ris["sottoinsieme_lambda_veri"] = sottoinsieme(D, S, ev, pred, b1, modelli, lam, lam_h, lam_a,
                                                   lam_tot, atlas, maschera=pulito)
    ris["sottoinsieme_lambda_veri_regolari_sicuri"] = sottoinsieme(D, S, ev, pred, b1, modelli, lam, lam_h,
                                                                   lam_a, lam_tot, atlas, maschera=sicuri)
    _scrivi(out_dir, "test", ris)
    return ris


def _sotto(pred: Dict[str, Dict[str, np.ndarray]], m: np.ndarray) -> Dict[str, Dict[str, np.ndarray]]:
    return {n: {k: v[m] for k, v in d.items() if isinstance(v, np.ndarray)} for n, d in pred.items()}


def salva_predizioni(out_dir: str, ev: np.ndarray, pred: Dict[str, Dict[str, np.ndarray]]) -> None:
    """Predizioni del test in cache (per rifare le metriche senza riaddestrare)."""
    cartella = os.path.join(out_dir, "cache")
    os.makedirs(cartella, exist_ok=True)
    arr = {"ev": ev}
    for n, d in pred.items():
        for k in ("p2", "p3", "sd2", "sd3"):
            if k in d:
                arr[f"{n}|{k}"] = np.asarray(d[k], dtype=float)
    np.savez_compressed(os.path.join(cartella, "predizioni_test.npz"), **arr)


def carica_o_addestra_b1(S, tr, lam_h, lam_a, giri, fatt, par_b1, zero_st, out_dir, ris) -> Dict[str, Any]:
    """B1 del test: 3 modelli per orizzonte (bagging per partita). I modelli si
    salvano in cache (testo LightGBM) con la loro configurazione: una seconda
    corsa con la STESSA configurazione li ricarica invece di riaddestrarli."""
    import lightgbm as lgb

    from Betfair.stream.scalper.validazione_hazard.modello_b1 import addestra_b1
    cartella = os.path.join(out_dir, "cache", "b1_test")
    firma = json.dumps({"giri": giri, "fatt": round(fatt, 6), "par": par_b1, "zero": zero_st,
                        "n_tr": int(tr.size), "fumo": FUMO["attivo"]}, sort_keys=True)
    b1: Dict[str, Any] = {"modelli": {2: [], 3: []}, "zero_stagione": zero_st}
    fpath = os.path.join(cartella, "firma.json")
    if os.path.exists(fpath) and open(fpath, encoding="utf-8").read() == firma:
        for k in (2, 3):
            for b in range(3):
                b1["modelli"][k].append(lgb.Booster(model_file=os.path.join(cartella, f"b1_{k}_{b}.txt")))
        ris["B1_da_cache"] = True
        return b1
    for k in (2, 3):
        mk = addestra_b1(S, tr, lam_h, lam_a,
                         n_round=(5 if FUMO["attivo"] else max(50, int(round(giri[str(k)] * fatt)))),
                         n_bag=3, parametri=par_b1, zero_stagione=zero_st)
        b1["modelli"][k] = mk["modelli"][k]
    os.makedirs(cartella, exist_ok=True)
    for k in (2, 3):
        for b, bst in enumerate(b1["modelli"][k]):
            bst.save_model(os.path.join(cartella, f"b1_{k}_{b}.txt"))
    with open(fpath, "w", encoding="utf-8") as fh:
        fh.write(firma)
    ris["B1_da_cache"] = False
    return b1


def valuta_modulo_v4(partite: List[Any], S: Dict[str, np.ndarray], ev: np.ndarray, lam_h: np.ndarray,
                     lam_a: np.ndarray, mod_stella: CA.ModelloA, train_max: int
                     ) -> Tuple[Dict[str, np.ndarray], Dict[str, Any]]:
    """Il modulo ``atlante_v4`` stato per stato, con la configurazione di A*."""
    from Betfair.stream.scalper import atlante_v4 as V4
    conf = mod_stella.conf
    stati: Dict[str, Dict[str, Any]] = {}
    for p in partite:
        if p.season <= train_max:
            st = stati.setdefault(str(p.league_id), V4.stato_lega_v4_vuoto(p.league_id))
            V4.aggiungi_partita_v4(st, p)
    beta = mod_stella.beta if (conf.forza and mod_stella.beta) else {2: 0.0, 3: 0.0}
    blocco = V4.assembla_v4(stati, generated_at="2026-09-25T00:00:00+00:00", stagione_rif=train_max + 1,
                            emivita=conf.emivita, k_celle=float(conf.k) if conf.k != "mdm" else V4.K_CELLE,
                            beta=beta)
    atlas = {"meta": {"generated_at": "2026-09-25T00:00:00+00:00", "n_fixtures_used": None}, "v4": blocco}
    p2 = np.empty(ev.size)
    p3 = np.empty(ev.size)
    for n, i in enumerate(ev):
        c = V4.consulta_atlante_v4(atlas, int(S["m_live"][i]), int(S["gh"][i] + S["ga"][i]), int(S["lega"][i]),
                                   tempo=int(S["tempo"][i]), usa_cella_recupero_1t=True,
                                   lambda_home=float(lam_h[i]) if conf.forza else None,
                                   lambda_away=float(lam_a[i]) if conf.forza else None)
        p2[n], p3[n] = c["p_2min"], c["p_3min"]
    return {"p2": p2, "p3": p3}, {"beta": {str(k): v for k, v in beta.items()}, "meta": {
        k: v for k, v in blocco["meta"].items() if k != "etichette_tc"}}


def _emivita_scelta(val: Dict[str, Any]) -> float:
    for p in val["catena"]:
        if p["passo"] == "A2":
            best = min(p["esiti"], key=lambda e: e["delta_ll_vs_corrente"][0])
            return float(best["opzione"]["emivita"])
    return 3.0


def calibrazioni(pred: Dict[str, Dict[str, np.ndarray]], S: Dict[str, np.ndarray], idx: np.ndarray,
                 nomi: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    tc = CA.cella_tempo(S, idx)
    etich = [f"{5 * b}-{5 * b + 5}" for b in range(18)] + ["45+"] + [f"90+{j}" for j in
                                                                     ("0", "1", "2", "3", "4", "5", "6-7", "8+")]
    for n in nomi:
        if n not in pred:
            continue
        for k in (2, 3):
            p, y = pred[n][f"p{k}"], S[f"y{k}"][idx]
            dec = ME.calibrazione(p, y, 10)
            per_min = []
            for c in range(CA.NT):
                m = tc == c
                if m.any():
                    per_min.append({"cella": etich[c], "n": int(m.sum()), "prevista": float(p[m].mean()),
                                    "osservata": float(y[m].mean())})
            out[f"{n}|{k}"] = {"decili": dec, "per_minuto": per_min}
    return out


def sottoinsieme(D, S, ev, pred, b1, modelli, lam, lam_h, lam_a, lam_tot, atlas,
                 maschera: Optional[np.ndarray] = None) -> Dict[str, Any]:
    partite = D["partite"]
    reali = D["lam_real"]
    fx = np.array([p.fixture_id for p in partite])
    ha = np.array([p.fixture_id in reali for p in partite])
    m_ev = ha[S["mi"][ev]]
    if maschera is not None:
        m_ev = m_ev & maschera
    sub = ev[m_ev]
    out: Dict[str, Any] = {"n_partite": int(np.unique(S["mi"][sub]).size), "n_stati": int(sub.size)}
    if sub.size == 0:
        return out
    # lambda veri al posto del proxy (B2 = B1 con i lambda del motore; A* idem se usa la forza)
    lh_r = lam_h.copy()
    la_r = lam_a.copy()
    rr = np.array([reali.get(int(f), (np.nan, np.nan)) for f in fx])
    lh_r = np.where(ha[S["mi"]], rr[S["mi"], 0], lh_r)
    la_r = np.where(ha[S["mi"]], rr[S["mi"], 1], la_r)
    from Betfair.stream.scalper.validazione_hazard.modello_b1 import prevedi_b1
    ps: Dict[str, Dict[str, np.ndarray]] = {}
    for n in ("A0", "A1", "A*", "B1"):
        ps[n] = {k: v[m_ev] for k, v in pred[n].items() if isinstance(v, np.ndarray)}
    ps["B2"] = prevedi_b1(b1, S, sub, lh_r, la_r)
    ps["A*_lambda_veri"] = CA.prevedi_a(modelli["A*"], S, sub, lh_r + la_r)
    # lambda: proxy contro veri, verosimiglianza dei gol
    pp = [p for p in partite if p.season == 2025 and p.fixture_id in reali]
    llp = [(p.ft[0] * math.log(lam[p.fixture_id][0]) - lam[p.fixture_id][0]
            + p.ft[1] * math.log(lam[p.fixture_id][1]) - lam[p.fixture_id][1]) for p in pp]
    llr = [(p.ft[0] * math.log(reali[p.fixture_id][0]) - reali[p.fixture_id][0]
            + p.ft[1] * math.log(reali[p.fixture_id][1]) - reali[p.fixture_id][1]) for p in pp]
    out["lambda"] = {"n": len(pp), "corr_tot": float(np.corrcoef(
        [lam[p.fixture_id][0] + lam[p.fixture_id][1] for p in pp],
        [reali[p.fixture_id][0] + reali[p.fixture_id][1] for p in pp])[0, 1]),
        "ll_poisson_proxy": float(np.mean(llp)), "ll_poisson_veri": float(np.mean(llr)),
        "media_proxy": float(np.mean([lam[p.fixture_id][0] + lam[p.fixture_id][1] for p in pp])),
        "media_veri": float(np.mean([reali[p.fixture_id][0] + reali[p.fixture_id][1] for p in pp])),
        "gol_medi": float(np.mean([sum(p.ft) for p in pp]))}
    # il MODELLO LIVE di Safe (event_goal_hazard) coi lambda veri
    ps["modello_live"] = modello_live(S, sub, lh_r, la_r)
    # il modello live tace (None) dove il suo tempo e' esaurito (>= 95'): lo si
    # confronta solo dove parla, e si dichiara quanti stati restano fuori
    ok = np.isfinite(ps["modello_live"]["p2"]) & np.isfinite(ps["modello_live"]["p3"])
    out["stati_senza_modello_live"] = int((~ok).sum())
    out["stati_senza_modello_live_recupero2T"] = int((~ok & (S["stop"][sub] == 1) & (S["tempo"][sub] == 2)).sum())
    sub = sub[ok]
    ps = {n: {k: v[ok] for k, v in d.items()} for n, d in ps.items()}
    out["metriche"] = valuta(ps, S, sub, "A0", b_auc=100, auc_ic_per={"A0", "A*", "B2", "modello_live"})
    out["divergenza_spuria"] = divergenza(ps, S, sub)
    return out


def modello_live(S: Dict[str, np.ndarray], idx: np.ndarray, lh: np.ndarray, la: np.ndarray) -> Dict[str, np.ndarray]:
    """``event_goal_hazard`` di produzione (quello che Safe confronta con l'atlante).
    Minuto: 0..89, recupero 2T 90+j, recupero 1T 45 (il modello non ha il 1T
    lungo). Rossi dallo stato. None (tempo del modello esaurito) -> NaN."""
    from Betfair.stream.engine.live_engine_pro import event_goal_hazard
    out = {"p2": np.full(idx.size, np.nan), "p3": np.full(idx.size, np.nan)}
    cache: Dict[Tuple[Any, ...], Optional[float]] = {}
    for n, i in enumerate(idx):
        m = int(S["m_live"][i])
        if S["stop"][i] == 1 and S["tempo"][i] == 1:
            m = 45
        for k in (2, 3):
            ch = (m, int(S["gh"][i]), int(S["ga"][i]), round(float(lh[i]), 4), round(float(la[i]), 4),
                  int(S["lega"][i]), int(S["rh"][i]), int(S["ra"][i]), k)
            v = cache.get(ch, "x")
            if v == "x":
                r = event_goal_hazard(score_home=ch[1], score_away=ch[2], minute=m,
                                      prematch_lambda_home=ch[3], prematch_lambda_away=ch[4],
                                      league_id=ch[5], red_home=ch[6], red_away=ch[7], horizon_min=float(k))
                v = None if r is None else float(r["p_next"])
                cache[ch] = v
            out[f"p{k}"][n] = np.nan if v is None else v
    return out


def divergenza(ps: Dict[str, Dict[str, np.ndarray]], S: Dict[str, np.ndarray], idx: np.ndarray) -> Dict[str, Any]:
    """Quante volte l'atlante diverge dal modello live oltre le soglie di Safe
    (warn 30%, drop 60%) e oltre il 35% del brief, e CHI aveva ragione: per
    decile del rapporto log(p_modello/p_atlante) fra gli stati segnalati, la
    frequenza osservata e' piu' vicina al modello o all'atlante?"""
    out: Dict[str, Any] = {}
    y3 = S["y3"][idx]
    pm = ps["modello_live"]["p3"]
    for atl in ("A0", "A*", "B1"):
        pa = ps[atl]["p3"]
        ok = np.isfinite(pm) & np.isfinite(pa) & (pa > 0)
        div = np.abs(pm - pa) / np.where(pa > 0, pa, np.nan)
        r_atl: Dict[str, Any] = {"stati_confrontabili": int(ok.sum())}
        for soglia in (0.30, 0.35, 0.60):
            seg = ok & (div > soglia)
            rr: Dict[str, Any] = {"n": int(seg.sum()), "quota": float(seg.sum() / max(ok.sum(), 1))}
            if seg.sum() >= 50:
                lr = np.log(pm[seg] / pa[seg])
                q = np.unique(np.quantile(lr, np.linspace(0, 1, 11)))
                b = np.clip(np.searchsorted(q, lr, side="right") - 1, 0, len(q) - 2)
                ragione_modello = 0
                bins = []
                for c in range(len(q) - 1):
                    m = b == c
                    if not m.any():
                        continue
                    obs = float(y3[seg][m].mean())
                    mm, aa = float(pm[seg][m].mean()), float(pa[seg][m].mean())
                    mod_ok = abs(obs - mm) < abs(obs - aa)
                    ragione_modello += int(m.sum()) if mod_ok else 0
                    bins.append({"n": int(m.sum()), "p_modello": mm, "p_atlante": aa, "osservata": obs,
                                 "ragione": "modello" if mod_ok else "atlante"})
                rr["spurie_ragione_al_modello"] = ragione_modello
                rr["quota_spurie"] = ragione_modello / max(int(seg.sum()), 1)
                rr["logloss_modello"] = float(ME.logloss_vett(pm[seg], y3[seg]).mean())
                rr["logloss_atlante"] = float(ME.logloss_vett(pa[seg], y3[seg]).mean())
                rr["osservata"] = float(y3[seg].mean())
                rr["decili"] = bins
            r_atl[f">{int(soglia * 100)}%"] = rr
        out[atl] = r_atl
    return out


def _scrivi(out_dir: str, fase: str, ris: Dict[str, Any]) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"risultati_{fase}.json"), "w", encoding="utf-8") as fh:
        json.dump(ris, fh, indent=1, default=_json_default)


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Banco di validazione fuori campione dell'Atlante Hazard.")
    ap.add_argument("--da-cache", action="store_true", required=True,
                    help="obbligatorio: il banco legge SOLO la cache locale")
    ap.add_argument("--cache", default=CACHE_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--fase", choices=("validazione", "test", "tutto"), default="tutto")
    ap.add_argument("--fumo", action="store_true", help="prova veloce (1 partita su 10), esiti in --out")
    a = ap.parse_args(argv)
    FUMO["attivo"] = bool(a.fumo)
    t0 = time.time()
    D = carica_tutto(a.cache)
    log("partite", len(D["partite"]), "stati", D["S"]["y3"].size, round(time.time() - t0, 1), "s")
    val = None
    if a.fase in ("validazione", "tutto"):
        val = fase_validazione(D, a.out)
    if a.fase in ("test", "tutto"):
        if val is None:
            with open(os.path.join(a.out, "risultati_validazione.json"), encoding="utf-8") as fh:
                val = json.load(fh)
        else:
            val = json.loads(json.dumps(val, default=_json_default))
        fase_test(D, a.out, val)
    log("fine", round(time.time() - t0, 1), "s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
