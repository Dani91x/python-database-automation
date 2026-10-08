"""G1 - funzioni con lo stesso nome nei moduli DB dei bot: righe, similarita' del corpo (difflib), differenze.

Solo libreria standard, sola lettura (ast sui file tracciati). Scrive SOLO in uscite/.
Rieseguibile: python ARCHITETTURA_2026-10/strumenti/dati_g1/gemelle.py
Uscita: gemelle.tsv (nome, modulo_a, riga_a, righe_a, modulo_b, riga_b, righe_b, similarita')
Similarita' = difflib.SequenceMatcher sui corpi senza commenti/docstring/righe vuote (0..1).
"""
from __future__ import annotations

import ast
import difflib
import itertools
import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]
USCITE = Path(__file__).resolve().parent / "uscite"
USCITE.mkdir(parents=True, exist_ok=True)

MODULI = {
    "mike": "Betfair/mike/db.py",
    "safe": "Betfair/safe_strategy/bot_db.py",
    "omega": "Betfair/omega/omega_db.py",
    "tennis": "Betfair/stream/tennis_live/tennis_db.py",
    "stream": "Betfair/stream/db.py",
    "safe_scan": "Betfair/safe_strategy/db.py",
}


def corpo(src: str, nodo: ast.AST) -> str:
    seg = ast.get_source_segment(src, nodo) or ""
    seg = re.sub(r'""".*?"""', "", seg, flags=re.S)
    righe = []
    for r in seg.split("\n"):
        r = re.sub(r"#.*$", "", r).rstrip()
        if r.strip():
            righe.append(r.strip())
    return "\n".join(righe)


def main() -> None:
    funz: dict[str, dict[str, tuple[int, int, str]]] = {}
    for sig, rel in MODULI.items():
        src = (RADICE / rel).read_text("utf-8", errors="replace")
        for n in ast.parse(src).body:
            if isinstance(n, ast.FunctionDef):
                funz.setdefault(n.name, {})[sig] = (n.lineno, n.end_lineno - n.lineno + 1, corpo(src, n))
    out = []
    for nome, d in sorted(funz.items()):
        if len(d) < 2:
            continue
        for a, b in itertools.combinations(sorted(d), 2):
            ra = d[a][2]
            rb = d[b][2]
            sim = difflib.SequenceMatcher(None, ra, rb, autojunk=False).ratio()
            out.append(f"{nome}\t{MODULI[a]}\t{d[a][0]}\t{d[a][1]}\t{MODULI[b]}\t{d[b][0]}\t{d[b][1]}\t{sim:.2f}")
    (USCITE / "gemelle.tsv").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(len(out), "coppie")


if __name__ == "__main__":
    main()
