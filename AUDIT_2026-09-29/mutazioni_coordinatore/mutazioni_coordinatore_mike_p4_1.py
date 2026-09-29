"""Mutazioni del COORDINATORE sul pacchetto P4, blocco 1 di Mike (ordini).

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
F = "Betfair/mike/service.py"
TEST = ["Betfair/mike"]

MUT: List[Tuple[str, bytes, bytes]] = [
    ("Y1 un fermo nostro torna a contare come rifiuto (richiesta)",
     b"    if not fermo_nostro:\n        _rifiutata(ctx, leg,",
     b"    if True:\n        _rifiutata(ctx, leg,"),
    ("Y2 un fermo nostro torna a contare nel freno della copertura",
     b"    if not fermo_nostro:\n        _esito_rifiuto_mercato(db, ctx, leg,",
     b"    if True:\n        _esito_rifiuto_mercato(db, ctx, leg,"),
    ("Y3 la sospensione letta solo dal mercato Under 3,5",
     b"        return E.stato_mercato(snap.book(l.market, l.selection))",
     b"        return E.stato_mercato(snap.book(E.MARKET_OU35, E.SEL_UNDER))"),
    ("Y4 lo sportello vero non sa rileggere per numero di scommessa",
     b"        return dict(omega_market.order_state_by_bet_id(str(bet_id)) or {\"found\": False})",
     b"        return {\"found\": False}"),
    ("Y5 ordine uscito dai correnti: non si rilegge, resta ignoto",
     b"        if letto is not None and letto[0] in (_ESITO_SCADUTO, _ESITO_ABBINATO, _ESITO_PARZIALE):",
     b"        if False:"),
    ("Y6 alla riapertura si legge anche a mercato ancora sospeso",
     b"    if any(s != E.STATO_APERTO for s in stati):",
     b"    if False:"),
    ("Y7 un ritiro nostro scritto come rifiuto",
     b"                                      }.get(str(reason), ESITO_RITIRATO_DA_NOI)})",
     b"                                      }.get(str(reason), ESITO_RIFIUTATO)})"),
    ("Y8 un ordine decaduto non detto «cancellato da Betfair»",
     b"                 \"esito_ordine\": ESITO_CANCELLATO_DA_BETFAIR})",
     b"                 \"esito_ordine\": ESITO_RITIRATO_DA_NOI})"),
    ("Y9 il fermo nostro detto «rifiutato»",
     b"    if fermo_nostro:\n        return ESITO_FERMATO_DA_NOI",
     b"    if False:\n        return ESITO_FERMATO_DA_NOI"),
]


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def suite() -> Tuple[bool, str]:
    r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider", "-x"],
                       capture_output=True, text=True, timeout=1200)
    coda = [x for x in (r.stdout or "").splitlines() if x.strip()][-1:]
    return r.returncode == 0, (coda[0] if coda else "?")


def main() -> int:
    ok, coda = suite()
    print("BASE (senza mutazioni): %s  %s" % ("VERDE" if ok else "ROSSA", coda), flush=True)
    if not ok:
        return 2
    p = Path(F)
    orig = p.read_bytes()
    crlf = b"\r\n" in orig
    vive = 0
    for nome, prima, dopo in MUT:
        a = prima.replace(b"\n", b"\r\n") if crlf else prima
        d = dopo.replace(b"\n", b"\r\n") if crlf else dopo
        n = orig.count(a)
        if n != 1:
            print("%-62s ANCORA NON UNICA (%d)" % (nome, n), flush=True)
            vive += 1
            continue
        try:
            p.write_bytes(orig.replace(a, d))
            verde, coda = suite()
        finally:
            p.write_bytes(orig)
        assert md5(p.read_bytes()) == md5(orig)
        errore = "error" in coda and "failed" not in coda
        print("%-62s %s  %s" % (nome, "SOPRAVVISSUTA" if verde else
                                ("ERRORE DI RACCOLTA" if errore else "rossa"), coda), flush=True)
        vive += 1 if (verde or errore) else 0
    print("mutazioni sopravvissute o non valide: %d su %d" % (vive, len(MUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
