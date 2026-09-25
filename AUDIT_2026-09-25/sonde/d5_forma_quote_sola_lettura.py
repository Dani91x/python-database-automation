"""D5 (25/09) - SOLA LETTURA: forma delle fonti per la misura del punto 7
(tennis_markets: moneyline pre-partita; fixture_predictions.raw_json_odds).
Tre SELECT limit 1-2. Nessuna scrittura."""
import json
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", ".env"))
from supabase import create_client  # noqa: E402

sb = create_client(os.environ["SUPABASE_URL"],
                   os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"])
r = sb.table("tennis_markets").select("*").order("run_date").limit(1).execute().data
print("tennis_markets prima", r[0]["run_date"] if r else None, sorted(r[0].keys()) if r else None)
if r:
    x = r[0]
    print({k: x[k] for k in x if k not in ("markets", "full_odds")})
    print(json.dumps(x.get("markets"))[:500])
r = sb.table("tennis_markets").select("run_date").order("run_date", desc=True).limit(1).execute().data
print("tennis_markets ultima", r)
r = (sb.table("fixture_predictions").select("fixture_id,result_outcome,raw_json_odds")
     .eq("status", "ok").not_.is_("result_outcome", "null").not_.is_("raw_json_odds", "null")
     .lte("fixture_date", "2026-09-20").order("fixture_date", desc=True).limit(1).execute().data)
if r:
    print("result_outcome", r[0]["result_outcome"])
    print(json.dumps(r[0]["raw_json_odds"])[:900])
