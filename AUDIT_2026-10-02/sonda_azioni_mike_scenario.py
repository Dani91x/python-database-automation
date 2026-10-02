"""Sonda (sola lettura): ogni AZIONE proposta da Mike (con stato, motivo, feed
fresco o no) su uno scenario della registrazione 35760084, col codice del
checkout corrente (cwd). Serve a spiegare, azione per azione, le differenze di
referto fra due versioni (02/10, regressione lettura-dati-ko).
Uso (dalla radice del checkout da provare):
    python <percorso>/sonda_azioni_mike_scenario.py <data_dir> <uscita.json> [scenario]
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from Betfair.mike import engine as E  # noqa: E402
from Betfair.mike.tools import replay_registrazioni as R  # noqa: E402

data_dir, uscita = sys.argv[1], sys.argv[2]
scenario = sys.argv[3] if len(sys.argv) > 3 else "lettura-dati-ko"
azioni = []
seq = []
# finestra opzionale (secondi epoch) in cui scrivere OGNI decisione: argv 4 e 5
FINESTRA = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else None
n ={"decisioni": 0, "a_feed_stantio": 0}
vero = E.decide


def spia(ctx, snap, params):
    d = vero(ctx, snap, params)
    n["decisioni"] += 1
    if not snap.feed_fresh:
        n["a_feed_stantio"] += 1
    if FINESTRA and FINESTRA[0] <= float(snap.now) <= FINESTRA[1]:
        verdi = [l for l in ctx.legs if l.role == "under_green"]
        seq.append({"t": round(float(snap.now), 1), "st": str(ctx.state), "->": str(d.state),
                    "fresh": bool(snap.feed_fresh), "motivo": str(d.reason or "")[:80],
                    "green": [(l.ref, l.status, l.matched) for l in verdi[-2:]]})
    for a in d.actions or []:
        azioni.append({"t": round(float(snap.now), 1), "da": str(ctx.state), "a": str(d.state),
                       "kind": a.kind, "role": a.role, "side": a.side, "size": a.size,
                       "price": a.price, "feed_fresh": bool(snap.feed_fresh),
                       "motivo": str(d.reason or "")[:100]})
    return d


E.decide = spia
from Betfair.stream.backtest import certifica as CF  # noqa: E402
from Betfair.stream.backtest import trasporto as TRA  # noqa: E402

with CF._freni_da_banco():
    with TRA.contesto("mike", "coda"):
        ref = R.certifica_scenario("35760084", data_dir=data_dir, scenario=scenario)
json.dump({"decisioni_referto": ref.decisioni, "azioni_referto": ref.azioni, **n,
           "azioni": azioni, "finestra": seq}, open(uscita, "w"), indent=1)
print("decisioni", ref.decisioni, "azioni", ref.azioni, "spia", n, "azioni spiate", len(azioni))
for a in azioni:
    print(a)
prima = None
for s in seq:  # solo i cambi (motivo, freschezza, gambe)
    chiave = (s["motivo"], s["fresh"], str(s["green"]), s["->"])
    if chiave != prima:
        print(s)
    prima = chiave
