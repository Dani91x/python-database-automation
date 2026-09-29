"""Mutazioni del COORDINATORE sul cantiere S (scalper calcio: chiusura doppia,
sostituto non agganciato, close ritirata, ultima spiaggia).

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
F = "Betfair/stream/scalper/scalper_bot.py"
TEST = ["Betfair/stream/tests", "-k", "scalper or cantiere_s"]

MUT: List[Tuple[str, bytes, bytes]] = [
    ("S1 sorveglianza DONE: l'ordine in volo non tiene lo slot",
     b"                still = [o for o in live if self._vivo_o_in_volo(o)]",
     b"                still = [o for o in live if self._has_live(o)]"),
    ("S2 LOCKING: la close corrente viene di nuovo ritirata",
     b"                if id(o) in tenute:",
     b"                if False:"),
    ("S3 cancel chiesto = cancel eseguito (reset troppo presto)",
     b"        elif not any(self._vivo_o_in_volo(o) for o in legs):",
     b"        elif not any(self._has_live(o) for o in legs):"),
    ("S4 flatten: DONE a posizione piatta con ordini in volo",
     b"            if in_volo or slot.submins:",
     b"            if False:"),
    ("S5 flatten: il parcheggio orfano si aspetta per sempre",
     b"            if (p >= 999.0 or p <= 1.011) and id(o) in in_seq:",
     b"            if (p >= 999.0 or p <= 1.011):"),
    ("S6 CAUSA RADICE: seconda chiusura col parcheggio in Cancelling",
     b"        if any(self._vivo_o_in_volo(o) for o in slot.flatten_orders):",
     b"        if any(self._has_live(o) for o in slot.flatten_orders):"),
    ("S7 flatten: sequenza avviata letta come residuo da accettare",
     b"        elif slot.submins:\n            # CANTIERE S (29/09, gemello del cantiere T): `_place_exact` torna",
     b"        elif False:\n            # CANTIERE S (29/09, gemello del cantiere T): `_place_exact` torna"),
    ("S8 ultima spiaggia: accetta anche a prezzi assenti",
     b"        if base is None:\n            return False\n        g = compute_green(net_win, net_lose, get_nearest_price(base))",
     b"        if base is None:\n            return True\n        g = compute_green(net_win, net_lose, get_nearest_price(base))"),
    ("S9 ultima spiaggia: accetta una posizione piazzabile",
     b"        if size >= self._side_min(side) - _EPS:\n            return False",
     b"        if False:\n            return False"),
    ("S10 sostituto del rimpiazzo non agganciato",
     b"            for x in list(getattr(tr, \"orders\", None) or []):\n                self._track(slot, x)",
     b"            for x in list(getattr(tr, \"orders\", None) or []):\n                pass"),
    ("S11 parcheggio morto: la sequenza resta appesa",
     b"                and not self._vivo_o_in_volo(entry[\"order\"])",
     b"                and False"),
    ("S12 in volo: REPLACING non conta",
     b"            OrderStatus.UPDATING, OrderStatus.REPLACING,",
     b"            OrderStatus.UPDATING,"),
    ("S13 in volo: CANCELLING non conta",
     b"            OrderStatus.EXECUTABLE, OrderStatus.PENDING, OrderStatus.CANCELLING,",
     b"            OrderStatus.EXECUTABLE, OrderStatus.PENDING,"),
    ("S14 LOCKING: ciclo pari chiuso con ordini vivi",
     b"                elif (slot.submins\n                      or any(self._vivo_o_in_volo(o) for o in slot.flatten_orders)):",
     b"                elif False:"),
    ("S15 chiusura bloccata: torna il DONE silenzioso",
     b"                slot.chiusura_bloccata_detta = True\n                self._emit(\"flatten_bloccato\", level=\"CRITICAL\",",
     b"                slot.status = DONE\n                self._emit(\"flatten_bloccato\", level=\"CRITICAL\","),
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
