"""Esplorazione usa-e-getta dei log: conta le 'firme' delle righe (senza numeri/ID) per file.
Sola lettura, a flusso. Uso: python m00_esplora_log.py <cartella_log> <parola> [<parola>...]
Stampa, per ogni parola chiave, quante righe la contengono per file e 3 esempi."""
import sys, os, re, glob, collections
D = sys.argv[1]; KW = [k.lower() for k in sys.argv[2:]]
cnt = collections.defaultdict(collections.Counter); ex = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(D, '*.log'))):
    b = os.path.basename(f)
    if b.startswith('backtest-worker'):
        continue
    with open(f, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            l = line.lower()
            for k in KW:
                if k in l:
                    cnt[k][b] += 1
                    if len(ex[k]) < 3:
                        ex[k].append(line.strip()[:400])
for k in KW:
    print('== ', k, 'totale', sum(cnt[k].values()))
    for b, n in sorted(cnt[k].items()):
        print('   ', n, b)
    for e in ex[k]:
        print('   EX:', e)
