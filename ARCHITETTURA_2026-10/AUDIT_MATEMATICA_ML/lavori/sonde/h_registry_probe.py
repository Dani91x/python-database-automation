import sys
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from db_client import get_supabase_client
sb = get_supabase_client()
r = sb.table("ai_model_registry").select("league_id,target,brier,train_rows").limit(5).execute().data
print(r)
