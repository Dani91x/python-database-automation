"""raccolta_db.py - E2E FASE 2 (26/09): raccolta periodica in SOLA LETTURA (solo GET PostgREST).

Ogni <periodo> secondi salva in e2e_fase2/db/: righe di controllo intere, righe NUOVE delle attivita'
(cursore su id), trade/ordini/code del giorno toccati dall'ultimo giro, righe per partita attive.
Metodo HTTP fisso a GET, select e filtri espliciti: nessuna scrittura possibile da qui.
Uso: python raccolta_db.py <minuti> [periodo_s]
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

W = Path(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
OUT = W / "AUDIT_2026-09-25" / "e2e_fase2" / "db"
OUT.mkdir(parents=True, exist_ok=True)
env = {}
for line in open(W / ".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_ROLE_KEY"]
H = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Accept": "application/json"}
GIORNO = "2026-09-26T09:00:00Z"   # inizio della fase 2 (accensioni dalle 09:10Z)


def get(path):
    req = urllib.request.Request(URL + "/rest/v1/" + path, headers=H, method="GET")
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


CONTROL = ["omega_control", "mike_control", "safe_strategy_control", "tennis_bot_service_control",
           "scalper_service_control", "betfair_live_settings"]
ATTIVITA = ["omega_activity", "mike_activity", "safe_strategy_activity", "tennis_bot_activity", "scalper_activity"]
# tabella -> colonna del tempo per "toccati dall'ultimo giro"
RIGHE = {
    "omega_trades": "placed_at", "mike_trades": "placed_at", "safe_strategy_trades": "placed_at",
    "betfair_live_orders": "updated_at", "tennis_live_orders": "updated_at",
    "betfair_live_order_requests": "requested_at", "tennis_live_order_queue": "created_at",
    "safe_strategy_requests": "updated_at", "omega_manual_requests": "updated_at", "mike_requests": "updated_at",
    "tennis_bot_control": "updated_at", "scalper_control": "updated_at", "mike_events": "updated_at",
    "live_follow": None, "tennis_live_follow": None,
}
cursori = {t: 0 for t in ATTIVITA}


def giro(n):
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "giro": n}
    for t in CONTROL:
        rec[t] = get(f"{t}?select=*")
    for t in ATTIVITA:
        if cursori[t] == 0:
            q = f"{t}?select=*&ts=gte.{GIORNO}&order=id.asc&limit=5000"
        else:
            q = f"{t}?select=*&id=gt.{cursori[t]}&order=id.asc&limit=5000"
        rows = get(q)
        if rows:
            cursori[t] = max(int(r["id"]) for r in rows)
        rec[t] = rows
    for t, col in RIGHE.items():
        try:
            if col is None:
                rec[t] = get(f"{t}?select=*&status=neq.CLOSED&limit=2000")
            else:
                rec[t] = get(f"{t}?select=*&{col}=gte.{GIORNO}&order={col}.asc&limit=5000")
        except Exception as e:  # tabella/colonna diversa: si registra l'errore
            rec[t] = {"errore": repr(e)[:200]}
    with open(OUT / f"giro_{n:04d}.json", "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, default=str)
    with open(OUT / "indice.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"giro": n, "ts": rec["ts"], "nuove_attivita": {t: len(rec[t]) for t in ATTIVITA}}) + "\n")


if __name__ == "__main__":
    mins = float(sys.argv[1]) if len(sys.argv) > 1 else 60
    per = float(sys.argv[2]) if len(sys.argv) > 2 else 300
    fine = time.time() + mins * 60
    n = 0
    while time.time() < fine:
        n += 1
        try:
            giro(n)
        except Exception as e:
            print("errore giro", n, repr(e)[:300], flush=True)
        time.sleep(per)
