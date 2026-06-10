"""
Dump predizioni con modello DC alimentato a xG.
Stima le forze su 'gol efficaci' = xg_w*xG + (1-xg_w)*gol_reali (dove xG esiste),
gol reali altrove. Outcome di settlement = SEMPRE gol reali.
Confrontabile 1:1 con dump.py (goals-only).
"""
import sys, os, math
from collections import defaultdict
import numpy as np, pandas as pd
from sklearn.isotonic import IsotonicRegression
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dc_model import fit_dc, predict_markets
from devig import devig_shin
from dataload import get_league_data

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
MK1 = {"H": "Home", "D": "Draw", "A": "Away"}
MK5 = {"O25": "Over 2.5", "U25": "Under 2.5"}
BET_BOOKS = ["Maximum", "Average", "Bet365", "Pinnacle_closing", "Maximum_closing"]
HALF_LIFE, REFIT_DAYS, MAX_HIST_DAYS, MIN_HISTORY, RHO = 200.0, 7, 1100, 150, -0.13
CALIB_MIN, CALIB_REFIT = 350, 120
XG_W = 0.6   # peso xG nella miscela gol-efficaci


def _out(sel, gh, ga):
    return {"H": gh > ga, "D": gh == ga, "A": gh < ga,
            "O25": gh + ga >= 3, "U25": gh + ga <= 2}[sel] and 1 or 0


def _devig(row, book, labels):
    cols = [f"{book}__{l}" for l in labels.values()]
    vals = [row.get(c) for c in cols]
    try:
        vals = [float(v) for v in vals]
    except (TypeError, ValueError):
        return None
    if any((v is None) or math.isnan(v) or v <= 1.0 for v in vals):
        return None
    return dict(zip(labels.keys(), devig_shin(vals)))


def dump_league_xg(league_id: int) -> pd.DataFrame:
    m, odds = get_league_data(league_id)
    xgp = os.path.join(CACHE, f"xg_{league_id}.pkl")
    if not os.path.exists(xgp):
        return pd.DataFrame()
    xg = pd.read_pickle(xgp)
    m = m.merge(xg, on="fixture_id", how="left").sort_values("fixture_date").reset_index(drop=True)
    # gol efficaci per il FIT (blend dove xG presente)
    has = m["xg_home"].notna() & m["xg_away"].notna()
    m["g_home_eff"] = np.where(has, XG_W * m["xg_home"].fillna(0) + (1 - XG_W) * m["goals_home"], m["goals_home"])
    m["g_away_eff"] = np.where(has, XG_W * m["xg_away"].fillna(0) + (1 - XG_W) * m["goals_away"], m["goals_away"])
    # m_fit: copia con goals = efficaci (fit_dc legge goals_home/away)
    m_fit = m.copy()
    m_fit["goals_home"] = m["g_home_eff"]
    m_fit["goals_away"] = m["g_away_eff"]

    o1 = odds.get("1"); o5 = odds.get("5")
    o1 = o1.set_index("fixture_id") if (o1 is not None and not o1.empty) else pd.DataFrame()
    o5 = o5.set_index("fixture_id") if (o5 is not None and not o5.empty) else pd.DataFrame()

    calib_buf = defaultdict(lambda: ([], [])); calibrators = {}; since = 0
    model = None; model_date = None; rows = []
    # inizia quando c'e' storico xG: prima data con xG + un po' di warmup
    xg_dates = m.loc[has, "fixture_date"]
    start_date = (xg_dates.min() + pd.Timedelta(days=120)) if len(xg_dates) else m["fixture_date"].iloc[0] + pd.Timedelta(days=400)

    for i in range(len(m)):
        r = m.iloc[i]; ko = r["fixture_date"]
        if ko < start_date:
            continue
        past_all = m_fit[m_fit["fixture_date"] < ko]
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
                    try: iso.fit(rw, ou); calibrators[mk] = iso
                    except Exception: pass
            since = 0
        r1 = o1.loc[fid].to_dict() if (not o1.empty and fid in o1.index) else {}
        r5 = o5.loc[fid].to_dict() if (not o5.empty and fid in o5.index) else {}
        fp1 = _devig(r1, "Pinnacle_closing", MK1) if r1 else None
        fa1 = _devig(r1, "Average", MK1) if r1 else None
        fp5 = _devig(r5, "Pinnacle_closing", MK5) if r5 else None
        fa5 = _devig(r5, "Average", MK5) if r5 else None
        for sel in ["H", "D", "A", "O25", "U25"]:
            raw = pred.get(sel)
            if raw is None: continue
            cal = raw
            if sel in calibrators:
                cal = float(min(max(calibrators[sel].predict([raw])[0], 1e-4), 0.9999))
            is1 = sel in MK1; lab = MK1[sel] if is1 else MK5[sel]; src = r1 if is1 else r5
            rec = {"league": league_id, "date": ko, "fixture_id": fid, "market": sel,
                   "raw": raw, "cal": cal, "y": _out(sel, gh, ga)}
            for bk in BET_BOOKS:
                v = src.get(f"{bk}__{lab}")
                try:
                    v = float(v); v = np.nan if (math.isnan(v) or v <= 1.0) else v
                except (TypeError, ValueError): v = np.nan
                rec[f"odd_{bk}"] = v
            fp = fp1 if is1 else fp5; fa = fa1 if is1 else fa5
            rec["fair_pin"] = fp.get(sel) if fp else np.nan
            rec["fair_avg"] = fa.get(sel) if fa else np.nan
            rows.append(rec)
        for sel in ["H", "D", "A", "O25", "U25"]:
            raw = pred.get(sel)
            if raw is not None:
                rw, ou = calib_buf[sel]; rw.append(raw); ou.append(_out(sel, gh, ga))
        since += 1
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import glob
    leagues = sorted(int(os.path.basename(f).split("_")[1].split(".")[0])
                     for f in glob.glob(os.path.join(CACHE, "matches_*.pkl")))
    alld = []
    for lid in leagues:
        df = dump_league_xg(lid)
        if not df.empty:
            df.to_pickle(os.path.join(CACHE, f"predxg_{lid}.pkl")); alld.append(df)
        print(f"lega {lid}: {len(df)} righe (xG model)", flush=True)
    if alld:
        full = pd.concat(alld, ignore_index=True)
        full.to_pickle(os.path.join(CACHE, "predxg_ALL.pkl"))
        print(f"TOTALE: {len(full)} -> predxg_ALL.pkl")
    print("DONE")
