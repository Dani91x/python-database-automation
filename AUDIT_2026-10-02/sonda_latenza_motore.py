"""Sonda del revisore (02/10): la latenza comando->place del motore (test esistente
``test_latenza_logica_comando_place_sotto_20_ms``), base contro patch, alternate N volte.
Uso: python sonda_latenza_motore.py <dir_base> <dir_patch> [N]"""
import re
import subprocess
import sys

T = "Betfair/stream/tests/test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms"
base, patch = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
for i in range(n):
    for nome, d in (("base", base), ("patch", patch)):
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-s", "-p", "no:cacheprovider", T],
                           cwd=d, capture_output=True, text=True)
        m = re.search(r"p50=([0-9.]+) ms p95=([0-9.]+) ms max=([0-9.]+)", r.stdout)
        print(i, nome, m.groups() if m else r.stdout[-200:], "rc", r.returncode, flush=True)
