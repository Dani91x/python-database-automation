"""Avenue F/G/H: line-shopping closing, favorite-longshot, modello vs closing."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy import load, eval_strategy, HOLDOUT


def show(df, label, **kw):
    d = eval_strategy(df, **kw)
    dev = d[d["date"] < HOLDOUT]; hold = d[d["date"] >= HOLDOUT]
    def line(tag, x):
        if len(x) == 0: return f"   {tag:9s} n=0"
        clv = x["clv"].dropna()
        return (f"   {tag:9s} n={len(x):5d}  ROI={100*x['pnl'].sum()/x['stake'].sum():+6.2f}%  "
                f"hit={100*x['y'].mean():4.1f}%  avgodd={x.filter(like='odd_').iloc[:,0].mean():.2f}  "
                f"CLV={100*clv.mean() if len(clv) else float('nan'):+5.2f}%  CLV+={100*(clv>0).mean() if len(clv) else float('nan'):4.1f}%")
    print(f"\n[{label}] {kw}")
    for tag, x in [("DEV", dev), ("HOLDOUT", hold), ("TOT", d)]:
        print(line(tag, x))
    return d


if __name__ == "__main__":
    df = load()

    print("="*74 + "\nF) LINE-SHOPPING ALLA CHIUSURA: prob=fair sharp (Pinnacle close),\n"
          "   scommetti a Maximum_closing dove la quota best batte la fair sharp.\n" + "="*74)
    for thr in [0.0, 0.02, 0.04, 0.06]:
        show(df, f"LS close all e{thr}", markets=["H","D","A","O25","U25"],
             bet_book="Maximum_closing", prob="fair_pin", edge_min=thr, min_odds=1.2, max_odds=15)
    print("\n-- solo 1X2 --")
    for thr in [0.0, 0.03]:
        show(df, f"LS close 1x2 e{thr}", markets=["H","D","A"],
             bet_book="Maximum_closing", prob="fair_pin", edge_min=thr, min_odds=1.2, max_odds=15)

    print("\n" + "="*74 + "\nG) FAVORITE-LONGSHOT: scommetti favoriti (quote basse) col modello\n" + "="*74)
    for mo in [1.0, 1.3]:
        for Mo in [1.7, 2.0, 2.5]:
            show(df, f"fav H/A {mo}-{Mo}", markets=["H","A"], bet_book="Maximum",
                 prob="cal", edge_min=0.0, min_odds=mo, max_odds=Mo)

    print("\n" + "="*74 + "\nH) MODELLO vs quote CHIUSURA (Maximum_closing), per mercato\n" + "="*74)
    for mk in [["H"],["D"],["A"],["O25"],["U25"]]:
        show(df, f"model vs close {mk[0]}", markets=mk, bet_book="Maximum_closing",
             prob="cal", edge_min=0.03, min_odds=1.3, max_odds=10)
