"""verifica_mike_c.py - SOLA LETTURA: parametri EFFETTIVI di Mike (mike.config.merge_params sui params
di mike_control, funzione di produzione) e controllo C degli ingressi pre-match di oggi: banda di prezzo,
stake, finestra (ko - entry_hours_before_ko .. ko - pre_last_entry_min). Uso: verifica_mike_c.py"""
import json, os, sys
from datetime import datetime

sys.path.insert(0, os.getcwd())
from Betfair.mike import db as MDB, config as MC  # noqa: E402

ctl = MDB.read_control() or {}
p = MC.merge_params(ctl.get("params") or {})
chiavi = ["stake", "pre_entry_price_min", "pre_entry_price_max", "entry_hours_before_ko", "pre_last_entry_min",
          "pre_min_back_size_factor", "pre_max_spread_ticks", "pre_max_cycles", "uscite_automatiche",
          "veto_p_under35_cal", "competition_filter", "pre_enabled"]
out = {"params_effettivi": {k: p.get(k) for k in chiavi}, "ingressi": []}
sb = MDB._sb()
trades = sb.table("mike_trades").select("id,event_id,role,side,price,size,mode,placed_at").eq(
    "role", "under_entry").gte("placed_at", "2026-09-26T09:00:00Z").execute().data or []
for t in trades:
    ev = (sb.table("mike_events").select("event_id,event_name,ko_at,competition").eq("event_id", t["event_id"]).execute().data or [{}])[0]
    ko = datetime.fromisoformat(str(ev.get("ko_at")).replace("Z", "+00:00"))
    pl = datetime.fromisoformat(str(t["placed_at"]).replace("Z", "+00:00"))
    min_prima = (ko - pl).total_seconds() / 60.0
    c = {
        "banda_prezzo": float(p["pre_entry_price_min"]) <= float(t["price"]) <= float(p["pre_entry_price_max"]),
        "stake": abs(float(t["size"]) - float(p["stake"])) < 1e-9,
        "finestra": float(p["pre_last_entry_min"]) <= min_prima <= float(p["entry_hours_before_ko"]) * 60.0,
        "paper": t["mode"] == "paper",
    }
    out["ingressi"].append({"trade": t, "evento": ev, "minuti_prima_del_ko": round(min_prima, 1), "condizioni": c,
                            "esito": "OK" if all(c.values()) else "KO"})
print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
