"""Sonda (sola lettura): i giri con la riga del feed vecchia > 25 s (B4).
Uso: python3 sonda_eta.py <ev> <sc> [finestre 0/1]"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
from Betfair.omega.tools import replay_registrazioni as R
from Betfair.stream.backtest import certifica as C
ev, sc = sys.argv[1:3]
if len(sys.argv) > 3:
    R.FINESTRE_DI_PRODUZIONE = sys.argv[3] == "1"
vero = R.FeedReplay.eta_riga
righe = []
def eta(self, eid):
    out = vero(self, eid)
    if out is not None and out > 25.0:
        r = self.banco.riga(eid) or {}
        p = r.get("payload") or {}
        righe.append((datetime.fromtimestamp(self.banco.ora, tz=timezone.utc).strftime("%H:%M:%S"),
                      round(out), p.get("minute"), p.get("inplay"), p.get("mo_status"),
                      (p.get("flusso") or {}).get("vivo")))
    return out
R.FeedReplay.eta_riga = eta
with C._freni_da_banco():
    ref = R.certifica_scenario(ev, data_dir=os.path.abspath("_live_raw"), scenario=sc)
print("decisioni", ref.decisioni, "azioni", ref.azioni, "giri con riga > 25 s:", len(righe))
for r in righe:
    print(r)
