"""Confronto riga per riga di due referti di ``certifica``, senza le righe che cambiano a
ogni corsa (tempi, durate, worker, impronta del codice, avvisi di log). ASCII-only.

Uso: python confronta_referti.py <prima.txt> <dopo.txt>
"""
import difflib
import re
import sys

VARIABILI = re.compile(
    r"(TEMPO TOTALE|exit=|durata|DURATA|worker:|impronta|codice bot|^WARNING:|^INFO:|"
    r"\d+\.\d+ s\b|\(\d+\.\d+ s\)|s di mercato|costo del banco|^comando:)")


def righe(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        out = []
        for r in f:
            r = r.rstrip("\n")
            if VARIABILI.search(r):
                continue
            out.append(re.sub(r"\b\d+\.\d+s\b", "<t>", r))
        return out


a, b = righe(sys.argv[1]), righe(sys.argv[2])
d = list(difflib.unified_diff(a, b, sys.argv[1], sys.argv[2], n=0, lineterm=""))
print("\n".join(d) if d else "IDENTICI (al netto di tempi e avvisi)")
