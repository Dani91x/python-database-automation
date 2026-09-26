"""Sostituzione esatta (una sola occorrenza) old->new in un file, conservando CRLF/LF.
Uso: python sostituisci.py <file> <file_con_old> <file_con_new>"""
import sys

dest, fo, fn = sys.argv[1:4]
t = open(dest, encoding='utf-8', newline='').read()
crlf = '\r\n' in t
t = t.replace('\r\n', '\n')
old = open(fo, encoding='utf-8', newline='').read().replace('\r\n', '\n').rstrip('\n')
new = open(fn, encoding='utf-8', newline='').read().replace('\r\n', '\n').rstrip('\n')
n = t.count(old)
if n != 1:
    raise SystemExit(f'occorrenze di old: {n} (attesa 1)')
t = t.replace(old, new)
if crlf:
    t = t.replace('\n', '\r\n')
open(dest, 'w', encoding='utf-8', newline='').write(t)
print('ok', dest)
