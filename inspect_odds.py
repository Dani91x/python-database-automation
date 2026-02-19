
import os
import sys
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db_client import get_supabase_client

def inspect_odds():
    sb = get_supabase_client()
    # Get 5 rows to see structure and market types
    res = sb.table("match_odds").select("*").limit(5).execute()
    data = res.data
    if data:
        print(json.dumps(data, indent=2))
    else:
        print("No data found in match_odds")

if __name__ == "__main__":
    inspect_odds()
