import json
import sys
from datetime import datetime, timezone

d = json.load(open(sys.argv[1], encoding="utf-8"))
prev = None
inizio = None
for r in d["righe"]:
    if "t" not in r:
        continue
    fl = r.get("flusso") or {}
    k = (fl.get("vivo"), tuple(fl.get("mercati") or []))
    if k != prev:
        h = datetime.fromtimestamp(r["t"], tz=timezone.utc).strftime("%H:%M:%S")
        print(h, "UTC", "min", r["min"], "gol", r["gol"], "st", r["st"], "flusso", k, "ff", r["ff"],
              "u35", r["u35"], "o45", r["o45"])
        prev = k
# conteggio giri per stato del flusso dopo il 4o gol
n = sum(1 for r in d["righe"] if "t" in r and r["ff"] is False)
print("giri con feed_fresh False:", n, "su", len(d["righe"]))
