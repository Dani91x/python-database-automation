"""confronto_d.py - E2E FASE 2 (26/09), passo D: view-model VERO della Control Room vs DB (sola lettura).

Legge un file plancia/vm_*.json (scritto da frontend/e2e_fase2/plancia.e2e.test.tsx) e confronta con
righe lette ORA dal DB via GET PostgREST: posizioni aperte (id, prezzo, stake, liability, modalita'),
liability paper totale, realizzato di oggi in paper per sport, righe bot (stato/modalita'/P&L tennis).
Stampa JSON con ogni confronto e l'esito. Uso: confronto_d.py <vm.json>
"""
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
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


d = json.load(open(sys.argv[1], encoding="utf8"))
vm = d["vm"]
out = {"vm_ts": d["ts"], "confronti": []}


def c(nome, video, db, ok, nota=""):
    out["confronti"].append({"controllo": nome, "a_video": video, "db": db, "esito": "OK" if ok else "KO", "nota": nota})


# 1) posizioni aperte
pos = vm.get("posizioni") or []
vid = []
for p in pos:
    vid.append({k: p.get(k) for k in ("bot", "id", "tradeId", "eventId", "evento", "selezione", "lato", "prezzo",
                                      "stake", "liability", "modalita", "stato", "pnlSeChiudo", "fonte", "etaS")
                if k in p})
out["posizioni_a_video"] = vid
oo = get("omega_trades?select=id,event_id,side,price,size,liability,mode,status&status=in.(open,pending)")
mo = get("mike_trades?select=id,event_id,side,price,size,liability,mode,status,role&status=in.(open,pending)")
so = get("safe_strategy_trades?select=id,event_id,side,price,size,mode,status,strategy&status=in.(open,pending)")
out["db_aperte"] = {"omega": oo, "mike": mo, "safe": so}
liab_db = 0.0
for r in oo:
    liab_db += float(r["liability"] or 0)
for r in mo:
    liab_db += float(r["liability"] or (float(r["size"]) if r["side"] == "back" else 0))
for r in so:
    liab_db += float(r["size"]) * (float(r["price"]) - 1.0) if r["side"] == "lay" else float(r["size"])
tot = vm.get("totali") or {}
c("liabilityPaper (totali) vs somma liability aperte DB (omega+mike+safe)", tot.get("liabilityPaper"), round(liab_db, 2),
  abs(float(tot.get("liabilityPaper") or 0) - liab_db) < 0.01)
c("numero posizioni a video vs righe aperte DB", len(pos), len(oo) + len(mo) + len(so), len(pos) == len(oo) + len(mo) + len(so),
  "a video possono esserci anche tennis/scalper")
# 2) realizzato paper di oggi
tl = get("tennis_live_orders?select=source,mode,pnl,settled_at&mode=eq.paper&settled_at=gte.2026-09-26T00:00:00Z")
rp = (vm.get("realizzatoOggi") or {}).get("paper") or {}
ten_db = round(sum(float(r["pnl"] or 0) for r in tl), 2)
c("realizzato paper tennis (vm) vs somma pnl tennis_live_orders paper regolati oggi", (rp.get("perSport") or {}).get("tennis"), ten_db,
  abs(float((rp.get("perSport") or {}).get("tennis") or 0) - ten_db) < 0.005)
cal = []
for t, q in (("omega_trades", "omega_trades?select=id,pnl,mode,settled_at&mode=eq.paper&settled_at=gte.2026-09-26T00:00:00Z"),
             ("mike_trades", "mike_trades?select=id,pnl,mode,settled_at&mode=eq.paper&settled_at=gte.2026-09-26T00:00:00Z"),
             ("safe_strategy_trades", "safe_strategy_trades?select=id,pnl,mode,settled_at,sport&mode=eq.paper&settled_at=gte.2026-09-26T00:00:00Z")):
    try:
        rows = get(q)
    except Exception as e:  # colonna diversa: si dichiara
        rows = [{"errore": repr(e)[:120]}]
    cal.append({t: rows})
out["db_regolati_calcio"] = cal
# 3) righe bot
bots = vm.get("bots") or []
ctl = {"omega": get("omega_control?select=status,mode")[0], "mike": get("mike_control?select=status,mode")[0],
       "safe": get("safe_strategy_control?select=status,mode")[0]}
for r in get("tennis_bot_service_control?select=bot_key,status,mode"):
    ctl[r["bot_key"]] = r
ctl["scalper"] = get("scalper_service_control?select=status,mode")[0]
for b in bots:
    k = b.get("bot")
    if k in ctl:
        c(f"riga {k}: inCorsa/modalita", [b.get("inCorsa"), b.get("modalita"), b.get("stato")],
          [ctl[k]["status"], ctl[k]["mode"]], bool(b.get("inCorsa")) == (ctl[k]["status"] == "running") and b.get("modalita") == ctl[k]["mode"])
    if str(k).startswith("tennis_"):
        pdb = round(sum(float(r["pnl"] or 0) for r in tl if r["source"] == k), 2) if any(r["source"] == k for r in tl) else None
        c(f"cr-bot-pnl-{k} (pnlOggiPaper) vs somma pnl paper regolati", b.get("pnlOggiPaper"), pdb,
          (b.get("pnlOggiPaper") is None and pdb is None) or (b.get("pnlOggiPaper") is not None and pdb is not None and abs(b["pnlOggiPaper"] - pdb) < 0.005))
out["bots_a_video"] = [{k: b.get(k) for k in ("bot", "inCorsa", "modalita", "stato", "fonteStato", "etaStatoS", "etaPushS",
                                               "freschezzaPush", "varianti", "modiStrategia", "motivoBlocco", "tettoPartite",
                                               "partiteEsposte", "pnlOggi", "pnlOggiPaper")} for b in bots]
out["n_KO"] = sum(1 for x in out["confronti"] if x["esito"] == "KO")
print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
