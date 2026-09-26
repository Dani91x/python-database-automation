"""falsifica_log_figli.py - K2 (26/09): falsificazione della verifica del log dei figli.

Ogni mutazione si applica a una COPIA di desktop/main.js in una cartella
temporanea (il file vero non si tocca mai) e verifica_log_figli.js deve
diventare ROSSO. In coda: la copia intatta deve restare VERDE e lo sha del
main.js vero deve essere quello di partenza.

Uso: python AUDIT_2026-09-26/falsifica_log_figli.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

QUI = Path(__file__).resolve().parent
MAIN = QUI.parent / "desktop" / "main.js"
VERIFICA = QUI / "verifica_log_figli.js"

MUTAZIONI = {
    "pipe senza scrittura su file": (
        "writeChildLog(label, `${label}${tag}`, line);", ""),
    "exit non scritto nel file": (
        "writeChildLog(label, 'desktop', `terminato (exit ${code})`);", ""),
    "nessuna potatura dei vecchi": (
        "if (now - fs.statSync(p).mtimeMs > CHILD_LOG_RETENTION_MS) fs.unlinkSync(p);", ""),
    "potatura anche dei non .log": (
        "if (!name.endsWith('.log')) continue;", ""),
    "riga senza timestamp": (
        "return `${(now || new Date()).toISOString()} [${tag}] ${line}\\n`;",
        "return `[${tag}] ${line}\\n`;"),
    "cartella non scrivibile solleva": (
        "        return null;\n    }\n}\n\nfunction childLogStream",
        "        throw err;\n    }\n}\n\nfunction childLogStream"),
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def gira(percorso: Path) -> int:
    return subprocess.run(["node", str(VERIFICA), str(percorso)],
                          capture_output=True, text=True).returncode


def main() -> int:
    sha0 = sha(MAIN)
    testo = MAIN.read_text(encoding="utf-8")
    male = 0
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "main.js"
        for nome, (vecchio, nuovo) in MUTAZIONI.items():
            if testo.count(vecchio) != 1:
                print(f"ERRORE: ancora della mutazione '{nome}' trovata {testo.count(vecchio)} volte")
                male += 1
                continue
            copia.write_text(testo.replace(vecchio, nuovo), encoding="utf-8")
            rc = gira(copia)
            esito = "ROSSO (atteso)" if rc != 0 else "VERDE (!!! il test non vede la mutazione)"
            print(f"{nome}: {esito}")
            male += 0 if rc != 0 else 1
        copia.write_text(testo, encoding="utf-8")
        rc = gira(copia)
        print(f"copia intatta: {'VERDE (atteso)' if rc == 0 else 'ROSSO (!!!)'}")
        male += 0 if rc == 0 else 1
    intatto = sha(MAIN) == sha0
    print(f"desktop/main.js vero intatto: {intatto}")
    return 0 if (male == 0 and intatto) else 1


if __name__ == "__main__":
    sys.exit(main())
