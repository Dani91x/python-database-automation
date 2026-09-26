"""sonda_feed_atlante_71_monitor.py - 7.1.1-7.1.4 (e2e fase 2, 26/09): monitor in SOLA LETTURA.
Ogni PASSO secondi, nello stesso istante:
  * battito scanner (safe_strategy_status id=scanner) ed eta';
  * RICONTEGGIO INDIPENDENTE delle partite del feed unico (safe_strategy_scan) con i filtri
    dichiarati da scalper (auto_mode.partite_dal_feed: mo_market_id, mo_status!=CLOSED, home/away),
    tennis (tennis_live/auto_mode.partite_dal_feed: mo_market_id, mo_status!=CLOSED) e auto-follow
    (auto_follow.partite_dal_feed: mo_status!=CLOSED e almeno un mercato fra mo/cs/ht/btts/ht_result/ou);
    reimplementati QUI (non importati) per confrontarli con le note dei servizi;
  * nota stats.auto dello scalper (scalper_service_control) e dei 4 bot tennis;
  * sessioni scalper_control e righe tennis_live_follow con origine='auto', live_follow STREAMING (event_id in feed?);
  * stato dell'auto-follow del runner: hello del canale 47331 (lettore, nessun token, topic auto_follow).
Scrive una riga JSON per passo in sonda_71_monitor.jsonl. Nessuna scrittura sul DB.
Uso: python sonda_feed_atlante_71_monitor.py <minuti> [passo_s]
"""
import asyncio, datetime as dt, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonda_feed_atlante_db import get

QUI = Path(__file__).resolve().parent
def ts(s):
    if not s: return None
    d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()

def conta_feed():
    sel = ("event_id,sport,updated_at,inplay:payload->inplay,home:payload->>home,away:payload->>away,"
           "mo:payload->>mo_market_id,mo_status:payload->>mo_status,cs:payload->cs->>market_id,"
           "ht:payload->ht->>market_id,btts:payload->btts->>market_id,htr:payload->ht_result->>market_id,ou:payload->ou")
    st, righe, ms = get(f"safe_strategy_scan?select={sel}&limit=5000")
    if st != 200: return {"errore": str(righe)[:200]}
    cal = [r for r in righe if r["sport"] == "calcio"]; ten = [r for r in righe if r["sport"] == "tennis"]
    aperta = lambda r: str(r.get("mo_status") or "").upper() != "CLOSED"
    scal = [r for r in cal if r.get("mo") and aperta(r) and (r.get("home") or "").strip() and (r.get("away") or "").strip()]
    def mercati(r):
        m = {x for x in (r.get("mo"), r.get("cs"), r.get("ht"), r.get("btts"), r.get("htr")) if x}
        m |= {str(b["market_id"]) for b in (r.get("ou") or []) if isinstance(b, dict) and b.get("market_id")}
        return m
    af = [r for r in cal if aperta(r) and mercati(r)]
    tn = [r for r in ten if r.get("mo") and aperta(r)]
    ora = time.time()
    return {"righe_calcio": len(cal), "righe_tennis": len(ten), "ms": ms,
            "partite_scalper": len(scal), "partite_tennis": len(tn), "partite_autofollow": len(af),
            "calcio_agg_30s": sum(1 for r in cal if ora - ts(r["updated_at"]) <= 30),
            "ev_scalper": sorted(r["event_id"] for r in scal), "ev_tennis": sorted(r["event_id"] for r in tn),
            "upd": {r["event_id"]: r["updated_at"] for r in righe}}

async def hello_47331():
    import websockets
    try:
        async with websockets.connect("ws://127.0.0.1:47331/lettore/auto_follow", open_timeout=5) as ws:
            m = json.loads(await asyncio.wait_for(ws.recv(), 5))
            return (m.get("d") or {}).get("auto_follow")
    except Exception as e:
        return {"errore": repr(e)[:200]}

def passo():
    o = {"t": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    st, s, _ = get("safe_strategy_status?select=updated_at&id=eq.scanner&limit=1")
    o["scanner_eta_s"] = round(time.time() - ts(s[0]["updated_at"]), 1) if st == 200 and s else None
    f = conta_feed(); upd = f.pop("upd", {}); o["feed"] = f
    st, sc, _ = get("scalper_service_control?select=status,mode,stats,updated_at&limit=1")
    o["scalper_srv"] = ({"status": sc[0]["status"], "mode": sc[0]["mode"], "auto": (sc[0].get("stats") or {}).get("auto")}
                        if st == 200 and sc else sc)
    st, tb, _ = get("tennis_bot_service_control?select=bot_key,status,mode,stats&limit=10")
    o["tennis_srv"] = ({r["bot_key"]: {"status": r["status"], "mode": r["mode"], "auto": (r.get("stats") or {}).get("auto")}
                        for r in tb} if st == 200 else tb)
    st, sa, _ = get("scalper_control?select=event_id,status,mode,dry_run,origine,requested_at,updated_at"
                    "&origine=eq.auto&order=updated_at.desc&limit=50")
    o["scalper_auto_righe"] = ([dict(r, in_feed=r["event_id"] in upd, feed_upd=upd.get(r["event_id"])) for r in sa]
                               if st == 200 else sa)
    st, ta, _ = get("tennis_live_follow?select=event_id,market_id,status,origine,updated_at"
                    "&origine=eq.auto&order=updated_at.desc&limit=50")
    o["tennis_auto_follow"] = ([dict(r, in_feed=str(r["event_id"]) in upd, feed_upd=upd.get(str(r["event_id"])))
                                for r in ta] if st == 200 else ta)
    st, lf, _ = get("live_follow?select=event_id,status,origine,updated_at&status=eq.STREAMING&limit=200")
    o["live_follow_streaming"] = ([{"event_id": r["event_id"], "origine": r.get("origine")} for r in lf]
                                  if st == 200 else lf)
    o["auto_follow_47331"] = asyncio.run(hello_47331())
    return o

if __name__ == "__main__":
    minuti = float(sys.argv[1]) if len(sys.argv) > 1 else 1
    ogni = float(sys.argv[2]) if len(sys.argv) > 2 else 60
    fine = time.time() + minuti * 60
    while True:
        try:
            o = passo()
        except Exception as e:
            o = {"t": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "errore": repr(e)[:300]}
        with open(QUI / "sonda_71_monitor.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(o, ensure_ascii=False, default=str) + "\n")
        if time.time() + ogni > fine: break
        time.sleep(ogni)
