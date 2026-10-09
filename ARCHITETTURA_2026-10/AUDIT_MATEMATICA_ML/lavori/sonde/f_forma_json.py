import sys, json
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from db_client import get_supabase_client
sb = get_supabase_client()
r = (sb.table("fixture_predictions").select("fixture_id,fixture_date,db_json_analisi,tactical_engine_json,updated_at")
     .not_.is_("db_json_analisi", "null").order("updated_at", desc=True).limit(5).execute().data or [])
for x in r:
    a = x.get("db_json_analisi"); t = x.get("tactical_engine_json")
    print(x["fixture_id"], x["fixture_date"], x.get("updated_at"), "| analisi tipo:", type(a).__name__,
          "| chiavi:", sorted(a.keys()) if isinstance(a, dict) else None,
          "| mc:", sorted((a.get("markets_calibrated") or {}).keys()) if isinstance(a, dict) else None,
          "| src:", a.get("calibration_source") if isinstance(a, dict) else None,
          "| gen:", a.get("generated_at") if isinstance(a, dict) else None,
          "| tact tipo:", type(t).__name__, (t or {}).get("generated_at") if isinstance(t, dict) else None)
