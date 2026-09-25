"""modello_b1.py - B1: hazard a tempo discreto con gradient boosting (LightGBM).

Un modello per orizzonte (2' e 3'), obiettivo binario sulla STESSA verita' della
famiglia A (gol nei prossimi k minuti di gioco dello stesso tempo), una riga per
stato a rischio. Variabili (tutte disponibili in live salvo dove detto):
  tempo, t (minuti nel tempo), stop (recupero), j (minuto di recupero giocato),
  gol totali, differenza reti (casa-trasferta), rossi casa, rossi trasferta,
  minuti dall'ultimo gol, lega (categorica), stagione (era),
  lambda_casa, lambda_trasferta pre-partita (monotone crescenti).
Incertezza: ``n_bag`` modelli su ricampioni per PARTITA (bagging) -> media e
deviazione standard per stato (IC ~ media +- 1,96 sd).
Nessuna libreria installata: lightgbm 4.6.0 e' gia' nel .venv del repo.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

COLONNE = ["tempo", "t", "stop", "j", "gtot", "diff", "rh", "ra", "dal_gol", "lega",
           "stagione", "lam_h", "lam_a"]
MONOTONE = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1]
PARAMETRI = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 63,
             "min_data_in_leaf": 400, "feature_fraction": 0.9, "lambda_l2": 10.0,
             "max_cat_to_onehot": 64, "cat_smooth": 20.0, "verbose": -1, "num_threads": 6,
             "seed": 20260925, "deterministic": True, "force_row_wise": True}


def matrice(S: Dict[str, np.ndarray], idx: np.ndarray, lam_h: np.ndarray, lam_a: np.ndarray,
            zero_stagione: bool = False) -> np.ndarray:
    """``zero_stagione``: la variabile 'stagione' neutralizzata (costante), se la
    taratura in validazione ha scelto di non usarla (niente estrapolazione d'era)."""
    gh, ga = S["gh"][idx], S["ga"][idx]
    X = np.column_stack([
        S["tempo"][idx], S["t"][idx], S["stop"][idx], S["j"][idx],
        gh + ga, gh - ga, S["rh"][idx], S["ra"][idx], S["dal_gol"][idx],
        S["lega"][idx], (S["stagione"][idx] * 0 if zero_stagione else S["stagione"][idx]),
        lam_h[idx], lam_a[idx],
    ]).astype(np.float32)
    return X


def addestra_b1(S: Dict[str, np.ndarray], idx: np.ndarray, lam_h: np.ndarray, lam_a: np.ndarray,
                *, n_round: int = 400, idx_val: Optional[np.ndarray] = None, n_bag: int = 1,
                seme: int = 20260925, parametri: Optional[Dict[str, Any]] = None,
                zero_stagione: bool = False) -> Dict[str, Any]:
    """Addestra i modelli per 2' e 3'. Con ``idx_val`` usa l'arresto anticipato
    (solo nella fase di VALIDAZIONE, mai sul test) e riporta il giro migliore."""
    import lightgbm as lgb

    par = dict(PARAMETRI)
    par.update(parametri or {})
    par["monotone_constraints"] = MONOTONE
    X = matrice(S, idx, lam_h, lam_a, zero_stagione)
    out: Dict[str, Any] = {"modelli": {2: [], 3: []}, "giri": {}, "zero_stagione": zero_stagione}
    mi = S["mi"][idx]
    partite = np.unique(mi)
    rng = np.random.default_rng(seme)
    for k in (2, 3):
        y = S[f"y{k}"][idx].astype(np.float32)
        for b in range(n_bag):
            if n_bag > 1:
                scelte = rng.choice(partite, size=partite.size, replace=True)
                cnt = np.bincount(np.searchsorted(partite, scelte), minlength=partite.size)
                peso = cnt[np.searchsorted(partite, mi)].astype(np.float32)
            else:
                peso = None
            ds = lgb.Dataset(X, y, weight=peso, feature_name=COLONNE, categorical_feature=["lega"],
                             free_raw_data=False)
            p = dict(par, seed=seme + b)
            if idx_val is not None:
                Xv = matrice(S, idx_val, lam_h, lam_a, zero_stagione)
                dv = lgb.Dataset(Xv, S[f"y{k}"][idx_val].astype(np.float32), reference=ds)
                bst = lgb.train(p, ds, num_boost_round=n_round, valid_sets=[dv],
                                callbacks=[lgb.early_stopping(50, verbose=False)])
                out["giri"][k] = int(bst.best_iteration)
            else:
                bst = lgb.train(p, ds, num_boost_round=n_round)
            out["modelli"][k].append(bst)
    return out


def prevedi_b1(mod: Dict[str, Any], S: Dict[str, np.ndarray], idx: np.ndarray, lam_h: np.ndarray,
               lam_a: np.ndarray) -> Dict[str, np.ndarray]:
    X = matrice(S, idx, lam_h, lam_a, bool(mod.get("zero_stagione")))
    out: Dict[str, np.ndarray] = {}
    for k in (2, 3):
        pr = []
        for bst in mod["modelli"][k]:
            it = bst.best_iteration if bst.best_iteration and bst.best_iteration > 0 else None
            pr.append(bst.predict(X, num_iteration=it))
        pr = np.array(pr)
        out[f"p{k}"] = pr.mean(0)
        out[f"sd{k}"] = pr.std(0) if pr.shape[0] > 1 else np.zeros(pr.shape[1])
    return out


def importanza(mod: Dict[str, Any]) -> Dict[int, List[List[Any]]]:
    out = {}
    for k in (2, 3):
        bst = mod["modelli"][k][0]
        g = bst.feature_importance(importance_type="gain")
        tot = float(g.sum()) or 1.0
        out[k] = sorted([[n, round(float(v) / tot, 4)] for n, v in zip(COLONNE, g)], key=lambda x: -x[1])
    return out
