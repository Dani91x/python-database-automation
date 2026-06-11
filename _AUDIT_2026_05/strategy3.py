"""Avenue I/J/K: line-shopping raffinato, doppio filtro, eterogeneita' per-lega."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy import load, eval_strategy, HOLDOUT

LN = {39:"Premier",40:"Champ",61:"Ligue1",71:"Brasil",78:"Bundes",88:"Erediv",
      94:"Primeira",135:"SerieA",140:"LaLiga",144:"Jupiler",197:"GreeceSL",203:"SuperLig"}


def m(d):
    if len(d)==0: return (0,0,0,float('nan'))
    clv=d["clv"].dropna()
    return (len(d), 100*d["pnl"].sum()/d["stake"].sum(), 100*d["y"].mean(),
            100*clv.mean() if len(clv) else float('nan'))


def show(df, label, **kw):
    d = eval_strategy(df, **kw)
    dev=d[d["date"]<HOLDOUT]; hold=d[d["date"]>=HOLDOUT]
    nd,rd,hd,cd = m(dev); nh,rh,hh,ch = m(hold)
    print(f"  {label:30s} DEV[n={nd:5d} ROI={rd:+6.2f}% CLV={cd:+5.2f}]  HOLD[n={nh:5d} ROI={rh:+6.2f}% CLV={ch:+5.2f}]")
    return d


if __name__ == "__main__":
    df = load()

    print("="*100 + "\nI) LINE-SHOPPING raffinato (prob=fair_pin, bet=Maximum_closing): soglia + cap quote\n"+"="*100)
    for thr in [0.04, 0.08, 0.12]:
        for mo,Mo in [(1.2,15),(1.5,6),(1.5,4)]:
            show(df, f"LS thr{thr} odds{mo}-{Mo}", markets=["H","D","A","O25","U25"],
                 bet_book="Maximum_closing", prob="fair_pin", edge_min=thr, min_odds=mo, max_odds=Mo)

    print("\n"+"="*100 + "\nJ) DOPPIO FILTRO: modello d'accordo col valore (cal>fair) + line-shopping closing\n"+"="*100)
    # implementiamo il doppio filtro manualmente: edge modello vs Max_closing >0 E quota>fair_pin
    for thr in [0.03, 0.06]:
        d = df.copy()
        d = d[d["odd_Maximum_closing"].notna() & (d["odd_Maximum_closing"]>=1.3) & (d["odd_Maximum_closing"]<=10)]
        d = d[d["fair_pin"].notna()]
        edge_model = d["cal"]*d["odd_Maximum_closing"]-1.0
        edge_value = d["odd_Maximum_closing"]*d["fair_pin"]-1.0   # CLV ex-ante
        sel = d[(edge_model>=thr) & (edge_value>=thr)]
        pnl = np.where(sel["y"]==1, sel["odd_Maximum_closing"]-1.0, -1.0)
        sel = sel.assign(pnl=pnl, stake=1.0, clv=edge_value.loc[sel.index])
        dev=sel[sel["date"]<HOLDOUT]; hold=sel[sel["date"]>=HOLDOUT]
        nd,rd,hd,cd=m(dev); nh,rh,hh,ch=m(hold)
        print(f"  doppio-filtro thr{thr:<4}           DEV[n={nd:5d} ROI={rd:+6.2f}% CLV={cd:+5.2f}]  HOLD[n={nh:5d} ROI={rh:+6.2f}% CLV={ch:+5.2f}]")

    print("\n"+"="*100 + "\nK) PER-LEGA: modello vs Max (apertura), D edge3 — dove il modello ha edge reale?\n"+"="*100)
    for lid,name in LN.items():
        dl = df[df["league"]==lid]
        show(dl, f"{name} D", markets=["D"], bet_book="Maximum", prob="cal", edge_min=0.03)

    print("\n"+"="*100 + "\nK2) PER-LEGA: line-shopping closing 1x2 (la via +CLV)\n"+"="*100)
    for lid,name in LN.items():
        dl = df[df["league"]==lid]
        show(dl, f"{name} LS", markets=["H","D","A"], bet_book="Maximum_closing", prob="fair_pin", edge_min=0.04, min_odds=1.2, max_odds=15)
