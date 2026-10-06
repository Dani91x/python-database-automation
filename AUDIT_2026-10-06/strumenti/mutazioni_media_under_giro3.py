"""Falsificazione del terzo giro della modalita' <<media under>> (06/10/2026).

Stessa macchina dei giri 1 e 2 (``AUDIT_2026-10-05/strumenti/mutazioni_media_under.py``:
UNA sostituzione di testo per volta, deve comparire esattamente una volta; test
dei tre giri; ripristino con ``git checkout -- <file>`` e verifica
``git diff --quiet``).

Uso (dalla radice del repo, albero pulito):
    python AUDIT_2026-10-06/strumenti/mutazioni_media_under_giro3.py [id ...]

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                "AUDIT_2026-10-05", "strumenti"))
import mutazioni_media_under as G1  # noqa: E402

MU = G1.MU
RR = G1.RR
CE = G1.CE

PY = ["python", "-m", "pytest",
      "Betfair/stream/tests/test_scalper_media_under_2026_10_05.py",
      "Betfair/stream/tests/test_scalper_media_under_giro2_2026_10_05.py",
      "Betfair/stream/tests/test_scalper_media_under_giro3_2026_10_06.py",
      "-q", "-p", "no:cacheprovider", "-p", "no:randomly"]

# (id, file, vecchio, nuovo, descrizione)
MUTAZIONI: List[Tuple[str, str, str, str, str]] = [
    ("H1", MU, '''    if cm is not None and (c is None or cm < c - 1e-9):
        return cm
    return c''',
     '''    return c''',
     "la quota media non comanda: banca sempre a ultimo ingresso - N tick (la regola vecchia)"),
    ("H2", MU, '''    if cm is not None and (c is None or cm < c - 1e-9):
        return cm''',
     '''    if cm is not None and (c is None or cm > c + 1e-9):
        return cm''',
     "il PIU' ALTO fra le due quote invece del piu' basso"),
    ("H3", MU, '''    p = float(get_nearest_price(float(media)))
    if p >= float(media) - 1e-9:
        p = price_ticks_away(p, -1)
    return float(p) if p and p > 1.0 else None


def quota_della_banca(''',
     '''    p = float(get_nearest_price(float(media)))
    if p > float(media) + 1e-9:
        p = price_ticks_away(p, -1)
    return float(p) if p and p > 1.0 else None


def quota_della_banca(''',
     "tick sotto la media NON stretto (media esattamente su un tick: chiusura a zero)"),
    ("H4", MU, '''        if pos.puntato > _EPS:
            self._annulla_resti_delle_punte(market)''',
     '''        if False:
            self._annulla_resti_delle_punte(market)''',
     "il resto non abbinato delle punte NON si annulla quando si appoggia la banca"),
    ("H5", MU, '''            if float(getattr(o, "size_remaining", 0.0) or 0.0) <= 0.0:
                continue
            self._annulla(market, o, "banca appoggiata: il resto non abbinato della punta "''',
     '''            if float(getattr(o, "size_matched", 0.0) or 0.0) <= 99999.0:
                continue
            self._annulla(market, o, "banca appoggiata: il resto non abbinato della punta "''',
     "l'annullo dei resti non tocca mai le punte (filtro sbagliato)"),
    ("H6", MU, '''        dalla_media = (pos.quota_media is not None
                       and c < (tick_sotto(prezzo_ingresso, self.par.tick_chiusura) or c) - 1e-9)''',
     '''        dalla_media = False''',
     "l'attivita' della banca non dice che la quota viene dalla media"),
    ("H7", CE, '''    for b in banche:
        if float(b.get("price") or 0.0) >= media - 1e-9:''',
     '''    for b in banche:
        if float(b.get("price") or 0.0) >= media + 1.0:''',
     "M11 muto su una banca non in profitto"),
    ("H8", CE, '''        if (str(r.get("side") or "").upper() == "BACK" and _m_vivo(r)
                and str(r.get("status")) != SB.OrderStatus.CANCELLING.value):''',
     '''        if (str(r.get("side") or "").upper() == "BACK" and _m_vivo(r)
                and False):''',
     "M11 muto su un resto di punta vivo"),
    ("H9", CE, '''        if (str(r.get("side") or "").upper() == "BACK" and _m_vivo(r)
                and str(r.get("status")) != SB.OrderStatus.CANCELLING.value):''',
     '''        if (str(r.get("side") or "").upper() == "BACK" and _m_vivo(r)):''',
     "M11 rosso anche con l'annullo del resto gia' chiesto (falso allarme)"),
    ("H10", CE, '''    if cm is not None and (c is None or cm < c - 1e-9):
        c = cm
    if c is None or abs(float(banca.get("price") or 0.0) - c) > 1e-9:''',
     '''    if c is None or abs(float(banca.get("price") or 0.0) - c) > 1e-9:''',
     "M6 con la regola vecchia (ignora la quota media)"),
    ("H11", RR, '''    if variante is not None and variante[0].get("media_mercato"):
        return str(variante[0]["media_mercato"])''',
     '''    if False:
        return str(variante[0]["media_mercato"])''',
     "lo scenario Under 3,5 con liquidita' 50 gira sull'Under 2,5"),
    ("H12", RR, '''    "media-under-liquidita-100": ({"media_min_size": 100.0}, None,''',
     '''    "media-under-liquidita-100": ({"media_min_size": 300.0}, None,''',
     "lo scenario di liquidita' 100 gira coi 300 di serie"),
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
    with open("AUDIT_2026-10-06/strumenti/mutazioni_media_under_giro3_esito.json", "w",
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
