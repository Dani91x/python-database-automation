"""Estrae (offline) id, categoria, nome, 'come si vede viva' e fase·controllo dall'inventario."""
import os
import re
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
inv = os.path.join(QUI, "..", "..", "INVENTARIO_COMPONENTI_2026-09-25.md")
cats = set(sys.argv[1].split(","))
for riga in open(inv, encoding="utf-8"):
    if not re.match(r"^\| C\d{3} ", riga):
        continue
    c = [x.strip() for x in riga.strip().strip("|").split("|")]
    if re.split(r"[- ]", c[1])[0] not in cats:
        continue
    viva = c[8] if len(c) > 8 else ""
    fase = c[10] if len(c) > 10 else ""
    print(f"{c[0]} | {c[1]} | {c[2][:70]} | VIVA: {viva[:110]} | {fase[:60]}")
