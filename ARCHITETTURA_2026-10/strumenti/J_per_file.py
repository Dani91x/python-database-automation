# Misura usa-e-getta scheda J: per ogni file non test di pages/components/lib una riga con
# righe, n. data-testid, n. bottoni, n. campi, RPC/tabelle/canali diretti, prima riga di commento.
# Sola lettura. Uso: PYTHONIOENCODING=utf-8 python ARCHITETTURA_2026-10/strumenti/J_per_file.py > dati_J/per_file.tsv
import re, subprocess
fs = [f for f in subprocess.run(["git", "ls-files", "frontend/src"], capture_output=True, text=True).stdout.split("\n") if f]
ist = lambda f: bool(re.search(r"\.(test|spec)\.", f))
P = dict(
  testid=re.compile(r"data-testid="), button=re.compile(r"<(Button|button)\b"),
  campo=re.compile(r"<(Input|input|Switch|Checkbox|Select|select|textarea|Slider)\b"),
  rpc=re.compile(r"\.rpc\(\s*['\"`]([A-Za-z0-9_]+)"), frm=re.compile(r"\.from\(\s*['\"`]([A-Za-z0-9_]+)"),
  can=re.compile(r"getLocalChannel\(\s*['\"`]?([A-Za-z_]+)"), iv=re.compile(r"setInterval\("),
  rt=re.compile(r"postgres_changes"))
print("file\triga\ttestid\tbottoni\tcampi\tsetInterval\trealtime\trpc\ttabelle\tcanali\tdescrizione")
for f in fs:
    if ist(f) or not f.endswith((".ts", ".tsx")): continue
    if not f.startswith(("frontend/src/pages/", "frontend/src/components/", "frontend/src/lib/", "frontend/src/hooks/")): continue
    t = open(f, encoding="utf-8", errors="replace").read()
    c = {k: len(p.findall(t)) for k, p in P.items() if k in ("testid","button","campo","iv","rt")}
    rpc = sorted(set(P["rpc"].findall(t))); frm = sorted(set(P["frm"].findall(t))); can = sorted(set(P["can"].findall(t)))
    desc = ""
    for l in t.split("\n")[:25]:
        s = l.strip()
        if s.startswith(("//", "/*", "*")):
            s = s.lstrip("/*").strip(" =-")
            if len(s) > 12 and not s.startswith("eslint"): desc = s[:140]; break
    print(f"{f[13:]}\t{t.count(chr(10))+1}\t{c['testid']}\t{c['button']}\t{c['campo']}\t{c['iv']}\t{c['rt']}\t{','.join(rpc)[:150]}\t{','.join(frm)}\t{','.join(can)}\t{desc}")
