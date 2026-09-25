"""D5 (25/09) - SOLA LETTURA: forma delle colonne che Safe legge per i punti
1, 5, 6 (round della fixture, h2h e forze della Dashboard). Nessuna scrittura."""
import json
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", ".env"))
from supabase import create_client  # noqa: E402

sb = create_client(os.environ["SUPABASE_URL"],
                   os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"])
for t in ("fixture_predictions", "matches"):
    r = sb.table(t).select("*").limit(1).execute().data
    print(t, sorted(r[0].keys()) if r else None)
r = (sb.table("matches").select("fixture_id,round:raw_json->league->>round")
     .order("fixture_date", desc=True).limit(3).execute().data)
print(r)
r = (sb.table("fixture_predictions").select("fixture_id,raw_json").eq("status", "ok").not_.is_("raw_json", "null").lte("fixture_date", "2026-09-24")
     .order("fixture_date", desc=True).limit(1).execute().data)
rj = r[0]["raw_json"]
resp = (rj.get("response") or [rj])[0] if isinstance(rj, dict) else None
print(r[0]["fixture_id"], list(rj.keys()) if isinstance(rj, dict) else type(rj))
if resp:
    print(list(resp.keys()))
    print("league", resp.get("league"))
    print("comparison", json.dumps(resp.get("comparison"))[:400])
    print("teams.home keys", list((resp.get("teams") or {}).get("home", {}).keys()))
    print("last_5", json.dumps(resp["teams"]["home"].get("last_5"))[:300])
    print("league.goals.against",
          json.dumps(resp["teams"]["home"].get("league", {}).get("goals", {}).get("against"))[:300])
    h = resp.get("h2h") or []
    print("h2h n", len(h))
    if h:
        print(json.dumps(h[0])[:900])
