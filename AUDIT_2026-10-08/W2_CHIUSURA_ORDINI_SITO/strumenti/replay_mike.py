"""Replay PRIMA (worker di b5547eb) / DOPO (worker nuovo) di Omega sul canale
(porta vera -> motore ordini -> live_order_worker._dispatch), --worker 1.
Il worker viene rimesso com'era, verificato con sha256."""
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import time

W = '/home/user/python-database-automation/.claude/worktrees/agent-a1c21d4fd7008caf6/'
OUT = W + 'AUDIT_2026-10-08/W2_CHIUSURA_ORDINI_SITO/'
F = W + 'Betfair/stream/live_order_worker.py'
os.makedirs(OUT, exist_ok=True)

for ev in ("35760084",):
    dst = os.path.join(W, "_live_raw", ev)
    os.makedirs(dst, exist_ok=True)
    src = os.path.join(W, "registrazioni_banco", ev)
    for nome in os.listdir(src):
        if nome.endswith(".gz"):
            with gzip.open(os.path.join(src, nome), "rb") as a, \
                    open(os.path.join(dst, nome[:-3]), "wb") as b:
                shutil.copyfileobj(a, b)
        else:
            shutil.copy(os.path.join(src, nome), dst)


def sha():
    return hashlib.sha256(open(F, 'rb').read()).hexdigest()


nuovo = open(F).read()
sha_nuovo = sha()
head = subprocess.run(['git', '-C', W, 'show', 'b5547eb:Betfair/stream/live_order_worker.py'],
                      capture_output=True, text=True, check=True).stdout
CMD = [sys.executable, '-m', 'Betfair.stream.backtest.certifica', 'mike', '35760084',
       '--trasporto', 'canale', '--worker', '1']


def gira(nome, sorgente):
    open(F, 'w').write(sorgente)
    t0 = time.time()
    r = subprocess.run(CMD, cwd=W, capture_output=True, text=True, timeout=3000)
    dt = time.time() - t0
    open(OUT + f'mike_canale_{nome}.txt', 'w').write(r.stdout)
    open(OUT + f'mike_canale_{nome}.err', 'w').write(r.stderr[-20000:])
    print(f"{nome}: exit {r.returncode}, {dt:.1f} s", flush=True)


try:
    gira('prima', head)
    gira('dopo', nuovo)
finally:
    open(F, 'w').write(nuovo)
assert sha() == sha_nuovo
print("worker ripristinato", sha())
print(subprocess.run(['uptime'], capture_output=True, text=True).stdout)
