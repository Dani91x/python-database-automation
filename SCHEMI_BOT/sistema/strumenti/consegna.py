"""Produce gli HTML archify di tutti i capitoli di SCHEMI_BOT/sistema/schemi/ (deliver showcase).

Uso: python consegna.py   (richiede node e la skill archify in ~/.claude/skills/archify)
Stampa una riga per capitolo: nome, esito, controlli superati. Esce 1 se un capitolo fallisce.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCHEMI = Path(__file__).resolve().parents[1] / "schemi"
ARCHIFY = Path.home() / ".claude" / "skills" / "archify"


def main() -> int:
    ko = 0
    for spec in sorted(SCHEMI.glob("*.architecture.json")):
        out = spec.with_name(spec.name.replace(".architecture.json", ".html"))
        r = subprocess.run(
            ["node", "bin/archify.mjs", "deliver", "architecture", str(spec), str(out),
             "--quality", "showcase", "--json"],
            cwd=ARCHIFY, capture_output=True, text=True, encoding="utf-8",
        )
        try:
            j = json.loads(r.stdout)
        except ValueError:
            print(f"{spec.name}: uscita non leggibile (codice {r.returncode})\n{r.stderr[:400]}")
            ko += 1
            continue
        esito = "OK" if (r.returncode == 0 and j.get("ok")) else "FALLITO"
        if esito != "OK":
            ko += 1
            for d in j.get("diagnostics", []):
                print("   ", d.get("message", "")[:240])
        print(f"{spec.name}: {esito} (codice {r.returncode})")
    return 1 if ko else 0


if __name__ == "__main__":
    raise SystemExit(main())
