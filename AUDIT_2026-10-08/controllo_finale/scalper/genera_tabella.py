import re,sys
from collections import Counter
f797,fpap,f084,c1,c2,c3=sys.argv[1:]
RE=re.compile(r"^(OK|KO|NE)\s+(\d+)(?:\s+\[([^\]]+)\])?\s+tick=\s*(\d+) decisioni=\s*(\d+) azioni=\s*(\d+)")
def leggi(p,unico=None):
    out={};cur=None
    for r in open(p):
        m=RE.match(r)
        if m:
            cur=(m.group(3) or unico); out[cur]=dict(e=m.group(1),t=m.group(4),d=m.group(5),a=m.group(6),v=[]);continue
        if cur and re.match(r"^      [A-Z]+\d+ x\d+:",r): out[cur]["v"].append(r.split(":")[0].strip())
        elif cur and not r.startswith("      "): cur=None
    return out
def conf(p):
    o={}
    for r in open(p):
        x=r.strip().split(" | ")
        if len(x)==6 and x[0].isdigit(): o[x[1]]=(x[2],x[5])
    return o
a=leggi(f797); a.update(leggi(fpap,"rifiuti-betfair-codici-paper"))
b=leggi(f084)
ca=conf(c1); ca.update(conf(c2)); cb=conf(c3)
print("| scenario | 35797769 | tick | dec. | azioni | violati | rif. | righe diverse | 35760084 | tick | dec. | azioni | violati | rif. | righe diverse |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for s in b:
    x=a[s];y=b[s]
    print("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"%(s,x["e"],x["t"],x["d"],x["a"],", ".join(x["v"]) or "-",ca[s][0],ca[s][1],y["e"],y["t"],y["d"],y["a"],", ".join(y["v"]) or "-",cb[s][0],cb[s][1]))
print(); print("35797769:",dict(Counter(v["e"] for v in a.values())),len(a)); print("35760084:",dict(Counter(v["e"] for v in b.values())),len(b))
