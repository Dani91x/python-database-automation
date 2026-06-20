import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_client import get_supabase_client
sb = get_supabase_client()
rows = sb.table("matches").select(
    "fixture_id,season_year,status_short,home_team_name,away_team_name,"
    "goals_home,goals_away,fulltime_home,fulltime_away,extratime_home,extratime_away,"
    "penalty_home,penalty_away,halftime_home,halftime_away"
).eq("league_id", 1).execute().data
played = [r for r in rows if r["status_short"] in ("FT","AET","PEN")]
mm = [r for r in played if r["fulltime_home"] is not None and r["goals_home"] is not None
      and r["fulltime_home"] != r["goals_home"]]
print(f"mismatch goals_home != fulltime_home: {len(mm)}")
from collections import Counter
print("status dei mismatch:", dict(Counter(r["status_short"] for r in mm)))
for r in mm:
    print(f"  {r['season_year']} {r['status_short']:3} {r['home_team_name'][:14]:14} vs {r['away_team_name'][:14]:14} "
          f"| goals {r['goals_home']}-{r['goals_away']} ft {r['fulltime_home']}-{r['fulltime_away']} "
          f"et {r['extratime_home']}-{r['extratime_away']} pen {r['penalty_home']}-{r['penalty_away']} ht {r['halftime_home']}-{r['halftime_away']}")
# Quante AET/PEN in totale?
print("\nstatus totali (giocate):", dict(Counter(r["status_short"] for r in played)))
