"""Mutazioni del COORDINATORE sul pacchetto P5 blocco 4 + 4B di Mike (banco
ritarato per la copertura come banca Under 4,5, impronta del referto, chiusura
manuale a mercato sospeso).

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
CER = "Betfair/mike/certificazione.py"
REG = "Betfair/stream/backtest/registro_bot.py"
TEST = ["Betfair/mike", "Betfair/stream/tests/test_registro_bot_2026_09_16.py"]

MUT: List[Tuple[str, str, bytes, bytes]] = [
    ("T1 banco E2: l'importo della banca non si verifica piu'", CER,
     b"            if abs(size - x) <= 0.011:\n                continue\n            spazio = E.liability_room(ctx, params)",
     b"            if True:\n                continue\n            spazio = E.liability_room(ctx, params)"),
    ("T2 banco E2: banca senza Under abbinato non vista", CER,
     b"            if liab <= 0:\n                return f\"banca di copertura da {a.size} senza nessun Under abbinato\"",
     b"            if False:\n                return f\"banca di copertura da {a.size} senza nessun Under abbinato\""),
    ("T3 banco E2: banca piu' piccola accettata anche senza tetto", CER,
     b"            if size < x and spazio != float(\"inf\") \\\n",
     b"            if size < x \\\n"),
    ("T4 banco J5B: due banche in volo sul 4,5 non viste", CER,
     b"    if len(in_volo) > 1:\n        return (f\"due lay in volo sul mercato 4,5:",
     b"    if False:\n        return (f\"due lay in volo sul mercato 4,5:"),
    ("T5 banco J5B: banca nuova sul 4,5 con un'altra in volo non vista", CER,
     b"        if str(a.side) == \"lay\" and a.market == E.MARKET_OU45:\n            annullata = any(",
     b"        if False:\n            annullata = any("),
    ("T6 banco J6: sovracopertura della banca non vista", CER,
     b"        if chiesto > residuo + 0.01:\n            return (f\"sovracopertura: banca",
     b"        if False:\n            return (f\"sovracopertura: banca"),
    ("T7 banco J6: la banca giudicata col conto della puntata", CER,
     b"    if all(str(a.side) == \"lay\" for a in nuove):",
     b"    if False:"),
    ("T8 banco S2: guarda sempre il libro dell'Over", CER,
     b"    return E.SEL_UNDER if E.cover_form(params or {}) == E.COVER_LAY_U45 else E.SEL_OVER",
     b"    return E.SEL_OVER"),
    ("T9 banco S2: non guarda la selezione dell'ordine proposto", CER,
     b"    for a in _piazzamenti(d):\n        if a.role == \"over_cover\" and a.selection:\n            return str(a.selection)",
     b"    for a in _piazzamenti(d):\n        if False:\n            return str(a.selection)"),
    ("T10 chiusura manuale: a mercato sospeso piazza lo stesso", ENG,
     b"    if ferme:\n        return Decision(ctx.state, [], \"chiusura manuale: mercato %s su %s|%s, attendo \"",
     b"    if False:\n        return Decision(ctx.state, [], \"chiusura manuale: mercato %s su %s|%s, attendo \""),
    ("T11 impronta: il motore esce dal registro di Mike", REG,
     b"        moduli_produzione=(\"Betfair.mike.service\", \"Betfair.mike.engine\",",
     b"        moduli_produzione=(\"Betfair.mike.service\","),
    ("T12 impronta: la configurazione esce dal registro di Mike", REG,
     b"                           \"Betfair.mike.config\", \"Betfair.mike.db\", \"Betfair.mike.dossier\",",
     b"                           \"Betfair.mike.db\", \"Betfair.mike.dossier\","),
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
