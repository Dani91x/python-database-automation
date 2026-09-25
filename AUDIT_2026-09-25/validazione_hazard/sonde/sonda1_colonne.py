"""SONDA IN SOLA LETTURA (25/09, validazione hazard): colonne vere di matches,
match_events e fixture_predictions su UNA partita. Solo GET con limit/eq.
Credenziali lette a mano dal .env del repo principale (mai load_dotenv)."""
import json
import sys
import time
import urllib.parse
import urllib.request

ENV = r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/.env"
env = {}
for l in open(ENV, encoding="utf-8"):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_ROLE_KEY"]
N = {"req": 0, "rows": 0}


def get(t, p):
    q = urllib.parse.urlencode(p, safe="(),.*:!>-")
    r = urllib.request.Request(f"{URL}/rest/v1/{t}?{q}", method="GET")
    r.add_header("apikey", KEY)
    r.add_header("Authorization", "Bearer " + KEY)
    t0 = time.time()
    with urllib.request.urlopen(r, timeout=60) as h:
        rows = json.loads(h.read().decode())
    N["req"] += 1
    N["rows"] += len(rows)
    print(f"GET {t} {len(rows)} {time.time() - t0:.2f}s", file=sys.stderr)
    return rows


m = get("matches", {"select": "*", "league_id": "eq.39", "season_year": "eq.2024", "limit": "1"})
print(json.dumps(m, default=str)[:3000])
fid = m[0]["fixture_id"]
e = get("match_events", {"select": "*", "fixture_id": f"eq.{fid}"})
print(json.dumps(e[:2], default=str)[:1500])
print(sorted({(x["event_type"], x["detail"]) for x in e}))
print([(x["event_type"], x["minute"], x["minute_extra"]) for x in e if x.get("minute_extra") is not None])
fp = get("fixture_predictions", {"select": "fixture_id,fixture_date,league_id,db_json_analisi",
                                 "fixture_id": f"eq.{fid}"})
print(json.dumps(fp, default=str)[:4000])
print(N)
