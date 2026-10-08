"""E1: tabella markdown dei 107 parametri: default, limiti, riga in config.py, riga del campo in mike.ts, gruppo UI,
dove sono LETTI (engine/service/feed/dossier). Solo lettura statica. ASCII-only."""
import ast, re
cfg = open("Betfair/mike/config.py", encoding="utf-8").read()
tree = ast.parse(cfg)
spec = {}
for n in ast.walk(tree):
    if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "PARAM_SPEC":
        for k, v in zip(n.value.keys, n.value.values):
            spec[k.value] = (ast.literal_eval(v.elts[0]), ast.literal_eval(v.elts[2]), ast.literal_eval(v.elts[3]),
                             ast.literal_eval(v.elts[4]), k.lineno)
ts = open("frontend/src/lib/mike.ts", encoding="utf-8").read().split("\n")
fld = {}
for i, l in enumerate(ts, 1):
    m = re.match(r"\s*\{ key: '([a-z_0-9]+)'.*group: '(\w+)'", l)
    if m:
        fld[m.group(1)] = (i, m.group(2))
src = {f: open("Betfair/mike/%s.py" % f, encoding="utf-8").read() for f in ("engine", "service", "feed", "dossier")}
print("| chiave | default | limiti / scelte | config.py | mike.ts | gruppo UI | letto in |")
print("|---|---|---|---:|---:|---|---|")
for k, (d, lo, hi, ch, ln) in spec.items():
    lim = ("{" + "/".join(ch) + "}") if ch else ("%s..%s" % (lo, hi) if lo is not None else "-")
    dove = ",".join(f for f, t in src.items() if re.search(r"[\"']%s[\"']" % k, t)) or "NESSUNO"
    tl, g = fld.get(k, ("?", "?"))
    print("| `%s` | %r | %s | %d | %s | %s | %s |" % (k, d, lim, ln, tl, g, dove))
