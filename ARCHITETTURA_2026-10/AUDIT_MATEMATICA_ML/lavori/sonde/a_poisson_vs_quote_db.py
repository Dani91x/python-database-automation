"""Sonda A3: RPS/Brier/logloss 1X2 delle quote (de-vig proporzionale, bookmaker Betfair o primo) vs Poisson grezzo/calibrato, stesso campione. SOLO SELECT, 800 righe."""
import sys, math
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
import numpy as np
from db_client import get_supabase_client
from generate_dynamic_cal import _extract_implied_1x2
import generate_dynamic_cal as g
sb = get_supabase_client()
rows = (sb.table("fixture_predictions")
        .select("fixture_id,result_home_goals,result_away_goals,raw_json_odds,m:db_json_analisi->markets,mc:db_json_analisi->markets_calibrated")
        .eq("result_status_short", "FT").gte("fixture_date", "2026-09-21").lt("fixture_date", "2026-10-08")
        .not_.is_("db_json_analisi", "null").not_.is_("raw_json_odds", "null").limit(800).execute().data or [])
print("righe:", len(rows), " _OVERROUND_CORRECTION =", getattr(g, "_OVERROUND_CORRECTION", None))
def rps(p, o):
    c = np.cumsum(p) - np.cumsum(o); return float(np.sum(c[:-1] ** 2) / 2)
acc = {"quote(de-vig prop.)": [], "poisson grezzo": [], "poisson calibrato": []}
for r in rows:
    h, a = r["result_home_goals"], r["result_away_goals"]
    if h is None: continue
    o = np.array([h > a, h == a, h < a], float)
    q = _extract_implied_1x2(r["raw_json_odds"])
    m = (r.get("m") or {}).get("1x2"); mc = (r.get("mc") or {}).get("1x2")
    if not (q and m and mc): continue
    q = np.array(q); q = q / q.sum()
    for k, p in (("quote(de-vig prop.)", q), ("poisson grezzo", np.array([m["H"], m["D"], m["A"]])), ("poisson calibrato", np.array([mc["H"], mc["D"], mc["A"]]))):
        acc[k].append((rps(p, o), float(np.sum((p - o) ** 2)), -math.log(max(p[o.argmax()], 1e-12))))
for k, v in acc.items():
    v = np.array(v); print(f"{k:22s} n={len(v)} RPS={v[:,0].mean():.4f} Brier={v[:,1].mean():.4f} logloss={v[:,2].mean():.4f}")
# prova semplice di combinazione 50/50 quote+poisson calibrato
ys = []
for r in rows:
    h, a = r["result_home_goals"], r["result_away_goals"]
    q = _extract_implied_1x2(r["raw_json_odds"]); mc = (r.get("mc") or {}).get("1x2")
    if h is None or not (q and mc): continue
    q = np.array(q); q = q / q.sum(); p = np.array([mc["H"], mc["D"], mc["A"]])
    o = np.array([h > a, h == a, h < a], float)
    ys.append([rps(w * q + (1 - w) * p, o) for w in (0, 0.25, 0.5, 0.75, 1)])
print("RPS blend quote/poisson_cal con peso quote w=0,.25,.5,.75,1:", np.round(np.mean(ys, axis=0), 4))
