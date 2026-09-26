"""estrae dai JSONL dell'ascoltatore i messaggi di un canale:topic (sola lettura dei file).
Uso: topic_canale.py <canale> <topic> [chiavi,separate] [max]"""
import glob, json, sys
C = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\canali"
can, top = sys.argv[1], sys.argv[2]
keys = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else None
mx = int(sys.argv[4]) if len(sys.argv) > 4 else 50
n = 0
for f in sorted(glob.glob(C + r"\messaggi_*.jsonl")):
    for line in open(f, encoding="utf8"):
        r = json.loads(line)
        if r["canale"] != can or r["t"] != top:
            continue
        d = r["d"]
        if keys and isinstance(d, dict):
            d = {k: d.get(k) for k in keys}
        print(r["ts_utc"], json.dumps(d, ensure_ascii=False)[:600])
        n += 1
        if n >= mx:
            sys.exit(0)
