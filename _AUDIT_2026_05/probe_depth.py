"""READ-ONLY: che profondita' dati ho davvero? Mercati con quote + copertura xG."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_client import get_supabase_client
from collections import defaultdict
c = get_supabase_client()

def sec(t): print("\n"+"="*70+f"\n{t}\n"+"="*70)

# 1. Mercati con quote: market_key x snapshot_type, su un campione ampio per lega
sec("1. match_odds: market_key x snapshot_type (per alcune leghe principali)")
for lid in [39, 135, 78]:
    rows = c.table("match_odds").select("market_key,market_name,snapshot_type,bookmaker_name") \
        .eq("league_id", lid).limit(8000).execute().data
    mk = defaultdict(int); snap = defaultdict(int); names = {}
    for r in rows:
        mk[r.get("market_key")] += 1
        snap[r.get("snapshot_type")] += 1
        names[r.get("market_key")] = r.get("market_name")
    print(f"  lega {lid}: snapshot={dict(snap)}")
    for k in sorted(mk, key=lambda x:-mk[x])[:15]:
        print(f"     market_key={k:>4}  {str(names.get(k))[:32]:32s}  n={mk[k]}")

# 2. api_football odds: quali mercati? (snapshot_type='api_football')
sec("2. match_odds snapshot_type='api_football': mercati disponibili (quote live multi-mercato)")
rows = c.table("match_odds").select("market_key,market_name,label,bookmaker_name") \
    .eq("snapshot_type", "api_football").limit(5000).execute().data
print(f"  righe api_football campione: {len(rows)}")
mm = defaultdict(int)
for r in rows:
    mm[(r.get("market_key"), r.get("market_name"))] += 1
for (k,nm),n in sorted(mm.items(), key=lambda x:-x[1])[:25]:
    print(f"     {str(k):>5} {str(nm)[:38]:38s} n={n}")

# 3. xG coverage: quante partite hanno expected_goals, per lega
sec("3. expected_goals: copertura per lega (n righe team-match con xG)")
for lid in [39, 40, 61, 78, 88, 135, 140, 144, 94, 71, 197, 203]:
    try:
        n = c.table("match_team_stats").select("id", count="exact") \
            .eq("league_id", lid).eq("stat_type", "expected_goals").limit(1).execute().count
        print(f"  lega {lid}: {n} righe xG")
    except Exception as e:
        print(f"  lega {lid}: ERR {str(e)[:50]}")
