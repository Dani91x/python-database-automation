"""Confronto per scenario di due referti `--scenari tutti` (esclusi tempi e hash).
Uso: python3 per_scenario.py PRIMA.txt DOPO.txt"""
import difflib
import re
import sys

TESTA = re.compile(r"^(OK|KO|NE)\s+(\d+) \[([^\]]+)\]")


def blocchi(p):
    out, nome, coda = {}, None, []
    for r in open(p, encoding="utf-8", errors="replace"):
        r = r.rstrip("\n")
        if r.startswith("CRITICAL:") or re.match(r"^\s*tempo: ", r) or r.startswith("TEMPO TOTALE"):
            continue
        r = re.sub(r"codice bot [0-9a-f]+ ", "codice bot <hash> ", r)
        r = re.sub(r"registrazioni: (\d+) in \S+", r"registrazioni: \1 in <dir>", r)
        m = TESTA.match(r)
        if m:
            nome = m.group(3)
            out[nome] = [r]
            continue
        if r.startswith("ESITO:"):
            nome = "_coda"
            out[nome] = []
        if nome is None:
            coda.append(r)
        else:
            out[nome].append(r)
    out["_testa"] = coda
    return out


a, b = blocchi(sys.argv[1]), blocchi(sys.argv[2])
for nome in list(a) + [n for n in b if n not in a]:
    d = list(difflib.unified_diff(a.get(nome, []), b.get(nome, []), n=0, lineterm=""))
    print("=" * 20, nome, "IDENTICO" if not d else "%d righe diverse" % len([x for x in d if x[:1] in "+-" and not x.startswith(("+++", "---"))]))
    for x in d[2:]:
        if not x.startswith("@@"):
            print("   ", x[:330])
