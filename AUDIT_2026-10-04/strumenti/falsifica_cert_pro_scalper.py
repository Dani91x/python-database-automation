"""Falsificazione dei test nuovi (04/10). Ogni mutazione: applica, lancia i test, ripristina
con `git checkout -- <file>`. Uso: python _lavoro_cert/falsifica.py"""
import subprocess
import sys

PY = sys.executable
T = "Betfair/stream/tennis_live/tests/test_certificazione_pro_scalper_2026_10_04.py"
C = "Betfair/stream/tennis_live/certificazione_bot.py"
R = "Betfair/stream/tennis_live/tools/replay_bot.py"
MUT = [
    ("M1 B8 minimi scritti a mano 2,00/0,50", C,
     'MINIMO_IT = {"BACK": float(_MINIMI.IT_MIN_BACK), "LAY": float(_MINIMI.IT_MIN_LAY)}',
     'MINIMO_IT = {"BACK": 2.0, "LAY": 0.5}  # MUTAZIONE', "-k b8"),
    ("M2 B10 ripetuto mai vero", C, '"ripetuto": contatori[chiave] > 1})',
     '"ripetuto": False})  # MUTAZIONE', "-k rifiuti_taglia"),
    ("M3 B10 ordini di altri bot contati", C,
     'if getattr(trade, "strategy", None) is not strategia:',
     'if False:  # MUTAZIONE', "-k rifiuti_taglia"),
    ("M4 SV1 sempre verde", C, '    atteso = oss.catena_soldi_veri\n',
     '    return None  # MUTAZIONE\n    atteso = oss.catena_soldi_veri\n', "-k sv1"),
    ("M5 client_reale invertito", C, '    return not is_client_paper(client)',
     '    return is_client_paper(client)  # MUTAZIONE', "-k client"),
    ("M6 bot live NON instradato sul client reale", R,
     '                GT.instrada_ordini_su_client(strat, cliente_reale)',
     '                pass  # MUTAZIONE', "-k replay_scalper"),
    ("M7 terza rete non montata", R, '                aggiungi_controlli_ordini(quadro)\n',
     '                pass  # MUTAZIONE\n', "-k replay_scalper"),
    ("M8 B8 passo della punta ignorato", C, '            if abs(q - round(q)) > 1e-6:',
     '            if False:  # MUTAZIONE', "-k passo"),
]
for nome, f, vecchio, nuovo, k in [m for m in MUT if m[0].startswith(tuple(sys.argv[1:]) or 'M')]:
    s = open(f, encoding="utf-8").read()
    assert s.count(vecchio) == 1, nome
    open(f, "w", encoding="utf-8", newline="").write(s.replace(vecchio, nuovo))
    try:
        r = subprocess.run([PY, "-m", "pytest", T, "-q", "-p", "no:cacheprovider"] + k.split(),
                           capture_output=True, text=True)
        ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
        print("%-45s -> %s  [%s]" % (nome, "ROSSO" if r.returncode else "VERDE (!)", ultima))
    finally:
        subprocess.run(["git", "checkout", "--", f])
print("residui MUTAZIONE:", sum(open(x, encoding="utf-8").read().count("MUTAZIONE") for x in (C, R)))
