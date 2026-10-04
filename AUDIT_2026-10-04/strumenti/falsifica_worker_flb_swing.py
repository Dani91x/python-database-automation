"""Falsificazione: worker tennis (W) e flb/swing (F). git checkout per ripristinare."""
import subprocess
import sys

PY = sys.executable
W = "Betfair/stream/tennis_live/tennis_live_order_worker.py"
TW = "Betfair/stream/tennis_live/tests/test_worker_minimi_tennis_2026_10_04.py"
MUT = [
    ("W1 punta_050 mai dichiarata", W, "    if r <= 0.0:\n        return None\n    logger.warning(\"[tennis-order] punta",
     "    return None  # MUTAZIONE\n    logger.warning(\"[tennis-order] punta", TW, "difetto"),
    ("W2 hedge sotto 0,50: torna il ValueError", W,
     "        if regola.via == _MI.VIA_NESSUNA:\n",
     "        if False:  # MUTAZIONE\n", TW, "floor"),
    ("W3 hedge 0,50-1,00: niente place-and-trim", W,
     "        if regola.via == _MI.VIA_PLACE_AND_TRIM:\n",
     "        if False:  # MUTAZIONE\n", TW, "place_and_trim"),
    ("W4 il giro non avanza i place-and-trim", W,
     "    if not _ESATTE:\n        return\n",
     "    return  # MUTAZIONE\n", TW, "place_and_trim"),
]
EXTRA = []
try:
    import falsifica3_extra  # noqa: F401
    EXTRA = falsifica3_extra.MUT
except Exception:  # noqa: BLE001
    pass
scelte = sys.argv[1:]
for nome, f, vecchio, nuovo, test, k in MUT + EXTRA:
    if scelte and nome.split()[0] not in scelte:
        continue
    s = open(f, encoding="utf-8").read()
    assert s.count(vecchio) == 1, (nome, s.count(vecchio))
    open(f, "w", encoding="utf-8", newline="").write(s.replace(vecchio, nuovo))
    try:
        r = subprocess.run([PY, "-m", "pytest", test, "-q", "-p", "no:cacheprovider", "-k", k],
                           capture_output=True, text=True, timeout=600)
        ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
        print("%-50s -> %s  [%s]" % (nome, "ROSSO" if r.returncode else "VERDE (!)", ultima))
    finally:
        subprocess.run(["git", "checkout", "--", f])
