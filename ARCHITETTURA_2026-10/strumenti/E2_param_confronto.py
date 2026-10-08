# -*- coding: utf-8 -*-
"""E2 - confronta i 87 parametri di Omega fra Python (omega_config._SPEC) e TS (omega.ts).
Legge solo i sorgenti come testo (NON importa moduli di produzione). Uso: python E2_param_confronto.py"""
import io, os, re
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
def leggi(p):
    return io.open(os.path.join(R, p), encoding="utf-8").read().split("\n")
py = leggi("Betfair/omega/omega_config.py")
ts = leggi("frontend/src/lib/omega.ts")
def num(s):
    s = s.strip().replace("_", "")
    if s in ("True", "true"): return True
    if s in ("False", "false"): return False
    if s.startswith(("'", '"')): return s.strip("'\"")
    try: return float(s)
    except ValueError: return s
spec = {}
for i, riga in enumerate(py[22:323], start=23):
    m = re.match(r'^    "([a-z_0-9]+)": \((.+?), (float|int|bool|str), (None|[-0-9._e]+), (None|[-0-9._e]+)\)', riga)
    if m:
        spec[m.group(1)] = (i, num(m.group(2)), None if m.group(4) == "None" else num(m.group(4)), None if m.group(5) == "None" else num(m.group(5)))
dts = {}
for i, riga in enumerate(ts[958:1053], start=959):
    m = re.match(r"^\s+([a-z_0-9]+): (.+?),\s*$", riga)
    if m: dts[m.group(1)] = (i, num(m.group(2)))
grp = {}
for i, riga in enumerate(ts[1066:1250], start=1067):
    m = re.search(r"key: '([a-z_0-9]+)'", riga)
    if m:
        mn = re.search(r"\bmin: ([-0-9._]+)", riga); mx = re.search(r"\bmax: ([-0-9._]+)", riga)
        grp[m.group(1)] = (i, float(mn.group(1).replace("_", "")) if mn else None, float(mx.group(1).replace("_", "")) if mx else None)
print("chiavi: Python _SPEC=%d  TS PARAM_DEFAULTS=%d  TS GROUPS=%d" % (len(spec), len(dts), len(grp)))
print("solo Python:", sorted(set(spec) - set(dts)), " solo TS defaults:", sorted(set(dts) - set(spec)))
print("in GROUPS non in Python:", sorted(set(grp) - set(spec)), " in Python non in GROUPS:", sorted(set(spec) - set(grp)))
diff = 0
for k, (i, d, lo, hi) in spec.items():
    if k in dts and dts[k][1] != d:
        diff += 1; print("DEFAULT DIVERSO %s: py %s (:%d) ts %s (:%d)" % (k, d, i, dts[k][1], dts[k][0]))
    if k in grp:
        if (grp[k][1] is not None and lo is not None and grp[k][1] != lo) or (grp[k][2] is not None and hi is not None and grp[k][2] != hi):
            diff += 1; print("LIMITI DIVERSI %s: py [%s,%s] (:%d) ts [%s,%s] (:%d)" % (k, lo, hi, i, grp[k][1], grp[k][2], grp[k][0]))
print("differenze default/limiti:", diff)
print("chiavi TS GROUPS senza min/max (select/boolean/testo):", len([k for k, v in grp.items() if v[1] is None and v[2] is None]))
