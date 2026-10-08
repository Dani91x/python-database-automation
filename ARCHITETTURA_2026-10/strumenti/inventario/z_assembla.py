"""Assembla ARCHITETTURA_2026-10/00_INVENTARIO.md dalle parti scritte a mano (parti/p*.md) e dalle uscite degli script.

Segnaposto nelle parti:
  {{file:NOME}}            include uscite/NOME (se .md: tale e quale; altrimenti in un blocco di codice)
  {{sez:NOME:MARCATORE}}   include da uscite/NOME la sezione che inizia con una riga che comincia con MARCATORE:
                           se MARCATORE inizia con '==' fino alla prossima riga che inizia con '== ' (esclusa);
                           altrimenti fino alla prima riga vuota. Sempre in un blocco di codice.
Scrive SOLO ARCHITETTURA_2026-10/00_INVENTARIO.md. Uso: python z_assembla.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402

PARTI = Path(__file__).resolve().parent / "parti"
USC = c.USCITE
NL = chr(10)
FENCE = chr(96) * 3


def blocco(testo: str) -> str:
    return FENCE + NL + testo.rstrip() + NL + FENCE


def sezione(nome: str, marcatore: str) -> str:
    righe = (USC / nome).read_text(encoding="utf-8").splitlines()
    for i, r in enumerate(righe):
        if r.startswith(marcatore):
            out = [r]
            for q in righe[i + 1:]:
                if marcatore.startswith("==") and q.startswith("== "):
                    break
                if not marcatore.startswith("==") and not q.strip():
                    break
                out.append(q)
            return blocco(NL.join(out))
    raise SystemExit("marcatore non trovato: %s in %s" % (marcatore, nome))


def rimpiazza(m: "re.Match[str]") -> str:
    kind, resto = m.group(1), m.group(2)
    if kind == "file":
        s = (USC / resto).read_text(encoding="utf-8")
        return s.rstrip() if resto.endswith(".md") else blocco(s)
    nome, marc = resto.split(":", 1)
    return sezione(nome, marc)


def main() -> int:
    testo = []
    for p in sorted(PARTI.glob("p*.md")):
        testo.append(re.sub(r"\{\{(file|sez):([^}]+)\}\}", rimpiazza, p.read_text(encoding="utf-8")))
    out = c.RADICE / "ARCHITETTURA_2026-10" / "00_INVENTARIO.md"
    out.write_text(NL.join(testo), encoding="utf-8", newline=NL)
    print("scritto", out, out.stat().st_size, "byte,", out.read_text(encoding="utf-8").count(NL), "righe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
