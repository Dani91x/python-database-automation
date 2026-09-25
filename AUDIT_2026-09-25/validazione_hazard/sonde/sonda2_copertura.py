"""SONDA IN SOLA LETTURA (25/09, validazione hazard), seconda:
 - status.extra in matches.raw_json per la stagione 2025 (recupero annunciato?)
 - fixture_predictions sulla stagione 2025/2024: copertura e struttura di db_json_analisi
 - api_coverage_by_season: leghe con fixtures_events=true (per scegliere le piccole)
Solo GET."""
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
N = {"req": 0, "rows": 0}


def get(t, p):
    q = urllib.parse.urlencode(p, safe="(),.*:!>-")
    r = urllib.request.Request(f"{URL}/rest/v1/{t}?{q}", method="GET")
    r.add_header("apikey", KEY)
    r.add_header("Authorization", "Bearer " + KEY)
    t0 = time.time()
    with urllib.request.urlopen(r, timeout=90) as h:
        rows = json.loads(h.read().decode())
    N["req"] += 1
    N["rows"] += len(rows)
    print(f"GET {t} {len(rows)} {time.time() - t0:.2f}s", file=sys.stderr)
    return rows


m = get("matches", {"select": "fixture_id,fixture_date,status_short,extra:raw_json->fixture->status->extra",
                    "league_id": "eq.39", "season_year": "eq.2025", "limit": "400"})
print("PL2025 partite", len(m), "extra non null", sum(1 for x in m if x.get("extra") is not None),
      collections.Counter(x.get("extra") for x in m).most_common(8))
fids = [x["fixture_id"] for x in m][:200]
fp = get("fixture_predictions", {"select": "fixture_id,fixture_date,db_json_analisi",
                                 "fixture_id": "in.(" + ",".join(map(str, fids)) + ")"})
print("PL2025 fixture_predictions", len(fp), "su", len(fids))
if fp:
    d = fp[0]["db_json_analisi"]
    print(json.dumps(d, default=str)[:2500])
cov = get("api_coverage_by_season", {"select": "league_id,season_year,fixtures_events",
                                     "fixtures_events": "eq.true", "limit": "10000"})
per = collections.defaultdict(list)
for r in cov:
    per[r["league_id"]].append(r["season_year"])
print("leghe con eventi", len(per))
# candidate piccole: eventi su 2024 e 2025, prima del 2023 niente
picc = sorted(l for l, s in per.items() if 2025 in s and 2024 in s and min(s) >= 2023)
print("piccole candidate (eventi solo da 2023, con 2024 e 2025):", len(picc), picc[:80])
json.dump({str(k): sorted(v) for k, v in per.items()},
          open("AUDIT_2026-09-25/validazione_hazard/sonde/coverage_eventi.json", "w"))
print(N)
