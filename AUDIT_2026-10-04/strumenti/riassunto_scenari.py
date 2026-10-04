"""Per ogni scenario di un referto di ``certifica``: righe per stato, P&L, rifiuti
INVALID_BET_SIZE, K2 e CP1, attivita' place_parziale. Stampa prima/dopo affiancati.
ASCII-only. Uso: python riassunto_scenari.py <prima.txt> <dopo.txt>
"""
import re
import sys

CAMPI = [("stati", re.compile(r"righe per stato: (\{.*\})")),
         ("pnl", re.compile(r"P&L del replay: (.*?) \(non")),
         ("rifiuti", re.compile(r"(\d+) rifiutati INVALID_BET_SIZE")),
         ("K2", re.compile(r"K2   PROCESSO \S+\s+(x\d+)")),
         ("CP1", re.compile(r"^\s*nota:\s+CP1 .*?(x\d+)")),
         ("parziale", re.compile(r"place_parziale x(\d+)"))]


def leggi(p):
    out, cur = {}, None
    for r in open(p, encoding="utf-8", errors="replace"):
        m = re.search(r"nota: scenario=([\w-]+)", r)
        if m:
            cur = m.group(1)
            out.setdefault(cur, {})
            continue
        if cur is None:
            continue
        for k, rx in CAMPI:
            m = rx.search(r)
            if m and k not in out[cur]:
                out[cur][k] = m.group(1)
    return out


a, b = leggi(sys.argv[1]), leggi(sys.argv[2])
for s in a:
    x, y = a[s], b.get(s, {})
    diff = {k: (x.get(k), y.get(k)) for k, _ in CAMPI if x.get(k) != y.get(k)}
    print(f"{s}: " + ("identico" if not diff else
                      "; ".join(f"{k}: {p} -> {d}" for k, (p, d) in diff.items())))
