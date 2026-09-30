"""Falsificazione del blocco 1 di P5 (M3.4): ogni mutazione reintroduce il
conto PER SELEZIONE in un punto; i test nuovi devono diventare rossi.
Ripristino da copia in memoria con controllo dell'hash (mai git checkout).
Uso: python AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_1.py
"""
import hashlib
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENG = os.path.join(RADICE, "Betfair", "mike", "engine.py")
SRV = os.path.join(RADICE, "Betfair", "mike", "service.py")
TEST = ["Betfair/mike/tests/test_mike_p5_compensazione_mercato_2026_09_29.py",
        "Betfair/mike/tests/test_mike_conto_e_sovracopertura_2026_09_16.py"]

MUTAZIONI = [
    ("M1 exposure senza il ramo altra selezione", ENG,
     "        elif leg.side == \"back\":\n            # punta sull'altra selezione",
     "        elif False:  # MUTAZIONE\n            # punta sull'altra selezione"),
    ("M1b exposure: banca sull'altra selezione ignorata", ENG,
     "        else:\n            # banca sull'altra selezione: se vince la nostra, quella perde e si incassa\n            w += s\n            l -= s * (p - 1.0)",
     "        else:\n            pass  # MUTAZIONE\n"),
    ("M2 opening_ref col filtro side==back", ENG,
     "    ruoli = _APERTURE_DEL_RUOLO.get(str(role or \"\"), OPENING_ROLES)\n",
     "    ruoli = _APERTURE_DEL_RUOLO.get(str(role or \"\"), OPENING_ROLES)\n    legs = [l for l in legs if l.side == \"back\"]  # MUTAZIONE\n"),
    ("M3 invested solo puntate", ENG,
     "                      else float(l.matched) * (l.fill_price - 1.0))",
     "                      else 0.0)  # MUTAZIONE"),
    ("M4 copertura_in_volo per selezione", ENG,
     "        if l.role != \"over_cover\" or not (l.is_live or l.needs_reconcile):\n            continue\n        if not _stessa_posizione(l.market, l.selection, market, selection):",
     "        if l.role != \"over_cover\" or not (l.is_live or l.needs_reconcile):\n            continue\n        if l.market != market or l.selection != selection:  # MUTAZIONE"),
    ("M5 lay_in_volo per selezione", ENG,
     "        if l.side != \"lay\" or not (l.is_live or l.needs_reconcile):\n            continue\n        if not _stessa_posizione(l.market, l.selection, market, selection):",
     "        if l.side != \"lay\" or not (l.is_live or l.needs_reconcile):\n            continue\n        if l.market != market or l.selection != selection:  # MUTAZIONE"),
    ("M6 conto: solo le chiavi di open_selections", SRV,
     "    for (mercato, selezione) in E.selezioni_da_sorvegliare(ctx.legs):",
     "    for (mercato, selezione) in sorted(aperte):  # MUTAZIONE"),
    ("M7 ordini_vivi_su per selezione", ENG,
     "            if l.is_live and _stessa_posizione(l.market, l.selection, market, selection)\n            and l.role not in escludi]",
     "            if l.is_live and l.market == market and l.selection == selection  # MUTAZIONE\n            and l.role not in escludi]"),
    ("M8 chiave: banca di apertura corta resta sulla sua selezione", ENG,
     "            return (MARKET_OU45, SEL_OVER if sel == SEL_UNDER else SEL_UNDER)",
     "            return (MARKET_OU45, sel)  # MUTAZIONE"),
    ("M9 riepilogo_cicli senza il rischio delle banche", ENG,
     "        if rischio_banche > 0:\n            stake",
     "        if False:  # MUTAZIONE\n            stake"),
    ("M10 chiusura manuale: altra lay per selezione", ENG,
     "                  and any(_stessa_posizione(c.market, c.selection, l.market, l.selection)",
     "                  and any((c.market == l.market and c.selection == l.selection)  # MUTAZIONE"),
    ("M11 _stessa_posizione = stessa selezione", ENG,
     "    return m1 == m2 and (s1 == s2 or m1 in LINE)",
     "    return m1 == m2 and s1 == s2  # MUTAZIONE"),
]


def h(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    py = sys.executable
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_KEY="x",
               SUPABASE_SERVICE_ROLE_KEY="x")
    originali = {p: open(p, "rb").read() for p in (ENG, SRV)}
    hash0 = {p: h(p) for p in originali}
    esiti = []
    try:
        for nome, file, vecchio, nuovo in MUTAZIONI:
            testo = originali[file].decode("utf-8")
            if "\r\n" in testo:
                vecchio = vecchio.replace("\n", "\r\n")
                nuovo = nuovo.replace("\n", "\r\n")
            if testo.count(vecchio) != 1:
                esiti.append((nome, "MUTAZIONE NON APPLICABILE (%d occorrenze)" % testo.count(vecchio)))
                continue
            with open(file, "wb") as f:
                f.write(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run([py, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider"],
                               cwd=RADICE, env=env, capture_output=True, text=True)
            coda = [x for x in r.stdout.splitlines() if " passed" in x or " failed" in x]
            rossi = [x.split("::")[-1] for x in r.stdout.splitlines() if x.startswith("FAILED")]
            esiti.append((nome, ("ROSSO " if r.returncode else "VERDE (!) ") + (coda[-1] if coda else r.stdout[-300:]), rossi))
            with open(file, "wb") as f:
                f.write(originali[file])
    finally:
        for p, b in originali.items():
            with open(p, "wb") as f:
                f.write(b)
    for p in originali:
        assert h(p) == hash0[p], "RIPRISTINO FALLITO " + p
        assert b"MUTAZIONE" not in open(p, "rb").read(), "MUTAZIONE RIMASTA " + p
    for e in esiti:
        print(" | ".join(str(x) for x in e))
    print("ripristino verificato: hash identici, nessuna MUTAZIONE nei file")


if __name__ == "__main__":
    main()
