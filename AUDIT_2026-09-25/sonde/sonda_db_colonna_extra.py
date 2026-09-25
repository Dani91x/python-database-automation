"""Sonda sul DB VERO in SOLA LETTURA (4 GET): quanto costa aggiungere
``extra:raw_json->fixture->status->extra`` alla select di ``matches``.

Stessa query del bootstrap (una lega-stagione, ordine per fixture_id), prima
con le colonne di ieri e poi con quelle di oggi, alternate due volte: righe,
byte della risposta, millisecondi; e quante righe hanno ``extra``.
Il .env si legge A MANO (mai load_dotenv), come ``raccogli --env``.
Uso: python sonda_db_colonna_extra.py <percorso .env> [lega] [stagione]
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, RADICE)

from Betfair.stream.scalper import genera_atlante as G  # noqa: E402
from Betfair.stream.scalper.validazione_hazard.raccogli import leggi_env  # noqa: E402


def get(url: str, key: str, params: dict) -> tuple:
    q = urllib.parse.urlencode(params, safe="(),.*:!")      # come G.LettoreDB
    req = urllib.request.Request(f"{url}/rest/v1/matches?{q}", method="GET")
    req.add_header("apikey", key)
    req.add_header("Authorization", "Bearer " + key)
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        corpo = r.read()
    return json.loads(corpo.decode("utf-8")), len(corpo), (time.perf_counter() - t0) * 1000


def main() -> None:
    env = leggi_env(sys.argv[1])
    url, key = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_ROLE_KEY"]
    lega = int(sys.argv[2]) if len(sys.argv) > 2 else 39
    anno = int(sys.argv[3]) if len(sys.argv) > 3 else 2024
    prima = G.COLONNE_MATCH.replace(",extra:raw_json->fixture->status->extra", "")
    for giro in range(2):
        for nome, col in (("prima", prima), ("dopo", G.COLONNE_MATCH)):
            rows, byte, ms = get(url, key, {"select": col, "league_id": f"eq.{lega}",
                                            "season_year": f"eq.{anno}", "order": "fixture_id.asc",
                                            "limit": "1000"})
            con_extra = sum(1 for r in rows if r.get("extra") is not None)
            print(f"giro {giro} {nome}: righe {len(rows)}, byte {byte}, {ms:.0f} ms, con extra {con_extra}")
            time.sleep(1.0)


if __name__ == "__main__":
    main()
