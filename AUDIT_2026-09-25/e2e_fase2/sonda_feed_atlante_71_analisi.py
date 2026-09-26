"""sonda_feed_atlante_71_analisi.py - analisi di sonda_71_monitor.jsonl (7.1.1-7.1.4), sola lettura di file.
Per ogni passo del monitor confronta la nota del servizio con il MIO riconteggio del feed nello stesso
passo: partite (scalper/tennis), eta' dello scanner, event_id armati presenti nel feed.
Uso: python sonda_feed_atlante_71_analisi.py
"""
import json
from pathlib import Path

QUI = Path(__file__).resolve().parent
righe = [json.loads(x) for x in (QUI / "sonda_71_monitor.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
out = {"passi": len(righe), "da": righe[0]["t"], "a": righe[-1]["t"]}
sc = {"passi_acceso": 0, "partite_uguali": 0, "partite_diverse": [], "armate_fuori_feed": [], "eta_max": 0,
      "armate_viste": set(), "sessioni_auto_max": 0}
tn = {"passi_acceso": 0, "partite_uguali": 0, "partite_diverse": [], "follow_fuori_feed": [], "armate_viste": set()}
af = {"passi": 0, "attori": set(), "letto": set(), "partite": set()}
eta_scanner = []
for r in righe:
    if "errore" in r:
        continue
    eta_scanner.append(r.get("scanner_eta_s"))
    f = r["feed"]
    a = (r.get("scalper_srv") or {}).get("auto") or {}
    if a.get("acceso"):
        sc["passi_acceso"] += 1
        fp = (a.get("feed") or {}).get("partite")
        if fp == f["partite_scalper"]:
            sc["partite_uguali"] += 1
        else:
            sc["partite_diverse"].append([r["t"], a.get("giro_at"), fp, f["partite_scalper"]])
        sc["eta_max"] = max(sc["eta_max"], (a.get("feed") or {}).get("eta_scanner_s") or 0)
        sc["sessioni_auto_max"] = max(sc["sessioni_auto_max"], a.get("sessioni_auto") or 0)
    for x in r.get("scalper_auto_righe") or []:
        if x.get("status") in ("requested", "running"):
            sc["armate_viste"].add(x["event_id"])
            if not x.get("in_feed"):
                sc["armate_fuori_feed"].append([r["t"], x["event_id"], x["status"]])
    for bot, v in (r.get("tennis_srv") or {}).items():
        au = v.get("auto") or {}
        if v.get("status") == "running" and au:
            tn["passi_acceso"] += 1
            if au.get("feed_partite") == f["partite_tennis"]:
                tn["partite_uguali"] += 1
            else:
                tn["partite_diverse"].append([r["t"], bot, au.get("letto_at"), au.get("feed_partite"), f["partite_tennis"]])
    for x in r.get("tennis_auto_follow") or []:
        if x.get("status") == "STREAMING":
            tn["armate_viste"].add(x["event_id"])
            if not x.get("in_feed"):
                tn["follow_fuori_feed"].append([r["t"], x["event_id"]])
    h = r.get("auto_follow_47331") or {}
    if isinstance(h, dict) and "feed" in h:
        af["passi"] += 1
        af["attori"].add(json.dumps(h["feed"].get("attori")))
        af["letto"].add(str(h["feed"].get("letto")))
        af["partite"].add(h["feed"].get("partite"))
eta = [e for e in eta_scanner if e is not None]
out["scanner_eta_s"] = {"max": max(eta) if eta else None, "oltre_30": sum(1 for e in eta if e > 30)}
for d in (sc, tn, af):
    for k, v in list(d.items()):
        if isinstance(v, set):
            d[k] = sorted(v)
sc["partite_diverse"] = sc["partite_diverse"][:10]
tn["n_diverse"] = len(tn["partite_diverse"])
tn["partite_diverse"] = tn["partite_diverse"][:10]
out["scalper"], out["tennis"], out["auto_follow"] = sc, tn, af
print(json.dumps(out, ensure_ascii=False, indent=1))
