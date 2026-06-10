"""
Runner multi-lega con split temporale DEV/HOLDOUT.
Esegue il backtest point-in-time su tutte le leghe in cache, unisce i bet,
e riporta ROI/CLV per mercato separando DEV (sviluppo) e HOLDOUT (validazione finale).
"""
from __future__ import annotations
import glob
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataload import get_league_data
from backtest import Config, run_backtest

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
HOLDOUT_START = pd.Timestamp("2020-07-01", tz="UTC")


def cached_leagues():
    out = []
    for f in glob.glob(os.path.join(CACHE, "matches_*.pkl")):
        lid = int(os.path.basename(f).split("_")[1].split(".")[0])
        out.append(lid)
    return sorted(out)


def run_all(cfg: Config, leagues=None, tag="run") -> pd.DataFrame:
    leagues = leagues or cached_leagues()
    all_bets = []
    for lid in leagues:
        m, odds = get_league_data(lid)
        res = run_backtest(m, odds.get("1"), odds.get("5"), cfg, lid)
        if not res.bets.empty:
            all_bets.append(res.bets)
        s = res.summary()
        print(f"  lega {lid}: n={s.get('n',0)} roi={s.get('roi_pct',0):.2f}% clv={s.get('clv_pct',float('nan')):.2f}%", flush=True)
    bets = pd.concat(all_bets, ignore_index=True) if all_bets else pd.DataFrame()
    if not bets.empty:
        bets.to_parquet(os.path.join(CACHE, f"bets_{tag}.parquet"))
    return bets


def report(bets: pd.DataFrame, title: str):
    print("\n" + "#" * 74 + f"\n# {title}\n" + "#" * 74)
    if bets.empty:
        print("  nessun bet"); return
    dev = bets[bets["date"] < HOLDOUT_START]
    hold = bets[bets["date"] >= HOLDOUT_START]
    for name, b in [("DEV (<2020-07)", dev), ("HOLDOUT (>=2020-07)", hold), ("TOTALE", bets)]:
        if b.empty:
            print(f"\n== {name}: nessun bet"); continue
        st = b["stake"].sum(); pnl = b["pnl"].sum()
        clv = b["clv"].dropna()
        print(f"\n== {name}: n={len(b)} ROI={100*pnl/st:+.2f}% PnL={pnl:+.1f} "
              f"hit={100*b['win'].mean():.1f}% CLV={100*clv.mean() if len(clv) else float('nan'):+.2f}% "
              f"CLV+={100*(clv>0).mean() if len(clv) else float('nan'):.1f}%")
        print(f"   {'mkt':6s}{'n':>6}{'ROI%':>9}{'hit%':>7}{'avgodd':>8}{'CLV%':>8}{'CLV+%':>7}")
        for mk, g in b.groupby("market"):
            gst = g["stake"].sum(); gpnl = g["pnl"].sum()
            gclv = g["clv"].dropna()
            print(f"   {mk:6s}{len(g):>6}{100*gpnl/gst:>9.2f}{100*g['win'].mean():>7.1f}"
                  f"{g['odds'].mean():>8.2f}{100*gclv.mean() if len(gclv) else float('nan'):>8.2f}"
                  f"{100*(gclv>0).mean() if len(gclv) else float('nan'):>7.1f}")


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    cfg = Config()
    print(f"Leghe in cache: {cached_leagues()}")
    bets = run_all(cfg, tag=tag)
    report(bets, f"BASELINE point-in-time | bet_book={cfg.bet_book} edge>={cfg.edge_threshold} calib={cfg.calibrate}")
