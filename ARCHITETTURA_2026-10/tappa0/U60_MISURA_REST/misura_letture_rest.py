"""U-60: misura il tempo delle letture REST del DB che il banco imita con 120 ms.

SOLA LETTURA: solo GET su /rest/v1/<tabella>. Nessuna scrittura, nessuna RPC.
Le query sono quelle di `esposizione_fuori_bot.proprietari_bot` (la verifica
"del bot / fuori bot" che `ConfermaBanco` imita con LATENZA_LETTURA_S):
una select per ciascuna di omega_trades, safe_strategy_trades, mike_trades,
betfair_live_orders, betfair_live_order_requests, filtro mode=live e
bet_id in (...).

Due modi per ogni endpoint:
  nuova = urllib.request (apre una connessione NUOVA, TCP+TLS, a ogni GET)
  viva  = http.client keep-alive (una sola connessione; il bot di produzione
          tiene la sessione viva). Il GET di riscaldamento apre la connessione
          e viene scartato dalle statistiche (ma salvato nel grezzo).
Uso: python misura_letture_rest.py [--n 60] [--serie 2] [--attesa 300]
File ASCII-only, commenti in italiano.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import ssl
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from dotenv import load_dotenv

QUI = os.path.dirname(os.path.abspath(__file__))
ENV = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.env"
load_dotenv(ENV)
URL = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
CHIAVE = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
INTESTAZ = {"apikey": CHIAVE, "Authorization": "Bearer " + CHIAVE}
HOST = urllib.parse.urlparse(URL).netloc

# (nome, tabella, colonne) come in proprietari_bot
ENDPOINT = [
    ("omega_trades", "omega_trades", "bet_id"),
    ("safe_strategy_trades", "safe_strategy_trades", "bet_id"),
    ("mike_trades", "mike_trades", "bet_id"),
    ("betfair_live_orders", "betfair_live_orders", "bet_id,source"),
    ("betfair_live_order_requests", "betfair_live_order_requests", "bet_id,client_ref,params"),
]


def _get_urllib(percorso: str):
    t0 = time.perf_counter()
    req = urllib.request.Request(f"{URL}/rest/v1/{percorso}", headers=INTESTAZ)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            corpo = r.read()
            cod = r.status
    except urllib.error.HTTPError as e:
        corpo, cod = e.read(), e.code
    except Exception:  # noqa: BLE001 - errore di rete: campione KO (-1)
        corpo, cod = b"", -1
    return (time.perf_counter() - t0) * 1000.0, len(corpo), cod, corpo


class Viva:
    """Una connessione http.client keep-alive riusata; si riapre se cade."""

    def __init__(self):
        self.c = None
        self.aperture = 0

    def get(self, percorso: str):
        t0 = time.perf_counter()
        for tentativo in (0, 1):
            try:
                if self.c is None:
                    self.c = http.client.HTTPSConnection(HOST, timeout=30,
                                                         context=ssl.create_default_context())
                    self.aperture += 1
                self.c.request("GET", "/rest/v1/" + percorso, headers=INTESTAZ)
                r = self.c.getresponse()
                corpo = r.read()
                return (time.perf_counter() - t0) * 1000.0, len(corpo), r.status, corpo
            except Exception:  # noqa: BLE001 - connessione caduta: si riapre una volta
                try:
                    self.c.close()
                except Exception:  # noqa: BLE001
                    pass
                self.c = None
                if tentativo:
                    return (time.perf_counter() - t0) * 1000.0, 0, -1, b""
        return 0.0, 0, -1, b""


def _query(tabella, colonne, ids):
    lista = ",".join(ids)
    return f"{tabella}?select={colonne}&mode=eq.live&bet_id=in.({lista})"


def _id_reali():
    """Un bet_id vero (se c'e') da safe_strategy_trades: solo per dare al filtro
    la forma di produzione (1 bet_id). Una GET in piu', fuori dalle statistiche."""
    try:
        _, _, cod, corpo = _get_urllib("safe_strategy_trades?select=bet_id&mode=eq.live"
                                       "&bet_id=not.is.null&limit=1")
        if cod == 200:
            r = json.loads(corpo)
            if r and r[0].get("bet_id"):
                return [str(r[0]["bet_id"])]
    except Exception:  # noqa: BLE001
        pass
    return []


def percentile(v, p):
    """Rango piu' vicino su lista ordinata."""
    s = sorted(v)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * len(s) + 0.5)) - 1))
    return s[k]


def serie(num, n, pausa, ids, f):
    viva = Viva()
    ini = datetime.now().astimezone().isoformat(timespec="milliseconds")
    print(f"[serie {num}] inizio {ini}", flush=True)
    # riscaldamento: un GET per endpoint su ciascun modo, scartato
    for nome, tab, col in ENDPOINT:
        q = _query(tab, col, ids)
        for modo, fn in (("nuova", _get_urllib), ("viva", viva.get)):
            ms, by, cod, _ = fn(q)
            f.write(json.dumps({"serie": num, "modo": modo, "endpoint": nome, "ms": round(ms, 2),
                                "byte": by, "http": cod, "riscaldamento": True}) + "\n")
            time.sleep(0.25)
    for i in range(n):
        for nome, tab, col in ENDPOINT:
            q = _query(tab, col, ids)
            for modo, fn in (("nuova", _get_urllib), ("viva", viva.get)):
                ms, by, cod, _ = fn(q)
                f.write(json.dumps({"serie": num, "modo": modo, "endpoint": nome, "i": i,
                                    "ms": round(ms, 2), "byte": by, "http": cod,
                                    "riscaldamento": False,
                                    "t": datetime.now().astimezone().isoformat(timespec="milliseconds")}) + "\n")
                f.flush()
                time.sleep(pausa)
    fine = datetime.now().astimezone().isoformat(timespec="milliseconds")
    print(f"[serie {num}] fine {fine} (connessioni vive aperte: {viva.aperture})", flush=True)


def riepilogo(percorso):
    righe = [json.loads(x) for x in open(percorso, encoding="utf-8")]
    out = []
    for m in ("nuova", "viva"):
        tutti = []
        for e in [x[0] for x in ENDPOINT]:
            g = [r for r in righe if r["modo"] == m and r["endpoint"] == e and not r["riscaldamento"]]
            tutti += g
            out.append((m, e, g))
        out.append((m, "TUTTI", tutti))
    print("modo   endpoint                         N(ok)  non200  p50    p90    p99    min    max   byte")
    for m, e, g in out:
        ok = [r["ms"] for r in g if r["http"] == 200]
        if not ok:
            print(m, e, "nessun 200", sorted({r["http"] for r in g}))
            continue
        print(f"{m:6s} {e:30s} {len(ok):5d} {len(g) - len(ok):6d} {percentile(ok, 50):6.1f} "
              f"{percentile(ok, 90):6.1f} {percentile(ok, 99):6.1f} {min(ok):6.1f} {max(ok):6.1f} "
              f"{statistics.mean(r['byte'] for r in g):7.0f}")
    rw = [r for r in righe if r["riscaldamento"]]
    for m in ("nuova", "viva"):
        v = [r["ms"] for r in rw if r["modo"] == m and r["http"] == 200]
        if v:
            print(f"riscaldamento {m}: n={len(v)} primo={v[0]:.1f} ms mediana={statistics.median(v):.1f}")
    nonok = sorted({(r["endpoint"], r["http"]) for r in righe if r["http"] != 200})
    print("risposte non 200:", nonok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--serie", type=int, default=2)
    ap.add_argument("--attesa", type=int, default=300)
    ap.add_argument("--pausa", type=float, default=0.3)
    ap.add_argument("--riepilogo", default="")
    a = ap.parse_args()
    if a.riepilogo:
        riepilogo(a.riepilogo)
        return
    ids = _id_reali()
    print("bet_id di prova reale trovato:", bool(ids), flush=True)
    ids = ids or ["0000000000"]
    percorso = os.path.join(QUI, "misure_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".jsonl")
    with open(percorso, "w", encoding="utf-8") as f:
        for s in range(1, a.serie + 1):
            if s > 1:
                print(f"attesa {a.attesa} s", flush=True)
                time.sleep(a.attesa)
            serie(s, a.n, a.pausa, ids, f)
    print("grezzo:", percorso)
    riepilogo(percorso)


if __name__ == "__main__":
    main()
