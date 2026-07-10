"""ATLANTE v0 — mining dei momenti di ingresso sniper dall'archivio raw.

Per OGNI istante campionato (ogni 10s in-play, per ogni linea Under con book
valido) simula l'operazione sniper col modello di esecuzione certificato
(taker al best back; uscita LAY resting a -1 tick con PIQ = size visibile al
prezzo; fill sul traded DIMEZZATO a prezzi <= uscita; delay 5.12s; SUSPEND =
morte dell'ordine) e registra FEATURES + ESITO:

  esiti: fill (tick incassato, con t2fill), stop2 (bb sale 2 tick prima del
  fill), suspend (mercato sospeso prima del fill: quasi sempre gol),
  goal (gol dal feed prima del fill), timeout (300s senza fill).

Output: atlas_v0.jsonl (un campione per riga) + report aggregato per cella.
Uso: python atlas_v0.py <event_id> | all
"""
from __future__ import annotations

import json
import os
import sys
from collections import deque
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
THETA = os.path.join(os.path.dirname(HERE), "theta_decay")
sys.path.insert(0, THETA)

from mcm import BANDS, MarketState, frac_tick, replay  # noqa: E402

REPO = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
DATA = os.path.join(REPO, "_live_raw")
OUT = os.path.join(HERE, "atlas_v0")

OU_LINES = {f"OVER_UNDER_{n}5": n + 0.5 for n in range(0, 9)}
SAMPLE_EVERY_MS = 10_000
DELAY_MS = 5_120          # betDelay 5s + place latency 0.12 (certificato)
TIMEOUT_MS = 300_000
STAKE = 10.0
GOAL_HORIZON_MS = 120_000

# ladder completa dei prezzi validi (per fare -1 tick esatto)
_PRICES: List[float] = []
for _lo, _hi, _st in BANDS:
    p = _lo
    while p < _hi - 1e-9:
        _PRICES.append(round(p, 2))
        p += _st
_PRICES.append(1000.0)
_P_IDX = {p: i for i, p in enumerate(_PRICES)}


def tick_away(price: float, n: int) -> Optional[float]:
    i = _P_IDX.get(round(price, 2))
    if i is None:
        return None
    j = i + n
    if j < 0 or j >= len(_PRICES):
        return None
    return _PRICES[j]


def load_scores(event_id: str):
    path = os.path.join(DATA, event_id, f"{event_id}.scores.jsonl")
    rows = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("ts_ms") is None:
                    continue
                rows.append((int(r["ts_ms"]), r.get("minute"),
                             int(r.get("score_home") or 0),
                             int(r.get("score_away") or 0)))
    rows.sort()
    return rows


def make_score_fn(rows):
    def at(ts: float):
        goals, minute = 0, None
        for t, m, sh, sa in rows:
            if t > ts:
                break
            goals = sh + sa
            if m is not None:
                minute = m
        return goals, minute
    return at


class _Track:
    """Stato microstruttura per il runner Under di un mercato."""

    __slots__ = ("prev_bb", "level_max", "dns", "mid_hist", "trd_win",
                 "last_sample", "samples_open")

    def __init__(self):
        self.prev_bb = None
        self.level_max = 0.0
        self.dns = deque(maxlen=32)
        self.mid_hist = deque(maxlen=64)     # (ts, frac_tick(mid)) ogni ~10s
        self.trd_win = deque()               # (ts, eur) finestra 60s
        self.last_sample = 0
        self.samples_open: List[dict] = []


def run_event(event_id: str) -> int:
    raw = os.path.join(DATA, event_id, f"{event_id}.raw.jsonl")
    if not os.path.isfile(raw):
        return 0
    score_at = make_score_fn(load_scores(event_id))
    tracks: Dict[str, _Track] = {}
    done: List[dict] = []

    def close(s: dict, ts: float, outcome: str) -> None:
        s["outcome"] = outcome
        s["t_out_s"] = round((ts - s["ts"]) / 1000.0, 1)
        done.append(s)

    def on_update(pt, m: MarketState, trd_delta) -> None:
        if m.market_type not in OU_LINES:
            return
        under = m.sid_by_priority(1)
        if under is None:
            return
        tr = tracks.get(m.market_id)
        if tr is None:
            tr = _Track()
            tracks[m.market_id] = tr
        r = m.runners.get(under)
        if r is None:
            return
        bb, sb = r.best_back()
        bl, sl = r.best_lay()
        open_mkt = (m.status == "OPEN")

        # ---- microstruttura ----
        if bb is not None and open_mkt:
            if tr.prev_bb is not None and bb < tr.prev_bb - 1e-9:
                tr.dns.append(pt)
                tr.level_max = sb or 0.0
            elif tr.prev_bb is not None and bb > tr.prev_bb + 1e-9:
                tr.level_max = sb or 0.0
            else:
                tr.level_max = max(tr.level_max, sb or 0.0)
            tr.prev_bb = bb
        if bb and bl:
            ftm = frac_tick((bb + bl) / 2.0)
            if ftm is not None and (not tr.mid_hist
                                    or pt - tr.mid_hist[-1][0] >= 10_000):
                tr.mid_hist.append((pt, ftm))
        d_eur = sum((trd_delta.get(under) or {}).values())
        if d_eur > 0:
            tr.trd_win.append((pt, d_eur))
        while tr.trd_win and pt - tr.trd_win[0][0] > 60_000:
            tr.trd_win.popleft()

        goals_now, minute_now = score_at(pt)

        # ---- avanza i campioni APERTI (simulazione uscita) ----
        still = []
        for s in tr.samples_open:
            if pt < s["ts"] + DELAY_MS:
                # ordine non ancora al mercato
                if not open_mkt:
                    close(s, pt, "suspend_pre")
                    continue
                still.append(s)
                continue
            if not s.get("armed"):
                # arrivo al mercato: cross check + PIQ congelata
                s["armed"] = True
                if bl is not None and bl <= s["exit_price"] + 1e-9:
                    close(s, pt, "fill_cross")
                    continue
                s["piq"] = float((r.atb.get(s["exit_price"]) or 0.0))
                s["fill_acc"] = 0.0
            if not open_mkt:
                close(s, pt, "suspend")
                continue
            g, _ = score_at(pt)
            if g > s["goals0"]:
                close(s, pt, "goal")
                continue
            # stop 2 tick: bb salito di >=2 tick sopra l'entry
            if bb is not None and s["stop_price"] is not None \
                    and bb >= s["stop_price"] - 1e-9:
                close(s, pt, "stop2")
                continue
            # fill: traded DIMEZZATO a prezzi <= exit_price
            dd = trd_delta.get(under) or {}
            for p, v in dd.items():
                if p <= s["exit_price"] + 1e-9:
                    s["fill_acc"] += v / 2.0
            if s["fill_acc"] >= s["piq"] + STAKE:
                close(s, pt, "fill")
                continue
            if pt - s["ts"] > TIMEOUT_MS:
                close(s, pt, "timeout")
                continue
            still.append(s)
        tr.samples_open = still

        # ---- nuovo campione ogni 10s (book valido, in-play, OPEN) ----
        if (not m.in_play or not open_mkt or bb is None or bl is None
                or pt - tr.last_sample < SAMPLE_EVERY_MS):
            return
        tr.last_sample = pt
        fb, fl = frac_tick(bb), frac_tick(bl)
        if fb is None or fl is None:
            return
        spread = round(fl - fb, 2)
        exit_price = tick_away(bb, -1)
        stop_price = tick_away(bb, +2)
        if exit_price is None:
            return
        recent = [t for t in tr.dns if pt - t <= 240_000]
        decay5 = None
        for t0, f0 in tr.mid_hist:
            if pt - t0 <= 300_000:
                decay5 = round((fb + fl) / 2.0 - f0, 2)
                break
        line_val = OU_LINES[m.market_type]
        s = {
            "event": event_id, "market": m.market_type, "ts": pt,
            "price": bb, "spread_ticks": spread,
            "queue_frac": round((sb or 0.0) / tr.level_max, 3)
            if tr.level_max > 0 else None,
            "level_max": round(tr.level_max, 1),
            "size_back": round(sb or 0.0, 1), "size_lay": round(sl or 0.0, 1),
            "n_dn_240s": len(recent),
            "s_since_dn": round((pt - recent[-1]) / 1000.0, 1) if recent else None,
            "cadence_ok": len(recent) >= 2 and recent
            and (pt - recent[-1]) <= 90_000,
            "decay_5m_ticks": decay5,
            "trd_rate_eur_min": round(sum(v for _, v in tr.trd_win), 1),
            "line_k": round(line_val - goals_now, 1),
            "goals0": goals_now, "minute": minute_now,
            "exit_price": exit_price, "stop_price": stop_price,
        }
        tr.samples_open.append(s)

    replay(raw, on_update, market_types=set(OU_LINES))
    # chiudi i campioni rimasti aperti a fine registrazione
    for tr in tracks.values():
        for s in tr.samples_open:
            s["outcome"] = "eof"
            s["t_out_s"] = None
            done.append(s)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{event_id}.jsonl"), "w",
              encoding="utf-8") as fh:
        for s in done:
            s.pop("armed", None)
            s.pop("fill_acc", None)
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"{event_id}: {len(done)} campioni", flush=True)
    return len(done)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "all":
        evs = [d for d in sorted(os.listdir(DATA))
               if not d.startswith("_")
               and os.path.isfile(os.path.join(DATA, d, f"{d}.raw.jsonl"))]
        tot = 0
        for e in evs:
            tot += run_event(e)
        print("TOTALE campioni:", tot)
    else:
        run_event(arg)
