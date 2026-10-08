# Misura usa-e-getta per la scheda J (frontend): righe per cartella e per tipo, accessi ai dati.
# Sola lettura. Uso: python ARCHITETTURA_2026-10/strumenti/misura_frontend_J.py
import re, subprocess, collections, sys
out = subprocess.run(["git", "ls-files", "frontend/src"], capture_output=True, text=True).stdout.split("\n")
files = [f for f in out if f]
def n(f):
    with open(f, encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)
istest = lambda f: bool(re.search(r"\.(test|spec)\.", f))
code = [f for f in files if f.endswith((".ts", ".tsx")) and not istest(f)]
tests = [f for f in files if istest(f)]
if len(sys.argv) < 2:
    print("file codice ts/tsx:", len(code), "righe:", sum(n(f) for f in code))
    print("file test:", len(tests), "righe:", sum(n(f) for f in tests))
    other = [f for f in files if not f.endswith((".ts", ".tsx"))]
    print("altri file:", [(f, n(f)) for f in other if f.endswith((".css", ".js", ".json"))][:20])
    d = collections.defaultdict(lambda: [0, 0])
    for f in code:
        k = "/".join(f.split("/")[:-1])
        d[k][0] += n(f); d[k][1] += 1
    for k, v in sorted(d.items(), key=lambda x: -x[1][0]):
        print(v[0], v[1], k)


# --- accessi ai dati: rpc, from, canali locali, polling ---------------------
if len(sys.argv) > 1 and sys.argv[1] == "accessi":
    pat = {
        "rpc": re.compile(r"\.rpc\(\s*['\"`]([A-Za-z0-9_]+)['\"`]"),
        "rpc_dyn": re.compile(r"\.rpc\(\s*([^'\"`\s][^,)]*)"),
        "from": re.compile(r"\.from\(\s*['\"`]([A-Za-z0-9_]+)['\"`]"),
        "canale": re.compile(r"getLocalChannel\(\s*['\"`]?([A-Za-z_]+)"),
        "interval": re.compile(r"(setInterval\(|refetchInterval|POLL[A-Z_]*\s*=|_MS\s*=\s*\d)"),
        "realtime": re.compile(r"\.channel\(|postgres_changes|\.on\(\s*['\"]postgres"),
        "functions": re.compile(r"functions\.invoke\(\s*['\"`]([A-Za-z0-9_\-]+)"),
        "fetch": re.compile(r"\bfetch\(\s*([`'\"][^`'\"]{0,80})"),
    }
    for f in code:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                for k, p in pat.items():
                    for m in p.finditer(line):
                        print(f"{k}\t{f}:{i}\t{(m.group(1) if m.groups() else m.group(0)).strip()[:90]}")

# --- ancore della UI: data-testid, pulsanti, esportazioni, localStorage ------
if len(sys.argv) > 1 and sys.argv[1] == "ancore":
    pat = {
        "testid": re.compile(r"data-testid=(?:\"([^\"]+)\"|\{`([^`]+)`\}|\{([^}]+)\})"),
        "button": re.compile(r"<(Button|button)\b"),
        "export": re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?(function|const|class|interface|type|enum)\s+([A-Za-z0-9_]+)"),
        "storage": re.compile(r"(localStorage|sessionStorage)\.(getItem|setItem|removeItem)\(\s*([^,)]+)"),
        "input": re.compile(r"<(Input|input|Switch|Checkbox|Select|select|textarea|Slider)\b"),
    }
    for f in code:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                for k, p in pat.items():
                    m = p.search(line)
                    if m:
                        g = [x for x in m.groups() if x]
                        print(f"{k}\t{f}:{i}\t{' '.join(g)[:90]}")
