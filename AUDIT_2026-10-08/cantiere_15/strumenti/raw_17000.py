"""Analisi in sola lettura del raw 35797769 attorno al messaggio delle 17:00:06.704 UTC."""
import json
import sys
import datetime as dt

f = sys.argv[1]
MID = "1.259819674"
T = int(dt.datetime(2026, 7, 10, 17, 0, 6, 704000, tzinfo=dt.timezone.utc).timestamp() * 1000)
ops, cts, chiavi = {}, {}, set()
righe = []
for i, l in enumerate(open(f)):
    d = json.loads(l)
    ops[d.get("op")] = ops.get(d.get("op"), 0) + 1
    cts[d.get("ct")] = cts.get(d.get("ct"), 0) + 1
    chiavi |= set(d.keys())
    righe.append((i, d))


def hm(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%H:%M:%S.%f")[:-3]


print("op:", ops)
print("ct:", cts)
print("chiavi di testa:", sorted(chiavi))
print("prima riga pt", hm(righe[0][1]["pt"]), "ultima", hm(righe[-1][1]["pt"]))
print("target", T, hm(T))
# distanza fra messaggi consecutivi (tutti i mercati) e per il MATCH_ODDS
pts = [d.get("pt") for _, d in righe]
gaps = sorted(((pts[k] - pts[k - 1]), k) for k in range(1, len(pts)))
print("gap fra messaggi (ms): mediana", gaps[len(gaps) // 2][0], "p90", gaps[int(len(gaps) * .9)][0],
      "p99", gaps[int(len(gaps) * .99)][0], "max", gaps[-1])
mo = [(i, d) for i, d in righe if any(mc.get("id") == MID for mc in d.get("mc") or [])]
pmo = [d["pt"] for _, d in mo]
g2 = sorted(pmo[k] - pmo[k - 1] for k in range(1, len(pmo)))
print("MATCH_ODDS: messaggi", len(mo), "gap mediana", g2[len(g2) // 2], "p90", g2[int(len(g2) * .9)],
      "p99", g2[int(len(g2) * .99)])
# pre-match prima del KO (19:00)
ko = int(dt.datetime(2026, 7, 10, 19, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
pre = [p for p in pmo if p < ko]
g3 = sorted(pre[k] - pre[k - 1] for k in range(1, len(pre)))
print("MATCH_ODDS pre-KO: gap mediana", g3[len(g3) // 2], "p90", g3[int(len(g3) * .9)])
cnt = sum(1 for g in g3 if g >= 5000)
print("MATCH_ODDS pre-KO gap >= 5 s:", cnt, "su", len(g3))
# intorno al target
print("--- messaggi del MATCH_ODDS fra T-30s e T+10s")
for i, d in mo:
    if T - 30000 <= d["pt"] <= T + 10000:
        for mc in d["mc"]:
            if mc.get("id") != MID:
                continue
            for rc in mc.get("rc") or []:
                if rc.get("id") in (22, 58805):
                    print(i, hm(d["pt"]), "clk", d.get("clk"), "con", mc.get("con"), "img", mc.get("img"),
                          "sel", rc["id"], "trd", rc.get("trd"), "ltp", rc.get("ltp"), "tv", rc.get("tv"))
print("--- tutti i messaggi (ogni mercato) fra T-6s e T+1s: pt, clk, mercati")
for i, d in righe:
    if T - 6000 <= d["pt"] <= T + 1000:
        print(i, hm(d["pt"]), d.get("clk"), [mc.get("id") for mc in d.get("mc") or []],
              [mc.get("con") for mc in d.get("mc") or []])
