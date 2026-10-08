"""RM6: il bot continua a decidere dopo l'intervento (involucro della sorveglianza E
fermo per istanza tolti insieme). Replay ordine-esterno 35797769: deve diventare rosso."""
import hashlib
import re
import subprocess
import sys

WT = "/home/user/python-database-automation/.claude/worktrees/agent-aa6d8083bb40b34bd"
OUT = "/tmp/claude-0/-home-user-python-database-automation/d9b4fd9d-aa86-54f8-97b7-ad733bb0c124/scratchpad/w3b_prove/mut_RM6.txt"
MUT = [
    ("Betfair/stream/tennis_scalper/ordini_esterni.py",
     "        if _s.controlla() is not None:\n            return False\n        return bool(_orig(market, market_book))",
     "        _s.controlla()  # MUTAZIONE\n        return bool(_orig(market, market_book))"),
    ("Betfair/stream/scalper/scalper_session.py",
     "            for s in attive:\n                OE.ferma_strategia(s)\n",
     "            pass  # MUTAZIONE\n"),
]
orig = {}
h0 = {}
for f, old, new in MUT:
    p = WT + "/" + f
    orig[p] = open(p, encoding="utf-8").read()
    h0[p] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    assert orig[p].count(old) == 1, f
try:
    for f, old, new in MUT:
        p = WT + "/" + f
        open(p, "w", encoding="utf-8").write(orig[p].replace(old, new))
    with open(OUT, "w") as fh:
        r = subprocess.run([sys.executable, "-m", "Betfair.stream.backtest.certifica",
                            "scalper_calcio", "35797769", "--scenari", "ordine-esterno",
                            "--worker", "1"], cwd=WT, stdout=fh, stderr=subprocess.DEVNULL,
                           timeout=2400)
finally:
    for p, t in orig.items():
        open(p, "w", encoding="utf-8").write(t)
testo = open(OUT).read()
print("RM6 rc=%s esito=%s violazioni=%s" % (
    r.returncode, re.findall(r"^(OK|KO|NE)\s+35797769", testo, re.M),
    sorted(set(re.findall(r"^\s+([A-Z]+[0-9]+[a-z]?) x\d+: ", testo, re.M)))))
for p in orig:
    h1 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(p.split("/")[-1], h0[p][:12], "ripristinato" if h0[p] == h1 else "DIVERSO!")
