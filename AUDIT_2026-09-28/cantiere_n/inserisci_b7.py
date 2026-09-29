"""Referto: sostituisce la vecchia specifica dello sniper (B.5) con B.7 e
aggiorna le righe che dicevano "sniper non fatto"."""
import os

D = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(os.path.dirname(D), "CANTIERE_N_PULSANTE_USCITE.md")
with open(R, "r", encoding="utf-8") as fh:
    t = fh.read()
with open(os.path.join(D, "sezione_b7.md"), "r", encoding="utf-8") as fh:
    b7 = fh.read()
i = t.index("## B.5 Specifiche NON fatte")
j = t.index("- **Theta**", i)
t = t[:i] + b7 + t[j:]
t = t.replace("- Sniper e theta (§B.5).", "- Theta (§B.5); lo sniper e' fatto (§B.7).")
t = t.replace("| **Sniper** (in D2, non ancora su master) | stop 2 tick / timeout 300 s oggi ancora automatici (spec in B.5) | - |",
              "| **Sniper** (in-play, stake 10 EUR) | BACK Under 10 EUR @ 1,40; gol: la quota sale a 2,50, stop e timeout proposti, chiudendo ora circa -4,40 EUR | al gol successivo si perdono i 10 EUR |")
with open(R, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(t)
print("ok")
