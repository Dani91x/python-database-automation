"""FALSIFICAZIONE A LIVELLO DI REPLAY (30/09, P&L REALE DEL CONTO).

Mutazione M2 (il P&L della partita resta il calcolo interno di Mike, senza gli
ordini dell'utente) sul codice di produzione; scenario ``chiuso-fuori-app`` sulla
coda (Mike in LIVE, l'utente chiude con ordini VERI su flumine): il controllo
RG1 del banco (P&L della partita = conto del banco, ordini dell'utente compresi)
DEVE diventare rosso. Il file si ripristina SEMPRE dalla copia (try/finally) e
si verifica byte per byte. Mai interromperlo a meta'. ASCII-only.

Uso (radice del worktree, ambiente NEUTRO):
    bash _pnl_scratch/neutro.sh .venv/Scripts/python.exe \
        AUDIT_2026-09-30/falsifica_pnl_reale_conto_replay.py <data-dir> <file di uscita>
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = os.path.join(RADICE, ".venv", "Scripts", "python.exe")
SVC = os.path.join(RADICE, "Betfair", "mike", "service.py")
VERO = b'            ctx.settled_pnl = float(conto["netto_conto"])'
MUTATO = b'            pass  # MUTAZIONE M2'


def main() -> int:
    data_dir, uscita = sys.argv[1], sys.argv[2]
    copia = open(SVC, "rb").read()
    impronta = hashlib.sha256(copia).hexdigest()
    if copia.count(VERO) != 1:
        print("mutazione non applicabile")
        return 2
    try:
        open(SVC, "wb").write(copia.replace(VERO, MUTATO))
        with open(uscita, "wb") as out:
            rc = subprocess.run([PY, "-m", "Betfair.stream.backtest.certifica", "mike", "35760084",
                                 "--scenari", "chiuso-fuori-app", "--trasporto", "coda",
                                 "--worker", "0", "--data-dir", data_dir],
                                cwd=RADICE, stdout=out, stderr=subprocess.STDOUT).returncode
    finally:
        open(SVC, "wb").write(copia)
    ok = hashlib.sha256(open(SVC, "rb").read()).hexdigest() == impronta
    print(f"certifica uscita {rc} | service.py ripristinato: {ok}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
