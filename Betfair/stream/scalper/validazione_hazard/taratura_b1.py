"""taratura_b1.py - scelta degli iperparametri di B1 SOLO in validazione (<=2023 -> 2024).

Tre configurazioni, arresto anticipato sul 2024; si tiene quella con la
log-loss 2'+3' piu' bassa. Il test (2025) non si guarda. Scrive
``taratura_b1.json`` accanto ai risultati del banco.
    python -m Betfair.stream.scalper.validazione_hazard.taratura_b1
"""
from __future__ import annotations

import json
import os
import sys
import time

os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"

import numpy as np  # noqa: E402

from Betfair.stream.scalper.validazione_hazard import banco as B  # noqa: E402
from Betfair.stream.scalper.validazione_hazard import metriche as ME  # noqa: E402
from Betfair.stream.scalper.validazione_hazard import modello_b1 as MB  # noqa: E402
from Betfair.stream.scalper.validazione_hazard.forza import lambda_prepartita  # noqa: E402

CONFIG = {
    "base": {},
    "regolarizzato": {"num_leaves": 15, "min_data_in_leaf": 3000, "learning_rate": 0.03},
    "regolarizzato_senza_stagione": {"num_leaves": 15, "min_data_in_leaf": 3000, "learning_rate": 0.03,
                                     "_senza": "stagione"},
}


def main() -> int:
    D = B.carica_tutto(B.CACHE_DEFAULT)
    S, partite = D["S"], D["partite"]
    with open(os.path.join(B.OUT_DEFAULT, "risultati_validazione.json"), encoding="utf-8") as fh:
        val = json.load(fh)
    lam = lambda_prepartita(partite, **val["forza"]["scelta"])
    lh, la = B.vettori_lambda(partite, S, lam)
    tr, ev = B.indici(S, 2023, 2024)
    out = {}
    for nome, par in CONFIG.items():
        par = dict(par)
        senza = par.pop("_senza", None)
        S2 = S
        if senza:
            S2 = dict(S)
            S2["stagione"] = np.zeros_like(S["stagione"])   # variabile neutralizzata
        t0 = time.time()
        mod = MB.addestra_b1(S2, tr, lh, la, n_round=3000, idx_val=ev, parametri=par)
        pr = MB.prevedi_b1(mod, S2, ev, lh, la)
        ll = {k: float(ME.logloss_vett(pr[f"p{k}"], S[f"y{k}"][ev]).mean()) for k in (2, 3)}
        out[nome] = {"parametri": par, "senza": senza, "giri": mod["giri"], "logloss": ll,
                     "somma": ll[2] + ll[3], "secondi": round(time.time() - t0, 1)}
        print(nome, out[nome], file=sys.stderr, flush=True)
    scelta = min(out, key=lambda n: out[n]["somma"])
    out["scelta"] = scelta
    with open(os.path.join(B.OUT_DEFAULT, "taratura_b1.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("scelta", scelta, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
