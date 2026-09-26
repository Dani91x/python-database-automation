"""verifica_pnl.py - E2E FASE 2 (26/09): P&L netto delle posizioni paper REGOLATE da oggi 09:00Z,
ricalcolato indipendentemente dalla riga (lato, prezzo, stake, esito, commissione 5% sul vinto netto
del mercato) e confrontato con `pnl` scritto dal bot. SOLA LETTURA (GET). Posizioni a una gamba:
lay vinto = +s*(1-c); lay perso = -s*(L-1); back vinto = +s*(P-1)*(1-c); back perso = -s.
Le posizioni con chiusure (closes_trade_id) si sommano per ciclo e si confrontano come totale.
Uso: verifica_pnl.py"""
import json, urllib.request
from pathlib import Path

W = Path(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
env = {}
for line in open(W / ".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_ROLE_KEY"]


def get(path):
    req = urllib.request.Request(URL + "/rest/v1/" + path, method="GET",
                                 headers={"apikey": KEY, "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


C = 0.05
DA = "2026-09-26T09:00:00Z"
out = {"righe": [], "totali": {}}


def atteso(side, price, size, status):
    L, s = float(price), float(size)
    if status == "won":
        return round(s * (1 - C), 2) if side == "lay" else round(s * (L - 1) * (1 - C), 2)
    if status == "lost":
        return round(-s * (L - 1), 2) if side == "lay" else round(-s, 2)
    if status in ("void", "voided", "cancelled"):
        return 0.0
    return None


for t, sel in (("omega_trades", "id,event_id,side,price,size,status,pnl,mode,settled_at,placed_at"),
               ("safe_strategy_trades", "id,event_id,strategy,side,price,size,status,pnl,mode,settled_at,placed_at,closes_trade_id"),
               ("mike_trades", "id,event_id,role,side,price,size,status,pnl,mode,settled_at,placed_at,closes_trade_id")):
    rows = get(f"{t}?select={sel}&settled_at=gte.{DA}&placed_at=gte.{DA}&order=id")
    tot = 0.0
    for r in rows:
        a = atteso(r["side"], r["price"], r["size"], r["status"])
        chiusura = r.get("closes_trade_id") is not None
        ok = None if (a is None or chiusura) else abs(a - float(r["pnl"] or 0)) < 0.011
        tot += float(r["pnl"] or 0)
        out["righe"].append({"tabella": t, **{k: r.get(k) for k in ("id", "event_id", "side", "price", "size", "status", "pnl", "mode")},
                             "pnl_atteso_gamba_singola": a, "esito": "OK" if ok else ("n/a (ciclo con chiusure)" if chiusura else ("KO" if ok is False else "n/a"))})
    out["totali"][t] = round(tot, 2)
tl = get(f"tennis_live_orders?select=id,source,side,price,size,size_matched,average_price_matched,status,pnl,commission,mode,settled_at&settled_at=gte.{DA}&order=id")
out["tennis"] = tl
out["totali"]["tennis_per_bot"] = {}
for r in tl:
    out["totali"]["tennis_per_bot"][r["source"]] = round(out["totali"]["tennis_per_bot"].get(r["source"], 0) + float(r["pnl"] or 0), 2)
out["n_KO"] = sum(1 for x in out["righe"] if x["esito"] == "KO")
print(json.dumps(out, indent=1, ensure_ascii=False))
