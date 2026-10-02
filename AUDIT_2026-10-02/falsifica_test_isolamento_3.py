# -*- coding: utf-8 -*-
"""Falsificazione dell'isolamento 3 (02/10): ``_CONFIG_WARNED`` di Mike.

    python AUDIT_2026-10-02/falsifica_test_isolamento_3.py

Il file di test di Mike da solo, con ``SAFE_PRE_KO_OU_HOURS`` = 0 (ramo
pre-KO spento: l'avviso ``config_warn`` esce), = 3 e assente dall'ambiente del
processo (allora decide il ``.env`` vero letto alla raccolta). Con la riga
``S._CONFIG_WARNED.clear()`` tolta il caso 0 deve tornare ROSSO. File rimesso
dal contenuto in memoria (sha256 verificato nel ``finally``).
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
OUT = Path(__file__).resolve().parent / "falsifica_test_isolamento_3_out.txt"
FILE = RADICE / "Betfair/mike/tests/test_mike_legge_canale_2026_09_23.py"
REL = "Betfair/mike/tests/test_mike_legge_canale_2026_09_23.py"
RIGA = "    S._CONFIG_WARNED.clear()\n"
righe: list[str] = []


def scrivi(s: str) -> None:
    print(s, flush=True)
    righe.append(s)


def corri(nome: str, atteso: str, ore: str | None) -> bool:
    env = dict(os.environ)
    env.pop("SAFE_PRE_KO_OU_HOURS", None)
    if ore is not None:
        env["SAFE_PRE_KO_OU_HOURS"] = ore
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "pytest", REL, "-q", "-p", "no:cacheprovider"],
                       cwd=RADICE, capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace")
    ult = [r for r in p.stdout.splitlines() if r.strip()]
    som = ult[-1] if ult else f"rc={p.returncode}"
    ott = "ROSSO" if re.search(r"\b\d+ (failed|error)", som) else "VERDE"
    for f in [r for r in p.stdout.splitlines() if r.startswith("FAILED")][:5]:
        scrivi(f"        {f}")
    ok = ott == atteso
    scrivi(f"  [{'OK ' if ok else 'KO!'}] {nome}: atteso {atteso}, ottenuto {ott} -> {som} "
           f"({time.time() - t0:.1f}s)")
    return ok


def main() -> int:
    orig = FILE.read_bytes()
    h = hashlib.sha256(orig).hexdigest()
    ok = True
    scrivi(f"falsifica_test_isolamento_3 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        scrivi("\n== 0) CON LA CORREZIONE")
        for ore in ("0", "3", None):
            ok &= corri(f"HOURS={ore if ore is not None else '(assente: .env)'}", "VERDE", ore)
        scrivi("\n== 1) MUTAZIONE: _CONFIG_WARNED non azzerato fra le due corse")
        testo = orig.decode("utf-8")
        nl = "\r\n" if "\r\n" in testo else "\n"
        cerca = RIGA.replace("\n", nl)
        assert testo.count(cerca) == 1
        FILE.write_bytes(testo.replace(cerca, f"    pass  # MUTAZIONE{nl}").encode("utf-8"))
        ok &= corri("HOURS=0 (avviso emesso)", "ROSSO", "0")
        ok &= corri("HOURS=3 (nessun avviso: il difetto non si vede)", "VERDE", "3")
        FILE.write_bytes(orig)
        scrivi("\n== 2) RIPRISTINATO")
        ok &= corri("HOURS=0", "VERDE", "0")
    finally:
        FILE.write_bytes(orig)
        rip = hashlib.sha256(FILE.read_bytes()).hexdigest() == h
        scrivi(f"\nripristino verificato (sha256): {rip}")
        ok &= rip
        scrivi(f"ESITO COMPLESSIVO: {'TUTTO COME ATTESO' if ok else 'DIFFORMITA'}")
        OUT.write_text("\n".join(righe) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
