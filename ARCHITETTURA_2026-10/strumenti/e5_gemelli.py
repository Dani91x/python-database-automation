"""E5: misura del codice gemello fra due file (solo lettura, solo libreria standard).

Uso: python -I ARCHITETTURA_2026-10/strumenti/e5_gemelli.py A.py B.py [A.py B.py ...]
Per ogni coppia: righe di codice (senza vuote e senza commenti/docstring a riga intera),
righe di A trovate identiche in B (stessa sequenza, difflib), percentuale su A e su B,
e i blocchi gemelli piu' lunghi con i numeri di riga in entrambi i file.
Normalizza: strip, collassa spazi; ignora righe vuote e che iniziano con '#'.
Non importa codice di produzione. Non scrive nulla.
"""
import difflib
import re
import sys


def carica(path):
    righe = []
    with open(path, encoding="utf-8") as f:
        for n, r in enumerate(f, 1):
            t = re.sub(r"\s+", " ", r.strip())
            if not t or t.startswith("#"):
                continue
            righe.append((n, t))
    return righe


def main(argv):
    if len(argv) < 2 or len(argv) % 2:
        print(__doc__)
        return 2
    for i in range(0, len(argv), 2):
        a, b = argv[i], argv[i + 1]
        ra, rb = carica(a), carica(b)
        sm = difflib.SequenceMatcher(None, [t for _, t in ra], [t for _, t in rb],
                                     autojunk=False)
        blocchi = [m for m in sm.get_matching_blocks() if m.size > 0]
        tot = sum(m.size for m in blocchi)
        # blocchi "significativi": >= 5 righe consecutive
        sig = sum(m.size for m in blocchi if m.size >= 5)
        print("== %s (%d righe di codice) <> %s (%d)" % (a, len(ra), b, len(rb)))
        print("   righe uguali (tutte): %d = %.1f%% di A, %.1f%% di B" % (
            tot, 100.0 * tot / max(1, len(ra)), 100.0 * tot / max(1, len(rb))))
        print("   righe uguali in blocchi >=5: %d = %.1f%% di A, %.1f%% di B" % (
            sig, 100.0 * sig / max(1, len(ra)), 100.0 * sig / max(1, len(rb))))
        top = sorted(blocchi, key=lambda m: -m.size)[:8]
        for m in top:
            print("   blocco %d righe: A:%d-%d  B:%d-%d" % (
                m.size, ra[m.a][0], ra[m.a + m.size - 1][0],
                rb[m.b][0], rb[m.b + m.size - 1][0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
