"""
VALIDAZIONE FINALE della strategia profittevole (line-shopping alla chiusura).
Config scelta su DEV, validata su HOLDOUT. Stabilita' anno-per-anno + drawdown + Kelly.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy import load, HOLDOUT


def build(df, thr, mo, Mo, markets, book="Maximum_closing"):
    d = df[df["market"].isin(markets)].copy()
    oc = f"odd_{book}"
    d = d[d[oc].notna() & (d[oc] >= mo) & (d[oc] <= Mo) & d["fair_pin"].notna()]
    edge = d[oc] * d["fair_pin"] - 1.0          # CLV ex-ante (info disponibile alla chiusura)
    d = d[edge >= thr].copy()
    d["edge"] = edge.loc[d.index]
    d["pnl_flat"] = np.where(d["y"] == 1, d[oc] - 1.0, -1.0)
    # Kelly frazionario (1/4) con prob = fair_pin (stima sharp)
    b = d[oc] - 1.0
    k = (d["fair_pin"] * b - (1 - d["fair_pin"])) / b
    d["kstake"] = np.clip(k * 0.25, 0, 0.05)
    d["pnl_kelly"] = np.where(d["y"] == 1, d["kstake"] * (d[oc] - 1.0), -d["kstake"])
    d["odd"] = d[oc]
    return d.sort_values("date")


def report(d, name):
    n = len(d); roi = 100 * d["pnl_flat"].sum() / n
    clv = 100 * d["edge"].mean()
    # drawdown su equity flat
    eq = d["pnl_flat"].cumsum()
    peak = eq.cummax(); dd = (eq - peak).min()
    # Kelly
    kst = d["kstake"].sum(); kroi = 100 * d["pnl_kelly"].sum() / kst if kst else 0
    print(f"\n### {name}: n={n}  ROI_flat={roi:+.2f}%  PnL_flat={d['pnl_flat'].sum():+.1f}u  "
          f"hit={100*d['y'].mean():.1f}%  avgodd={d['odd'].mean():.2f}  CLV={clv:+.2f}%  maxDD={dd:.1f}u  ROI_kelly={kroi:+.2f}%")
    return roi


if __name__ == "__main__":
    df = load()
    # CONFIG LOCKED (scelta guardando solo il DEV in strategy3): soglia 0.08, quote 1.5-4.5, tutti i mercati
    THR, MO, MOX = 0.08, 1.5, 4.5
    MARKETS = ["H", "D", "A", "O25", "U25"]

    print("="*90)
    print(f"STRATEGIA LINE-SHOPPING CLOSING  | soglia CLV>={THR}  quote {MO}-{MOX}  mercati={MARKETS}")
    print("Selezione usa SOLO info a bet-time (chiusura): best price vs fair Pinnacle. Leak-free.")
    print("="*90)

    d = build(df, THR, MO, MOX, MARKETS)
    dev = d[d["date"] < HOLDOUT]; hold = d[d["date"] >= HOLDOUT]
    report(dev, "DEV (2012..2020-06, scelta config)")
    report(hold, "HOLDOUT (2020-07..2025, MAI usato per scegliere)")
    report(d, "FULL")

    print("\n--- Stabilita' ANNO-PER-ANNO (ROI flat) ---")
    d["year"] = d["date"].dt.year
    for yr, g in d.groupby("year"):
        roi = 100 * g["pnl_flat"].sum() / len(g)
        print(f"   {yr}: n={len(g):5d}  ROI={roi:+6.2f}%  PnL={g['pnl_flat'].sum():+7.1f}u  hit={100*g['y'].mean():4.1f}%")

    print("\n--- Per mercato (HOLDOUT) ---")
    for mk, g in hold.groupby("market"):
        print(f"   {mk:5s} n={len(g):5d}  ROI={100*g['pnl_flat'].sum()/len(g):+6.2f}%  CLV={100*g['edge'].mean():+5.2f}%  hit={100*g['y'].mean():.1f}%")

    print("\n--- Confronto: stessa strategia ma SENZA shopping (bet a Pinnacle_closing) ---")
    d2 = build(df, THR, MO, MOX, MARKETS, book="Pinnacle_closing")
    h2 = d2[d2["date"] >= HOLDOUT]
    if len(h2):
        report(h2, "HOLDOUT @ Pinnacle_closing (no shopping)")
    else:
        print("   (nessun bet: a Pinnacle stesso non esiste discrepanza vs se' stesso)")

    # salva i bet della strategia per ispezione
    d.to_pickle(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "strategy_final_bets.pkl"))
    print("\nSalvati i bet -> cache/strategy_final_bets.pkl")
