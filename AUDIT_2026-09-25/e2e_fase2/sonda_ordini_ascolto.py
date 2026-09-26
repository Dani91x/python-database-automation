"""sonda_ordini_ascolto.py - E2E FASE 2 (26/09), referto ADMIN26_ORDINI_SCHEDE. SOLA LETTURA.

Ascoltatore SENZA token (nessun comando possibile: local_channel.py:53-63) delle porte:
  47331 runner calcio (tutti i topic tranne ladder/now: interi; ladder/now: solo conteggio)
  47334 omega, 47335 safe (tutti i topic interi; *_stato un campione ogni 20 s o al cambio)
  47336 scanner: scan_calcio COMPATTO (ts ricezione, odds_ts_ms, odds_pt_ms, minuto, punteggio,
        mo_status, quote MO, blocco CS e HT come tuple), scritto SOLO quando cambia per evento.
Non invia MAI nulla sul socket. Uscita: canali_ordini/<porta>_<ora>.jsonl
Uso: python sonda_ordini_ascolto.py <minuti>
"""
import asyncio, json, sys, time
from pathlib import Path
import websockets

OUT = Path(__file__).resolve().parent / "canali_ordini"
OUT.mkdir(parents=True, exist_ok=True)
PORTE = {47331: "runner_calcio", 47334: "omega", 47335: "safe", 47336: "scanner"}
tag = time.strftime("%Y%m%d_%H%M%S")
FILES = {p: open(OUT / f"{n}_{tag}.jsonl", "a", encoding="utf-8") for p, n in PORTE.items()}
ultimo_stato, firma_scan, conta = {}, {}, {}


def w(porta, rec):
    FILES[porta].write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    FILES[porta].flush()


def _sel(s):
    return [s.get("selection_id"), s.get("name"), s.get("runner_status"), s.get("back"), s.get("lay"),
            s.get("back_size"), s.get("lay_size")]


def compatta(d):
    p = d.get("payload") or {}
    cs = p.get("cs") or {}
    ht = p.get("ht") or {}
    odds = p.get("odds") or {}
    return {
        "ev": d.get("event_id"), "name": p.get("event_name"), "comp": p.get("competition"),
        "inplay": p.get("inplay"), "min": p.get("minute"),
        "sc": [p.get("score_home"), p.get("score_away")],
        "mo": [p.get("mo_market_id"), p.get("mo_status")],
        "odds": {k: [v.get("selection_id"), v.get("back"), v.get("lay"), v.get("back_size"), v.get("lay_size")]
                 for k, v in odds.items() if isinstance(v, dict)},
        "cs": [cs.get("market_id"), cs.get("status"), [_sel(s) for s in cs.get("selections") or []]] if cs else None,
        "ht": [ht.get("market_id"), ht.get("status"), [_sel(s) for s in ht.get("selections") or []]] if ht else None,
        "altri": {k: [[b.get("market_id"), b.get("market_type"), b.get("line"), b.get("status"),
                       [_sel(s) for s in b.get("selections") or []]] for b in (p.get(k) if isinstance(p.get(k), list) else [p.get(k)]) if isinstance(b, dict)]
                  for k in ("ou", "btts", "ht_result") if p.get(k)},
        "odds_ts_ms": p.get("odds_ts_ms"), "odds_pt_ms": p.get("odds_pt_ms"), "bet_delay": p.get("bet_delay"),
    }


def gestisci(porta, raw):
    now = time.time()
    try:
        m = json.loads(raw)
    except Exception:
        return
    t = m.get("t"); d = m.get("d")
    if not isinstance(t, str):
        return
    conta[(porta, t)] = conta.get((porta, t), 0) + 1
    base = {"rx_ms": int(now * 1000), "t": t}
    if porta == 47336:
        if t in ("scan_calcio", "scan_tennis") and isinstance(d, dict):
            c = compatta(d)
            f = json.dumps({k: v for k, v in c.items() if k not in ("odds_ts_ms", "odds_pt_ms")}, default=str)
            if firma_scan.get(c["ev"]) != f:
                firma_scan[c["ev"]] = f
                w(porta, {**base, **c})
        elif t in ("scanner_stato", "hello"):
            if now - ultimo_stato.get((porta, t), 0) >= 60:
                ultimo_stato[(porta, t)] = now; w(porta, {**base, "d": d})
        return
    if porta == 47331 and t in ("ladder", "now", "account"):
        if t == "account" and now - ultimo_stato.get((porta, t), 0) < 120:
            return
        ultimo_stato[(porta, t)] = now
        w(porta, {**base, "d": d if t == "account" else None, "nota": "solo conteggio" if t != "account" else None})
        return
    if t.endswith("_stato") or t == "battito":
        if now - ultimo_stato.get((porta, t), 0) < 20:
            return
        ultimo_stato[(porta, t)] = now
    w(porta, {**base, "d": d})


async def ascolta(porta, fine):
    while time.time() < fine:
        try:
            async with websockets.connect(f"ws://127.0.0.1:{porta}", max_size=None, open_timeout=5) as ws:
                w(porta, {"rx_ms": int(time.time() * 1000), "t": "_connesso"})
                while time.time() < fine:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    gestisci(porta, raw)
        except Exception as e:
            w(porta, {"rx_ms": int(time.time() * 1000), "t": "_errore", "d": repr(e)[:200]})
            await asyncio.sleep(3)


async def main(mins):
    fine = time.time() + mins * 60
    await asyncio.gather(*(ascolta(p, fine) for p in PORTE))


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 60))
