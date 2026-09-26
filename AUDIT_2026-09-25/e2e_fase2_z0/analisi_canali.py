"""Analisi offline (nessuna rete) delle letture dei canali: chiavi dell'hello del 47331 e
chiavi di tempo dei messaggi di stato dei bot."""
import json
import os
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(QUI, sys.argv[1]), encoding="utf-8"))
for c in d["canali"]:
    h = c.get("hello") or {}
    print(c["porta"], "hello chiavi:", sorted(h.keys()), "| modo_ordini:",
          json.dumps(h.get("modo_ordini"))[:600] if "modo_ordini" in h else "ASSENTE")
    for t, pt in c["per_topic"].items():
        if t.endswith("_stato") or t in ("scalper_sessioni",):
            s = pt["ultimo"]
            try:
                m = json.loads(s)
            except Exception:
                print("   ", t, "troncato:", s[:300])
                continue
            ctrl = m.get("control") or {}
            stats = m.get("stats") or ctrl.get("stats") or {}
            print("   ", t, "chiavi:", sorted(m.keys())[:25])
            print("      updated_at", m.get("updated_at"), "| control.updated_at", ctrl.get("updated_at"),
                  "| control.status/mode", ctrl.get("status"), ctrl.get("mode"),
                  "| stats.last_cycle", stats.get("last_cycle"), "| heartbeat_at", m.get("heartbeat_at") or ctrl.get("heartbeat_at"))
