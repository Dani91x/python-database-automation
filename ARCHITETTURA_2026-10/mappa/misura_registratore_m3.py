"""misura_registratore_m3.py - costo e peso del registratore del canale (M-3).

Carico: ``--al-secondo`` ladder al secondo su 10 mercati (di serie 500 = 10 x 50,
il caso peggiore; 50 = 10 mercati al tetto del canale di 200 ms), riga del ladder
con la forma di ``runner.py``: 3 runner x 10 livelli per lato), 1 ``order`` al
secondo, 1 ``conto`` ogni 5 s. Canale di PRODUZIONE (``LocalChannel``) su una
porta libera di 127.0.0.1, un client desktop VERO che legge in un thread e un
lettore ``/lettore/order``. Due fasi alternate per ``--giri`` volte: registratore
SPENTO e ACCESO (thread di scrittura vero, gzip vero, in una cartella usa e getta).

Misura per fase: costo di ``publish()`` nel chiamante (us/messaggio, p50/p99),
latenza publish -> ricezione nel client (ms, p50/p95/p99), CPU del processo (%),
messaggi ricevuti; in fase accesa anche i byte gzip scritti e la proiezione al
giorno. Non tocca l'app: nessun runner, nessun processo, solo questo script.

    python ARCHITETTURA_2026-10/mappa/misura_registratore_m3.py --secondi 10 --giri 2 \\
        --cartella <cartella usa e getta>

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))

from Betfair.stream import registratore_canale as reg  # noqa: E402
from Betfair.stream.local_channel import LocalChannel  # noqa: E402

TOKEN = "m" * 64


def _porta() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _ladder(mid: str, i: int, t: float) -> Dict[str, Any]:
    lad = {"runners": [{"selection_id": 1000 + r,
                        "back": [[round(2.0 + 0.02 * (lv + i % 3), 2), 10.0 + lv + i % 7]
                                 for lv in range(10)],
                        "lay": [[round(2.02 + 0.02 * (lv + i % 3), 2), 12.0 + lv + i % 5]
                                for lv in range(10)],
                        "ltp": 2.02, "tv": 12345.6 + i} for r in range(3)]}
    return {"event_id": "35760084", "market_id": mid, "market_type": "MATCH_ODDS",
            "market_name": "Esito Finale", "status": "OPEN", "ladder": lad, "t0": t}


def _q(v: List[float], p: float) -> float:
    if not v:
        return float("nan")
    s = sorted(v)
    return s[max(0, min(len(s) - 1, int(-(-p * len(s) // 100)) - 1))]


def fase(secondi: float, acceso: bool, cartella: Path, al_secondo: int = 500) -> Dict[str, Any]:
    from websockets.sync.client import connect

    reg.spegni()
    reg.azzera_per_test()
    if acceso:
        assert reg.accendi(cartella=str(cartella), _consenti_in_test=True)
    porta = _porta()
    ch = LocalChannel(porta, sport="calcio", token=TOKEN)
    assert ch.start()
    lat: List[float] = []
    ricevuti = [0]
    stop = threading.Event()

    def leggi(ws: Any) -> None:
        while not stop.is_set():
            try:
                m = ws.recv(timeout=0.5)
            except TimeoutError:
                continue
            except Exception:  # noqa: BLE001
                return
            ricevuti[0] += 1
            try:
                d = json.loads(m).get("d") or {}
                if isinstance(d, dict) and "t0" in d:
                    lat.append((time.perf_counter() - d["t0"]) * 1000.0)
            except Exception:  # noqa: BLE001
                pass

    costi: List[float] = []
    with connect(f"ws://127.0.0.1:{porta}/?t={TOKEN}", open_timeout=5) as desk, \
            connect(f"ws://127.0.0.1:{porta}/lettore/order", open_timeout=5) as lett:
        desk.recv(timeout=5)
        lett.recv(timeout=5)
        t_desk = threading.Thread(target=leggi, args=(desk,), daemon=True)
        t_desk.start()
        time.sleep(0.3)
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
            mid = "1.%d" % (n % 10)
            a = time.perf_counter()
            ch.publish("ladder", _ladder(mid, n, a))
            costi.append((time.perf_counter() - a) * 1e6)
            if n % al_secondo == 0:
                ch.publish("order", {"bet_id": "B%d" % n, "status": "EXECUTABLE",
                                     "size_matched": 0.0, "t0": time.perf_counter()})
            if n % (5 * al_secondo) == 0:
                ch.publish("conto", {"modo": "live", "ordini": [{"bet_id": "B%d" % n}]})
            n += 1
        durata = time.perf_counter() - t_ini
        cpu = (time.process_time() - cpu0) / durata * 100.0
        time.sleep(0.5)
        stop.set()
        t_desk.join(timeout=2)
    reg.spegni(attesa_s=10.0)
    peso = reg.peso_cartella(cartella) if acceso else 0
    return {"acceso": acceso, "pubblicati": n, "secondi": durata, "ricevuti": ricevuti[0],
            "publish_us_p50": _q(costi, 50), "publish_us_p99": _q(costi, 99),
            "lat_ms_p50": _q(lat, 50), "lat_ms_p95": _q(lat, 95), "lat_ms_p99": _q(lat, 99),
            "cpu_pct": cpu, "byte_gz": peso, "conti": reg.conti() if acceso else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--secondi", type=float, default=10.0)
    ap.add_argument("--giri", type=int, default=2)
    ap.add_argument("--al-secondo", type=int, default=500, help="ladder al secondo in tutto")
    ap.add_argument("--cartella", required=True)
    a = ap.parse_args()
    base = Path(a.cartella)
    risultati = []
    for g in range(a.giri):
        for acceso in (False, True):
            r = fase(a.secondi, acceso, base / ("giro%d" % g), a.al_secondo)
            risultati.append(r)
            print(json.dumps({k: (round(v, 2) if isinstance(v, float) else v)
                              for k, v in r.items()}))
    acc = [r for r in risultati if r["acceso"]]
    spe = [r for r in risultati if not r["acceso"]]
    for nome, gruppo in (("SPENTO", spe), ("ACCESO", acc)):
        print("%s publish p50 %.1f us, p99 %.1f us; latenza p50 %.2f ms, p95 %.2f ms, "
              "p99 %.2f ms; CPU %.1f%%" % (
                  nome, statistics.median(r["publish_us_p50"] for r in gruppo),
                  statistics.median(r["publish_us_p99"] for r in gruppo),
                  statistics.median(r["lat_ms_p50"] for r in gruppo),
                  statistics.median(r["lat_ms_p95"] for r in gruppo),
                  statistics.median(r["lat_ms_p99"] for r in gruppo),
                  statistics.median(r["cpu_pct"] for r in gruppo)))
    byte_s = statistics.median(r["byte_gz"] / r["secondi"] for r in acc)
    print("PESO a %d msg/s: %.2f KB/s gzip = %.1f MB/ora = %.0f MB per 24 h di carico pieno"
          % (a.al_secondo, byte_s / 1024, byte_s * 3600 / 1048576, byte_s * 86400 / 1048576))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
