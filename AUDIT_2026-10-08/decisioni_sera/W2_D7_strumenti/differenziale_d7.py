# -*- coding: utf-8 -*-
"""Differenziale D-7: gli stessi test del W2 (``test_greenup_fuori_bot_2026_10_08.py``,
compresi i 51 scenari di parita' del green-up di sempre) eseguiti col worker di
``master`` (prima di D-7) e col worker di oggi; si confronta, chiamata per chiamata,
la riga di coda, gli ordini piazzati, i metodi del conto, le letture del DB.

Il worker di master si mette nel worktree con ``git show`` e, alla fine, si rimette
quello nuovo verificandone lo sha256 (ripristino provato). Uso, dalla radice del
worktree: ``python AUDIT_2026-10-08/decisioni_sera/W2_D7_strumenti/differenziale_d7.py``.
ASCII-only."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

RADICE = pathlib.Path(__file__).resolve().parents[3]
WORKER = RADICE / "Betfair" / "stream" / "live_order_worker.py"
TEST = "Betfair/stream/tests/test_greenup_fuori_bot_2026_10_08.py"
QUI = pathlib.Path(__file__).resolve().parent
USCITA = QUI / "uscite"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def corsa(nome):
    out = USCITA / f"cattura_{nome}.json"
    env = dict(os.environ, D7_CATTURA=str(out), PYTHONPATH=str(QUI))
    r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider",
                        "-p", "cattura_plugin"], cwd=RADICE, env=env,
                       capture_output=True, text=True)
    print(nome, r.stdout.strip().splitlines()[-1])
    return json.loads(out.read_text(encoding="utf-8"))


def main():
    USCITA.mkdir(exist_ok=True)
    nuovo = WORKER.read_bytes()
    sha_nuovo = sha(WORKER)
    vecchio = subprocess.run(["git", "show", "master:Betfair/stream/live_order_worker.py"],
                             cwd=RADICE, capture_output=True).stdout
    try:
        WORKER.write_bytes(vecchio)
        prima = corsa("master")
    finally:
        WORKER.write_bytes(nuovo)
    assert sha(WORKER) == sha_nuovo, "RIPRISTINO FALLITO"
    print("ripristino verificato sha256", sha_nuovo[:16])
    dopo = corsa("d7")
    nodi = sorted(set(prima) | set(dopo))
    diversi = [n for n in nodi if prima.get(n) != dopo.get(n)]
    chiamate = sum(len(v) for v in prima.values())
    print(f"test con esegui: {len(nodi)}, chiamate a esegui: {chiamate}, diversi: {len(diversi)}")
    for n in diversi:
        print("DIVERSO:", n)
        for a, b in zip(prima.get(n) or [], dopo.get(n) or []):
            for k in a:
                if a[k] != b.get(k):
                    print("   ", k, "\n      master:", json.dumps(a[k])[:400],
                          "\n      d7    :", json.dumps(b.get(k))[:400])


if __name__ == "__main__":
    main()
