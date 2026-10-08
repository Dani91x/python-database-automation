"""Sonda in sola lettura: registra i payload posizione_di_conto e i verdetti di Mike."""
import sys, json, collections, atexit
from Betfair.stream.backtest import banco_comune as B
import Betfair.mike.service as M
uscita = sys.argv.pop(1)
log_orig = B.DbMemoria.log
voci = []
def log(self, kind, payload=None, event_id=None):
    if kind == "posizione_di_conto":
        voci.append(dict(payload or {}))
    return log_orig(self, kind, payload, event_id)
B.DbMemoria.log = log
ver_orig = M._verdetto_di_conto
verdetti = collections.Counter()
esempi = []
def ver(**kw):
    r = ver_orig(**kw)
    chiuse, parziali, nr = r
    verdetti[(len(chiuse), len(parziali), len(nr) if hasattr(nr, '__len__') else nr)] += 1
    if parziali and len(esempi) < 3:
        esempi.append(parziali)
    return r
M._verdetto_di_conto = ver
def fine():
    c = collections.Counter(v.get("verdetto") for v in voci)
    with open(uscita, "w") as f:
        json.dump({"n_voci": len(voci), "verdetti_voci": dict(c),
                   "chiamate_verdetto (chiuse,parziali,nonritr)": {str(k): v for k, v in verdetti.items()},
                   "prime_voci": voci[:3], "esempi_parziali": esempi}, f, indent=1, default=str)
atexit.register(fine)
from Betfair.stream.backtest import certifica
sys.argv = ["certifica"] + sys.argv[1:]
certifica.main(sys.argv[1:])
