"""Prova (solo cache): partite e stati del banco, tassi grezzi."""
import collections
import time

import numpy as np

from Betfair.stream.scalper.validazione_hazard.dati import costruisci_partite
from Betfair.stream.scalper.validazione_hazard.raccogli import carica
from Betfair.stream.scalper.validazione_hazard.stati import tabella_stati

C = "AUDIT_2026-09-25/validazione_hazard/cache/"
t0 = time.time()
P, res = costruisci_partite(carica(C + "matches.json.gz"), carica(C + "eventi.json.gz"),
                            carica(C + "coverage.json.gz"))
print("partite", len(P), res["scarti"], res["non_ft"], res["stagioni_saltate_copertura"],
      res["stagioni_senza_eventi_coverage"][:30], round(time.time() - t0, 1), "s")
print(collections.Counter((p.league_id) for p in P))
t0 = time.time()
S = tabella_stati(P)
print("stati", len(S["y3"]), round(time.time() - t0, 1), "s")
for nome, msk in (("reg", S["stop"] == 0), ("rec1", (S["stop"] == 1) & (S["tempo"] == 1)),
                  ("rec2", (S["stop"] == 1) & (S["tempo"] == 2))):
    print(nome, int(msk.sum()), "y2", round(S["y2"][msk].mean(), 4), "y3", round(S["y3"][msk].mean(), 4))
for s in range(2016, 2026):
    msk = (S["stagione"] == s) & (S["stop"] == 0)
    print(s, int(msk.sum()), round(S["y3"][msk].mean(), 4))
msk = (S["stop"] == 1) & (S["tempo"] == 2)
for j in range(0, 12):
    mj = msk & (S["j"] == j)
    print("rec2 j", j, int(mj.sum()), round(S["y3"][mj].mean(), 4) if mj.any() else None)
m8 = (S["stop"] == 0) & (S["tempo"] == 2) & (S["t"] >= 40)
print("85-89 reg", round(S["y3"][m8].mean(), 4))
print("rossi stati", int(((S["rh"] + S["ra"]) > 0).sum()))
