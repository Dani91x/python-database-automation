"""sonda_fase3_canali.py - admin-26 fase 3: LETTORE puro dei canali locali (percorso /lettore/<topic>,
nessun token, NESSUN invio: il server rifiuta ogni comando da un lettore, local_channel.py:396-402).
Registra per N secondi ogni messaggio in JSONL: {"ts": <epoch ms locale>, "porta": p, "msg": {...}}.
Uso: python sonda_fase3_canali.py <secondi> <file_out.jsonl>
"""
import asyncio, json, sys, time
import websockets

TOPIC = {
    47331: "hello,now,battito,account,ladder,position,order,board,modo_ordini",
    47332: "hello,now,battito,account,ladder,position,order,board,modo_ordini",
    47333: "mike_stato,mike_posizioni,account",
    47334: "omega_stato,omega_posizioni,omega_proposta,account",
    47335: "safe_stato,safe_posizioni_calcio,safe_posizioni_tennis,safe_proposta,account",
    47336: "scan_calcio,scan_tennis,scanner_stato",
    47337: "tennis_bot_stato,tennis_bot_posizioni",
    47338: "scalper_stato,scalper_sessioni",
}


async def leggi(porta, fine, out):
    url = f"ws://127.0.0.1:{porta}/lettore/{TOPIC[porta]}"
    try:
        async with websockets.connect(url, max_size=None, open_timeout=5) as ws:
            while time.time() < fine:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, fine - time.time()))
                except asyncio.TimeoutError:
                    break
                out.write(json.dumps({"ts": int(time.time() * 1000), "porta": porta, "msg": json.loads(raw)}) + "\n")
    except Exception as e:  # noqa: BLE001
        out.write(json.dumps({"ts": int(time.time() * 1000), "porta": porta, "errore": repr(e)}) + "\n")


async def main(sec, path):
    fine = time.time() + sec
    with open(path, "w", encoding="utf8") as out:
        await asyncio.gather(*(leggi(p, fine, out) for p in TOPIC))


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]), sys.argv[2]))
