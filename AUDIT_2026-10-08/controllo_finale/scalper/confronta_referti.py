# -*- coding: utf-8 -*-
"""Confronto scenario per scenario fra referti del banco (certifica scalper_calcio).

Uso:
    python confronta_referti.py NUOVO.txt --r1 a.txt b.txt ... --r2 c.txt d.txt ...

Spezza ogni referto in blocchi di scenario: un blocco comincia con la riga di esito
(`OK|KO|NE  <evento> [<scenario>] ...`) e prosegue sulle righe rientrate di 6 spazi.
Esclusi dal confronto: righe `tempo:`, LENTO, TEMPO TOTALE, `worker:`, `MEMORIA:`,
righe di log `LIVELLO:modulo:`, impronta del codice, comando, percorso delle registrazioni.
Per ogni scenario del nuovo referto: se e' in R1 confronta con R1, altrimenti con R2,
altrimenti lo dichiara NUOVO. Stampa le differenze riga per riga (PRIMA/DOPO).
Con --maschera-id (seconda passata) gli identificativi numerici a 18 cifre diventano <ID18>:
serve solo a dire se, tolti quelli, resta altro di diverso.
"""
import argparse
import difflib
import re
import sys

RE_ESITO = re.compile(r"^(OK|KO|NE)\s+(\d+)(?:\s+\[([^\]]+)\])?\s+tick=")
SCENARIO_UNICO = None
RE_LOG = re.compile(r"^\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL):[\w.]+:")
ESCLUSE = ("tempo:", "LENTO", "TEMPO TOTALE", "worker:", "MEMORIA:")


def da_escludere(riga):
    s = riga.strip()
    if RE_LOG.match(riga):
        return True
    for p in ESCLUSE:
        if s.startswith(p) or (p in ("LENTO", "TEMPO TOTALE") and p in s):
            return True
    return False


MASCHERA_ID = False


def normalizza(riga):
    # percorso delle registrazioni e impronta del codice: mai confrontati
    if MASCHERA_ID:
        # seconda passata (opzione --maschera-id): identificativi d'ordine a 18 cifre
        riga = re.sub(r"\b\d{18}\b", "<ID18>", riga)
    riga = re.sub(r"/\S*_live_raw", "<RAW>", riga)
    riga = re.sub(r"codice bot [0-9a-f]+ \(\d+ file\)", "codice bot <IMPRONTA>", riga)
    return riga.rstrip()


def spezza(percorso):
    """Ritorna {(evento, scenario): [righe]} e la lista d'ordine."""
    blocchi = {}
    corrente = None
    with open(percorso, encoding="utf-8", errors="replace") as f:
        for riga in f:
            riga = riga.rstrip("\n")
            m = RE_ESITO.match(riga)
            if m:
                # referto di un solo scenario: il banco non stampa [scenario]
                chiave = (m.group(2), m.group(3) or SCENARIO_UNICO)
                if m.group(3) is None:
                    riga = riga.replace(m.group(2) + "  tick=",
                                        "%s [%s]  tick=" % (m.group(2), SCENARIO_UNICO), 1)
                if chiave in blocchi:
                    print("ATTENZIONE: scenario ripetuto %s in %s" % (chiave, percorso))
                corrente = chiave
                blocchi[chiave] = [normalizza(riga)]
                continue
            if corrente is None:
                continue
            if RE_LOG.match(riga):
                continue  # log interlacciati: esclusi, non chiudono il blocco
            if riga.startswith("      "):
                if not da_escludere(riga):
                    blocchi[corrente].append(normalizza(riga))
                continue
            corrente = None  # riga non rientrata: fine del blocco
    return blocchi


def carica(percorsi):
    tutti = {}
    for p in percorsi:
        for k, v in spezza(p).items():
            if k in tutti:
                print("ATTENZIONE: scenario %s in piu' file di riferimento" % (k,))
            tutti[k] = (p, v)
    return tutti


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nuovo")
    ap.add_argument("--r1", nargs="*", default=[])
    ap.add_argument("--r2", nargs="*", default=[])
    ap.add_argument("--maschera-id", action="store_true",
                    help="seconda passata: maschera gli identificativi a 18 cifre")
    ap.add_argument("--scenario-unico", default=None,
                    help="nome dello scenario per un referto lanciato con un solo scenario")
    a = ap.parse_args()
    global MASCHERA_ID, SCENARIO_UNICO
    MASCHERA_ID = a.maschera_id
    SCENARIO_UNICO = a.scenario_unico
    nuovo = spezza(a.nuovo)
    r1, r2 = carica(a.r1), carica(a.r2)
    print("referto nuovo: %s (%d scenari)" % (a.nuovo, len(nuovo)))
    print("R1: %d scenari, R2: %d scenari" % (len(r1), len(r2)))
    riassunto = []
    for chiave, righe in nuovo.items():
        if chiave in r1:
            rif, (fonte, vecchie) = "R1", r1[chiave]
        elif chiave in r2:
            rif, (fonte, vecchie) = "R2", r2[chiave]
        else:
            riassunto.append((chiave, "NUOVO", righe[0][:3].strip(), "-", 0))
            print("\n=== %s [%s] NUOVO (assente da R1 e R2)" % chiave)
            for r in righe:
                print("    " + r)
            continue
        diff = list(difflib.unified_diff(vecchie, righe, "PRIMA " + fonte, "DOPO " + a.nuovo,
                                         n=0, lineterm=""))
        uguale = not diff
        riassunto.append((chiave, rif, righe[0][:3].strip(), vecchie[0][:3].strip(),
                          0 if uguale else sum(1 for d in diff if d[:1] in "+-" and d[:3] not in ("+++", "---"))))
        if not uguale:
            print("\n=== %s [%s] DIVERSO da %s (%s)" % (chiave[0], chiave[1], rif, fonte))
            for d in diff:
                print("    " + d)
    mancanti = [k for k in list(r1) + list(r2) if k not in nuovo and k[0] in {c[0] for c in nuovo}]
    print("\n=== RIASSUNTO")
    print("evento | scenario | rif | esito DOPO | esito PRIMA | righe diverse")
    for (ev, sc), rif, dopo, prima, n in riassunto:
        print("%s | %s | %s | %s | %s | %d" % (ev, sc, rif, dopo, prima, n))
    for k in sorted(set(mancanti)):
        print("MANCANTE nel nuovo referto: %s [%s]" % k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
