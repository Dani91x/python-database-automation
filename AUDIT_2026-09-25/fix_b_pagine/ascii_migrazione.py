"""Rende ASCII i commenti di un file (regola del repo: codice ASCII-only)."""
import sys

MAPPA = {'→': '->', '§': 'par.', 'à': "a'", 'è': "e'", 'é': "e'",
         '∈': 'in', 'ì': "i'", 'ò': "o'", 'ù': "u'", '—': '-', '×': 'x'}
for p in sys.argv[1:]:
    t = open(p, encoding='utf-8', newline='').read()
    for k, v in MAPPA.items():
        t = t.replace(k, v)
    resto = sorted({c for c in t if ord(c) > 127})
    open(p, 'w', encoding='utf-8', newline='').write(t)
    print(p, 'non-ASCII rimasti:', [hex(ord(c)) for c in resto])
