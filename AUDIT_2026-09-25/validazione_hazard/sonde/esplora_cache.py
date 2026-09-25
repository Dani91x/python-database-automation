"""Esplorazione della CACHE (nessuna lettura del DB): copertura di status.extra,
coerenza recupero annunciato vs eventi, convenzioni dei minuti, lambda."""
import collections
import statistics as st

from Betfair.stream.scalper.validazione_hazard.raccogli import carica

C = "AUDIT_2026-09-25/validazione_hazard/cache/"
M = carica(C + "matches.json.gz")
E = carica(C + "eventi.json.gz")
P = carica(C + "predizioni.json.gz")
print("matches", len(M), "eventi", len(E), "pred", len(P))
ft = [m for m in M if m["status_short"] == "FT"]
print("FT", len(ft), collections.Counter(m["status_short"] for m in M).most_common(8))
per_s = collections.defaultdict(lambda: [0, 0])
for m in ft:
    per_s[m["season_year"]][0] += 1
    per_s[m["season_year"]][1] += m.get("extra") is not None
print("extra per stagione", {k: f"{v[1]}/{v[0]}" for k, v in sorted(per_s.items())})
ev = collections.defaultdict(list)
for e in E:
    ev[e["fixture_id"]].append(e)
# minuti anomali
c = collections.Counter()
for e in E:
    mi, ex = e["minute"], e["minute_extra"]
    if mi is None:
        c["min_none"] += 1
    elif mi > 90:
        c["min>90"] += 1
    elif 45 < mi < 46:
        c["?"] += 1
    if ex is not None and mi not in (45, 90):
        c[f"extra_con_min_{mi}"] += 1
    if ex is not None and ex <= 0:
        c["extra<=0"] += 1
print("anomalie minuti", c.most_common(20))
# D2 annunciato vs limite inferiore dagli eventi (stagioni >= 2024: eventi in recupero)
diff = collections.Counter()
d2 = collections.defaultdict(list)
d1lb = []
d1per = []
for m in ft:
    s = m["season_year"]
    if m.get("extra") is not None:
        d2[s].append(int(m["extra"]))
    if s < 2024:
        continue
    evs = ev.get(m["fixture_id"], [])
    lb2 = max([e["minute_extra"] for e in evs if e["minute"] == 90 and e["minute_extra"]] or [0])
    lb1 = max([e["minute_extra"] for e in evs if e["minute"] == 45 and e["minute_extra"]] or [0])
    d1lb.append(lb1)
    if m.get("extra") is not None:
        diff[lb2 - int(m["extra"])] += 1
    if m.get("p1") and m.get("p2"):
        d1per.append((int(m["p2"]) - int(m["p1"])) / 60.0 - 60.0)
print("LB2 - extra (stagioni>=2024)", sorted(diff.items()))
print("D2 annunciato per stagione", {s: (round(st.mean(v), 2), len(v)) for s, v in sorted(d2.items())})
print("LB1 (eventi 45+) media", round(st.mean(d1lb), 2), collections.Counter(d1lb).most_common(12))
print("D1 da periods (p2-p1)/60-60: media", round(st.mean(d1per), 2), "mediana", st.median(d1per),
      "quantili", [round(x, 1) for x in st.quantiles(d1per, n=10)])
# gol per stagione con extra
g = [e for e in E if e["event_type"] == "Goal" and e["detail"] != "Missed Penalty"]
gs = collections.Counter((e["minute"] == 90 and bool(e["minute_extra"]), e["minute"] == 45 and bool(e["minute_extra"])) for e in g)
print("gol: (recupero2T, recupero1T)", gs)
print("dettagli", collections.Counter((e["event_type"], e["detail"]) for e in E if e["event_type"] != "subst").most_common(15))
# predizioni
ok = [p for p in P if p.get("lh") is not None and p.get("la") is not None]
fs = {m["fixture_id"]: m for m in M}
print("pred con lambda", len(ok), collections.Counter(fs[p["fixture_id"]]["season_year"] for p in ok))
print("pred per lega 2025", collections.Counter(fs[p["fixture_id"]]["league_id"] for p in ok if fs[p["fixture_id"]]["season_year"] == 2025))
print("gen", collections.Counter(str(p.get("gen"))[:7] for p in ok).most_common(12))
