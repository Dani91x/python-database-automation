"""Estrae dai registri RPC salvati la PRIMA risposta di una RPC e stampa i campi chiesti (sola lettura file).
Uso: python estrai.py <log.json> <nome_rpc> <percorso1> [<percorso2> ...]   (percorso a punti, es. control.stats)"""
import json
import sys

L = json.load(open(sys.argv[1], encoding='utf8'))
rows = [l for l in L if l['name'] == sys.argv[2]]
print('chiamate', len(rows), 'errori', [r['error'] for r in rows if r['error']])
if rows:
    d = rows[0]['data']
    for path in sys.argv[3:]:
        v = d
        for k in path.split('.'):
            if isinstance(v, dict):
                v = v.get(k)
            elif isinstance(v, list) and k.isdigit():
                v = v[int(k)] if int(k) < len(v) else None
            else:
                v = None
        print(path, '=', json.dumps(v, ensure_ascii=False)[:3000])
