"""Sola lettura: quante volte (campioni ogni N s, pre-match fino a KO - stop_s) un runner
dei mercati dello scalper ha quota 1.50-4.6, size >=300 su ENTRAMBI i best e spread <=2 tick.
uso: habitat.py <dir> <evento> <passo_s> <stop_s> <min_size>"""
import json, sys
from datetime import datetime

base, ev, passo, stop_s, min_size = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
TIPI = {"MATCH_ODDS", "OVER_UNDER_15", "OVER_UNDER_25", "OVER_UNDER_35"}

def tick(p):
    for lim, t in ((2, .01), (3, .02), (4, .05), (6, .1), (10, .2), (20, .5), (30, 1), (50, 2), (100, 5), (1000, 10)):
        if p < lim - 1e-9:
            return t
    return 10

def ticks_between(a, b):
    n, p = 0, a
    while p < b - 1e-9 and n < 100:
        p = round(p + tick(p), 2)
        n += 1
    return n

tl = [json.loads(l) for l in open(f'{base}/{ev}/{ev}.timeline.jsonl')]
ko = datetime.fromisoformat(next(d['ts'] for d in tl if d['type'] == 'KickOff')).timestamp() * 1000
tipo, lad, stato = {}, {}, {}
cont = {}
prossimo = 0
primo = None
with open(f'{base}/{ev}/{ev}.raw.jsonl') as f:
    for line in f:
        d = json.loads(line)
        pt = d.get('pt', 0)
        primo = primo or pt
        for m in d.get('mc', []):
            mid = m['id']
            md = m.get('marketDefinition')
            if md:
                tipo[mid] = md.get('marketType')
                stato[mid] = (md.get('status'), md.get('inPlay'))
            if tipo.get(mid) not in TIPI:
                continue
            for r in m.get('rc', []):
                L = lad.setdefault((mid, r['id']), {'b': {}, 'l': {}})
                for fld, side in (('atb', 'b'), ('atl', 'l')):
                    for p, s in r.get(fld, []) or []:
                        if s == 0:
                            L[side].pop(p, None)
                        else:
                            L[side][p] = s
        if pt >= prossimo and pt < ko - stop_s * 1000:
            for k, L in lad.items():
                if stato.get(k[0], ('',))[0] != 'OPEN' or stato[k[0]][1]:
                    continue
                c = cont.setdefault((tipo[k[0]], k[1]), [0, 0, 0, 0])
                c[0] += 1
                if not L['b'] or not L['l']:
                    continue
                bb, bl = max(L['b']), min(L['l'])
                if 1.5 <= bb <= 4.6:
                    c[1] += 1
                    if L['b'][bb] >= min_size and L['l'][bl] >= min_size:
                        c[2] += 1
                        if ticks_between(bb, bl) <= 2:
                            c[3] += 1
            prossimo = pt + passo * 1000
print(f'pre-match registrato: {(ko - primo) / 60000:.1f} min; campioni ogni {passo}s fino a KO-{stop_s}s')
print('mercato selezione | campioni | quota in banda | +size>=%g entrambi | +spread<=2 tick' % min_size)
for k, c in sorted(cont.items(), key=lambda x: str(x)):
    print(k, c)
