import re, sys
ESITO = re.compile(r'^(OK|KO|NE)\s+(\d+) \[([^\]]+)\]')
def leggi(p):
    blocchi, coda, cur = {}, [], None
    for r in open(p, encoding='utf-8', errors='replace'):
        r = r.rstrip('\n')
        m = ESITO.match(r)
        if m:
            cur = m.group(3); blocchi[cur] = [r]; continue
        if r.startswith(('ESITO:', 'TEMPO TOTALE', 'LENTO')) or (r and not r.startswith(' ') and cur and not ESITO.match(r)):
            cur = None
        if cur is None:
            if not r.startswith(('TEMPO TOTALE', 'LENTO', 'BOT:', 'controlli attivi', 'comando:')):
                coda.append(r)
        elif not r.strip().startswith('tempo:'):
            blocchi[cur].append(r)
    return blocchi, coda
a, ca = leggi(sys.argv[1]); b, cb = leggi(sys.argv[2])
print('ESITI DOPO:')
for k, v in b.items(): print('  ', v[0][:160])
print('SCENARI NUOVI:', [k for k in b if k not in a]); print('SCENARI SPARITI:', [k for k in a if k not in b])
for k in b:
    if k not in a: continue
    if a[k] == b[k]: continue
    print(f'=== DIFF [{k}]')
    sa, sb = set(a[k]), set(b[k])
    for r in a[k]:
        if r not in sb: print('  PRIMA:', r)
    for r in b[k]:
        if r not in sa: print('  DOPO :', r)
if ca != cb:
    print('=== DIFF coda/intestazione')
    for r in ca:
        if r not in cb: print('  PRIMA:', r)
    for r in cb:
        if r not in ca: print('  DOPO :', r)
