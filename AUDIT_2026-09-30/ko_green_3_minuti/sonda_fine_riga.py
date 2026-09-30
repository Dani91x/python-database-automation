"""Sonda: fine riga (CRLF/LF) e caratteri non ASCII dei file toccati, contro HEAD."""
import subprocess

FILES = ["Betfair/mike/engine.py", "Betfair/mike/certificazione.py",
         "Betfair/mike/tools/replay_registrazioni.py",
         "Betfair/stream/backtest/chiusura_parziale.py",
         "Betfair/mike/tests/test_mike_ko_green_3_minuti_2026_09_30.py",
         "Betfair/mike/tests/test_mike_flusso_fischio_2026_09_13.py",
         "Betfair/mike/tests/test_mike_ko_green_appoggiata_2026_09_16.py",
         "Betfair/mike/COSTITUZIONE_MIKE.md"]
for f in FILES:
    b = open(f, "rb").read()
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    try:
        h = subprocess.run(["git", "show", "HEAD:" + f], capture_output=True).stdout
        hcr = h.count(b"\r\n")
        hlf = h.count(b"\n") - hcr
    except Exception:
        hcr = hlf = -1
    print(f, "ora crlf", crlf, "lf", lf, "| HEAD crlf", hcr, "lf", hlf)
