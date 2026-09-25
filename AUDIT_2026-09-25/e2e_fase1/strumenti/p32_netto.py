"""P32: il diff fotografia_iniziale -> P32_finale, al netto della migrazione uscite_manuali_default_2026-09-25.sql
applicata da terzi alle 18:45:22 UTC durante il test (sola lettura di file locali).

Applica alla fotografia iniziale ESATTAMENTE cio' che la migrazione scrive (migrations/uscite_manuali_default_2026-09-25.sql
righe 52-127: uscite_automatiche=false su mike/safe(per strategia)/scalper_service/tennis_bot_service + updated_at=now())
e confronta con P32_finale: deve restare ZERO differenze. Elenca anche l'ora di ogni ripristino dei percorsi.
"""
import copy, glob, json, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ld = lambda n: json.load(open(os.path.join(OUT, n + ".json"), encoding="utf-8"))
a, b = ld("fotografia_iniziale"), ld("P32_finale")
TS = "2026-09-25T18:45:22.33826+00:00"
x = copy.deepcopy(a)
m = x["mike_control"][0]; m["params"]["uscite_automatiche"] = False; m["updated_at"] = TS
s = x["safe_strategy_control"][0]
s["params"]["uscite_automatiche"] = {k: False for k in ("base", "esatto", "punta", "tennis", "model")}; s["updated_at"] = TS
c = x["scalper_service_control"][0]; c["params"] = dict(c.get("params") or {}); c["params"]["uscite_automatiche"] = False
c["updated_at"] = TS
for r in x["tennis_bot_service_control"]:
    r["uscite_automatiche"] = False; r["updated_at"] = TS


def diff(p, q, path=""):
    out = []
    if isinstance(p, dict) and isinstance(q, dict):
        for k in sorted(set(p) | set(q)):
            if k in ("ts", "sql_equivalente", "grezzo"):
                continue
            out += diff(p.get(k, "<assente>"), q.get(k, "<assente>"), path + "/" + k)
    elif isinstance(p, list) and isinstance(q, list) and len(p) == len(q):
        for i, (u, v) in enumerate(zip(p, q)):
            out += diff(u, v, "%s[%d]" % (path, i))
    elif p != q or type(p) != type(q):
        out.append((path, p, q))
    return out


d = diff(x, b)
print(json.dumps({"differenze_al_netto_della_migrazione": [{"campo": p, "atteso": u, "trovato": v} for p, u, v in d],
                  "n": len(d)}, ensure_ascii=False, default=str))
orari = sorted((ld(os.path.basename(f)[:-5])["ts"], os.path.basename(f)[:-5])
               for f in glob.glob(os.path.join(OUT, "*_ripristino.json")))
print(json.dumps({"ripristini_in_ordine": orari}, ensure_ascii=False))
