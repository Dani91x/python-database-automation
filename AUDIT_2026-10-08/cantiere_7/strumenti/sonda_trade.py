"""Sonda (sola lettura): le righe omega_trades inserite (ora di mercato, gamba,
selection_id, nome, prezzo). Uso: python3 sonda_trade.py <ev> <sc>"""
import os, sys
sys.path.insert(0, os.getcwd())
from Betfair.omega.tools import replay_registrazioni as R
from Betfair.stream.backtest import certifica as C
vero = R.DbMemoriaOmega.insert_trade
righe = []
def ins(self, t):
    righe.append((self.orologio() if callable(getattr(self, "orologio", None)) else "?",
                  t.get("phase"), t.get("market_id"), t.get("selection_id"), t.get("runner_name"),
                  t.get("side"), t.get("price"), (t.get("meta") or {}).get("fonte_prezzi") ))
    return vero(self, t)
R.DbMemoriaOmega.insert_trade = ins
with C._freni_da_banco():
    ref = R.certifica_scenario(sys.argv[1], data_dir=os.path.abspath(os.environ.get("DATI","/home/user/python-database-automation/.claude/worktrees/agent-adb756da0c06e837d/_live_raw")), scenario=sys.argv[2])
print("decisioni", ref.decisioni, "azioni", ref.azioni)
for r in righe: print(r)
