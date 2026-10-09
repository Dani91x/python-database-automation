# CERT_5: per OGNI citazione di codice di 00 e 03, segnala quelle con riga oltre la fine del file o file non risolvibile.
import re, subprocess, os, sys
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
AU = os.path.join(R, "ARCHITETTURA_2026-10", "AUDIT_MATEMATICA_ML")
files = subprocess.run(["git", "ls-files"], cwd=R, capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
byname = {}
for f in files: byname.setdefault(os.path.basename(f), []).append(f)
pat = re.compile(r"((?:Ai Engine/)?[\w./\-]+\.(?:py|ts|tsx|sql|yml|sh)):(\d+)(?:-(\d+))?")
def resolve(c):
    if c in files: return c
    cands = [f for f in files if f.endswith("/" + c)]
    if len(cands) == 1: return cands[0]
    b = byname.get(os.path.basename(c), [])
    b2 = [x for x in b if "test" not in x.lower() and "AUDIT" not in x]
    if len(b2) == 1: return b2[0]
    if len(b) == 1: return b[0]
    return None
n = 0; bad = []
for doc in ("00_INVENTARIO_MATEMATICO.md", "03_COMPONENTI_MATEMATICI.md"):
    for i, l in enumerate(open(os.path.join(AU, doc), encoding="utf-8").read().splitlines(), 1):
        for m in pat.finditer(l):
            n += 1
            p = resolve(m.group(1)); a = int(m.group(2)); b = int(m.group(3) or a)
            if not p:
                bad.append((doc, i, m.group(0), "NON RISOLTO (file fuori repo o ambiguo)")); continue
            ln = len(open(os.path.join(R, p), encoding="utf-8", errors="replace").read().splitlines())
            if b > ln or a > ln: bad.append((doc, i, m.group(0), "oltre fine file (%s ha %d righe)" % (p, ln)))
print("citazioni totali (con ripetizioni):", n)
for x in bad: print(x)
