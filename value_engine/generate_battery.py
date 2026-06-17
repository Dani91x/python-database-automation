"""
generate_battery.py — genera la batteria di casi (input grezzi -> output Python) per validare
il port TypeScript 1:1, e stampa l'array CDF da embeddare nel TS.
Esegue l'INTERO pipeline (de-vig -> derivazione -> condizionamento -> pricing) sul motore Python.
"""
from __future__ import annotations
import os
import json

from value_engine import markets, goal_timing
from value_engine import bivariate as bv
from value_engine.devig import devig_pair, devig_multiplicative
from value_engine.pricing import price

RF = goal_timing.remaining_frac
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "Telegram bot", "_calc_validation")


def total_case(market, q0, minute, goals, q_opp=None):
    p0 = devig_pair(q0, q_opp) if q_opp else 1.0 / q0
    p = markets.prob_total(market, p0, minute, goals, remaining_frac=RF)
    mp = price(market, p)
    return dict(kind="total", market=market, q0=q0, q_opp=q_opp, minute=minute, goals=goals,
                prob=p, fair=mp.fair_odds, min_back=mp.min_back, max_lay=mp.max_lay)


def score_case(market, qH, qD, qA, qO, qU, minute, gh, ga):
    pH = devig_multiplicative({"H": qH, "D": qD, "A": qA})["H"]
    pO25 = devig_pair(qO, qU)
    p = bv.evaluate(market, p_home=pH, p_over25=pO25, minute=minute, gh=gh, ga=ga,
                    remaining_frac=RF, ht_fraction=goal_timing.first_half_share())
    mp = price(market, p)
    return dict(kind="score", market=market, qH=qH, qD=qD, qA=qA, qO=qO, qU=qU,
                minute=minute, gh=gh, ga=ga,
                prob=p, fair=mp.fair_odds, min_back=mp.min_back, max_lay=mp.max_lay)


cases = []
# --- TOTALI: vari mercati, quote, minuti, gol, con/senza de-vig ---
for mk, q0, qopp in [("U35", 1.30, 3.60), ("O25", 2.00, 1.95), ("O15", 1.40, None),
                     ("U25", 2.05, 1.85), ("HT05", 1.60, 2.45), ("O35", 3.50, None)]:
    for minute, goals in [(0, 0), (8, 1), (17, 1), (30, 0), (44, 0), (60, 2), (75, 1)]:
        if mk == "HT05" and minute > 44:
            continue
        cases.append(total_case(mk, q0, minute, goals, qopp))

# --- SCORE: 1X2/DC/DNB/BTTS, scenari realistici ---
ou = (1.90, 2.00)
for mk in ["H", "D", "A", "BTTS", "BTTS_NO", "DC_1X", "DC_X2", "DNB_H", "DNB_A"]:
    for (qH, qD, qA), (minute, gh, ga) in [
        ((2.10, 3.40, 3.60), (0, 0, 0)),
        ((2.10, 3.40, 3.60), (30, 1, 0)),
        ((1.70, 3.80, 5.00), (55, 0, 1)),
        ((3.20, 3.30, 2.20), (70, 1, 1)),
    ]:
        cases.append(score_case(mk, qH, qD, qA, ou[0], ou[1], minute, gh, ga))

# --- HT 1X2: solo minuto <= 45 (primo tempo), gol = gol del 1o tempo ---
for mk in ["HT_H", "HT_D", "HT_A"]:
    for (qH, qD, qA), (minute, gh, ga) in [
        ((2.10, 3.40, 3.60), (0, 0, 0)),
        ((2.10, 3.40, 3.60), (20, 1, 0)),
        ((1.70, 3.80, 5.00), (35, 0, 1)),
        ((3.20, 3.30, 2.20), (44, 0, 0)),
    ]:
        cases.append(score_case(mk, qH, qD, qA, ou[0], ou[1], minute, gh, ga))

os.makedirs(OUT_DIR, exist_ok=True)
with open(os.path.join(OUT_DIR, "battery.json"), "w", encoding="utf-8") as f:
    json.dump(cases, f, ensure_ascii=False, indent=1)
print(f"[OK] {len(cases)} casi -> {os.path.join(OUT_DIR, 'battery.json')}")

# CDF da embeddare nel TS
cdf = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "data", "goal_time_cdf.json"), encoding="utf-8"))["cdf_by_minute"]
print("\n// --- CDF (incolla in calc.ts) ---")
print("const GOAL_CDF: number[] = [" + ",".join(f"{v:.6f}" for v in cdf) + "];")
