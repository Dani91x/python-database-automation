"""Confronto PRIMA/DOPO dei referti certifica (per scenario)."""
import difflib
import re
import sys

ESITO = re.compile(r"^(OK|KO|NE)\s+(\d+)\s+\[([^\]]+)\]")
SCARTA = re.compile(r"^\s*tempo:|impronta|^TEMPO TOTALE|^LENTO|codice bot|^comando:|registrazioni: \d+ in ")


def leggi(percorso):
    testa, blocchi, ordine, coda = [], {}, [], []
    cur = None
    for riga in open(percorso, encoding="utf-8", errors="replace"):
        riga = riga.rstrip("\n")
        if SCARTA.search(riga):
            continue
        m = ESITO.match(riga)
        if m:
            cur = m.group(3)
            ordine.append(cur)
            blocchi[cur] = [re.sub(r"\s+", " ", riga)]
            continue
        if cur is None:
            testa.append(riga)
        elif riga.startswith("      ") or riga.startswith("\t"):
            blocchi[cur].append(riga)
        else:
            cur = "__CODA__"
            coda.append(riga)
            ordine.append(cur) if cur not in ordine else None
            blocchi.setdefault(cur, [])
    blocchi.pop("__CODA__", None)
    ordine = [o for o in ordine if o != "__CODA__"]
    return testa, blocchi, ordine, coda


def main(prima, dopo):
    tp, bp, op, cp = leggi(prima)
    td, bd, od, cd = leggi(dopo)
    print("### esiti")
    for s in od:
        e = bd[s][0]
        prev = bp.get(s, [None])[0]
        stato = "NUOVO" if prev is None else ("identico" if prev == e else "DIVERSO")
        print(f"- [{stato}] DOPO: `{e}`" + ("" if stato != "DIVERSO" else f"\n  PRIMA: `{prev}`"))
    for s in op:
        if s not in bd:
            print(f"- [SPARITO] PRIMA: `{bp[s][0]}`")
    print("\n### violazioni (viol>0, KO, FALLITO)")
    for s in od:
        for r in bd[s]:
            if re.search(r"viol=[1-9]|VIOLAT|FALLIT|\bKO\b", r):
                print(f"- {s}: {r.strip()}")
    print("\n### righe diverse negli scenari ESISTENTI")
    for s in od:
        if s in bp and bp[s][1:] != bd[s][1:]:
            print(f"#### {s}")
            for r in difflib.unified_diff(bp[s][1:], bd[s][1:], lineterm="", n=0):
                if r.startswith(("---", "+++", "@@")):
                    continue
                print("    " + r)
    print("\n### testa")
    for r in difflib.unified_diff(tp, td, lineterm="", n=0):
        if not r.startswith(("---", "+++", "@@")):
            print("    " + r)
    print("\n### coda")
    for r in difflib.unified_diff(cp, cd, lineterm="", n=0):
        if not r.startswith(("---", "+++", "@@")):
            print("    " + r)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
