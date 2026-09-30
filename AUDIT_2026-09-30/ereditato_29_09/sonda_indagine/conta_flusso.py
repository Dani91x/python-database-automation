import json
import sys
from collections import Counter

d = json.load(open(sys.argv[1], encoding="utf-8"))
c = Counter()
for a in d["attivita"]:
    if a["kind"] in ("flusso_interrotto", "flusso_interrotto_senza_rest"):
        c[(a["kind"], tuple(a["payload"].get("mercati") or []))] += 1
for k, v in sorted(c.items()):
    print(k, v)
