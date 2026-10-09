import io
sys_stdout_utf8 = True
import re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ESCL = re.compile(r"^\s*(tempo:|worker:|MEMORIA|comando:|BOT:|controlli attivi:|TEMPO TOTALE)|^(INFO|WARNING|ERROR|DEBUG):")
ID18 = re.compile(r"\b\d{18}\b")
def blocchi(p):
    out, cur, nome = {}, [], None
    b = open(p, "rb").read()
    try:
        testo = b.decode("utf-8")
    except UnicodeDecodeError:
        testo = b.decode("cp1252", errors="replace")
    for l in testo.splitlines():
        l = l.rstrip("\r")
        m = re.match(r"^(OK|KO|NE)\s+\d+\s+\[([^\]]+)\]", l)
        if m:
            if nome: out[nome] = cur
            nome, cur = m.group(2), [l]
            continue
        if nome is None: continue
        if l.strip() == "" or l.startswith("MEMORIA") or l.startswith("ESITO"):
            if nome: out[nome] = cur
            nome, cur = None, []
            continue
        cur.append(l)
    if nome: out[nome] = cur
    return out
def norm(ls):
    return [ID18.sub("<id18>", l).replace("�", "?").replace("§", "?") for l in ls if not ESCL.search(l)]
rif, mio = blocchi(sys.argv[1]), blocchi(sys.argv[2])
for s in mio:
    if s not in rif:
        print(f"[{s}] ASSENTE nel riferimento"); continue
    a, b = norm(rif[s]), norm(mio[s])
    if a == b:
        print(f"[{s}] IDENTICO ({len(b)} righe)")
    else:
        sa, sb = set(a), set(b)
        print(f"[{s}] DIVERSO: {len([x for x in a if x not in sb])} righe solo nel riferimento, {len([x for x in b if x not in sa])} solo nel mio")
        for x in a:
            if x not in sb: print("   -", x[:230])
        for x in b:
            if x not in sa: print("   +", x[:230])
