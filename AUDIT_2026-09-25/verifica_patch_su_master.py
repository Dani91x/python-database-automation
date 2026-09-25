# Verifica che la patch si applichi PULITA su origin/master: estrae i file toccati da
# origin/master in una cartella temporanea FUORI dal repo e ci lancia `git apply --check`.
import os
import re
import subprocess
import sys
import tempfile

PATCH = os.path.abspath(sys.argv[1])
testo = open(PATCH, "rb").read().decode("utf-8")
toccati = sorted(set(re.findall(r"^--- a/(.+)$", testo, re.M)))
d = tempfile.mkdtemp(prefix="verifica_patch_")
for f in toccati:
    blob = subprocess.run(["git", "show", "origin/master:" + f], capture_output=True, check=True).stdout
    p = os.path.join(d, f)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(blob.replace(b"\r\n", b"\n") if b"\r\n" not in blob else blob)
r = subprocess.run(["git", "apply", "--check", "-v", PATCH], cwd=d, capture_output=True, text=True,
                   env=dict(os.environ, GIT_CEILING_DIRECTORIES=os.path.dirname(d)))
print("file esistenti estratti da origin/master:", len(toccati))
print("git apply --check rc:", r.returncode)
print((r.stderr or r.stdout)[-1500:])
