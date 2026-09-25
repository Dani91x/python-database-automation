"""Misure delle action dalle run reali (solo `gh run list`, sola lettura).

Durata (startedAt -> updatedAt) delle run VERDI al primo tentativo, non manuali,
dal 25/08/2026; ritardo tra l'orario del cron e la creazione della run.
Uso: python AUDIT_2026-09-25/misure_action.py
"""
import json
import statistics as st
import subprocess
from datetime import datetime

CRON = {"Daily Yesterday Backfill": (1, 12), "Today Predictions Backfill": (2, 18),
        "Predictions Results Backfill": (3, 23),
        "ML Post-Calibration (assembla per-lega + globale)": (5, 14),
        "Retrain ML Models (cloud, all leagues)": (8, 19),
        "Weekly Poisson Calibration": (3, 27), "Monthly Leagues Mapping": (0, 12)}
out = subprocess.run(["gh", "run", "list", "--limit", "500", "--json",
                      "databaseId,workflowName,conclusion,event,createdAt,startedAt,updatedAt,attempt"],
                     capture_output=True, text=True, encoding="utf-8").stdout
runs = json.loads(out)


def P(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


by = {}
for r in runs:
    if r["createdAt"] < "2026-08-25":
        continue
    by.setdefault(r["workflowName"], []).append(r)
for w, rs in sorted(by.items()):
    ok = sorted((P(r["updatedAt"]) - P(r["startedAt"])).total_seconds() / 60 for r in rs
                if r["conclusion"] == "success" and r["attempt"] == 1 and r["event"] != "workflow_dispatch")
    ev = {}
    for r in rs:
        k = f"{r['event']}/{r['conclusion']}"
        ev[k] = ev.get(k, 0) + 1
    line = f"{w[:48]:48} verdi={len(ok):3}"
    if ok:
        line += (f" durata min: mediana={st.median(ok):6.1f} p90={ok[max(0, int(len(ok) * 0.9) - 1)]:6.1f}"
                 f" max={ok[-1]:6.1f}")
    print(line)
    print("     esiti:", ev)
    if w in CRON:
        h, m = CRON[w]
        rit = []
        for r in rs:
            if r["event"] != "schedule":
                continue
            c = P(r["createdAt"])
            x = (c - c.replace(hour=h, minute=m, second=0, microsecond=0)).total_seconds() / 3600
            if x >= 0:
                rit.append(x)
        if rit:
            print(f"     ritardo creazione vs cron (ore): mediana={st.median(rit):.2f} "
                  f"min={min(rit):.2f} max={max(rit):.2f} n={len(rit)}")
