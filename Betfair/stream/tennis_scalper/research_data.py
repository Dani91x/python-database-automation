"""Helper condiviso per la RICERCA sui dati registrati (book + punteggio).

Fornisce: lettura serie book (prezzi + size top) da .raw.jsonl, timeline
punteggio da .score.jsonl, e il modello Markov (O'Malley) per il fair-value.
Usato dagli script/agenti di ricerca per non riscrivere il parsing ogni volta.
"""
from __future__ import annotations

import bisect
import json
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from betfairlightweight import StreamListener

from ..auth import build_client


def load_book(raw_path: str) -> Dict[int, List[Tuple[int, float, float, float, float, float]]]:
    """Ritorna per selection_id una lista (pt_ms, best_back, best_lay, size_back,
    size_lay, ltp) ordinata per tempo."""
    t = build_client(login=False)
    listener = StreamListener(max_latency=None)
    stream = t.streaming.create_historical_generator_stream(
        file_path=raw_path, listener=listener)
    out: Dict[int, List[Tuple[int, float, float, float, float, float]]] = {}
    for books in stream.get_generator()():
        for mb in books:
            pt = mb.publish_time_epoch
            for r in mb.runners:
                ex = r.ex
                if not ex.available_to_back or not ex.available_to_lay:
                    continue
                bb = ex.available_to_back[0]
                bl = ex.available_to_lay[0]
                out.setdefault(int(r.selection_id), []).append(
                    (int(pt), bb.price, bl.price, bb.size, bl.size,
                     r.last_price_traded or (bb.price + bl.price) / 2))
    for k in out:
        out[k].sort()
    return out


def load_scores(score_path: str) -> List[Tuple[int, Dict[str, Any], Dict[str, Any]]]:
    """Ritorna [(pt_ms, home_dict, away_dict)] dal .score.jsonl."""
    sc: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = []
    for line in open(score_path, encoding="utf-8"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        s = rec.get("score") or {}
        sc.append((int(float(rec["t"]) * 1000),
                   s.get("home") or {}, s.get("away") or {}))
    sc.sort()
    return sc


def series_at(series: List[Tuple], ts: int, idx: int = 1) -> Optional[float]:
    """Valore (colonna idx) dell'ultimo sample <= ts."""
    if not series:
        return None
    i = bisect.bisect_right([s[0] for s in series], ts) - 1
    i = max(0, min(i, len(series) - 1))
    return series[i][idx]


# ---------------- MODELLO MARKOV (O'Malley) ----------------
def game_hold(p: float) -> float:
    q = 1 - p
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    base = p**4 + 4*p**4*q + 10*p**4*q*q
    deuce = 20*(p**3)*(q**3)
    return base + deuce*(p*p/(p*p+q*q))


@lru_cache(maxsize=None)
def _tb(a: int, b: int, srv: int, pa: float, pb: float) -> float:
    if a >= 7 and a-b >= 2:
        return 1.0
    if b >= 7 and b-a >= 2:
        return 0.0
    if a >= 6 and b >= 6:
        pp = (pa + (1-pb))/2
        return pp*pp/(pp*pp+(1-pp)*(1-pp))
    p = pa if srv else (1-pb)
    ns = 0 if srv else 1
    return p*_tb(a+1, b, ns, pa, pb) + (1-p)*_tb(a, b+1, ns, pa, pb)


@lru_cache(maxsize=None)
def _set(ga: int, gb: int, srv: int, pa: float, pb: float) -> float:
    if ga >= 6 and ga-gb >= 2:
        return 1.0
    if gb >= 6 and gb-ga >= 2:
        return 0.0
    if ga == 6 and gb == 6:
        return _tb(0, 0, 1, pa, pb)
    hold = game_hold(pa) if srv else (1-game_hold(pb))
    return hold*_set(ga+1, gb, 0 if srv else 1, pa, pb) + \
        (1-hold)*_set(ga, gb+1, 0 if srv else 1, pa, pb)


@lru_cache(maxsize=None)
def match_win(sa: int, sb: int, ga: int, gb: int, srv: int,
              pa: float, pb: float, best_of: int = 5) -> float:
    need = best_of//2 + 1
    if sa >= need:
        return 1.0
    if sb >= need:
        return 0.0
    ps = _set(ga, gb, srv, pa, pb)
    return ps*match_win(sa+1, sb, 0, 0, 1, pa, pb, best_of) + \
        (1-ps)*match_win(sa, sb+1, 0, 0, 1, pa, pb, best_of)


def calibrate(prematch_prob_home: float, best_of: int = 5,
              base: float = 0.63) -> Tuple[float, float]:
    lo, hi = -0.25, 0.25
    for _ in range(40):
        d = (lo+hi)/2
        if match_win(0, 0, 0, 0, 1, base+d, base-d, best_of) < prematch_prob_home:
            lo = d
        else:
            hi = d
    d = (lo+hi)/2
    return base+d, base-d
