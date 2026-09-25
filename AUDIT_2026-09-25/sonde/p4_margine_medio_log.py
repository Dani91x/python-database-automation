"""Margine medio degli ultimi 7 giorni sul DB vero con la funzione di produzione (25/09/2026).
SOLA LETTURA: api_quota.consumo_giorni_log = 1 select di max(id) + 8 count su finestra di PK di api_call_log.
Uso: python AUDIT_2026-09-25/sonde/p4_margine_medio_log.py"""
import os
import sys

RADICE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, RADICE)
env = {}
for riga in open(os.path.join(RADICE, "..", "..", "..", ".env"), encoding="utf-8"):
    if "=" in riga and not riga.startswith("#"):
        k, v = riga.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
from supabase import create_client  # noqa: E402

import api_quota  # noqa: E402

sb = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])
giorni = api_quota.consumo_giorni_log(sb, 7)
for g, n in giorni:
    print(f"{g}: {n} chiamate in api_call_log, margine avanzato max(0, 7500 - 3000 - n) = {max(0, 4500 - n)}")
print("margine medio:", sum(max(0, 4500 - n) for _, n in giorni) / len(giorni))
