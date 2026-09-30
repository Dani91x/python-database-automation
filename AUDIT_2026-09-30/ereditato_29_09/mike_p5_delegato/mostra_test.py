"""Stampa le righe con i parametri dei test indicati (uso interno al blocco 5)."""
import ast
import sys

base = sys.argv[1]
for riga in sys.stdin.read().replace("﻿", "").split():
    f, nome = riga.split("::")
    nome = nome.split("[")[0]
    src = open(base + "/" + f, encoding="utf-8").read()
    t = ast.parse(src)
    for n in ast.walk(t):
        if isinstance(n, ast.FunctionDef) and n.name == nome:
            linee = src.splitlines()[n.lineno - 1:n.end_lineno]
            print("=====", f, n.lineno, n.end_lineno)
            print("\n".join(l for l in linee if "param" in l.lower() or "def " in l
                            or "merge" in l or "PAR" in l))
