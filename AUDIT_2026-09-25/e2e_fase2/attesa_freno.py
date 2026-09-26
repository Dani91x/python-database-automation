"""attesa_freno.py - SOLA LETTURA: durante il freno tirato stampa ogni tentativo d'apertura o riga nuova
di trade/ordini dei bot dopo l'istante <dalle> ed esce quando ne trova uno o allo scadere. Uso: attesa_freno.py <dalle ISO> <minuti>"""
import json, sys, time, urllib.request
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


da, fine = sys.argv[1], time.time() + float(sys.argv[2]) * 60
Q = {
    "omega_trades": f"omega_trades?select=id,event_id,status,mode,placed_at,meta->>fill_note&placed_at=gt.{da}",
    "safe_strategy_trades": f"safe_strategy_trades?select=id,event_id,status,strategy,mode,placed_at&placed_at=gt.{da}",
    "mike_trades": f"mike_trades?select=id,event_id,role,status,mode,placed_at&placed_at=gt.{da}",
    "tennis_live_orders": f"tennis_live_orders?select=id,source,status,mode,side,updated_at&updated_at=gt.{da}&status=neq.EXECUTION_COMPLETE",
    "tennis_bot_activity_entry": f"tennis_bot_activity?select=ts,bot_key,kind,payload&ts=gt.{da}&kind=in.(entry,rifiuto,freno,kill_switch,errore,error)",
    "omega_kill": f"omega_activity?select=ts,kind,payload&ts=gt.{da}&kind=in.(place,error,leg_failed,fail)",
    "safe_kill": f"safe_strategy_activity?select=ts,kind,payload&ts=gt.{da}&kind=in.(place,error,place_failed,kill_switch)",
    "mike_kill": f"mike_activity?select=ts,kind,payload&ts=gt.{da}&kind=in.(place,error,freno)",
}
while time.time() < fine:
    trovato = False
    for k, q in Q.items():
        try:
            rows = get(q + "&limit=20")
        except Exception as e:
            print("errore", k, repr(e)[:150], flush=True)
            continue
        if rows:
            trovato = True
            print(k, json.dumps(rows, ensure_ascii=False)[:1500], flush=True)
    if trovato:
        break
    time.sleep(20)
print("fine attesa", time.strftime("%H:%M:%SZ", time.gmtime()), flush=True)
