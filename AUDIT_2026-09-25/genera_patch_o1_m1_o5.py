# Genera la patch unica O1+M1+O5 (base = HEAD del worktree) con i file nuovi.
# Uso (dalla radice del worktree): python AUDIT_2026-09-25/genera_patch_o1_m1_o5.py
import subprocess

OUT = "AUDIT_2026-09-25/o1_m1_o5_integrabili_2026-09-25.patch"
MODIFICATI = ["Betfair/mike/config.py", "Betfair/mike/dossier.py", "Betfair/mike/engine.py",
              "Betfair/mike/feed.py", "Betfair/mike/service.py",
              "Betfair/omega/omega_config.py", "Betfair/omega/omega_engine.py",
              "Betfair/omega/omega_proposte.py", "Betfair/omega/omega_service.py",
              "Betfair/omega/omega_v3.py", "frontend/src/lib/mike.ts",
              "frontend/src/lib/omega.ts"]
NUOVI = ["Betfair/mike/tests/test_mike_veto_p_under35_2026_09_25.py",
         "Betfair/omega/tests/test_o1_quote_prima_2026_09_25.py",
         "Betfair/omega/tests/test_o5_rossi_v3_2026_09_25.py"]
parti = [subprocess.run(["git", "diff", "HEAD", "--"] + MODIFICATI, capture_output=True,
                        check=True).stdout]
for f in NUOVI:
    r = subprocess.run(["git", "diff", "--no-index", "--", "/dev/null", f], capture_output=True)
    parti.append(r.stdout)
dati = b"".join(parti).replace(b"\r\n", b"\n")
open(OUT, "wb").write(dati)
print(OUT, len(dati), "byte")
