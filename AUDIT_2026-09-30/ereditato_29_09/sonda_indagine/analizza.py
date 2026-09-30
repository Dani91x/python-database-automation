import json
import sys
from datetime import datetime, timezone, timedelta

d = json.load(open(sys.argv[1], encoding="utf-8"))
dal = sys.argv[2] if len(sys.argv) > 2 else "17:20"
modo = sys.argv[3] if len(sys.argv) > 3 else "cambi"


def hh(t):
    return datetime.fromtimestamp(float(t), tz=timezone.utc).strftime("%H:%M:%S")


h0 = int(dal.split(":")[0]) * 3600 + int(dal.split(":")[1]) * 60
prev = None
for r in d["righe"]:
    if "t" not in r:
        print(r)
        continue
    dt = datetime.fromtimestamp(r["t"], tz=timezone.utc)
    if dt.hour * 3600 + dt.minute * 60 < h0:
        continue
    c = r.get("cash") or {}
    lo = r.get("loss") or {}
    fl = r.get("flusso") or {}
    firma = (r["st"], r["d_st"], r["reason"][:60], r["gol"], r["ff"], fl.get("vivo"),
             tuple(fl.get("mercati") or []), r["u35"] is None, r["o45"] is None, c.get("complete"))
    if modo == "cambi" and firma == prev:
        continue
    prev = firma
    print(hh(r["t"]), "UTC", "min", r["min"], "gol", r["gol"], "ht", r["ht"], "st", r["st"], "->", r["d_st"],
          "|", r["reason"][:110])
    print("    ff", r["ff"], "of", r["of"], "ms", r["ms"], "fonte", r["fonte"], "flusso", fl,
          "u35", r["u35"], "o45", r["o45"], "u45", r["u45"])
    if c:
        print("    cash net", c.get("net"), "gross", c.get("gross"), "base", c.get("base"),
              "complete", c.get("complete"), "per", c.get("per_gross"), "decided", c.get("decided"))
    if lo:
        print("    loss", {k: lo.get(k) for k in ("mode", "window", "ev_hold", "p4", "premium",
                                                  "threshold", "missing", "p4_market", "sources")})
    if r.get("decad"):
        print("    DECADUTA", r["decad"])
    if r.get("prop") is not None:
        print("    PROPOSTA bloccabile", r["prop"])
