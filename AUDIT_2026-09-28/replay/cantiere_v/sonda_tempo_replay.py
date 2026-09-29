"""Sonda del COORDINATORE: dove passa il tempo il replay dello scalper calcio.

Lancia il banco vero (`certifica.main`) sotto cProfile e lo interrompe dopo
SECONDI secondi: stampa le funzioni piu' care. Non scrive niente nel repo.
Uso: python sonda_tempo_replay.py SECONDI SCENARIO
"""
from __future__ import annotations

import _thread
import cProfile
import io
import pstats
import sys
import threading
import time


def main() -> int:
    secondi = float(sys.argv[1])
    scenario = sys.argv[2]
    data_dir = sys.argv[3]
    sys.argv = ["certifica", "scalper_calcio", "35797769", "--scenari", scenario,
                "--worker", "1", "--data-dir", data_dir]
    from Betfair.stream.backtest import certifica

    threading.Timer(secondi, _thread.interrupt_main).start()
    pr = cProfile.Profile()
    t0 = time.time()
    try:
        pr.enable()
        certifica.main()
    except KeyboardInterrupt:
        pass
    finally:
        pr.disable()
    print("durata misurata: %.0f s" % (time.time() - t0))
    for chiave in ("tottime", "cumulative"):
        s = io.StringIO()
        pstats.Stats(pr, stream=s).strip_dirs().sort_stats(chiave).print_stats(45)
        print("=" * 30, chiave)
        print(s.getvalue()[:9000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
