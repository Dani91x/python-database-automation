"""Costruisce SCHEMI_BOT/sistema/ARCHITETTURA_ATTUALE.html con il costruttore comune delle guide.

Passi:
  1. lancia `SCHEMI_BOT/costruisci_guida.py sistema` (legge schemi/NN_*.html e NN_*.schede.md);
  2. rinomina il titolo «Guida di Sistema» in «Architettura attuale»;
  3. scrive ARCHITETTURA_ATTUALE.html e cancella il file intermedio GUIDA_SISTEMA.html.

Uso: python costruisci_architettura.py [--versione "base 22d19cc"]
Solo libreria standard. Non modifica il costruttore comune.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parents[1]
COSTRUTTORE = CARTELLA.parent / "costruisci_guida.py"


def main(argv: list[str]) -> int:
    r = subprocess.run([sys.executable, str(COSTRUTTORE), "sistema", *argv],
                       capture_output=True, text=True, encoding="utf-8")
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return r.returncode
    intermedio = CARTELLA / "GUIDA_SISTEMA.html"
    testo = intermedio.read_text(encoding="utf-8")
    testo = testo.replace("Guida di Sistema", "Architettura attuale")
    uscita = CARTELLA / "ARCHITETTURA_ATTUALE.html"
    uscita.write_text(testo, encoding="utf-8")
    intermedio.unlink()
    print(f"Scritto: {uscita} ({len(testo.encode('utf-8'))} byte)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
