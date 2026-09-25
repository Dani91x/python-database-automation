# Genera la patch O1+M1+O5 (default ACCESI) + Safe come `git diff origin/master`
# (albero di lavoro contro origin/master, file nuovi compresi se committati o in stage).
# Uso (dalla radice del worktree, dopo `git fetch`):
#     python AUDIT_2026-09-25/genera_patch_o1_m1_o5.py
# Le patch stesse sono escluse dal diff (una patch non contiene se stessa).
import subprocess

base = subprocess.run(["git", "rev-parse", "--short", "origin/master"], capture_output=True,
                      check=True, text=True).stdout.strip()
OUT = f"AUDIT_2026-09-25/o1_m1_o5_default_acceso_su_{base}.patch"
dati = subprocess.run(["git", "diff", "origin/master", "--", ".",
                       ":(exclude)AUDIT_2026-09-25/*.patch"],
                      capture_output=True, check=True).stdout.replace(b"\r\n", b"\n")
open(OUT, "wb").write(dati)
print(OUT, len(dati), "byte, base origin/master", base)
