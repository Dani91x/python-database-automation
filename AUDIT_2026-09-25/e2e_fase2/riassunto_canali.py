"""riassunto dei file JSONL dell'ascoltatore (sola lettura). Uso: riassunto_canali.py [dalle_utc]"""
import glob, json, sys
from collections import Counter, defaultdict
C = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\canali"
dalle = sys.argv[1] if len(sys.argv) > 1 else ""
cnt = Counter()
stato = {}
primo_run = {}
for f in sorted(glob.glob(C + r"\messaggi_*.jsonl")):
    for line in open(f, encoding="utf8"):
        r = json.loads(line)
        if r["ts_utc"] < dalle:
            continue
        t = r["t"]; d = r["d"]
        cnt[(r["canale"], t)] += 1
        if t.endswith("_stato") and isinstance(d, dict):
            c = d.get("control") or d
            k = (r["canale"], t, c.get("bot_key"))
            stato[k] = (r["ts_utc"], c.get("status"), c.get("mode"), "control" in d)
            if c.get("status") == "running" and k not in primo_run:
                primo_run[k] = r["ts_utc"]
print("CONTEGGI messaggi salvati per canale:topic")
for k, n in sorted(cnt.items()):
    print(" ", k, n)
print("ULTIMO *_stato (ts, status, mode, porta 'control'):")
for k, v in sorted(stato.items(), key=lambda x: str(x[0])):
    print(" ", k, v, "primo running:", primo_run.get(k))
