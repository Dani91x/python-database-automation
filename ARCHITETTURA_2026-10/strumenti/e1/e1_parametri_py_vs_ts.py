"""E1: confronta PARAM_SPEC (Python) con MIKE_PARAM_FIELDS e MIKE_PARAM_DEFAULTS (frontend).
Solo lettura statica (ast + regex), non importa codice di produzione. ASCII-only."""
import ast, re, sys
PY = "Betfair/mike/config.py"
TS = "frontend/src/lib/mike.ts"
src = open(PY, encoding="utf-8").read()
tree = ast.parse(src)
spec = {}
for n in ast.walk(tree):
    if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "PARAM_SPEC":
        for k, v in zip(n.value.keys, n.value.values):
            d = ast.literal_eval(v.elts[0]); lo = ast.literal_eval(v.elts[2]); hi = ast.literal_eval(v.elts[3])
            ch = ast.literal_eval(v.elts[4]); cast = v.elts[1].id
            spec[k.value] = (d, cast, lo, hi, ch, k.lineno)
ts = open(TS, encoding="utf-8").read().split("\n")
fields = {}
for i, line in enumerate(ts, 1):
    m = re.match(r"\s*\{ key: '([a-z_0-9]+)', label: '.*?', kind: '(\w+)'(.*)", line)
    if m:
        key, kind, rest = m.groups()
        mn = re.search(r"min: ([-0-9._]+)", rest); mx = re.search(r"max: ([-0-9._]+)", rest)
        fields[key] = (kind, float(mn.group(1).replace("_", "")) if mn else None, float(mx.group(1).replace("_", "")) if mx else None, i)
# blocco default
start = next(i for i, l in enumerate(ts) if l.startswith("export const MIKE_PARAM_DEFAULTS"))
end = next(i for i in range(start, len(ts)) if ts[i].startswith("};"))
blk = "\n".join(l.split("//")[0] for l in ts[start + 1:end])
defs = {}
for m in re.finditer(r"([a-z_0-9]+): ('[^']*'|[-0-9._]+|true|false)", blk):
    v = m.group(2)
    defs[m.group(1)] = v.strip("'") if v.startswith("'") else (v == "true" if v in ("true", "false") else float(v.replace("_", "")))
print("python chiavi:", len(spec), " ts campi:", len(fields), " ts default:", len(defs))
print("solo python:", sorted(set(spec) - set(fields)))
print("solo ts campi:", sorted(set(fields) - set(spec)))
print("senza default ts:", sorted(set(spec) - set(defs)))
print("default ts senza chiave python:", sorted(set(defs) - set(spec)))
diff = 0
for k, (d, cast, lo, hi, ch, ln) in spec.items():
    if k in defs and defs[k] != d and not (isinstance(d, (int, float)) and not isinstance(d, bool) and float(defs[k]) == float(d)):
        print("DEFAULT DIVERSO", k, d, defs[k]); diff += 1
    if k in fields:
        kind, mn, mx, tl = fields[k]
        if kind == "number" and ((lo is not None and mn != float(lo)) or (hi is not None and mx != float(hi))):
            print("LIMITI DIVERSI", k, (lo, hi), (mn, mx)); diff += 1
print("differenze:", diff)
print("campi per tipo:", {t: sum(1 for f in fields.values() if f[0] == t) for t in set(f[0] for f in fields.values())})
