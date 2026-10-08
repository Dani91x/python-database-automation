"""Diff dei referti PRIMA/DOPO per i 5 scenari di riferimento: esclusi tempi, impronta,
comando e percorso; gli scenari nuovi (solo DOPO) si elencano a parte."""
import re
import sys

D = "/home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd/AUDIT_2026-10-08/W3B"
NUOVI = ("ordine-esterno", "ordine-esterno-altro-mercato")


def blocchi(path):
    """{scenario: [righe]} + righe di testa/coda."""
    out = {}
    cur = "_testa"
    for r in open(path, encoding="utf-8", errors="replace").read().splitlines():
        m = re.match(r"^(OK|KO|NE)\s+\d+ \[([^\]]+)\]", r)
        if m:
            cur = m.group(2)
        elif r.startswith("ESITO:"):
            cur = "_coda"
        out.setdefault(cur, []).append(r)
    return out


def pulisci(righe):
    tolte = ("tempo:", "TEMPO TOTALE", "LENTO", "codice bot", "comando:", "registrazioni:",
             "SCENARI:")
    return [r for r in righe if not any(t in r for t in tolte)]


for ev in ("35797769", "35760084"):
    p = blocchi("%s/prima_%s.txt" % (D, ev))
    d = blocchi("%s/dopo_%s.txt" % (D, ev))
    print("=== %s" % ev)
    for sc in [k for k in p if not k.startswith("_")]:
        a, b = pulisci(p[sc]), pulisci(d.get(sc, []))
        if a == b:
            print("  %-30s IDENTICO (%d righe)" % (sc, len(a)))
        else:
            print("  %-30s DIVERSO" % sc)
            import difflib
            for x in difflib.unified_diff(a, b, lineterm="", n=0):
                print("     " + x[:220])
    for sc in NUOVI:
        print("  %-30s NUOVO: %s" % (sc, (d.get(sc) or ["assente"])[0][:150]))
    import difflib
    for x in difflib.unified_diff(pulisci(p.get("_coda", [])), pulisci(d.get("_coda", [])),
                                  lineterm="", n=0):
        print("   coda " + x[:200])
