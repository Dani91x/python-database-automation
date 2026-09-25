# Falsificazione dei test O5: ogni mutazione si applica al file, si lancia il file di
# test, si RIPRISTINANO i byte originali in finally (mai git checkout).
import hashlib
import os
import re
import subprocess
import sys

TEST = "Betfair/omega/tests/test_o5_rossi_v3_2026_09_25.py"
V3 = "Betfair/omega/omega_v3.py"
EN = "Betfair/omega/omega_engine.py"
PR = "Betfair/omega/omega_proposte.py"
SV = "Betfair/omega/omega_service.py"
CF = "Betfair/omega/omega_config.py"

MUT = [
    ("F1 moltiplicatore ignorato ovunque (V3)", V3,
     "    mh, ma = float(mult_rossi[0]), float(mult_rossi[1])", "    mh, ma = 1.0, 1.0", 2),
    ("F1b moltiplicatore ignorato solo nella griglia NegBin", V3,
     "residua * math.exp(-p.beta_squilibrio * d)) * mh", "residua * math.exp(-p.beta_squilibrio * d))", 1),
    ("F1c tau con le intensita' senza rossi", V3,
     "p=p, lambdas=lambdas, mult_rossi=(mh, ma))", "p=p, lambdas=lambdas)", 1),
    ("F2 interruttore ignorato (sempre acceso)", EN,
     'if not C.parametri_v3(params or {})["rossi"]:', "if False:", 1),
    ("F2b interruttore ignorato (mai acceso)", EN,
     'if not C.parametri_v3(params or {})["rossi"]:', "if True:", 1),
    ("F3a uscita: la P del bancato non vede i rossi", PR,
     "nomi=nomi, p=parametri_modello(), lambdas=lambdas,\n            mult_rossi=mult_rossi)",
     "nomi=nomi, p=parametri_modello(), lambdas=lambdas,\n            mult_rossi=V3.MULT_NEUTRO)", 1),
    ("F3b uscita: la traiettoria non vede i rossi", PR,
     "p_lose_max=p_lose_max, mult_rossi=mult_rossi)", "p_lose_max=p_lose_max)", 1),
    ("F3c uscita: V3.proposta_uscita ignora mult nella traiettoria", V3,
     "p_evento_ora=float(p_evento), mult_rossi=mult_rossi)", "p_evento_ora=float(p_evento))", 1),
    ("F4 ingresso: seleziona_v3 non passa i rossi al modello", EN,
     "nomi=nomi, p=p, lambdas=lambdas,\n                                           mult_rossi=mult)",
     "nomi=nomi, p=p, lambdas=lambdas,\n                                           mult_rossi=V3.MULT_NEUTRO)", 1),
    ("F5 _v3_select non passa i rossi del feed", SV,
     'rossi=(int(getattr(state, "red_home", 0) or 0),\n               int(getattr(state, "red_away", 0) or 0)))',
     "rossi=None)", 1),
    ("F6 coefficienti PER LEGA invece che globali", EN,
     "mh, ma = red_card_multipliers(rh, ra, None)", "mh, ma = red_card_multipliers(rh, ra, 39)", 1),
    ("F7 casa/trasferta invertiti", EN,
     "return (float(mh), float(ma))", "return (float(ma), float(mh))", 1),
    # 25/09 sera: il default e' ACCESO per ordine dell'utente; la mutazione lo spegne
    ("F8 default della whitelist spento", CF,
     '"model_red_cards": (True, bool, None, None)', '"model_red_cards": (False, bool, None, None)', 1),
    ("F9 fonte della P senza +rossi", PR,
     'fonte += "+rossi"', 'fonte += ""', 1),
]


def h(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
               SUPABASE_KEY="x")
    prima = {f: h(f) for f in (V3, EN, PR, SV, CF)}
    esiti = []
    for nome, path, old, new, n in MUT:
        orig = open(path, "rb").read()
        testo = orig.decode("utf-8")
        nl = "\r\n" if "\r\n" in testo else "\n"
        o, nw = old.replace("\n", nl), new.replace("\n", nl)
        assert testo.count(o) == n, (nome, testo.count(o))
        try:
            open(path, "wb").write(testo.replace(o, nw).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                TEST], capture_output=True, text=True, env=env, timeout=600)
            coda = [x for x in r.stdout.splitlines() if re.search(r"passed|failed|error", x)]
            riga = coda[-1] if coda else r.stdout[-200:]
        finally:
            open(path, "wb").write(orig)
        rosso = "failed" in riga or "error" in riga
        esiti.append((nome, "ROSSO" if rosso else "VERDE", riga.strip()))
        print(("ROSSO " if rosso else "VERDE ") + nome + " -> " + riga.strip(), flush=True)
    dopo = {f: h(f) for f in (V3, EN, PR, SV, CF)}
    print("ripristino byte per byte:", "OK" if prima == dopo else "DIVERSO " + str(dopo))


if __name__ == "__main__":
    main()
