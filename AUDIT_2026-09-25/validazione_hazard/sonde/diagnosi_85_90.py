"""Diagnosi (solo cache): perche' A1 sul test prevede ~0.09 nella cella 85-90."""
import collections

import numpy as np

from Betfair.stream.scalper.validazione_hazard import banco as B
from Betfair.stream.scalper.validazione_hazard import candidati as CA

D = B.carica_tutto(B.CACHE_DEFAULT)
S, P = D["S"], D["partite"]
for s in range(2016, 2026):
    m = (S["stagione"] == s) & (S["stop"] == 0) & (S["m_live"] >= 85)
    m2 = (S["stagione"] == s) & (S["stop"] == 0) & (S["m_live"] >= 40) & (S["m_live"] < 45)
    print(s, "85-89 y3", round(S["y3"][m].mean(), 4), "40-44 y3", round(S["y3"][m2].mean(), 4))
c = collections.Counter()
for p in P:
    for g in p.gol:
        if g[1] > 45:
            c[(p.season, g[0])] += 1
print("gol in recupero per stagione/tempo", sorted(c.items()))
# stagioni vecchie: gol con minuto 90 senza extra?
ev = D["eventi"]
c2 = collections.Counter()
fx_season = {p.fixture_id: p.season for p in P}
for e in ev:
    if e["event_type"] == "Goal" and e["fixture_id"] in fx_season:
        if e["minute"] in (45, 90):
            c2[(fx_season[e["fixture_id"]], e["minute"], e["minute_extra"] is not None)] += 1
print(sorted(c2.items()))
leghe = np.array(sorted({p.league_id for p in P}))
lam = np.ones(S["y3"].size) * 2.7
for tm in (2023, 2024):
    tr = np.flatnonzero(S["stagione"] <= tm)
    mod = CA.addestra_a(CA.ConfA(), S, tr, leghe, lam, tm + 1)
    print(tm, "globale cella 17 p3", mod.info["globale_3"][17], "cella 8", mod.info["globale_3"][8])
    ev_i = np.flatnonzero((S["stagione"] == tm + 1) & (S["stop"] == 0) & (S["m_live"] >= 85))
    pr = CA.prevedi_a(mod, S, ev_i, lam)
    print("  prevista 85-89", pr["p3"].mean(), "osservata", S["y3"][ev_i].mean())
