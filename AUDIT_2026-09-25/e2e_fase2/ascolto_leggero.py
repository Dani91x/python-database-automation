"""ascolto_leggero.py - E2E FASE 2, RIAVVIO 2: registratore LEGGERO dei canali locali (SOLA LETTURA).

Websocket SENZA token su 47331-47338, non invia mai nulla. Memoria costante: per ogni (porta, topic) un
contatore del minuto e l'istante dell'ultimo campione; niente liste. Scrive in APPEND:
  * una riga di conteggi per topic ogni 60 s;
  * UN campione intero (payload) per topic ogni 60 s (i topic di stato portano `control`);
  * gli eventi di connessione/errore.
Rotazione del file ogni 30 min. Uscita: e2e_fase2/canali_r2/. Uso: python ascolto_leggero.py <minuti>
"""
import asyncio, json, sys, time
from pathlib import Path
import websockets

OUT = Path(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\canali_r2")
OUT.mkdir(parents=True, exist_ok=True)
PORTE = {47331: "runner_calcio", 47332: "runner_tennis", 47333: "mike", 47334: "omega",
         47335: "safe", 47336: "scanner", 47337: "tennis_bot", 47338: "scalper"}
conta = {}
ultimo = {}


def fh():
    blocco = time.strftime("%Y%m%d_%H", time.gmtime()) + ("00" if time.gmtime().tm_min < 30 else "30")
    return open(OUT / f"canali_{blocco}Z.jsonl", "a", encoding="utf-8")


def scrivi(rec):
    with fh() as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def gestisci(porta, raw):
    try:
        m = json.loads(raw)
    except Exception:
        return
    t = m.get("t")
    if not isinstance(t, str):
        return
    k = (porta, t)
    conta[k] = conta.get(k, 0) + 1
    now = time.time()
    if now - ultimo.get(k, 0) >= 60:
        ultimo[k] = now
        scrivi({"tipo": "campione", "ts_ms": int(now * 1000), "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "canale": PORTE[porta], "t": t, "d": m.get("d")})


async def ascolta(porta, fine):
    while time.time() < fine:
        try:
            async with websockets.connect(f"ws://127.0.0.1:{porta}", max_size=None, open_timeout=5) as ws:
                scrivi({"tipo": "connesso", "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "canale": PORTE[porta]})
                while time.time() < fine:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    gestisci(porta, raw)
        except Exception as e:
            scrivi({"tipo": "errore", "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "canale": PORTE[porta], "e": repr(e)[:160]})
            await asyncio.sleep(5)


async def minuti(fine):
    while time.time() < fine:
        await asyncio.sleep(60)
        c = {f"{PORTE[p]}:{t}": n for (p, t), n in sorted(conta.items())}
        conta.clear()
        scrivi({"tipo": "conteggi", "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "c": c})


async def main(mins):
    fine = time.time() + mins * 60
    await asyncio.gather(*(ascolta(p, fine) for p in PORTE), minuti(fine))


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 60))
