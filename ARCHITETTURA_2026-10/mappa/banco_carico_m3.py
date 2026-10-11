"""banco_carico_m3.py - il registratore del canale sotto carico (M-3, revisione 11/10).

Lo stesso banco della revisione indipendente: canale di PRODUZIONE
(``LocalChannel``) su una porta libera di 127.0.0.1, TRE client veri (un desktop
col token e due lettori ``/lettore/order``) che leggono ciascuno nel suo thread,
una SONDA nel loop del canale ogni 5 ms (ritardo = quanto il loop arriva tardi
rispetto al previsto: e' il tempo che un ordine o un ladder aspetterebbero), e
un carico di ``--al-secondo`` publish ``order`` (payload PIENO, quindi scritto
per intero) da ``--kb`` KB l'uno. Fasi alternate: registratore SPENTO e ACCESO
(thread di scrittura vero, gzip vero, in una cartella usa e getta); con
``--anche-vecchio`` anche la versione del commit ``3625838b`` (json.loads +
ripulitura + json.dumps nel thread di scrittura), presa con ``git show``.

    python ARCHITETTURA_2026-10/mappa/banco_carico_m3.py --secondi 15 --giri 2 \\
        --al-secondo 100 --kb 20 --cartella <cartella usa e getta> --anche-vecchio

Non tocca l'app: nessun runner, nessun processo, solo questo script.
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))

from Betfair.stream import local_channel  # noqa: E402
from Betfair.stream import registratore_canale as reg_nuovo  # noqa: E402
from Betfair.stream.local_channel import LocalChannel  # noqa: E402

TOKEN = "b" * 64
COMMIT_VECCHIO = "3625838b"


def _porta() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _q(v: List[float], p: float) -> float:
    if not v:
        return float("nan")
    s = sorted(v)
    return s[max(0, min(len(s) - 1, int(-(-p * len(s) // 100)) - 1))]


def _vecchio() -> Any:
    r = subprocess.run(["git", "show", "%s:Betfair/stream/registratore_canale.py" % COMMIT_VECCHIO],
                       cwd=str(RADICE), capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise SystemExit("git show del commit %s fallito: %s" % (COMMIT_VECCHIO, r.stderr))
    nome = "Betfair.stream._registratore_canale_vecchio"
    spec = importlib.util.spec_from_loader(nome, loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "Betfair.stream"
    mod.__file__ = reg_nuovo.__file__
    sys.modules[nome] = mod
    exec(compile(r.stdout, "<%s>" % COMMIT_VECCHIO, "exec"), mod.__dict__)  # noqa: S102
    return mod


def _payload(i: int, kb: int) -> Dict[str, Any]:
    ordini = []
    n = 0
    while n < kb * 1024:
        o = {"bet_id": "B%d_%d" % (i, len(ordini)), "market_id": "1.%d" % (i % 10),
             "selection_id": 1000 + len(ordini), "side": "BACK", "price": 2.02,
             "size": 4.0, "size_matched": 1.5, "status": "EXECUTABLE",
             "customer_order_ref": "omega-%d-%d" % (i, len(ordini)), "mode": "live"}
        ordini.append(o)
        n += len(json.dumps(o))
    return {"modo": "live", "seq": i, "ordini": ordini}


def fase(secondi: float, modo: str, cartella: Path, al_secondo: int, kb: int,
         vecchio: Any) -> Dict[str, Any]:
    from websockets.sync.client import connect

    reg_nuovo.spegni()
    if vecchio is not None:
        vecchio.spegni()
    local_channel._reg = reg_nuovo
    if modo == "acceso":
        reg_nuovo.azzera_per_test()
        assert reg_nuovo.accendi(cartella=str(cartella), _consenti_in_test=True)
    elif modo == "vecchio":
        vecchio.azzera_per_test()
        local_channel._reg = vecchio
        assert vecchio.accendi(cartella=str(cartella), _consenti_in_test=True)
    porta = _porta()
    ch = LocalChannel(porta, sport="calcio", token=TOKEN)
    assert ch.start()
    stop = threading.Event()
    ricevuti = [0, 0, 0]

    def leggi(ws: Any, k: int) -> None:
        while not stop.is_set():
            try:
                ws.recv(timeout=0.5)
                ricevuti[k] += 1
            except TimeoutError:
                continue
            except Exception:  # noqa: BLE001
                return

    ritardi: List[float] = []

    async def sonda() -> None:
        while not stop.is_set():
            t0 = time.perf_counter()
            await asyncio.sleep(0.005)
            ritardi.append((time.perf_counter() - t0 - 0.005) * 1000.0)

    with connect(f"ws://127.0.0.1:{porta}/?t={TOKEN}", open_timeout=5) as a, \
            connect(f"ws://127.0.0.1:{porta}/lettore/order", open_timeout=5) as b, \
            connect(f"ws://127.0.0.1:{porta}/lettore/order", open_timeout=5) as c:
        for ws in (a, b, c):
            ws.recv(timeout=5)
        lettori = [threading.Thread(target=leggi, args=(ws, k), daemon=True)
                   for k, ws in enumerate((a, b, c))]
        for t in lettori:
            t.start()
        payload = [_payload(i, kb) for i in range(20)]
        time.sleep(0.3)
        loop = ch._loop
        assert loop is not None
        fut = asyncio.run_coroutine_threadsafe(sonda(), loop)
        time.sleep(0.5)
        ritardi.clear()
        cpu0, t_ini = time.process_time(), time.perf_counter()
        passo = 1.0 / float(al_secondo)
        n = 0
        prossimo = time.perf_counter()
        while time.perf_counter() - t_ini < secondi:
            ora = time.perf_counter()
            if ora < prossimo:
                time.sleep(min(0.002, prossimo - ora))
                continue
            prossimo += passo
            ch.publish("order", payload[n % len(payload)])
            n += 1
        durata = time.perf_counter() - t_ini
        cpu = (time.process_time() - cpu0) / durata * 100.0
        time.sleep(0.5)
        stop.set()
        try:
            fut.result(timeout=2)
        except Exception:  # noqa: BLE001
            pass
        for t in lettori:
            t.join(timeout=2)
    attivo = reg_nuovo if modo != "vecchio" else vecchio
    attivo.spegni(attesa_s=30.0)
    local_channel._reg = reg_nuovo
    conti = attivo.conti() if modo != "spento" else None
    return {"modo": modo, "pubblicati": n, "ricevuti": ricevuti, "secondi": round(durata, 2),
            "sonde": len(ritardi), "ritardo_p50_ms": round(_q(ritardi, 50), 3),
            "ritardo_p99_ms": round(_q(ritardi, 99), 3),
            "ritardo_max_ms": round(max(ritardi) if ritardi else float("nan"), 3),
            "cpu_pct": round(cpu, 1),
            "scritti": (conti or {}).get("scritti"),
            "scartati_coda": (conti or {}).get("scartati_coda")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--secondi", type=float, default=15.0)
    ap.add_argument("--giri", type=int, default=2)
    ap.add_argument("--al-secondo", type=int, default=100)
    ap.add_argument("--kb", type=int, default=20)
    ap.add_argument("--cartella", required=True)
    ap.add_argument("--anche-vecchio", action="store_true")
    a = ap.parse_args()
    vecchio = _vecchio() if a.anche_vecchio else None
    modi = ["spento", "acceso"] + (["vecchio"] if vecchio is not None else [])
    ris: Dict[str, List[Dict[str, Any]]] = {m: [] for m in modi}
    for g in range(a.giri):
        for m in modi:
            r = fase(a.secondi, m, Path(a.cartella) / ("%s_%d" % (m, g)), a.al_secondo, a.kb,
                     vecchio)
            ris[m].append(r)
            print(json.dumps(r), flush=True)
    for m in modi:
        g = ris[m]
        print("%-8s ritardo del loop p50 %.2f ms, p99 %.2f ms, max %.2f ms; CPU %.1f%% "
              "(peggiore dei giri: p99 %.2f, max %.2f)" % (
                  m, sorted(x["ritardo_p50_ms"] for x in g)[len(g) // 2],
                  sorted(x["ritardo_p99_ms"] for x in g)[len(g) // 2],
                  sorted(x["ritardo_max_ms"] for x in g)[len(g) // 2],
                  sorted(x["cpu_pct"] for x in g)[len(g) // 2],
                  max(x["ritardo_p99_ms"] for x in g), max(x["ritardo_max_ms"] for x in g)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
