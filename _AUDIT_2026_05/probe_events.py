"""READ-ONLY: match_events ha i tempi dei gol? Struttura + copertura per lega."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_client import get_supabase_client
from collections import defaultdict
c = get_supabase_client()

# struttura: tipi di evento e campi
print("=== sample match_events ===")
rows = c.table("match_events").select("*").limit(20).execute().data
if rows:
    print("colonne:", list(rows[0].keys()))
    for r in rows[:8]:
        print({k: r.get(k) for k in ["fixture_id", "team_id", "event_type", "detail", "minute", "minute_extra"] if k in r})

print("\n=== distinct event_type (campione) ===")
rows = c.table("match_events").select("event_type").limit(5000).execute().data
et = defaultdict(int)
for r in rows:
    et[r.get("event_type")] += 1
for k, v in sorted(et.items(), key=lambda x: -x[1]):
    print(f"   {k}: {v}")

print("\n=== copertura gol per lega (n eventi Goal) ===")
for lid in [39, 135, 78, 88, 144]:
    try:
        n = c.table("match_events").select("id", count="exact") \
            .eq("league_id", lid).eq("event_type", "Goal").limit(1).execute().count
        print(f"   lega {lid}: {n} eventi Goal")
    except Exception as e:
        print(f"   lega {lid}: ERR {str(e)[:60]}")
