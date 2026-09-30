# Sonda SOLA LETTURA (30/09): legge UN messaggio "board" dal canale locale del
# runner calcio come LETTORE (nessun comando possibile) e conta le righe.
import asyncio, json, sys
import websockets

PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 47331


async def main():
    async with websockets.connect(f"ws://127.0.0.1:{PORTA}/lettore/board", max_size=None) as ws:
        for _ in range(30):
            msg = json.loads(await asyncio.wait_for(ws.recv(), 30))
            if msg.get("t") == "board" or msg.get("topic") == "board" or "rows" in json.dumps(msg)[:200]:
                break
        print("chiavi messaggio", list(msg.keys()))
        d = msg.get("d") or msg.get("data") or msg.get("payload") or msg
        rows = d.get("rows") or []
        vuote = [r for r in rows if all(s.get("back") is None and s.get("lay") is None
                                        for s in r.get("selections") or [])]
        print("righe", len(rows), "senza quote", len(vuote))
        for r in vuote[:2]:
            print(json.dumps(r)[:500])
        piene = [r for r in rows if r not in vuote]
        for r in piene[:2]:
            print("PIENA", json.dumps(r)[:500])

asyncio.run(main())
