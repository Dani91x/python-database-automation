"""ascolto_scanner.py - E2E FASE 2 (26/09): registra in SOLA LETTURA le righe del feed unico (47336).

Serve alla verifica semantica B (ricalcolo delle decisioni dai dati dello STESSO istante): per ogni
evento salva la riga intera `scan_calcio`/`scan_tennis` al piu' ogni 4 s, compressa (gzip, un file
per ora). Non invia MAI nulla sul socket; nessun token. Uso: python ascolto_scanner.py <minuti>
"""
import asyncio, gzip, json, sys, time
from pathlib import Path
import websockets

OUT = Path(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\canali\scanner")
OUT.mkdir(parents=True, exist_ok=True)
OGNI_S = 4.0
ultimo = {}
_f = {"ora": None, "fh": None}


def fh():
    ora = time.strftime("%Y%m%d_%H", time.gmtime())
    if _f["ora"] != ora:
        if _f["fh"]:
            _f["fh"].close()
        _f["fh"] = gzip.open(OUT / f"scan_{ora}Z.jsonl.gz", "at", encoding="utf-8")
        _f["ora"] = ora
    return _f["fh"]


async def main(mins):
    fine = time.time() + mins * 60
    n = 0
    while time.time() < fine:
        try:
            async with websockets.connect("ws://127.0.0.1:47336", max_size=None, open_timeout=5) as ws:
                while time.time() < fine:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        m = json.loads(raw)
                    except Exception:
                        continue
                    t = m.get("t")
                    if t not in ("scan_calcio", "scan_tennis"):
                        continue
                    d = m.get("d")
                    righe = d if isinstance(d, list) else [d]
                    now = time.time()
                    for r in righe:
                        if not isinstance(r, dict):
                            continue
                        ev = str(r.get("event_id"))
                        if now - ultimo.get(ev, 0) < OGNI_S:
                            continue
                        ultimo[ev] = now
                        f = fh()
                        f.write(json.dumps({"ts_ms": int(now * 1000), "t": t, "d": r}, ensure_ascii=False, default=str) + "\n")
                        n += 1
                        if n % 200 == 0:
                            f.flush()
        except Exception as e:
            print("errore", repr(e)[:200], flush=True)
            await asyncio.sleep(3)
    if _f["fh"]:
        _f["fh"].close()


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 60))
