"""Sonda (sola lettura): tutti i motivi di Mike e la loro sequenza nel tempo
sullo scenario ``base`` della registrazione 35760084, col codice del checkout
corrente (cwd). Serve a spiegare le differenze di referto fra master e la
correzione «attesa del fischio». Uso (dalla radice del checkout da provare):
    python <percorso>/sonda_motivi_mike.py <data_dir> <uscita.json>
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from Betfair.mike import engine as E  # noqa: E402
from Betfair.mike.tools import replay_registrazioni as R  # noqa: E402

data_dir, uscita = sys.argv[1], sys.argv[2]
seq = []
vero = E.decide


def spia(ctx, snap, params):
    d = vero(ctx, snap, params)
    seq.append([round(float(snap.now), 1), str(ctx.state), str(d.state or ""),
                str(getattr(d, "reason", "") or "-")[:90], bool(getattr(snap, "inplay", False)),
                len(d.actions or [])])
    return d


E.decide = spia
from Betfair.stream.backtest import certifica as CF  # noqa: E402

from Betfair.stream.backtest import trasporto as TRA  # noqa: E402

trasp = sys.argv[3] if len(sys.argv) > 3 else "coda"
with CF._freni_da_banco():   # gli stessi freni d'ambiente del banco (LIVE, kill spento)
    with TRA.contesto("mike", trasp):
        ref = R.certifica_scenario("35760084", data_dir=data_dir, scenario="base")
json.dump({"decisioni": ref.decisioni, "motivi": ref.motivi, "seq": seq}, open(uscita, "w"))
print("decisioni", ref.decisioni, "motivi", len(ref.motivi), "seq", len(seq))
