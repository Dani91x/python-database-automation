"""Prova (solo cache): parita' di A0 col v3 committato."""
import json
import time

from Betfair.stream.scalper.validazione_hazard.dati import stagioni_valide
from Betfair.stream.scalper.validazione_hazard.parita import confronta_v3
from Betfair.stream.scalper.validazione_hazard.produzione import LettoreCache, atlante_a0
from Betfair.stream.scalper.validazione_hazard.raccogli import carica

C = "AUDIT_2026-09-25/validazione_hazard/cache/"
L = LettoreCache(carica(C + "matches.json.gz"), carica(C + "eventi.json.gz"))
v3 = json.load(open("Betfair/omega/data/hazard_atlas_v3.json"))
val = stagioni_valide(carica(C + "coverage.json.gz"))
leghe = [40, 140, 39, 135, 62, 61, 78, 88, 94, 144, 179]
t0 = time.time()
atlas, stati = atlante_a0(L, {l: [s for s in val[l] if 2016 <= s <= 2025] for l in leghe})
print("A0 in", round(time.time() - t0, 1), "s")
r = confronta_v3(v3, stati, [str(l) for l in leghe])
print(json.dumps({k: v for k, v in r.items() if k != "leghe"}, indent=1))
for l, x in r["leghe"].items():
    print(l, x)
