"""
goal_timing.py — frazione di gol attesi nel tempo rimanente, dalla CDF empirica reale
(value_engine/data/goal_time_cdf.json, prodotta da calibrate.py).

Sostituisce l'ipotesi lineare (T-t)/T con la curva vera (2o tempo + finale piu' carichi).
Se il file manca, ricade sul lineare (degradazione sicura).
"""
from __future__ import annotations
import os
import json
import logging

_log = logging.getLogger(__name__)
_CDF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "goal_time_cdf.json")
_cdf: list[float] | None = None
_loaded = False


def _load() -> list[float] | None:
    global _cdf, _loaded
    if not _loaded:
        _loaded = True
        try:
            with open(_CDF_PATH, encoding="utf-8") as f:
                data = json.load(f)
            c = data["cdf_by_minute"]
            if isinstance(c, list) and len(c) == 91 and abs(c[90] - 1.0) < 1e-6:
                _cdf = c
            else:
                _log.warning("goal_timing: CDF malformata, uso fallback lineare")
        except Exception as exc:
            _log.warning("goal_timing: CDF non caricata (%s), uso fallback lineare", exc)
            _cdf = None
    return _cdf


def first_half_share() -> float:
    """Frazione di gol-partita che cade nel 1o tempo = cdf[45] (per scalare i lambda all'HT).
    Fallback 0.5 (lineare) se la CDF non c'e'."""
    cdf = _load()
    return cdf[45] if cdf is not None else 0.5


def remaining_frac(t: float, T: float = 90.0) -> float:
    """Frazione di gol del PERIODO che si verifica DOPO il minuto t (0..1).
    T=90 -> intera partita; T~45 -> primo tempo. Fallback lineare se la CDF non c'e'.
    NB: usa floor(t) (int(t)), NON round(): garantisce parita' 1:1 col port TypeScript
    (Python round() usa banker's rounding, JS Math.round no -> divergerebbero sui .5)."""
    cdf = _load()
    if cdf is None:
        return max(0.0, min(1.0, (T - t) / T)) if T > 0 else 0.0
    ti = int(t) if t > 0 else 0          # floor (t >= 0 in pratica)
    if T <= 45.5:                         # mercati primo tempo (lo stoppage di 1T conta a 45)
        ti = min(ti, 45)
        c45 = cdf[45]
        if c45 <= 0:
            return max(0.0, (45.0 - t) / 45.0)
        return max(0.0, min(1.0, (c45 - cdf[ti]) / c45))
    if ti >= 90:                          # 90'+ recupero: regolamentari finite -> ~0 (conservativo)
        return 0.0
    return max(0.0, min(1.0, 1.0 - cdf[ti]))
