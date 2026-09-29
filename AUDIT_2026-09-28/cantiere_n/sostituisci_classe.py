"""Sostituisce la classe CancelloUscite in uscite_proposte.py con classe_cancello.txt
e rende il file ASCII (virgolette a caporale -> doppi apici). Uso una tantum."""
import os

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(WT, "Betfair", "stream", "uscite_proposte.py")
N = os.path.join(os.path.dirname(os.path.abspath(__file__)), "classe_cancello.txt")

with open(P, "r", encoding="utf-8") as fh:
    t = fh.read()
with open(N, "r", encoding="utf-8") as fh:
    nuovo = fh.read()
i = t.index("class CancelloUscite:")
t = t[:i] + nuovo
t = t.replace("from datetime import datetime\n", "import threading\nfrom datetime import datetime\n", 1)
t = t.replace(chr(0xab), chr(34)).replace(chr(0xbb), chr(34))
t.encode("ascii")
with open(P, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(t)
print("ok")
