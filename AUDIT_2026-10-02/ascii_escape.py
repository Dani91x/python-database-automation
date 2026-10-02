"""Riscrive un file sostituendo ogni carattere non ASCII con il suo escape \\uXXXX
(serve per i test che contengono le sequenze di mojibake: scritte come escape,
il file di test non si accusa da solo e resta ASCII-only come vuole CLAUDE.md)."""
import sys

p = sys.argv[1]
t = open(p, encoding='utf-8').read()
BS = chr(92)
t = ''.join(c if ord(c) < 128 else BS + 'u%04x' % ord(c) for c in t)
open(p, 'w', encoding='utf-8', newline='').write(t)
print('non ASCII rimasti:', sum(1 for c in t if ord(c) > 127))
