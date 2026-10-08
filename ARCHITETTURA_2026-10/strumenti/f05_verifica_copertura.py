# -*- coding: utf-8 -*-
"""Verifica del coordinatore: ogni identificatore di 01_FUNZIONALITA.md compare in UNA sola riga
della tabella della sezione 4 di 05_PIANO_DI_MIGRAZIONE.md (intervalli X-a..X-b espansi sui soli id
esistenti in 01). Uso usa-e-getta, sola lettura."""
import io
import os
import re
from collections import Counter

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RE_ID = re.compile(r"\b([A-K][0-9]?)-(S?)([0-9]{2,3})\b")


def chiave(m):
    return (m.group(1), m.group(2), int(m.group(3)))


def ids_01():
    out = []
    for riga in io.open(os.path.join(R, "01_FUNZIONALITA.md"), encoding="utf-8"):
        if riga.startswith("- "):
            # tutti gli id del proprio prefisso nella testa della voce (A-013 e A-014 sulla stessa riga)
            testa = riga[:40]
            for m in RE_ID.finditer(testa):
                out.append((chiave(m), m.group(0)))
    return out


def main():
    tutti = ids_01()
    esistenti = {k for k, _ in tutti}
    testo = io.open(os.path.join(R, "05_PIANO_DI_MIGRAZIONE.md"), encoding="utf-8").read()
    sez = testo.split("## 4.", 1)[1].split("\n## 5.", 1)[0]
    conta = Counter()
    for riga in sez.splitlines():
        if not riga.startswith("| T") and not riga.startswith("| RESTA") and not riga.startswith("| K"):
            if not riga.startswith("|") or riga.startswith("|---") or riga.startswith("| Tappa"):
                continue
        celle = riga.split("|")
        if len(celle) < 3:
            continue
        cella = celle[2]
        for m in re.finditer(r"`([A-K][0-9]?)-(S?)([0-9]{2,3})(?:\.\.([A-K][0-9]?)-(S?)([0-9]{2,3}))?`", cella):
            p, s, a = m.group(1), m.group(2), int(m.group(3))
            if m.group(4):
                b = int(m.group(6))
                for k in esistenti:
                    if k[0] == p and k[1] == s and a <= k[2] <= b:
                        conta[k] += 1
            else:
                conta[(p, s, a)] += 1
    mancanti = sorted(k for k in esistenti if conta[k] == 0)
    doppi = sorted(k for k in esistenti if conta[k] > 1)
    inesistenti = sorted(k for k in conta if k not in esistenti)
    print("id in 01:", len(esistenti), "| coperti:", len(esistenti) - len(mancanti),
          "| mancanti:", len(mancanti), "| doppi:", len(doppi), "| inesistenti citati:", len(inesistenti))
    for nome, lst in (("mancanti", mancanti), ("doppi", doppi), ("inesistenti", inesistenti)):
        if lst:
            print(nome, ["%s-%s%03d" % k for k in lst[:30]])


if __name__ == "__main__":
    main()
