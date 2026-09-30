"""Tabella minuto per minuto (ora ITALIANA = UTC+2) dalle 17:20 UTC alla fine."""
import json
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone

d = json.load(open(sys.argv[1], encoding="utf-8"))
per_min = OrderedDict()
for r in d["righe"]:
    if "t" not in r:
        continue
    dt = datetime.fromtimestamp(r["t"], tz=timezone.utc)
    if dt.strftime("%H:%M") < "17:20":
        continue
    k = (dt + timedelta(hours=2)).strftime("%H:%M")
    per_min.setdefault(k, []).append(r)


def motivo(r):
    m = r["reason"]
    if m.startswith("uscita proposta"):
        return "PROPOSTA"
    return m[:22]


print("| Ora IT | Min | Gol | Flusso prezzi (per Mike) | Prezzi Over 4,5 (punta/banca) | Chiudendo ora (min..max) | Soglia modello | Finestra | Motivi dei giri |")
print("|---|---|---|---|---|---|---|---|---|")
for k, rs in per_min.items():
    mins = sorted({r["min"] for r in rs if r["min"] is not None})
    gol = sorted({r["gol"] for r in rs if r["gol"] is not None})
    fl = Counter("vivo" if (r.get("flusso") or {}).get("vivo") else "FERMO(" + ",".join(
        m[-3:] for m in (r.get("flusso") or {}).get("mercati") or []) + ")" for r in rs)
    nets = [r["cash"]["net"] for r in rs if r.get("cash") and r["cash"].get("complete")]
    soglie = [r["loss"]["threshold"] for r in rs if r.get("loss") and r["loss"].get("threshold") is not None]
    fin = sorted({(r.get("loss") or {}).get("window") or "-" for r in rs})
    o45 = [r["o45"] for r in rs if r.get("o45")]
    o = o45[len(o45) // 2] if o45 else None
    mot = Counter(motivo(r) for r in rs)
    print("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        k, "-".join(str(x) for x in (mins[:1] + mins[-1:])) if mins else "?",
        ",".join(str(g) for g in gol),
        " ".join(f"{a} x{b}" for a, b in fl.items()),
        f"{o[0]}/{o[1]}" if o else "assenti",
        (f"{min(nets):.2f}..{max(nets):.2f}" if nets else "incompleto"),
        (f"{min(soglie):.2f}..{max(soglie):.2f}" if soglie else "-"),
        ",".join(fin),
        "; ".join(f"{a} x{b}" for a, b in mot.most_common())))
