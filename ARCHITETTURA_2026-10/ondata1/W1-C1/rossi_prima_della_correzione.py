"""I test nuovi della revisione sul codice CONSEGNATO (0b4f2b59): devono essere rossi.
Rimette i moduli di 0b4f2b59, lancia i test, ripristina i moduli correnti (sha256)."""
import hashlib
import subprocess
import sys
from pathlib import Path

R = Path(sys.argv[1])
MODULI = ["Betfair/nucleo/ordini/porta.py", "Betfair/nucleo/ordini/controlli.py",
          "Betfair/nucleo/ordini/eventi.py", "Betfair/nucleo/ordini/minimi.py",
          "Betfair/nucleo/ordini/esecutori/runner.py"]
TEST = ["Betfair/nucleo/ordini/tests/test_c1_revisione.py",
        "Betfair/nucleo/ordini/tests/test_c1_esecutore_runner.py",
        "Betfair/nucleo/ordini/tests/test_c1_eventi.py",
        "Betfair/nucleo/ordini/tests/test_c1_minimi.py"]
correnti = {m: (R / m).read_bytes() for m in MODULI}
h0 = {m: hashlib.sha256(b).hexdigest() for m, b in correnti.items()}
try:
    for m in MODULI:
        vecchio = subprocess.run(["git", "show", f"0b4f2b59:{m}"], cwd=R, capture_output=True,
                                 check=True).stdout
        (R / m).write_bytes(vecchio)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "--no-header", "-rf", *TEST], cwd=R, capture_output=True, text=True,
                       timeout=900)
    righe = [x for x in r.stdout.splitlines() if x.startswith(("FAILED", "ERROR"))]
    print("\n".join(righe))
    print([x for x in r.stdout.splitlines() if x.strip()][-1])
finally:
    for m, b in correnti.items():
        (R / m).write_bytes(b)
ok = all(hashlib.sha256((R / m).read_bytes()).hexdigest() == h0[m] for m in MODULI)
print("ripristino sha256:", "ok" if ok else "KO")
