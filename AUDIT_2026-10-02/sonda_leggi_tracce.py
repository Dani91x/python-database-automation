"""Sonda di sola lettura: stampa le tracce coda/canale scritte da ``--tracce``."""
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
for tr in ("coda", "canale"):
    t = d[tr]
    print("==", tr, list(t.keys()))
    for k, v in t.items():
        if isinstance(v, list):
            print(" ", k, len(v))
            for x in v[:8]:
                print("    ", json.dumps(x, default=str)[:700])
        else:
            print(" ", k, str(v)[:300])
