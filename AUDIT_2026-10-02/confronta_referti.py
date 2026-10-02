"""Confronto riga per riga di due referti del banco, tolte le sole righe dei
tempi, i WARNING del logger e i percorsi/hash che dipendono dal checkout.
Uso: python confronta_referti.py PRIMA.txt DOPO.txt
"""
import difflib
import re
import sys

_VIA = [
    (re.compile(r"WARNING:[^\n]*"), ""),
    (re.compile(r"tempo: .*"), "tempo: X"),
    (re.compile(r"TEMPO TOTALE.*"), "TEMPO TOTALE X"),
    (re.compile(r"DURATA DEL PROFILO RAPIDO.*"), "DURATA X"),
    (re.compile(r"durata replay s: \{[^}]*\}"), "durata replay s: X"),
    (re.compile(r"durata [0-9.]+ s"), "durata X"),
    (re.compile(r"costo del banco sul canale: [0-9.]+ s"), "costo del banco sul canale: X"),
    (re.compile(r"[0-9.]+ tick/s"), ""),
    (re.compile(r"  [0-9.]+ s$"), ""),
    (re.compile(r"registrazioni: 1 in .*"), "registrazioni: 1"),
    (re.compile(r"codice bot [0-9a-f]+"), "codice bot H"),
    # 02/10 (REPLAY VELOCE) - due altri TEMPI, e solo tempi:
    #  * la riga `LENTO:` e' una riga dei tempi del banco (`certifica.PREFISSI_RIGHE_TEMPI`)
    #  * l'id di un ordine flumine mai passato da Betfair e' `str(uuid.uuid1().time)`
    #    (`flumine/order/order.py:78`): l'ORA DEL PC in centinaia di ns, 18 cifre,
    #    diversa a ogni esecuzione dello stesso codice (compare cosi' nei referti del
    #    01/10). I bet id del banco sono di 12 cifre e restano confrontati.
    (re.compile(r"LENTO: .*"), "LENTO: X"),
    (re.compile(r"'1[0-9]{17}'"), "'UUID1_ORA_DEL_PC'"),
]


def norma(percorso):
    testo = open(percorso, encoding="utf-8-sig", errors="replace").read()
    out = []
    for riga in testo.splitlines():
        for rx, sost in _VIA:
            riga = rx.sub(sost, riga)
        riga = riga.rstrip()
        if riga:
            out.append(riga)
    return out


a, b = norma(sys.argv[1]), norma(sys.argv[2])
diff = list(difflib.unified_diff(a, b, "prima", "dopo", n=0, lineterm=""))
print(f"righe prima {len(a)}, dopo {len(b)}, righe diverse {sum(1 for d in diff if d[:1] in '+-' and d[:3] not in ('+++', '---'))}")
for d in diff:
    print(d[:400])
