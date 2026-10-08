"""Sonda (sola lettura): il verdetto di Omega sul flusso (_flusso_della_riga) in
una finestra di tempo di mercato. Uso: python3 sonda_verdetto.py <ev> <sc> <da> <a> [finestre]"""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.getcwd())
from Betfair.omega.tools import replay_registrazioni as R
from Betfair.omega import omega_service as S
from Betfair.stream.backtest import certifica as C
ev, sc, da, a = sys.argv[1:5]
if len(sys.argv) > 5:
    R.FINESTRE_DI_PRODUZIONE = sys.argv[5] == "1"
vero = S._flusso_della_riga
banco = {}
vero_init = R.FeedReplay.__init__
def init(self, b):
    banco["b"] = b
    vero_init(self, b)
R.FeedReplay.__init__ = init
righe = []
def fr(event_id, con_ht):
    out = vero(event_id, con_ht)
    t = float(banco["b"].ora)
    h = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    if da <= h[:8] <= a:
        righe.append((h, con_ht, out.vivo, out.motivo, out.mercati))
    return out
S._flusso_della_riga = fr
with C._freni_da_banco():
    ref = R.certifica_scenario(ev, data_dir="/home/user/python-database-automation/.claude/worktrees/agent-adb756da0c06e837d/_live_raw", scenario=sc)
print("decisioni", ref.decisioni, "azioni", ref.azioni)
for r in righe:
    print(r)
