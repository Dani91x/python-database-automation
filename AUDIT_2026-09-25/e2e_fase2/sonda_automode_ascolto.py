"""sonda_automode_ascolto.py - E2E FASE 2 (26/09), referto ADMIN26_AUTOMODE_SAFE.

SOLA LETTURA. Si collega come LETTORE (percorso /lettore/<topic>, nessun token, nessun invio,
non conta come "desktop collegato") ai canali:
  47336 scanner (scan_calcio, scan_tennis, scanner_stato)
  47335 Safe (safe_attivita, safe_proposta, safe_posizioni_calcio, safe_posizioni_tennis, safe_stato)
  47337 tennis bot (tennis_bot_stato, tennis_bot_armamento, tennis_bot_posizioni)
  47338 scalper (scalper_stato, scalper_sessioni)
e, a parte, fa girare IN MEMORIA un SafeEngine di PRODUZIONE (Betfair.safe_strategy.engine.SafeEngine,
importato, mai riscritto) sulle stesse righe del feed ricevute dal canale 47336, ogni 2 s (poll del bot),
con i params VERI letti (GET) da safe_strategy_control ogni 5 min. Registra:
  - automode_safe/bot_msgs_*.jsonl       : ogni riga dei topic dei bot (stato: al cambio o ogni 30 s)
  - automode_safe/engine_segnali_*.jsonl : ogni segnale ATTIVO nuovo del motore indipendente
  - automode_safe/engine_stati_*.jsonl   : per evento in gioco, stato varianti al CAMBIO
  - SCRATCH/scan_raw_*.jsonl.gz          : tutte le righe scan ricevute
Uso: python sonda_automode_ascolto.py <minuti>
"""
import asyncio
import gzip
import json
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import websockets  # noqa: E402
from Betfair.safe_strategy import engine as E  # noqa: E402
import sonda_automode_db as DB  # noqa: E402

OUT = Path(__file__).resolve().parent / "automode_safe"
OUT.mkdir(exist_ok=True)
SCRATCH = Path(r"C:\Users\Admin\AppData\Local\Temp\claude\C--Users-Admin"
               r"\c122eed7-7d1e-4bc1-980e-b620a1c006ce\scratchpad\automode")
SCRATCH.mkdir(parents=True, exist_ok=True)
TAG = time.strftime("%Y%m%d_%H%M%S")
f_bot = open(OUT / f"bot_msgs_{TAG}.jsonl", "a", encoding="utf-8")
f_sig = open(OUT / f"engine_segnali_{TAG}.jsonl", "a", encoding="utf-8")
f_st = open(OUT / f"engine_stati_{TAG}.jsonl", "a", encoding="utf-8")
f_raw = gzip.open(SCRATCH / f"scan_raw_{TAG}.jsonl.gz", "at", encoding="utf-8")

LETTORI = {
    47336: "scan_calcio,scan_tennis,scanner_stato",
    47335: "safe_attivita,safe_proposta,safe_posizioni_calcio,safe_posizioni_tennis,safe_stato",
    47337: "tennis_bot_stato,tennis_bot_armamento,tennis_bot_posizioni",
    47338: "scalper_stato,scalper_sessioni",
}
righe = {}
ultimo_stato = {}
firma_stato = {}
stati_eval = {}
segnali_visti = set()
params = {"v": None, "letto": 0.0}


def now_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def scrivi(f, rec):
    f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    f.flush()


def gestisci(porta, raw):
    try:
        m = json.loads(raw)
    except Exception:
        return
    t, d = m.get("t"), m.get("d")
    if not isinstance(t, str):
        return
    ts = int(time.time() * 1000)
    if t in ("scan_calcio", "scan_tennis") and isinstance(d, dict) and d.get("event_id"):
        ev = str(d["event_id"])
        prev = righe.get(ev)
        if prev is None or E._accepts(prev, d):
            righe[ev] = {k: d.get(k) for k in ("event_id", "sport", "payload", "updated_at")}
        f_raw.write(json.dumps({"ts_ms": ts, "d": d}, ensure_ascii=False, default=str) + "\n")
        return
    if t.endswith("_stato"):
        ctl = d if isinstance(d, dict) else {}
        chiave = (porta, t, ctl.get("bot_key"))
        st = ctl.get("stats") if isinstance(ctl.get("stats"), dict) else {}
        fr = json.dumps([ctl.get("status"), ctl.get("mode"), st.get("auto"), st.get("motivo_blocco")],
                        sort_keys=True, default=str)
        if fr != firma_stato.get(chiave) or time.time() - ultimo_stato.get(chiave, 0) >= 30:
            firma_stato[chiave] = fr
            ultimo_stato[chiave] = time.time()
            scrivi(f_bot, {"ts_ms": ts, "ts_utc": now_utc(), "porta": porta, "t": t, "d": d})
        return
    scrivi(f_bot, {"ts_ms": ts, "ts_utc": now_utc(), "porta": porta, "t": t, "d": d})


async def ascolta(porta, fine):
    url = f"ws://127.0.0.1:{porta}/lettore/{LETTORI[porta]}"
    while time.time() < fine:
        try:
            async with websockets.connect(url, max_size=None, open_timeout=5) as ws:
                scrivi(f_bot, {"ts_ms": int(time.time() * 1000), "ts_utc": now_utc(), "porta": porta,
                               "t": "_connesso", "d": url})
                while time.time() < fine:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    gestisci(porta, raw)
        except Exception as e:
            scrivi(f_bot, {"ts_ms": int(time.time() * 1000), "ts_utc": now_utc(), "porta": porta,
                           "t": "_errore", "d": repr(e)[:200]})
            await asyncio.sleep(3)


def leggi_params():
    try:
        r = DB.get("safe_strategy_control?select=params,status,mode,updated_at&limit=1")
        if r:
            params["v"] = r[0].get("params") or {}
            params["letto"] = time.time()
            scrivi(f_bot, {"ts_ms": int(time.time() * 1000), "ts_utc": now_utc(), "porta": 0,
                           "t": "_params_safe", "d": r[0]})
    except Exception as e:
        scrivi(f_bot, {"ts_ms": int(time.time() * 1000), "ts_utc": now_utc(), "porta": 0,
                       "t": "_params_errore", "d": repr(e)[:200]})


def _chk(evx):
    return [[c.id, c.ok, c.value] for c in evx.checks]


async def motore(fine):
    eng = None
    while time.time() < fine:
        await asyncio.sleep(2)
        if params["v"] is None or time.time() - params["letto"] > 300:
            await asyncio.to_thread(leggi_params)
            if params["v"] is None:
                continue
            if eng is None:
                eng = E.SafeEngine(params["v"])
            else:
                eng.update_params(params["v"])
        ora = time.time()
        for ev in [e for e, r in righe.items() if (E._parse_ts(r.get("updated_at")) or 0) <= ora - 600]:
            righe.pop(ev, None)
        vive = [r for r in righe.values() if (E._parse_ts(r.get("updated_at")) or 0) > ora - 180]
        try:
            sig = eng.evaluate(vive)
        except Exception as e:
            scrivi(f_sig, {"ts_utc": now_utc(), "errore_motore": repr(e)[:300]})
            continue
        for s in sig:
            if s.key in segnali_visti:
                continue
            segnali_visti.add(s.key)
            r = righe.get(str(s.event_id)) or {}
            scrivi(f_sig, {"ts_ms": int(ora * 1000), "ts_utc": now_utc(), "key": s.key,
                           "event_id": s.event_id, "variant": s.variant, "sport": s.sport,
                           "event_name": s.event_name, "side": s.side, "price": s.price,
                           "size": s.size, "size_available": s.size_available,
                           "minute": s.minute, "score": s.score,
                           "market_id": s.market_id, "selection_id": s.selection_id,
                           "checks": s.checks, "riga_updated_at": r.get("updated_at"),
                           "payload": r.get("payload")})
        for m in getattr(eng, "_last_monitors", []) or []:
            if not getattr(m.ctx, "inplay", False):
                continue
            firma = [(x.variant, x.sub_id, x.state,
                      tuple(sorted(c.id for c in x.checks if c.ok is not True))) for x in m.evaluations]
            fs = json.dumps(firma, default=str)
            if stati_eval.get(m.event_id) != fs:
                stati_eval[m.event_id] = fs
                p = m.payload if isinstance(m.payload, dict) else {}
                scrivi(f_st, {"ts_ms": int(ora * 1000), "ts_utc": now_utc(), "event_id": m.event_id,
                              "sport": m.sport, "event_name": p.get("event_name"),
                              "competition": p.get("competition"), "minute": p.get("minute"),
                              "score": [p.get("score_home"), p.get("score_away")],
                              "sets": p.get("sets"), "games": p.get("games"),
                              "valutazioni": [{"variant": x.variant, "sub_id": x.sub_id,
                                               "state": x.state, "entry_odds": x.entry_odds,
                                               "checks": _chk(x)} for x in m.evaluations]})


async def main(mins):
    fine = time.time() + mins * 60
    await asyncio.gather(*(ascolta(p, fine) for p in LETTORI), motore(fine))


if __name__ == "__main__":
    try:
        asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 150))
    finally:
        f_raw.close()
