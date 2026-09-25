"""candidati.py - la famiglia A (empirica, come l'atlante) con le sue varianti.

Tutte le varianti leggono gli stati di ``stati.tabella_stati`` (verita' a
tempo reale: niente clamp a 45/90) e producono P(gol entro 2') e P(gol entro 3').

CELLE DI TEMPO (tc): 0..17 = bucket di 5' del minuto regolare (come l'atlante),
18 = recupero del 1T, 19..27 = recupero del 2T per minuto gia' giocato j
(0,1,2,3,4,5,6,7,8+). GOL (gk): 0,1,2,3+ come l'atlante.

A1  celle regolari e recupero 1T contate come l'atlante ma sulla verita' vera;
    recupero 2T con un MODELLO: tasso di gol per minuto di recupero r(lega, gk)
    x distribuzione della durata del recupero pi(d) stimata dai dati (per lega,
    shrinkata verso il campione): P_k(j) = 1 - E[exp(-r*min(k, D-j)) | D > j].
    La partita finisce quando finisce: si condiziona su "viva al 90+j".
A2  pesi per eta' della stagione: w = 0.5 ** ((stagione_rif - stagione) / emivita).
A3  stato del gioco: differenza reti (-2..+2, lato casa) oltre ai gol totali,
    come moltiplicatore in spazio hazard stimato sul globale (shrinkato).
A4  cartellini rossi: moltiplicatore hazard per configurazione (nessuno, casa
    in meno, trasferta in meno, pari), stimato per massima verosimiglianza.
A5  forza pre-partita: moltiplicatore (lambda_tot / lambda_medio_lega) ** beta.
A6  K di shrinkage dal metodo dei momenti (varianza fra leghe vs varianza di
    campionamento con cluster per partita) invece di 1500.
Trasformazione in spazio hazard (la stessa del livello squadre dell'atlante):
    p' = 1 - (1 - p) ** moltiplicatore.
PURO: numpy (+ scipy per le ottimizzazioni a una dimensione).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize_scalar

NT = 28
TC_REC1 = 18
TC_REC2 = 19
J_BIN = np.array([0, 1, 2, 3, 4, 5, 6, 6, 7], dtype=np.int32)   # j 0..8+ -> 9 celle (6-7 insieme)
N_JB = 8
NG = 4
ND = 5
D_MAX = 30
MIN_PARTITE_AFFIDABILE = 300
K_ATLANTE = 1500.0


def cella_tempo(S: Dict[str, np.ndarray], idx: np.ndarray) -> np.ndarray:
    stop = S["stop"][idx]
    tempo = S["tempo"][idx]
    j = np.minimum(S["j"][idx], 8)
    reg = np.minimum(S["m_live"][idx], 89) // 5
    rec2 = TC_REC2 + J_BIN[j]
    return np.where(stop == 0, reg, np.where(tempo == 1, TC_REC1, rec2)).astype(np.int32)


def gol_key(S: Dict[str, np.ndarray], idx: np.ndarray) -> np.ndarray:
    return np.minimum(S["gh"][idx] + S["ga"][idx], 3).astype(np.int32)


def diff_key(S: Dict[str, np.ndarray], idx: np.ndarray) -> np.ndarray:
    return (np.clip(S["gh"][idx] - S["ga"][idx], -2, 2) + 2).astype(np.int32)


def rossi_key(S: Dict[str, np.ndarray], idx: np.ndarray) -> np.ndarray:
    rh, ra = S["rh"][idx], S["ra"][idx]
    return np.where((rh == 0) & (ra == 0), 0, np.where(rh > ra, 1, np.where(ra > rh, 2, 3))).astype(np.int32)


def hazard_mult(p: np.ndarray, mult: np.ndarray) -> np.ndarray:
    p = np.clip(p, 0.0, 1.0 - 1e-12)
    return 1.0 - np.power(1.0 - p, mult)


def pesi_stagione(stagioni: np.ndarray, rif: int, emivita: Optional[float]) -> np.ndarray:
    if not emivita:
        return np.ones(stagioni.shape, dtype=float)
    return np.power(0.5, (rif - stagioni).astype(float) / float(emivita))


def _ll(p: np.ndarray, y: np.ndarray, w: Optional[np.ndarray] = None) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    v = y * np.log(p) + (1 - y) * np.log(1 - p)
    return float(-(v if w is None else v * w).sum())


def _fit_mult(p: np.ndarray, y: np.ndarray, w: np.ndarray, lo: float = 0.2, hi: float = 5.0) -> float:
    """Moltiplicatore hazard che massimizza la verosimiglianza (1 parametro)."""
    if p.size == 0:
        return 1.0
    r = minimize_scalar(lambda m: _ll(hazard_mult(p, np.full(p.shape, m)), y, w),
                        bounds=(lo, hi), method="bounded", options={"xatol": 1e-4})
    return float(r.x)


def k_metodo_momenti(S: Dict[str, np.ndarray], idx: np.ndarray, y: np.ndarray, lega_i: np.ndarray,
                     tc: np.ndarray, gk: np.ndarray, affidabili: np.ndarray, n_leghe: int
                     ) -> Dict[str, Any]:
    """K empirical-Bayes per le celle regolari: K = sigma2_eff / tau2, con
    sigma2_eff = varianza di campionamento per partita-minuto (cluster per
    PARTITA: le finestre si sovrappongono) e tau2 = varianza vera fra leghe
    (varianza osservata dei p_lega meno la media delle varianze di
    campionamento). Ritorna la mediana sulle celle con tau2 > 0 e il dettaglio."""
    sel = affidabili[lega_i] & (tc < 18)
    ii = np.flatnonzero(sel)
    cella = (tc[ii] * NG + gk[ii]).astype(np.int64)
    mi = S["mi"][idx][ii].astype(np.int64)
    chiave = mi * (18 * NG) + cella
    u, inv = np.unique(chiave, return_inverse=True)
    n_c = np.bincount(inv).astype(float)
    s_c = np.bincount(inv, weights=y[ii].astype(float))
    lega_c = lega_i[ii][np.unique(inv, return_index=True)[1]]
    cella_c = (u % (18 * NG)).astype(np.int64)
    ks = []
    dettagli = []
    for c in range(18 * NG):
        mc = cella_c == c
        if not mc.any():
            continue
        leghe_c = lega_c[mc]
        nn, ss = n_c[mc], s_c[mc]
        ph = []
        vv = []
        nl = []
        for l in np.unique(leghe_c):
            ml = leghe_c == l
            n_l = nn[ml].sum()
            if n_l < 50:
                continue
            p_l = ss[ml].sum() / n_l
            v_l = float(((ss[ml] - p_l * nn[ml]) ** 2).sum() / n_l ** 2)
            ph.append(p_l)
            vv.append(v_l)
            nl.append(n_l)
        if len(ph) < 5:
            continue
        ph, vv, nl = np.array(ph), np.array(vv), np.array(nl)
        tau2 = float(np.var(ph, ddof=1) - vv.mean())
        sig2 = float((vv * nl).mean())
        dettagli.append({"cella": int(c), "tau2": tau2, "sigma2_eff": sig2,
                         "k": (sig2 / tau2) if tau2 > 0 else None})
        if tau2 > 0:
            ks.append(sig2 / tau2)
    ks = np.array(ks)
    return {"k": float(np.median(ks)) if ks.size else K_ATLANTE,
            "n_celle": int(ks.size), "n_celle_tau2_nonpositivo": int(len(dettagli) - ks.size),
            "quantili": [float(x) for x in np.quantile(ks, [0.1, 0.25, 0.5, 0.75, 0.9])] if ks.size else [],
            "dettagli": dettagli}


@dataclass(frozen=True)
class ConfA:
    nome: str = "A1"
    recupero: bool = True
    emivita: Optional[float] = None
    stato: bool = False
    rossi: bool = False
    forza: bool = False
    k: Any = K_ATLANTE          # numero o "mdm"
    k_durata: Any = "mdm"       # shrinkage della durata del recupero per lega


@dataclass
class ModelloA:
    conf: ConfA
    leghe: np.ndarray
    p_lega: Dict[int, np.ndarray] = field(default_factory=dict)   # k -> [L, NT, NG]
    mult_stato: Dict[int, np.ndarray] = field(default_factory=dict)  # k -> [NT, NG, ND]
    r_lega: Optional[np.ndarray] = None       # [L, NG] tassi di gol per minuto di recupero 2T
    mult_stato_r: Optional[np.ndarray] = None  # [NG, ND]
    pi_lega: Optional[np.ndarray] = None      # [L, D_MAX+1]
    pi_pool: Optional[np.ndarray] = None      # [D_MAX+1] ripiego per leghe senza dati
    mult_rossi: Dict[int, np.ndarray] = field(default_factory=dict)  # k -> [4]
    beta: Dict[int, float] = field(default_factory=dict)
    lam_ref: Optional[np.ndarray] = None      # [L]
    info: Dict[str, Any] = field(default_factory=dict)


def _indice_lega(leghe: np.ndarray, lega: np.ndarray) -> np.ndarray:
    pos = np.searchsorted(leghe, lega)
    pos = np.clip(pos, 0, len(leghe) - 1)
    ok = leghe[pos] == lega
    return np.where(ok, pos, -1).astype(np.int64)


def addestra_a(conf: ConfA, S: Dict[str, np.ndarray], idx: np.ndarray, leghe: np.ndarray,
               lam_tot: np.ndarray, stagione_rif: int, gol_tot: Optional[np.ndarray] = None) -> ModelloA:
    """Stima la variante ``conf`` sugli stati ``idx`` (solo addestramento).

    A5: il riferimento della forza di una lega e' la media PESATA (pesi A2) dei
    gol per partita della lega (``gol_tot``, per stato = gol finali della sua
    partita): e' una grandezza che il generatore di produzione ha gia' e che sta
    sulla stessa scala dei lambda che Safe riceve in live. Senza ``gol_tot`` si
    usa la media dei lambda di addestramento."""
    L = len(leghe)
    mod = ModelloA(conf=conf, leghe=leghe)
    lega_i = _indice_lega(leghe, S["lega"][idx])
    tc = cella_tempo(S, idx)
    gk = gol_key(S, idx)
    dk = diff_key(S, idx)
    w = pesi_stagione(S["stagione"][idx], stagione_rif, conf.emivita)
    # leghe affidabili: >= 300 partite di addestramento (conteggio non pesato)
    mi = S["mi"][idx]
    part_lega = np.zeros(L)
    _, primo = np.unique(mi, return_index=True)
    np.add.at(part_lega, lega_i[primo], 1)
    affid = part_lega >= MIN_PARTITE_AFFIDABILE
    mod.info["partite_per_lega"] = {int(leghe[i]): int(part_lega[i]) for i in range(L)}
    for k, y in ((2, S["y2"][idx]), (3, S["y3"][idx])):
        yk = y.astype(float)
        if conf.k == "mdm":
            km = k_metodo_momenti(S, idx, yk, lega_i, tc, gk, affid, L)
            K = km["k"]
            mod.info[f"k_mdm_{k}"] = {kk: v for kk, v in km.items() if kk != "dettagli"}
        else:
            K = float(conf.k)
        mod.info[f"K_{k}"] = K
        chiave = (lega_i * NT + tc) * NG + gk
        n = np.bincount(chiave, weights=w, minlength=L * NT * NG).reshape(L, NT, NG)
        s = np.bincount(chiave, weights=w * yk, minlength=L * NT * NG).reshape(L, NT, NG)
        ng = n[affid].sum(0)
        sg = s[affid].sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            pg = np.where(ng > 0, sg / np.maximum(ng, 1e-12), np.nan)
        # celle globali vuote (recupero non addestrato): ripiego DICHIARATO sul
        # bucket regolare adiacente (40-45 per il 1T, 85-90 per il 2T)
        for tcx, rip in [(TC_REC1, 8)] + [(TC_REC2 + b, 17) for b in range(N_JB)]:
            vuote = ~np.isfinite(pg[tcx]) | (ng[tcx] <= 0)
            pg[tcx] = np.where(vuote, pg[rip], pg[tcx])
            if vuote.any():
                mod.info.setdefault("ripieghi", []).append([int(tcx), int(rip)])
                n[:, tcx][:, vuote] = 0.0
                s[:, tcx][:, vuote] = 0.0
                # la lega eredita il suo bucket regolare adiacente
                n[:, tcx] = np.where(vuote[None, :], n[:, rip], n[:, tcx])
                s[:, tcx] = np.where(vuote[None, :], s[:, rip], s[:, tcx])
        # celle globali ancora vuote (gk mai visto): media della riga
        pg = np.where(np.isfinite(pg), pg, np.nanmean(pg))
        mod.p_lega[k] = (s + K * pg[None]) / (n + K)
        mod.info[f"globale_{k}"] = pg
        if conf.stato:
            chiave_d = (tc * NG + gk) * ND + dk
            aff_st = affid[lega_i]
            nd = np.bincount(chiave_d[aff_st], weights=w[aff_st], minlength=NT * NG * ND).reshape(NT, NG, ND)
            sd = np.bincount(chiave_d[aff_st], weights=(w * yk)[aff_st], minlength=NT * NG * ND).reshape(NT, NG, ND)
            pd = (sd + K * pg[:, :, None]) / (nd + K)
            with np.errstate(divide="ignore", invalid="ignore"):
                m = np.log(np.clip(1 - pd, 1e-12, 1)) / np.log(np.clip(1 - pg[:, :, None], 1e-12, 1))
            mod.mult_stato[k] = np.where(np.isfinite(m) & (m > 0), m, 1.0)
    if conf.recupero:
        _addestra_recupero(mod, S, idx, lega_i, gk, dk, w, affid)
    # A5 prima di A4: la forza vale per tutti gli stati, i rossi sono rari
    lam_i = lam_tot[idx]
    if conf.forza:
        ref = np.full(L, np.nan)
        base_ref = gol_tot[idx] if gol_tot is not None else lam_i
        for l in range(L):
            m = (lega_i[primo] == l)
            if m.any():
                ref[l] = float(np.average(base_ref[primo][m], weights=w[primo][m]))
        ref = np.where(np.isfinite(ref), ref, float(np.nanmean(ref)))
        mod.lam_ref = ref
        base = {k: _prevedi_base(mod, S, idx) [k] for k in (2, 3)}
        rap = np.clip(lam_i / ref[np.maximum(lega_i, 0)], 0.2, 5.0)
        for k, y in ((2, S["y2"][idx]), (3, S["y3"][idx])):
            pb = base[k]
            r = minimize_scalar(lambda b: _ll(hazard_mult(pb, np.power(rap, b)), y, w),
                                bounds=(0.0, 3.0), method="bounded", options={"xatol": 1e-4})
            mod.beta[k] = float(r.x)
    if conf.rossi:
        pr = _prevedi_senza_rossi(mod, S, idx, lam_tot)
        rk = rossi_key(S, idx)
        for k, y in ((2, S["y2"][idx]), (3, S["y3"][idx])):
            mult = np.ones(4)
            for c in (1, 2, 3):
                m = rk == c
                mult[c] = _fit_mult(pr[k][m], y[m].astype(float), w[m])
            mod.mult_rossi[k] = mult
            mod.info[f"rossi_stati_{k}"] = [int((rk == c).sum()) for c in range(4)]
    return mod


def _addestra_recupero(mod: ModelloA, S: Dict[str, np.ndarray], idx: np.ndarray, lega_i: np.ndarray,
                       gk: np.ndarray, dk: np.ndarray, w: np.ndarray, affid: np.ndarray) -> None:
    """Tasso di gol per minuto di recupero del 2T e distribuzione della durata."""
    L = len(mod.leghe)
    conf = mod.conf
    rec = (S["stop"][idx] == 1) & (S["tempo"][idx] == 2)
    ii = np.flatnonzero(rec)
    mod.info["recupero2_stati_addestramento"] = int(ii.size)
    if ii.size == 0:
        mod.r_lega = None
        return
    g1 = S["g1"][idx][ii].astype(float)
    ww = w[ii]
    ch = lega_i[ii] * NG + gk[ii]
    E = np.bincount(ch, weights=ww, minlength=L * NG).reshape(L, NG)
    Gs = np.bincount(ch, weights=ww * g1, minlength=L * NG).reshape(L, NG)
    Eg, Gg = E[affid].sum(0), Gs[affid].sum(0)
    if Eg.sum() <= 0:
        Eg, Gg = E.sum(0), Gs.sum(0)
    rg = np.where(Eg > 0, Gg / np.maximum(Eg, 1e-12), (Gg.sum() / max(Eg.sum(), 1e-12)))
    K = float(mod.info.get("K_3", K_ATLANTE))
    mod.r_lega = (Gs + K * rg[None]) / (E + K)
    mod.info["r_globale_per_gk"] = rg.tolist()
    if conf.stato:
        chd = gk[ii] * ND + dk[ii]
        Ed = np.bincount(chd, weights=ww, minlength=NG * ND).reshape(NG, ND)
        Gd = np.bincount(chd, weights=ww * g1, minlength=NG * ND).reshape(NG, ND)
        rd = (Gd + K * rg[:, None]) / (Ed + K)
        mod.mult_stato_r = rd / np.maximum(rg[:, None], 1e-12)
    # durata del recupero: una riga per partita (lo stato j=0 della partita)
    j0 = ii[S["j"][idx][ii] == 0]
    # d2 = numero di stati di recupero della partita
    mi_r = S["mi"][idx][ii]
    u, cnt = np.unique(mi_r, return_counts=True)
    d_per = dict(zip(u.tolist(), cnt.tolist()))
    lega_j0 = lega_i[j0]
    d_j0 = np.array([d_per[int(m)] for m in S["mi"][idx][j0]], dtype=np.int64)
    w_j0 = w[j0]
    cnts = np.zeros((L, D_MAX + 1))
    np.add.at(cnts, (lega_j0, np.minimum(d_j0, D_MAX)), w_j0)
    pool = cnts.sum(0)
    pool = pool / pool.sum()
    # K della durata: metodo dei momenti sulle medie di lega
    medie, var_c, nl = [], [], []
    for l in range(L):
        tot = cnts[l].sum()
        if tot >= 30:
            dd = np.arange(D_MAX + 1)
            mu = (cnts[l] * dd).sum() / tot
            medie.append(mu)
            var_c.append(((cnts[l] * (dd - mu) ** 2).sum() / tot) / tot)
            nl.append(tot)
    kd = 50.0
    if conf.k_durata == "mdm" and len(medie) >= 3:
        tau2 = float(np.var(medie, ddof=1) - np.mean(var_c))
        sig2 = float(np.mean(np.array(var_c) * np.array(nl)))
        kd = sig2 / tau2 if tau2 > 0 else 1e9
    elif conf.k_durata != "mdm":
        kd = float(conf.k_durata)
    mod.info["k_durata"] = kd
    mod.info["durata_media_pool"] = float((pool * np.arange(D_MAX + 1)).sum())
    tot_l = cnts.sum(1, keepdims=True)
    mod.pi_lega = (cnts + kd * pool[None]) / (tot_l + kd)
    mod.pi_pool = pool
    mod.info["durata_media_per_lega"] = {int(mod.leghe[l]): round(float((mod.pi_lega[l] * np.arange(D_MAX + 1)).sum()), 3)
                                         for l in range(L)}
    mod.info["partite_con_durata_per_lega"] = {int(mod.leghe[l]): round(float(tot_l[l, 0]), 1) for l in range(L)}


def _prevedi_recupero2(mod: ModelloA, lega_i: np.ndarray, gk: np.ndarray, dk: np.ndarray,
                       j: np.ndarray, k: int, modo: str = "distribuzione",
                       d_vero: Optional[np.ndarray] = None) -> np.ndarray:
    """P(gol entro k) al 90+j, partita VIVA. ``modo``:
      'distribuzione'  E[exp(-r*min(k, D-j)) | D > j] con D ~ pi(lega) (decisione
                       dell'utente 25/09: stima per lega, ripiego sul campione);
      'media'          stessa pi(lega) ma solo il resto ATTESO E[D-j | D>j];
      'oracolo'        D = recupero VERO della partita (noto solo a posteriori:
                       misura il prezzo del dato che in live manca)."""
    glob = np.array(mod.info["r_globale_per_gk"])[gk]
    r = np.where(lega_i >= 0, mod.r_lega[np.maximum(lega_i, 0), gk], glob)
    if mod.mult_stato_r is not None:
        r = r * mod.mult_stato_r[gk, dk]
    if modo == "oracolo":
        resto = np.minimum(k, np.maximum(d_vero - j, 1))
        return 1.0 - np.exp(-r * resto)
    pool = mod.pi_pool if mod.pi_pool is not None else mod.pi_lega.mean(0)
    pi = np.where((lega_i >= 0)[:, None], mod.pi_lega[np.maximum(lega_i, 0)], pool[None])
    d = np.arange(D_MAX + 1)[None, :]
    vivo = d > j[:, None]
    massa = (pi * vivo).sum(1)
    if modo == "media":
        atteso = (pi * vivo * (d - j[:, None])).sum(1) / np.maximum(massa, 1e-300)
        atteso = np.where(massa > 0, atteso, 1.0)
        return 1.0 - np.exp(-r * np.minimum(k, atteso))
    resto = np.minimum(k, np.maximum(d - j[:, None], 0))
    sopr = (pi * vivo * np.exp(-r[:, None] * resto)).sum(1)
    p = 1.0 - np.where(massa > 0, sopr / np.maximum(massa, 1e-300), np.exp(-r))
    return p


def _prevedi_base(mod: ModelloA, S: Dict[str, np.ndarray], idx: np.ndarray, modo: str = "distribuzione",
                  d_vero: Optional[np.ndarray] = None) -> Dict[int, np.ndarray]:
    lega_i = _indice_lega(mod.leghe, S["lega"][idx])
    tc = cella_tempo(S, idx)
    gk = gol_key(S, idx)
    dk = diff_key(S, idx)
    out = {}
    for k in (2, 3):
        glob = mod.info[f"globale_{k}"]
        p = np.where(lega_i >= 0, mod.p_lega[k][np.maximum(lega_i, 0), tc, gk], glob[tc, gk])
        if mod.conf.stato:
            p = hazard_mult(p, mod.mult_stato[k][tc, gk, dk])
        if mod.conf.recupero and mod.r_lega is not None:
            rec2 = tc >= TC_REC2
            if rec2.any():
                p = p.copy()
                dv = d_vero[idx][rec2] if d_vero is not None else None
                p[rec2] = _prevedi_recupero2(mod, lega_i[rec2], gk[rec2], dk[rec2],
                                             S["j"][idx][rec2], k, modo, dv)
        out[k] = p
    return out


def _prevedi_senza_rossi(mod: ModelloA, S: Dict[str, np.ndarray], idx: np.ndarray,
                         lam_tot: np.ndarray, modo: str = "distribuzione",
                         d_vero: Optional[np.ndarray] = None) -> Dict[int, np.ndarray]:
    out = _prevedi_base(mod, S, idx, modo, d_vero)
    if mod.conf.forza and mod.beta:
        lega_i = _indice_lega(mod.leghe, S["lega"][idx])
        ref = np.where(lega_i >= 0, mod.lam_ref[np.maximum(lega_i, 0)], float(np.mean(mod.lam_ref)))
        rap = np.clip(lam_tot[idx] / ref, 0.2, 5.0)
        out = {k: hazard_mult(p, np.power(rap, mod.beta[k])) for k, p in out.items()}
    return out


def prevedi_a(mod: ModelloA, S: Dict[str, np.ndarray], idx: np.ndarray,
              lam_tot: np.ndarray, modo: str = "distribuzione",
              d_vero: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """``modo``/``d_vero``: solo per il recupero del 2T (vedi ``_prevedi_recupero2``);
    ``d_vero`` e' indicizzato come gli stati di S."""
    out = _prevedi_senza_rossi(mod, S, idx, lam_tot, modo, d_vero)
    if mod.conf.rossi and mod.mult_rossi:
        rk = rossi_key(S, idx)
        out = {k: hazard_mult(p, mod.mult_rossi[k][rk]) for k, p in out.items()}
    return {"p2": out[2], "p3": out[3]}


def variante(base: ConfA, **kw: Any) -> ConfA:
    return replace(base, **kw)
