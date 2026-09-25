"""Sonda SOLA LETTURA (GET PostgREST) per il catchup P4 (25/09/2026). Nessuna scrittura.
Uso: python p4_sonda_get.py <tabella> <query> [out.json]"""
import json
import os
import sys
import time

import requests

ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "..", ".env")
env = {}
for riga in open(ENV, encoding="utf-8"):
    if "=" in riga and not riga.startswith("#"):
        k, v = riga.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
url = env["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + sys.argv[1] + "?" + sys.argv[2]
key = env["SUPABASE_SERVICE_ROLE_KEY"]
t = time.time()
r = requests.get(url, headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=60)
print("HTTP", r.status_code, "sec", round(time.time() - t, 2), "content-range", r.headers.get("content-range"))
if len(sys.argv) > 3 and r.status_code == 200:
    json.dump(r.json(), open(sys.argv[3], "w"), default=str)
    print("salvato", len(r.json()))
else:
    print(r.text[:1500])
