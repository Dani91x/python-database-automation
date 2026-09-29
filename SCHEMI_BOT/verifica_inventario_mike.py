"""Verifica del COORDINATORE: l'inventario delle logiche di Mike copre TUTTO?

Per ogni area: estrae dal codice vero i nomi (funzioni, classi, parametri di
config, variabili d'ambiente, file della UI, funzioni SQL) e controlla che
ciascuno compaia per nome nel file di inventario. Sola lettura.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

R = Path(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
INV = R / "SCHEMI_BOT" / "mike" / "inventario"


def nomi_py(percorso: str, da: int = 1, a: int = 10 ** 9) -> List[Tuple[str, int]]:
    """Funzioni e classi (anche annidate e metodi) definite fra le righe date."""
    albero = ast.parse((R / percorso).read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(albero):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if da <= n.lineno < a:
                out.append((n.name, n.lineno))
    return sorted(set(out), key=lambda x: x[1])


def parametri_config() -> List[Tuple[str, int]]:
    albero = ast.parse((R / "Betfair/mike/config.py").read_text(encoding="utf-8"))
    out = []
    for n in albero.body:
        bersagli = []
        if isinstance(n, ast.Assign):
            bersagli = n.targets
        elif isinstance(n, ast.AnnAssign):
            bersagli = [n.target]
        for t in bersagli:
            if isinstance(t, ast.Name):
                out.append((t.id, n.lineno))
    # chiavi dei dizionari di default (i parametri modificabili)
    testo = (R / "Betfair/mike/config.py").read_text(encoding="utf-8")
    for i, riga in enumerate(testo.splitlines(), 1):
        m = re.match(r'\s+"([a-z][a-z0-9_]+)"\s*:', riga)
        if m:
            out.append((m.group(1), i))
    return sorted(set(out), key=lambda x: x[1])


def variabili_ambiente(percorso: str, da: int = 1, a: int = 10 ** 9) -> List[Tuple[str, int]]:
    out = []
    for i, riga in enumerate((R / percorso).read_text(encoding="utf-8").splitlines(), 1):
        if not (da <= i < a):
            continue
        for m in re.finditer(r'(?:environ(?:\.get)?|getenv)\s*[\(\[]\s*["\']([A-Z][A-Z0-9_]+)["\']', riga):
            out.append((m.group(1), i))
    return sorted(set(out), key=lambda x: x[1])


def file_ui() -> List[Tuple[str, int]]:
    out = []
    for p in (R / "frontend" / "src").rglob("*"):
        if p.suffix not in (".ts", ".tsx") or ".test." in p.name or "node_modules" in p.parts:
            continue
        try:
            testo = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if re.search(r"mike", testo, re.I) or re.search(r"mike", p.name, re.I):
            out.append((p.name, 0))
    return sorted(set(out))


def funzioni_sql() -> List[Tuple[str, int]]:
    out = set()
    for p in (R / "migrations").glob("*.sql"):
        testo = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"create\s+(?:or\s+replace\s+)?function\s+(?:public\.)?([a-z0-9_]*mike[a-z0-9_]*)",
                             testo, re.I):
            out.add((m.group(1).lower(), 0))
    return sorted(out)


AREE: Dict[str, List[Tuple[str, Iterable[Tuple[str, int]]]]] = {
    "A_calcoli_e_guardie.md": [
        ("engine.py 1-2495", nomi_py("Betfair/mike/engine.py", 1, 2495)),
        ("config.py nomi", nomi_py("Betfair/mike/config.py")),
        ("config.py parametri", parametri_config()),
        ("variabili d'ambiente", variabili_ambiente("Betfair/mike/engine.py", 1, 2495)
         + variabili_ambiente("Betfair/mike/config.py")),
    ],
    "B_strategia.md": [
        ("engine.py 2495-fine", nomi_py("Betfair/mike/engine.py", 2495)),
        ("variabili d'ambiente", variabili_ambiente("Betfair/mike/engine.py", 2495)),
    ],
    "C_servizio_e_ordini.md": [
        ("service.py 1-3250", nomi_py("Betfair/mike/service.py", 1, 3250)),
        ("porta_ordini.py", nomi_py("Betfair/mike/porta_ordini.py")),
        ("variabili d'ambiente", variabili_ambiente("Betfair/mike/service.py", 1, 3250)
         + variabili_ambiente("Betfair/mike/porta_ordini.py")),
    ],
    "D_giro_e_conti.md": [
        ("service.py 3250-fine", nomi_py("Betfair/mike/service.py", 3250)),
        ("feed.py", nomi_py("Betfair/mike/feed.py")),
        ("db.py", nomi_py("Betfair/mike/db.py")),
        ("dossier.py", nomi_py("Betfair/mike/dossier.py")),
        ("variabili d'ambiente", variabili_ambiente("Betfair/mike/service.py", 3250)
         + variabili_ambiente("Betfair/mike/feed.py") + variabili_ambiente("Betfair/mike/db.py")
         + variabili_ambiente("Betfair/mike/dossier.py")),
    ],
    "E_schermate_e_pulsanti.md": [
        ("file della UI che nominano Mike", file_ui()),
        ("funzioni SQL di Mike", funzioni_sql()),
    ],
}


def main() -> int:
    solo = set(sys.argv[1:])
    buchi_tot = 0
    for nome, gruppi in AREE.items():
        if solo and nome[0] not in solo:
            continue
        f = INV / nome
        if not f.exists():
            print("== %s: NON ANCORA CONSEGNATO" % nome)
            continue
        testo = f.read_text(encoding="utf-8", errors="ignore")
        schede = len(re.findall(r"^### ", testo, re.M))
        print("== %s: %d righe, %d schede" % (nome, testo.count("\n"), schede))
        for titolo, nomi in gruppi:
            nomi = sorted(set(nomi), key=lambda x: (x[1], x[0]))
            mancano = [(n, r) for n, r in nomi
                       if not re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(n), testo)]
            buchi_tot += len(mancano)
            print("   %-34s %3d nomi, mancano %d" % (titolo, len(nomi), len(mancano)))
            for n, r in mancano:
                print("        - %s (riga %s)" % (n, r or "-"))
        for sez in ("Glossario", "Differenze dalla Costituzione", "Cose strane", "Non ho capito"):
            if sez.lower() not in testo.lower():
                print("   SEZIONE MANCANTE: %s" % sez)
                buchi_tot += 1
    print("TOTALE buchi: %d" % buchi_tot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
