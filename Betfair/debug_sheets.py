import os
import json
from supabase import create_client, Client
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from db_client import get_supabase_client

def debug_data():
    supabase = get_supabase_client()
    today = "2026-02-25"
    tomorrow = "2026-02-26"
    
    res = supabase.from_("fixture_predictions").select("*").gte("fixture_date", today).lt("fixture_date", tomorrow).execute()
    data = res.data or []
    
    if data:
        f = data[0]
        print(f"Sample Fixture: {f.get('home_team_name')} vs {f.get('away_team_name')}")
        print(f"fixture_date: '{f.get('fixture_date')}'")

if __name__ == "__main__":
    debug_data()
