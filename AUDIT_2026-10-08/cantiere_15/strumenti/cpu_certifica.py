"""Lancia `python -m Betfair.stream.backtest.certifica <argomenti>` nella cartella
corrente e stampa il TEMPO CPU (user+sys del figlio) oltre al tempo di parete: con
la macchina condivisa e carica il tempo di parete non misura il codice.

Uso: python3 cpu_certifica.py <file_uscita> <argomenti di certifica...>
"""
import resource
import subprocess
import sys
import time

out = sys.argv[1]
t0 = time.perf_counter()
with open(out, "w") as f:
    r = subprocess.run([sys.executable, "-m", "Betfair.stream.backtest.certifica", *sys.argv[2:]],
                       stdout=f, stderr=subprocess.DEVNULL)
parete = time.perf_counter() - t0
ru = resource.getrusage(resource.RUSAGE_CHILDREN)
print("exit=%d parete=%.1fs cpu_user=%.1fs cpu_sys=%.1fs cpu_tot=%.1fs" % (
    r.returncode, parete, ru.ru_utime, ru.ru_stime, ru.ru_utime + ru.ru_stime))
