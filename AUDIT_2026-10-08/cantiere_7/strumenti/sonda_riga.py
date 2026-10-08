"""Sonda (sola lettura): la riga di scan che Omega legge in una finestra di
tempo di mercato (blocco flusso, istante di scrittura). Uso:
    python3 sonda_riga.py <evento> <scenario> <HH:MM:SS da> <HH:MM:SS a> [finestre 0/1]
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())
from Betfair.omega.tools import replay_registrazioni as R  # noqa: E402
from Betfair.stream.backtest import certifica as C  # noqa: E402

ev, sc, da, a = sys.argv[1:5]
if len(sys.argv) > 5:
    R.FINESTRE_DI_PRODUZIONE = sys.argv[5] == "1"
vero = R.FeedReplay.righe
righe = []


def hhmmss(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def leggi(self, event_ids):
    t = float(self.banco.ora)
    if da <= hhmmss(t)[:8] <= a:
        r = self.banco.riga(ev)
        p = (r or {}).get("payload") or {}
        righe.append((hhmmss(t), (r or {}).get("updated_at"), p.get("flusso"),
                      (p.get("ht") or {}).get("status"), p.get("minute")))
    return vero(self, event_ids)


R.FeedReplay.righe = leggi
with C._freni_da_banco():
    ref = R.certifica_scenario(ev, data_dir=os.path.abspath(os.environ.get("DATI", "_live_raw")),
                               scenario=sc)
print("decisioni", ref.decisioni, "azioni", ref.azioni)
for r in righe:
    print(r)
