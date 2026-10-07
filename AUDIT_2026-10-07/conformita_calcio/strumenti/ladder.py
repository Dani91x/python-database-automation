"""Sola lettura: migliori back/lay per mercati/selezioni scelti, campionati ogni N secondi.
uso: ladder.py <dir> <evento> <passo_s> <mkt:sel,...> [da_min] [a_min]
minuto e punteggio ricostruiti dalla timeline (stessa fonte del sidecar)."""
import json, sys
from datetime import datetime

base, ev, passo = sys.argv[1], sys.argv[2], float(sys.argv[3])
voci = [tuple(x.split(':')) for x in sys.argv[4].split(',')]
da_min = float(sys.argv[5]) if len(sys.argv) > 5 else -999
a_min = float(sys.argv[6]) if len(sys.argv) > 6 else 999

def ts(s):
    return datetime.fromisoformat(s).timestamp() * 1000

tl = [json.loads(l) for l in open(f'{base}/{ev}/{ev}.timeline.jsonl')]
ko = next(ts(d['ts']) for d in tl if d['type'] == 'KickOff')
fhe = next((ts(d['ts']) for d in tl if d['type'] == 'FirstHalfEnd'), None)
shko = next((ts(d['ts']) for d in tl if d['type'] == 'SecondHalfKickOff'), None)
gol = [(ts(d['ts']), d['team']) for d in tl if d['type'] == 'Goal']

def minuto(pt):
    if pt < ko:
        return (pt - ko) / 60000.0
    if shko and pt >= shko:
        return 45 + (pt - shko) / 60000.0
    if fhe and pt >= fhe:
        return 45.0
    return (pt - ko) / 60000.0

def punteggio(pt):
    h = sum(1 for t, s in gol if t <= pt and s == 'home')
    a = sum(1 for t, s in gol if t <= pt and s == 'away')
    return f'{h}-{a}'

lad = {}  # (mkt, sel) -> {'b': {p: s}, 'l': {p: s}}
stato = {}
prossimo = 0
with open(f'{base}/{ev}/{ev}.raw.jsonl') as f:
    for line in f:
        d = json.loads(line)
        pt = d.get('pt', 0)
        for m in d.get('mc', []):
            mid = m['id']
            md = m.get('marketDefinition')
            if md:
                stato[mid] = (md.get('status'), md.get('inPlay'))
            for r in m.get('rc', []):
                k = (mid, str(r['id']))
                L = lad.setdefault(k, {'b': {}, 'l': {}})
                for fld, side in (('atb', 'b'), ('atl', 'l')):
                    for p, s in r.get(fld, []) or []:
                        if s == 0:
                            L[side].pop(p, None)
                        else:
                            L[side][p] = s
        if pt >= prossimo:
            mn = minuto(pt)
            if da_min <= mn <= a_min:
                out = []
                for mk, sel in voci:
                    L = lad.get((mk, sel), {'b': {}, 'l': {}})
                    bb = max(L['b']) if L['b'] else None
                    bl = min(L['l']) if L['l'] else None
                    out.append(f"{mk[-3:]}:{sel} B={bb}({L['b'].get(bb, 0):.0f}) L={bl}({L['l'].get(bl, 0):.0f}) {stato.get(mk, ('?',))[0][:4]}")
                print(f"{mn:6.1f}' {punteggio(pt)} | " + ' | '.join(out))
            prossimo = pt + passo * 1000
