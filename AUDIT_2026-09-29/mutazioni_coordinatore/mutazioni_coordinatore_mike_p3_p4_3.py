"""Mutazioni del COORDINATORE sui pacchetti P3 (rientro con 1 o 2 gol) e P4
blocco 3 (dati assenti e paper) di Mike.

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
CFG = "Betfair/mike/config.py"
CER = "Betfair/mike/certificazione.py"
SER = "Betfair/mike/service.py"
TEST = ["Betfair/mike"]

MUT: List[Tuple[str, str, bytes, bytes]] = [
    # ------------------------------------------------------------------ P3
    ("K1 rientro: valore di serie rimasto a 1 gol", CFG,
     b"    \"reentry_max_goals\": (2, int, 0, 2, None),",
     b"    \"reentry_max_goals\": (1, int, 0, 2, None),"),
    ("K2 rientro: massimo consentito 3 gol", CFG,
     b"    \"reentry_max_goals\": (2, int, 0, 2, None),",
     b"    \"reentry_max_goals\": (2, int, 0, 3, None),"),
    ("K3 banco H2: accetta il rientro con 3 gol", CER,
     b"    if snap.goals is not None and int(snap.goals) not in (1, 2):",
     b"    if snap.goals is not None and int(snap.goals) not in (1, 2, 3):"),
    ("K4 banco H2: rifiuta il rientro con 2 gol", CER,
     b"    if snap.goals is not None and int(snap.goals) not in (1, 2):",
     b"    if snap.goals is not None and int(snap.goals) != 1:"),
    # ------------------------------------------------------------ P4 blocco 3
    ("V1 paper: ordine senza risposta dato per non eseguito", SER,
     b"                leg.status = E.STATUS_RECONCILE\n                meta.update({\"phase\": \"reserved\", \"reason\": \"place_exception_reconciling\",",
     b"                leg.status = \"cancelled\"\n                meta.update({\"phase\": \"reserved\", \"reason\": \"place_exception_reconciling\","),
    ("V2 paper: ordine senza risposta ridichiarato a ogni giro", SER,
     b"            if (not appoggiata and not leg.needs_reconcile\n",
     b"            if (not appoggiata\n"),
    ("V3 punteggio assente in gioco: mai dichiarato", SER,
     b"                           [\"punteggio\"] if bool(payload.get(\"inplay\")) and goals is None else [],",
     b"                           [],"),
    ("V4 punteggio assente dichiarato anche prima del fischio", SER,
     b"                           [\"punteggio\"] if bool(payload.get(\"inplay\")) and goals is None else [],",
     b"                           [\"punteggio\"] if goals is None else [],"),
    ("V5 quote assenti: avviso subito invece che dopo 10 s", SER,
     b"\"quote_assenti\", missing,\n                           _DATO_ASSENTE_AVVISO_S,",
     b"\"quote_assenti\", missing,\n                           0.0,"),
    ("V6 dato assente: avviso a ogni giro", SER,
     b"        if not ep.get(\"avvisato\") and now_ts - float(ep.get(\"dal\") or now_ts) >= dopo_s:",
     b"        if now_ts - float(ep.get(\"dal\") or now_ts) >= dopo_s:"),
    ("V7 dato tornato: detto anche se l'assenza non era stata avvisata", SER,
     b"        extra.pop(chiave, None)\n        if ep.get(\"avvisato\"):",
     b"        extra.pop(chiave, None)\n        if True:"),
    ("V8 dato tornato: l'episodio non si chiude", SER,
     b"    if ep is not None:\n        extra.pop(chiave, None)\n",
     b"    if ep is not None:\n        pass\n"),
    ("V9 paper: ordine senza risposta, riga segnata in errore come prima", SER,
     b"                    X.aggiorna_trade(db, int(r[\"id\"]), campi={\"meta\": meta})",
     b"                    X.aggiorna_trade(db, int(r[\"id\"]), campi={\"status\": \"error\", \"meta\": meta})"),
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
            print("%-72s ANCORA NON UNICA (%d)" % (nome, n), flush=True)
            vive += 1
            continue
        try:
            p.write_bytes(orig.replace(a, d))
            verde, coda = suite()
        finally:
            p.write_bytes(orig)
        assert md5(p.read_bytes()) == md5(orig)
        errore = "error" in coda and "failed" not in coda
        print("%-72s %s  %s" % (nome, "SOPRAVVISSUTA" if verde else
                                ("ERRORE DI RACCOLTA" if errore else "rossa"), coda), flush=True)
        vive += 1 if (verde or errore) else 0
    print("mutazioni sopravvissute o non valide: %d su %d" % (vive, fatte))
    return 0


if __name__ == "__main__":
    sys.exit(main())
