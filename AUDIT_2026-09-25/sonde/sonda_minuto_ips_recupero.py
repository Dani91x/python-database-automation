"""Sonda (SOLA LETTURA, file locali): come l'IPS Betfair registra il minuto nei
recuperi. Legge ``_live_raw/<id>/<id>.scores.jsonl`` (i sidecar punteggi del
registratore) e tabula matchStatus x timeElapsed x elapsedRegularTime x
elapsedAddedTime. Uso: python sonda_minuto_ips_recupero.py <cartella _live_raw>
"""
import collections
import glob
import json
import os
import sys

radice = sys.argv[1] if len(sys.argv) > 1 else "_live_raw"
tab = collections.Counter()
per_stato = collections.Counter()
esempi = {}
n_file = n_righe = 0
for f in sorted(glob.glob(os.path.join(radice, "*", "*.scores.jsonl"))):
    n_file += 1
    with open(f, encoding="utf-8") as fh:
        for riga in fh:
            try:
                r = json.loads(riga)
            except ValueError:
                continue
            p = r.get("payload") or {}
            n_righe += 1
            st = p.get("matchStatus")
            te, er, ea = p.get("timeElapsed"), p.get("elapsedRegularTime"), p.get("elapsedAddedTime")
            per_stato[st] += 1
            if 43 <= (te or 0) <= 50 or (te or 0) >= 88:
                k = (st, te, er, ea, r.get("minute"))
                tab[k] += 1
                esempi.setdefault(k, os.path.basename(f))
print(f"file {n_file}, righe {n_righe}")
print("stati:", dict(per_stato))
print("matchStatus | timeElapsed | elapsedRegularTime | elapsedAddedTime | minute(feed) | righe | esempio")
for k in sorted(tab, key=lambda k: (str(k[0]), k[1] or 0, k[3] if k[3] is not None else -1)):
    print(" | ".join(str(x) for x in k), "|", tab[k], "|", esempi[k])
