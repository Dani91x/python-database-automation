"""SONDA IN SOLA LETTURA (25/09, atlante a domanda): quante leghe compaiono in
una giornata (fixture_predictions, la fonte che Safe/Omega gia' usano per le
fixture del giorno) e quante stagioni con eventi hanno in coverage.
Solo GET con limit; nessuna scrittura. Legge le credenziali dal .env del repo
principale (passato come argomento)."""
import collections
import json
import sys
import time
import urllib.parse
import urllib.request

env = {}
for l in open(sys.argv[1], encoding="utf-8"):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_ROLE_KEY"]
N = {"req": 0, "rows": 0}


def get(t, p):
    q = urllib.parse.urlencode(p, safe="(),.*:!")
    r = urllib.request.Request(f"{URL}/rest/v1/{t}?{q}", method="GET")
    r.add_header("apikey", KEY)
    r.add_header("Authorization", "Bearer " + KEY)
    t0 = time.time()
    with urllib.request.urlopen(r, timeout=60) as h:
        rows = json.loads(h.read().decode())
    N["req"] += 1
    N["rows"] += len(rows)
    print(f"  GET {t} {len(rows)} righe {time.time() - t0:.2f}s")
    return rows


out = {}
for nome, lo, hi in (("ieri", "2026-09-24T00:00:00+00:00", "2026-09-25T00:00:00+00:00"),
                     ("oggi", "2026-09-25T00:00:00+00:00", "2026-09-26T00:00:00+00:00"),
                     ("finestra_36h", "2026-09-24T12:00:00+00:00", "2026-09-26T12:00:00+00:00")):
    rows = get("fixture_predictions", {"select": "fixture_id,league_id", "fixture_date": f"gte.{lo}",
                                      "and": f"(fixture_date.lt.{hi})", "limit": "3000"})
    leghe = collections.Counter(r["league_id"] for r in rows)
    out[nome] = {"partite": len(rows), "leghe": len(leghe)}
    out[nome + "_ids"] = sorted(leghe)
ids = sorted(set(out["ieri_ids"]) | set(out["oggi_ids"]) | set(out["finestra_36h_ids"]))
cov = []
for i in range(0, len(ids), 150):
    blocco = ",".join(str(x) for x in ids[i:i + 150])
    cov += get("api_coverage_by_season", {"select": "league_id,season_year,fixtures_events",
                                          "league_id": f"in.({blocco})", "limit": "5000"})
per = collections.defaultdict(dict)
for r in cov:
    per[r["league_id"]][r["season_year"]] = bool(r["fixtures_events"])


def stag(lid, n=10):
    ev = sorted(y for y, e in per.get(lid, {}).items() if e)
    return ev[-n:]


for nome in ("ieri", "oggi", "finestra_36h"):
    L = out[nome + "_ids"]
    out[nome]["leghe_con_eventi"] = sum(1 for l in L if stag(l))
    out[nome]["coppie_lega_stagione_ult10"] = sum(len(stag(l)) for l in L)
    out[nome]["leghe_2026_eventi_false"] = sum(1 for l in L if per.get(l, {}).get(2026) is False)
    out[nome]["leghe_2026_eventi_true"] = sum(1 for l in L if per.get(l, {}).get(2026) is True)
    out[nome]["leghe_2026_assente_in_coverage"] = sum(1 for l in L if 2026 not in per.get(l, {}))
    out[nome]["leghe_2025_eventi_true"] = sum(1 for l in L if per.get(l, {}).get(2025) is True)
    out[nome]["leghe_senza_coverage"] = sum(1 for l in L if l not in per)
v3 = {2, 4, 13, 39, 40, 45, 46, 61, 62, 71, 78, 88, 94, 135, 140, 144, 179, 180, 261, 305, 390}
out["finestra_36h"]["leghe_gia_nel_v3"] = len(v3 & set(out["finestra_36h_ids"]))
for k in list(out):
    if k.endswith("_ids"):
        out[k] = len(out[k])
out["costo_misura"] = N
print(json.dumps(out, indent=1))
