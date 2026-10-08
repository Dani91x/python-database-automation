# -*- coding: utf-8 -*-
"""Assembla ARCHITETTURA_2026-10/01_FUNZIONALITA.md dalle schede dei componenti.

Prende da ogni scheda in 03_SCHEDE_COMPONENTI/ la PRIMA riga che definisce ogni
identificatore di funzionalita' (es. `A-001`, `E3-S01`, `J-101`): riga di elenco
(`- A-001 ...`) o di tabella (`| A-001 | ...`). Il testo resta quello della scheda,
con il suo `file:riga`. Rieseguibile: python ARCHITETTURA_2026-10/strumenti/f01_assembla_funzionalita.py
Uso usa-e-getta, non importato dall'app.
"""
import io
import os
import re
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
SCHEDE = os.path.join(RADICE, "03_SCHEDE_COMPONENTI")
USCITA = os.path.join(RADICE, "01_FUNZIONALITA.md")

# identificatore all'inizio di una voce di elenco o di una cella di tabella
RE_VOCE = re.compile(r"^\s*(?:[-*]\s+|\|\s*)(?:\*\*)?`?(?P<id>[A-K][0-9]?-S?[0-9]{2,3})\b`?(?:\*\*)?")

ORDINE = ["A", "B", "C", "D", "E1", "E2", "E3", "E4", "E5", "F", "G", "H", "I", "J", "K"]


def prefisso(nome_file):
    return nome_file.split("_", 1)[0]


def main():
    file_schede = sorted(f for f in os.listdir(SCHEDE) if f.endswith(".md"))
    per_pref = {}
    for f in file_schede:
        per_pref[prefisso(f)] = f
    righe_out = []
    totale = 0
    riassunto = []
    for pref in ORDINE:
        f = per_pref.get(pref)
        if not f:
            riassunto.append((pref, "(scheda mancante)", 0))
            continue
        visti = set()
        voci = []
        with io.open(os.path.join(SCHEDE, f), encoding="utf-8") as h:
            for n, riga in enumerate(h, 1):
                m = RE_VOCE.match(riga)
                if not m:
                    continue
                vid = m.group("id")
                # solo gli id del prefisso della scheda (le citazioni di altre schede no)
                if not re.match(r"^%s-" % re.escape(pref), vid):
                    continue
                if vid in visti:
                    continue
                visti.add(vid)
                testo = riga.strip()
                if testo.startswith("|"):
                    celle = [c.strip() for c in testo.strip("|").split("|")]
                    testo = " -- ".join(c for c in celle if c)
                elif testo[:1] in "-*":
                    testo = testo[1:].strip()
                voci.append((vid, n, testo))
        totale += len(voci)
        riassunto.append((pref, f, len(voci)))
        righe_out.append("")
        righe_out.append("## %s -- `03_SCHEDE_COMPONENTI/%s` (%d voci)" % (pref, f, len(voci)))
        righe_out.append("")
        for vid, n, testo in voci:
            righe_out.append("- %s  [scheda:%d]" % (testo, n))
    testa = [
        "# 01 -- FUNZIONALITA' DEL SOFTWARE (elenco numerato, generato dalle schede)",
        "",
        "Generato da `ARCHITETTURA_2026-10/strumenti/f01_assembla_funzionalita.py` (rieseguibile): per ogni",
        "identificatore la prima riga che lo definisce nella sua scheda, con il `file:riga` di oggi scritto dal",
        "delegato e verificato a campione dal coordinatore (vedi `CRONOSTORIA.md`, blocco del 08/10). `[scheda:N]` =",
        "riga della scheda da cui viene la voce. E' la lista contro cui si misura <<nessuna funzionalita' persa>>:",
        "ogni tappa di `05_PIANO_DI_MIGRAZIONE.md` dichiara quali identificatori sposta e con quale test di parita'.",
        "",
        "Avvertenze: alcune voci raggruppano piu' regole (la scheda le elenca per intero); i buchi di numerazione",
        "sono dei delegati (gruppi), non voci mancanti; le voci [S] (strategia) sono INTOCCABILI e si spostano",
        "identiche. Il dettaglio dei pulsanti e dei testi della UI e' anche in `strumenti/dati_J/ancore.tsv` e",
        "nei documenti `AUDIT_2026-10-01/REDESIGN/inventario_parti/*.md` (citati dalla scheda J).",
        "",
        "| Componente | Scheda | Voci |",
        "|---|---|---|",
    ]
    for pref, f, n in riassunto:
        testa.append("| %s | %s | %d |" % (pref, f, n))
    testa.append("| **Totale** | | **%d** |" % totale)
    with io.open(USCITA, "w", encoding="utf-8", newline="\n") as h:
        h.write("\n".join(testa + righe_out) + "\n")
    print("voci totali:", totale)
    for r in riassunto:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
