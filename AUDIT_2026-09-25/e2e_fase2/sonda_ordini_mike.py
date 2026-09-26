"""sonda_ordini_mike.py - E2E FASE 2 (26/09). SOLA LETTURA. Come sonda_ordini_catena.py ma per mike_trades
(paper REST interno, fuori dallo specchio): libro del feed prima/dopo placed_at, +bet delay, delta tick
(ticks_between di produzione), mercato_operabile di produzione.
Uso: python sonda_ordini_mike.py"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sonda_ordini_catena as C

scan = C.carica_scan()
_, rows = C.get("mike_trades?select=*&placed_at=gte.2026-09-26T09:11:56Z&order=id.asc&limit=200")
for r in rows:
    t = C.ms(r["placed_at"])
    ev = str(r["event_id"])
    p, d = C.intorno(scan.get(ev), t)
    lb = C.libro(p, r["market_id"], r["selection_id"]) if p else None
    bd = (p or {}).get("bet_delay") or 0
    q, _ = C.intorno(scan.get(ev), t + bd * 1000.0)
    lbq = C.libro(q, r["market_id"], r["selection_id"]) if q else None
    print(json.dumps({"id": r["id"], "ev": f'{ev} {r["event_name"]}', "role": r["role"], "mkt": r["market_type"],
                      "sel": r["selection_name"], "side": r["side"], "price": r["price"], "size": r["size"],
                      "avg": r["avg_price_matched"], "matched": r["size_matched"], "fill": (r.get("meta") or {}).get("fill"),
                      "min/sc riga": [r["minute_at_entry"], r["score_at_entry"]], "placed_at": r["placed_at"],
                      "scan_prima": None if not p else {"rx": C.iso(p["rx_ms"]), "min": p["min"], "sc": p["sc"],
                                                        "eta_ms": round(t - p["rx_ms"]), "libro": lb},
                      "verifica": C.verifica_prezzo(r["side"], r["avg_price_matched"], lb),
                      "operabile": C.operabile(lb),
                      "libro_+bet_delay": None if not q else {"bd": bd, "rx": C.iso(q["rx_ms"]), "libro": lbq}},
                     ensure_ascii=False, default=str))
