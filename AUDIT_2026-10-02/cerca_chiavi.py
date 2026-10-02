"""Stampa, per ogni chiave data, le righe dei file Python che la nominano (sola lettura).
Uso: python AUDIT_2026-10-02/cerca_chiavi.py <file1,file2,...> <chiave1> <chiave2> ...
"""
import re
import sys

files = sys.argv[1].split(',')
for k in sys.argv[2:]:
    print(f'== {k}')
    pat = re.compile(r'''["']''' + re.escape(k) + r'''["']''')
    for f in files:
        for i, riga in enumerate(open(f, encoding='utf-8', errors='replace'), 1):
            if pat.search(riga):
                print(f'   {f}:{i}: {riga.strip()[:150]}')
