"""Falsificazione di RUNNER_MINIMI_CHIUSURE: ogni mutazione rimette un difetto e i test
nuovi DEVONO diventare rossi; poi il file si ripristina dal testo originale (in memoria,
e comunque in un finally). Uso: python AUDIT_2026-10-01/falsifica_runner_minimi.py"""
import subprocess
import sys

TEST = "Betfair/stream/tests/test_runner_minimi_chiusure_2026_10_01.py"
LB = "Betfair/stream/live_order_build.py"
MO = "Betfair/stream/motore_ordini.py"

MUTAZIONI = [
    ("M1 esenzione reduces_liability rimessa", LB,
     "    del reduces_liability  # informazione: mai un'esenzione dai minimi\n",
     "    if reduces_liability:\n        return MinStakeVerdict(True, round(float(size), 2), None)\n"),
    ("M2 floor della punta a 0,50 rimesso", LB,
     "        legal = round(float(size), 2)\n        if s == \"back\":\n",
     "        legal = round(float(size), 2)\n        if s == \"back\":\n"
     "            legal = _floor_to_step(legal, IT_BACK_STEP)\n"),
    ("M3 equivalente tick al piu' vicino (limite peggiore)", LB,
     "    tick = _tick_su(esatta) if lato == \"back\" else _tick_giu(esatta)\n",
     "    tick = get_nearest_price(esatta) if lato == \"back\" else _tick_giu(esatta)\n"),
    ("M4 eventi NON riportati al chiesto", MO,
     "            if info.get(\"tradotto\"):\n                d = _riporta_tradotto(d, info[\"tradotto\"])\n",
     "            pass\n"),
    ("M5 nessun ripiego ai 0,50", MO,
     "            self._ripiega(s, nuova)\n            n += 1\n",
     "            pass\n"),
    ("M6 taglia rifiutata ritentata identica", MO,
     "        if not piano.get(\"submin\") and chiave in self._taglie_rifiutate:\n",
     "        if False:\n"),
    ("M7 floor del trim tolto (0,50 non verificato)", LB,
     "    if float(size) < SUBMIN_IMPORTO_FINALE_MIN - _EPS \\\n"
     "            or chiesta < SUBMIN_IMPORTO_FINALE_MIN - _EPS:\n",
     "    if False:\n"),
    ("M8 regola d'ingresso della macchina tolta", "Betfair/stream/trading/submin.py",
     "    if t < SUBMIN_IMPORTO_FINALE_MIN - _TOL:\n",
     "    if False:\n"),
]

ok = True
for nome, path, vecchio, nuovo in MUTAZIONI:
    testo = open(path, encoding="utf-8").read()
    if vecchio not in testo:
        print("%s: PUNTO DI MUTAZIONE NON TROVATO" % nome)
        ok = False
        continue
    try:
        open(path, "w", encoding="utf-8").write(testo.replace(vecchio, nuovo, 1))
        r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider"],
                           capture_output=True, text=True)
        riga = [x for x in r.stdout.splitlines() if "passed" in x or "failed" in x][-1:]
        rosso = r.returncode != 0
        ok = ok and rosso
        print("%s: %s  %s" % (nome, "ROSSO (atteso)" if rosso else "VERDE (DIFETTO NON VISTO)",
                              riga[0] if riga else ""))
    finally:
        open(path, "w", encoding="utf-8").write(testo)
r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider"],
                   capture_output=True, text=True)
print("ripristino:", [x for x in r.stdout.splitlines() if "passed" in x or "failed" in x][-1:])
print("ESITO:", "tutte rosse" if ok else "QUALCOSA NON E' DIVENTATO ROSSO")
