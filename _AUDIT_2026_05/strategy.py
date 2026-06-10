"""
Valutazione strategie sul dump di predizioni (pred_ALL.parquet).
Strategie = filtri pandas. Split DEV/HOLDOUT. Metrica chiave: ROI + CLV.

Criterio di robustezza (anti-overfit): una strategia e' accettata solo se ha
ROI>0 E CLV>0 sul DEV, e si VALIDA riportando l'HOLDOUT (mai usato per scegliere).
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
HOLDOUT = pd.Timestamp("2020-07-01", tz="UTC")


def load():
    return pd.read_pickle(os.path.join(CACHE, "pred_ALL.pkl"))


def eval_strategy(df, markets, bet_book="Maximum", prob="cal", blend_w=0.0,
                  edge_min=0.0, min_odds=1.4, max_odds=8.0, commission=0.0,
                  clv_min=None):
    """Ritorna df dei bet con pnl e clv."""
    d = df[df["market"].isin(markets)].copy()
    oc = f"odd_{bet_book}"
    d = d[d[oc].notna() & (d[oc] >= min_odds) & (d[oc] <= max_odds)]
    # probabilita' usata
    p = d[prob].astype(float)
    if blend_w > 0:
        p = (1 - blend_w) * p + blend_w * d["fair_avg"].astype(float)
        p = p.where(d["fair_avg"].notna(), d[prob].astype(float))
    d = d.assign(p=p)
    odd_net = (d[oc] - 1.0) * (1.0 - commission) + 1.0
    d = d.assign(odd_net=odd_net, edge=d["p"] * odd_net - 1.0)
    d = d[d["edge"] >= edge_min]
    # CLV vs Pinnacle closing
    clv = d[oc] * d["fair_pin"] - 1.0   # odd presa * fair_prob_sharp - 1
    d = d.assign(clv=clv)
    if clv_min is not None:
        d = d[d["clv"].notna() & (d["clv"] >= clv_min)]
    pnl = np.where(d["y"] == 1, d["odd_net"] - 1.0, -1.0)
    d = d.assign(pnl=pnl, stake=1.0)
    return d


def metrics(d):
    if len(d) == 0:
        return dict(n=0, roi=0, hit=0, clv=float("nan"), clvpos=float("nan"), avgodd=0)
    clv = d["clv"].dropna()
    return dict(
        n=len(d), roi=100 * d["pnl"].sum() / d["stake"].sum(),
        hit=100 * d["y"].mean(), avgodd=d["odd_" ].iloc[0] if False else d.filter(like="odd_").iloc[:, 0].mean(),
        clv=100 * clv.mean() if len(clv) else float("nan"),
        clvpos=100 * (clv > 0).mean() if len(clv) else float("nan"),
    )


def show(df, label, markets, **kw):
    d = eval_strategy(df, markets, **kw)
    dev = d[d["date"] < HOLDOUT]; hold = d[d["date"] >= HOLDOUT]
    def line(tag, x):
        if len(x) == 0:
            return f"   {tag:20s} n=0"
        clv = x["clv"].dropna()
        return (f"   {tag:20s} n={len(x):5d}  ROI={100*x['pnl'].sum()/x['stake'].sum():+6.2f}%  "
                f"hit={100*x['y'].mean():4.1f}%  CLV={100*clv.mean() if len(clv) else float('nan'):+5.2f}%  "
                f"CLV+={100*(clv>0).mean() if len(clv) else float('nan'):4.1f}%")
    print(f"\n[{label}] markets={markets} {kw}")
    print(line("DEV", dev)); print(line("HOLDOUT", hold)); print(line("TOT", d))
    return d


def calibration_diag(df):
    print("\n=== DIAGNOSTICA CALIBRAZIONE (cal vs esito) per mercato ===")
    for mk, g in df.groupby("market"):
        print(f"  {mk:5s} n={len(g):6d}  cal_mean={g['cal'].mean():.3f}  y_mean={g['y'].mean():.3f}  "
              f"raw_mean={g['raw'].mean():.3f}")


if __name__ == "__main__":
    df = load()
    print(f"pred_ALL: {len(df)} righe, leghe={sorted(df['league'].unique())}, "
          f"date {df['date'].min().date()}..{df['date'].max().date()}")
    calibration_diag(df)

    print("\n" + "="*74 + "\nA) Per-mercato, Max odds (apertura), edge>=3% — quote=best price\n" + "="*74)
    for mk in [["H"], ["D"], ["A"], ["O25"], ["U25"]]:
        show(df, f"Max e3 {mk[0]}", mk, bet_book="Maximum", edge_min=0.03)

    print("\n" + "="*74 + "\nB) Effetto del book su cui si scommette (mercato D)\n" + "="*74)
    for bk in ["Maximum", "Average", "Bet365"]:
        show(df, f"{bk} D e3", ["D"], bet_book=bk, edge_min=0.03)

    print("\n" + "="*74 + "\nC) Blend modello+consenso (anti-overconfidence), Max odds\n" + "="*74)
    for w in [0.0, 0.3, 0.5]:
        show(df, f"D blend{w}", ["D"], bet_book="Maximum", blend_w=w, edge_min=0.03)

    print("\n" + "="*74 + "\nD) Soglia edge (mercato D, Max)\n" + "="*74)
    for e in [0.02, 0.05, 0.08, 0.12]:
        show(df, f"D e{e}", ["D"], bet_book="Maximum", edge_min=e)

    print("\n" + "="*74 + "\nE) Multi-mercato candidati (Max, edge>=5%)\n" + "="*74)
    show(df, "D+U25", ["D", "U25"], bet_book="Maximum", edge_min=0.05)
    show(df, "tutti", ["H","D","A","O25","U25"], bet_book="Maximum", edge_min=0.05)
