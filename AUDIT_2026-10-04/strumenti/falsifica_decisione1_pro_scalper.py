"""Falsificazione della decisione 1 (04/10). Applica, lancia, ripristina con git checkout."""
import subprocess
import sys

PY = sys.executable
TR = "Betfair/stream/tennis_live/tests/test_residui_ricordati_2026_10_04.py"
TC = "Betfair/stream/tennis_live/tests/test_certificazione_pro_scalper_2026_10_04.py"
CD = "Betfair/stream/tennis_scalper/condotta_ordini.py"
PRO = "Betfair/stream/tennis_scalper/tennis_pro_bot.py"
SC = "Betfair/stream/tennis_scalper/tennis_scalper_bot.py"
CB = "Betfair/stream/tennis_live/certificazione_bot.py"
MUT = [
    ("N1 UsciteEsatte: place-and-trim anche sotto il floor", CD,
     "        if 0.0 < resto < FLOOR_PLACE_AND_TRIM - 1e-9:\n",
     "        if False:  # MUTAZIONE\n", TR, "floor or pro_residuo"),
    ("N2 DONE accettato senza sostituto", CD,
     "                and not _sostituto_a_mercato(seq, nuovo):",
     "                and False:  # MUTAZIONE", TR, "sostituto"),
    ("N3 CRITICAL a ogni dichiarazione", CD,
     "        if nuovo and critico:", "        if critico:  # MUTAZIONE", TR, "memoria or ricordato"),
    ("N4 residuo ricordato chiuso gia' sotto 0,02", CD,
     "        if abs(float(se_vince) - float(se_perde)) <= 0.011:",
     "        if abs(float(se_vince) - float(se_perde)) <= 0.02:  # MUTAZIONE", TR, "ricordato_poi"),
    ("N5 PRO: niente ramo del residuo (resta CLOSING)", PRO,
     "        d = px.get(sel)\n        p = (d.get(\"bl\") if trade.get(\"side\") == \"BACK\" else d.get(\"bb\")) if d else None\n        if p is None or p <= 1.0:\n            return False\n        g = compute_green(nw, nl, p)",
     "        return False  # MUTAZIONE\n        d = px.get(sel)\n        p = (d.get(\"bl\") if trade.get(\"side\") == \"BACK\" else d.get(\"bb\")) if d else None\n        if p is None or p <= 1.0:\n            return False\n        g = compute_green(nw, nl, p)",
     TR, "pro_residuo"),
    ("N6 PRO: residuo non regolato a mercato chiuso", PRO,
     "        self.residui_ricordati.regola_mercato(mid)\n",
     "        pass  # MUTAZIONE\n", TR, "pro_residuo"),
    ("N7 SCALPER: place-and-trim anche sotto il floor", SC,
     "        if rest < FLOOR_PLACE_AND_TRIM - _EPS:\n",
     "        if False:  # MUTAZIONE\n", TR, "scalper_resto"),
    ("N8 SCALPER: micro-residuo prima del residuo dichiarato", SC,
     "            if slot.resto_np is not None and not any(",
     "            if False and slot.resto_np is not None and not any(  # MUTAZIONE", TR,
     "scalper_resto"),
    ("N9 SCALPER: minimi scritti a mano 2,00 / 0,50", SC,
     "        return float(_IT_MIN_BACK if (side or \"\").upper() == \"BACK\" else _IT_MIN_LAY)",
     "        return 2.0 if (side or \"\").upper() == \"BACK\" else 0.5  # MUTAZIONE", TR, "minimi"),
    ("N10 K5 ignora i residui dichiarati", CB,
     "    for r in oss.residui or ():\n        try:\n            k_r",
     "    for r in ():  # MUTAZIONE\n        try:\n            k_r", TC, "k5"),
    ("N11 K5 tollera qualunque sbilancio con un residuo", CB,
     "float(r.get(\"sbilancio\") or 0.0) + EPS)",
     "float(r.get(\"sbilancio\") or 0.0) + 99.0)  # MUTAZIONE", TC, "k5"),
    ("N12 RS1 non guarda il floor", CB,
     "        if imp is None or imp + 1e-9 >= floor:",
     "        if imp is None:  # MUTAZIONE", TC, "rs1"),
    ("N13 resto non piazzato non dichiarato subito", CD,
     "            if mem is not None:\n                p = float(price)",
     "            if False:  # MUTAZIONE\n                p = float(price)", TR, "dichiara_subito"),
    ("N14 importi dell'episodio non accumulati", CD,
     "        if riga[\"importo\"] not in prima:\n            prima.append(riga[\"importo\"])",
     "        prima = []  # MUTAZIONE\n        prima.append(riga[\"importo\"])", TR,
     "dichiara_subito"),
    ("N15 UF2 ignora la soglia del chiamante", "Betfair/stream/backtest/uscite_manuali.py",
     "            if 0 < manca < self._soglia_resto and self._resto_dichiarato(",
     "            if 0 < manca < SOGLIA_RESTO_NON_PIAZZABILE and self._resto_dichiarato(  # MUTAZIONE",
     "Betfair/stream/tests/test_banco_uscite_manuali_n3_2026_09_28.py", "soglia_del_resto"),
    ("N16 hook UF2 ignora la memoria dei residui", "Betfair/stream/tennis_live/tools/replay_bot.py",
     "    mem = getattr(getattr(s, \"residui_ricordati\", None), \"aperti\", None) or {}",
     "    mem = {}  # MUTAZIONE", TR, "uf2"),
    ("N17 SCALPER: passo 0,50 anche sulla banca d'uscita", SC,
     "        if self.size_step > 0 and (str(side).upper() == \"BACK\" or floor_min):",
     "        if self.size_step > 0:  # MUTAZIONE", TR, "centesimo"),
    ("N18 credenza scalper senza il residuo dichiarato", CB,
     "                          + _residuo_ricordato(strat, mid, sel))),",
     "                          + 0.0)),  # MUTAZIONE", TR, "credenza"),
]
scelte = sys.argv[1:]
for nome, f, vecchio, nuovo, test, k in MUT:
    if scelte and not nome.split()[0] in scelte:
        continue
    s = open(f, encoding="utf-8").read()
    assert s.count(vecchio) == 1, (nome, s.count(vecchio))
    open(f, "w", encoding="utf-8", newline="").write(s.replace(vecchio, nuovo))
    try:
        r = subprocess.run([PY, "-m", "pytest", test, "-q", "-p", "no:cacheprovider", "-k", k],
                           capture_output=True, text=True, timeout=600)
        ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
        print("%-55s -> %s  [%s]" % (nome, "ROSSO" if r.returncode else "VERDE (!)", ultima))
    finally:
        subprocess.run(["git", "checkout", "--", f])
print("residui MUTAZIONE:", sum(open(x, encoding="utf-8").read().count("MUTAZIONE")
                                for x in (CD, PRO, SC, CB)))
