"""Lancia UN replay dal punto d'ingresso unico (``Betfair.stream.backtest.certifica``) con
il tetto di 900 s (equivalente di ``timeout 900``): oltre, il processo e' ucciso e il
referto lo dice. Scrive comando, uscita completa, codice e durata nel file indicato.
ASCII-only.

Uso: python replay_con_tetto.py <referto.txt> <argomenti di certifica...>
"""
import os
import subprocess
import sys
import time

TETTO_S = 900

referto, argomenti = sys.argv[1], sys.argv[2:]
cmd = [sys.executable, "-m", "Betfair.stream.backtest.certifica", *argomenti]
env = dict(os.environ, PYTHONIOENCODING="utf-8")
t0 = time.time()
with open(referto, "w", encoding="utf-8") as f:
    f.write("comando: python -m Betfair.stream.backtest.certifica " + " ".join(argomenti) + "\n")
    f.flush()
    try:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, timeout=TETTO_S)
        codice = r.returncode
    except subprocess.TimeoutExpired:
        codice = "TETTO_900_S_SUPERATO"
    f.write(f"exit={codice} durata={round(time.time() - t0)}s\n")
print(f"exit={codice} durata={round(time.time() - t0)}s")
