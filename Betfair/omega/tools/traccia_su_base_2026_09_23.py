"""Ricalcola la traccia di parita' con ``omega_service.py`` di BASE (``git show
HEAD:...``) SENZA toccare il file del worktree: il sorgente di base viene
eseguito come modulo ``Betfair.omega.omega_service`` prima di ogni altro import
di Omega. Deve stampare ``BASE == TRACCIA: True``.

    python -m Betfair.omega.tools.traccia_su_base_2026_09_23
"""
from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import Betfair.omega

NOME = "Betfair.omega.omega_service"


def main() -> int:
    radice = Path(__file__).resolve().parents[3]
    sorgente = subprocess.check_output(
        ["git", "show", "HEAD:Betfair/omega/omega_service.py"], cwd=str(radice))
    mod = types.ModuleType(NOME)
    mod.__file__ = str(radice / "Betfair" / "omega" / "omega_service.py")
    mod.__package__ = "Betfair.omega"
    sys.modules[NOME] = mod
    exec(compile(sorgente, mod.__file__, "exec"), mod.__dict__)  # noqa: S102
    Betfair.omega.omega_service = mod
    from Betfair.omega.tests import traccia_canale_scan_2026_09_23 as T

    if hasattr(mod, "_CLIENT_SCAN"):
        print("ERRORE: non e' il codice di base")
        return 2
    uguale = T.calcola() == json.loads(T.GOLDEN.read_text(encoding="ascii"))
    print("BASE == TRACCIA:", uguale)
    return 0 if uguale else 1


if __name__ == "__main__":
    sys.exit(main())
