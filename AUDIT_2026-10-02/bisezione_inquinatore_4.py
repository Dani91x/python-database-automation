"""Bisezione dell'inquinatore di ``test_net_retry.py::test_db_client_is_per_thread``.

Uso (dalla radice del worktree):
    python AUDIT_2026-10-02/bisezione_inquinatore_4.py [--candidati FILE...] [--raccogli]

1. raccoglie l'ordine dei file della suite ``Betfair`` (pytest --collect-only);
2. tiene i file che PRECEDONO il bersaglio (o i ``--candidati`` dati);
3. verifica che l'insieme + bersaglio sia ROSSO;
4. dimezza: prova la prima meta', se rossa tiene quella, altrimenti la seconda;
   se nessuna delle due da sola e' rossa (servono due file insieme) si ferma e
   lo dichiara;
5. stampa l'inquinatore minimo (un file), poi bisezione sui SUOI test.

Nessun riordino: i file sono passati a pytest nell'ordine della suite, il
bersaglio sempre per ultimo.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
PY = sys.executable
BERSAGLIO = "Betfair/stream/tests/test_net_retry.py::test_db_client_is_per_thread"
FILE_BERSAGLIO = "Betfair/stream/tests/test_net_retry.py"


def _pytest(args: list[str], timeout: int = 1500) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "pytest", *args, "-q", "-p", "no:cacheprovider"],
                          cwd=RADICE, capture_output=True, text=True, timeout=timeout)


def raccogli_file() -> list[str]:
    r = _pytest(["Betfair", "--collect-only"])
    visti: list[str] = []
    for riga in r.stdout.splitlines():
        if "::" in riga:
            f = riga.split("::", 1)[0]
            if not visti or visti[-1] != f:
                if f not in visti:
                    visti.append(f)
    return visti


def raccogli_test(file: str) -> list[str]:
    r = _pytest([file, "--collect-only"])
    return [riga.strip() for riga in r.stdout.splitlines() if "::" in riga]


def rosso(insieme: list[str]) -> bool:
    t0 = time.time()
    r = _pytest([*insieme, BERSAGLIO])
    # il bersaglio e' rosso se compare tra i FAILED
    esito = f"FAILED {BERSAGLIO}" in r.stdout
    print(f"  [{len(insieme):4d} elementi] {'ROSSO' if esito else 'verde'} "
          f"({time.time() - t0:.0f} s) :: {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]}",
          flush=True)
    return esito


def bisezione(elementi: list[str]) -> list[str]:
    while len(elementi) > 1:
        meta = len(elementi) // 2
        a, b = elementi[:meta], elementi[meta:]
        if rosso(a):
            elementi = a
        elif rosso(b):
            elementi = b
        else:
            print("  nessuna meta' da sola e' rossa: servono elementi di entrambe", flush=True)
            return elementi
    return elementi


def main() -> int:
    argv = sys.argv[1:]
    if "--candidati" in argv:
        candidati = argv[argv.index("--candidati") + 1:]
    else:
        tutti = raccogli_file()
        idx = tutti.index(FILE_BERSAGLIO)
        candidati = tutti[:idx]
    print(f"candidati: {len(candidati)} file", flush=True)
    if not rosso(candidati):
        print("L'insieme dei candidati NON riproduce il rosso.", flush=True)
        return 2
    file_min = bisezione(candidati)
    print(f"FILE inquinatore minimo: {file_min}", flush=True)
    if len(file_min) == 1:
        test = raccogli_test(file_min[0])
        print(f"bisezione sui {len(test)} test del file", flush=True)
        test_min = bisezione(test)
        print(f"TEST inquinatore minimo: {test_min}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
