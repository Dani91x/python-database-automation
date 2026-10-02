"""Misura A/B di UNO scenario nello stesso processo: memorie del replay veloce
SPENTE (A, la via di prima) e ACCESE (B), alternate, con tempo di parete e tempo
di CPU del processo (meno sensibile al carico delle altre sessioni). Stampa anche
tick/decisioni/azioni/violazioni di ogni giro: devono essere uguali fra A e B.
Uso: python AUDIT_2026-10-02/misura_ab.py BOT EVENTO SCENARIO DATA_DIR [GIRI]
"""
import logging
import sys
import time

from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest import certifica as C

INTERRUTTORI = [n for n in ("RIUSA_LIBRO_CHIUSO", "RIUSA_LAPSE", "CHIUSURA_SENZA_RESOCONTI_MUTI")
                if hasattr(B, n)]
if len(sys.argv) > 6:
    INTERRUTTORI = [n for n in INTERRUTTORI if n in sys.argv[6].split(",")]


def giro(acceso: bool, compito):
    for n in INTERRUTTORI:
        setattr(B, n, acceso)
    t0, c0 = time.perf_counter(), time.process_time()
    r, _mem = C._lavora(compito)
    return (time.perf_counter() - t0, time.process_time() - c0,
            (r.tick, r.decisioni, r.azioni, len(r.violazioni), tuple(r.stati_visti)))


def main():
    bot, ev, sc, data_dir = sys.argv[1:5]
    giri = int(sys.argv[5]) if len(sys.argv) > 5 else 2
    logging.basicConfig(level=logging.WARNING)
    compito = (bot, ev, data_dir, sc, 0, 0, None)
    C._lavora(compito)          # riscaldamento: import e cache di processo
    print("interruttori:", ", ".join(INTERRUTTORI))
    a, b = [], []
    for _ in range(giri):
        for acceso, dove in ((False, a), (True, b)):
            parete, cpu, numeri = giro(acceso, compito)
            dove.append((parete, cpu, numeri))
            print(f"{'B acceso' if acceso else 'A spento'}: parete {parete:6.1f} s  "
                  f"cpu {cpu:6.1f} s  {numeri[:4]}", flush=True)
    uguali = len({x[2] for x in a + b}) == 1
    ma = sum(x[1] for x in a) / len(a)
    mb = sum(x[1] for x in b) / len(b)
    print(f"CPU media A {ma:.1f} s, B {mb:.1f} s, guadagno {100 * (ma - mb) / ma:.1f} % | "
          f"numeri identici fra tutti i giri: {uguali}")


if __name__ == "__main__":
    main()
