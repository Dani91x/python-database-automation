import json, statistics as st, datetime, sys
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML\lavori\sonde\b_ml_metriche_out.json"
d = json.load(open(R))
print("keys", d[0].get("keys"))
errs = [x for x in d if "err" in x]; print("errori", len(errs), errs[:2])
for t in ["1x2", "over_2_5", "btts", "over_1_5"]:
    xs = [x for x in d if x["target"] == t and "err" not in x]
    ok = [x for x in xs if x["brier"] is not None]
    nc = ok[0]["n_cls"] if ok else 0
    rnd = (nc - 1) / nc if nc > 1 else .5
    bss = [1 - x["brier"] / rnd for x in ok]
    print(t, "n", len(xs), "con brier", len(ok), "n_cls", nc, "brier mediana %.4f min %.4f max %.4f" % (st.median([x["brier"] for x in ok]), min(x["brier"] for x in ok), max(x["brier"] for x in ok)),
          "BSS med %.3f p10 %.3f p90 %.3f" % (st.median(bss), sorted(bss)[len(bss)//10], sorted(bss)[9*len(bss)//10]),
          "BSS>=0.12:", sum(b >= .12 for b in bss), "ece med %.4f" % st.median([x["ece"] for x in ok if x["ece"] is not None]),
          "cal vuoto:", sum(1 for x in xs if not x["has_cal"]))
    ta = sorted(x["trained_at"] for x in xs if x["trained_at"]); print("   trained_at min", ta[0][:10], "max", ta[-1][:10], "n_feat med", st.median([x["n_feat"] for x in xs]))
ts = [x["ts"] for x in d if x.get("ts")]
print("temperature scaling n", len(ts), "T med", st.median([t["T"] for t in ts]) if ts else None, "T range", (min(t["T"] for t in ts), max(t["T"] for t in ts)) if ts else None)
