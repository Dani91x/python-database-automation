"""Controllo di consegna del cantiere C: fine riga coerenti (CRLF dove il file
e' CRLF), nessun BOM, righe AGGIUNTE solo ASCII, file nuovi solo ASCII.

    .venv\\Scripts\\python.exe AUDIT_2026-09-28\\cantiere_c\\controllo_consegna.py
"""
import io
import os
import re
import subprocess

out = subprocess.run(["git", "status", "--porcelain", "-uall"], capture_output=True,
                     text=True).stdout
files = [l[3:].strip() for l in out.splitlines() if l[3:].strip().endswith((".py", ".sql"))]
for p in files:
    with io.open(p, encoding="utf-8", newline="") as f:
        d = f.read()
    crlf, soli = d.count("\r\n"), len(re.findall(r"(?<!\r)\n", d))
    if crlf and soli:
        d = re.sub(r"(?<!\r)\n", "\r\n", d)
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(d)
        print("EOL corretti", p, soli)
    if d.startswith("\ufeff"):
        print("BOM", p)
diff = subprocess.run(["git", "diff", "-U0"], capture_output=True, text=True,
                      encoding="utf-8").stdout
for riga in diff.splitlines():
    if riga.startswith("+") and not riga.startswith("+++") and re.search(r"[^\x00-\x7f]", riga):
        print("NON ASCII (aggiunta):", riga[:120])
nuovi = [l[3:].strip() for l in out.splitlines() if l.startswith("??")]
for p in nuovi:
    if p.endswith((".py", ".sql")) and os.path.isfile(p):
        for i, r in enumerate(io.open(p, encoding="utf-8"), 1):
            if re.search(r"[^\x00-\x7f]", r):
                print("NON ASCII (file nuovo)", p, i, r.strip()[:80])
print("fine")
