# Misura usa-e-getta scheda J: test per area e righe di polling con il periodo.
# Sola lettura. Uso: python ARCHITETTURA_2026-10/strumenti/J_test_e_polling.py [test|polling]
import re, subprocess, collections, sys
fs = [f for f in subprocess.run(["git", "ls-files", "frontend/src"], capture_output=True, text=True).stdout.split("\n") if f]
ist = lambda f: bool(re.search(r"\.(test|spec)\.", f))
modo = sys.argv[1] if len(sys.argv) > 1 else "test"
if modo == "test":
    d = collections.defaultdict(lambda: [0, 0, 0]); tot = [0, 0, 0]
    for f in fs:
        if not ist(f): continue
        t = open(f, encoding="utf-8", errors="replace").read()
        n = len(re.findall(r"^\s*(?:it|test)(?:\.each\([^)]*\))?\s*\(", t, re.M))
        p = f.split("/")
        k = "/".join(p[2:4]) if p[2] == "components" else p[2]
        d[k][0] += 1; d[k][1] += n; d[k][2] += t.count("\n")
    for k, v in sorted(d.items(), key=lambda x: -x[1][1]):
        print(k, "file", v[0], "casi(it/test)", v[1], "righe", v[2]); tot = [a + b for a, b in zip(tot, v)]
    print("TOT file", tot[0], "casi", tot[1], "righe", tot[2])
else:
    pat = re.compile(r"(setInterval\(|refetchInterval|\bPOLL[A-Z_]*\s*=|\b[A-Z_]+_MS\s*=\s*[\d_*. ]+|\bPOLL_SEC\b\s*=)")
    for f in fs:
        if ist(f) or not f.endswith((".ts", ".tsx")): continue
        if "/anteprima/" in f or "/certification/" in f or "/fotografia/" in f: continue
        for i, l in enumerate(open(f, encoding="utf-8", errors="replace"), 1):
            if pat.search(l) and not l.strip().startswith("//") and not l.strip().startswith("*"):
                print(f"{f[13:]}:{i}\t{l.strip()[:130]}")
