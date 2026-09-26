"""ascolto_canali.py - E2E FASE 2 (26/09): ascoltatore in SOLA LETTURA dei canali locali dell'app.

Si collega SENZA token (quindi senza poter comandare: i canali dei bot sono solo_lettura e i runner
accettano 'order' solo col token dell'app) alle porte 47331-47338 e registra i push {t, d}.
Non invia MAI nulla sul socket. Uscita: JSONL nella cartella e2e_fase2/canali del checkout PRINCIPALE.
 - topic *_stato / hello / battito / modo_ordini / scanner_stato: il primo, poi uno ogni 30 s per topic,
   SEMPRE intero se cambia `status`/`mode` del control;
 - topic di righe (posizioni/attivita/proposta/armamento/sessioni/order/position): TUTTI interi;
 - ladder/now/board/scan_calcio/scan_tennis: solo conteggi, piu' un campione intero ogni 60 s;
 - conteggi al minuto per topic.
Uso: python ascolto_canali.py <minuti>
"""
import asyncio, json, sys, time
from pathlib import Path
import websockets

OUT = Path(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\canali")
OUT.mkdir(parents=True, exist_ok=True)
PORTE = {47331: "runner_calcio", 47332: "runner_tennis", 47333: "mike", 47334: "omega",
         47335: "safe", 47336: "scanner", 47337: "tennis_bot", 47338: "scalper"}
STATO = ("_stato", "hello", "battito", "modo_ordini", "scanner_stato")
PESANTI = ("ladder", "now", "board", "scan_calcio", "scan_tennis")
giorno = time.strftime("%Y%m%d_%H%M%S")
f_msg = open(OUT / f"messaggi_{giorno}.jsonl", "a", encoding="utf-8")
f_cnt = open(OUT / f"conteggi_{giorno}.jsonl", "a", encoding="utf-8")
ultimo, firma, conta = {}, {}, {}


def scrivi(porta, t, d, perche):
    rec = {"ts_ms": int(time.time() * 1000), "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "porta": porta, "canale": PORTE[porta], "t": t, "perche": perche, "d": d}
    f_msg.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    f_msg.flush()


def gestisci(porta, raw):
    try:
        m = json.loads(raw)
    except Exception:
        return
    t = m.get("t")
    if not isinstance(t, str):
        return
    d = m.get("d")
    k = (porta, t)
    conta[k] = conta.get(k, 0) + 1
    now = time.time()
    if any(t.endswith(s) or t == s for s in STATO):
        ctl = d.get("control") if isinstance(d, dict) and isinstance(d.get("control"), dict) else (d if isinstance(d, dict) else {})
        fr = (ctl.get("status"), ctl.get("mode"), ctl.get("bot_key"))
        kk = (porta, t, ctl.get("bot_key"))
        if kk not in ultimo:
            scrivi(porta, t, d, "primo"); ultimo[kk] = now; firma[kk] = fr
        elif fr != firma.get(kk):
            scrivi(porta, t, d, f"cambio {firma.get(kk)} -> {fr}"); ultimo[kk] = now; firma[kk] = fr
        elif now - ultimo[kk] >= 30:
            scrivi(porta, t, d, "campione30s"); ultimo[kk] = now
    elif t in PESANTI:
        if now - ultimo.get(k, 0) >= 60:
            scrivi(porta, t, d, "campione60s"); ultimo[k] = now
    else:
        scrivi(porta, t, d, "riga")


async def ascolta(porta, fine):
    while time.time() < fine:
        try:
            async with websockets.connect(f"ws://127.0.0.1:{porta}", max_size=None, open_timeout=5) as ws:
                scrivi(porta, "_connesso", None, "connessione")
                while time.time() < fine:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    gestisci(porta, raw)
        except Exception as e:  # canale giu': si registra e si riprova
            scrivi(porta, "_errore", repr(e)[:200], "connessione")
            await asyncio.sleep(3)


async def minuti(fine):
    while time.time() < fine:
        await asyncio.sleep(60)
        rec = {"ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "conteggi": {f"{PORTE[p]}:{t}": n for (p, t), n in sorted(conta.items())}}
        f_cnt.write(json.dumps(rec) + "\n"); f_cnt.flush()
        conta.clear()


async def main(mins):
    fine = time.time() + mins * 60
    await asyncio.gather(*(ascolta(p, fine) for p in PORTE), minuti(fine))


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 60))
