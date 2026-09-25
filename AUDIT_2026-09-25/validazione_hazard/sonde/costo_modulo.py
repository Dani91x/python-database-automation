"""Misure (solo cache): costo del modulo atlante_v4 per UNA lega (Championship,
10 stagioni) e tassi grezzi del recupero sul 2024 (stagione con recupero registrato)."""
import time

import numpy as np

from Betfair.stream.scalper import atlante_v4 as V4
from Betfair.stream.scalper.validazione_hazard import banco as B

D = B.carica_tutto(B.CACHE_DEFAULT)
S, P = D["S"], D["partite"]
lega = [p for p in P if p.league_id == 40 and p.season <= 2024]
t0 = time.perf_counter()
st = V4.stato_lega_v4_vuoto(40)
for p in lega:
    V4.aggiungi_partita_v4(st, p)
t1 = time.perf_counter()
blocco = V4.assembla_v4({"40": st}, generated_at="2026-09-25T00:00:00+00:00", stagione_rif=2025)
t2 = time.perf_counter()
atlas = {"meta": {"generated_at": "2026-09-25T00:00:00+00:00"}, "v4": blocco}
for m in range(10000):
    V4.consulta_atlante_v4(atlas, m % 98, m % 4, 40, lambda_home=1.4, lambda_away=1.1)
t3 = time.perf_counter()
import json
print(f"partite {len(lega)}: conteggio {t1 - t0:.2f}s, assemblaggio {t2 - t1:.3f}s, "
      f"consultazione {1000 * (t3 - t2) / 10000:.3f} ms; stato {len(json.dumps(st)) / 1024:.0f} KB "
      f"(di cui fixture_id {len(json.dumps(st['fixtures'])) / 1024:.0f} KB), blocco {len(json.dumps(blocco)) / 1024:.0f} KB")
m24 = S["stagione"] == 2024
for nome, m in (("85-89 regolari", m24 & (S["stop"] == 0) & (S["m_live"] >= 85)),
                ("recupero 2T", m24 & (S["stop"] == 1) & (S["tempo"] == 2)),
                ("recupero 1T (vivo provato)", m24 & (S["stop"] == 1) & (S["tempo"] == 1))):
    print(nome, int(m.sum()), "y3", round(float(S["y3"][m].mean()), 4), "y2", round(float(S["y2"][m].mean()), 4))
