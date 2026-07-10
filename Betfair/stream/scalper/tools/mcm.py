"""Parser MCM nativo per i raw.jsonl registrati (_live_raw).

Semantica dei messaggi (verificata sui dati):
  - op="mcm", pt=publish time ms, mc=[{id, img?, marketDefinition?, rc=[...]}]
  - rc.atb / rc.atl: DELTA DI LIVELLO [prezzo, size]; size==0 -> rimuovi livello,
    altrimenti size ASSOLUTA nuova a quel prezzo.
  - rc.trd: CUMULATIVO per prezzo [prezzo, volume_totale]; il delta scambiato
    dall'ultimo update e' (nuovo - vecchio), mai negativo.
  - rc.ltp / rc.tv: last traded price / total volume.
  - mc.img==True -> immagine completa: azzera i ladder del mercato.

Ladder tick Betfair (CLASSIC) con indice frazionario per regressioni.
"""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional, Tuple

BANDS = [
    (1.01, 2.0, 0.01),
    (2.0, 3.0, 0.02),
    (3.0, 4.0, 0.05),
    (4.0, 6.0, 0.10),
    (6.0, 10.0, 0.20),
    (10.0, 20.0, 0.50),
    (20.0, 30.0, 1.0),
    (30.0, 50.0, 2.0),
    (50.0, 100.0, 5.0),
    (100.0, 1000.0, 10.0),
]

_BASE: List[Tuple[float, float, float, float]] = []  # (lo, hi, step, base_idx)
_idx = 0.0
for _lo, _hi, _st in BANDS:
    _BASE.append((_lo, _hi, _st, _idx))
    _idx += round((_hi - _lo) / _st)


def frac_tick(price: float) -> Optional[float]:
    """Indice tick frazionario (continuo) di un prezzo sulla ladder CLASSIC."""
    if price is None or price < 1.01 or price > 1000.0:
        return None
    for lo, hi, st, base in _BASE:
        if price <= hi + 1e-9:
            return base + (price - lo) / st
    return None


class RunnerState:
    __slots__ = ("atb", "atl", "trd", "ltp")

    def __init__(self) -> None:
        self.atb: Dict[float, float] = {}
        self.atl: Dict[float, float] = {}
        self.trd: Dict[float, float] = {}
        self.ltp: Optional[float] = None

    def reset(self) -> None:
        self.atb.clear()
        self.atl.clear()
        self.trd.clear()
        self.ltp = None

    def best_back(self) -> Tuple[Optional[float], float]:
        if not self.atb:
            return None, 0.0
        p = max(self.atb)
        return p, self.atb[p]

    def best_lay(self) -> Tuple[Optional[float], float]:
        if not self.atl:
            return None, 0.0
        p = min(self.atl)
        return p, self.atl[p]


class MarketState:
    __slots__ = ("market_id", "market_type", "status", "in_play", "bet_delay",
                 "version", "sort_priority", "runner_status", "runners",
                 "inplay_since_pt", "bet_delay_seen")

    def __init__(self, market_id: str) -> None:
        self.market_id = market_id
        self.market_type: Optional[str] = None
        self.status: Optional[str] = None
        self.in_play: bool = False
        self.bet_delay: int = 0
        self.version: Optional[int] = None
        self.sort_priority: Dict[int, int] = {}
        self.runner_status: Dict[int, str] = {}
        self.runners: Dict[int, RunnerState] = {}
        self.inplay_since_pt: Optional[int] = None
        self.bet_delay_seen: Dict[str, set] = {"prematch": set(), "inplay": set()}

    def runner(self, rid: int) -> RunnerState:
        r = self.runners.get(rid)
        if r is None:
            r = RunnerState()
            self.runners[rid] = r
        return r

    def sid_by_priority(self, want: int) -> Optional[int]:
        for sid, sp in self.sort_priority.items():
            if sp == want:
                return sid
        return None


def replay(path: str,
           on_update: Callable[[int, MarketState, Dict[int, Dict[float, float]]], None],
           market_types: Optional[set] = None) -> Dict[str, MarketState]:
    """Replay del raw: chiama on_update(pt, market, trd_delta_per_runner) a ogni
    messaggio che tocca un mercato (dopo aver applicato i delta).

    trd_delta_per_runner: {selection_id: {prezzo: delta_volume}} SOLO del msg.
    """
    markets: Dict[str, MarketState] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("op") != "mcm":
                continue
            pt = msg.get("pt")
            for mc in msg.get("mc", []) or []:
                mid = mc.get("id")
                if mid is None:
                    continue
                m = markets.get(mid)
                if m is None:
                    m = MarketState(mid)
                    markets[mid] = m
                md = mc.get("marketDefinition")
                if md is not None:
                    m.market_type = md.get("marketType", m.market_type)
                    m.status = md.get("status", m.status)
                    was_inplay = m.in_play
                    m.in_play = bool(md.get("inPlay", False))
                    if m.in_play and not was_inplay and m.inplay_since_pt is None:
                        m.inplay_since_pt = pt
                    m.bet_delay = int(md.get("betDelay", 0) or 0)
                    m.bet_delay_seen["inplay" if m.in_play else "prematch"].add(m.bet_delay)
                    m.version = md.get("version", m.version)
                    for rd in md.get("runners", []) or []:
                        rid = int(rd.get("id"))
                        m.sort_priority[rid] = int(rd.get("sortPriority", 0) or 0)
                        m.runner_status[rid] = rd.get("status", "")
                if market_types is not None and m.market_type not in market_types:
                    continue
                if mc.get("img"):
                    for r in m.runners.values():
                        r.reset()
                trd_delta: Dict[int, Dict[float, float]] = {}
                for rc in mc.get("rc", []) or []:
                    rid = int(rc.get("id"))
                    r = m.runner(rid)
                    for p, s in rc.get("atb", []) or []:
                        if s == 0:
                            r.atb.pop(p, None)
                        else:
                            r.atb[p] = s
                    for p, s in rc.get("atl", []) or []:
                        if s == 0:
                            r.atl.pop(p, None)
                        else:
                            r.atl[p] = s
                    for p, v in rc.get("trd", []) or []:
                        old = r.trd.get(p, 0.0)
                        d = v - old
                        if d > 1e-9:
                            trd_delta.setdefault(rid, {})[p] = d
                        r.trd[p] = v
                    if rc.get("ltp") is not None:
                        r.ltp = rc["ltp"]
                on_update(pt, m, trd_delta)
    return markets
