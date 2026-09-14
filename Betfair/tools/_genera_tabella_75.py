# -*- coding: utf-8 -*-
"""Genera la tabella 1->75 di Mike per la COSTITUZIONE, dallo strumento.

Fonte unica: ``Betfair/tools/verifica_75_condizioni_2026_09_13.py``. Se domani
una condizione cambia testo o sonda, questa tabella si rigenera diversa e la
differenza si vede — strumento e costituzione non possono divergere in silenzio.

Per ogni condizione localizza il ramo di codice cercando cio' che la sonda
riconosce: la frase del motivo, il nome dell'attivita', il ruolo della gamba,
oppure il campo di stato. Dove non lo trova lo DICE.
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRUM = os.path.join(ROOT, "Betfair", "tools", "verifica_75_condizioni_2026_09_13.py")
FONTI = ["Betfair/mike/engine.py", "Betfair/mike/service.py", "Betfair/mike/feed.py"]

src = io.open(STRUM, encoding="utf8").read()
blocchi = dict(re.findall(r'(B\d+)\s*=\s*"([^"]+)"', src))

indice = []
for rel in FONTI:
    for i, riga in enumerate(
            io.open(os.path.join(ROOT, *rel.split("/")), encoding="utf8").read().splitlines(), 1):
        indice.append((rel, i, riga))


def cerca(frase, solo_stringhe=True):
    f = frase.strip().lower()
    if len(f) < 3:
        return []
    out = []
    for rel, i, riga in indice:
        r = riga.lower()
        if f not in r:
            continue
        if r.lstrip().startswith("#"):
            continue
        if solo_stringhe and '"' not in riga and "'" not in riga:
            continue
        out.append("%s:%d" % (rel, i))
    return out


# ---- estrazione completa ---------------------------------------------------
conds = []
for p in re.split(r"\n\s*Cond\(", src)[1:]:
    m = re.match(r"(\d+),\s*(B\d+),\s*\"([^\"]+)\",", p)
    if not m:
        continue
    corpo = p[m.end():].split("\n        Cond(")[0]
    sonda = " ".join(corpo.split())
    sonda = sonda.split("# ---- blocco")[0].rstrip(" ,)]")
    conds.append({"n": int(m.group(1)), "blocco": blocchi.get(m.group(2), m.group(2)),
                  "testo": m.group(3), "sonda": sonda})

assert len(conds) == 75, len(conds)

# ---- localizzazione del ramo ----------------------------------------------
# i quattro casi che si riconoscono da un CAMPO e non da una frase
A_MANO = {
    22: ("ctx.cycle_no", "cycle_no"),
    44: ("meta.exit_kind == 'profit'", "exit_kind"),
    62: ("ctx.reentry_done", "reentry_done"),
    71: ("ctx.no_reentry", "no_reentry"),
    75: ("SETTLED senza gambe", "pnl_indipendente_dal_risultato"),
    17: ("ttl + tengo", "ttl scaduto"),
}

for c in conds:
    s = c["sonda"]
    chiavi = re.findall(r'motivo_contiene\("([^"]+)"(?:,\s*"([^"]+)")?', s)
    chiavi += [(x, "") for x in re.findall(r'attivita_con\("([^"]+)"', s)]
    chiavi += [(x, "") for x in re.findall(r'righe_con_ruolo\("([^"]+)"', s)]
    chiavi += [(x, "") for x in re.findall(r'eventi_in_stato\("([^"]+)"', s)]
    parole = [a for k in chiavi for a in k if a]
    if c["n"] in A_MANO and not parole:
        parole = [A_MANO[c["n"]][1]]
    punti = []
    for w in parole:
        punti += cerca(w)
    # dedup mantenendo l'ordine
    visti, uniq = set(), []
    for x in punti:
        if x not in visti:
            visti.add(x)
            uniq.append(x)
    c["riconosciuta_da"] = ", ".join(parole) or (A_MANO.get(c["n"], ("?", ""))[0])
    c["punti"] = uniq[:2]

if __name__ == "__main__":
    trovate = sum(1 for c in conds if c["punti"])
    print("condizioni: %d   ramo localizzato: %d" % (len(conds), trovate))
    for c in conds:
        if not c["punti"]:
            print("   %2d  %s   [%s]" % (c["n"], c["testo"][:50], c["riconosciuta_da"]))
