"""verifica_mike_b.py - SOLA LETTURA, semantica B per le COPERTURE Over 4.5 di Mike: per ogni attivita'
`cover` di oggi ricalcola lo stake con la funzione di PRODUZIONE `mike.engine.cover_residual`
(liability, prezzo, commissione, fattore dai params EFFETTIVI `mike.config.merge_params`, gia' coperto) e
lo confronta con `x_pieno`/`x` scritti. Uso: verifica_mike_b.py"""
import json, os, sys

sys.path.insert(0, os.getcwd())
from Betfair.mike import db as MDB, config as MC, engine as E  # noqa: E402

ctl = MDB.read_control() or {}
p = MC.merge_params(ctl.get("params") or {})
chiavi_f = [k for k in p if "cover" in k and ("factor" in k or "fattore" in k)]
fattore = None
for k in ("cover_profit_factor", "cover_factor", "over_cover_factor"):
    if k in p:
        fattore = float(p[k])
        break
comm = float(p.get("commission", p.get("commission_pct", 5) / 100 if p.get("commission_pct") else 0.05))
rows = MDB._sb().table("mike_activity").select("id,ts,event_id,kind,payload").eq("kind", "cover").gte(
    "ts", "2026-09-26T09:00:00Z").order("id").execute().data or []
out = {"params_cover": {k: p[k] for k in sorted(p) if "cover" in k}, "fattore_usato": fattore, "commissione": comm, "righe": []}
for r in rows:
    q = r["payload"]
    try:
        x_ric = E.cover_residual(float(q["liability"]), float(q["price"]), comm, fattore, float(q.get("already") or 0.0))
    except Exception as e:
        x_ric = repr(e)[:100]
    xp = q.get("x_pieno")
    ok = isinstance(x_ric, float) and xp is not None and abs(round(x_ric, 2) - float(xp)) <= 0.011
    out["righe"].append({"id": r["id"], "ts": r["ts"], "event_id": r["event_id"], "scritto": q,
                         "x_ricalcolato": x_ric, "esito": "OK" if ok else "DA VERIFICARE"})
print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
