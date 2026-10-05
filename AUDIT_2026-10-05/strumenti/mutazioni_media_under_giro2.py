"""Falsificazione del secondo giro della modalita' <<media under>> (05/10/2026).

Stessa macchina del primo giro (``mutazioni_media_under.py``: UNA sostituzione di
testo per volta, deve comparire esattamente una volta; test; ripristino con
``git checkout -- <file>`` e verifica ``git diff --quiet``), con le mutazioni
del secondo giro e i test dei due giri.

Uso (dalla radice del repo, albero pulito):
    python AUDIT_2026-10-05/strumenti/mutazioni_media_under_giro2.py [id ...]

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutazioni_media_under as G1  # noqa: E402

MU = G1.MU
RR = G1.RR
SS = G1.SS
CE = G1.CE

PY = ["python", "-m", "pytest",
      "Betfair/stream/tests/test_scalper_media_under_2026_10_05.py",
      "Betfair/stream/tests/test_scalper_media_under_giro2_2026_10_05.py",
      "-q", "-p", "no:cacheprovider", "-p", "no:randomly"]

# (id, file, vecchio, nuovo, descrizione)
MUTAZIONI: List[Tuple[str, str, str, str, str]] = [
    # --- 2.1: le due mutazioni sopravvissute alla verifica del revisore
    ("G1", MU, '''        su = ticks_between(self._ultimo_ingresso, bb)
        if su is None or su < self.par.tick_rientro:
            return''',
     '''        su = ticks_between(self._ultimo_ingresso, bb)
        if su is None or su < 0:
            return''',
     "_forse_rientro decide il rientro anche con la quota salita meno di N tick"),
    ("G2", MU, '''                if abs(float(b.order_type.price) - c) < 1e-9 and abs(resto - voluto) <= 0.01:
                    return''',
     '''                if True:
                    return''',
     "_assicura_banca: la banca viva e' sempre <<giusta>> (mai riallineata)"),
    ("G3", MU, '''                if abs(float(b.order_type.price) - c) < 1e-9 and abs(resto - voluto) <= 0.01:
                    return''',
     '''                if abs(float(b.order_type.price) - c) < 1e-9:
                    return''',
     "_assicura_banca: confronta solo la quota, non l'importo"),
]


def main(scelte: List[str]) -> int:
    rc, _ = G1._esegui(["git", "diff", "--quiet"])
    if rc != 0:
        print("ALBERO NON PULITO: commit prima della falsificazione")
        return 2
    rc, out = G1._esegui(PY)
    if rc != 0:
        print("SUITE ROSSA SENZA MUTAZIONI: niente da falsificare\n" + out[-2000:])
        return 2
    righe = []
    for mid, f, vecchio, nuovo, descr in MUTAZIONI:
        if scelte and mid not in scelte:
            continue
        testo = open(f, encoding="utf-8").read()
        n = testo.count(vecchio)
        if n != 1:
            righe.append((mid, descr, "MUTAZIONE NON APPLICABILE (%d occorrenze)" % n, []))
            print("%s | %s | non applicabile (%d)" % (mid, descr, n), flush=True)
            continue
        open(f, "w", encoding="utf-8").write(testo.replace(vecchio, nuovo))
        try:
            _rc, out = G1._esegui(PY)
            rossi = G1._rossi_py(out)
            if "collected 0" in out or ("error" in out.lower() and not rossi):
                rossi.append("ERRORE DI RACCOLTA: " + out.strip().splitlines()[-1])
        finally:
            subprocess.run(["git", "checkout", "--", f], check=True)
        rc, _ = G1._esegui(["git", "diff", "--quiet"])
        if rc != 0:
            print("RIPRISTINO FALLITO dopo %s" % mid)
            return 3
        righe.append((mid, descr, "%d rossi" % len(rossi), rossi))
        print("%s | %s | %d rossi" % (mid, descr, len(rossi)), flush=True)
    print()
    print("| # | mutazione | test rossi |")
    print("|---|---|---|")
    for mid, descr, esito, rossi in righe:
        nomi = ", ".join(r.split("::")[-1] for r in rossi[:4]) + (" ..." if len(rossi) > 4 else "")
        print("| %s | %s | %s: %s |" % (mid, descr, esito, nomi))
    with open("AUDIT_2026-10-05/strumenti/mutazioni_media_under_giro2_esito.json", "w",
              encoding="utf-8") as fh:
        json.dump([{"id": m, "mutazione": d, "esito": e, "rossi": r}
                   for m, d, e, r in righe], fh, indent=1, ensure_ascii=True)
    sopravvissute = [r for r in righe if not r[2].endswith("rossi") or r[2].startswith("0 ")]
    print()
    print("SOPRAVVISSUTE O NON APPLICABILI: %s"
          % (", ".join(r[0] for r in sopravvissute) or "nessuna"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
