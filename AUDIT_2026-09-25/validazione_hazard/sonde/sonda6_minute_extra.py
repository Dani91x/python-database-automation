"""SONDA IN SOLA LETTURA (25/09): i gol al 45'/90' della stagione 2025 hanno
minute_extra NULL; il raw_json dell'evento ha time.extra? (1-2 GET)"""
import collections
import json

from Betfair.stream.scalper.genera_atlante import LettoreDB
from Betfair.stream.scalper.validazione_hazard.raccogli import carica, leggi_env

C = "AUDIT_2026-09-25/validazione_hazard/cache/"
M = carica(C + "matches.json.gz")
fids = sorted(m["fixture_id"] for m in M if m["league_id"] == 39 and m["season_year"] == 2025)[:200]
fids24 = sorted(m["fixture_id"] for m in M if m["league_id"] == 39 and m["season_year"] == 2024)[:200]
env = leggi_env(r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/.env")
L = LettoreDB(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])
for nome, lista in (("2025", fids), ("2024", fids24)):
    rows = L.get("match_events", {
        "select": "id,fixture_id,minute,minute_extra,rx:raw_json->time->extra,re:raw_json->time->elapsed,created_at,updated_at",
        "fixture_id": "in.(" + ",".join(map(str, lista)) + ")", "event_type": "eq.Goal",
        "minute": "in.(45,90)"})
    c = collections.Counter((r["minute"], r["minute_extra"] is not None, r["rx"] is not None) for r in rows)
    print(nome, len(rows), sorted(c.items()))
    print(nome, "esempi", json.dumps([r for r in rows if r["minute_extra"] is None][:4]))
    print(nome, "created", collections.Counter(str(r["created_at"])[:7] for r in rows).most_common(5))
print("richieste", L.n_richieste, "righe", L.n_righe)
