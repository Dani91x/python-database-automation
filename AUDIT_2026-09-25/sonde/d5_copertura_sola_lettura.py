"""D5 (25/09) - SOLA LETTURA: copertura della finestra fixture di oggi in
`fixture_predictions` (fonte del matcher di Safe) e in `matches` (fonte del
round). Quattro SELECT con proiezione minima. Nessuna scrittura."""
import os
from collections import Counter

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", ".env"))
from supabase import create_client  # noqa: E402

sb = create_client(os.environ["SUPABASE_URL"],
                   os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"])
LO, HI = "2026-09-20T00:00:00+00:00", "2026-09-26T00:00:00+00:00"
fp = (sb.table("fixture_predictions").select("fixture_id,status")
      .gte("fixture_date", LO).lt("fixture_date", HI).limit(5000).execute().data)
ma = (sb.table("matches").select("fixture_id,round:raw_json->league->>round")
      .gte("fixture_date", LO).lt("fixture_date", HI).limit(5000).execute().data)
ids_fp = {r["fixture_id"] for r in fp}
ids_ma = {r["fixture_id"]: r.get("round") for r in ma}
print("fixture_predictions", len(ids_fp), Counter(r["status"] for r in fp))
print("matches", len(ids_ma), "con round", sum(1 for v in ids_ma.values() if v))
print("fp coperte da matches", len(ids_fp & set(ids_ma)), "/", len(ids_fp))
print("round (primi 15 tipi)", Counter(
    (v or "").split(" - ")[0] for v in ids_ma.values()).most_common(15))
# forma del blocco h2h via proiezione JSON (senza scaricare tutto raw_json)
r = (sb.table("fixture_predictions")
     .select("fixture_id,h2h:raw_json->response->0->h2h,cmp:raw_json->response->0->comparison")
     .gte("fixture_date", LO).lt("fixture_date", HI).eq("status", "ok").limit(20).execute().data)
print("proiezione h2h", [(x["fixture_id"], len(x.get("h2h") or []), bool(x.get("cmp"))) for x in r])
