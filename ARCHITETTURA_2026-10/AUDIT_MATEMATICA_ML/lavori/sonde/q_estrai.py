"""Sonda Q1: 4 SELECT di sola lettura (stesso campione di m_estrai.py: FT, db_json_analisi e raw_json_odds non null,
21/09-07/10) con SOLO i timestamp: raw_json_odds->>'update', generated_at Poisson e ML, created_at/updated_at.
Salva q_ts.json."""
import sys, json, os
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from db_client import get_supabase_client
sb = get_supabase_client()
SEL = ("fixture_id,fixture_date,created_at,updated_at,"
       "upd:raw_json_odds->>update,fx_date_odds:raw_json_odds->fixture->>date,"
       "p_gen:db_json_analisi->>generated_at,ml_gen:model_predictions_json->>generated_at")
WIN = [("2026-09-21","2026-09-25"),("2026-09-25","2026-09-29"),("2026-09-29","2026-10-03"),("2026-10-03","2026-10-08")]
out, stats = [], []
for a, b in WIN:
    r = (sb.table("fixture_predictions").select(SEL).eq("result_status_short","FT")
         .gte("fixture_date",a).lt("fixture_date",b).not_.is_("db_json_analisi","null").not_.is_("raw_json_odds","null")
         .order("fixture_id").limit(1000).execute().data or [])
    stats.append((a, b, len(r))); out.extend(r)
print("finestre:", stats, "totale", len(out))
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "q_ts.json"), "w"))
