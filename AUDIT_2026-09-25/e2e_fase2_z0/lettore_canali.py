"""SONDA DI SOLA LETTURA dei canali locali 47331-47338 (E2E fase 2, Z0, 26/09).

Si collega come LETTORE (`/lettore/<topic,...>`, Betfair/stream/local_channel.py:115-133):
nessun token, nessun header Origin, NESSUN messaggio inviato (mai `send`), mai `/comando/`.
Un lettore non conta come desktop (non cambia il comportamento del runner).
Uso: python lettore_canali.py <secondi> <out.json>
"""
import asyncio, json, sys, time, statistics
from datetime import datetime
import websockets

CANALI = {
    47331: "battito,modo_ordini,now,account,auto_follow,betfair_live_xhedge,board,order",
    47332: "battito,modo_ordini,now,account,order",
    47333: "mike_stato,mike_posizioni,mike_attivita,mike_event",
    47334: "omega_stato,omega_posizioni,omega_attivita,omega_proposta",
    47335: "safe_stato,safe_posizioni_calcio,safe_posizioni_tennis,safe_attivita,safe_proposta,safe_scan",
    47336: "scan_calcio,scan_tennis,scanner_stato",
    47337: "tennis_bot_stato,tennis_bot_posizioni,tennis_bot_armamento",
    47338: "scalper_stato,scalper_sessioni",
}


def _ts(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v / 1000.0 if v > 1e11 else float(v)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _cerca(d, chiavi=("updated_at", "ts")):
    if isinstance(d, dict):
        for k in chiavi:
            if k in d and _ts(d[k]) is not None:
                return k, _ts(d[k])
        for k in ("riga", "row", "d", "control"):
            if isinstance(d.get(k), dict):
                r = _cerca(d[k], chiavi)
                if r:
                    return r
    return None


def _corto(x, n=1500):
    s = json.dumps(x, default=str, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "...<troncato>"


async def leggi(porta, topics, secondi):
    out = {"porta": porta, "topics_richiesti": topics, "hello": None, "per_topic": {}, "errore": None}
    try:
        async with websockets.connect(f"ws://127.0.0.1:{porta}/lettore/{topics}",
                                      open_timeout=5, max_size=None) as ws:
            fine = time.time() + secondi
            while time.time() < fine:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, fine - time.time()))
                except asyncio.TimeoutError:
                    break
                ora = time.time()
                m = json.loads(raw)
                t = m.get("t")
                d = m.get("d")
                if t == "hello" and out["hello"] is None:
                    out["hello"] = d
                    out["hello_at"] = ora
                    continue
                pt = out["per_topic"].setdefault(t, {"n": 0, "eta_s": [], "primo": None, "ultimo": None,
                                                     "chiave_eta": None, "ricevuti_at": []})
                pt["n"] += 1
                pt["ricevuti_at"].append(round(ora, 3))
                if pt["primo"] is None:
                    pt["primo"] = _corto(d)
                pt["ultimo"] = _corto(d)
                c = _cerca(d)
                if c:
                    pt["chiave_eta"] = c[0]
                    pt["eta_s"].append(round(ora - c[1], 3))
    except Exception as ex:
        out["errore"] = repr(ex)[:300]
    for t, pt in out["per_topic"].items():
        e = sorted(pt["eta_s"])
        if e:
            pt["eta_p50"] = e[len(e) // 2]
            pt["eta_p95"] = e[min(len(e) - 1, int(len(e) * 0.95))]
            pt["eta_max"] = e[-1]
        r = pt.pop("ricevuti_at")
        if len(r) > 1:
            gaps = [b - a for a, b in zip(r, r[1:])]
            pt["intervallo_medio_s"] = round(statistics.mean(gaps), 3)
            pt["intervallo_max_s"] = round(max(gaps), 3)
        pt["eta_s"] = pt["eta_s"][:50]
    return out


async def main():
    secondi = float(sys.argv[1])
    dest = sys.argv[2]
    inizio = datetime.now().astimezone().isoformat()
    ris = await asyncio.gather(*(leggi(p, t, secondi) for p, t in CANALI.items()))
    with open(dest, "w", encoding="utf-8") as f:
        json.dump({"inizio_locale": inizio, "fine_locale": datetime.now().astimezone().isoformat(),
                   "secondi": secondi, "canali": ris}, f, indent=1, ensure_ascii=False, default=str)
    for r in ris:
        print(r["porta"], "ERR" if r["errore"] else "ok", r["errore"] or "", "hello:", _corto(r["hello"], 400))
        for t, pt in r["per_topic"].items():
            print("   ", t, "n=", pt["n"], "eta p50/p95/max=", pt.get("eta_p50"), pt.get("eta_p95"),
                  pt.get("eta_max"), "(", pt["chiave_eta"], ") int medio/max", pt.get("intervallo_medio_s"),
                  pt.get("intervallo_max_s"))


asyncio.run(main())
