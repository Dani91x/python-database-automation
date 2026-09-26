"""ladder_fasce.py - SOLA LETTURA dei file dell'ascoltatore: per il runner calcio (47331) e tennis (47332)
conta i messaggi ladder/now per fascia di 10 min (dai conteggi al minuto) e, sui campioni interi salvati
(uno ogni 60 s), quanti payload DISTINTI (prezzi diversi) e quali partite. Stampa anche l'ultimo istante
registrato. Uso: ladder_fasce.py"""
import glob, hashlib, json
from collections import defaultdict
C = r"C:\\Users\\Admin\\Desktop\\PYTHON DATABASE\\python-database-automation\\AUDIT_2026-09-25\\e2e_fase2\\canali"
fasce = defaultdict(lambda: defaultdict(int))
ultimo = None
for f in sorted(glob.glob(C + r"\\conteggi_*.jsonl")):
    for line in open(f, encoding="utf8"):
        r = json.loads(line)
        ultimo = r["ts_utc"]
        fa = r["ts_utc"][11:15] + "0"
        for k, v in r["conteggi"].items():
            if k.split(":")[0] in ("runner_calcio", "runner_tennis") and k.split(":")[1] in ("ladder", "now", "battito", "position", "order"):
                fasce[fa][k] += v
print("ultimo minuto registrato:", ultimo)
print("fascia(UTC) | messaggi per canale:topic")
for fa in sorted(fasce):
    print(fa, dict(sorted(fasce[fa].items())))
camp = defaultdict(lambda: {"n": 0, "hash": set(), "eventi": set()})
ult_msg = None
for f in sorted(glob.glob(C + r"\\messaggi_*.jsonl")):
    for line in open(f, encoding="utf8"):
        r = json.loads(line)
        ult_msg = r["ts_utc"]
        if r["canale"] not in ("runner_calcio", "runner_tennis") or r["t"] not in ("ladder", "now"):
            continue
        fa = r["ts_utc"][11:15] + "0"
        k = (fa, r["canale"], r["t"])
        d = r["d"] if isinstance(r["d"], dict) else {}
        corpo = {x: d.get(x) for x in d if x not in ("ts", "updated_ms", "ts_ms", "_seq", "_pubblicato_ms", "age_ms")}
        camp[k]["n"] += 1
        camp[k]["hash"].add(hashlib.md5(json.dumps(corpo, sort_keys=True, default=str).encode()).hexdigest())
        camp[k]["eventi"].add(str(d.get("event_id")))
print("ultimo messaggio salvato:", ult_msg)
print("campioni interi (1/min per topic): fascia canale topic -> campioni, payload distinti, eventi")
for k in sorted(camp):
    v = camp[k]
    print(k, v["n"], len(v["hash"]), sorted(v["eventi"]))
