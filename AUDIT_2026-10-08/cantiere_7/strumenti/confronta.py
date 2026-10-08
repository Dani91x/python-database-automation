"""Confronto di due referti del banco ESCLUSI tempi e hash (regola §0.4).
Uso: python3 confronta.py PRIMA.txt DOPO.txt
"""
import difflib
import re
import sys

VIA = [
    re.compile(r"^\s*tempo: "),                     # secondi e tick/s per scenario
    re.compile(r"^TEMPO TOTALE"),
    re.compile(r"^\s*LENTO"),
]
SOSTITUISCI = [
    (re.compile(r"codice bot [0-9a-f]+ "), "codice bot <hash> "),
    (re.compile(r"registrazioni: (\d+) in \S+"), r"registrazioni: \1 in <dir>"),
]


def righe(p):
    out = []
    for r in open(p, encoding="utf-8", errors="replace"):
        r = r.rstrip("\n")
        if r.startswith("CRITICAL:") or any(v.search(r) for v in VIA):
            continue
        for rx, nuovo in SOSTITUISCI:
            r = rx.sub(nuovo, r)
        out.append(r)
    return out


a, b = righe(sys.argv[1]), righe(sys.argv[2])
diff = list(difflib.unified_diff(a, b, sys.argv[1], sys.argv[2], n=0, lineterm=""))
print("\n".join(diff) if diff else "IDENTICI (esclusi tempi e hash)")
