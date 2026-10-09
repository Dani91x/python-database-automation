"""W1-C1 - importare i moduli della porta non ha effetti collaterali (brief comune par. 1
regola 7) e rispetta le dipendenze ammesse (04 par. 2.3): niente thread, niente file
aperti, niente rete, niente supabase, e il runner di oggi (``motore_ordini``,
``live_order_worker``, flumine) NON si carica all'import: solo dentro le funzioni."""
from __future__ import annotations

import subprocess
import sys
import textwrap


def test_import_senza_effetti_e_senza_il_runner() -> None:
    codice = textwrap.dedent("""
        import os, sys, threading
        fd0 = set(os.listdir('/proc/self/fd')) if os.path.isdir('/proc/self/fd') else set()
        th0 = set(threading.enumerate())
        import Betfair.nucleo.ordini.porta
        import Betfair.nucleo.ordini.eventi
        import Betfair.nucleo.ordini.controlli
        import Betfair.nucleo.ordini.minimi
        import Betfair.nucleo.ordini.adattatore_comando
        import Betfair.nucleo.ordini.esecutori.runner
        fd1 = set(os.listdir('/proc/self/fd')) if os.path.isdir('/proc/self/fd') else set()
        vietati = [m for m in ("Betfair.stream.motore_ordini", "Betfair.stream.live_order_worker",
                               "flumine", "supabase", "db_client", "requests")
                   if m in sys.modules]
        print(len(set(threading.enumerate()) - th0), len(fd1 - fd0), vietati)
    """)
    r = subprocess.run([sys.executable, "-c", codice], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "0 0 []", r.stdout
