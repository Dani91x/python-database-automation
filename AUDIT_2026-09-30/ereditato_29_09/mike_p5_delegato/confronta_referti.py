"""Confronto di due referti del banco di Mike, scenario per scenario, tolte le
sole righe dei tempi. Uso: python confronta_referti.py <riferimento> <nuovo>"""
import re
import sys


def scenari(path):
    out = {}
    cur = None
    for riga in open(path, encoding="utf-8", errors="replace"):
        riga = riga.rstrip("\n")
        m = re.match(r"^(OK|KO)\s+(\S+) \[([^\]]+)\] <([^>]+)>", riga)
        if m:
            cur = f"{m.group(3)}<{m.group(4)}>"
            out[cur] = [re.sub(r"\s+", " ", riga)]
            continue
        if cur is None:
            continue
        if not riga.startswith("      "):
            cur = None
            continue
        if "tempo:" in riga or "tick/s" in riga:
            continue
        out[cur].append(riga.strip())
    return out


def main():
    a, b = scenari(sys.argv[1]), scenari(sys.argv[2])
    diversi = 0
    for k in sorted(set(a) | set(b)):
        if a.get(k) == b.get(k):
            print(f"IDENTICO  {k}")
            continue
        diversi += 1
        print(f"DIVERSO   {k}")
        ra, rb = a.get(k, []), b.get(k, [])
        for x in ra:
            if x not in rb:
                print("   - " + x[:220])
        for x in rb:
            if x not in ra:
                print("   + " + x[:220])
    print(f"scenari diversi: {diversi} su {len(set(a) | set(b))}")


if __name__ == "__main__":
    main()
