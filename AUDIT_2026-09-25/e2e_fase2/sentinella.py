"""sentinella.py - E2E FASE 2 (26/09): una riga per evento notevole (SOLA LETTURA, GET PostgREST).
Ogni 60 s: attivita' nuove dei bot con kind notevoli, qualunque riga `live` in trade/ordini di oggi,
cambi di status/mode delle righe di controllo, freno/order_mode. Uso: sentinella.py <minuti>"""
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


NOIOSI = {"skip", "modalita", "superficie", "missione_blocca", "feed_line_missing", "opportunita_non_piu_valida",
          "diagnosi", "state", "info", "exit_hold", "exit_wait", "submin_step", "min_bet_skip", "habitat_scan", "sniper_lines"}
ATT = ["omega_activity", "mike_activity", "safe_strategy_activity", "tennis_bot_activity", "scalper_activity"]
cur = {}
for t in ATT:
    r = get(f"{t}?select=id&order=id.desc&limit=1")
    cur[t] = r[0]["id"] if r else 0
prev_ctl = {}
fine = time.time() + float(sys.argv[1]) * 60
while time.time() < fine:
    try:
        for t in ATT:
            rows = get(f"{t}?select=*&id=gt.{cur[t]}&order=id.asc&limit=1000")
            for r in rows:
                cur[t] = max(cur[t], r["id"])
                if r["kind"] in NOIOSI:
                    continue
                p = json.dumps(r.get("payload"), ensure_ascii=False)[:220]
                print(f"{r['ts'][11:19]}Z {t.split('_')[0]}{(':' + r['bot_key']) if r.get('bot_key') else ''} {r['kind']} ev={r.get('event_id') or (r.get('payload') or {}).get('event_id')} {p}", flush=True)
        for t, q in (("omega_trades", "placed_at"), ("mike_trades", "placed_at"), ("safe_strategy_trades", "placed_at"),
                     ("tennis_live_orders", "updated_at"), ("betfair_live_orders", "updated_at"),
                     ("betfair_live_order_requests", "requested_at"), ("tennis_bot_control", "updated_at"),
                     ("scalper_control", "updated_at")):
            rows = get(f"{t}?select=*&mode=eq.live&{q}=gte.2026-09-26T09:00:00Z&limit=5")
            if rows:
                print(f"!!! RIGA LIVE in {t}: {json.dumps(rows[0])[:300]}", flush=True)
        ctl = {}
        for t in ("omega_control", "mike_control", "safe_strategy_control", "scalper_service_control"):
            r = get(f"{t}?select=status,mode")[0]
            ctl[t] = (r["status"], r["mode"])
        for r in get("tennis_bot_service_control?select=bot_key,status,mode"):
            ctl[r["bot_key"]] = (r["status"], r["mode"])
        s = get("betfair_live_settings?select=order_mode,kill_switch")[0]
        ctl["settings"] = (s["order_mode"], s["kill_switch"])
        for k, v in ctl.items():
            if prev_ctl.get(k) != v:
                print(f"CONTROLLO {k}: {prev_ctl.get(k)} -> {v}", flush=True)
        prev_ctl = ctl
    except Exception as e:
        print("errore sentinella", repr(e)[:200], flush=True)
    time.sleep(60)
