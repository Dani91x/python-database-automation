"""I due test di latenza (<20 ms) col worker di b5547eb e col worker nuovo, sulla
stessa macchina carica, alternati. Ripristino verificato con sha256."""
import hashlib
import subprocess
import sys

W = '/home/user/python-database-automation/.claude/worktrees/agent-a1c21d4fd7008caf6/'
F = W + 'Betfair/stream/live_order_worker.py'
TESTS = ["Betfair/stream/tests/test_auto_follow_2026_09_25.py::test_latenza_logica_aggancio_sotto_i_20_ms",
         "Betfair/stream/tests/test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms"]


def sha():
    return hashlib.sha256(open(F, 'rb').read()).hexdigest()


nuovo = open(F).read()
sha_nuovo = sha()
head = subprocess.run(['git', '-C', W, 'show', 'b5547eb:Betfair/stream/live_order_worker.py'],
                      capture_output=True, text=True, check=True).stdout


def giro():
    r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *TESTS],
                       cwd=W, capture_output=True, text=True, timeout=600)
    return [l for l in r.stdout.splitlines() if 'passed' in l or 'failed' in l][-1]


try:
    for i in range(4):
        open(F, 'w').write(head)
        print("HEAD ", giro(), flush=True)
        open(F, 'w').write(nuovo)
        print("NUOVO", giro(), flush=True)
finally:
    open(F, 'w').write(nuovo)
assert sha() == sha_nuovo
print("ripristinato", sha())
print(subprocess.run(['uptime'], capture_output=True, text=True).stdout)
