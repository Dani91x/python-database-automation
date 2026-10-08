"""Sonda (sola lettura del codice): stampa le attivita' di Omega di certi tipi,
con l'ora di mercato, per uno scenario. Uso, dalla radice dell'albero:
    python3 sonda_attivita.py <evento> <scenario> <tipo1,tipo2,...> [finestre 0/1]
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())
from Betfair.omega.tools import replay_registrazioni as R  # noqa: E402
from Betfair.stream.backtest import certifica as C  # noqa: E402,F401

ev, sc, tipi = sys.argv[1], sys.argv[2], set(sys.argv[3].split(","))
if len(sys.argv) > 4 and hasattr(R, "FINESTRE_DI_PRODUZIONE"):
    R.FINESTRE_DI_PRODUZIONE = sys.argv[4] == "1"
visti = []
vero_log = R.DbMemoriaOmega.log


def log(self, kind, payload=None, *a, **kw):
    if kind in tipi:
        ora = self.orologio() if callable(getattr(self, "orologio", None)) else "?"
        visti.append((ora, kind, dict(payload or {})))
    return vero_log(self, kind, payload, *a, **kw)


R.DbMemoriaOmega.log = log
dati = os.environ.get("DATI", "_live_raw")
with C._freni_da_banco():
    ref = R.certifica_scenario(ev, data_dir=os.path.abspath(dati), scenario=sc)
print("decisioni", ref.decisioni, "azioni", ref.azioni)
for ora, k, p in visti:
    print(ora, k, {x: p.get(x) for x in ("reason", "testo", "fase", "mercati", "event_id",
                                         "trade_id", "da_secondi", "selection", "price")})
