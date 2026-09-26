"""verifica_safe_c.py - E2E FASE 2 (26/09), semantica C per Safe calcio (base/esatto/punta).

SOLA LETTURA. Rigioca le righe del feed REGISTRATE dal 47336 (canali/scanner/*.gz, una per evento ogni
4 s) dentro il motore di PRODUZIONE `engine.SafeEngine` (stessi parametri di `safe_strategy_control`
risolti con `bot_service.resolve_params`), con l'orologio al tempo della registrazione: a ogni passo
(5 s) passa lo stato COMPLETO (ultima riga per evento) come fa il servizio. Raccoglie i SEGNALI attivi
(= tutte le condizioni del manuale vere) e li confronta con i trade `safe_strategy_trades` e con le
attivita' `skip` del bot:
  * ingresso senza segnale del ricalcolo nei +-20 s        -> ingresso FUORI condizione (KO candidato)
  * segnale senza ingresso ne' skip motivato nei +-60 s   -> MANCATO INGRESSO da spiegare
Limiti dichiarati: righe al piu' ogni 4 s (il servizio le vede ogni 2 s): la stabilita' del punteggio
(>=30 s) puo' partire fino a 4 s dopo; le condizioni fuori dal motore (tetti del servizio, stake,
una posizione per evento, veto campionati del servizio) non sono nel motore: si leggono dagli skip.
Uso: verifica_safe_c.py <dalle_utc ISO> <alle_utc ISO>
"""
import glob, gzip, json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())
from Betfair.safe_strategy import engine as E, bot_db, bot_service  # noqa: E402

REG = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\canali\scanner"


def ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


t_da, t_a = ms(sys.argv[1]), ms(sys.argv[2])
righe = []
for f in sorted(glob.glob(os.path.join(REG, "*.jsonl.gz"))):
    try:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r["t"] == "scan_calcio" and t_da - 120000 <= r["ts_ms"] <= t_a:
                    righe.append(r)
    except (OSError, EOFError):
        pass
righe.sort(key=lambda r: r["ts_ms"])
ctl = bot_db.read_control() or {}
params = bot_service.resolve_params(ctl.get("params") or {})
clock = {"t": 0.0}
eng = E.SafeEngine(params, clock=lambda: clock["t"])
stato = {}
segnali = []   # (ts_ms, event_id, variant, side, selection, price)
i = 0
passo = 5000
t = righe[0]["ts_ms"] if righe else t_da
while t <= t_a and righe:
    while i < len(righe) and righe[i]["ts_ms"] <= t:
        d = righe[i]["d"]
        stato[str(d["event_id"])] = d
        i += 1
    clock["t"] = t / 1000.0
    try:
        sig = eng.evaluate(list(stato.values()))
    except Exception as e:
        print("errore motore", repr(e)[:200])
        sig = []
    if t >= t_da:
        for s in sig:
            segnali.append({"ts": datetime.fromtimestamp(t / 1000, timezone.utc).isoformat()[11:19], "ts_ms": t,
                            "event_id": s.event_id, "variant": s.variant, "side": s.side,
                            "selection": s.selection_name, "price": getattr(s, "price", None) or getattr(s, "entry_odds", None)})
    t += passo
trades = bot_db._sb().table("safe_strategy_trades").select(
    "id,event_id,event_name,strategy,side,selection_name,price,placed_at,mode,origin").gte(
    "placed_at", sys.argv[1]).lte("placed_at", sys.argv[2]).execute().data or []
trades = [x for x in trades if x.get("strategy") in ("base", "esatto", "punta")]
skips = bot_db._sb().table("safe_strategy_activity").select("ts,kind,payload").gte("ts", sys.argv[1]).lte(
    "ts", sys.argv[2]).in_("kind", ["skip", "place"]).execute().data or []
out = {"finestra": sys.argv[1:3], "righe_rigiocate": len(righe), "segnali_ricalcolati": len(segnali),
       "ingressi": [], "segnali_senza_ingresso": []}
for tr in trades:
    tt = ms(tr["placed_at"])
    ok = [s for s in segnali if s["event_id"] == str(tr["event_id"]) and s["variant"] == tr["strategy"]
          and abs(s["ts_ms"] - tt) <= 20000]
    out["ingressi"].append({"trade": tr, "segnale_ricalcolato_vicino": ok[:2],
                            "esito": "OK" if ok else "KO_candidato: ingresso senza segnale ricalcolato"})
visti = set()
for s in segnali:
    k = (s["event_id"], s["variant"], s["side"])
    if k in visti:
        continue
    visti.add(k)
    tr = [x for x in trades if str(x["event_id"]) == s["event_id"] and x["strategy"] == s["variant"]]
    if tr:
        continue
    sk = [a for a in skips if str((a.get("payload") or {}).get("event_id")) == s["event_id"]
          and abs(ms(a["ts"]) - s["ts_ms"]) <= 60000]
    out["segnali_senza_ingresso"].append({"segnale": s, "skip_del_bot_vicini": [
        {"ts": a["ts"][11:19], "kind": a["kind"], "reason": (a.get("payload") or {}).get("reason"),
         "variant": (a.get("payload") or {}).get("variant")} for a in sk[:6]]})
print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
