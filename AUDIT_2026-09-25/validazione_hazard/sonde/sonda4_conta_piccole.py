"""SONDA IN SOLA LETTURA (25/09, validazione hazard), quarta: partite FT 2023-2025
per 11 leghe candidate "piccole" (eventi dichiarati solo dal 2023/2024). Solo GET
paginate per fixture_id."""
import collections
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


def get(t, p):
    q = urllib.parse.urlencode(p, safe="(),.*:!>-")
    r = urllib.request.Request(f"{URL}/rest/v1/{t}?{q}", method="GET")
    r.add_header("apikey", KEY)
    r.add_header("Authorization", "Bearer " + KEY)
    t0 = time.time()
    with urllib.request.urlopen(r, timeout=90) as h:
        rows = json.loads(h.read().decode())
    print(f"GET {t} {len(rows)} {time.time() - t0:.2f}s", file=sys.stderr)
    return rows


leghe = "395,613,833,834,835,836,962,478,534,545,306"
out, ultimo = [], None
while True:
    p = {"select": "fixture_id,league_id,season_year,status_short",
         "league_id": f"in.({leghe})", "season_year": "in.(2023,2024,2025)",
         "order": "fixture_id.asc", "limit": "1000"}
    if ultimo:
        p["fixture_id"] = f"gt.{ultimo}"
    rows = get("matches", p)
    out += rows
    if len(rows) < 1000:
        break
    ultimo = rows[-1]["fixture_id"]
c = collections.Counter((r["league_id"], r["season_year"]) for r in out if r["status_short"] == "FT")
for k in sorted(c):
    print(k, c[k])
