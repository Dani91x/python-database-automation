# -*- coding: utf-8 -*-
"""Funzioni e metodi di PRODUZIONE mai riferiti (solo lettura, nessun import del codice).

Criterio: nome definito con def in un file .py tracciato di produzione (esclusi test_*, tests/,
tools/, AUDIT*, SCHEMI_BOT, ARCHITETTURA*, laboratorio/, sql/) che compare UNA SOLA VOLTA
(parola intera) in tutto il testo dei .py di produzione, test inclusi nel conteggio negativo:
se un test lo cita, il nome compare >1 e NON e' segnalato come morto (limite per difetto).
Sono esclusi i nomi dunder, i metodi decorati (route/handler/property/fixture) e `main`.
Uso: python k_funzioni_mai_riferite.py > uscite/k_funzioni_mai_riferite.txt
"""
import ast, re, subprocess, sys, collections
RADICE = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
files = subprocess.check_output(["git", "-C", RADICE, "ls-files", "*.py"], text=True).splitlines()
ESCL = ("AUDIT", "SCHEMI_BOT", "ARCHITETTURA", "_AUDIT", "laboratorio/", "sql/", "migrations/")
def prod(f):
    if f.startswith(ESCL): return False
    b = f.rsplit("/", 1)[-1]
    if b.startswith("test_") or "/tests/" in f or "/tools/" in f or "conftest" in b: return False
    return True
testo = {}
for f in files:
    try: testo[f] = open(RADICE + "/" + f, encoding="utf-8", errors="replace").read()
    except OSError: pass
# conteggio parole su TUTTI i .py non-audit (test inclusi) + yml/js/ts/bat per nomi citati da fuori
altri = subprocess.check_output(["git", "-C", RADICE, "ls-files", "*.yml", "*.js", "*.bat", "*.ps1", "*.ts", "*.tsx"], text=True).splitlines()
corpus = "\n".join(t for f, t in testo.items() if not f.startswith(("AUDIT", "SCHEMI_BOT", "ARCHITETTURA", "_AUDIT")))
for f in altri:
    if f.startswith(("AUDIT", "SCHEMI_BOT", "ARCHITETTURA", "_AUDIT", "frontend/node_modules")): continue
    try: corpus += "\n" + open(RADICE + "/" + f, encoding="utf-8", errors="replace").read()
    except OSError: pass
cnt = collections.Counter(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", corpus))
out = []
for f in sorted(files):
    if not prod(f): continue
    try: tree = ast.parse(testo[f])
    except SyntaxError: continue
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nome = n.name
            if nome.startswith("__") or nome == "main" or n.decorator_list: continue
            if cnt[nome] == 1:
                righe = (n.end_lineno or n.lineno) - n.lineno + 1
                out.append((f, n.lineno, nome, righe))
tot = collections.defaultdict(lambda: [0, 0])
for f, l, nome, r in out:
    tot[f][0] += 1; tot[f][1] += r
print("# funzioni/metodi di produzione mai riferiti (nome presente 1 sola volta nel corpus): %d, %d righe" % (len(out), sum(o[3] for o in out)))
print("# per file (n funzioni, righe):")
for f, (n, r) in sorted(tot.items(), key=lambda x: -x[1][1]):
    print("%6d righe %3d fn  %s" % (r, n, f))
print("# dettaglio (file:riga nome righe)")
for f, l, nome, r in sorted(out, key=lambda o: (-o[3], o[0])):
    print("%s:%d %s %d" % (f, l, nome, r))
