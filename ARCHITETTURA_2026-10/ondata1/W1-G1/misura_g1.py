"""misura_g1.py - misure dell'archivio locale e del postino di W1-G1 (stesso metodo di ``m06``).

Scrive SOLO in <cartella_tmp> (da passare; il chiamante la cancella). Nessuna rete: il cloud e'
il PostgREST finto dei test dietro il client supabase VERO (httpx.MockTransport).

Misure:
  A. ArchivioLocale vero, 3 regimi: latenza di ACCODAMENTO (paga il chiamante), di COMMIT (thread
     di scrittura) e «durevole dopo» (accodamento -> commit), p50/p95/p99/max, N record x R ripetizioni;
  B. checkpoint: nel commit (wal_autocheckpoint=1000, il default misurato da m06) contro il thread di
     manutenzione (wal_autocheckpoint=0 + PASSIVE ogni 1 s): massimo del commit del vivo;
  C. U-55, un file contro due: commit del denaro (FULL) mentre il vivo (NORMAL) scrive lotti da 100,
     stesso thread, sullo STESSO file contro file SEPARATI (laboratorio sqlite3 puro, come m06);
  D. R08 (sostituto di laboratorio della prova sotto carico di T8): un ciclo di «decisione» CPU
     (json.dumps di un ladder + calcolo) misura il suo giro con scrittore e postino SPENTI (due volte:
     variabilita') e ACCESI (scrittura a cadenza + drenaggio verso il cloud finto).
Uso: python misura_g1.py <cartella_tmp> [N=3000] [R=3]
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import statistics
import sys
import threading
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RADICE))
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

from Betfair.nucleo.dati.archivio import ArchivioLocale, _percentili  # noqa: E402
from Betfair.nucleo.dati.postino import PostinoLocale  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, CloudProva, PostgrestFinto  # noqa: E402

TMP = Path(sys.argv[1])
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
R = int(sys.argv[3]) if len(sys.argv) > 3 else 3
PAD = "x" * 110          # riga JSON di ~190 byte come m06


def riga(i: int) -> dict:
    return {"kind": "giro", "event_id": "35760084", "payload": {"i": i, "p": PAD}}


def riga_ordine(i: int) -> dict:
    return {"mode": "paper", "client_order_ref": f"r{i}", "market_id": "1.234", "selection_id": 47972, "side": "back",
            "price": 2.0, "size": 2.0, "status": "EXECUTABLE", "updated_at": "2026-10-09T10:00:00+00:00"}


def riga_vivo(i: int) -> dict:
    return {"event_id": f"e{i}", "home_name": "A", "away_name": "B", "status": "STREAMING", "open_date": PAD[:20],
            "updated_at": "2026-10-09T10:00:00+00:00"}


def fmt(d: dict) -> str:
    if not d.get("n"):
        return "n=0"
    return "n=%d p50=%.1f p95=%.1f p99=%.1f max=%.1f" % (d["n"], d["p50"], d["p95"], d["p99"], d["max"])


def pulisci(p: Path) -> None:
    shutil.rmtree(p, ignore_errors=True)


# ---------------------------------------------------------------------------
def misura_a(rep: int, esterno: bool) -> dict:
    base = TMP / f"a{rep}_{int(esterno)}"
    pulisci(base)
    a = ArchivioLocale("misura", SPEC, base=base, checkpoint_esterno=esterno, checkpoint_ogni_s=0.2).apri()
    out = {}
    for tab, fn in (("betfair_live_orders", riga_ordine), ("live_follow", riga_vivo), ("mike_activity", riga)):
        a._lat_accoda.clear()
        t0 = time.perf_counter()
        for i in range(N):
            a.scrivi(tab, fn(i))
        accodato = time.perf_counter() - t0
        assert a.conferma(120)
        durata = time.perf_counter() - t0
        out[tab] = {"accodamento": _percentili(x / 1000 for x in a._lat_accoda), "rec_s_accodamento": N / accodato,
                    "rec_s_durevole": N / durata}
    m = a.misure()
    out["commit"] = m["commit_us"]
    out["durevole"] = m["durevole_dopo_us"]
    out["checkpoint"] = m["checkpoint_us"]
    a.chiudi()
    out["disco_mb"] = sum(f.stat().st_size for f in base.rglob("*") if f.is_file()) / 1048576
    pulisci(base)
    return out


# ---------------------------------------------------------------------------
def misura_c(due_file: bool) -> dict:
    base = TMP / ("c2" if due_file else "c1")
    pulisci(base)
    base.mkdir(parents=True)

    def conn(nome: str, sync: str) -> sqlite3.Connection:
        c = sqlite3.connect(base / nome, isolation_level=None)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(f"PRAGMA synchronous={sync}")
        c.execute("CREATE TABLE IF NOT EXISTS t%s (i INTEGER PRIMARY KEY, j TEXT)" % sync)
        return c

    d = conn("denaro.db" if due_file else "unico.db", "FULL")
    v = conn("vivo.db" if due_file else "unico.db", "NORMAL")
    lat = []
    j = json.dumps(riga(0))
    k = 0
    for i in range(N // 3):
        t = time.perf_counter()
        d.execute("BEGIN")
        d.execute("INSERT INTO tFULL VALUES (?, ?)", (i, j))
        d.execute("COMMIT")
        lat.append(time.perf_counter() - t)
        if i % 3 == 0:
            v.execute("BEGIN")
            v.executemany("INSERT INTO tNORMAL VALUES (?, ?)", [(k + x, j) for x in range(100)])
            v.execute("COMMIT")
            k += 100
    d.close()
    v.close()
    pulisci(base)
    return _percentili(x * 1e6 for x in lat)


# ---------------------------------------------------------------------------
def ladder() -> dict:
    return {"marketId": "1.234", "rc": [{"id": s, "batb": [[p, 1.0 + p / 10, 10.0 * p] for p in range(10)],
                                         "batl": [[p, 1.1 + p / 10, 9.0 * p] for p in range(10)]} for s in range(3)]}


def ciclo_decisione(secondi: float, ferma: threading.Event, lat: list) -> None:
    lad = ladder()
    fine = time.perf_counter() + secondi
    while time.perf_counter() < fine and not ferma.is_set():
        t = time.perf_counter()
        s = json.dumps(lad)
        x = sum(len(s) * k for k in range(200))
        lat.append(time.perf_counter() - t)
        if x < 0:
            break
        time.sleep(0.002)


def misura_d(acceso: bool, secondi: float = 6.0, pausa_s: float = 0.002) -> dict:
    base = TMP / f"d{int(acceso)}_{time.time_ns()}"
    lat: list = []
    ferma = threading.Event()
    th = threading.Thread(target=ciclo_decisione, args=(secondi, ferma, lat))
    a = p = None
    if acceso:
        a = ArchivioLocale("misura", SPEC, base=base).apri()
        p = PostinoLocale(a, CloudProva(PostgrestFinto()))
        p.avvia(intervallo_s=0.05)
    th.start()
    i = 0
    fine = time.perf_counter() + secondi
    while acceso and time.perf_counter() < fine:
        a.scrivi("mike_activity", riga(i))                      # ~500 righe/s: sopra ogni carico misurato (07 par. 4)
        if i % 5 == 0:
            a.scrivi("betfair_live_orders", riga_ordine(i))
        i += 1
        time.sleep(pausa_s)
    th.join()
    if acceso:
        p.ferma()
        a.chiudi()
    pulisci(base)
    out = _percentili(x * 1e6 for x in lat)
    out["giri_al_s"] = len(lat) / secondi                   # cadenza del ciclo: la sveglia dopo sleep paga il GIL
    return out


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    print("# misura_g1: N=%d record per tabella, %d ripetizioni, cartella %s" % (N, R, TMP))
    print("\n## A. archivio vero (checkpoint nel thread di manutenzione): microsecondi")
    for r in range(R):
        o = misura_a(r, True)
        for tab in ("betfair_live_orders", "live_follow", "mike_activity"):
            print("rep%d %-20s accodamento %s | rec/s accodamento %.0f, durevole %.0f" % (
                r + 1, tab, fmt(o[tab]["accodamento"]), o[tab]["rec_s_accodamento"], o[tab]["rec_s_durevole"]))
        for reg in ("stato_denaro", "stato_vivo", "log"):
            print("rep%d commit %-13s %s | durevole dopo %s" % (r + 1, reg, fmt(o["commit"][reg]), fmt(o["durevole"][reg])))
        print("rep%d checkpoint %s | disco %.2f MB" % (r + 1, fmt(o["checkpoint"]), o["disco_mb"]))
    print("\n## B. checkpoint NEL commit (wal_autocheckpoint=1000, default)")
    for r in range(R):
        o = misura_a(r, False)
        for reg in ("stato_denaro", "stato_vivo"):
            print("rep%d commit %-13s %s" % (r + 1, reg, fmt(o["commit"][reg])))
    print("\n## C. U-55: commit del denaro (FULL) con il vivo a lotti da 100 nello stesso thread")
    for r in range(R):
        print("rep%d UN file  %s" % (r + 1, fmt(misura_c(False))))
        print("rep%d DUE file %s" % (r + 1, fmt(misura_c(True))))
    print("\n## D. R08 laboratorio: giro di decisione (json.dumps ladder + calcolo), microsecondi")
    for r in range(R):
        for etichetta, acceso, pausa in (("spento #1", False, 0.002), ("spento #2", False, 0.002),
                                         ("ACCESO 600 righe/s", True, 0.002), ("ACCESO 60 righe/s", True, 0.02)):
            d = misura_d(acceso, pausa_s=pausa)
            print("rep%d %-19s %s | giri/s %.0f" % (r + 1, etichetta, fmt(d), d["giri_al_s"]))


if __name__ == "__main__":
    main()
