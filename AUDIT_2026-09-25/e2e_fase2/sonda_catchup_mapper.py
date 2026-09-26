"""sonda_catchup_mapper.py - verifica che leagues_mapper (run 26/09 06:18:52-06:20:00Z)
abbia davvero toccato api_coverage_by_season intorno a quell'orario. SOLA LETTURA."""
import sys
sys.path.insert(0, ".")
from db_client import get_supabase_client

sb = get_supabase_client()
resp = sb.table("api_coverage_by_season").select(
    "league_id,season_year,updated_at", count="exact") \
    .gte("updated_at", "2026-09-26T06:15:00Z").lte("updated_at", "2026-09-26T06:25:00Z") \
    .order("updated_at", desc=False).limit(10).execute()
print("righe toccate 06:15-06:25 UTC 26/09 (count esatto):", resp.count)
for r in (resp.data or [])[:10]:
    print(" ", r)
