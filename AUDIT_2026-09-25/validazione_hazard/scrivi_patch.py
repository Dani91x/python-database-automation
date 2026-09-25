"""Scrive AUDIT_2026-09-25/validazione_hazard.patch: git diff dei file tracciati +
i file nuovi (.py/.md, cache esclusa) come diff da /dev/null. Nessuna modifica
all'indice di git."""
import os
import subprocess

W = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
out = subprocess.run(["git", "diff", "--", ".gitignore"], cwd=W, capture_output=True, text=True,
                     encoding="utf-8").stdout
st = subprocess.run(["git", "status", "--short", "--untracked-files=all"], cwd=W, capture_output=True,
                    text=True, encoding="utf-8").stdout
nuovi = [l[3:] for l in st.splitlines() if l.startswith("??") and "/cache/" not in l
         and l.endswith((".py", ".md"))]
for f in nuovi:
    out += subprocess.run(["git", "diff", "--no-index", "--", "/dev/null", f], cwd=W, capture_output=True,
                          text=True, encoding="utf-8").stdout
with open(os.path.join(W, "AUDIT_2026-09-25", "validazione_hazard.patch"), "w", encoding="utf-8",
          newline="\n") as fh:
    fh.write(out)
print(len(nuovi), "file nuovi;", out.count("diff --git"), "diff;", out.count("\n"), "righe")
