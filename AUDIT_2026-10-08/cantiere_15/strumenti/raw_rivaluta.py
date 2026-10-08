"""Rivalutazioni di cambio nel raw (sola lettura): aggiornamenti di trd in cui TUTTI i
livelli toccati crescono (o calano) dello STESSO fattore rispetto al cumulato di prima.

Uso: python3 raw_rivaluta.py <raw> [riga_da_mostrare]
"""
import json
import sys
import statistics
import datetime as dt

raw = sys.argv[1]
mostra = int(sys.argv[2]) if len(sys.argv) > 2 else -1
TOL = 0.011


def hm(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%H:%M:%S.%f")[:-3]


stato = {}
eventi = []
tot = 0
for i, l in enumerate(open(raw)):
    d = json.loads(l)
    for mc in d.get("mc") or []:
        mid = mc.get("id")
        if mc.get("img"):
            for k in [k for k in stato if k[0] == mid]:
                stato.pop(k)
        for rc in mc.get("rc") or []:
            k = (mid, rc.get("id"))
            st = stato.setdefault(k, {})
            trd = rc.get("trd")
            if not trd:
                continue
            tot += 1
            ratios, livelli = [], []
            for p, v in trd:
                prev = st.get(p, 0.0)
                if prev > 0:
                    ratios.append((v - prev) / prev)
                livelli.append((p, prev, v))
            for p, v in trd:
                if v == 0:
                    st.pop(p, None)
                else:
                    st[p] = v
            if len(ratios) < 3 or i < 10:
                continue
            f1 = statistics.median(ratios)
            resid = [(p, round((v - prev) - f1 * prev, 3)) for p, prev, v in livelli]
            fuori = [(p, r) for p, r in resid if abs(r) > TOL]
            if len(resid) - len(fuori) >= 3 and abs(f1) <= 0.01:
                eventi.append((i, d["pt"], mid, rc.get("id"), len(livelli), f1, fuori))
            if i == mostra:
                print("RIGA", i, hm(d["pt"]), mid, rc.get("id"), "fattore-1 = %.3e" % f1)
                for (p, prev, v), (_, r) in zip(livelli, resid):
                    print("   %-6s prima %10.2f dopo %10.2f delta %+8.2f atteso %+8.3f scarto %+7.3f"
                          % (p, prev, v, v - prev, f1 * prev, r))
print("aggiornamenti di trd:", tot, "- rivalutazioni (>=3 livelli allo stesso fattore):", len(eventi))
istanti = {}
for e in eventi:
    istanti.setdefault(e[1], []).append(e)
print("istanti distinti:", len(istanti))
for pt in sorted(istanti):
    es = istanti[pt]
    misti = [(e[2], e[3], e[6]) for e in es if e[6]]
    print(hm(pt), "selezioni", len(es), "fattore-1 %.2e" % es[0][5],
          "livelli fuori dal fattore (scambio vero insieme):", misti[:3])
