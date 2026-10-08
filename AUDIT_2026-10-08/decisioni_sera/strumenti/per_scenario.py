# confronto per scenario: estrae i blocchi (riga di esito + righe rientrate)
# e applica righe_confrontabili del banco. Uso: per_scenario.py RIF NUOVO [scen,...]
import re, sys, difflib
sys.path.insert(0, ".")
from Betfair.stream.backtest.tools.confronta_referti import righe_confrontabili
RE = re.compile(r"^(OK|KO|NE)\s+(\d+)(?:\s+\[([^\]]+)\])?\s+tick=")
def blocchi(testo, unico=None):
    out = {}; cur = None
    for r in testo.splitlines():
        m = RE.match(r)
        if m:
            cur = (m.group(2), m.group(3) or unico); out[cur] = [r]; continue
        if cur and (r.startswith("      ") ):
            out[cur].append(r); continue
        if cur and r.strip(): cur = None
    return out
def leggi(p):
    b = open(p, "rb").read()
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252")
def norm(r):
    return re.sub(r"\s\[[^\]]+\]\s+tick=", "  tick=", r) if RE.match(r) else r
import os
a = blocchi(leggi(sys.argv[1]), os.environ.get("UNICO_A"))
b = blocchi(leggi(sys.argv[2]), sys.argv[4] if len(sys.argv) > 4 else None)
scen = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else None
tot = 0
for k in b:
    if scen and k[1] not in scen: continue
    if k not in a: print("NUOVO", k); continue
    ra = [norm(x) for x in righe_confrontabili("\n".join(a[k]))]
    rb = [norm(x) for x in righe_confrontabili("\n".join(b[k]))]
    d = [x for x in difflib.unified_diff(ra, rb, lineterm="", n=0) if not x.startswith(("---", "+++", "@@"))]
    print("%-40s righe %d/%d  diverse %d" % (k, len(ra), len(rb), len(d)))
    for x in d: print("    " + x[:400])
    tot += len(d)
print("TOTALE righe diverse:", tot)
