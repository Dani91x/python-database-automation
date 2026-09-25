# Falsificazione dei test "default ACCESO" (ordine dell'utente 25/09 sera): si rimette
# il default SPENTO (o si rompe il ripiego della chiave assente) e i test devono
# diventare ROSSI. Ripristino dei byte originali in finally, hash prima/dopo.
import hashlib
import os
import re
import subprocess
import sys

T_O1 = "Betfair/omega/tests/test_o1_quote_prima_2026_09_25.py"
T_O5 = "Betfair/omega/tests/test_o5_rossi_v3_2026_09_25.py"
T_M1 = "Betfair/mike/tests/test_mike_veto_p_under35_2026_09_25.py"
CF = "Betfair/omega/omega_config.py"
SV = "Betfair/omega/omega_service.py"
MC = "Betfair/mike/config.py"
ME = "Betfair/mike/engine.py"

MUT = [
    ("D1 O1 default whitelist spento", CF,
     '"lambda_quote_prima": (True, bool, None, None)',
     '"lambda_quote_prima": (False, bool, None, None)', T_O1),
    ("D2 O1 chiave assente = spento nel servizio", SV,
     'omega_config.DEFAULTS["lambda_quote_prima"]))', 'False))', T_O1),
    ("D3 O5 default whitelist spento", CF,
     '"model_red_cards": (True, bool, None, None)',
     '"model_red_cards": (False, bool, None, None)', T_O5),
    ("D4 M1 default whitelist spento", MC,
     '"veto_p_under35_cal": (True, bool, None, None, None)',
     '"veto_p_under35_cal": (False, bool, None, None, None)', T_M1),
    ("D5 M1 chiave assente = spento nel motore", ME,
     'return bool(_CFG.PARAM_SPEC["veto_p_under35_cal"][0])', 'return False', T_M1),
]


def h(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
               SUPABASE_KEY="x")
    prima = {f: h(f) for f in (CF, SV, MC, ME)}
    for nome, path, old, new, test in MUT:
        orig = open(path, "rb").read()
        testo = orig.decode("utf-8")
        assert testo.count(old) == 1, (nome, testo.count(old))
        try:
            open(path, "wb").write(testo.replace(old, new).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                test], capture_output=True, text=True, env=env, timeout=600)
            coda = [x for x in r.stdout.splitlines() if re.search(r"passed|failed|error", x)]
            riga = coda[-1] if coda else r.stdout[-200:]
        finally:
            open(path, "wb").write(orig)
        rosso = "failed" in riga or "error" in riga
        print(("ROSSO " if rosso else "VERDE ") + nome + " -> " + riga.strip(), flush=True)
    dopo = {f: h(f) for f in (CF, SV, MC, ME)}
    print("ripristino byte per byte:", "OK" if prima == dopo else "DIVERSO")


if __name__ == "__main__":
    main()
