"""Falsificazione del backend del replay professionale: ogni mutazione deve far
diventare ROSSO il test Python. Applica, lancia pytest, ripristina."""
import subprocess
import sys

W = sys.argv[1]
TEST = "Betfair/stream/tests/test_replay_professionale_2026_10_07.py"
MUT = [
    ("Betfair/stream/backtest/applica_bot.py", "profitto arrotondato sul totale e non per ordine",
     [("        v = round(abbinato * (prezzo - 1.0), 2)", "        v = abbinato * (prezzo - 1.0)"),
      ("round(per_mercato.get(mid, 0.0) + round(prof, 2), 2)", "per_mercato.get(mid, 0.0) + prof")]),
    ("Betfair/stream/backtest/applica_bot.py", "identita' dell'ordine dal ref (replace fuso)",
     [('    if r.get("_ordine"):\n        return "o:" + str(r["_ordine"])', '    if False:\n        return ""')]),
    ("Betfair/stream/backtest/applica_bot.py", "accensione confermata senza la riga del bot",
     [('        dal = bool(any(t.startswith("ACCENSIONE") and str(dal_ms) in t for t in testi)',
       '        dal = bool(True or any(t.startswith("ACCENSIONE") and str(dal_ms) in t for t in testi)')]),
    ("Betfair/stream/backtest/varianti_bot.py", "legame di riprezzo senza prova (stesso trade basta)",
     [("        if not stesso:\n            continue", "        if False:\n            continue")]),
    ("Betfair/stream/backtest/varianti_bot.py", "legame di riprezzo perso",
     [('        out["_sostituisce"] = str(getattr(o, "id", "")) or None', '        out["_sostituisce"] = None')]),
    ("Betfair/stream/backtest/applica_bot.py", "nota P&L del referto letta male (lordo e netto scambiati)",
     [('"lordo": float(m.group(1)), "commissione": float(m.group(2)),', '"lordo": float(m.group(4)), "commissione": float(m.group(2)),')]),
]
for f, nome, sost in MUT:
    p = W + "/" + f
    orig = open(p, encoding="utf-8").read()
    nuovo = orig
    ok = True
    for a, b in sost:
        if nuovo.count(a) != 1:
            ok = False
        nuovo = nuovo.replace(a, b)
    if not ok:
        print("%-60s NON APPLICABILE" % nome)
        continue
    try:
        open(p, "w", encoding="utf-8").write(nuovo)
        r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider", "-x"],
                           cwd=W, capture_output=True, text=True, timeout=900)
        ultima = [x for x in r.stdout.splitlines() if "passed" in x or "failed" in x]
        print("%-60s %s %s" % (nome, "ROSSO" if r.returncode else "VERDE (!)", ultima[-1] if ultima else ""))
    finally:
        open(p, "w", encoding="utf-8").write(orig)
