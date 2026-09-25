"""Log-loss per lega sul test 2025 dalle predizioni salvate (nessun riaddestramento).
Insiemi: 'pulito' (blocchi che registrano il recupero) e 'regolari_sicuri' (t <= 41)."""
import json
import os

import numpy as np

from Betfair.stream.scalper.validazione_hazard import banco as B
from Betfair.stream.scalper.validazione_hazard import metriche as ME
from Betfair.stream.scalper.validazione_hazard.dati import recupero_registrato

D = B.carica_tutto(B.CACHE_DEFAULT)
S, P = D["S"], D["partite"]
Z = np.load(os.path.join(B.OUT_DEFAULT, "cache", "predizioni_test.npz"))
ev = Z["ev"]
reg_ok = recupero_registrato(D["matches"], D["eventi"])
fx = np.array([p.fixture_id for p in P])
pulito = np.array([reg_ok.get(int(f), True) for f in fx])[S["mi"][ev]]
sicuri = (S["stop"][ev] == 0) & (S["t"][ev] <= 41)
lega = S["lega"][ev]
out = {}
for nome_ins, m_ins in (("pulito", pulito), ("regolari_sicuri", sicuri)):
    righe = {}
    for l in sorted(set(lega.tolist())):
        m = m_ins & (lega == l)
        if m.sum() < 500:
            continue
        mi = np.unique(S["mi"][ev][m], return_inverse=True)[1]
        n_p = int(mi.max() + 1)
        pesi = ME.ricampioni(n_p, 500)
        r = {"stati": int(m.sum()), "partite": n_p}
        y = S["y3"][ev][m]
        base = ME.logloss_vett(Z["A0|p3"][m], y)
        r["A0"] = float(base.mean())
        for c in ("A1", "A*", "B1"):
            v = ME.logloss_vett(Z[f"{c}|p3"][m], y)
            d = ME.ic_media(ME.per_partita(v - base, mi, n_p), ME.per_partita(np.ones(m.sum()), mi, n_p), pesi)
            r[c] = float(v.mean())
            r[f"d_{c}"] = [round(x, 5) for x in d]
        righe[int(l)] = r
    out[nome_ins] = righe
    print(nome_ins)
    for l, r in righe.items():
        print(f"| {l} | {r['partite']} | {r['stati']} | {r['A0']:.5f} | {r['A*']:.5f} | {r['B1']:.5f} | "
              f"{r['d_A*'][0]:+.5f} [{r['d_A*'][1]:+.5f}, {r['d_A*'][2]:+.5f}] | "
              f"{r['d_B1'][0]:+.5f} [{r['d_B1'][1]:+.5f}, {r['d_B1'][2]:+.5f}] |")
json.dump(out, open(os.path.join(B.OUT_DEFAULT, "per_lega_test.json"), "w"), indent=1)
