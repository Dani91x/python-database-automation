"""h_: D R1. 1 SELECT limit 2000 su engine_signals (finestra run_date>=2026-09-15, ordinata per fixture_id). Misura righe per (fixture,market)."""
import sys, collections, statistics as st
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from db_client import get_supabase_client
sb = get_supabase_client()
rows = (sb.table("engine_signals").select("fixture_id,run_date,market,odds,signal_uid")
        .gte("run_date", "2026-09-15").not_.is_("odds", "null").order("fixture_id").limit(2000).execute().data or [])
print("righe", len(rows))
lastf = rows[-1]["fixture_id"]; rows = [r for r in rows if r["fixture_id"] != lastf]
g = collections.defaultdict(list)
for r in rows: g[(r["fixture_id"], r["market"])].append(float(r["odds"]))
n = len(g); multi = {k: v for k, v in g.items() if len(v) > 1}
print("gruppi (fixture,market):", n, "con >1 riga:", len(multi), f"({100*len(multi)/n:.0f}%)", "righe/gruppo max", max(len(v) for v in g.values()))
dist = collections.Counter(len(v) for v in g.values()); print("distribuzione righe/gruppo", sorted(dist.items()))
d_max_mean = [max(v) / (sum(v) / len(v)) - 1 for v in multi.values()]
d_max_min = [max(v) - min(v) for v in multi.values()]
if multi:
    print("gruppi multi: max/media-1 medio %.4f mediano %.4f max %.4f | max-min medio %.3f mediano %.3f" % (st.mean(d_max_mean), st.median(d_max_mean), max(d_max_mean), st.mean(d_max_min), st.median(d_max_min)))
    print("esempio:", list(multi.items())[:3])
mk = collections.Counter(m for (_, m) in g); print("mercati", mk.most_common(8))
