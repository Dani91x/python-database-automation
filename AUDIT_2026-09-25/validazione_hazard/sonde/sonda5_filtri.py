"""SONDA IN SOLA LETTURA (25/09): verifica la sintassi dei filtri del raccoglitore
e le varianti di 'detail' dei cartellini non gialli (2 GET)."""
import collections
import sys

from Betfair.stream.scalper.genera_atlante import LettoreDB
from Betfair.stream.scalper.validazione_hazard.raccogli import (FILTRO_EVENTI_RECUPERO, _filtro,
                                                                leggi_env)

env = leggi_env(r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/.env")
L = LettoreDB(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])
m = L.get("matches", {"select": "fixture_id", "league_id": "eq.39", "season_year": "eq.2024",
                      "limit": "250"})
lista = ",".join(str(x["fixture_id"]) for x in m)
card = L.get("match_events", {"select": "detail", "fixture_id": f"in.({lista})",
                              "event_type": "eq.Card", "detail": "neq.Yellow Card"})
print(collections.Counter(r["detail"] for r in card))
ev = L.get("match_events", _filtro({"select": "event_type,detail,minute,minute_extra",
                                    "fixture_id": f"in.({lista})", "limit": "5000"},
                                   FILTRO_EVENTI_RECUPERO))
print(len(ev), collections.Counter((r["event_type"], r["detail"]) for r in ev).most_common(12))
print("richieste", L.n_richieste, "righe", L.n_righe, file=sys.stderr)
