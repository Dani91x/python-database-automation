# -*- coding: utf-8 -*-
"""Falsificazione delle due correzioni di isolamento dei test (02/10).

Lancio (dalla radice del repo, con l'interprete del .venv):

    python AUDIT_2026-10-02/falsifica_test_isolamento.py [--ordini]

Per ciascuna correzione rimette il file com'era su ``master`` (``git show
master:<file>``), lancia la combinazione che falliva e pretende ROSSO; poi
rimette il file corretto (contenuto tenuto in memoria, verificato per sha256
alla fine, anche se lo script si interrompe: ``finally``) e pretende VERDE.
In piu' le direzioni incrociate: senza la correzione A il difetto B resta
corretto e viceversa (le due correzioni sono indipendenti).

``--ordini``: lancia anche mike + omega/tests + test_audit di Safe in ordine
inverso e con 3 semi casuali (plugin ``ordine_test_plugin.py``: pytest-randomly
non e' installato). Il referto va in ``falsifica_test_isolamento_out.txt``.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
AUDIT = Path(__file__).resolve().parent
OUT = AUDIT / "falsifica_test_isolamento_out.txt"

CONFTEST_A = "Betfair/conftest.py"                       # difetto (a)
CONFTEST_B = "Betfair/safe_strategy/tests/conftest.py"   # difetto (b)

OMEGA = ("Betfair/omega/tests/test_ref_strategia_per_attore_r1_2026_09_24.py"
         "::test_omega_piazza_con_omega_come_prima")
INQUINATORE = "Betfair/mike/tests/test_mike_p4_ordini_2026_09_29.py"
L4 = ("Betfair/safe_strategy/tests/test_audit_2026_09_11.py"
      "::test_l4_la_guardia_combo_decide_UGUALE_in_paper_e_in_live")

righe: list[str] = []


def scrivi(s: str) -> None:
    print(s, flush=True)
    righe.append(s)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def da_master(rel: str) -> bytes:
    return subprocess.run(["git", "show", f"master:{rel}"], cwd=RADICE,
                          capture_output=True, check=True).stdout


def pytest(*args: str, env_extra: dict | None = None) -> tuple[str, float]:
    env = dict(os.environ)
    env.update(env_extra or {})
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "pytest", *args, "-q", "-p", "no:cacheprovider"],
                       cwd=RADICE, capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace")
    dt = time.time() - t0
    ultime = [r for r in p.stdout.splitlines() if r.strip()]
    sommario = ultime[-1] if ultime else f"(nessun output, rc={p.returncode})"
    falliti = [r for r in p.stdout.splitlines() if r.startswith("FAILED")]
    for f in falliti[:10]:
        scrivi(f"        {f}")
    return sommario, dt


def esito(nome: str, atteso: str, args: tuple[str, ...], env_extra: dict | None = None) -> bool:
    sommario, dt = pytest(*args, env_extra=env_extra)
    rosso = bool(re.search(r"\b\d+ (failed|error)", sommario))
    ottenuto = "ROSSO" if rosso else "VERDE"
    ok = ottenuto == atteso
    scrivi(f"  [{'OK ' if ok else 'KO!'}] {nome}: atteso {atteso}, ottenuto {ottenuto} "
           f"-> {sommario} ({dt:.1f}s)")
    return ok


def main() -> int:
    ordini = "--ordini" in sys.argv
    pa, pb = RADICE / CONFTEST_A, RADICE / CONFTEST_B
    corretto_a, corretto_b = pa.read_bytes(), pb.read_bytes()
    sha_a, sha_b = sha(pa), sha(pb)
    tutto_ok = True
    scrivi(f"falsifica_test_isolamento - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    scrivi(f"interprete: {sys.executable}")
    try:
        scrivi("\n== 0) CON LE CORREZIONI (stato del ramo)")
        tutto_ok &= esito("(a) inquinatore Mike poi Omega", "VERDE", (INQUINATORE, OMEGA))
        tutto_ok &= esito("(b) l4 da solo", "VERDE", (L4,))

        scrivi(f"\n== 1) MUTAZIONE A: {CONFTEST_A} come su master")
        pa.write_bytes(da_master(CONFTEST_A))
        tutto_ok &= esito("(a) inquinatore Mike poi Omega", "ROSSO", (INQUINATORE, OMEGA))
        tutto_ok &= esito("(a) Omega da solo", "VERDE", (OMEGA,))
        tutto_ok &= esito("(b) l4 da solo (correzione B intatta)", "VERDE", (L4,))
        pa.write_bytes(corretto_a)

        scrivi(f"\n== 2) MUTAZIONE B: {CONFTEST_B} come su master")
        pb.write_bytes(da_master(CONFTEST_B))
        tutto_ok &= esito("(b) l4 da solo", "ROSSO", (L4,))
        tutto_ok &= esito("(b) file test_audit intero", "ROSSO",
                          ("Betfair/safe_strategy/tests/test_audit_2026_09_11.py",))
        tutto_ok &= esito("(a) inquinatore poi Omega (correzione A intatta)", "VERDE",
                          (INQUINATORE, OMEGA))
        pb.write_bytes(corretto_b)

        scrivi("\n== 3) RIPRISTINATO: di nuovo verde")
        tutto_ok &= esito("(a) inquinatore Mike poi Omega", "VERDE", (INQUINATORE, OMEGA))
        tutto_ok &= esito("(b) l4 da solo", "VERDE", (L4,))

        if ordini:
            scrivi("\n== 4) ORDINE: mike + omega/tests + test_audit Safe, inverso e 3 semi")
            insieme = ("Betfair/mike", "Betfair/omega/tests",
                       "Betfair/safe_strategy/tests/test_audit_2026_09_11.py",
                       "-p", "ordine_test_plugin")
            pp = str(AUDIT) + os.pathsep + os.environ.get("PYTHONPATH", "")
            for modo in ("inverso", "casuale:1", "casuale:2", "casuale:3"):
                tutto_ok &= esito(f"ORDINE_TEST={modo}", "VERDE", insieme,
                                  env_extra={"ORDINE_TEST": modo, "PYTHONPATH": pp})
    finally:
        pa.write_bytes(corretto_a)
        pb.write_bytes(corretto_b)
        ripristino = sha(pa) == sha_a and sha(pb) == sha_b
        scrivi(f"\nripristino dei file corretti verificato per sha256: {ripristino}")
        tutto_ok &= ripristino
        scrivi(f"ESITO COMPLESSIVO: {'TUTTO COME ATTESO' if tutto_ok else 'DIFFORMITA'}")
        OUT.write_text("\n".join(righe) + "\n", encoding="utf-8")
    return 0 if tutto_ok else 1


if __name__ == "__main__":
    sys.exit(main())
