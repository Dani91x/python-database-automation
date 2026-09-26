"""conta_freno.py - SOLA LETTURA (GET): nella finestra [da, a] (ISO UTC) conta, PER BOT, i tentativi di
apertura RIFIUTATI dal freno (attivita' il cui payload nomina kill/freno), le APERTURE passate (trade/ordini
nuovi non in errore), le CHIUSURE passate, e per lo scalper stop/force-flat/armamenti. Stampa JSON.
Uso: conta_freno.py <da> <a>"""
import json, sys, urllib.request
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
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


da, a = sys.argv[1], sys.argv[2]
F = f"ts=gte.{da}&ts=lte.{a}"
out = {"finestra": [da, a], "per_bot": {}}
for bot, t in (("omega", "omega_activity"), ("safe", "safe_strategy_activity"), ("mike", "mike_activity"),
               ("tennis", "tennis_bot_activity"), ("scalper", "scalper_activity")):
    rows = get(f"{t}?select=*&{F}&order=id&limit=10000")
    freno = [r for r in rows if any(x in json.dumps(r.get("payload"), ensure_ascii=False).lower()
                                    for x in ("kill", "freno"))]
    kinds = {}
    for r in rows:
        kk = (r.get("bot_key") + ":" if r.get("bot_key") else "") + r["kind"]
        kinds[kk] = kinds.get(kk, 0) + 1
    out["per_bot"][bot] = {"attivita_per_kind": kinds, "righe_col_freno": len(freno),
                           "esempi_freno": [{"ts": r["ts"], "kind": r["kind"], "bot": r.get("bot_key"),
                                             "p": json.dumps(r.get("payload"), ensure_ascii=False)[:260]} for r in freno[:12]]}
Q = {
    "omega_trades": f"omega_trades?select=id,event_id,status,mode,placed_at&placed_at=gte.{da}&placed_at=lte.{a}",
    "safe_strategy_trades": f"safe_strategy_trades?select=id,event_id,strategy,status,mode,placed_at,closes_trade_id&placed_at=gte.{da}&placed_at=lte.{a}",
    "mike_trades": f"mike_trades?select=id,event_id,role,status,mode,placed_at,closes_trade_id&placed_at=gte.{da}&placed_at=lte.{a}",
    "tennis_live_orders": f"tennis_live_orders?select=id,source,side,status,mode,placed_at,updated_at&placed_at=gte.{da}&placed_at=lte.{a}",
    "betfair_live_orders": f"betfair_live_orders?select=id,client_order_ref,source,status,mode,placed_at&placed_at=gte.{da}&placed_at=lte.{a}",
    "betfair_live_order_requests": f"betfair_live_order_requests?select=id,action,status,mode,error,requested_at&requested_at=gte.{da}&requested_at=lte.{a}",
    "scalper_control": f"scalper_control?select=event_id,status,origine,error,updated_at,stopped_at&updated_at=gte.{da}",
}
out["righe"] = {}
for k, q in Q.items():
    try:
        out["righe"][k] = get(q + "&limit=500")
    except Exception as e:
        out["righe"][k] = {"errore": repr(e)[:160]}
print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
