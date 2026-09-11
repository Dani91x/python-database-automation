"""omega_validate — BANCO DI VALIDAZIONE dei modelli di probabilità (§15, 11/09).

Domanda: "quando il modello dice che un risultato ha l'1 % di probabilità, esce
davvero l'1 % delle volte?" — per Omega è la sola cosa che conta: banca risultati
rari e paga tutta la liability quando escono. Metriche PURE (nessun I/O):

  • ``binary_metrics``: log-loss e Brier di previsioni (p, esito 0/1);
  • ``reliability``: tabella di affidabilità per fascia di P (P media vs frequenza reale);
  • ``multiclass_log_loss``: log-loss di una distribuzione sui risultati esatti;
  • ``tail_calibration``: sulla CODA (risultati con P ≤ p_max, quelli che Omega banca)
    quante volte sono usciti rispetto a quante il modello prevedeva — il numero
    che decide se il lay è a valore atteso ≥ 0.

Lo strumento ``tools/omega_validate_models.py`` applica queste metriche ai modelli
sullo storico (gol con minuto) e produce un rapporto. Le funzioni qui sono
riusabili anche sulle registrazioni REC e sui trade regolati.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

Score = Tuple[int, int]
EPS = 1e-9


def _clip(p: float) -> float:
    return min(1.0 - EPS, max(EPS, float(p)))


def binary_metrics(preds: Iterable[Tuple[float, int]]) -> Dict[str, Any]:
    """log-loss, Brier, P media e tasso reale di previsioni binarie (p, esito)."""
    n = 0
    ll = 0.0
    br = 0.0
    p_sum = 0.0
    hits = 0
    for p, y in preds:
        q = _clip(p)
        y = 1 if y else 0
        ll += -(y * math.log(q) + (1 - y) * math.log(1.0 - q))
        br += (q - y) ** 2
        p_sum += q
        hits += y
        n += 1
    if n == 0:
        return {"n": 0, "log_loss": None, "brier": None, "p_mean": None, "hit_rate": None}
    return {"n": n, "log_loss": round(ll / n, 6), "brier": round(br / n, 6),
            "p_mean": round(p_sum / n, 6), "hit_rate": round(hits / n, 6)}


def reliability(preds: Iterable[Tuple[float, int]],
                edges: Sequence[float] = (0.0, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)) -> List[Dict[str, Any]]:
    """Tabella di affidabilità: per fascia [lo, hi) P media prevista vs frequenza reale."""
    bins: List[Dict[str, Any]] = [{"lo": edges[i], "hi": edges[i + 1], "n": 0, "p_sum": 0.0, "hits": 0}
                                  for i in range(len(edges) - 1)]
    for p, y in preds:
        q = float(p)
        for b in bins:
            if b["lo"] <= q < b["hi"] or (q >= 1.0 and b["hi"] >= 1.0):
                b["n"] += 1
                b["p_sum"] += q
                b["hits"] += 1 if y else 0
                break
    out = []
    for b in bins:
        n = b["n"]
        out.append({"lo": b["lo"], "hi": b["hi"], "n": n,
                    "p_mean": round(b["p_sum"] / n, 6) if n else None,
                    "hit_rate": round(b["hits"] / n, 6) if n else None,
                    "hits": b["hits"]})
    return out


def multiclass_log_loss(cases: Iterable[Tuple[Dict[Score, float], Score]]) -> Optional[float]:
    """Log-loss media di distribuzioni sui risultati esatti (P del risultato uscito)."""
    n = 0
    tot = 0.0
    for probs, actual in cases:
        p = probs.get(tuple(actual), 0.0)
        tot += -math.log(_clip(p))
        n += 1
    return round(tot / n, 6) if n else None


def _bootstrap_ratio(per_case: Sequence[Tuple[float, int]], *, b: int = 300, seed: int = 11
                     ) -> Optional[Tuple[float, float]]:
    """IC 90 % (bootstrap per PARTITA) del rapporto usciti/previsti: i risultati
    della stessa partita sono dipendenti, quindi si ricampionano le partite."""
    if len(per_case) < 20:
        return None
    import random
    rng = random.Random(seed)
    m = len(per_case)
    ratios = []
    for _ in range(b):
        e = 0.0
        h = 0
        for _ in range(m):
            ei, hi = per_case[rng.randrange(m)]
            e += ei
            h += hi
        if e > 0:
            ratios.append(h / e)
    if len(ratios) < 10:
        return None
    ratios.sort()
    return round(ratios[int(0.05 * len(ratios))], 4), round(ratios[min(len(ratios) - 1, int(0.95 * len(ratios)))], 4)


def tail_calibration(cases: Iterable[Tuple[Dict[Score, float], Score]], *, p_max: float = 0.02,
                     p_min: float = 1.0 / 120.0, reachable_only: bool = True) -> Dict[str, Any]:
    """Sulla CODA: per ogni caso, tutti i risultati con P ≤ p_max sono "lay
    candidati"; conta quanti ne sono usciti e quanti il modello prevedeva
    (somma delle P). ``ratio`` = usciti / previsti: 1 = calibrato, > 1 = il
    modello sottostima la coda (i lay perdono più del previsto).
    ``ratio_ci`` = IC 90 % bootstrap per partita. ``lay_*`` = la SOLA selezione
    che Omega farebbe: il risultato meno probabile fra quelli BANCABILI, cioè con
    P fra ``p_min`` (≈ 1/price_max: sotto, la quota non esiste a mercato) e
    ``p_max`` — è il numero che conta per il P&L, non la media della coda (§16 F17)."""
    n = 0
    expected = 0.0
    hits = 0
    per_case: List[Tuple[float, int]] = []
    lay_expected = 0.0
    lay_hits = 0
    lay_n = 0
    lay_per_case: List[Tuple[float, int]] = []
    for probs, actual in cases:
        e_i = 0.0
        h_i = 0
        best = None
        for score, p in probs.items():
            if p <= p_max and p > 0:
                n += 1
                e_i += p
                if tuple(score) == tuple(actual):
                    h_i += 1
                if p >= p_min and (best is None or p < best[1]):
                    best = (score, p)
        expected += e_i
        hits += h_i
        if e_i > 0:
            per_case.append((e_i, h_i))
        if best is not None:
            lay_n += 1
            lay_expected += best[1]
            lh = 1 if tuple(best[0]) == tuple(actual) else 0
            lay_hits += lh
            lay_per_case.append((best[1], lh))
    ratio = (hits / expected) if expected > 0 else None
    lay_ratio = (lay_hits / lay_expected) if lay_expected > 0 else None
    return {"n": n, "expected_hits": round(expected, 4), "hits": hits,
            "ratio": round(ratio, 4) if ratio is not None else None, "p_max": p_max, "p_min": p_min,
            "ratio_ci": _bootstrap_ratio(per_case),
            "lay_n": lay_n, "lay_expected": round(lay_expected, 4), "lay_hits": lay_hits,
            "lay_ratio": round(lay_ratio, 4) if lay_ratio is not None else None,
            "lay_ratio_ci": _bootstrap_ratio(lay_per_case)}


def compare_models(named_cases: Dict[str, List[Tuple[Dict[Score, float], Score]]], *,
                   p_max: float = 0.02, p_min: float = 1.0 / 120.0) -> Dict[str, Dict[str, Any]]:
    """Per ogni modello: log-loss multiclasse + calibrazione della coda."""
    out: Dict[str, Dict[str, Any]] = {}
    for name, cases in named_cases.items():
        out[name] = {"n": len(cases), "log_loss": multiclass_log_loss(cases),
                     "tail": tail_calibration(cases, p_max=p_max, p_min=p_min)}
    return out


def blend_probs(dists: Sequence[Dict[Score, float]], weights: Optional[Sequence[float]] = None) -> Dict[Score, float]:
    """Media (pesata) di distribuzioni sui risultati — per confrontare anche il
    "modello + dati" oltre ai singoli."""
    if not dists:
        return {}
    w = list(weights) if weights else [1.0] * len(dists)
    tot_w = sum(w) or 1.0
    keys = set()
    for d in dists:
        keys |= set(d.keys())
    out = {k: sum(wi * d.get(k, 0.0) for wi, d in zip(w, dists)) / tot_w for k in keys}
    s = sum(out.values()) or 1.0
    return {k: v / s for k, v in out.items()}
