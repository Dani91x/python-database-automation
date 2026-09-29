"""Mutazioni del COORDINATORE sul pacchetto P5 blocco 1 di Mike (conti del
mercato 4,5 per MERCATO, M3.4) e sul P4 blocco 4.

Ogni mutazione rompe UN punto del codice nuovo: i test devono diventare rossi.
Ripristino da copia in memoria con controllo dell'hash. Si lancia dalla radice
del worktree di verifica.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PY = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.venv\Scripts\python.exe"
ENG = "Betfair/mike/engine.py"
SER = "Betfair/mike/service.py"
TEST = ["Betfair/mike"]

MUT: List[Tuple[str, str, bytes, bytes]] = [
    ("Q1 conti: la puntata sull'altra selezione non conta", ENG,
     b"            # punta sull'altra selezione: se vince la nostra, quella perde\n            w -= s\n            l += s * (p - 1.0)",
     b"            # punta sull'altra selezione: se vince la nostra, quella perde\n            pass"),
    ("Q2 conti: la banca sull'altra selezione non conta", ENG,
     b"            # banca sull'altra selezione: se vince la nostra, quella perde e si incassa\n            w += s\n            l -= s * (p - 1.0)",
     b"            # banca sull'altra selezione: se vince la nostra, quella perde e si incassa\n            pass"),
    ("Q3 conti: la banca sull'altra selezione col segno rovesciato", ENG,
     b"            # banca sull'altra selezione: se vince la nostra, quella perde e si incassa\n            w += s\n            l -= s * (p - 1.0)",
     b"            # banca sull'altra selezione: se vince la nostra, quella perde e si incassa\n            w -= s\n            l += s * (p - 1.0)"),
    ("Q4 chiave del 4,5: la copertura-banca si chiude sulla sua stessa selezione", ENG,
     b"            return (MARKET_OU45, SEL_OVER if sel == SEL_UNDER else SEL_UNDER)",
     b"            return (MARKET_OU45, sel)"),
    ("Q5 chiave del 4,5 a due selezioni: sempre l'Under", ENG,
     b"    return (MARKET_OU45, SEL_UNDER if (w - l) > 0 else SEL_OVER)",
     b"    return (MARKET_OU45, SEL_UNDER)"),
    ("Q6 chiave del 4,5 a due selezioni: piatto non riconosciuto", ENG,
     b"    w, l = exposure(legs, MARKET_OU45, SEL_UNDER)\n    if abs(w - l) < _FLAT_EPS:\n        return None\n    return (MARKET_OU45,",
     b"    w, l = exposure(legs, MARKET_OU45, SEL_UNDER)\n    if False:\n        return None\n    return (MARKET_OU45,"),
    ("Q7 capitale impegnato: la banca conta per l'importo e non per il rischio", ENG,
     b"    return round(sum((float(l.matched) if l.side == \"back\"\n                      else float(l.matched) * (l.fill_price - 1.0))",
     b"    return round(sum((float(l.matched) if l.side == \"back\"\n                      else float(l.matched))"),
    ("Q8 capitale impegnato: la banca di apertura non conta", ENG,
     b"    return round(sum((float(l.matched) if l.side == \"back\"\n                      else float(l.matched) * (l.fill_price - 1.0))",
     b"    return round(sum((float(l.matched) if l.side == \"back\"\n                      else 0.0)"),
    ("Q9 chiusura: non trova l'apertura sull'altra selezione", ENG,
     b"    if ref is not None:\n        return ref\n    return _scegli([l for l in legs if l.market == market and l.role in ruoli])",
     b"    return ref"),
    ("Q10 chiusura della copertura attribuita a un'apertura qualunque", ENG,
     b"    \"over_close\": (\"over_cover\",),",
     b"    \"over_close\": OPENING_ROLES,"),
    ("Q11 stessa posizione: solo la stessa selezione", ENG,
     b"    return m1 == m2 and (s1 == s2 or m1 in LINE)",
     b"    return m1 == m2 and s1 == s2"),
    ("Q12 stessa posizione: anche fra mercati diversi", ENG,
     b"    return m1 == m2 and (s1 == s2 or m1 in LINE)",
     b"    return (s1 == s2 or m1 in LINE)"),
    ("Q13 copertura in volo contata per selezione", ENG,
     b"        if l.role != \"over_cover\" or not (l.is_live or l.needs_reconcile):\n            continue\n        if not _stessa_posizione(l.market, l.selection, market, selection):",
     b"        if l.role != \"over_cover\" or not (l.is_live or l.needs_reconcile):\n            continue\n        if l.market != market or l.selection != selection:"),
    ("Q14 banca in volo contata per selezione", ENG,
     b"        if l.side != \"lay\" or not (l.is_live or l.needs_reconcile):\n            continue\n        if not _stessa_posizione(l.market, l.selection, market, selection):",
     b"        if l.side != \"lay\" or not (l.is_live or l.needs_reconcile):\n            continue\n        if l.market != market or l.selection != selection:"),
    ("Q15 ordini vivi contati per selezione", ENG,
     b"            if l.is_live and _stessa_posizione(l.market, l.selection, market, selection)",
     b"            if l.is_live and l.market == market and l.selection == selection"),
    ("Q16 conto: si sorveglia solo la chiave, non la selezione coi soldi", ENG,
     b"        for altra in selezioni_con_gambe(legs, m):\n            out.add((m, altra))",
     b"        pass"),
    ("Q17 conto: il servizio torna a guardare solo la chiave", SER,
     b"    for (mercato, selezione) in E.selezioni_da_sorvegliare(ctx.legs):",
     b"    for (mercato, selezione) in sorted(aperte):"),
    ("Q18 riepilogo dei cicli: il rischio della banca non entra nello stake", ENG,
     b"        if rischio_banche > 0:\n            stake = round(stake + rischio_banche, 2)",
     b"        if False:\n            stake = round(stake + rischio_banche, 2)"),
    ("Q19 posizione per mercato: abbinato contato per selezione", ENG,
     b"                             if x.market == market\n                             and not x.archived and float(x.matched) > 0), 2)",
     b"                             if x.market == market and x.selection == selection\n                             and not x.archived and float(x.matched) > 0), 2)"),
    ("Q20 chiusura manuale: l'altra banca in volo contata per selezione", ENG,
     b"                  and any(_stessa_posizione(c.market, c.selection, l.market, l.selection)\n                          for c in closes)),",
     b"                  and any(c.market == l.market and c.selection == l.selection\n                          for c in closes)),"),
    ("Q21 chiave del 4,5: posizione corta da una banca NON di apertura scambiata per copertura", ENG,
     b"                               and g.side == \"lay\" and g.role in OPENING_ROLES",
     b"                               and g.side == \"lay\""),
    # ------------------------------------------------------------ P4 blocco 4
    ("R1 punteggio assente: avviso subito", SER,
     b"\"punteggio_assente\",",
     b"\"punteggio_assente\","),
]


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def suite() -> Tuple[bool, str]:
    r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider", "-x"],
                       capture_output=True, text=True, timeout=1800)
    righe = [x for x in (r.stdout or "").splitlines() if x.strip()]
    coda = righe[-1:] or ["?"]
    primo = next((x for x in righe if x.startswith("FAILED") or x.startswith("ERROR")), "")
    return r.returncode == 0, (coda[0] + ("  | " + primo[:150] if primo else ""))


def main() -> int:
    solo = set(sys.argv[1:])
    ok, coda = suite()
    print("BASE (senza mutazioni): %s  %s" % ("VERDE" if ok else "ROSSA", coda), flush=True)
    if not ok:
        return 2
    vive = 0
    fatte = 0
    for nome, f, prima, dopo in MUT:
        if solo and nome.split()[0] not in solo:
            continue
        if prima == dopo:
            continue
        fatte += 1
        p = Path(f)
        orig = p.read_bytes()
        crlf = b"\r\n" in orig
        a = prima.replace(b"\n", b"\r\n") if crlf else prima
        d = dopo.replace(b"\n", b"\r\n") if crlf else dopo
        n = orig.count(a)
        if n != 1:
            print("%-84s ANCORA NON UNICA (%d)" % (nome, n), flush=True)
            vive += 1
            continue
        try:
            p.write_bytes(orig.replace(a, d))
            verde, coda = suite()
        finally:
            p.write_bytes(orig)
        assert md5(p.read_bytes()) == md5(orig)
        errore = "error" in coda and "failed" not in coda
        print("%-84s %s  %s" % (nome, "SOPRAVVISSUTA" if verde else
                                ("ERRORE DI RACCOLTA" if errore else "rossa"), coda), flush=True)
        vive += 1 if (verde or errore) else 0
    print("mutazioni sopravvissute o non valide: %d su %d" % (vive, fatte))
    return 0


if __name__ == "__main__":
    sys.exit(main())
