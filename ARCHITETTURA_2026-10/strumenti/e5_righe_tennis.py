"""E5: righe di codice (senza vuote e commenti a riga intera) per intervalli di righe.
Solo lettura, solo libreria standard. Uso: python -I e5_righe_tennis.py  (dalla radice del repo).
Gli intervalli sono scritti a mano nel dizionario RANGE dopo aver letto gli indici delle funzioni
(grep dei def)\|^    def "): STRATEGIA = regole di ingresso/uscita e stato che servono SOLO alle regole;
il resto del file e' GUSCIO (piazza, cancella, chiudi, residui, uscite manuali, telemetria)."""
import re

BASE = "Betfair/stream/tennis_scalper/"
RANGE = {
    "tennis_pro_bot.py": [(78, 93), (313, 358), (375, 428), (579, 792), (793, 876), (877, 995)],
    "tennis_flb_bot.py": [(332, 398), (431, 597)],
    "tennis_swing_bot.py": [(49, 64), (188, 214), (635, 708)],
}
# nota: il ctor (parametri e valori di serie) e' contato a parte come PARAMETRI
PARAMS = {"tennis_pro_bot.py": (118, 218), "tennis_flb_bot.py": (82, 120), "tennis_swing_bot.py": (78, 109)}


def righe(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for n, r in enumerate(f, 1):
            t = r.strip()
            if t and not t.startswith("#"):
                out[n] = t
    return out


def conta(d, a, b):
    return sum(1 for n in d if a <= n <= b)


for nome, rng in RANGE.items():
    d = righe(BASE + nome)
    tot = len(d)
    strat = sum(conta(d, a, b) for a, b in rng)
    pa, pb = PARAMS[nome]
    par = conta(d, pa, pb)
    print("%s: file %d righe di codice | strategia (intervalli %s) %d | parametri ctor %d | guscio (resto) %d" % (
        nome, tot, rng, strat, par, tot - strat - par))
