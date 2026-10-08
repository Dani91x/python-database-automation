"""Classificatore delle differenze tra due referti di certifica (controllo finale, 08/10/2026).

Uso: python classifica.py PRIMA.txt DOPO.txt
Confronta scenario per scenario (riga di esito + tutte le righe del blocco) e la coda
(sommario dei controlli). Esclude: tempi, LENTO, TEMPO TOTALE, `worker:`, `MEMORIA:`,
righe di log `LIVELLO:modulo:`, impronta del codice, comando, percorso, righe vuote.
Ogni riga diversa e' classificata:
  A-mercato   `chiamate al mercato:` uguale tolti i conteggi di list_today_football_events
  A-attivita  `attivita' del servizio:` uguale tolto `flusso_non_dichiarato xN`
  A-nonesrc   `[NON ESERCITABILE]` uguale tolto il segmento `fixtures_for_window: ...`
  A-nonesrc-sola  nota `[NON ESERCITABILE]` col solo `fixtures_for_window`, nuova nello scenario
  B-safe      note save_event_model / NON ESERCITABILE get_event (spostamento di scenario)
  NON-ATTESA  tutto il resto (stampata per intero)
Exit 0 se non ci sono differenze NON ATTESE, 1 altrimenti.
"""
import collections
import re
import sys

ESITO = re.compile(r"^(OK|KO|NE)\s+(\d+) \[([^\]]+)\]")
LOG = re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):[\w.]+:")
ESCLUSE = ("TEMPO TOTALE", "LENTO", "worker:", "MEMORIA:", "comando:", "impronta",
           "codice del bot", "percorso")


def escludi(r):
    s = r.strip()
    if not s or LOG.match(s) or s.startswith("tempo:"):
        return True
    return any(s.startswith(p) or p in s.split(":")[0] for p in ESCLUSE)


def leggi(p):
    blocchi, cur = collections.OrderedDict(), "_testa"
    blocchi[cur] = []
    for r in open(p, encoding="utf-8", errors="replace"):
        r = r.rstrip("\n")
        m = ESITO.match(r)
        if m:
            cur = m.group(3)
            blocchi[cur] = [r]
            continue
        if cur != "_coda" and r and not r.startswith(" ") and cur != "_testa":
            cur = "_coda"
            blocchi.setdefault(cur, [])
        if not escludi(r):
            blocchi[cur].append(r)
    return blocchi


def norm(r):
    s = r
    s = re.sub(r"list_today_football_events x\d+", "list_today_football_events xN", s)
    s = re.sub(r"flusso_non_dichiarato x\d+, |, flusso_non_dichiarato x\d+|flusso_non_dichiarato x\d+", "", s)
    s = re.sub(r"fixtures_for_window: [^|]*\| ", "", s)
    return s


def tipo(r):
    if "save_event_model" in r or ("NON ESERCITABILE" in r and "get_event" in r):
        return "B-safe"
    if "chiamate al mercato:" in r:
        return "A-mercato"
    if "attivita' del servizio:" in r:
        return "A-attivita"
    if "NON ESERCITABILE" in r:
        return "A-nonesrc"
    return None


def main():
    a, b = leggi(sys.argv[1]), leggi(sys.argv[2])
    conteggi = collections.Counter()
    non_attese = []
    for k in list(a) + [k for k in b if k not in a]:
        if k not in a or k not in b:
            non_attese.append((k, "SCENARIO presente solo " + ("PRIMA" if k in a else "DOPO"), ""))
            continue
        if k not in ("_testa", "_coda") and a[k][0] != b[k][0]:
            non_attese.append((k, "PRIMA: " + a[k][0], "DOPO : " + b[k][0]))
        ca, cb = collections.Counter(a[k]), collections.Counter(b[k])
        solo_a = list((ca - cb).elements())
        solo_b = list((cb - ca).elements())
        tipi_a = [r for r in solo_a if tipo(r) not in (None, "B-safe")]
        tipi_b = [r for r in solo_b if tipo(r) not in (None, "B-safe")]
        na = collections.Counter(norm(r) for r in tipi_a)
        nb = collections.Counter(norm(r) for r in tipi_b)
        pari = na & nb
        resto_a, resto_b = na - pari, nb - pari
        for r in tipi_a:
            if resto_a[norm(r)] > 0:
                resto_a[norm(r)] -= 1
                non_attese.append((k, "PRIMA: " + r, ""))
            else:
                conteggi[tipo(r)] += 1
        for r in tipi_b:
            if re.search(r"\[NON ESERCITABILE\][^|]*: fixtures_for_window: [^|]*$", r) and resto_b[norm(r)] > 0:
                # la nota NON ESERCITABILE fixtures_for_window, da sola, in uno scenario che prima non ne aveva
                resto_b[norm(r)] -= 1
                conteggi["A-nonesrc-sola"] += 1
                continue
            if resto_b[norm(r)] > 0:
                resto_b[norm(r)] -= 1
                non_attese.append((k, "DOPO : " + r, ""))
        for lato, righe in (("PRIMA", solo_a), ("DOPO ", solo_b)):
            for r in righe:
                if tipo(r) == "B-safe":
                    conteggi[("B-safe", lato.strip())] += 1
                    print(f"[{k}] B-safe {lato}: {r.strip()}")
                elif tipo(r) is None and not (k not in ("_testa", "_coda") and r == (a[k][0] if lato == "PRIMA" else b[k][0])):
                    non_attese.append((k, lato + ": " + r, ""))
        # le righe di esito si confrontano sopra; qui solo sanita' degli ordini
    print("ATTESE (coppie di righe PRIMA/DOPO):", dict(conteggi))
    print("NON ATTESE:", len(non_attese))
    for k, x, y in non_attese:
        print(f"  [{k}] {x}")
        if y:
            print(f"  [{k}] {y}")
    return 1 if non_attese else 0


if __name__ == "__main__":
    sys.exit(main())
