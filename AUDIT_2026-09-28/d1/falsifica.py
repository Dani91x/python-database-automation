"""Falsificazione D1: applica UNA mutazione, lancia i test, ripristina SEMPRE.

uso: python falsifica.py <file> <file_vecchio.txt> <file_nuovo.txt> <test...>
Vecchio/nuovo sono file di testo (stringhe multi-riga). Il ripristino e'
byte-identico (SHA-256 confrontato) anche se pytest esplode. Il testo nuovo
porta il marcatore MUTAZIONE (da verificare assente a fine giro).
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    target = ROOT / sys.argv[1]
    old = Path(sys.argv[2]).read_text(encoding="utf-8")
    new = Path(sys.argv[3]).read_text(encoding="utf-8")
    tests = sys.argv[4:]
    orig = target.read_bytes()
    h0 = hashlib.sha256(orig).hexdigest()
    testo = orig.decode("utf-8")
    if "\r\n" in testo:           # file con fine riga Windows
        old = old.replace("\r\n", "\n").replace("\n", "\r\n")
        new = new.replace("\r\n", "\n").replace("\n", "\r\n")
    if testo.count(old) != 1:
        print("MUTAZIONE NON APPLICABILE: occorrenze =", testo.count(old))
        return 2
    try:
        target.write_bytes(testo.replace(old, new, 1).encode("utf-8"))
        r = subprocess.run([str(ROOT / ".venv/Scripts/python.exe"), "-m", "pytest", "-q",
                            "-p", "no:cacheprovider", *tests],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        righe = r.stdout.strip().splitlines()
        falliti = [l for l in righe if l.startswith("FAILED")]
        print("\n".join(falliti)[:3000])
        print("N_FALLITI", len(falliti))
        print(righe[-1] if righe else r.stderr[-500:])
        print("ESITO:", "ROSSO" if r.returncode != 0 else "VERDE (mutazione NON catturata)")
    finally:
        target.write_bytes(orig)
    h1 = hashlib.sha256(target.read_bytes()).hexdigest()
    print("ripristino byte-identico:", h0 == h1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
