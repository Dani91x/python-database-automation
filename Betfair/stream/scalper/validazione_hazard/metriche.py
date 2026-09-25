"""metriche.py - metriche di previsione e bootstrap PER PARTITA (PURO, numpy).

Gli stati della stessa partita sono correlati (le finestre di 3' si
sovrappongono: un gol conta in 3 stati di fila): gli intervalli di confidenza
si fanno ricampionando PARTITE intere, mai stati.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

EPS = 1e-6


def clip(p: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), EPS, 1.0 - EPS)


def logloss_vett(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """-[y ln p + (1-y) ln(1-p)] stato per stato."""
    p = clip(p)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))


def brier_vett(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return (np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2


def auc(p: np.ndarray, y: np.ndarray) -> float:
    """AUC di Mann-Whitney con i pareggi a meta' (ranghi medi)."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y).astype(bool)
    n1 = int(y.sum())
    n0 = int(y.size - n1)
    if n1 == 0 or n0 == 0:
        return float("nan")
    ordine = np.argsort(p, kind="mergesort")
    ps = p[ordine]
    ranghi = np.empty(p.size, dtype=float)
    # ranghi medi sui pareggi
    pos = np.arange(1, p.size + 1, dtype=float)
    cambi = np.flatnonzero(np.diff(ps)) + 1
    inizi = np.concatenate(([0], cambi))
    fini = np.concatenate((cambi, [p.size]))
    medi = (pos[inizi] + pos[fini - 1]) / 2.0
    r_ord = np.repeat(medi, fini - inizi)
    ranghi[ordine] = r_ord
    return float((ranghi[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def per_partita(valori: np.ndarray, mi: np.ndarray, n_partite: int) -> np.ndarray:
    """Somma di un valore per partita (indice ``mi`` 0..n_partite-1)."""
    return np.bincount(mi, weights=valori, minlength=n_partite)


def ricampioni(n_partite: int, b: int, seme: int = 20260925) -> np.ndarray:
    """Matrice [b, n_partite] di CONTEGGI multinomiali (bootstrap per partita)."""
    rng = np.random.default_rng(seme)
    return rng.multinomial(n_partite, np.full(n_partite, 1.0 / n_partite), size=b).astype(np.float64)


def ic_media(somme: np.ndarray, conteggi: np.ndarray, pesi: np.ndarray,
             alfa: float = 0.05) -> Tuple[float, float, float]:
    """Media per stato (somma/stati) e IC percentile dal bootstrap per partita.
    ``somme`` e ``conteggi``: per partita; ``pesi``: matrice dei ricampioni."""
    stima = float(somme.sum() / max(conteggi.sum(), 1))
    num = pesi @ somme
    den = pesi @ conteggi
    boot = num / np.maximum(den, 1)
    lo, hi = np.quantile(boot, [alfa / 2, 1 - alfa / 2])
    return stima, float(lo), float(hi)


def ic_auc(p: np.ndarray, y: np.ndarray, mi: np.ndarray, n_partite: int, b: int = 200,
           seme: int = 20260925) -> Tuple[float, float, float]:
    """AUC e IC percentile ricampionando partite (b ricampioni)."""
    rng = np.random.default_rng(seme)
    stima = auc(p, y)
    # indici degli stati per partita
    ordine = np.argsort(mi, kind="mergesort")
    confini = np.searchsorted(mi[ordine], np.arange(n_partite + 1))
    boot = []
    for _ in range(b):
        scelte = rng.integers(0, n_partite, n_partite)
        idx = np.concatenate([ordine[confini[c]:confini[c + 1]] for c in scelte])
        boot.append(auc(p[idx], y[idx]))
    lo, hi = np.nanquantile(boot, [0.025, 0.975])
    return stima, float(lo), float(hi)


def ic_differenza_auc(pa: np.ndarray, pb: np.ndarray, y: np.ndarray, mi: np.ndarray,
                      n_partite: int, b: int = 200, seme: int = 20260925) -> Tuple[float, float, float]:
    """AUC(a) - AUC(b) con IC per partita (stessi ricampioni per a e b)."""
    rng = np.random.default_rng(seme)
    stima = auc(pa, y) - auc(pb, y)
    ordine = np.argsort(mi, kind="mergesort")
    confini = np.searchsorted(mi[ordine], np.arange(n_partite + 1))
    boot = []
    for _ in range(b):
        scelte = rng.integers(0, n_partite, n_partite)
        idx = np.concatenate([ordine[confini[c]:confini[c + 1]] for c in scelte])
        boot.append(auc(pa[idx], y[idx]) - auc(pb[idx], y[idx]))
    lo, hi = np.nanquantile(boot, [0.025, 0.975])
    return float(stima), float(lo), float(hi)


def calibrazione(p: np.ndarray, y: np.ndarray, n_bin: int = 10,
                 confini: Optional[Sequence[float]] = None) -> List[Dict[str, float]]:
    """Tabella di affidabilita': per decile di p (o confini dati) media prevista,
    frequenza osservata, n."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    if confini is None:
        confini = np.unique(np.quantile(p, np.linspace(0, 1, n_bin + 1)))
    confini = np.asarray(confini, dtype=float)
    b = np.clip(np.searchsorted(confini, p, side="right") - 1, 0, len(confini) - 2)
    out = []
    for k in range(len(confini) - 1):
        m = b == k
        if not m.any():
            continue
        out.append({"da": float(confini[k]), "a": float(confini[k + 1]), "n": int(m.sum()),
                    "prevista": float(p[m].mean()), "osservata": float(y[m].mean())})
    return out


def errore_calibrazione(tab: List[Dict[str, float]]) -> float:
    """ECE: media pesata di |prevista - osservata|."""
    n = sum(r["n"] for r in tab)
    return float(sum(r["n"] * abs(r["prevista"] - r["osservata"]) for r in tab) / max(n, 1))
