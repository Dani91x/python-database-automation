"""D5 (25/09) - SOLA LETTURA: i nomi VERI dei round di API-Football che
contengono "final" (tabella `matches`, `raw_json->league->>round`).
Una SELECT a pagine da 1000, sola proiezione del round. Nessuna scrittura."""
import os
from collections import Counter

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", ".env"))
from supabase import create_client  # noqa: E402

sb = create_client(os.environ["SUPABASE_URL"],
                   os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"])
c: Counter = Counter()
for lo, hi in (("2025-05-01", "2025-07-15"), ("2026-05-01", "2026-07-20")):
  for off in range(0, 20000, 1000):
    r = (sb.table("matches").select("round:raw_json->league->>round")
          .gte("fixture_date", lo).lt("fixture_date", hi)
         .ilike("raw_json->league->>round", "%final%")
         .range(off, off + 999).execute().data)
    c.update(x.get("round") for x in r)
    if len(r) < 1000:
        break
for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
    print(v, repr(k))
