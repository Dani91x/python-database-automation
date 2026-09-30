import json
import sys
from datetime import datetime, timezone

d = json.load(open(sys.argv[1], encoding="utf-8"))
for n in d["note"]:
    if "P&L" in n or "fill:" in n or "attivita'" in n or "motivi dichiarati" in n:
        print("NOTA", n)
print("VIOLAZIONI", len(d["violazioni"]), d["violazioni"][:5])
chiusura = [r for r in d["righe"] if r.get("st") == "LIVE_CLOSING"]
print("giri in LIVE_CLOSING", len(chiusura))
for r in chiusura[:3] + chiusura[-3:]:
    print("  ", datetime.fromtimestamp(r["t"], tz=timezone.utc).strftime("%H:%M:%S"), r["d_st"],
          r["reason"][:90], "ff", r["ff"], "o45", r["o45"])
