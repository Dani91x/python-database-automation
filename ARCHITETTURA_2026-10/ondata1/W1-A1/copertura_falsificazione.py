import json
import re
import subprocess
import sys

d = json.load(open(sys.argv[1]))
print(len(d), "mutazioni;", sum(1 for x in d if x.get("n_rossi", 0) > 0), "rosse;",
      all(x.get("ripristino_ok") for x in d), "ripristini ok")
for x in d:
    if not x.get("n_rossi"):
        print("VERDE:", x)
rossi = set()
for x in d:
    for r in x.get("rossi", []):
        if "::" not in r:
            continue
        rossi.add(re.sub(r"\[.*", "", r.split("::", 1)[1]))
out = subprocess.run([sys.executable, "-m", "pytest", "Betfair/nucleo/betfair/tests/", "-q", "-p", "no:cacheprovider",
                      "--collect-only"], capture_output=True, text=True).stdout
tutti = {re.sub(r"\[.*", "", l.split("::", 1)[1]) for l in out.splitlines() if "::" in l}
print(len(tutti), "funzioni;", len(tutti & rossi), "viste rosse")
print("MAI ROSSE:", sorted(tutti - rossi))
casi = {l.split("::", 1)[1] for l in out.splitlines() if "::" in l}
rc = {r.split("::", 1)[1] for x in d for r in x.get("rossi", []) if "::" in r}
print(len(casi), "casi;", len(casi & rc), "casi visti rossi")
print("CASI MAI ROSSI:", sorted(casi - rc))
