"""Scrive la patch di un blocco (byte esatti, niente ricodifica della shell).
Uso: python fai_patch.py <uscita> <file modificati separati da virgola> <file nuovi separati da virgola>"""
import subprocess
import sys

out, mod, nuovi = sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""
parti = [subprocess.run(["git", "diff", "--", *[m for m in mod.split(",") if m]],
                        capture_output=True, check=True).stdout]
for n in [x for x in nuovi.split(",") if x]:
    r = subprocess.run(["git", "diff", "--no-index", "--", "/dev/null", n], capture_output=True)
    parti.append(r.stdout)
with open(out, "wb") as f:
    f.write(b"".join(parti))
print(out, sum(len(p) for p in parti), "byte")
