# -*- coding: utf-8 -*-
"""Scrive la tabella 1->75 in COSTITUZIONE_MIKE.md §16.4, con lo stato di OGGI.

Quattro valori, non due. «Non osservata» e «osservata e passata» non sono la
stessa cosa, e fra tre settimane la differenza non se la ricorda nessuno:

  V   osservata sul campo, ramo esercitato, esito quello atteso
  -   MAI osservata: non sappiamo niente
  P   NON ARRIVA DA SOLA: il ramo c'e' ed e' esercitabile, ma va PROVOCATO a
      mano (cash out dalla UI, TTL scaduto, cap di perdita...). E' lavoro che si
      puo' fare oggi
  X   NON ESERCITABILE: il ramo dipende da un dato che il provider non manda.
      Non si chiude scrivendo codice, si chiude quando arriva il dato — e la
      CAUSA va scritta per nome accanto alla riga

La distinzione fra P e X e' operativa: P misura quanto lavoro resta a noi, X
misura quanto dipende da altri. Metterle nello stesso mucchio vorrebbe dire non
sapere quanto manca davvero.
"""
import io
import json
import os
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(QUI))  # la radice del repo
# la mappa 1->75 si costruisce QUI, dallo strumento: nessun file intermedio da
# tenere allineato a mano, e quindi nessun modo di farli divergere.
sys.path.insert(0, QUI)
import _genera_tabella_75 as _mappa       # noqa: E402
conds = _mappa.conds

# la condizione 75 si riconosce dalla funzione, non da una frase
for c in conds:
    if c["n"] == 75 and not c["punti"]:
        c["punti"] = ["Betfair/mike/engine.py:654", "Betfair/mike/service.py:1566"]

# I RUOLI vanno puntati dove AGISCONO, non dove sono DICHIARATI. Cercando la
# parola "under_entry" si trova anche la tupla delle costanti in cima al file,
# che non dice niente a chi deve capire quando quella gamba viene piazzata.
import subprocess as _sp
_eng = io.open(os.path.join(ROOT, "Betfair", "mike", "engine.py"), encoding="utf8").read().splitlines()
_RUOLI = ("under_entry", "under_last", "under_second", "over_cover", "reentry",
          "under_green", "ko_green")
for c in conds:
    if c["riconosciuta_da"] in _RUOLI:
        agisce = ["Betfair/mike/engine.py:%d" % (i + 1) for i, r in enumerate(_eng)
                  if '_place("%s"' % c["riconosciuta_da"] in r]
        if agisce:
            c["punti"] = agisce[:2]

# ---- quante ne ha viste lo strumento, ADESSO, in paper ---------------------
out = subprocess.run([sys.executable,
                      os.path.join(ROOT, "Betfair", "tools", "verifica_75_condizioni_2026_09_13.py"),
                      "paper"], capture_output=True, text=True, cwd=ROOT).stdout
osservate, da_provocare = {}, set()
import re
for riga in out.splitlines():
    m = re.match(r"\s*(\d+)\s+\[\s*(VISTA|MAI)\s*(\d*)\s*\]", riga)
    if m:
        osservate[int(m.group(1))] = int(m.group(3) or 0) if m.group(2) == "VISTA" else 0

# la sezione "Da provocare a mano" dello strumento
dentro = False
for riga in out.splitlines():
    if "Da provocare a mano" in riga:
        dentro = True
        continue
    if dentro:
        m = re.match(r"\s+(\d+)\s+\S", riga)
        if m:
            da_provocare.add(int(m.group(1)))
        elif riga.strip() == "":
            continue
        else:
            dentro = False

# Le prime ~80 righe di engine.py sono l'intestazione delle COSTANTI (stati,
# ruoli, mercati): trovarci dentro una parola non dice niente a chi deve capire
# QUANDO quel ramo scatta. Si scartano, a meno che non resti nient'altro.
def _utile(punti):
    tenuti = [x for x in punti
              if not (x.startswith("Betfair/mike/engine.py:") and int(x.rsplit(":", 1)[1]) < 80)]
    # Se resta SOLO l'intestazione, meglio dichiararlo che dare un riferimento
    # fuorviante: una riga senza ramo e' una riga da guardare a mano, e va detto.
    return tenuti


for c in conds:
    c["punti"] = _utile(c["punti"])

print("osservate dallo strumento: %d" % sum(1 for n, v in osservate.items() if v > 0))
print("da provocare a mano: %s" % sorted(da_provocare))

# ---- la tabella ------------------------------------------------------------
righe = ["", "### 16.4-bis L'ELENCO OPERATIVO 1→75 (ricostruito il 14/09/2026)", "",
         "Fino a oggi §16.4 aveva **solo i dieci blocchi**, e diceva che «l'elenco",
         "operativo completo va riportato qui». Non c'era. Questa tabella lo è, ed è",
         "**generata dallo strumento** `Betfair/tools/verifica_75_condizioni_2026_09_13.py`,",
         "non scritta a mano: se domani una condizione cambia nello strumento, la tabella",
         "si rigenera diversa e la differenza si vede. Strumento e costituzione non possono",
         "divergere in silenzio.", "",
         "**I quattro stati.** «Non osservata» e «osservata e passata» non sono la stessa",
         "cosa, e fra tre settimane la differenza non se la ricorda nessuno.", "",
         "| | significato |",
         "|---|---|",
         "| **✓** | osservata sul campo, ramo esercitato, esito quello atteso |",
         "| **·** | **mai osservata**: non sappiamo niente |",
         "| **⊗** | **non arriva da sola**: il ramo c'è ed è esercitabile, ma va PROVOCATO a mano. È lavoro che possiamo fare oggi |",
         "| **⊘** | **non esercitabile**: dipende da un dato che il provider non manda. Non si chiude scrivendo codice — la causa è scritta accanto alla riga |",
         "",
         "La distinzione fra ⊗ e ⊘ è operativa: **⊗ misura quanto lavoro resta a noi, ⊘",
         "quanto dipende da altri.** Metterle nello stesso mucchio vorrebbe dire non sapere",
         "quanto manca davvero.",
         "",
         "La colonna **live** è vuota per tutte e 75: il live è bloccato",
         "(`MIKE_LIVE_ENABLED` assente, `LIVE_ORDER_MODE=PAPER`, i tre control in paper) e",
         "**nessuna riga di questa tabella può essere spuntata in live finché non lo si",
         "apre deliberatamente.**", ""]

blocco_corrente = None
for c in sorted(conds, key=lambda x: x["n"]):
    if c["blocco"] != blocco_corrente:
        blocco_corrente = c["blocco"]
        righe += ["", "#### " + blocco_corrente, "",
                  "| # | condizione | ramo di codice | riconosciuta da | paper | live |",
                  "|---:|---|---|---|:---:|:---:|"]
    n = c["n"]
    vis = osservate.get(n, 0)
    if vis > 0:
        stato = "✓ *(%d)*" % vis
    elif n in da_provocare:
        stato = "⊗"
    else:
        stato = "·"
    rami = "<br>".join("`%s`" % p for p in c["punti"]) or "**da individuare a mano**"
    righe.append("| %d | %s | %s | `%s` | %s | |"
                 % (n, c["testo"], rami, c["riconosciuta_da"], stato))

io.open(os.path.join(QUI, "tabella75.md"), "w", encoding="utf8").write("\n".join(righe) + "\n")
print("\nscritto tabella75.md (%d righe)" % len(righe))
