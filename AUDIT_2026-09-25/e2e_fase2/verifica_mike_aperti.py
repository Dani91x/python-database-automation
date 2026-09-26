"""verifica_mike_aperti.py - E2E FASE 2, RIAVVIO 2 (SOLA LETTURA, GET PostgREST): i 6 trade paper di Mike
rimasti `open` alla chiusura dell'app (5070-5075, eventi 36111770 e 36111764, femminili finite ~11:50Z).

Uso: verifica_mike_aperti.py [minuti_di_attesa]  (default 0 = una sola lettura)
Controlli, ripetuti ogni 60 s fino alla regolazione di tutti o allo scadere:
  1. REGOLAZIONE: status di 5070-5075 (open -> won/lost/void), settled_at, pnl; mike_events.state/settled_pnl.
  2. NESSUN DOPPIO ORDINE: nessuna riga nuova in mike_trades per i due eventi dopo il riavvio (placed_at >
     inizio del riavvio), nessuna chiusura (closes_trade_id in 5070-5075) e nessuna attivita' `place`
     per i due eventi dopo il riavvio (partite finite: non deve aprire ne' chiudere niente).
  3. P&L NETTO ricalcolato per gamba (commissione 5% sul vinto netto del MERCATO, come verifica_pnl):
     OU35 Under back 5070/5071/5072, OU45 Over back 5073/5074/5075 -> atteso dall'esito del mercato
     (risultato finale da IPS nella riga mike_events.live: score_home/score_away) e confronto con pnl
     scritto e con settled_pnl dell'evento (somma delle gambe dello stesso evento).
  4. Attivita' di Mike sui due eventi dopo il riavvio (kind, conteggio) per spiegare la regolazione.
"""
import json, sys, time, urllib.request
from pathlib import Path

W = Path(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
OUT = W / "AUDIT_2026-09-25" / "e2e_fase2" / "mike_aperti"
OUT.mkdir(parents=True, exist_ok=True)
env = {}
for line in open(W / ".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_ROLE_KEY"]
IDS = [5070, 5071, 5072, 5073, 5074, 5075]
EVENTI = ["36111770", "36111764"]
C = 0.05
RIAVVIO = "2026-09-26T14:58:00Z"   # l'utente ha chiuso l'app alle 16:58 locali: tutto cio' che e' dopo e' del riavvio 2


def get(path):
    req = urllib.request.Request(URL + "/rest/v1/" + path, method="GET",
                                 headers={"apikey": KEY, "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def atteso(t, gol):
    """pnl netto atteso per UNA gamba back, dato il totale gol finale (None = ignoto)."""
    if gol is None or t["status"] == "open":
        return None
    s, p = float(t["size"]), float(t["avg_price_matched"] or t["price"])
    linea = 3.5 if "35" in str(t["market_type"]) else 4.5
    under = "Under" in str(t["selection_name"])
    vince = (gol < linea) if under else (gol > linea)
    return round(s * (p - 1) * (1 - C), 2) if vince else round(-s, 2)


def giro():
    ids = ",".join(map(str, IDS))
    tr = get(f"mike_trades?select=id,event_id,role,side,market_type,selection_name,price,size,avg_price_matched,size_matched,mode,status,pnl,settled_at&id=in.({ids})&order=id")
    ev = get("mike_events?select=event_id,state,settled_pnl,live,updated_at&event_id=in.(" + ",".join(EVENTI) + ")")
    nuovi = get("mike_trades?select=id,event_id,role,status,mode,placed_at,closes_trade_id&event_id=in.("
                + ",".join(EVENTI) + f")&placed_at=gt.{RIAVVIO}")
    chiusure = get(f"mike_trades?select=id,closes_trade_id,placed_at&closes_trade_id=in.({ids})")
    att = get("mike_activity?select=kind,ts,event_id&event_id=in.(" + ",".join(EVENTI) + f")&ts=gt.{RIAVVIO}&order=id&limit=2000")
    gol = {}
    for e in ev:
        lv = e.get("live") or {}
        try:
            gol[e["event_id"]] = int(lv.get("score_home")) + int(lv.get("score_away"))
        except (TypeError, ValueError):
            gol[e["event_id"]] = None
    righe = []
    for t in tr:
        a = atteso(t, gol.get(t["event_id"]))
        righe.append({**t, "gol_finali_dal_feed": gol.get(t["event_id"]), "pnl_atteso": a,
                      "esito_pnl": None if a is None else ("OK" if abs(a - float(t["pnl"] or 0)) < 0.011 else "KO")})
    per_ev = {}
    for t in tr:
        per_ev[t["event_id"]] = round(per_ev.get(t["event_id"], 0) + float(t["pnl"] or 0), 2)
    kinds = {}
    for x in att:
        kinds[(x["event_id"], x["kind"])] = kinds.get((x["event_id"], x["kind"]), 0) + 1
    out = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "regolati": sum(1 for t in tr if t["status"] != "open"), "su": len(tr),
        "righe": righe,
        "eventi": [{"event_id": e["event_id"], "state": e["state"], "settled_pnl": e["settled_pnl"],
                    "somma_pnl_gambe": per_ev.get(e["event_id"]),
                    "coerente": e["settled_pnl"] is None or abs(float(e["settled_pnl"]) - per_ev.get(e["event_id"], 0)) < 0.011}
                   for e in ev],
        "doppi_ordini": {"righe_nuove_dopo_riavvio": nuovi, "chiusure_dei_6": chiusure,
                         "esito": "OK" if not nuovi and not chiusure else "KO"},
        "attivita_dopo_riavvio": {f"{k[0]}:{k[1]}": n for k, n in sorted(kinds.items())},
    }
    return out


if __name__ == "__main__":
    fine = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 0) * 60
    while True:
        o = giro()
        (OUT / f"mike_aperti_{o['ts'].replace(':', '')}.json").write_text(json.dumps(o, indent=1, ensure_ascii=False), encoding="utf-8")
        print(o["ts"], "regolati", o["regolati"], "/", o["su"], "| doppi", o["doppi_ordini"]["esito"],
              "| pnl", [(r["id"], r["status"], r["pnl"], r["esito_pnl"]) for r in o["righe"]], flush=True)
        if o["regolati"] == o["su"] or time.time() >= fine:
            break
        time.sleep(60)
