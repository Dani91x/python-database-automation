
import os
import sys
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db_client import get_supabase_client

def inspect_odds():
    sb = get_supabase_client()
    res = sb.table("match_odds").select("*").limit(1).execute()
    data = res.data
    if data:
        print("Keys:", list(data[0].keys()))
        print("Sample:", json.dumps(data[0], indent=2))
    else:
        print("No data")

if __name__ == "__main__":
    inspect_odds()
