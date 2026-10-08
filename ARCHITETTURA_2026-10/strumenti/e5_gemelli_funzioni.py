"""E5: gemelli A LIVELLO DI FUNZIONE fra due file (solo lettura, solo libreria standard).

Uso: python -I ARCHITETTURA_2026-10/strumenti/e5_gemelli_funzioni.py A.py B.py [soglia]
Per ogni funzione/metodo di A con LO STESSO NOME qualificato in B (i metodi si confrontano per nome, ignorando il nome della classe)
confronta le righe normalizzate (strip, spazi collassati, senza vuote e commenti a riga
intera) con difflib. Classi: >= soglia (default 0.80) = GEMELLA; 0.50-soglia = PARENTE.
Stampa: righe di A in funzioni gemelle / parenti / senza controparte in B.
Non importa codice di produzione. Non scrive nulla.
"""
import ast
import difflib
import re
import sys


def funzioni(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    righe = src.splitlines()
    out = {}

    def corpo(n):
        seg = righe[n.lineno - 1:n.end_lineno]
        res = []
        for r in seg:
            t = re.sub(r"\s+", " ", r.strip())
            if t and not t.startswith("#"):
                res.append(t)
        return res

    def visita(nodo, prefisso):
        for n in ast.iter_child_nodes(nodo):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefisso + n.name] = (n.lineno, n.end_lineno, corpo(n))
            elif isinstance(n, ast.ClassDef):
                visita(n, prefisso + "*.")
    visita(tree, "")
    return out


def main(argv):
    a, b = argv[0], argv[1]
    soglia = float(argv[2]) if len(argv) > 2 else 0.80
    fa, fb = funzioni(a), funzioni(b)
    tot = sum(len(v[2]) for v in fa.values())
    gem = par = senza = 0
    elenco = []
    for nome, (l0, l1, ca) in fa.items():
        if nome in fb:
            cb = fb[nome][2]
            r = difflib.SequenceMatcher(None, ca, cb, autojunk=False).ratio()
            if r >= soglia:
                gem += len(ca)
                k = "GEMELLA"
            elif r >= 0.5:
                par += len(ca)
                k = "parente"
            else:
                senza += len(ca)
                k = "diversa"
            elenco.append((len(ca), nome, l0, l1, fb[nome][0], fb[nome][1], r, k))
        else:
            senza += len(ca)
    print("== %s  <>  %s" % (a, b))
    print("   righe di codice in funzioni di A: %d" % tot)
    print("   in funzioni GEMELLE (stesso nome, somiglianza >= %.2f): %d = %.1f%%" % (
        soglia, gem, 100.0 * gem / max(1, tot)))
    print("   in funzioni PARENTI (0.50-%.2f): %d = %.1f%%" % (soglia, par, 100.0 * par / max(1, tot)))
    print("   senza controparte o diverse: %d = %.1f%%" % (senza, 100.0 * senza / max(1, tot)))
    for n, nome, l0, l1, m0, m1, r, k in sorted(elenco, reverse=True)[:14]:
        print("   %-8s %-40s A:%d-%d  B:%d-%d  ratio=%.2f  (%d righe)" % (k, nome, l0, l1, m0, m1, r, n))


if __name__ == "__main__":
    main(sys.argv[1:])
