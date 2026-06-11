"""
Simulatore strategia TRADER: BACK Under 2.5 + green-up time-decay (regola utente).
Regola: entro back Under 2.5 pre-match su partite segnalate 'chiuse' dal modello.
 - se al minuto T (mezz'ora) NON sono arrivati gol -> green up (profitto bloccato)
 - se arriva un gol prima di T -> NON esco, tengo fino al 90' (vinco se finale<=2, perdo se >=3)
Usa i TEMPI GOL REALI (match_events). Prezzo di uscita = fair di mercato decaduto (Poisson).
"""
import os, sys, glob
import numpy as np, pandas as pd
from scipy.stats import poisson
from scipy.optimize import brentq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
HOLD = pd.Timestamp("2020-07-01", tz="UTC")
COMM = 0.02   # commissione exchange sul profitto netto


def lambda_from_under(p_under):
    """Inverti P(Pois(lambda)<=2) = p_under -> lambda totale atteso."""
    p_under = min(max(p_under, 0.02), 0.98)
    try:
        return brentq(lambda lam: poisson.cdf(2, lam) - p_under, 0.05, 8.0)
    except Exception:
        return np.nan


def under_price_at(lam_total, minute, goals_so_far):
    """Quota equa Under 2.5 al 'minute' con 'goals_so_far' gia' segnati."""
    need = 2 - goals_so_far
    if need < 0:
        return np.inf   # under gia' perso
    lam_rem = lam_total * (90 - minute) / 90.0
    p = poisson.cdf(need, lam_rem)
    return 1.0 / max(p, 1e-6)


def load_all():
    pred = pd.read_pickle(os.path.join(CACHE, "pred_ALL.pkl"))
    u = pred[pred["market"] == "U25"].copy()
    # final goals + goal times
    gframes, mframes = [], []
    for f in glob.glob(os.path.join(CACHE, "goals_*.pkl")):
        gframes.append(pd.read_pickle(f))
    goals = pd.concat(gframes, ignore_index=True) if gframes else pd.DataFrame(columns=["fixture_id","minute"])
    # tempo primo/i gol per fixture: lista minuti
    gmin = goals.groupby("fixture_id")["minute"].apply(list).to_dict()
    return u, gmin


def goals_by(minutes, T):
    return sum(1 for mn in minutes if mn <= T)


def simulate(u, gmin, entry_col, T, sel_mask=None, comm=COMM):
    d = u.copy()
    if sel_mask is not None:
        d = d[sel_mask]
    d = d[d[entry_col].notna() & d["fair_pin"].notna()]
    pnls, scoreless, held, held_win = [], 0, 0, 0
    for _, r in d.iterrows():
        fid = r["fixture_id"]
        if fid not in gmin:
            continue
        O_entry = float(r[entry_col])
        lam_mkt = lambda_from_under(float(r["fair_pin"]))
        if np.isnan(lam_mkt):
            continue
        mins = gmin[fid]
        gT = goals_by(mins, T)
        if gT == 0:
            O_exit = under_price_at(lam_mkt, T, 0)
            locked = O_entry / O_exit - 1.0
            pnl = locked * (1 - comm) if locked > 0 else locked
            scoreless += 1
        else:
            # hold to settlement: y=1 se finale<=2 (under vince)
            held += 1
            if int(r["y"]) == 1:
                pnl = (O_entry - 1.0) * (1 - comm); held_win += 1
            else:
                pnl = -1.0
        pnls.append((pnl, gT == 0))
    if not pnls:
        return None
    arr = np.array([p for p, _ in pnls])
    scl = np.array([s for _, s in pnls])
    n = len(arr)
    gu = arr[scl]      # green-up (scoreless)
    hl = arr[~scl]     # held (gol presto)
    return dict(n=n, roi=100*arr.sum()/n, scoreless_pct=100*scoreless/n,
                held_pct=100*held/n, held_winrate=100*held_win/held if held else float("nan"),
                avg_greenup=100*gu.mean() if len(gu) else float("nan"),
                avg_held=100*hl.mean() if len(hl) else float("nan"),
                pnl=arr.sum())


if __name__ == "__main__":
    u, gmin = load_all()
    print(f"U25 rows con dati: {len(u)}, fixture con tempi-gol: {len(gmin)}")
    u = u[u["fixture_id"].isin(gmin.keys())].copy()
    print(f"U25 con tempi-gol: {len(u)}  periodo {u['date'].min().date()}..{u['date'].max().date()}\n")

    model_value = u["cal"] - u["fair_pin"]
    masks = {
        "TUTTE": None,
        "modello under value>=+4%": (model_value >= 0.04),
        "modello dice basso cal>=0.60": (u["cal"] >= 0.60),
    }

    print("### SWEEP MINUTO DI USCITA (green-up se scoreless, altrimenti hold al 90') ###")
    print("### Ingresso @ Pinnacle (sharp) = test puro, niente bonus line-shopping ###\n")
    for sel_name, mask in masks.items():
        print(f"-- selezione: {sel_name} --")
        print(f"   {'uscita':>7}{'n':>7}{'ROI':>9}{'scoreless%':>11}{'avg green-up':>14}{'avg held(tail)':>15}")
        for T in [1, 5, 10, 15, 25, 35]:
            r = simulate(u, gmin, "odd_Pinnacle_closing", T, mask)
            if r:
                print(f"   {T:>5}'{r['n']:>7}{r['roi']:>+8.2f}%{r['scoreless_pct']:>10.1f}%"
                      f"{r['avg_greenup']:>+13.2f}%{r['avg_held']:>+14.2f}%")
        print()

    print("### Confronto: ingresso @ Maximum (best price, con line-shopping) — uscita 15' ###")
    for sel_name, mask in masks.items():
        r = simulate(u, gmin, "odd_Maximum", 15, mask)
        if r:
            print(f"   {sel_name:32s} n={r['n']:5d} ROI={r['roi']:+6.2f}%  green-up_avg={r['avg_greenup']:+.2f}%  held_avg={r['avg_held']:+.2f}%")
