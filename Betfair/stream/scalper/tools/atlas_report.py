"""Report dell'Atlante v0: esiti per cella di contesto.

Domanda a cui risponde: i gate attuali (S16) selezionano davvero i momenti
migliori? E quali celle fanno meglio?
"""
from __future__ import annotations

import glob
import json
import os
import statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

rows = []
for f in glob.glob(os.path.join(HERE, "atlas_v0", "*.jsonl")):
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
rows = [r for r in rows if r["outcome"] not in ("eof",)]
print(f"campioni totali: {len(rows)} su {len(set(r['event'] for r in rows))} partite\n")

BAD = ("suspend", "suspend_pre", "goal")


def agg(sel, name):
    n = len(sel)
    if n == 0:
        print(f"{name:<46} n=0")
        return
    fills = [r for r in sel if r["outcome"].startswith("fill")]
    t2 = [r["t_out_s"] for r in fills if r["t_out_s"] is not None]
    f30 = sum(1 for t in t2 if t <= 30)
    f60 = sum(1 for t in t2 if t <= 60)
    bad = sum(1 for r in sel if r["outcome"] in BAD)
    stp = sum(1 for r in sel if r["outcome"] == "stop2")
    tout = sum(1 for r in sel if r["outcome"] == "timeout")
    print(f"{name:<46} n={n:>6}  fill={len(fills)/n*100:5.1f}%  "
          f"fill<=30s={f30/n*100:5.1f}%  <=60s={f60/n*100:5.1f}%  "
          f"t2fill_med={statistics.median(t2) if t2 else '-':>5}s  "
          f"stop2={stp/n*100:4.1f}%  gol/susp={bad/n*100:4.1f}%  "
          f"timeout={tout/n*100:4.1f}%")


def q_ok(r):
    return r["queue_frac"] is not None and r["queue_frac"] <= 0.35 \
        and r["level_max"] >= 60


def liq_ok(r):
    return r["size_back"] >= 50 and r["size_lay"] >= 50


print("=== BASELINE (tutti i momenti campionati, book valido) ===")
agg(rows, "TUTTO")
agg([r for r in rows if liq_ok(r)], "liquidita' minima (50/50)")

print("\n=== GATE ATTUALI (S16) scomposti ===")
agg([r for r in rows if r["spread_ticks"] <= 1.01 and liq_ok(r)], "spread<=1")
agg([r for r in rows if r["cadence_ok"] and liq_ok(r)], "cadenza attiva")
agg([r for r in rows if q_ok(r) and liq_ok(r)], "coda<=35% del livello")
agg([r for r in rows if r["spread_ticks"] <= 1.01 and r["cadence_ok"]
     and q_ok(r) and liq_ok(r)], ">>> S16 COMPLETO (3 gate)")

print("\n=== CELLE: linea k = (linea - gol attuali) [con 3 gate] ===")
for k in (0.5, 1.5, 2.5, 3.5):
    agg([r for r in rows if r["spread_ticks"] <= 1.01 and r["cadence_ok"]
         and q_ok(r) and liq_ok(r) and r["line_k"] == k], f"S16 & k={k}")

print("\n=== CELLE: decay osservato (5 min) [con 3 gate] ===")
agg([r for r in rows if r["spread_ticks"] <= 1.01 and r["cadence_ok"]
     and q_ok(r) and liq_ok(r) and r["decay_5m_ticks"] is not None
     and r["decay_5m_ticks"] <= -1], "S16 & decay <= -1 tick/5m (scende)")
agg([r for r in rows if r["spread_ticks"] <= 1.01 and r["cadence_ok"]
     and q_ok(r) and liq_ok(r) and r["decay_5m_ticks"] is not None
     and r["decay_5m_ticks"] > 0], "S16 & decay > 0 (sale: controsenso)")

print("\n=== CELLE: ritmo del traded [con 3 gate] ===")
agg([r for r in rows if r["spread_ticks"] <= 1.01 and r["cadence_ok"]
     and q_ok(r) and liq_ok(r) and r["trd_rate_eur_min"] >= 100],
    "S16 & traded>=100 EUR/min")
agg([r for r in rows if r["spread_ticks"] <= 1.01 and r["cadence_ok"]
     and q_ok(r) and liq_ok(r) and r["trd_rate_eur_min"] < 100],
    "S16 & traded<100 EUR/min")

print("\n=== LA CELLA D'ORO CANDIDATA (S16 + decay giusto + traded vivo) ===")
gold = [r for r in rows if r["spread_ticks"] <= 1.01 and r["cadence_ok"]
        and q_ok(r) and liq_ok(r)
        and r["decay_5m_ticks"] is not None and r["decay_5m_ticks"] <= -1
        and r["trd_rate_eur_min"] >= 100]
agg(gold, "ORO: S16 & decay<=-1 & traded>=100")
ev = defaultdict(int)
for r in gold:
    ev[r["event"]] += 1
print("  distribuzione per partita:", dict(sorted(ev.items())))
