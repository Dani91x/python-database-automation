import json, random
from Betfair.stream.trading.dutching import dutch_variable
from flumine.utils import get_nearest_price
random.seed(20261009)
cases = []
for i in range(20000):
    n = random.choice([2, 2, 3, 3, 4, 5, 8])
    sels = []
    for j in range(n):
        r = random.random()
        if r < 0.4:
            p = round(random.uniform(1.02, 12), 2)       # quote a 2 decimali, spesso fuori tick
        elif r < 0.8:
            p = get_nearest_price(random.uniform(1.02, 60))  # sul tick
        else:
            p = round(random.uniform(1.02, 1000), random.choice([0, 1, 2, 3]))
        if p <= 1.0: p = 1.5
        w = random.choice([1, 1, 2, 3, 0.5, 1.5, 0.1, 5, round(random.uniform(0.1, 9), random.choice([1, 2]))])
        sels.append([j + 1, p, w])
    T = random.choice([10, 50, 100, 37.5, round(random.uniform(2, 500), 2), round(random.uniform(2, 500), 1)])
    plan = dutch_variable([tuple(x) for x in sels], T)
    exp = {"sels": sels, "T": T, "ok": plan.actionable,
           "legs": [[l.price, l.size, l.profit_if_wins] for l in plan.legs],
           "total": plan.total_stake, "book": plan.book_pct}
    cases.append(exp)
json.dump(cases, open("ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML/lavori/fase2/suite/_cases.json", "w"))
print(len(cases), sum(1 for c in cases if not c["ok"]), "non azionabili")
