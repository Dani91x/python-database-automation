"""Falsificazione della correzione «isolamento 4» (``Betfair/conftest.py``,
fixture ``_ripristina_stato_di_processo_di_db_client``).

Uso (dalla radice del worktree):
    python AUDIT_2026-10-02/falsifica_test_isolamento_4.py

1. sha256 del conftest corretto;
2. CON la correzione: combinazione minima -> attesa VERDE;
3. correzione TOLTA (la fixture rimossa dal testo): combinazione minima ->
   attesa ROSSA con ``TypeError ... 'options'``;
4. correzione RIMESSA (byte originali, in ``finally``): -> attesa VERDE;
5. sha256 dopo == sha256 prima, altrimenti esce con errore.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
CONFTEST = RADICE / "Betfair" / "conftest.py"
PY = sys.executable
INQUINATORE = ("Betfair/mike/tests/test_mike_riga_assente_e_arresto_2026_10_02.py::"
               "test_R1_main_all_arresto_chiama_l_arresto_degli_ordini")
BERSAGLIO = "Betfair/stream/tests/test_net_retry.py::test_db_client_is_per_thread"
INIZIO = "@pytest.fixture(autouse=True)\ndef _ripristina_stato_di_processo_di_db_client"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def gira(etichetta: str) -> bool:
    r = subprocess.run([PY, "-m", "pytest", INQUINATORE, BERSAGLIO, "-q", "-p", "no:cacheprovider"],
                       cwd=RADICE, capture_output=True, text=True, timeout=600)
    rosso = f"FAILED {BERSAGLIO}" in r.stdout
    motivo = [riga.strip() for riga in r.stdout.splitlines() if "TypeError" in riga][:1]
    print(f"[{etichetta}] {'ROSSO' if rosso else 'VERDE'} :: {r.stdout.strip().splitlines()[-1]}"
          f"{' :: ' + motivo[0] if motivo else ''}", flush=True)
    return rosso


def senza_correzione(testo: str) -> str:
    testo_n = testo.replace("\r\n", "\n")
    i = testo_n.index(INIZIO)
    j = testo_n.find("\n\n\n@pytest.fixture", i + len(INIZIO))
    assert j > i, "fine della fixture non trovata"
    tolto = testo_n[:i] + testo_n[j + 3:]
    assert "_ripristina_stato_di_processo_di_db_client" not in tolto
    return tolto


def main() -> int:
    originale = CONFTEST.read_bytes()
    h0 = sha(CONFTEST)
    print(f"sha256 conftest (con correzione): {h0}", flush=True)
    esiti = {}
    esiti["con"] = gira("1 con correzione")
    try:
        CONFTEST.write_bytes(senza_correzione(originale.decode("utf-8")).encode("utf-8"))
        print(f"sha256 conftest (correzione tolta): {sha(CONFTEST)}", flush=True)
        esiti["senza"] = gira("2 correzione TOLTA")
    finally:
        CONFTEST.write_bytes(originale)
    h1 = sha(CONFTEST)
    print(f"sha256 conftest (rimesso): {h1} {'IDENTICO' if h1 == h0 else 'DIVERSO!'}", flush=True)
    esiti["rimessa"] = gira("3 correzione RIMESSA")
    ok = (not esiti["con"]) and esiti["senza"] and (not esiti["rimessa"]) and h1 == h0
    print(f"FALSIFICAZIONE {'RIUSCITA' if ok else 'FALLITA'}: con=verde, tolta=rossa, rimessa=verde, sha identico",
          flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
