"""V2: 1 SELECT LIMIT 5 su live_now per vedere order_mode oggi (sola lettura)."""
import sys, json
sys.path.insert(0, r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation")
from db_client import get_supabase_client
sb = get_supabase_client()
rows = sb.table("live_now").select("*").limit(5).execute().data or []
for r in rows:
    st = r.get("state") or {}
    print({k: (v if not isinstance(v, (dict, list)) else "...") for k, v in r.items() if k in ("id", "updated_at", "key")},
          "order_mode=", st.get("order_mode") if isinstance(st, dict) else st)
print("righe:", len(rows))
