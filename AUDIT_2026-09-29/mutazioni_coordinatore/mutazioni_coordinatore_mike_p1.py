"""Mutazioni del COORDINATORE sul pacchetto P1 di Mike (cancello delle uscite).

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
F = "Betfair/mike/engine.py"
TEST = ["Betfair/mike"]

MUT: List[Tuple[str, bytes, bytes]] = [
    ("X1 l'uscita in perdita a modello parte da sola",
     b'    if motivo.startswith("loss") or motivo == "reentry_time":',
     b'    if motivo == "reentry_time":'),
    ("X2 la chiusura a tempo del rientro parte da sola",
     b'    if motivo.startswith("loss") or motivo == "reentry_time":',
     b'    if motivo.startswith("loss"):'),
    ("X3 le uscite in profitto tornano proposte",
     b"    if not uscita_in_perdita(d):\n        # 29/09 (M1.1, M4.1-M4.4)",
     b"    if False:\n        # 29/09 (M1.1, M4.1-M4.4)"),
    ("X4 una gamba vecchia autorizza una nuova uscita in perdita",
     b"    if uscita_in_perdita(d):\n        return False",
     b"    if False:\n        return False"),
    ("X5 la chiusura del veto pre-partita parte da sola",
     b"    return any(a.kind == \"place\" and a.note == VETO_U35_NOTE for a in d.actions)",
     b"    return False"),
    ("X6 chiusura manuale: la lay a esito ignoto non ferma",
     b"                  if (l.is_live or l.needs_reconcile) and l.side == \"lay\"",
     b"                  if l.is_live and l.side == \"lay\""),
    ("X7 chiusura manuale: si ferma sulla sua stessa lay",
     b"                  and l.role != \"manual_close\"\n",
     b"\n"),
    ("X8 chiusura manuale: si ferma per una lay di un'altra selezione",
     b"                  and any(c.market == l.market and c.selection == l.selection for c in closes)),",
     b"                  and True),"),
    ("X9 il tetto di perdita torna a chiudere",
     b"    # 29/09 (piano Mike M4.5, decisione 18 dell'utente: \"toglilo\"): il tetto di\n",
     b"    if float(params[\"event_loss_cap_pct\"]) > 0 and base > 0 and cv.net <= -base * float(params[\"event_loss_cap_pct\"]) / 100.0:\n        return Decision(\"LIVE_CLOSING\", acts + _close_actions(ctx, cv, params), \"cap\", updates={\"close_reason\": \"loss_cap\", \"attempts\": 0}, telemetry=tele)\n    # 29/09 (piano Mike M4.5, decisione 18 dell'utente: \"toglilo\"): il tetto di\n"),
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
