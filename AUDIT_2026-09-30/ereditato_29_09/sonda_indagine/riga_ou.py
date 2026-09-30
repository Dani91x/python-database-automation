import json
import sys
from datetime import datetime, timezone

d = json.load(open(sys.argv[1], encoding="utf-8"))
prev = None
for r in d["righe"]:
    if "t" not in r:
        continue
    h = datetime.fromtimestamp(r["t"], tz=timezone.utc).strftime("%H:%M:%S")
    if h < sys.argv[2]:
        continue
    ou = r.get("riga_ou") or {}
    k = (json.dumps(ou.get("3.5"))[:60], json.dumps(r.get("riga_flusso"))[:120])
    if k != prev:
        print(h, "OU3.5 nella riga:", ou.get("3.5"), "| flusso riga:", r.get("riga_flusso"))
        prev = k
