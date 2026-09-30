"""Blocco 5 di P5: aggiunge ``@pytest.mark.usefixtures("forma_di_prima")`` sopra
i test ELENCATI (quelli che descrivono la forma di prima), niente altro.
Uso: python fissa_forma_di_prima.py <cartella dei test> < elenco (file::test)"""
import ast
import sys

DECORATORE = '@pytest.mark.usefixtures("forma_di_prima")'
base = sys.argv[1]
per_file = {}
for riga in sys.stdin.read().replace("﻿", "").split():
    f, nome = riga.split("::")
    per_file.setdefault(f, set()).add(nome.split("[")[0])
for f, nomi in sorted(per_file.items()):
    percorso = base + "/" + f
    raw = open(percorso, "rb").read()
    crlf = b"\r\n" in raw
    testo = raw.decode("utf-8").replace("\r\n", "\n")
    righe = testo.split("\n")
    albero = ast.parse(testo)
    posti = []
    for n in albero.body:
        if isinstance(n, ast.FunctionDef) and n.name in nomi:
            primo = min([d.lineno for d in n.decorator_list] + [n.lineno])
            gia = any(DECORATORE in righe[i] for i in range(primo - 1, n.lineno))
            if not gia:
                posti.append(primo - 1)
            nomi_trovati = n.name
    for i in sorted(posti, reverse=True):
        righe.insert(i, DECORATORE)
    nuovo = "\n".join(righe)
    if "import pytest" not in nuovo:
        raise SystemExit(f"{f}: manca 'import pytest'")
    if crlf:
        nuovo = nuovo.replace("\n", "\r\n")
    open(percorso, "wb").write(nuovo.encode("utf-8"))
    print(f, len(posti), "test fissati")
