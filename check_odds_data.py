
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db_client import get_supabase_client

def check_odds():
    sb = get_supabase_client()
    # Simple select
    res = sb.table("match_odds").select("*").limit(1).execute()
    data = res.data
    print(f"Rows found: {len(data)}")
    if data:
        print("Sample:", data[0])

if __name__ == "__main__":
    check_odds()
