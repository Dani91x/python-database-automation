"""Risolve il conflitto di scalper_session.py (merge con D2) tenendo ENTRAMBE le
modifiche: prima l'interruttore allo sniper (D2), poi le firme (cantiere N)."""
import os
import re

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(WT, "Betfair", "stream", "scalper", "scalper_session.py")
with open(P, "r", encoding="utf-8", newline="") as fh:
    t = fh.read()
m = re.search(r"<<<<<<< HEAD\r?\n(.*?)=======\r?\n(.*?)>>>>>>> origin/master\r?\n", t, re.S)
assert m, "conflitto non trovato"
t = t[:m.start()] + m.group(2) + m.group(1) + t[m.end():]
assert "<<<<<<<" not in t and ">>>>>>>" not in t
with open(P, "w", encoding="utf-8", newline="") as fh:
    fh.write(t)
print("ok")
