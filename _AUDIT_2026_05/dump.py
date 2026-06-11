"""
Genera la tabella di predizioni RICCA (una riga per fixture x mercato), point-in-time:
 - prob grezza e calibrata (walk-forward isotonic)
 - esito reale
 - quote da piu' book (Maximum, Average, Bet365, Pinnacle_closing, Maximum_closing)
 - fair prob da Pinnacle_closing (CLV) e Average (consenso apertura)
Salva un parquet per lega. Le strategie di betting diventano semplici filtri pandas.
"""
from __future__ import annotations
import math
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dc_model import fit_dc, predict_markets
from devig import devig_shin
from dataload import get_league_data

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

MK1 = {"H": "Home", "D": "Draw", "A": "Away"}
MK5 = {"O25": "Over 2.5", "U25": "Under 2.5"}
BET_BOOKS = ["Maximum", "Average", "Bet365", "Pinnacle_closing", "Maximum_closing", "Bet365_closing"]

HALF_LIFE = 180.0
REFIT_DAYS = 7
MAX_HIST_DAYS = 1000
MIN_HISTORY = 150
WARMUP_SEASONS = 1
RHO = -0.13
CALIB_MIN = 400
CALIB_REFIT = 150


def _out(sel, gh, ga):
    if sel == "H": return int(gh > ga)
    if sel == "D": return int(gh == ga)
    if sel == "A": return int(gh < ga)
    if sel == "O25": return int(gh + ga >= 3)
    if sel == "U25": return int(gh + ga <= 2)
    raise ValueError(sel)


def _devig(row, book, labels):
    cols = [f"{book}__{l}" for l in labels.values()]
    vals = [row.get(c) for c in cols]
    try:
        vals = [float(v) for v in vals]
    except (TypeError, ValueError):
        return None
    if any((v is None) or math.isnan(v) or v <= 1.0 for v in vals):
        return None
    p = devig_shin(vals)
    return dict(zip(labels.keys(), p))


def dump_league(league_id: int) -> pd.DataFrame:
    m, odds = get_league_data(league_id)
    o1 = odds.get("1"); o5 = odds.get("5")
    o1 = o1.set_index("fixture_id") if (o1 is not None and not o1.empty) else pd.DataFrame()
    o5 = o5.set_index("fixture_id") if (o5 is not None and not o5.empty) else pd.DataFrame()
    m = m.sort_values("fixture_date").reset_index(drop=True)

    calib_buf = defaultdict(lambda: ([], []))
    calibrators = {}
    since = 0
    model = None; model_date = None
    rows = []
    start_date = m["fixture_date"].iloc[0] + pd.Timedelta(days=365 * WARMUP_SEASONS)

    for _, r in m.iterrows():
        ko = r["fixture_date"]
        if ko < start_date:
            continue
        past_all = m[m["fixture_date"] < ko]
        if len(past_all) < MIN_HISTORY:
            continue
        past = past_all[past_all["fixture_date"] >= ko - pd.Timedelta(days=MAX_HIST_DAYS)]
        if model is None or (ko - model_date).days >= REFIT_DAYS:
            model = fit_dc(past if len(past) >= MIN_HISTORY else past_all, ko, HALF_LIFE, 1e-4, RHO)
            model_date = ko
        if model is None:
            continue
        pred = predict_markets(model, r["home_team_id"], r["away_team_id"])
        if pred is None:
            continue
        gh, ga = int(r["goals_home"]), int(r["goals_away"])
        fid = r["fixture_id"]

        if since >= CALIB_REFIT:
            for mk, (rw, ou) in calib_buf.items():
                if len(rw) >= CALIB_MIN:
                    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
                    try:
                        iso.fit(rw, ou); calibrators[mk] = iso
                    except Exception:
                        pass
            since = 0

        r1 = o1.loc[fid].to_dict() if (not o1.empty and fid in o1.index) else {}
        r5 = o5.loc[fid].to_dict() if (not o5.empty and fid in o5.index) else {}
        fair_pin1 = _devig(r1, "Pinnacle_closing", MK1) if r1 else None
        fair_avg1 = _devig(r1, "Average", MK1) if r1 else None
        fair_pin5 = _devig(r5, "Pinnacle_closing", MK5) if r5 else None
        fair_avg5 = _devig(r5, "Average", MK5) if r5 else None

        for sel in ["H", "D", "A", "O25", "U25"]:
            raw = pred.get(sel)
            if raw is None:
                continue
            cal = raw
            if sel in calibrators:
                cal = float(calibrators[sel].predict([raw])[0])
                cal = min(max(cal, 1e-4), 0.9999)
            is1 = sel in MK1
            lab = MK1[sel] if is1 else MK5[sel]
            src = r1 if is1 else r5
            rec = {"league": league_id, "date": ko, "fixture_id": fid, "market": sel,
                   "raw": raw, "cal": cal, "y": _out(sel, gh, ga)}
            for bk in BET_BOOKS:
                v = src.get(f"{bk}__{lab}")
                try:
                    v = float(v)
                    if math.isnan(v) or v <= 1.0:
                        v = np.nan
                except (TypeError, ValueError):
                    v = np.nan
                rec[f"odd_{bk}"] = v
            fp = (fair_pin1 if is1 else fair_pin5)
            fa = (fair_avg1 if is1 else fair_avg5)
            rec["fair_pin"] = fp.get(sel) if fp else np.nan
            rec["fair_avg"] = fa.get(sel) if fa else np.nan
            rows.append(rec)

        for sel in ["H", "D", "A", "O25", "U25"]:
            raw = pred.get(sel)
            if raw is not None:
                rw, ou = calib_buf[sel]
                rw.append(raw); ou.append(_out(sel, gh, ga))
        since += 1

    return pd.DataFrame(rows)


if __name__ == "__main__":
    import glob
    leagues = sorted(int(os.path.basename(f).split("_")[1].split(".")[0])
                     for f in glob.glob(os.path.join(CACHE, "matches_*.pkl")))
    if len(sys.argv) > 1:
        leagues = [int(x) for x in sys.argv[1:]]
    all_df = []
    for lid in leagues:
        df = dump_league(lid)
        if not df.empty:
            df.to_pickle(os.path.join(CACHE, f"pred_{lid}.pkl"))
            all_df.append(df)
        print(f"lega {lid}: {len(df)} righe predizione", flush=True)
    if all_df:
        full = pd.concat(all_df, ignore_index=True)
        full.to_pickle(os.path.join(CACHE, "pred_ALL.pkl"))
        print(f"TOTALE: {len(full)} righe -> pred_ALL.pkl")
    print("DONE")
