"""W1-B - importare il comparto B non apre file, socket o thread (brief comune, regola 7).

In un interprete NUOVO (sottoprocesso vero) si installa un audit hook
(``sys.addaudithook``) e si importano tutti i moduli del comparto: nessun
``open`` di file che non sia codice Python, nessun ``socket.*``, nessun thread
nuovo. Il test e' falsificabile: un import di ``betfair_inplay`` in testa a
``calcolo.py`` (che tira dentro ``urllib3``, che crea un socket di prova IPv6)
lo fa diventare rosso.
"""
from __future__ import annotations

import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

MODULI = [
    "Betfair.nucleo.stato_partita.calcolo",
    "Betfair.nucleo.stato_partita.freschezza",
    "Betfair.nucleo.stato_partita.servizio",
    "Betfair.nucleo.stato_partita.adattatori.lettura",
    "Betfair.nucleo.stato_partita.adattatori.ips",
    "Betfair.nucleo.stato_partita.adattatori.ips_tennis",
    "Betfair.nucleo.stato_partita.adattatori.api_football",
    "Betfair.nucleo.stato_partita.adattatori.registrazione",
    "Betfair.nucleo.stato_partita.adattatori.canale",
]

SONDA = r"""
import sys, threading
eventi = []
CODICE = (".py", ".pyc", ".so", ".pth")
def sonda(nome, args):
    if nome == "open":
        p = str(args[0])
        if not p.endswith(CODICE) and "__pycache__" not in p and not os_path_isdir(p):
            eventi.append(("open", p))
    elif nome.startswith("socket."):
        eventi.append((nome, ""))
def os_path_isdir(p):
    import os
    try:
        return os.path.isdir(p)
    except Exception:
        return False
prima = threading.active_count()
sys.addaudithook(sonda)
import importlib
for m in sys.argv[1:]:
    importlib.import_module(m)
print("EVENTI", eventi)
print("THREAD", threading.active_count() - prima)
"""


def test_import_del_comparto_b_non_apre_niente() -> None:
    res = subprocess.run([sys.executable, "-c", SONDA, *MODULI], cwd=RADICE,
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    righe = dict(r.split(" ", 1) for r in res.stdout.strip().splitlines())
    assert righe["EVENTI"] == "[]", righe["EVENTI"]
    assert righe["THREAD"] == "0"
