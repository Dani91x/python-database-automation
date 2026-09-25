"""SONDA IN SOLA LETTURA (25/09, validazione hazard), terza: copertura REALE per
lega/stagione (api_coverage_by_season_v2_mv, 726 righe, UNA GET) per scegliere
le 3 leghe piccole (< 300 partite con eventi fino al 2024, presenti nel 2025)."""
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


rows = get("api_coverage_by_season_v2_mv", {"select": "*", "limit": "5000"})
print(sorted(rows[0].keys()))
json.dump(rows, open("AUDIT_2026-09-25/validazione_hazard/sonde/coverage_v2_mv.json", "w"), default=str)
