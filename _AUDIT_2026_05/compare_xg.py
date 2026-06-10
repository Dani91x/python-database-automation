"""Confronto modello xG vs goals: Brier (sharpness) + ROI/CLV per mercato, stesse partite."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
HOLD = pd.Timestamp("2022-07-01", tz="UTC")  # split piu' tardi: l'era xG e' recente


def brier_by_market(df, name):
    print(f"\n--- Brier (calibrato) {name} ---  (piu' basso = meglio)")
    for mk, g in df.groupby("market"):
        b = ((g["cal"] - g["y"]) ** 2).mean()
        braw = ((g["raw"] - g["y"]) ** 2).mean()
        print(f"   {mk:5s} n={len(g):6d}  Brier_cal={b:.4f}  Brier_raw={braw:.4f}  y_mean={g['y'].mean():.3f} cal_mean={g['cal'].mean():.3f}")


def strat(df, sel, book, prob, thr, mo=1.3, Mo=8.0):
    d = df[df["market"] == sel].copy()
    oc = f"odd_{book}"
    d = d[d[oc].notna() & (d[oc] >= mo) & (d[oc] <= Mo)]
    p = d[prob].astype(float)
    edge = p * d[oc] - 1.0
    d = d[edge >= thr]
    if len(d) == 0: return None
    pnl = np.where(d["y"] == 1, d[oc] - 1.0, -1.0)
    clv = (d[oc] * d["fair_pin"] - 1.0)
    return dict(n=len(d), roi=100*pnl.sum()/len(d), hit=100*d["y"].mean(),
                clv=100*clv.dropna().mean() if clv.notna().any() else float("nan"))


if __name__ == "__main__":
    xg = pd.read_pickle(os.path.join(CACHE, "predxg_ALL.pkl"))
    go = pd.read_pickle(os.path.join(CACHE, "pred_ALL.pkl"))
    print(f"xG model: {len(xg)} righe, {xg['date'].min().date()}..{xg['date'].max().date()}")
    print(f"goals model: {len(go)} righe")

    # comune: stessi (fixture, market) presenti in entrambi
    key = ["fixture_id", "market"]
    common = set(map(tuple, xg[key].values)) & set(map(tuple, go[key].values))
    print(f"fixture×market comuni: {len(common)}")
    xgc = xg[xg.set_index(key).index.isin(common)].copy()
    goc = go[go.set_index(key).index.isin(common)].copy()

    print("\n==================== SHARPNESS / CALIBRAZIONE ====================")
    brier_by_market(goc, "GOALS model")
    brier_by_market(xgc, "xG model")

    print("\n==================== ROI/CLV per mercato (Maximum=apertura, edge>=3%) ====================")
    for book in ["Maximum", "Maximum_closing"]:
        print(f"\n### Book = {book}")
        for sel in ["H", "D", "A", "O25", "U25"]:
            rg = strat(goc, sel, book, "cal", 0.03)
            rx = strat(xgc, sel, book, "cal", 0.03)
            def f(r): return f"n={r['n']:4d} ROI={r['roi']:+6.2f}% CLV={r['clv']:+5.2f}%" if r else "n=0"
            print(f"   {sel:4s} | GOALS {f(rg):38s} | xG {f(rx)}")

    print("\n==================== xG model: edge soglia alta su OU (apertura) ====================")
    for sel in ["O25", "U25"]:
        for thr in [0.05, 0.08, 0.12]:
            r = strat(xgc, sel, "Maximum", "cal", thr)
            print(f"   {sel} thr{thr}: " + (f"n={r['n']:4d} ROI={r['roi']:+6.2f}% CLV={r['clv']:+5.2f}% hit={r['hit']:.1f}%" if r else "n=0"))
