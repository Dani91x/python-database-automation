"""Falsificazione: ogni mutazione applicata, test lanciati, file ripristinato con git
checkout dal commit (stato salvato). File temporaneo: NON va registrato."""
import io
import re
import subprocess
import sys

PY = sys.executable
TEST = ["Betfair/stream/tests/test_minimi_punte_050_2026_10_04.py",
        "Betfair/mike/tests/test_mike_punte_multiplo_050_2026_10_04.py",
        "Betfair/stream/tests/test_runner_minimi_chiusure_2026_10_01.py",
        "Betfair/stream/tests/test_banco_minimi_it_2026_10_02.py",
        "Betfair/stream/tests/test_runner_minimi_correzioni_2026_10_02.py"]

M = [
    ("M1 regola unica: punta senza passo", "Betfair/stream/trading/minimi_it.py",
     "giu = (chiesto / passo).to_integral_value(rounding=ROUND_FLOOR) * passo",
     "giu = chiesto"),
    ("M2 min_stake_rules torna al centesimo", "Betfair/stream/live_order_build.py",
     "return MinStakeVerdict(True, regola.importo, None, residuo=regola.residuo)",
     "return MinStakeVerdict(True, legal, None)"),
    ("M3 verdetto senza residuo", "Betfair/stream/live_order_build.py",
     "return VerdettoMinimi(VERDETTO_DIRETTO, v.legalized_size, None, residuo=v.residuo)",
     "return VerdettoMinimi(VERDETTO_DIRETTO, v.legalized_size, None)"),
    ("M4 equivalente non multiplo ammesso", "Betfair/stream/live_order_build.py",
     "elif v_eq.residuo > _EPS:", "elif False:"),
    ("M5 build_order senza dichiarazione", "Betfair/stream/live_order_build.py",
     "    if residuo > _EPS:\n        # 04/10/2026: punta .it diretta",
     "    if False:\n        # 04/10/2026: punta .it diretta"),
    ("M6 motore senza punta_050", "Betfair/stream/motore_ordini.py",
     "if verdetto.esito == LB.VERDETTO_DIRETTO and float(verdetto.residuo or 0.0) > 0.0:",
     "if False:"),
    ("M7 ripristino aggancio senza punta_050", "Betfair/stream/motore_ordini.py",
     "\"riprezzo_tradotto\", \"punta_050\"):", "\"riprezzo_tradotto\"):"),
    ("M8 worker senza punta_050 nell'esito", "Betfair/stream/live_order_worker.py",
     "if float(getattr(built, \"residuo\", 0.0) or 0.0) > 0.0:", "if False:"),
    ("M9 submin place normale al centesimo", "Betfair/stream/trading/submin.py",
     "park = round(float(regola.importo), 2)", "park = tsize"),
    ("M10 banco senza passo delle punte", "Betfair/stream/backtest/minimi_banco.py",
     "return v.via == _VIA_DIRETTA and v.residuo > 0.0", "return False"),
    ("M11 patch K1 spenta", "Betfair/stream/backtest/minimi_banco.py",
     "        _come_live_dopo_sostituto_respinto(vecchio, nuovo)\n",
     "        pass\n"),
    ("M12 Mike _place senza multiplo", "Betfair/mike/engine.py",
     "    if side == \"back\":\n        piazzata, residuo = punta_a_multiplo(s)",
     "    if False:\n        piazzata, residuo = punta_a_multiplo(s)"),
    ("M13 Mike per eccesso", "Betfair/mike/engine.py",
     "return (round(float(v.importo), 2), round(float(v.residuo), 2))",
     "return (round(float(v.importo) + (0.5 if v.residuo > 0 else 0.0), 2), 0.0)"),
    ("M14 L3 muto", "Betfair/mike/certificazione.py",
     "    return cent % int(round(IT_PASSO_PUNTA_DIRETTA * 100)) != 0",
     "    return False"),
    ("M15 controllo di piatto spento", "Betfair/mike/engine.py",
     "    if d.state != \"FLAT\":\n        return d\n    if not live_open_selections(ctx.legs, snap.goals):",
     "    if True:\n        return d\n    if not live_open_selections(ctx.legs, snap.goals):"),
    ("M16 avviso a ogni giro", "Betfair/mike/engine.py",
     "    if prima is not None and prima.get(\"residuo_scoperto\") and prima.get(\"sostanza\") == sostanza:\n        return prima, False",
     "    if False:\n        return prima, False\n    prima = None"),
    ("M18 proposta decade nei giri d'attesa", "Betfair/mike/engine.py",
     "    if snap is not None and not any(a.kind == \"place\" for a in d.actions) \\",
     "    if False and not any(a.kind == \"place\" for a in d.actions) \\"),
    ("M17 chiusura rifiutata data per chiusa", "Betfair/mike/engine.py",
     "    if residuo_non_chiudibile(ctx, snap, params, c):\n        return d\n    return _dichiara_residuo(ctx, d, snap, params, c, None, stato=\"LIVE_CLOSING\")",
     "    return d"),
]

righe = []
solo = sys.argv[1:]
for nome, f, old, new in M:
    if solo and nome.split()[0] not in solo:
        continue
    s = io.open(f, encoding="utf-8", newline="").read()
    if "\r\n" in s:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    n = s.count(old)
    if n != 1:
        righe.append(f"{nome}: MUTAZIONE NON APPLICABILE (trovate {n})")
        continue
    io.open(f, "w", encoding="utf-8", newline="").write(s.replace(old, new))
    try:
        r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider",
                            "--no-header", "--tb=no"], capture_output=True, text=True)
        out = r.stdout
        fail = re.findall(r"^FAILED (\S+)", out, re.M)
        tot = re.findall(r"(\d+) failed|(\d+) passed", out)
        riass = out.strip().splitlines()[-1] if out.strip() else r.stderr[-200:]
        righe.append(f"{nome}: {riass}")
        for x in fail:
            righe.append(f"    rosso: {x.split('::', 1)[-1]}")
    finally:
        subprocess.run(["git", "checkout", "--", f], check=True)
    pulito = subprocess.run(["git", "diff", "--quiet", "--", f]).returncode == 0
    righe.append(f"    ripristino {f}: {'ok' if pulito else 'SPORCO!'}")
io.open("_mutazioni_esito.txt", "w", encoding="utf-8").write("\n".join(righe) + "\n")
print("\n".join(righe))
