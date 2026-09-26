"""diff profondo fra due fotografie dell'accensione (sola lettura dei file). Uso: diff_foto.py A B tabella"""
import json, os, sys
D = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\accensione"


def carica(n):
    return json.load(open(os.path.join(D, n + ".json"), encoding="utf8"))


def diff(a, b, p=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k == "stats":
                continue
            yield from diff(a.get(k), b.get(k), f"{p}.{k}")
    elif isinstance(a, list) and isinstance(b, list) and all(isinstance(x, dict) for x in a + b):
        for i, (x, y) in enumerate(zip(a, b)):
            yield from diff(x, y, f"{p}[{i}]")
    elif a != b:
        yield p, a, b


a, b = carica(sys.argv[1]), carica(sys.argv[2])
for t in sys.argv[3:]:
    for p, x, y in diff(a[t], b[t], t):
        print(p, json.dumps(x)[:200], "->", json.dumps(y)[:200])
