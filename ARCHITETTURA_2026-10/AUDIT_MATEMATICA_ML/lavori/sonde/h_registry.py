"""h_: verifica avversaria B R2/R3: Brier per target dal registry (SOLO SELECT, 2 query, limit 2000)."""
import sys, statistics as st
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from db_client import get_supabase_client
sb = get_supabase_client()
allr = []
for tg in (["target_btts", "target_over_2_5"],):
    r = sb.table("ai_model_registry").select("league_id,target,brier,train_rows,trained_at").in_("target", tg).limit(2000).execute().data or []
    print("query", tg, "righe", len(r)); allr += r
for t in ["target_btts", "target_over_2_5"]:
    xs = [x for x in allr if x["target"] == t and x["brier"] is not None]
    b = sorted(float(x["brier"]) for x in xs)
    n = len(b)
    if not n: continue
    tr = [x["train_rows"] for x in xs if x["train_rows"]]
    print(f"{t}: n={n} brier med {st.median(b):.4f} p10 {b[n//10]:.4f} p90 {b[9*n//10]:.4f} min {b[0]:.4f} max {b[-1]:.4f} "
          f"| <0.15: {sum(v<0.15 for v in b)} | >0.50: {sum(v>0.5 for v in b)} ({100*sum(v>0.5 for v in b)/n:.0f}%) | BSS>=0.12 (brier<=0.44): {sum(v<=0.44 for v in b)} ({100*sum(v<=0.44 for v in b)/n:.0f}%)"
          f" | train_rows med {st.median(tr) if tr else None} -> holdout ~{0.1/0.75*st.median(tr) if tr else 0:.0f}")
