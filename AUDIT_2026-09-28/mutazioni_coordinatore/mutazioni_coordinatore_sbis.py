"""Mutazioni del COORDINATORE sul cantiere S-bis (sniper: chiusura doppia,
sostituto non agganciato, piatta dichiarata con ordini vivi, ultima spiaggia).

Ogni mutazione rompe UN punto del codice corretto: i test devono diventare
rossi. Il file si ripristina dalla copia in memoria e si controlla l'hash.
Si lancia dalla radice del worktree di verifica.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PY = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.venv\Scripts\python.exe"
F = "Betfair/stream/scalper/sniper_bot.py"
TEST = ["Betfair/stream/tests", "-k", "sniper or cantiere_s_bis"]

MUT: List[Tuple[str, bytes, bytes]] = [
    ("B1 flatten: parcheggio di una sequenza ritirato a ogni book",
     b"            if id(o) in in_seq:\n                continue",
     b"            if False:\n                continue"),
    ("B2 flatten: piatta dichiarata con ordini in volo o sequenze",
     b"            if in_volo or pos.submins:",
     b"            if False:"),
    ("B3 CAUSA: seconda chiusura con un ordine in Cancelling",
     b"        if any(self._vivo_o_in_volo(o) for o in pos.flatten_orders):",
     b"        if any(self._has_live(o) for o in pos.flatten_orders):"),
    ("B4 ultima spiaggia: accetta anche a prezzi assenti",
     b"        if base is None:\n            return False\n        g = compute_green(nw, nl, get_nearest_price(base))",
     b"        if base is None:\n            return True\n        g = compute_green(nw, nl, get_nearest_price(base))"),
    ("B5 ultima spiaggia: accetta una posizione piazzabile",
     b"        if float(g[1]) >= self._side_min(side) - _EPS:\n            return False",
     b"        if False:\n            return False"),
    ("B6 ordine rifiutato contato come chiusura partita",
     b"            if o is not None and getattr(o, \"status\", None) == OrderStatus.VIOLATION:\n                o = None",
     b"            if False:\n                o = None"),
    ("B7 sostituto del rimpiazzo non agganciato",
     b"            for x in list(getattr(tr, \"orders\", None) or []):\n                self._track(pos, x)",
     b"            for x in list(getattr(tr, \"orders\", None) or []):\n                pass"),
    ("B8 parcheggio morto: la sequenza resta appesa",
     b"                and not self._vivo_o_in_volo(entry[\"order\"])",
     b"                and False"),
    ("B9 in volo: REPLACING non conta",
     b"            OrderStatus.UPDATING, OrderStatus.REPLACING,",
     b"            OrderStatus.UPDATING,"),
    ("B10 in volo: CANCELLING non conta",
     b"            OrderStatus.EXECUTABLE, OrderStatus.PENDING, OrderStatus.CANCELLING,",
     b"            OrderStatus.EXECUTABLE, OrderStatus.PENDING,"),
    ("B11 chiusura bloccata: accettata in silenzio",
     b"            pos.chiusura_bloccata_detta = True\n            self._emit(\"flatten_bloccato\", level=\"CRITICAL\",",
     b"            pos.done = True\n            self._emit(\"flatten_bloccato\", level=\"CRITICAL\","),
]


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def suite() -> Tuple[bool, str]:
    r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider", "-x"],
                       capture_output=True, text=True, timeout=900)
    coda = [x for x in (r.stdout or "").splitlines() if x.strip()][-1:]
    return r.returncode == 0, (coda[0] if coda else "?")


def main() -> int:
    ok, coda = suite()
    print("BASE (senza mutazioni): %s  %s" % ("VERDE" if ok else "ROSSA", coda), flush=True)
    if not ok:
        return 2
    p = Path(F)
    orig = p.read_bytes()
    crlf = b"\r\n" in orig
    vive = 0
    for nome, prima, dopo in MUT:
        a = prima.replace(b"\n", b"\r\n") if crlf else prima
        d = dopo.replace(b"\n", b"\r\n") if crlf else dopo
        n = orig.count(a)
        if n != 1:
            print("%-62s ANCORA NON UNICA (%d)" % (nome, n), flush=True)
            vive += 1
            continue
        try:
            p.write_bytes(orig.replace(a, d))
            verde, coda = suite()
        finally:
            p.write_bytes(orig)
        assert md5(p.read_bytes()) == md5(orig)
        print("%-62s %s  %s" % (nome, "SOPRAVVISSUTA" if verde else "rossa", coda), flush=True)
        vive += 1 if verde else 0
    print("mutazioni sopravvissute o non applicate: %d su %d" % (vive, len(MUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
