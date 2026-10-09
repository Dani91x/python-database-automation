# Campione di citazioni file:riga (CERT_5). Criterio: tutte le citazioni di CODICE (py/ts/tsx/sql/yml/sh),
# deduplicate per (file,riga iniziale) in ordine di apparizione, una ogni N (N = totale // 20), per ciascun documento.
import re, subprocess, sys, os
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
AU = os.path.join(R, "ARCHITETTURA_2026-10", "AUDIT_MATEMATICA_ML")
files = subprocess.run(["git", "ls-files"], cwd=R, capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
byname = {}
for f in files:
    byname.setdefault(os.path.basename(f), []).append(f)
pat = re.compile(r"((?:Ai Engine/)?[\w./\-]+\.(?:py|ts|tsx|sql|yml|sh)):(\d+)(?:-(\d+))?")
def resolve(c):
    if c in files: return c
    cands = [f for f in files if f.endswith("/" + c) or f == c]
    if len(cands) == 1: return cands[0]
    b = byname.get(os.path.basename(c), [])
    # preferisci non-test
    b2 = [x for x in b if "test" not in x.lower() and "AUDIT" not in x]
    if len(b2) == 1: return b2[0]
    if len(b) == 1: return b[0]
    return None if not (b2 or b) else "AMBIGUO:" + "|".join((b2 or b)[:3])
N = int(sys.argv[2]) if len(sys.argv) > 2 else 0
doc = sys.argv[1]
lines = open(os.path.join(AU, doc), encoding="utf-8").read().splitlines()
seen = set(); cits = []
for i, l in enumerate(lines, 1):
    for m in pat.finditer(l):
        k = (m.group(1), m.group(2))
        if k in seen: continue
        seen.add(k); cits.append((i, m, l))
n = N or max(1, len(cits) // 20)
print(doc, "citazioni uniche:", len(cits), "passo:", n)
sel = cits[n // 2::n][:20]
cache = {}
def getline(p, no):
    if p not in cache:
        cache[p] = open(os.path.join(R, p), encoding="utf-8", errors="replace").read().splitlines()
    L = cache[p]
    return L[no - 1].strip()[:150] if 0 < no <= len(L) else "<<RIGA FUORI FILE (file ha %d righe)>>" % len(L)
for idx, (i, m, l) in enumerate(sel, 1):
    p = resolve(m.group(1)); a = int(m.group(2)); b = int(m.group(3)) if m.group(3) else None
    s = max(0, m.start() - 70); ctx = l[s:m.end() + 90].replace("\n", " ")
    print(f"\n[{idx}] {doc}:{i} -> {m.group(0)}  => {p}")
    print("  DOC:", ctx)
    if p and not p.startswith("AMBIGUO"):
        print(f"  L{a}:", getline(p, a))
        if b and b != a:
            print(f"  L{b}:", getline(p, b))
            mid = (a + b) // 2
            print(f"  L{mid}:", getline(p, mid))
