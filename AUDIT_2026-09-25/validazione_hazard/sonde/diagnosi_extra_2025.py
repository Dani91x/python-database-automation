"""Diagnosi (solo cache): partite con/senza eventi in recupero registrati (minute_extra), per stagione/lega/mese."""
import collections

from Betfair.stream.scalper.validazione_hazard import banco as B

D = B.carica_tutto(B.CACHE_DEFAULT)
P = D["partite"]
con_extra = collections.defaultdict(int)
for e in D["eventi"]:
    if e.get("minute_extra") is not None and (e.get("minute_extra") or 0) > 0:
        con_extra[e["fixture_id"]] += 1
tab = collections.defaultdict(lambda: [0, 0])
per_mese = collections.defaultdict(lambda: [0, 0])
for p in P:
    if p.season < 2024:
        continue
    ok = con_extra.get(p.fixture_id, 0) > 0
    tab[(p.season, p.league_id)][0] += 1
    tab[(p.season, p.league_id)][1] += ok
    per_mese[(p.season, p.date[:7])][0] += 1
    per_mese[(p.season, p.date[:7])][1] += ok
for k in sorted(tab):
    print(k, f"{tab[k][1]}/{tab[k][0]}")
for k in sorted(per_mese):
    print(k, f"{per_mese[k][1]}/{per_mese[k][0]}")
