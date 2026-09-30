"""Sonda in SOLA LETTURA: stessa logica di arretrati_prova con query normali.

Uso (dalla radice del worktree): python AUDIT_2026-09-30/sonda_arretrati_prova.py
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv(os.path.join("..", "..", "..", ".env"))
from db_client import get_supabase_client

sb = get_supabase_client()
try:
    r = sb.rpc("get_mike_state").execute().data
    print("RPC keys:", sorted(r.keys()) if isinstance(r, dict) else type(r))
except Exception as e:
    print("RPC errore:", str(e)[:300])
ROME = ZoneInfo("Europe/Rome")
oggi = datetime.now(ROME).date()
print("oggi Roma", oggi)


def pages(tab, sel="*", flt=None):
    out = []
    o = 0
    while True:
        q = sb.table(tab).select(sel)
        if flt:
            q = flt(q)
        d = q.range(o, o + 999).execute().data or []
        out += d
        if len(d) < 1000:
            break
        o += 1000
    return out


tr = pages("mike_trades", "*", lambda q: q.order("id"))
ev = {e["event_id"]: e for e in pages("mike_events", "event_id,event_name,ko_at")}
print("trades", len(tr), "eventi", len(ev), "mode:", {t["mode"] for t in tr})


def g(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ROME).date() if iso else None


byid = {t["id"]: t for t in tr}


def apertura(t):
    seen = set()
    while t.get("closes_trade_id") and t["id"] not in seen:
        seen.add(t["id"])
        t = byid.get(t["closes_trade_id"], t)
    return t


sel = []
for t in tr:
    if t["mode"] != "paper" or not t.get("settled_at") or g(t["settled_at"]) != oggi:
        continue
    ap = apertura(t)
    e = ev.get(t["event_id"]) or {}
    ref = e.get("ko_at") or ap["placed_at"]
    if g(ref) < oggi:
        sel.append((t, ap, e))
print("selezionate:", len(sel))
for t, ap, e in sel:
    print(t["id"], t["event_id"], e.get("event_name"), e.get("ko_at"), t["placed_at"],
          t["settled_at"], t["status"], t["pnl"], t["closes_trade_id"])
print("live regolate oggi (non devono entrare):",
      sum(1 for t in tr if t["mode"] == "live" and t.get("settled_at") and g(t["settled_at"]) == oggi))
print("paper regolate oggi totali:",
      sum(1 for t in tr if t["mode"] == "paper" and t.get("settled_at") and g(t["settled_at"]) == oggi))
