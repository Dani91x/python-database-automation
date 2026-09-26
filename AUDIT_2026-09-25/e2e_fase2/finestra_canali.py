"""finestra_canali.py - SOLA LETTURA dei JSONL dell'ascoltatore: tutti i messaggi salvati fra due istanti
UTC (HH:MM:SS) per i canali indicati, piu' i conteggi al minuto. Uso: finestra_canali.py <da> <a> <canali,separati|tutti>"""
import glob, json, sys
C = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\canali"
da, a = "2026-09-26T" + sys.argv[1] + "Z", "2026-09-26T" + sys.argv[2] + "Z"
can = None if sys.argv[3] == "tutti" else set(sys.argv[3].split(","))
for f in sorted(glob.glob(C + r"\messaggi_*.jsonl")):
    for line in open(f, encoding="utf8"):
        r = json.loads(line)
        if not (da <= r["ts_utc"] <= a):
            continue
        if can and r["canale"] not in can:
            continue
        d = r["d"]
        if isinstance(d, dict):
            c = d.get("control") if isinstance(d.get("control"), dict) else None
            extra = {k: d.get(k) for k in ("ts", "mode", "status", "order_mode", "kind", "event_id", "bot_key") if k in d}
            if c:
                extra["control"] = [c.get("status"), c.get("mode")]
            testo = json.dumps(extra, ensure_ascii=False)[:220]
        else:
            testo = json.dumps(d, ensure_ascii=False)[:220]
        print(r["ts_utc"], r["canale"], r["t"], r["perche"], testo)
print("--- conteggi al minuto")
for f in sorted(glob.glob(C + r"\conteggi_*.jsonl")):
    for line in open(f, encoding="utf8"):
        r = json.loads(line)
        if da <= r["ts_utc"] <= a.replace(sys.argv[2], sys.argv[2]):
            cc = {k: v for k, v in r["conteggi"].items() if (not can) or k.split(":")[0] in can}
            print(r["ts_utc"], json.dumps(cc))
