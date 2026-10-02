"""Falsificazione della correzione PARITA_SAFE_ENV (02/10/2026).

Rimette il difetto in tre modi (uno alla volta), pretende ROSSO dai test, poi
ripristina il file (sha256 verificato nel ``finally``) e pretende VERDE.

  M1  ``trasporto.contesto`` torna a scrivere l'interruttore SOLO per il canale
      (la coda lo lascia all'ambiente: il difetto di master, strato trasporto)
  M2  ``AMBIENTE_DEL_BANCO`` senza i 20 interruttori (solo i freni di master:
      il difetto di master, strato freni)
  M3  M1 + M2 insieme = master: anche il test [cert] sulla registrazione vera
      deve diventare rosso (circa 90 s)
  M4  l'intestazione del referto non stampa gli interruttori

NON interrompere lo script: il ripristino e' nel ``finally``. Uscita in
``AUDIT_2026-10-02/falsifica_parita_env_out.txt``.
Uso (dalla radice del worktree): python AUDIT_2026-10-02/falsifica_parita_env.py
"""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import time

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRA = os.path.join(RADICE, "Betfair", "stream", "backtest", "trasporto.py")
CER = os.path.join(RADICE, "Betfair", "stream", "backtest", "certifica.py")
TEST_NUOVO = "Betfair/stream/tests/test_banco_ambiente_dichiarato_2026_10_02.py"
TEST_STRADA = "Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py"
OUT = os.path.join(RADICE, "AUDIT_2026-10-02", "falsifica_parita_env_out.txt")

M1 = (
    "        os.environ[nome_env] = VALORE_INTERRUTTORE[trasporto]",
    "        if trasporto == \"canale\":\n            os.environ[nome_env] = \"1\"",
)
M2 = (
    "    **{nome: \"0\" for nome in INTERRUTTORI_CANALE_DEL_BANCO},",
    "    # MUTAZIONE M2: interruttori non dichiarati",
)
M4 = (
    "            + \" \".join(f\"{k}={v}\" for k, v in sorted(AMBIENTE_DEL_BANCO.items()))",
    "            + \" \".join(f\"{k}={v}\" for k, v in sorted(FRENI_AMBIENTE_DEL_BANCO.items()))",
)

righe = []


def scrivi(s: str) -> None:
    print(s, flush=True)
    righe.append(s)


def sha(p: str) -> str:
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def leggi(p: str) -> str:
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def scrivi_file(p: str, s: str) -> None:
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def muta(p: str, coppia) -> None:
    s = leggi(p)
    vecchio, nuovo = coppia
    assert s.count(vecchio) == 1, "punto di mutazione non unico in %s: %r" % (p, vecchio)
    scrivi_file(p, s.replace(vecchio, nuovo))


def pytest(*args: str) -> tuple:
    t0 = time.monotonic()
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args]
    p = subprocess.run(cmd, cwd=RADICE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    coda = [r for r in p.stdout.splitlines() if r.strip()][-1:] or ["(nessuna uscita)"]
    return p.returncode, coda[0], round(time.monotonic() - t0, 1)


def passo(nome: str, atteso: str, *args: str) -> bool:
    rc, riga, dur = pytest(*args)
    ottenuto = "verde" if rc == 0 else "rosso"
    ok = ottenuto == atteso
    scrivi("%-4s %-62s atteso=%-5s ottenuto=%-5s %s | %s (%.1f s)" % (
        "OK" if ok else "KO", nome, atteso, ottenuto, "" if ok else "<-- !!", riga, dur))
    return ok


def main() -> int:
    originali = {TRA: leggi(TRA), CER: leggi(CER)}
    impronte = {p: sha(p) for p in originali}
    tutti_ok = True
    try:
        veloci = (TEST_NUOVO, TEST_STRADA, "-m", "not cert")
        scrivi("FALSIFICAZIONE PARITA_SAFE_ENV - %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
        tutti_ok &= passo("0  codice corretto: test veloci", "verde", *veloci)

        muta(TRA, M1)
        tutti_ok &= passo("M1 coda non scrive l'interruttore: test veloci", "rosso", *veloci)
        tutti_ok &= passo("M1   - test_coda_spegne... (valore '1')", "rosso",
                          TEST_NUOVO + "::test_coda_spegne_l_interruttore_per_ogni_valore_dell_ambiente[1]")
        scrivi_file(TRA, originali[TRA])

        muta(CER, M2)
        tutti_ok &= passo("M2 freni senza i 20 interruttori: test veloci", "rosso", *veloci)
        tutti_ok &= passo("M2   - test_load_dotenv_a_meta_replay_non_riaccende", "rosso",
                          TEST_NUOVO + "::test_load_dotenv_a_meta_replay_non_riaccende")
        scrivi_file(CER, originali[CER])

        muta(TRA, M1)
        muta(CER, M2)
        tutti_ok &= passo("M3 = master (M1+M2): test [cert] sulla registrazione vera",
                          "rosso", TEST_NUOVO, "-m", "cert")
        scrivi_file(TRA, originali[TRA])
        scrivi_file(CER, originali[CER])

        muta(CER, M4)
        tutti_ok &= passo("M4 intestazione senza interruttori", "rosso",
                          TEST_NUOVO + "::test_intestazione_identica_per_ogni_ambiente")
        scrivi_file(CER, originali[CER])

        tutti_ok &= passo("R  ripristinato: test veloci", "verde", *veloci)
        tutti_ok &= passo("R  ripristinato: test [cert]", "verde", TEST_NUOVO, "-m", "cert")
    finally:
        for p, s in originali.items():
            scrivi_file(p, s)
        for p, h in impronte.items():
            ok = sha(p) == h
            tutti_ok &= ok
            scrivi("ripristino %s sha256 %s" % (os.path.relpath(p, RADICE),
                                                "IDENTICO" if ok else "DIVERSO !!"))
        scrivi("ESITO: %s" % ("TUTTO COME ATTESO" if tutti_ok else "QUALCOSA NON TORNA"))
        with io.open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(righe) + "\n")
    return 0 if tutti_ok else 1


if __name__ == "__main__":
    sys.exit(main())
