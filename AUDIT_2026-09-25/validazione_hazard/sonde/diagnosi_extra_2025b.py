"""Diagnosi (solo cache): gol al 45'/90' con/senza minute_extra per stagione, lega, mese."""
import collections

from Betfair.stream.scalper.validazione_hazard import banco as B

D = B.carica_tutto(B.CACHE_DEFAULT)
fx = {p.fixture_id: p for p in D["partite"]}
lega = collections.defaultdict(lambda: [0, 0])
mese = collections.defaultdict(lambda: [0, 0])
per_partita = collections.defaultdict(lambda: [0, 0])
for e in D["eventi"]:
    p = fx.get(e["fixture_id"])
    if p is None or e["event_type"] != "Goal" or e["minute"] not in (45, 90) or p.season < 2023:
        continue
    ok = e["minute_extra"] is not None and e["minute_extra"] > 0
    lega[(p.season, p.league_id)][ok] += 1
    mese[(p.season, p.date[:7])][ok] += 1
    per_partita[p.fixture_id][ok] += 1
for k in sorted(lega):
    v = lega[k]
    print(k, "senza", v[0], "con", v[1], f"{v[1] / max(1, sum(v)):.2f}")
for k in sorted(mese):
    v = mese[k]
    print(k, "senza", v[0], "con", v[1], f"{v[1] / max(1, sum(v)):.2f}")
