"""Visore dei registri RPC/select salvati dai test di fase 3 (sola lettura di file locali)."""
import json
import sys

n = int(sys.argv[2]) if len(sys.argv) > 2 else 700
for p in sys.argv[1].split(','):
    L = json.load(open(p, encoding='utf8'))
    print('###', p)
    for l in L:
        print(l['kind'], l['name'], json.dumps(l['args'])[:250], 'ERR=' + str(l['error']), json.dumps(l['data'], ensure_ascii=False)[:n])
