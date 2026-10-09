"""Sonda A4: RPS 1X2 del motore tattico DC-MLE (tactical_engine_json) vs Poisson (grezzo/calibrato) vs quote, stessa partita. SOLO SELECT, 1200 righe."""
import sys, math
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
import numpy as np
from db_client import get_supabase_client
from generate_dynamic_cal import _extract_implied_1x2
sb = get_supabase_client()
rows = (sb.table("fixture_predictions")
        .select("fixture_id,result_home_goals,result_away_goals,raw_json_odds,t:tactical_engine_json->markets,tl:tactical_engine_json->lambda_home,mc:db_json_analisi->markets_calibrated,m:db_json_analisi->markets")
        .eq("result_status_short", "FT").gte("fixture_date", "2026-09-21").lt("fixture_date", "2026-10-08")
        .not_.is_("db_json_analisi", "null").not_.is_("tactical_engine_json", "null").limit(1200).execute().data or [])
print("righe lette:", len(rows))
def rps(p, o):
    c = np.cumsum(p) - np.cumsum(o); return float(np.sum(c[:-1] ** 2) / 2)
acc = {"tattico DC-MLE": [], "poisson calibrato": [], "poisson grezzo": [], "quote": [], "media(tattico,poisson cal)": []}
for r in rows:
    h, a = r["result_home_goals"], r["result_away_goals"]
    t = r.get("t"); mc = (r.get("mc") or {}).get("1x2"); m = (r.get("m") or {}).get("1x2")
    q = _extract_implied_1x2(r["raw_json_odds"]) if r.get("raw_json_odds") else None
    if h is None or not (t and mc and m and q and "home" in t): continue
    o = np.array([h > a, h == a, h < a], float)
    pt = np.array([t["home"], t["draw"], t["away"]]); pc = np.array([mc["H"], mc["D"], mc["A"]]); pg = np.array([m["H"], m["D"], m["A"]])
    q = np.array(q); q = q / q.sum()
    for k, p in (("tattico DC-MLE", pt), ("poisson calibrato", pc), ("poisson grezzo", pg), ("quote", q), ("media(tattico,poisson cal)", (pt + pc) / 2)):
        acc[k].append((rps(p, o), -math.log(max(p[o.argmax()], 1e-12))))
for k, v in acc.items():
    v = np.array(v); print(f"{k:28s} n={len(v)} RPS={v[:,0].mean():.4f} logloss={v[:,1].mean():.4f}")
