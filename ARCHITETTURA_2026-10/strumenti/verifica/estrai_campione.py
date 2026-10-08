# -*- coding: utf-8 -*-
"""Estrae a caso (seme fisso) N citazioni `file.py:riga` da un documento del piano.
Uso: python estrai_campione.py <documento.md> [N] [seme]. Sola lettura, usa-e-getta."""
import io
import random
import re
import sys

RE_CIT = re.compile(r"`([A-Za-z0-9_./\-]+\.(?:py|ts|tsx|js|sql|yml))[: ]([0-9]{1,5})(?:-([0-9]{1,5}))?")


def main():
    doc = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    seme = int(sys.argv[3]) if len(sys.argv) > 3 else 20261008
    trovate = []
    for num, riga in enumerate(io.open(doc, encoding="utf-8"), 1):
        for m in RE_CIT.finditer(riga):
            trovate.append((num, m.group(1), m.group(2), m.group(3) or "", riga.strip()[:220]))
    random.Random(seme).shuffle(trovate)
    print("citazioni nel documento:", len(trovate))
    for t in trovate[:n]:
        print("riga_doc=%d | %s:%s%s | %s" % (t[0], t[1], t[2], ("-" + t[3]) if t[3] else "", t[4]))


if __name__ == "__main__":
    main()
