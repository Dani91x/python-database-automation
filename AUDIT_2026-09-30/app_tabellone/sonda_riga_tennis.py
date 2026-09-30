# Sonda SOLA LETTURA (30/09): le righe tennis_live_orders dei 4 bot tennis che
# la RPC get_tennis_bot_orders_today restituisce OGGI (coalesce(placed_at,
# updated_at) = oggi) e quelle ancora "aperte" per la Control Room. Solo SELECT.
import sys, os, json
sys.path.insert(0, os.getcwd())
from db_client import get_supabase_client

sb = get_supabase_client()
BOT = ["tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing"]
r = (sb.table("tennis_live_orders").select("*")
     .in_("source", BOT).gte("updated_at", "2026-09-29T22:00:00+00:00")
     .order("updated_at").execute())
print("righe bot tennis con updated_at di oggi:", len(r.data))
for o in r.data:
    print(json.dumps(o, default=str))
aperte = (sb.table("tennis_live_orders").select("id,source,mode,event_id,status,placed_at,updated_at,settled_at,size_matched,size_remaining")
          .in_("source", BOT).is_("settled_at", "null").gt("size_remaining", 0).execute())
print("righe bot tennis NON regolate con residuo > 0 (tutte le date):", len(aperte.data))
for o in aperte.data:
    print(json.dumps(o, default=str))
f = sb.table("tennis_live_follow").select("*").eq("event_id", "36117569").execute()
print("follow 36117569:", json.dumps(f.data, default=str)[:600])
q = (sb.table("tennis_live_order_queue").select("id,action,status,created_at,updated_at,event_id")
     .eq("event_id", "36117569").order("id", desc=True).limit(5).execute())
print("coda 36117569:", json.dumps(q.data, default=str)[:900])
