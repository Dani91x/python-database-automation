"""Sonda (sola lettura del codice): quando un mercato entra/esce dalle finestre
di sottoscrizione del banco (ScannerReplay._ricalcola_voluti), con minuto e
punteggio dello scanner. Uso, dalla radice dell'albero:
    python3 sonda_finestre.py <evento> <scenario> <market_id>[,<market_id>...]
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())
from Betfair.omega.tools import replay_registrazioni as R  # noqa: E402
from Betfair.stream.backtest import banco_comune as BC  # noqa: E402
from Betfair.stream.backtest import certifica as C  # noqa: E402

ev, sc, mids = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
vero = BC.ScannerReplay._ricalcola_voluti
stato = {}
righe = []


def ricalcola(self):
    vero(self)
    e = self.scan.events.get(ev) or {}
    for m in mids:
        dentro = m in self._voluti
        if stato.get(m) != dentro:
            stato[m] = dentro
            righe.append((datetime.fromtimestamp(self._ora_s, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3],
                          m, "DENTRO" if dentro else "FUORI", e.get("minute"),
                          e.get("score_home"), e.get("score_away"), e.get("mo_status"),
                          sorted((self.scan._esposizioni_fonti or {}).get("omega", []) and
                                 [r.get("market_id") for r in self.scan._esposizioni_fonti["omega"]])))


BC.ScannerReplay._ricalcola_voluti = ricalcola
with C._freni_da_banco():
    ref = R.certifica_scenario(ev, data_dir=os.path.abspath(os.environ.get("DATI", "_live_raw")),
                               scenario=sc)
print("decisioni", ref.decisioni, "azioni", ref.azioni)
for r in righe:
    print(r)
