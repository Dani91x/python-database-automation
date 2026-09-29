"""Aggiorna il referto: sostituisce la sezione G e inserisce B.6 prima di B.5."""
import os

D = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(os.path.dirname(D), "CANTIERE_N_PULSANTE_USCITE.md")
with open(R, "r", encoding="utf-8") as fh:
    t = fh.read()
with open(os.path.join(D, "sezione_g_nuova.md"), "r", encoding="utf-8") as fh:
    g = fh.read()
with open(os.path.join(D, "sezione_b6.md"), "r", encoding="utf-8") as fh:
    b6 = fh.read()
i = t.index("# G. DECISIONI PER L'UTENTE")
j = t.index("# H. CONTROLLI DAL VIVO")
t = t[:i] + g + "\n" + t[j:]
k = t.index("## B.5 Specifiche NON fatte")
t = t[:k] + b6 + "\n" + t[k:]
with open(R, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(t)
print("ok")
