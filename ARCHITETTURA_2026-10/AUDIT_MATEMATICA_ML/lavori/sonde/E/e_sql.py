import re, subprocess, os, collections, sys
files = subprocess.run(["git","ls-files","sql","migrations"],capture_output=True,text=True).stdout.split("\n")
files = [f for f in files if f.endswith(".sql")]
# data ultimo commit
dates = {}
cur = None
log = subprocess.run(["git","log","--name-only","--format=@@%cI","--","sql","migrations"],capture_output=True,text=True,encoding="utf-8").stdout
for ln in log.splitlines():
    if ln.startswith("@@"): cur = ln[2:12]
    elif ln.strip() and ln not in dates: dates[ln.strip()] = cur
def fdate(f):
    m = re.search(r'(20\d\d-\d\d-\d\d)', os.path.basename(f))
    return m.group(1) if m else dates.get(f,"0000")
pat = re.compile(r'^\s*create\s+(or\s+replace\s+)?(function|view|materialized\s+view)\s+(?:if\s+not\s+exists\s+)?([\w."]+)', re.I)
arith = re.compile(r'\b(avg|sum|exp|ln|log|power|round|sqrt|stddev|percentile_cont|corr|regr_\w+)\s*\(|[\w)\]]\s*/\s*[\w(\[]|\)\s*\*\s*[\w(]|\w\s*\*\s*\(|\d\s*\*\s*\w|\w\s*\*\s*\d', re.I)
defs = collections.defaultdict(list)
for f in files:
    try: L = open(f,encoding="utf-8",errors="replace").read().splitlines()
    except Exception: continue
    idx = [(i,pat.match(l)) for i,l in enumerate(L)]
    idx = [(i,m) for i,m in idx if m]
    for k,(i,m) in enumerate(idx):
        end = idx[k+1][0] if k+1 < len(idx) else len(L)
        body = "\n".join(l for l in L[i:end] if not l.strip().startswith("--"))
        body2 = re.sub(r'count\(\*\)|select\s+\*|\.\*|\*/|/\*','',body, flags=re.I)
        hits = len(arith.findall(body2))
        name = m.group(3).replace('"','').replace("public.","")
        defs[name].append((fdate(f), f, i+1, hits, m.group(2).lower()))
out = open(sys.argv[1],"w",encoding="utf-8")
for name, v in sorted(defs.items()):
    v.sort()
    last = v[-1]
    out.write(f"{name}\t{last[4]}\tvigente={last[1]}:{last[2]}\t{last[0]}\tarit={last[3]}\tndef={len(v)}\tprime={';'.join(os.path.basename(x[1])+':'+str(x[2]) for x in v[:-1][-3:])}\n")
print(len(defs), "nomi,", sum(len(v) for v in defs.values()), "definizioni")
